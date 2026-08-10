# PAYLOV TO'LOVI — to'liq ishlab chiqish rejasi

> Holat: **KOD YOZILDI** (2026-08-10) — PL1–PL7 bajarildi, sinovlar hali
> ishlatilmagan (bazaga ulanish kerak). Qolgani: sinovni yugurtirish,
> Paylov kabinetini sozlash (11.1), jonli 1 000 so'mlik sinov (11.3),
> so'ng `kvota_faol=1` (11.4).
> Poydevor: `DIGITAL_TWIN_REJA.md` 3-bosqich «Pul» (`004_pul.sql`, `pul.py`,
> `tolov.py` — Click/Payme adapterlari allaqachon bor).
> Manba: https://developer.paylov.uz/ru/merchant-configuration va shu
> saytning `merchants/paylov-payment-gateway`, `merchants/statuses`,
> `subscribe/authorization`, `subscribe/ofd/register` sahifalari.
>
> Egasi tasdiqlagan qarorlar (2026-08-10):
> - **Faqat Paylov.** Click/Payme kodi o'chirilmaydi, lekin env sozlanmagan
>   bo'lgani uchun endpointlari 404 bo'lib qoladi (hozirgi holat).
> - **Checkout havolasi + callback.** Karta ma'lumoti bizga tegmaydi.
>   Avtomatik uzaytirish (Subscribe API) — keyingi bosqich, bu rejada yo'q.
> - **Fiskal chek Paylov tomonida.** Biz `fiscalization/register` ni
>   chaqirmaymiz; buni Paylov'dan **yozma tasdiqlash** kerak (P0-savol №5).

---

## 1. Maqsad

Digital Twin platformasi bugun pul olmaydi: `sozlamalar.kvota_faol = '0'`,
Click/Payme sirlari sozlanmagan, UI'dagi «Tanlash» tugmasi esa
`/api/tolov/boshla` ga `usul` yubormagani uchun **400 qaytaradi**. Ya'ni
to'lov yo'li uchdan uch joyda uzilgan.

Bu reja tugagach:

1. Foydalanuvchi «Rejalar» oynasidan planni tanlaydi → Paylov checkout
   sahifasiga o'tadi → to'laydi → ilovaga qaytadi va **obunasi darhol faol**.
2. Paylov `transaction.check` / `transaction.perform` callbacklarini
   bizning serverga yuboradi; obuna faqat **imzosi/auth'i tekshirilgan**
   callbackdan ochiladi.
3. Takroriy callback ikkinchi obuna bermaydi, noto'g'ri summa qabul
   qilinmaydi, to'lov tarixi audit uchun xom holda saqlanadi.
4. `kvota_faol = '1'` yoqilgach bepul 3 promptdan keyin to'lov majburiy
   bo'ladi — va bu to'siq **haqiqatan ham ishlaydi**.

---

## 2. Paylov protokoli — hujjatdan olingan faktlar

### 2.1 Checkout havolasi (biz yaratamiz)

```
https://my.paylov.uz/checkout/create/<base64(qator)>
```

`qator` — `&` bilan ulangan, qiymatlari URL-encoded parametrlar. Hujjatdagi
misol base64'i aynan shunga yechiladi (tekshirildi):

```
merchant_id=2ef4a896-8da2-48a4-9af3-2607e69210ec&amount=500&currency_id=860
&return_url=https%3A%2F%2Fgoogle.com&amount_in_tiyin=True&account.order_id=1233
```

| Parametr | Tur | Biz nima yuboramiz |
|---|---|---|
| `merchant_id` | UUID | `PAYLOV_MERCHANT_ID` |
| `amount` | int | `tolovlar.summa_som` (yoki ×100 — 2.4-bandga qara) |
| `currency_id` | int | `860` (UZS) |
| `return_url` | URL | `{PUBLIC_URL}/?tolov={tashqi_id}` |
| `amount_in_tiyin` | bool | `True`/`False` — 2.4-band |
| `account.order_id` | string | `tolovlar.tashqi_id` (UUID, 5.1-band) |

### 2.2 Callback — bitta URL, JSON-RPC 2.0, Basic Auth

Paylov bizning **bitta** callback URL'ga POST qiladi va login/parolni
merchant kabinetida biz o'zimiz belgilaymiz («Имя пользователя для
callback-авторизации» + parol).

**`transaction.check`** — to'lovdan oldin tekshiruv:

```json
{"jsonrpc":"2.0","id":1234567,"method":"transaction.check",
 "params":{"account":{"order_id":12},"amount":500,
           "amount_tiyin":50000,"currency":860}}
```

**`transaction.perform`** — to'lov bajarilgach:

```json
{"jsonrpc":"2.0","id":1234567,"method":"transaction.perform",
 "params":{"transaction_id":"9bd1a92b-5cce-47c8-a2df-99a20836ab9e",
           "account":{"order_id":12},"amount":500,
           "amount_tiyin":50000,"currency":860}}
```

