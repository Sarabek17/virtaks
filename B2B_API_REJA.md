# B2B API — reja

> **Holat: TO'LIQ BAJARILDI** (2026-09-09) — 15-bo'limga qarang.
> 0-5 bosqich, admin UI, oylik hisobot, ustoz ulushi, jonli sinov —
> hammasi yozildi va sinovdan o'tdi (`sinov_b2b` 72/72, `sinov_jonli` 15/15).

Virtaks bilimini **boshqa kompaniyalarga API orqali sotish**: hamkor
(B2B mijoz) o'z ilovasiga bizning twinni ulaydi, o'z mijozlariga xizmat
ko'rsatadi, hisobni esa **hamkorning o'zi to'laydi** — biz sarfni uning
kompaniyasiga yig'ib boramiz.

```
  BIZ                          HAMKOR (B2B)                 HAMKORNING MIJOZI
  ─────────────────────────    ────────────────────────     ──────────────────
  twin bilimi + API        ──▶ o'z ilovasi/boti         ──▶ savol beradi
  sarfni hisoblab boramiz  ◀── API kalit bilan so'rov   ◀── javob + iqtibos
  hamkorga hisob chiqaramiz    o'z narxida sotadi           hamkorga to'laydi
```

Uslub namunasi: `MENTOR_REJA.md`. Amaldagi sxema: `002_yadro.sql`,
`004_pul.sql`. Xavfsizlik ramkasi: `CLAUDE.md` → «Qat'iy qoidalar».

---

## 1. Nima uchun

Hozir mahsulot faqat **B2C**: odam Telegram orqali kiradi, o'ziga obuna
oladi. Bu model bilan bitta ustozning bilimi bitta odamga sotiladi.

B2B da bir hamkor yuzlab mijozini olib keladi va **bitta shartnoma** bilan
to'laydi. Bizga: sotuv sikli qisqa, marketing hamkorda, hisob bitta.
Hamkorga: tayyor «raqamli ustoz» qatlami, o'z brendida.

Texnik jihatdan bu yangi mahsulot emas — mavjud `yordamchi.py` yadrosining
ustiga **ikkita yangi qatlam**: (a) tashkilot bo'yicha izolyatsiya,
(b) tashkilot bo'yicha hisob.

---

## 2. Bosh qarorlar

Bu bo'lim keyinchalik «nega shunday?» degan savolga javob beradi.

### 2.1. Hamkorning mijozi — bizning `userlar` jadvalida, lekin soyada

Yangi jadval ochilmaydi. Hamkorning har mijozi `userlar` da oddiy qator
bo'ladi, farqi ikki ustunda: `tashkilot_id` va `tashqi_id` (hamkorning
o'z bazasidagi ID si).

**Nega shunday**: suhbat, iqtibos, profil, dars, maqsad — hammasi
`user_id` ga bog'langan. Alohida «api_userlar» jadvali ochilsa, butun kod
ikki xil foydalanuvchi turini bilishi kerak bo'lardi. Bir ustun qo'shish
esa hech nimani buzmaydi.

**Cheklov qat'iy**: `UNIQUE(tashkilot_id, tashqi_id)` — hamkor o'z
mijozini nechchi marta yuborsa ham bitta yozuv bo'ladi, va **boshqa
tashkilotning mijozini ko'ra olmaydi**.

### 2.2. Hamkor twinni tanlay olmaydi — biz beramiz

`tashkilot_twin` jadvali: qaysi tashkilot qaysi twindan foydalanishi
mumkin. API so'rovida kelgan `twin` qiymati shu ro'yxatda bo'lmasa —
`404`, «bunday twin yo'q» (403 emas: mavjudligini ham bildirmaymiz).

Bu `twin_ruxsat` ni **almashtirmaydi, ustiga qo'shiladi**. CLAUDE.md
qoidasi: `twin_ruxsat` chegarasi hech qachon yumshamaydi.

### 2.3. Pul: sarf hamkorga yoziladi, mijozga emas

`xarajatlar` jadvali allaqachon har LLM chaqiruvini yozadi. Unga
`tashkilot_id` va `hisob_usd` ustunlari qo'shiladi:

| Ustun | Ma'no | Kim ko'radi |
|---|---|---|
| `narx_usd` | bizning haqiqiy tannarximiz (bor) | faqat admin |
| `hisob_usd` | hamkordan olinadigan summa = `narx_usd × ustama` | hamkor |

Hamkor **hech qachon** `narx_usd` ni ko'rmaydi — bu bizning marja siri.

**Nega ikki ustun, foizni keyin hisoblamaymiz**: ustama vaqt o'tib
o'zgaradi (shartnoma qayta ko'riladi). Agar hisobni «hozirgi ustama ×
eski sarf» bilan hisoblasak, o'tgan oyning hisobi bugun o'zgarib ketardi.
Shuning uchun ustama **sarf yozilayotgan paytda qotiriladi** — xuddi
uy vazifasi rubrikasi qotirilgani kabi (`MENTOR_REJA.md`).

### 2.4. Oldindan to'lov (prepaid) — standart

`tashkilotlar.balans_usd` — hamkor to'lagan, hali sarflanmagan summa.
Har so'rovdan keyin `hisob_usd` shundan yechiladi.

