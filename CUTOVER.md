# CUTOVER — eski `kengash` dan yangi platformaga o'tish

7-bosqich ish tartibi. Har qadam **tekshiriladigan** natija bilan tugaydi.
Maqsad: haqiqiy foydalanuvchilar uzilishsiz yangi tizimga o'tsin, orqaga
qaytish yo'li 2 hafta ochiq qolsin.

> **Sirlar**: `RAILWAY_TOKEN` faqat sessiyada `$env:RAILWAY_TOKEN` sifatida
> beriladi va hech qayerda saqlanmaydi. `.env` / `.env.platforma` kalitlari
> hech qachon terminalga chop etilmaydi — faqat "bor/yo'q".

---

## 0. Kim nima qiladi

| Rol | Vazifa |
|---|---|
| Egasi (siz) | `RAILWAY_TOKEN`, BotFather sozlamalari, narx tasdig'i, "start" qarori |
| Claude | migratsiya, deploy buyruqlari, tekshiruvlar, rollback |

---

## 1. D-1 (cutover oldingi kun)

### 1.1 Kod bulutga chiqadi (bot hali eskida)

```powershell
$env:RAILWAY_TOKEN = "<token>"      # faqat shu sessiyada
Set-Location E:\NewOffice\Labaratoriya\VoIpTelefoniya\deploy_platforma
railway up --service worker
railway up --service twin-web
```

**Tekshiruv**: `twin-web-production.up.railway.app/salomatlik` 200 qaytaradi;
worker jurnalida `WORKER ishga tushdi (N handler: ...)` ko'rinadi.

> Eski `kengash` servisi hamon jonli va bot hamon undan ishlaydi — bu bosqichda
> foydalanuvchi hech narsani sezmaydi.

### 1.2 Tayyorlik ko'rigi

```powershell
Set-Location E:\NewOffice\Labaratoriya\VoIpTelefoniya
.\.venv\Scripts\python.exe -u -m platforma.tayyorlik
```