Ikkalasining javobi bir xil shaklda:

```json
{"jsonrpc":"2.0","id":1234567,"result":{"status":"0","statusText":"OK"}}
```

### 2.3 Status kodlari

| Kod | Ma'nosi | Biz qachon qaytaramiz |
|---|---|---|
| `0` | Success | Hammasi joyida |
| `3` | Maintenance in process | Baza yiqilgan / ichki xato (sabab yozilmaydi) |
| `5` | Invalid amount | Summa yoki valyuta mos emas |
| `303` | Order not found | `order_id` topilmadi, boshqa provayder, yoki muddati o'tgan |
| `+1` | Merchant o'z xato matni | `statusText` = `already_paid`, `order_cancelled`, `order_expired` |

**Diqqat:** `error` obyekti yo'q — xato ham `result.status` orqali
bildiriladi. Auth yiqilganda (login/parol mos emas) HTTP **401** qaytaramiz
(Basic Auth standarti); buni Paylov bilan tasdiqlash kerak (P0-savol №2).

### 2.4 ⚠ Hal qilinmagan noaniqlik: `amount` tiyindami yoki so'mdami

Hujjat ikki joyda ikki xil ko'rinadi:

- `transaction.check` da: `"amount": 500, "amount_tiyin": 50000` →
  demak `amount` **so'mda**, `amount_tiyin` tiyinda.
- Checkout misolida esa: `amount=500` va `amount_in_tiyin=True` →
  bu «500 tiyin = 5 so'm» degani bo'lib chiqadi, holbuki merchant
  konfiguratsiyasida **eng kam summa 500 so'm**. Ya'ni misol o'zi ziddiyatli.

**Yechim:** kodga qattiq yozilmaydi. `PAYLOV_TIYINDA` env bayrog'i:

- `PAYLOV_TIYINDA=1` (boshlang'ich): `amount = summa_som * 100`,
  `amount_in_tiyin=True`.
- `PAYLOV_TIYINDA=0`: `amount = summa_som`, `amount_in_tiyin=False`.

Jonli sinovda 1 000 so'mlik to'lov yaratiladi; Paylov sahifasida **1 000
so'm** ko'rinsa bayroq to'g'ri, **10 so'm** ko'rinsa teskarisiga o'giriladi.
Callback tomonda esa har ikki maydon ham (`amount`, `amount_tiyin`)
mustaqil tekshiriladi — bayroq noto'g'ri bo'lsa ham noto'g'ri summa
**hech qachon** qabul qilinmaydi.

### 2.5 ⚠ base64 ichidagi `/` va `+`

`base64` chiqishi URL **yo'l segmentiga** qo'yiladi. Agar natijada `/`
bo'lsa — havola buziladi. Shuning uchun `_havola` quruvchi:

1. standart base64 yasaydi;
2. natijada `/` yoki `+` bo'lsa, qatorning oxiriga zararsiz `&_=1`, `&_=2`,
   … qo'shib qayta yasaydi (eng ko'pi 50 urinish) — birinchi «toza»
   variant qaytariladi;
3. 50 urinishda ham chiqmasa `urlsafe_b64encode` ga tushadi va log yoziladi.