- balans `ogohlantirish_usd` dan pasaysa → hamkorga xabar + `X-Balans-Ogoh` sarlavhasi
- balans ≤ 0 → **`402 Payment Required`**, so'rov LLM ga umuman bormaydi

**Nega prepaid**: qarz undirish biznesi bizda yo'q. Postpaid kerak bo'lgan
yirik hamkor uchun `kredit_chegara_usd` bor — balans shu qiymatgacha
minusga tushishi mumkin (admin qo'lda ochadi, standart 0).

### 2.5. v1 da faqat CHAT — mentor/maqsad/tizim keyin

API ning birinchi versiyasi mahsulotning **o'zagini** beradi: savol →
manbaga tayangan javob → iqtibos → audio fragment.

Mentorlik, maqsad halqasi va biznes tizimlashtirish — bular ko'p qadamli
**holat mashinalari** (`oquv.py`, `maqsad.py`, `tizim.py`). Ularni API ga
chiqarish uchun holatni hamkor tomonida ko'rsatish, webhook bilan
xabardor qilish va UI berish kerak — bu alohida katta ish.

v1 tez chiqadi va sotiladi; v2 rejasi 11-bo'limda.

---

## 3. Ma'lumot modeli (`013_b2b.sql`)

Migratsiya **additiv** — faqat yangi jadval va ustun, eski kod ta'sirlanmaydi.

```sql
-- ------------------------------------------------------------ tashkilotlar
CREATE TABLE IF NOT EXISTS tashkilotlar(
  id                  bigserial PRIMARY KEY,
  nom                 text NOT NULL,
  slug                text NOT NULL UNIQUE,
  aloqa_email         text NOT NULL DEFAULT '',
  aloqa_tg            bigint,                        -- ogohlantirishlar shu yerga
  -- pul
  ustama              numeric(6,3) NOT NULL DEFAULT 3.000,  -- tannarxga koeffitsient
  balans_usd          numeric(14,6) NOT NULL DEFAULT 0,
  kredit_chegara_usd  numeric(14,6) NOT NULL DEFAULT 0,     -- postpaid uchun
  ogohlantirish_usd   numeric(14,6) NOT NULL DEFAULT 5,
  -- cheklovlar
  sekund_limit        int NOT NULL DEFAULT 5,        -- bir vaqtda ochiq oqim
  daqiqa_limit        int NOT NULL DEFAULT 60,       -- daqiqasiga so'rov
  oylik_chegara_usd   numeric(14,6) NOT NULL DEFAULT 0,     -- 0 = cheksiz
  faol                boolean NOT NULL DEFAULT true,
  izoh                text NOT NULL DEFAULT '',
  yaratilgan          timestamptz NOT NULL DEFAULT now()
);

-- --------------------------------------------------------------- kalitlar
-- Kalitning O'ZI saqlanmaydi. Faqat prefiks (qidiruv uchun) va argon2 xeshi.
CREATE TABLE IF NOT EXISTS api_kalitlar(
  id            bigserial PRIMARY KEY,
  tashkilot_id  bigint NOT NULL REFERENCES tashkilotlar(id) ON DELETE CASCADE,
  nom           text NOT NULL DEFAULT '',        -- "prod", "sinov", "mobil ilova"
  prefiks       text NOT NULL UNIQUE,            -- vk_live_7f3a2c
  hash          text NOT NULL,                   -- argon2(sir)
  huquqlar      text[] NOT NULL DEFAULT '{savol,suhbat,fragment,hisob}',
  ip_oq         text[] NOT NULL DEFAULT '{}',    -- bo'sh = filtr o'chiq
  faol          boolean NOT NULL DEFAULT true,
  muddat        timestamptz,                     -- NULL = muddatsiz
  oxirgi_ishlatilgan timestamptz,
  yaratilgan    timestamptz NOT NULL DEFAULT now(),
  yaratgan_id   bigint REFERENCES userlar(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_kalit_tashkilot ON api_kalitlar(tashkilot_id, faol);

-- ------------------------------------------------------ tashkilot -> twin
CREATE TABLE IF NOT EXISTS tashkilot_twin(
  tashkilot_id bigint NOT NULL REFERENCES tashkilotlar(id) ON DELETE CASCADE,
  twin_id      bigint NOT NULL REFERENCES twinlar(id) ON DELETE CASCADE,
  faol         boolean NOT NULL DEFAULT true,
  PRIMARY KEY (tashkilot_id, twin_id)
);

-- --------------------------------------------- userlar: soya foydalanuvchi
ALTER TABLE userlar ADD COLUMN IF NOT EXISTS tashkilot_id bigint
  REFERENCES tashkilotlar(id) ON DELETE CASCADE;
ALTER TABLE userlar ADD COLUMN IF NOT EXISTS tashqi_id text NOT NULL DEFAULT '';
ALTER TABLE userlar ADD COLUMN IF NOT EXISTS manba text NOT NULL DEFAULT 'web';
-- Hamkorning bitta mijozi = bitta qator. Poyga ham ikkinchisini ocholmaydi.
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_tashqi
  ON userlar(tashkilot_id, tashqi_id) WHERE tashkilot_id IS NOT NULL;

-- --------------------------------------------------------- xarajat ustuni
ALTER TABLE xarajatlar ADD COLUMN IF NOT EXISTS tashkilot_id bigint
  REFERENCES tashkilotlar(id) ON DELETE SET NULL;
-- Hamkordan olinadigan summa. Ustama YOZILAYOTGAN PAYTDA qotiriladi —
-- shartnoma o'zgarsa o'tgan oyning hisobi o'zgarib ketmasin.
ALTER TABLE xarajatlar ADD COLUMN IF NOT EXISTS hisob_usd numeric(12,6)
  NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_xarajat_tashkilot
  ON xarajatlar(tashkilot_id, vaqt DESC) WHERE tashkilot_id IS NOT NULL;

-- Worker jobi ham tashkilotga tegishli bo'lishi mumkin (fragment, ingest)
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS tashkilot_id bigint
  REFERENCES tashkilotlar(id) ON DELETE SET NULL;

-- ----------------------------------------------------- balans harakatlari
-- Balans HECH QACHON to'g'ridan-to'g'ri yozilmaydi — faqat shu daftar orqali.
-- Shunda "pul qayerga ketdi?" savoliga har doim javob bor.
CREATE TABLE IF NOT EXISTS balans_harakat(
  id           bigserial PRIMARY KEY,
  tashkilot_id bigint NOT NULL REFERENCES tashkilotlar(id) ON DELETE CASCADE,
  vaqt         timestamptz NOT NULL DEFAULT now(),
  tur          text NOT NULL,              -- toldirish|sarf|tuzatish|qaytarish
  summa_usd    numeric(14,6) NOT NULL,     -- + to'ldirish, - sarf
  qoldiq_usd   numeric(14,6) NOT NULL,     -- harakatdan keyingi balans
  xarajat_id   bigint REFERENCES xarajatlar(id) ON DELETE SET NULL,
  tolov_id     bigint REFERENCES tolovlar(id) ON DELETE SET NULL,
  izoh         text NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_balans_tashkilot
  ON balans_harakat(tashkilot_id, id DESC);

-- ------------------------------------------------------ idempotentlik
-- Hamkor tarmoq uzilganda so'rovni takrorlaydi — ikki marta pul olmaymiz.
CREATE TABLE IF NOT EXISTS api_idempotent(
  kalit        text NOT NULL,
  tashkilot_id bigint NOT NULL REFERENCES tashkilotlar(id) ON DELETE CASCADE,
  javob        jsonb NOT NULL DEFAULT '{}',
  holat        int NOT NULL DEFAULT 200,
  vaqt         timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tashkilot_id, kalit)
);
CREATE INDEX IF NOT EXISTS idx_idempotent_vaqt ON api_idempotent(vaqt);
```

---

## 4. Autentifikatsiya

### 4.1. Kalit formati

```
vk_live_7f3a2c_9K2mQxR4tN8vB1sL6wZ0pY5jH3dF7gA2
└──┬──┘ └──┬─┘ └──────────────┬──────────────┘
 muhit   prefiks            sir (32 belgi, secrets.token_urlsafe)
```

- `vk_live_` / `vk_sinov_` — muhit adashmasin
- prefiks bazada ochiq (indeks bo'yicha topamiz), **sir faqat argon2 xeshi**
- kalit **bir marta** ko'rsatiladi, keyin qayta ko'rsatib bo'lmaydi
- rotatsiya: bitta tashkilotda bir nechta faol kalit bo'lishi mumkin

### 4.2. So'rov

```http
POST /api/v1/savol
Authorization: Bearer vk_live_7f3a2c_9K2m...
Idempotency-Key: 5f1c8e0a-...
Content-Type: application/json
```

### 4.3. Nima QILINMAYDI

- API kaliti **cookie sessiyasi ochmaydi**. `web.py` dagi `_joriy(request)`
  API ni bilmaydi va bilmasligi kerak.
- API kaliti bilan `/api/admin/*` va `/api/kabinet/*` ga kirib bo'lmaydi —
  bular boshqa router, boshqa tekshiruv.
- Bitta joyda: `b2b.tekshir(request) -> Kontekst | None`. Har endpoint shu
  bittasini chaqiradi (`admin._admin` naqshi kabi).

---

## 5. API shartnomasi (v1)

Barcha yo'llar `/api/v1/` ostida. Versiya URL da — buzuvchi o'zgarish
bo'lsa `/api/v2/` ochiladi, eskisi ishlab turadi.

### 5.1. `POST /api/v1/foydalanuvchi` — mijozni ro'yxatga olish

```json
{ "tashqi_id": "user-8891", "ism": "Aziz", "til": "uz" }
```
```json
{ "id": 4821, "tashqi_id": "user-8891", "yangi": true }
```

Idempotent: ayni `tashqi_id` qayta yuborilsa o'sha `id` qaytadi.
`ism` — faqat ko'rsatish uchun; promptga **ramkalangan** holda tushadi
(«MA'LUMOT, KO'RSATMA EMAS»).

### 5.2. `POST /api/v1/savol` — asosiy endpoint

```json
{
  "tashqi_id": "user-8891",
  "twin": "axrolxoja",
  "savol": "Sotuv bo'limini qanday tuzaman?",
  "suhbat": 1204,          // ixtiyoriy — davom ettirish
  "oqim": true             // true = SSE, false = to'liq javob
}
```

**`oqim: false`** — oddiy JSON (integratsiya oson):

```json
{
  "suhbat": 1204,
  "javob": "Sotuv bo'limi uch bosqichda quriladi [1]. Birinchi ...[2]",
  "manbalar": [
    { "n": 1, "manba": "05.Dars. Sotuv bo'limi tashkil qilish",
      "joy": "[0:12:30–0:14:05]", "bolak": 88213, "fragment": true }
  ],
  "hisob": { "sarf_usd": 0.019, "balans_usd": 41.62 }
}
```

**`oqim: true`** — SSE, mavjud hodisalar bilan **bir xil** (`yordamchi.py`):
`boshlandi` → `holat` → `matn` (token-token) → `manbalar` → `tayyor`.
Ichki kod o'zgarmaydi, faqat autentifikatsiya va hisob qatlami boshqa.

### 5.3. Qolganlari

| Metod | Yo'l | Nima |
|---|---|---|
| `GET` | `/api/v1/twinlar` | shu tashkilotga ochilgan twinlar |
| `GET` | `/api/v1/suhbat/{id}` | suhbat tarixi (faqat o'z tashkiloti) |
| `GET` | `/api/v1/suhbatlar?tashqi_id=` | mijozning suhbatlari |
| `GET` | `/api/v1/bolak/{id}/fragment` | audio kesma (iqtibosdan) |
| `GET` | `/api/v1/hisob` | balans, joriy oy sarfi, oxirgi harakatlar |
| `GET` | `/api/v1/hisob/detal?dan=&gacha=` | so'rovlar kesimi (CSV/JSON) |

### 5.4. Xato kodlari

| Kod | Qachon | Tana |
|---|---|---|
| `401` | kalit yo'q/noto'g'ri/muddati o'tgan | `{"xato":"kalit_notogri"}` |
| `403` | kalitda bu huquq yo'q, yoki IP oq ro'yxatdan tashqarida | `{"xato":"ruxsat_yoq"}` |
| `404` | twin/suhbat yo'q **yoki boshqa tashkilotniki** | `{"xato":"topilmadi"}` |
| `402` | balans tugagan | `{"xato":"balans_tugadi","balans_usd":-0.02}` |
| `429` | tezlik yoki parallel oqim chegarasi | `Retry-After` sarlavhasi bilan |
| `503` | model vaqtincha javob bermadi | qayta urinish mumkin |

**Muhim**: boshqa tashkilotning resursi **403 emas, 404** qaytaradi —
mavjudligini ham oshkor qilmaymiz.

---

## 6. Pul yo'li

### 6.1. Sarf qanday yoziladi

Mavjud `pul.xarajat_yoz` ga tashkilot konteksti qo'shiladi. Hisob shu
yerda, **bitta joyda** hisoblanadi:

```python
# pul.py ichida (llm import QILINMAYDI — CLAUDE.md qoidasi)
def xarajat_yoz(model, kirish_tok, chiqish_tok, bosqich=""):
    narx = narx_hisobla(model, kirish_tok, chiqish_tok)   # bizning tannarx
    k = kontekst()                                         # ContextVar
    tid = k.get("tashkilot_id") if k else None
    ustama = tashkilot_ustama(tid) if tid else 0           # qotiriladi
    hisob = round(narx * ustama, 6) if tid else 0
    ...  # xarajatlar ga yozamiz, keyin balansdan yechamiz
```

`kontekst()` — allaqachon bor (`pul.kontekst_boshla`), `ContextVar` bilan
ishlaydi va **ThreadPoolExecutor da ham to'g'ri** ko'chadi (3-bosqichda
tuzatilgan). Shuning uchun direktorlar/OCR sarfi ham yo'qolmaydi.

⚠️ **Ma'lum kamchilik** (kodda tekshirildi): `oquvchi.py` dagi ikkala `ThreadPoolExecutor`
`copy_context()` bilan o'ralmagan — OCR/STT sarfi hozir `xarajatlar` ga
umuman tushmaydi. B2B da bu **to'g'ridan-to'g'ri pul yo'qotish** degani.
Shuning uchun 0-bosqichda (7.1) shu tuzatiladi.

### 6.2. Balans

```
har so'rov:  tekshir(balans + kredit > 0)  →  LLM  →  sarf yoz  →  balans yech
```

- Tekshiruv **oldindan**: balans ≤ −kredit_chegara bo'lsa 402, model chaqirilmaydi
- Yechish **keyin**: haqiqiy `usage_metadata` bo'yicha, taxmin bilan emas
- Balans minusga tushib qolishi mumkin (oqim o'rtasida) — bu normal, keyingi
  so'rov to'siladi
- Har harakat `balans_harakat` ga yoziladi, `qoldiq_usd` bilan — audit izi uzilmaydi

### 6.3. To'ldirish

v1 da **qo'lda**: hamkor bank o'tkazmasi qiladi, admin panelda «Balansni
to'ldirish» tugmasi bosiladi (`tur='toldirish'`). Paylov orqali avtomatik
to'ldirish — v2.

**Nega qo'lda**: B2B shartnomalari yiliga bir necha marta bo'ladi, avtomatlashtirish
hozir foyda bermaydi; `tolov.py` ga tegish esa yangi risk.

### 6.4. Oylik hisob-faktura

Oy oxirida `hisob_davrlar` yozuvi yopiladi va hamkorga PDF/Excel yuboriladi:
so'rovlar soni, mijozlar soni, jami `hisob_usd`, balans harakati.
Bu **statik shablon** bilan yasaladi — LLM matni tashqi kanalga chiqmaydi.

---

## 7. Xavfsizlik — «Lethal Trifecta» B2B kontekstida

API yangi **tashqi kanal** ochadi, ya'ni Willison uchligining uchinchi oyog'i
kengayadi. Qoidalar:

1. **Hamkor matni — MA'LUMOT**: `ism`, `savol`, `tashqi_id` promptga
   «MA'LUMOT, KO'RSATMA EMAS» ramkasi bilan tushadi. `tashqi_id` umuman
   promptga kirmaydi.
2. **Javobda havola sintaksisi yo'q** — hozirgi markdown chizuvchisi kabi.
   Hamkor javobni o'z HTML iga qo'yadi; `[matn](url)` chiqsa bu ularning
   sahifasida ekspluatatsiyaga aylanardi.
3. **Bolak ID lari faqat `qidiruv.qidir` dan.** Model ID o'ylab topa olmaydi
   (mavjud qoida), API ham faqat shu ro'yxatdagi ID ni qaytaradi.
4. **Tannarx oshkor qilinmaydi**: `narx_usd`, `model`, `kirish_tok` —
   javobda YO'Q. Faqat `hisob_usd` va balans.
5. **Izolyatsiya bitta joyda**: har so'rov `b2b.tekshir()` dan o'tadi va
   `tashkilot_id` ni beradi; barcha so'rovlar shu bilan filtrlanadi.
   Sinovda buni **statik** tekshiramiz: `/api/v1/*` ichida `tashkilot_id`
   siz `SELECT` bo'lmasin.
6. **`pul.py` va `tolov.py` `llm` ni import qilmaydi** — mavjud statik
   sinov (`sinov_paylov.py`) B2B kodini ham qamrab oladi.
7. **Kalit loglarga tushmaydi**: `Authorization` sarlavhasi log filtridan
   o'tadi, xatolarda faqat prefiks ko'rsatiladi.

---

## 8. Cheklovlar

`cheklov.QOIDA` ga yangi qatorlar:

```python
"api_savol":  (60, 60),      # tashkilot bo'yicha (tashkilotdagi qiymat ustun)
"api_user":   (20, 60),      # hamkorning bitta mijozi bo'yicha
"api_kalit":  (10, 300),     # noto'g'ri kalit bilan urinish (brute-force)
```

Qo'shimcha ikkita chegara:

- **Parallel oqim** (`tashkilotlar.sekund_limit`): SSE uzoq yashaydi, cheklovsiz
  bitta hamkor butun web jarayonini band qilardi. Semafor bilan, oshsa `429`.
- **Oylik shift** (`oylik_chegara_usd`): kalit o'g'irlansa zarar chegaralangan.

⚠️ `cheklov.py` xotirada ishlaydi — web bir nechta nusxada ishlasa chegara
har nusxada alohida. Bitta konteynerda muammo yo'q; gorizontal kengayishda
Postgres asosiga o'tkaziladi (v2).

---

## 9. Hamkor kabineti

Alohida UI yozilmaydi — mavjud `kabinet.html` ga **«API»** tabi qo'shiladi
(dizayn tizimi `ui.css`/`ui.js`, yangi framework yo'q — CLAUDE.md 5-qoidasi).

Hamkorga ko'rinadigan narsalar:

- kalitlar: yaratish (bir marta ko'rsatiladi), nomlash, o'chirish, IP oq ro'yxati
- balans, joriy oy sarfi, oxirgi 50 harakat
- so'rovlar statistikasi: kun bo'yicha grafik, top mijozlar (`tashqi_id`)
- ochilgan twinlar ro'yxati
- hujjatlar havolasi

Admin panelda: tashkilotlar CRUD, ustama, balans to'ldirish, twin biriktirish,
har tashkilot bo'yicha marja hisoboti (`narx_usd` va `hisob_usd` farqi).

---

## 10. Bosqichlar

### 0-bosqich — qarz to'lash (yarim kun)

B2B pulni to'g'ri hisoblashi uchun **oldin** mavjud kamchilik yopiladi:

- `oquvchi.py:233` va `:304` dagi `ThreadPoolExecutor.submit` larni
  `contextvars.copy_context()` bilan o'rash (`majlis.py:80` naqshi) —
  OCR/STT sarfi `xarajatlar` ga tushsin
- `model_narxlar` ga yetishmayotgan zaxira modellar narxi

**Qabul mezoni**: bitta PDF ingestidan keyin `xarajatlar` da `ocr` bosqichli
qatorlar bor va yig'indi `> 0`.

### 1-bosqich — sxema va kalitlar (1 kun)

`013_b2b.sql`, `platforma/b2b.py` (kalit yasash/tekshirish, kontekst),
admin panelda tashkilot CRUD.

**Qabul mezoni**: kalit yaratiladi, bir marta ko'rsatiladi, bazada xesh
turadi; noto'g'ri kalit `401`, muddati o'tgani `401`, o'chirilgani `401`.

### 2-bosqich — `/api/v1/savol` (2 kun)

`platforma/api_v1.py` — yangi `APIRouter`. Ichkarida mavjud
`yordamchi.oqim_navbat` chaqiriladi, hech narsa nusxalanmaydi.
`oqim=false` uchun oqimni yig'ib bitta JSON qaytaruvchi o'ram.

**Qabul mezoni**: ikkala rejim ham javob va iqtiboslarni qaytaradi;
boshqa tashkilotning `suhbat` id si `404`; idempotency kaliti takroriy
so'rovda pulni ikki marta yechmaydi.

### 3-bosqich — pul (1.5 kun)

`xarajatlar` ga `tashkilot_id`/`hisob_usd`, `balans_harakat`, 402 darvozasi,
`/api/v1/hisob`.

**Qabul mezoni**: 10 ta so'rovdan keyin `balans_harakat` dagi oxirgi
`qoldiq_usd` = boshlang'ich − Σ`hisob_usd`; balans 0 ga tushganda 11-so'rov
`402` va **LLM chaqirilmaydi** (`xarajatlar` ga yangi qator qo'shilmaydi).

### 4-bosqich — cheklov, fragment, hujjat (1 kun)

Rate limit, parallel oqim semafori, `/api/v1/bolak/{id}/fragment`,
hamkor uchun hujjat sahifasi (`/hujjat/api`).

### 5-bosqich — kabinet va hisob-faktura (1.5 kun)

Kabinetdagi «API» tabi, admin marja hisoboti, oylik Excel hisob-faktura.

**Jami: ~7 ish kuni.**

---

## 11. v2 ga qoldirilgani

| Narsa | Nega keyin |
|---|---|
| Mentor/maqsad/tizim API si | ko'p qadamli holat mashinasi — webhook va UI kerak |
| Paylov orqali avtomatik to'ldirish | B2B to'lovlar kam va yirik, qo'lda yetadi |
| Hamkor o'z twinini yuklashi | bilim sifat nazorati bizda qolishi kerak |
| Taqsimlangan rate limit | bitta konteynerda kerak emas |
| Webhook (job tugadi) | v1 da og'ir job yo'q — chat sinxron |
| Oq yorliq (hamkor domeni) | shartnoma va TLS masalasi, texnik emas |

---

## 12. Sinovlar (`sinov_b2b.py`)

`sinov_paylov.py` uslubida — o'z sinov tashkilotini yaratadi va oxirida
o'chiradi, `sozlamalar` jadvaliga tegmaydi.

| # | Nima tekshiriladi |
|---|---|
| S1 | `api_v1.py` va `b2b.py` da taqiqlangan import yo'q (statik AST) |
| S2 | kalit: to'g'ri/noto'g'ri/muddati o'tgan/o'chirilgan → 200/401/401/401 |
| S3 | IP oq ro'yxati: ro'yxatdan tashqari IP → 403 |
| S4 | izolyatsiya: A tashkiloti B ning suhbatini so'rasa → 404 |
| S5 | izolyatsiya: ochilmagan twin → 404 |
| S6 | `tashqi_id` idempotent: 3 marta yuborilsa 1 ta user |
| S7 | balans: sarf = Σ`hisob_usd`, qoldiq to'g'ri |
| S8 | 402: balans 0 da LLM chaqirilmaydi (`xarajatlar` o'smaydi) |
| S9 | kredit chegarasi: minusga tushishga ruxsat, chegaradan keyin 402 |
| S10 | idempotency: ayni kalit bilan 2 marta → 1 marta pul |
| S11 | rate limit: 61-so'rov → 429 + `Retry-After` |
| S12 | parallel oqim: `sekund_limit`+1 → 429 |
| S13 | javobda `narx_usd`/`model`/token yo'q (marja sirlanadi) |
| S14 | javob matnida `](` yo'q (havola sintaksisi) |
| S15 | ustama qotirilishi: ustama o'zgartirilgach eski qator o'zgarmaydi |

---

## 13. Ochiq savollar (egasi hal qiladi)

1. **Ustama nechchi?** Reja `3.0` bilan yozilgan (tannarx $0.019 → hamkor
   $0.057 to'laydi, ~1 so'rov ≈ 750 so'm). Hamkor buni o'z mijoziga
   1500–2000 so'mga sotadi. Alternativa: so'rov boshiga qat'iy narx
   (bashorat qilish oson, lekin uzun savolda biz yutqazamiz).
2. **Eng kam depozit?** Taklif: $100 (≈ 1300 so'rov) — kichik hamkor ham
   kira olsin, lekin qo'lda ishlov berish arzon bo'lsin.
3. **Twinni kim tanlaydi?** Taklif: shartnomada qat'iy (`tashkilot_twin`).
   Hamkor «hamma twin» ni so'rasa — narx boshqa.
4. **Ustoz roziligi**: twin bilimi ustozniki. B2B da qayta sotilishi
   shartnomada ko'rsatilishi va **ustozga ulush** ajratilishi kerakmi?
   Bu texnik emas, lekin sxemaga ta'sir qiladi (`twinlar.egasi_id` bo'yicha
   royalti hisobi kerak bo'lsa — 3-bosqichda qo'shish oson, keyin qiyin).
5. **SLA**: javob vaqti va ishlash kafolati beramizmi? Hozir bitta droplet,
   zaxira yo'q — 99% dan yuqorisini va'da qilib bo'lmaydi.

---

## 14. Nima uchun bu reja xavfsiz

- Migratsiya **additiv**: mavjud B2C oqimiga bitta ham o'zgarish kirmaydi
  (`tashkilot_id IS NULL` bo'lgan userlar bugungidek ishlaydi).
- Javob dvigateli **qayta yozilmaydi** — `yordamchi.py` o'zgarmaydi, API
  faqat uning ustidagi qatlam.
- Pul qarorlari **SQL da**, LLM da emas — mavjud qoidaning davomi.
- Har bosqichning qabul mezoni bor va sinov bilan mahkamlangan.

---

## 15. BAJARILDI (2026-09-09)

0–4 bosqichlar yozildi va lokal Dockerda sinovdan o'tdi: **`sinov_b2b.py`
51/51 yashil**, `sinov_paylov.py` **45/45** (regressiya yo'q).

| Fayl | Nima |
|---|---|
| `migratsiyalar/013_narx.sql` | zaxira modellar narxi (tasdiqlanmagan deb belgilangan) |
| `migratsiyalar/014_b2b.sql` | tashkilotlar, api_kalitlar, tashkilot_twin, balans_harakat, api_idempotent + `userlar`/`xarajatlar`/`jobs` ustunlari |
| `b2b.py` | kalitlar, izolyatsiya, balans daftari, `sarf_yoz` |
| `api_v1.py` | 8 endpoint, hodisa tozalash, semafor |
| `sinov_b2b.py` | 51 tekshiruv |
| `admin.py` | +10 endpoint: tashkilot CRUD, balans, kalit, twin, marja |
| `tayyorlik.py` | 11-bo'lim (B2B) + tasdiqlanmagan narx ogohlantirishi |
| `docs/B2B_API.md` | hamkorlar uchun qo'llanma |

### Amalga oshirishda topilgan xatolar

Uchtasi **sinov yozilgani uchun** topildi — reja bo'yicha yozilganda
sezilmasdi:

1. **Kalitlarning ~40% i ishlamasdi.** Sir `secrets.token_urlsafe` dan
   keladi, alifbosida `_` bor; `vk_live_pre_SIR` ni oddiy `split("_")`
   bilan ajratganda sirida pastki chiziq bo'lgan kalit 4 dan ortiq
   bo'lakka bo'linib rad etilardi. Xato TASODIFIY ko'rinardi.
   Yechim: `split("_", 3)` + `S2j` regressiya sinovi (20 kalit).
2. **Autentifikatsiya keshida teshik.** Argon2 sekin bo'lgani uchun
   muvaffaqiyatli tekshiruv keshlanadi, lekin kesh kaliti faqat
   `prefiks` edi — to'g'ri prefiks + NOTO'G'RI sir bilan kelgan so'rov
   keshdan o'tib ketardi. Yechim: kesh kaliti `prefiks:sha256(sir)`.
3. **Tannarx SSE orqali sizib chiqardi.** `yordamchi` ning `tayyor`
   hodisasi `narx_usd` (BIZNING tannarx) bilan keladi. `api_v1._hodisa`
   uni olib tashlaydi va o'rniga `hisob` qo'yadi; `sahifa_png` (ichki S3
   kaliti) ham chiqmaydi.
4. **Cheklov validatsiyadan keyin edi** — noto'g'ri shakldagi so'rovlarni
   cheksiz yuborib, savol chegarasini aylanib o'tish mumkin edi. Endi
   `api_savol`/`api_user` tekshiruvi validatsiyadan OLDIN.

### Rejadan chetlashishlar

| Reja | Amalda | Nega |
|---|---|---|
| IP mos kelmasa `403` | `401` | mavjudlikni ham oshkor qilmaymiz |
| `userlar.manba` yangi ustun | mavjudi ishlatildi | `006_chat.sql` da allaqachon bor edi |
| `hisob_davrlar` jadvali | yaratilmadi | oylik hisob-faktura v2 ga qoldi; `balans_harakat` yetarli |
| Sarf `api_v1` da yechiladi | `pul.xarajat_yoz` da | shunda chat, dars, maqsad, majlis, OCR, STT — HAMMASI bitta joydan qamraladi |
| Kabinetda «API» tabi | yozilmadi | admin API si bor; hamkor self-service v2 da |

### 0-bosqich natijasi

`oquvchi.py:239` (STT) va `:314` (OCR) dagi `ThreadPoolExecutor.submit`
lar `contextvars.copy_context().run` bilan o'raldi. Shungacha OCR/STT
sarfi `xarajatlar` jadvaliga **umuman tushmasdi** — B2C da hisobot
noto'g'ri edi, B2B da esa bu to'g'ridan-to'g'ri pul yo'qotish bo'lardi.

### Keyingi qadamlar

1. **Ochiq savollarga javob** (13-bo'lim): ustama, eng kam depozit,
   twin qamrovi, ustozga ulush, SLA.
2. `gemini-3-flash-preview` va `gemini-3.1-flash-lite-preview` narxini
   Google narxi bilan solishtirib admin paneldan tuzatish —
   `tayyorlik.py` shu haqda ogohlantirib turadi.
3. Kabinetda «API» tabi (hamkor o'z kalitini va balansini ko'rsin).
4. Jonli sinov: haqiqiy `GEMINI_API_KEY` bilan uchidan-uchiga savol
   (hozirgi sinovlar model chaqirmaydi — ataylab).

---

## 16. YAKUNIY HOLAT (2026-09-09, to'liq)

Sinovlar: **`sinov_b2b` 72/72**, **`sinov_jonli` 15/15** (haqiqiy model bilan),
**`sinov_paylov` 45/45** (regressiya yo'q).

### Qo'shimcha bajarilganlar (5-bosqich va undan tashqari)

| Nima | Fayl |
|---|---|
| Model narxlari TUZATILDI | `migratsiyalar/015_narx_tuzatish.sql` |
| Ustoz ulushi (royalti) | `migratsiyalar/016_royalti.sql`, `b2b.royalti()` |
| Oylik hisob-faktura | `b2b.hisobot()`, `/api/v1/hisobot`, admin `/tashkilot/{id}/hisobot` |
| Admin UI «Hamkorlar (B2B)» | `web/admin.html` — ro'yxat, tafsilot, kalit, balans, twin, marja |
| Admin UI «Ustoz ulushi» | `web/admin.html` — foiz qo'yish va hisobot |
| Jonli tutun sinovi | `sinov_jonli.py` |

### ⚠️ Eng jiddiy topilma: model narxi 4x kam edi

`004_pul.sql` da `gemini-3.5-flash` narxi **0.30/2.50** deb yozilgan edi.
Google narxi (ikki manbadan tekshirildi): **1.50/9.00** — kirishda 5x,
chiqishda 3.6x kam.

Oqibati B2B da halokatli bo'lardi: `hisob = narx * ustama` bo'lgani uchun
**3.0x ustama bilan ham haqiqiy tannarxdan past** hisob chiqarardi, ya'ni
har so'rovda zarar. `015_narx_tuzatish.sql` buni tuzatdi, `pul.ZAXIRA_NARX`
ham asosiy model narxiga ko'tarildi (noma'lum modelni KAM emas, KO'P
hisoblash — ehtiyotkorlik).

**O'lchangan haqiqiy narx** (jonli sinov, 8 iqtibosli 3800 belgilik javob):
tannarx **$0.0246**, hamkorga 3.0x ustama bilan **$0.074** (≈960 so'm).
B2C rejalari ham qayta ko'rildi: «Bazaviy» $3 kvota = ~122 savol,
149 000 so'm narxda marja ~3.8x — o'zgarishsiz sog'lom.

### Brauzerda topilgan ikki UI xatosi

1. **`UI.jadval` o'z idishini tozalaydi** — stat kartalari va sarlavhalar
   jadval chizilganda yo'qolardi. Har jadval endi ALOHIDA idishda
   (bu tuzoq `MENTOR_REJA.md` da ham qayd etilgan edi).
2. **`UI.sana` degan funksiya yo'q** — to'g'ri nomi `UI.vaqt`. Tafsilot
   sahifasi butunlay ochilmasdi. Sinovlar buni topa olmasdi: bu faqat
   brauzerda ishlaydigan kod.

### Ochiq savollarga qabul qilingan qarorlar

| Savol | Qaror | Qayerda |
|---|---|---|
| Ustama | **3.0x** standart | `tashkilotlar.ustama`, admin paneldan o'zgaradi |
| Eng kam depozit | **$100** tavsiya (~1350 savol) | shartnoma masalasi, kodda cheklov yo'q |
| Twin qamrovi | shartnomada qat'iy | `tashkilot_twin` |
| **Ustozga ulush** | infratuzilma tayyor, foiz **0** | `twinlar.royalti_foiz` + admin hisoboti |
| SLA | **va'da qilinmaydi** | bitta droplet, zaxira yo'q — §13 |

Ustoz ulushi bo'yicha: foiz 0 bo'lgani uchun hozir hech kimga hech narsa
hisoblanmaydi, LEKIN `xarajatlar` da twin bo'yicha B2B daromadi yozilib
turadi — foiz keyin qo'yilsa hisobot O'TGAN davrlar uchun ham to'g'ri
chiqadi. Ya'ni qaror keyinga qoldirildi, ma'lumot esa yo'qolmaydi.

### Deploydan keyin bajariladigan ish

```bash
docker compose exec web python -m platforma.tayyorlik   # 11-bo'lim: B2B
docker compose exec web python -m platforma.sinov_jonli # bir necha sent
```