XATO bo'lsa cutover **qilinmaydi**. OGOH lar ro'yxati ko'rib chiqiladi
(masalan, to'lov provayderi sozlanmagani — bu joiz).

### 1.3 Zaxira

```powershell
# yangi bazaning zaxirasi (worker ham haftalik o'zi qiladi)
.\.venv\Scripts\python.exe -c "from platforma import zaxira; print(zaxira.bajar({'id':0}, print))"
```

Eski tizimning volume'i **o'chirilmaydi** — 2 hafta rollback uchun turadi.

### 1.4 Narx va kvota qarori

- Admin panel → 💰 Moliya → planlar narxi tasdiqlanadi
  (hozir taxminiy: Bazaviy 149 000 so'm / $3, Professional 449 000 so'm / $12).
- `kvota_faol` **hali yoqilmaydi** — cutoverdan keyin, tizim barqaror
  ishlagach yoqiladi (aks holda birinchi kunning o'zida to'siqqa uchrash xavfi).

---

## 2. D (cutover kuni)

### 2.1 Eski tizimni to'xtatish — MUZLATISH YO'Q, webhook orqali

> ⛔ **`KENGASH_BOT_OFF=1` ni ESKI servisga QO'YMANG.** Eski koddagi shart
> `dev_rejim() = not bot_token()` — token o'chirilishi bilan eski jonli URL'da
> `/api/kirish/dev` OCHILIB KETADI (istalgan odam ism yozib klient sessiyasi
> oladi). Bu 2026-07-31 da amalda tekshirilib, darhol orqaga qaytarilgan.
> Yangi kodda teshik yopilgan, eskisida yo'q.

Bot **webhook** rejimida ishlaydi, ya'ni oqimni Telegram tomonidagi yagona
webhook manzili belgilaydi. Shuning uchun to'xtatish alohida qadam emas:
2.4 da yangi web webhookni o'ziga qaratadi va eski servisga xabar kelmay qoladi.

Muzlatish bo'lmagani uchun o'tish oynasida kelgan savollar eski bazaga tushadi —
ular **2.6 dagi takroriy ko'chirish** bilan olinadi (`--tarix` idempotent).

### 2.2 Eski ma'lumotni olish (volume'dan)

> ⚠️ **`railway ssh` loyiha tokeni bilan ISHLAMAYDI** ("Unauthorized").
> U shaxsiy hisobga kirishni talab qiladi. Shuning uchun cutover kuni
> egasi bir marta brauzer orqali kirishi kerak:
>
> ```powershell
> railway login          # brauzer ochiladi, bir marta
> ```
>
> Shundan keyin quyidagilar ishlaydi ( `RAILWAY_TOKEN` ni bu buyruqlarda
> BERMANG — u shaxsiy sessiyani bosib qo'yadi).

```powershell
$b = "E:\NewOffice\Labaratoriya\VoIpTelefoniya\cutover_data"
New-Item -ItemType Directory -Force $b | Out-Null

railway ssh --service kengash "base64 -w0 /data/baza/kengash.db" > "$b\kengash.db.b64"
railway ssh --service kengash "tar czf - -C /data chiqish | base64 -w0" > "$b\chiqish.tgz.b64"

certutil -decode "$b\kengash.db.b64" "$b\kengash.db"
certutil -decode "$b\chiqish.tgz.b64" "$b\chiqish.tgz"
tar xzf "$b\chiqish.tgz" -C $b
```

**Tekshiruv**:

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3,sys; s=sqlite3.connect(r'$b\kengash.db'); print({t: s.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('userlar','suhbatlar','majlislar')})"
(Get-ChildItem "$b\chiqish" -Filter *.md).Count
```

Sonlar eski admin paneldagi statistikaga mos kelishi kerak.

### 2.3 Tarixni ko'chirish

```powershell
.\.venv\Scripts\python.exe -u -m platforma.migratsiya_eski --tarix `
    --db "$b\kengash.db" --chiqish "$b\chiqish"
```

`--tarix` rejimi:
- twinlarni, direktorlarni, bilim bazasini **tegmaydi** (ular allaqachon
  ko'chirilgan va adminda sozlangan bo'lishi mumkin);
- avval `eski_id` li suhbat/majlislarni o'chiradi, keyin qaytadan yozadi —
  shuning uchun **qayta ishga tushirish xavfsiz**, ikkilanish bo'lmaydi;
- asl vaqtlarni (`yaratilgan`/`vaqt`) saqlaydi.

**Tekshiruv**: jurnalda `suhbatlar: N ta, majlislar: M ta` — 2.2 dagi sonlarga
teng bo'lishi kerak. Admin panelda bir nechta eski majlis ochib ko'riladi:
xulosa matni, direktor javoblari va manbalar joyida.

### 2.4 Botni yangi tizimga ulash

1. BotFather → `/setdomain` → `twin-web-production.up.railway.app`
   (Telegram Login Widget shu domenni talab qiladi).
2. Yangi web'da bot yoqiladi va webhook o'rnatiladi:

```powershell
# webhook manzili shu o'zgaruvchidan olinadi — bo'lmasa webhook O'RNATILMAYDI
railway variable set PUBLIC_URL=https://twin-web-production.up.railway.app --service twin-web
railway variable set TELEGRAM_BOT_TOKEN=<eski servisdagi AYNI token> --service twin-web
railway variable delete KENGASH_BOT_OFF --service twin-web
railway redeploy --service twin-web -y
```

**Tekshiruv**: web jurnalida `TG webhook o'rnatildi: @<bot>` qatori chiqadi.
Chiqmasa — `PUBLIC_URL` https bilan boshlanmagan yoki token yo'q.

Web ishga tushganda `tg.webhook_ornat()` webhookni yangi manzilga qaratadi.
Webhook Telegram tomonda **bitta** bo'ladi — ya'ni eski servisga xabar
kelmay qoladi (2.1 dagi `KENGASH_BOT_OFF=1` esa ikkinchi qulf).

**Tekshiruv**: botga `/start` yoziladi → yangi ilova tugmasi keladi → ochilib
kirish ishlaydi → eski suhbatlar ro'yxati ko'rinadi → bitta savol berilib
majlis oxirigacha o'tadi (jonli jurnal, iqtiboslar, fragment).

### 2.6 O'tish oynasidagi savollarni olish (takroriy ko'chirish)

Webhook yangi web'ga o'tgach, 2.2 va 2.3 QAYTA bajariladi — o'tish oynasida
eski bazaga tushgan savollar shunda ko'chadi. `--tarix` idempotent, shuning
uchun takror xavfsiz.

> ⛔ Shundan keyin eski servisni **qayta ishga tushirmang** (`redeploy`) —
> u startda webhookni o'ziga qaytarib oladi.

### 2.5 Eski servis — o'chirilmaydi, jim turadi

Bot va web yangisiga o'tgani tasdiqlangach eski servis **deploy holida
qoldiriladi**, faqat boti o'chiq (2.1). Sababi: rollback bir buyruq bilan
bo'lishi kerak, `railway down` esa deploymentni olib tashlaydi.

D+14 da (rollback oynasi yopilgach):

```powershell
railway down --service kengash -y      # volume ALOHIDA o'chiriladi, qo'lda
```

---

## 3. Rollback (agar biror narsa noto'g'ri ketsa)

Qaror nuqtasi: 2.4 dan keyin 30 daqiqa ichida jiddiy nosozlik ko'rinsa.

```powershell
# 1. yangi web'da botni o'chirish
railway variable set KENGASH_BOT_OFF=1 --service twin-web
railway redeploy --service twin-web -y

# 2. eski servisni qaytarish
railway variable delete KENGASH_BOT_OFF --service kengash
railway redeploy --service kengash -y     # webhookni o'ziga qaytaradi
```

3. BotFather → `/setdomain` → eski domen (`kengash-production.up.railway.app`).

Eski volume tegilmagani uchun eski tizim cutover daqiqasidagi holatida
ishlaydi. Yangi platformada cutoverdan keyin tug'ilgan suhbatlar eski tizimda
ko'rinmaydi — shuning uchun rollback oynasi qisqa (30 daqiqa) bo'lishi kerak.

---

## 4. D+1 … D+14

| Muddat | Ish |
|---|---|
| D+0 kechqurun | Admin → Jobs monitor: xato bo'lgan job yo'qligini tekshirish |
| D+1 | `python -m platforma.tayyorlik` qayta ishga tushiriladi — endi «obuna_nazorat» bajarilgan bo'lishi kerak |
| D+1 | Narx tasdiqlangach admin panelda `kvota_faol` **yoqiladi** |
| D+7 | Birinchi haftalik `zaxira` job'i bajarilganini tekshirish (MinIO `zaxira/`) |
| D+14 | Eski `kengash` volume arxivlanadi/o'chiriladi |

---

## 5. Cutover holatini kuzatish

Xatolar admin Telegramiga o'zi keladi (`monitoring.py`): ayni xato 10 daqiqada
bir marta, soatiga ko'pi bilan 20 ta. Cutover kuni `XATO_TG_KANAL` alohida
kanalga qo'yilsa qulay bo'ladi.

Qo'lda ko'rish:

```powershell
railway logs --service twin-web
railway logs --service worker
```

---

## 6. Bajarilmagan/qaror kutayotgan ishlar

- [ ] `CLICK_SERVICE_ID` / `CLICK_MERCHANT_ID` / `CLICK_SECRET` — merchant hisobi ochilgach
- [ ] `PAYME_MERCHANT_ID` / `PAYME_KEY` — o'shanda
- [ ] Yakuniy narx tasdig'i (hozirgisi taxminiy, kurs 1$≈13 000 so'm)
- [ ] `XATO_TG_KANAL` — xatolar uchun alohida kanal (ixtiyoriy)
- [ ] Twinlarga egasi biriktirish (hozir 0 ta — kabinet ishlashi uchun kerak)