Bu deterministik va qo'shimcha parametr Paylov tomonidan e'tiborsiz
qoldiriladi (`account.` prefiksisiz bo'lgani uchun hisobga kirmaydi) —
P0-savol №3 bilan tasdiqlanadi.

### 2.6 Bu rejaga KIRMAYDIGAN Paylov imkoniyatlari

| Imkoniyat | Nega hozir emas |
|---|---|
| `POST /merchant/oauth2/token/` (Bearer token) | Faqat quyidagilar uchun kerak — hozir chaqirmaymiz |
| `paymentWithoutRegistration` + `confirmPayment` (karta + OTP) | Karta raqami bizning serverdan o'tadi — PCI yuki, egasi rad etdi |
| Subscribe API (karta biriktirish, avto-uzaytirish) | Keyingi bosqich; obuna hozir qo'lda uzaytiriladi |
| `fiscalization/register` (OFD chek) | Paylov kabineti o'zi bajaradi (yozma tasdiq kerak) |
| `subMerchant` | Bizda sub-merchant sxemasi yo'q |

`PAYLOV_BASE_URL` env sifatida **hozirdan** kiritiladi (qiymatsiz), keyingi
bosqichda kod o'zgarmasin uchun. Hujjatda aniq prod BASE_URL berilmagan —
Paylov'dan so'raladi (P0-savol №4).

---

## 3. Bosh tamoyillar

| # | Tamoyil | Amalda |
|---|---|---|
| P1 | **To'lov yo'li LLM'siz zona** | `tolov.py`/`pul.py` `llm`, `agentlar`, `majlis` ni import qilmaydi. Paylov kodi ham **shu ikki fayl ichida** qoladi — yangi modul ochilmaydi, shunda statik sinov qoidasi o'zgarishsiz kuchda. |
| P2 | **Summa faqat bizdan** | Mijoz ham, Paylov ham summani bizga «aytmaydi». Summa `planlar.oylik_narx_som` dan olinadi, callbackdagi qiymat esa faqat **solishtirish** uchun. Mos kelmasa — status `5`, holat o'zgarmaydi. |
| P3 | **Holatni faqat server o'zgartiradi** | `tolangan` bo'lish, obuna ochilishi/uzayishi — hammasi SQL qoidasi (`pul.tolandi`, `SELECT … FOR UPDATE`). Callback matnidagi hech narsa qarorga ta'sir qilmaydi. |
| P4 | **Idempotentlik — bazada** | `tolovlar(provayder, provayder_id)` unikal indeksi + `paylov_tranzaksiyalar` PK + `pul.tolandi` ichidagi qulf. Uchta qatlamdan biri ishlamay qolsa ham ikkinchi obuna berilmaydi. |
| P5 | **Auth tekshirilmasa — hech narsa** | Basic Auth `hmac.compare_digest` bilan (login ham, parol ham). Yiqilsa 401 va `monitoring.xato` — baza o'qilmaydi ham. |
| P6 | **Xom callback — ishonchsiz matn** | `tolovlar.xom` ga yoziladi, hech qachon promptga kirmaydi, admin panelda faqat ekranlangan matn. |
| P7 | **Yarim sozlangan holat = o'chiq** | `PAYLOV_MERCHANT_ID`/`_LOGIN`/`_PAROL` dan bittasi yetishmasa endpoint 404, `/api/planlar` da `usullar` bo'sh. Yarim sozlangan holda pul olinmaydi. |
| P8 | **Mavjud infra qayta ishlatiladi** | `pul.tolov_yasa`/`tolandi`/`bekor`/`xom_qosh`, `cheklov`, `jobs`, `ui.css/ui.js` — yangi paralel tizim qurilmaydi. |

---

## 4. Foydalanuvchi oqimi

```
[Rejalar oynasi]  ──Tanlash──▶ POST /api/tolov/boshla {plan_id, usul:"paylov"}
                                     │  tolovlar: kutilmoqda, tashqi_id=UUID
                                     ▼
                          location.href = my.paylov.uz/checkout/create/<b64>
                                     │
                     ┌───────────────┴────────────────┐
                     ▼                                ▼
        Paylov → POST /tolov/paylov          user "Ortga" bosdi
        transaction.check  → status 0        (to'lov bo'lmadi)
        transaction.perform→ obuna ochildi          │
                     │                              │
                     ▼                              ▼
        return_url: /?tolov=<tashqi_id>   tolov 24 soatdan keyin
                     │                    `tolov_tozala` job bilan bekor
                     ▼
        UI: GET /api/tolov/<tashqi_id> ni 2 s dan 15 marta so'raydi
            tolangan → "✅ Obuna faollashdi" + holat yangilanadi
            kutilmoqda → "To'lov tekshirilmoqda…" (callback kechikishi normal)
            bekor → "To'lov amalga oshmadi"
```

Parallel ravishda `_obuna_xabar()` Telegram'ga **statik shablon** yuboradi
(mavjud kod, o'zgarmaydi).

---

## 5. Ma'lumotlar modeli — `migratsiyalar/010_paylov.sql`

Additiv: faqat yangi ustun/jadval, `IF NOT EXISTS`, eski kod ta'sirlanmaydi.

### 5.1 `tolovlar` ga ikki ustun

```sql
-- order_id sifatida ketma-ket id emas, UUID: tashqi tomon boshqa
-- foydalanuvchining buyurtmasini taxmin qila olmaydi va bizning
-- to'lov hajmimiz havolada ko'rinmaydi.
ALTER TABLE tolovlar ADD COLUMN IF NOT EXISTS tashqi_id uuid
  NOT NULL DEFAULT gen_random_uuid();
CREATE UNIQUE INDEX IF NOT EXISTS idx_tolov_tashqi ON tolovlar(tashqi_id);

-- Kutilayotgan to'lovning amal qilish muddati (default 24 soat).
ALTER TABLE tolovlar ADD COLUMN IF NOT EXISTS muddat timestamptz;
CREATE INDEX IF NOT EXISTS idx_tolov_muddat
  ON tolovlar(muddat) WHERE holat IN ('kutilmoqda','tayyorlangan');
```

### 5.2 `paylov_tranzaksiyalar`

```sql
CREATE TABLE IF NOT EXISTS paylov_tranzaksiyalar(
  id           text PRIMARY KEY,        -- Paylov transaction_id (UUID)
  tolov_id     bigint NOT NULL REFERENCES tolovlar(id) ON DELETE CASCADE,
  summa_som    bigint NOT NULL,
  summa_tiyin  bigint NOT NULL,
  valyuta      int    NOT NULL DEFAULT 860,
  holat        text   NOT NULL DEFAULT 'bajarildi',  -- bajarildi|bekor
  vaqt         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_paylov_tolov ON paylov_tranzaksiyalar(tolov_id);
```

PK ustidagi `INSERT … ON CONFLICT DO NOTHING` — takroriy `perform` ni
bazaning o'zi ushlaydi (2-qatlam idempotentlik).

### 5.3 Sozlamalar

```sql
INSERT INTO sozlamalar(kalit, qiymat, izoh) VALUES
  ('tolov_muddat_soat', '24',
   'Kutilayotgan to''lov necha soatdan keyin avtomatik bekor qilinadi')
ON CONFLICT (kalit) DO NOTHING;
```

`planlar` narxlari o'zgarmaydi — ular admin paneldan deploysiz sozlanadi
(11.2-bandga qara: prodga chiqishdan oldin narxni egasi tasdiqlaydi).

---

## 6. Kod o'zgarishlari

| Fayl | O'zgarish | Taxminiy hajm |
|---|---|---|
| `migratsiyalar/010_paylov.sql` | **yangi** — 5-bo'lim | ~30 qator |
| `platforma/tolov.py` | **Paylov bo'limi**: `paylov_sozlangan`, `_paylov_havola`, `_paylov_auth_ok`, `_paylov_tolov`, `POST /tolov/paylov`, `_pl_check`, `_pl_perform`; `sozlama_holati` ga `paylov` | ~200 qator |
| `platforma/tolov.py` | `/api/tolov/boshla`: `usul` bo'sh bo'lsa yagona sozlangan usul avtomatik; `muddat` yoziladi; havola quruvchi tanlanadi | ~25 qator |
| `platforma/tolov.py` | **yangi** `GET /api/tolov/{tashqi_id}` — faqat o'z to'lovi, `{holat, plan_nom, summa_som}` | ~15 qator |
| `platforma/pul.py` | `tolov_yasa` ga `muddat` argumenti; `tolov_tashqi_ol(uuid)`; `tolov_tozala()` (muddati o'tganlarni bekor qilish) | ~35 qator |
| `platforma/worker.py` | `@handler("tolov_tozala")` + `_davriy_ish` ga `_navbatga("tolov_tozala", "55 minutes", 7, 120)` | ~10 qator |
| `platforma/web/index.html` | `usullar` bir nechta bo'lsa usul tanlash; `?tolov=` ni ushlab natija oynasi + poll | ~60 qator |
| `platforma/web/admin.html` + `admin.py` | To'lovlar jadvalida provayder filtri, xom callbackni ko'rish (ekranlangan), qo'lda bekor qilish tugmasi | ~50 qator |
| `platforma/tayyorlik.py` | Paylov env tekshiruvi; `kvota_faol=1` bo'lsa `muhim=True` | ~15 qator |
| `platforma/sinov_paylov.py` | **yangi** — 10-bo'lim | ~350 qator |
| `platforma/README.md`, `CLAUDE.md` | Hujjat yangilanishi (`CUTOVER.md` — tarixiy hujjat, tegilmaydi; Paylov cutoveri shu faylning 11-bo'limi) | ~60 qator |

**Yangi modul ochilmaydi** — Paylov kodi `tolov.py` ichida Click/Payme
yonida bo'lim bo'lib turadi (P1 tamoyili).

### 6.1 Env o'zgaruvchilari (`.env.platforma`, gitga tushmaydi)

```
PAYLOV_MERCHANT_ID=<UUID>
PAYLOV_CALLBACK_LOGIN=<kabinetda belgilangan login>
PAYLOV_CALLBACK_PAROL=<kabinetda belgilangan parol>
PAYLOV_TIYINDA=1                                   # 2.4-band
PAYLOV_CHECKOUT=https://my.paylov.uz/checkout/create/
PAYLOV_VALYUTA=860
PAYLOV_IP=                                         # bo'sh = IP filtri o'chiq
PAYLOV_BASE_URL=                                   # kelajak uchun, hozir bo'sh
```

---

## 7. Callback holat mashinasi

`POST /tolov/paylov` — yagona kirish. Tartib: **auth → JSON → metod →
to'lovni topish → summa → holat**. Har bosqich yiqilsa keyingisiga o'tilmaydi.

| Vaziyat | `check` javobi | `perform` javobi | Baza |
|---|---|---|---|
| Basic Auth yo'q / noto'g'ri | HTTP 401 | HTTP 401 | o'zgarmaydi, `monitoring.xato` |
| Paylov sozlanmagan | HTTP 404 | HTTP 404 | — |
| JSON o'qilmadi / metod noma'lum | `3` | `3` | — |
| `order_id` UUID emas / topilmadi | `303` | `303` | — |
| To'lov boshqa provayderniki | `303` | `303` | — |
| `muddat < now()` va hali to'lanmagan | `+1 order_expired` | `+1 order_expired` | to'lov `bekor` |
| `amount`/`amount_tiyin`/`currency` mos emas | `5` | `5` | **o'zgarmaydi** |
| To'lov `bekor` | `+1 order_cancelled` | `+1 order_cancelled` | — |
| To'lov `tolangan`, **shu** `transaction_id` | `+1 already_paid` | `0` (idempotent) | — |
| To'lov `tolangan`, **boshqa** `transaction_id` | `+1 already_paid` | `+1 already_paid` | `monitoring.xato` |
| Hammasi joyida | `0` + holat `tayyorlangan` | `0` + `pul.tolandi` → obuna + TG | `paylov_tranzaksiyalar` qatori |
| Ichki istisno | `3` | `3` | tranzaksiya rollback |

**`check`siz kelgan `perform`** to'liq ishlaydi — Paylov kabinetda faqat
`perform` yoqilgan bo'lsa ham obuna ochiladi.

**Bekor/qaytarish (refund)** protokolda yo'q: Paylov kabinetidan qo'lda
qilinadi. Admin panelda «Bekor qilish» tugmasi `pul.bekor()` ni chaqiradi
(to'lovni ham, undan ochilgan obunani ham yopadi) — kabinetdagi refunddan
keyin admin shuni bosadi. Bu qadam `README.md` da yozib qo'yiladi.

---

## 8. API yuzasi

| Metod | Yo'l | Kim | Nima |
|---|---|---|---|
| GET | `/api/planlar` | user | `usullar` ro'yxatiga `"paylov"` qo'shiladi |
| POST | `/api/tolov/boshla` | user | `{plan_id, usul?}` → `{tolov_id, tashqi_id, summa_som, havola}` |
| GET | `/api/tolov/{tashqi_id}` | user (**faqat o'zi**) | `{holat, plan_nom, summa_som}` — qaytish sahifasi uchun |
| GET | `/api/tolovlarim` | user | o'zgarmaydi |
| POST | `/tolov/paylov` | **Paylov** | JSON-RPC callback (Basic Auth) |
| POST | `/api/admin/tolov/{id}/bekor` | admin | qo'lda bekor + obunani yopish |

`web.py:83` dagi statik yo'l filtri `/tolov/` prefiksini allaqachon
o'tkazadi — o'zgartirish shart emas.

**Cheklov (`cheklov.py`):** `"tolov": (10, 60)` mavjud — o'zgarmaydi.
Callback endpointiga user-cheklov qo'yilmaydi (Paylov'ni o'zimiz
bloklab qo'ymaslik uchun), lekin `PAYLOV_IP` bo'sh bo'lmasa faqat
ro'yxatdagi IP'lar o'tkaziladi.

**CSP:** checkout — `location.href` bilan **navigatsiya**, `fetch` emas.
`connect-src 'self'` va `form-action 'self'` buzilmaydi, CSP o'zgarmaydi.

---

## 9. Xavfsizlik — Lethal Trifecta xaritasi

| Oyoq | Bu oqimda | Uzilish nuqtasi |
|---|---|---|
| Shaxsiy ma'lumot | `userlar`, `obunalar`, `tolovlar` | To'lov kodi bu ma'lumotni **modelga umuman ko'rsatmaydi** |
| Ishonchsiz kontent | Paylov callbacki, `return_url` ga qaytgan query | `tolovlar.xom` ga yoziladi, promptga kirmaydi; UI'da ekranlangan matn |
| Tashqi kanal | Telegram xabari | Matn **faqat statik shablon** + DB'dagi plan nomi (`_qoch` bilan ekranlangan) |

Qo'shimcha nazorat:

- `tolov.py` `llm`/`agentlar`/`majlis` ni import qilmasligi **statik sinov**
  bilan tekshiriladi (10-bo'lim, S21).
- Basic Auth `hmac.compare_digest` — vaqt bo'yicha sizib chiqish yo'q.
- `order_id` — UUID: boshqa foydalanuvchining buyurtmasini taxmin qilib
  bo'lmaydi.
- Summa uch marta tekshiriladi: so'mda, tiyinda, valyutada.
- Har rad etilgan callback `monitoring.xato` orqali adminga boradi
  (`jimgina=True` bilan — spam bo'lmasin, kalit bo'yicha guruhlanadi).

---

## 10. Sinovlar — `platforma/sinov_paylov.py`

Ishga tushirish: `python -m platforma.sinov_paylov`. FastAPI `TestClient` +
haqiqiy baza (sinov userи va to'lovlari yaratiladi, oxirida tozalanadi).
`tg.matn_yubor` monkeypatch bilan to'xtatiladi — sinov Telegram'ga
xabar yubormaydi.

**Statik va birlik:**

| # | Sinov |
|---|---|
| S1 | `tolov.py` va `pul.py` da `llm`/`agentlar`/`majlis` importi yo'q |
| S2 | `_paylov_havola` base64'i dekodlanganda kutilgan qatorga teng |
| S3 | `return_url` havolada URL-encoded (`%3A%2F%2F`) |
| S4 | `PAYLOV_TIYINDA=1` → `amount = som*100`, `=0` → `amount = som` |
| S5 | base64'da `/` yoki `+` chiqmaydi (50 ta ketma-ket to'lov id bilan) |
| S6 | Paylov sozlanmagan bo'lsa `/tolov/paylov` → 404 |

**Protokol (callback):**

| # | Sinov | Kutilgan |
|---|---|---|
| S7 | Auth sarlavhasiz | 401, holat o'zgarmadi |
| S8 | Noto'g'ri parol | 401 |
| S9 | Noto'g'ri login, to'g'ri parol | 401 |
| S10 | Noma'lum metod | `3` |
| S11 | Buzuq JSON | `3` |
| S12 | `check`: order topilmadi | `303` |
| S13 | `check`: boshqa provayder to'lovi | `303` |
| S14 | `check`: summa noto'g'ri (so'm) | `5`, holat `kutilmoqda` |
| S15 | `check`: `amount_tiyin` mos emas | `5` |
| S16 | `check`: valyuta 840 | `5` |
| S17 | `check`: OK | `0`, holat `tayyorlangan` |
| S18 | `check`: muddati o'tgan | `+1 order_expired`, holat `bekor` |
| S19 | `perform`: OK | `0`, `tolangan`, obuna faol, `tugash ≈ now+30d` |
| S20 | `perform`: **takroriy, bir xil** `transaction_id` | `0`, obuna **bitta** |
| S21 | `perform`: to'langan to'lovga boshqa `transaction_id` | `+1 already_paid`, obuna o'zgarmadi |
| S22 | `perform`: `check`siz to'g'ridan-to'g'ri | `0`, obuna ochildi |
| S23 | `perform`: summa noto'g'ri | `5`, holat `tayyorlangan` (o'zgarmadi) |
| S24 | `perform`: bekor qilingan to'lovga | `+1 order_cancelled` |
| S25 | Xom callback `tolovlar.xom` ga yozildi (2 ta yozuv) |
| S26 | **Konkurent** 2 ta `perform` (thread) | bitta obuna, bitta TG xabari |
| S27 | Faol obunasi bor userga ikkinchi to'lov | obuna **uzaydi**, yangi qator yaratilmadi |

**Oqim (uchdan-uchgacha):**

| # | Sinov |
|---|---|
| S28 | `/api/tolov/boshla` `usul`siz → yagona sozlangan usul olinadi, `havola` qaytadi |
| S29 | `/api/tolov/boshla` kirmagan userdan → 401 |
| S30 | `/api/tolov/{tashqi_id}` boshqa userning to'lovi → 404 |
| S31 | Kvota darvozasi: bepul 0 → `pul.tekshir` rad etadi; `perform` dan keyin ruxsat beradi |
| S32 | `tolov_tozala` job: muddati o'tgan `kutilmoqda` → `bekor`; yangisi — tegilmaydi |

**Mezon:** hammasi yashil. Bittasi ham qizil bo'lsa prodga chiqilmaydi.

**Bazaga tegish qoidasi (amalda qo'shildi).** Skript lokalda ham PROD bazaga
ulanishi mumkin, shuning uchun:

- o'z sinov useri (`tg_id = -999001/-999002`) va plani (`kod='sinov_paylov'`)
  bilan ishlaydi, boshida va oxirida hammasini o'chiradi;
- **hech qanday job yaratmaydi** — bulutdagi worker pul sarflamaydi;
- **`sozlamalar.kvota_faol` ga TEGMAYDI.** S31 dastlab shu kalitni yoqib
  sinash uchun rejalashtirilgan edi; bu xavfli — skript kalit yoqilgan
  paytda uzilib qolsa **prodda hamma foydalanuvchi bloklanardi**. Buning
  o'rniga `pul.kvota_faolmi` jarayon ichida almashtiriladi: aynan o'sha
  darvoza mantig'i sinaladi, umumiy holat esa tegilmaydi;
- Telegram'ga xabar ketmaydi (`_obuna_xabar` va `monitoring.xato` sanagichga
  almashtiriladi);
- **qolgan yagona ta'sir:** S28 `/api/tolov/boshla` ni sinash uchun sinov
  plani `faol=true` bo'lishi shart, shuning uchun sinov davomida (~10 soniya)
  «Sinov (Paylov) — 1 000 so'm» jonli «Rejalar» ro'yxatida ko'rinadi. Skript
  buni boshida ogohlantiradi; jonli bazada kam bandlik paytida yugurtiring.

Sinovga Paylov'ning HAQIQIY kalitlari kerak emas — skript o'z sinov
qiymatlarini `os.environ` ga qo'yadi va jarayonda Click/Payme'ni o'chiradi
(«yagona usul» xulqi tekshirilishi uchun).

---

## 11. Prodga chiqish

### 11.1 Paylov kabinetida sozlash

1. Merchant nomi, logotip (PNG), kategoriya — «Онлайн-сервисы».
2. Chek maydoni: `order_id`.
3. Tranzaksiya chegaralari: min **1 000** so'm, max **1 000 000** so'm
   (planlarimiz 149 000 / 449 000 — orasida).
4. Callback URL: `https://twin.bmslab.uz/tolov/paylov`
5. Callback login/parol — kuchli, tasodifiy; faqat `.env.platforma` da.
6. Yoqiladigan metodlar: **`transaction.check` + `transaction.perform`**
   (ikkalasi — `check` bizga «bu buyurtma haqiqiy» deb oldindan aytadi).

### 11.2 Deploydan oldin

```powershell
python -m platforma.pg                # 010_paylov.sql qo'llanadi
python -m platforma.sinov_paylov      # hammasi yashil
python -m platforma.tayyorlik         # Paylov bo'limi yashil
robocopy ..\platforma ..\deploy_platforma\platforma /MIR /XD __pycache__ eski_v1
```

Serverda (`/opt/twin`): `app.eski` zaxira → `tar -xzf` →
`docker compose build && up -d` → `python -m platforma.pg` (010 migratsiya).

⚠ `.env.platforma` ga PAYLOV_* qo'shilgach konteyner **qayta ishga
tushirilishi** shart (env faqat startda o'qiladi).

### 11.3 Jonli sinov (`kvota_faol` hali `0`)

1. Vaqtincha `planlar` ga `sinov` kodli 1 000 so'mlik faol plan qo'shiladi.
2. Egasi o'z kartasi bilan to'laydi.
   - Paylov sahifasida summa **1 000 so'm** ekanini tasdiqlash → 2.4-band.
   - Callback keldi, `tolovlar.holat='tolangan'`, obuna faol.
   - `/?tolov=` sahifasi «✅ Obuna faollashdi» ko'rsatdi.
   - Telegram xabari keldi.
3. Paylov kabinetidan **refund** qilinadi → admin panelda «Bekor qilish».
4. Fiskal chek: Paylov kabinetida/SMS'da chek paydo bo'lganini tekshirish
   (P0-savol №5 ning amaliy isboti).
5. `sinov` plani `faol=false` qilinadi.

### 11.4 Pulni yoqish (alohida kun)

Bu **biznes qadami**, texnik emas — shuning uchun deploydan ajratilgan:

1. Egasi `planlar` narxini tasdiqlaydi (hozirgilari «TAXMINIY» deb yozilgan).
2. Mavjud faol foydalanuvchilarga Telegram orqali **oldindan** xabar.
3. `sozlamalar.kvota_faol = '1'`.
4. Birinchi sutka: `/api/admin/moliya` va `monitoring` kuzatiladi;
   noto'g'ri rad etishlar bo'lsa `kvota_faol` bir soniyada `'0'` ga
   qaytariladi (deploy shart emas).

---

## 12. Bosqichlar va «tayyor» mezonlari

| Bosqich | Ish | «Tayyor» mezoni |
|---|---|---|
| **PL1** | `010_paylov.sql` + `pul.py` yordamchilari | Migratsiya lokal va prod baza nusxasida toza qo'llanadi; eski to'lovlarga `tashqi_id` berildi |
| **PL2** | `_paylov_havola` + `/api/tolov/boshla` | S2–S5, S28–S29 yashil; qo'lda yasalgan havola Paylov sahifasini ochadi |
| **PL3** | Callback: auth + `check` | S6–S18 yashil |
| **PL4** | Callback: `perform` + idempotentlik | S19–S27 yashil |
| **PL5** | UI: usul tanlash, `?tolov=` natija oynasi | Brauzerda uchdan-uchgacha oqim ko'zdan o'tkazildi |
| **PL6** | Admin: filtr, xom ko'rish, qo'lda bekor; `tolov_tozala` job | S32 yashil; admin panelda refunddan keyingi bekor ishlaydi |
| **PL7** | `tayyorlik.py`, hujjatlar, deploy | `tayyorlik` yashil; 11.3 jonli sinov muvaffaqiyatli |
| **PL8** | `kvota_faol=1` | 11.4 bajarildi, birinchi haqiqiy obuna sotildi |

**Amalda topilgan qo'shimcha nosozlik (PL5 da tuzatildi).** `rejalarOyna`
`/api/planlar` javobini massiv deb ishlatardi (`planlar.forEach`), holbuki
endpoint `{planlar, usullar, holat}` obyektini qaytaradi — «Rejalar» oynasi
har doim «Ochilmadi» xato holatini ko'rsatgan. Endi javob to'g'ri ochiladi
va bo'sh holat ham `boshmi()` orqali to'g'ri aniqlanadi.

---

## 13. Risklar va qarshi choralar

| Risk | Ehtimol | Qarshi chora |
|---|---|---|
| `amount` tiyin/so'm chalkashligi → mijozdan 100× kam yoki ko'p olinadi | **Yuqori** | `PAYLOV_TIYINDA` bayrog'i + 1 000 so'mlik jonli sinov + callbackda uch tomonlama summa tekshiruvi (noto'g'ri bo'lsa pul qabul qilinmaydi) |
| base64'dagi `/` havolani buzadi | O'rta | 2.5-banddagi «toza variant» algoritmi + S5 sinovi |
| `+1` status formati boshqacha (masalan `"1"` yoki `-1`) | O'rta | P0-savol №1; sandbox javobiga qarab bitta konstanta o'zgaradi |
| Callback keldi, lekin biz 500 qaytardik → Paylov qayta yubormasa pul «osilib» qoladi | O'rta | Ichki xatoda `3` (maintenance) qaytariladi — bu «keyinroq urin» signali; qo'shimcha: admin panelda «to'langan lekin obunasiz» hisoboti |
| Paylov'da to'langan, bizda yo'q (sverka farqi) | O'rta | Kunlik `moliya` hisobotida `tolovlar` soni Paylov kabineti bilan solishtiriladi; P0-savol №6 — tranzaksiyalar ro'yxati API'si bormi |
| `kvota_faol=1` yoqilishi bilan mavjud userlar bloklanadi | Yuqori | 11.4: oldindan xabar + bir soniyada orqaga qaytarish imkoni |
| Callback URL'ni tashqi tomon topib, so'rov yog'diradi | Past | Basic Auth + ixtiyoriy `PAYLOV_IP` filtri + auth yiqilganda bazaga umuman tegilmaydi |
| Fiskal chek Paylov tomonida emas ekan | O'rta | P0-savol №5; kerak bo'lsa `fiscalization/register` alohida bosqich sifatida qo'shiladi (~1 kun) |

---

## 14. Hajm bahosi

| Bosqich | Vaqt |
|---|---|
| PL1–PL2 (baza, havola) | 0.5 kun |
| PL3–PL4 (callback + sinovlar) | 1.5 kun |
| PL5–PL6 (UI, admin, job) | 1 kun |
| PL7 (tayyorlik, hujjat, deploy, jonli sinov) | 0.5 kun |
| **Jami** | **~3.5 kun** |

PL8 (`kvota_faol=1`) — texnik ish emas, egasi qarori.

---

## 15. Paylov'ga yoziladigan P0-savollar

Bularsiz ham kod yoziladi (barchasi env/konstantaga chiqarilgan), lekin
**jonli pul olishdan oldin** javob kelishi shart:

1. `+1` («merchant o'z xatosi») statusi javobda **aynan qanday** yoziladi —
   `"status": "+1"` mi, `"1"` mi, son `-1` mi? `statusText` uchun format bormi?
2. Callback auth yiqilganda merchant nima qaytarishi kerak — HTTP 401 mi,
   yoki `200` + biror status kodmi?
3. Checkout base64 payload'iga notanish parametr (`&_=1`) qo'shilsa
   e'tiborsiz qoldiriladimi?
4. API uchun prod va sandbox **BASE_URL** qiymatlari (kelajakdagi
   fiskalizatsiya/obuna uchun).
5. **Fiskal chek (OFD)** merchant kabinetida avtomatik ro'yxatdan
   o'tadimi, yoki `fiscalization/register` ni biz chaqirishimiz shartmi?
6. Tranzaksiyalar ro'yxati (sverka) uchun API bormi, yoki faqat kabinetdan
   eksport qilinadimi?
7. Callback yetib bormasa Paylov qayta urinadimi — necha marta, qanday
   oraliqda?
8. Callback so'rovlari chiqadigan **IP manzillar** ro'yxati.

---

## 16. Ish paytidagi eslatma

`platforma/web/index.html` da 5 ta NUL bayt bor — bu **buzilish emas**:
markdown renderi kod bloklarini vaqtincha belgilash uchun `"\n\x00B<n>\x00\n"`
sentinelini ishlatadi. Oqibati shuki, `grep`/`file` bu faylni ikkilik deb
biladi va oddiy qidiruv vositalari uni o'tkazib yuboradi. PL5 bosqichida
index.html ni tahrirlashda buni yodda tuting (`grep -a` yoki bevosita
o'qish kerak).
