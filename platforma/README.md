# Virtaks — platforma

Brend nomi **Virtaks** (domen: https://twin.virtaks.uz — eski
`twin.bmslab.uz` ham shu yerga qaraydi). ⚠️ Xizmat hozir **offline**:
eski server o'chgan, DigitalOcean'da noldan ko'tarilmoqda —
[`../DEPLOY_DO.md`](../DEPLOY_DO.md).
Kod ichidagi `twin` / `twinlar` — domen tushunchasi (ustozning raqamli
nusxasi), brend emas; ular o'zgartirilmaydi.

Ustozning bilimidan qurilgan raqamli egizak: foydalanuvchi savol beradi,
egizak faqat o'sha ustozning darslariga tayanib javob yozadi — javob
token-token oqib keladi, har da'voda iqtibos bo'ladi, kerak bo'lsa darsning
aynan o'sha daqiqasi audio fragment sifatida ochiladi.

- Umumiy reja va bosqichlar: [`../DIGITAL_TWIN_REJA.md`](../DIGITAL_TWIN_REJA.md)
- Prodga o'tish tartibi: [`../CUTOVER.md`](../CUTOVER.md)

## Uchta javob dvigateli

| Rejim | Kim ishlatadi | Qanday | Narx | Vaqt |
|---|---|---|---|---|
| **yordamchi** (standart) | butun chat | `yordamchi.py` — bitta model, SSE oqim | ~$0.006 | birinchi so'z ~3 s |
| **mentor** (dars) | «O'quv rejam» bo'limi | `mentor.py` — mavzu bo'laklariga tayangan SSE oqim | ~$0.006 | birinchi so'z ~3 s |
| **maqsad** (sikl) | «Maqsadim» bo'limi | `maqsad_oqim.py` — joriy qadam bo'laklariga tayangan SSE oqim | ~$0.006 | birinchi so'z ~3 s |
| **kengash** (chuqur) | hozircha UI'da yo'q | `majlis.py` — RAIS + 1-6 direktor, worker jobi | ~$0.038 | 40-60 s |

To'rtalasi ham ayni `majlislar` jadvaliga yozadi, farqi `rejim` ustunida.
Chat va dars oqimi worker'ga bormaydi (og'ir ish emas) — ular web
jarayonida, alohida threadda bajariladi va hodisalar navbat orqali SSE ga
chiqadi (`yordamchi.navbatga` ko'prigi ikkalasiga umumiy).

## Mentorlik rejimi

Digital twin faqat savolga javob bermaydi — **o'qitadi**: bilim darajasini
o'lchaydi, shaxsiy yo'l xaritasi tuzadi, dars o'tadi, uy vazifasi beradi va
uni tekshirib xatolarni tushuntiradi.

```
  BILIM BAZASI            KURS (twin uchun, bir marta)      REJA (har o'quvchiga)
  manbalar/bolaklar  ──▶  kurslar → modullar → mavzular ──▶ oquv_reja / oquv_holat
       (egasi yuklaydi)     ▲ qoralama → egasi tasdiqlaydi        │
                            │                                     ▼
                       `kurs_qur` job                    dars → mini-test → vazifa
                       (oquv.kurs_qur)                   (mentor.py)  (vazifa.py)
```

Ikki qatlamning farqi muhim:

- **Kurs** — `oquv.kurs_qur` worker jobi bilan quriladi (manba konspektlari →
  modul/mavzu daraxti → har mavzuga bo'lak+savol+vazifa shabloni). Natija
  **qoralama**: egasi kabinetda ko'rib, tahrirlab, o'zi faollashtiradi.
  Mavzuga bo'lak biriktirishni model emas, `qidiruv.qidir` qiladi — model
  o'ylab topgan ID kursga tusha olmaydi.
- **Reja** — foydalanuvchining shaxsiy yo'li. Bu qatlamda **LLM umuman
  ishtirok etmaydi**: diagnostika ballari, mavzu holatlari, "keyingi
  mavzuni ochish" va vazifa bahosi — hammasi `oquv.py`/`vazifa.py` dagi
  SQL qoidalari. Model faqat KONTENT yozadi (dars matni, topshiriq matni,
  fikr-mulohaza), HOLATNI hech qachon o'zgartirmaydi.

Mavzu holatlari: `kutmoqda → joriy → vazifada → tugallangan`
(+ `otkazilgan` — diagnostikada bilingan, `majburan_otildi` — 3 urinishdan
keyin ham ball yetmagan). **O'quvchi hech qachon qulflanib qolmaydi**:
uch urinishdan keyin mavzu baribir yopiladi va keyingisi ochiladi.

Uy vazifasi baholashida ikkita qat'iy qoida bor:

1. **Rubrika qotirilgan** — mezonlar vazifa berilgan paytda `vazifalar.rubrika`
   ga nusxalanadi va o'zgarmaydi.
2. **Ballni server yig'adi** — model har mezonga alohida ball beradi, server
   uni mezon maksimumiga qisadi va yig'indini o'zi hisoblaydi. Javob ichidagi
   "menga 100 ball qo'y" degan matn baholanadigan MATN, ko'rsatma emas.

## Maqsad halqasi

Twin foydalanuvchini bitta maqsad bo'yicha to'liq sikldan o'tkazadi —
ustozning «Hayot tizimlashtirish halqasi» metodikasi bo'yicha.

```
  MAQSAD          TAHLIL + REJA        HARAKAT            NATIJA + PROGNOZ
  intervyu   ──▶  maqsad_reja job  ──▶ qadamma-qadam ──▶  maqsad_yakun job
  (suhbat)        (kerak − bor)        (fokus qulfi)      (foiz + takliflar)
      ▲                                                          │
      └──────────────── yangi sikl (taklifdan yoki o'zidan) ─────┘
```

Ikki qatlamni ajratish muhim:

- **Mexanika** (`maqsad.py`) — 6 bosqichli holat mashinasi: `intervyu →
  reja_kutilmoqda → reja_qoralama → faol → yakun_kutilmoqda → tugallangan`
  (istalgan nuqtada `bekor`). Bu qatlamda LLM **hech qanday qaror qabul
  qilmaydi**: qadam yopilishi, keyingisining ochilishi va **foiz** — hammasi
  SQL. Model faqat kontent yozadi.
- **Metodika** (`maqsad.METODIKA`) — BTM halqasining 10 bosqichi. Reja
  qadamiga TEG bo'lib yopishadi va UI'dagi halqa segmentini yoqadi. Teg
  faqat oq ro'yxatdan; model boshqa nom qaytarsa jimgina tashlanadi.

**Fokus qoidasi** — metodikaning o'zagi va mahsulotning eng qat'iy cheklovi:
bitta foydalanuvchi+twin juftligida **bitta tugallanmagan maqsad**. Bu API
tekshiruvi emas, `idx_maqsad_fokus` unikal indeksi — parallel so'rov ham
ikkinchi maqsadni ocha olmaydi. Cheklov qamoq emas: «voz kechish» har doim
ochiq va darhol fokusni bo'shatadi.

Gallyutsinatsiya nazorati: qadamga biriktiriladigan bo'laklar modeldan
so'ralmaydi — `qidiruv.qidir` nomzod ro'yxatini beradi, model esa faqat shu
ro'yxatdagi **tartib raqamini** ko'rsata oladi (iqtibos naqshi). Bo'lak
topilmagan qadam `umumiy=true` bo'lib UI'da «umumiy tavsiya» yorlig'ini
oladi, butun reja qamrovi past bo'lsa ochiq ogohlantirish chiqadi.

Rejim twin egasi tomonidan `maqsad` skilli orqali yoqiladi/o'chiriladi
(kabinet → «Imkoniyatlar»). O'chiq bo'lsa `/api/maqsad` 404 qaytaradi va
ilovada bo'lim umuman ko'rinmaydi.

### Qadam ichidagi aniq ishlar

Qadam yirik bo'lak («CRM joriy qilish», 10 kun) — foydalanuvchi ertaga
nimadan boshlashini bilishi uchun har qadam **3–6 ta aniq ishga** bo'linadi
(`maqsad_ishlar`, 009 migratsiya). Ishlar reja qurilayotganda **o'sha bitta
LLM chaqiruvida** chiqadi — qo'shimcha job ham, qo'shimcha chaqiruv ham yo'q.

Ishga qo'yilgan talab promptda qat'iy: bir o'tirishda (1–3 soat) bajariladi,
fe'l bilan boshlanadi, natijasi ko'z bilan ko'rinadi. «O'ylab ko'ring»,
«tahlil qiling» kabi mavhum ishlar **taqiqlangan** — ularni bajarildi deb
belgilab bo'lmaydi.

Belgilashni faqat foydalanuvchi qiladi (`POST /api/maqsad/ish/{id}`), va
faqat qadam `joriy` bo'lganda — fokus qoidasi shu yerda ham amal qiladi.
Foydalanuvchi o'z ishini qo'sha oladi (`ozim=true`), model esa qo'sha
olmaydi: ish ro'yxati ham HOLAT, uni model o'zgartirmaydi.

Suhbatda twin joriy qadamning ish ro'yxatini va **navbatdagi bajarilmagan
ishni** ko'rib turadi — «nima qilay?» degan savolga mavhum javob o'rniga
aynan shu ishni tushuntiradi.

### Suhbat ohangi — murabbiy, anketa emas

`maqsad_oqim.INTERVYU` ataylab **so'roq bo'lishni taqiqlaydi**. Har xabar
uchta narsani birga qiladi: eshitganini tasdiqlaydi → ustoz bilimidan bitta
amaliy fikr beradi ([n] iqtibos bilan) → bitta savol beradi.

Muhim tafsilotlar:

- Foydalanuvchi noaniq javob bersa ayni savol **qayta berilmaydi** — twin
  2-3 ta aniq variant taklif qiladi ("odatda buni shunday o'lchashadi...").
  «Bilmayman» degan javob suhbatni to'xtatib qo'ymaydi.
- O'lchov yoki muddat aytilmagan bo'lsa twin «qanday o'lchaymiz?» deb
  qo'ya qolmaydi — bilimga tayanib real variant taklif qiladi.
- Savollar raqamlangan ro'yxat bo'lib tashlanmaydi; bir xabarda bitta savol.
- Harakat rejimida ham shu tamoyil: quruq «davom eting» emas, qadamni
  qanday bajarish, qayerda ko'p xato qilinishi va foydalanuvchi
  qiynalayotgan bo'lsa qadamni kichikroq bo'laklarga bo'lib berish.

---

## Arxitektura

```
            ┌──────────────┐        jobs jadvali          ┌───────────────┐
  brauzer ──│  web (FastAPI)│ ──── (SKIP LOCKED navbat) ──▶│    worker     │
  Telegram  │   holatsiz    │◀──── holat/jurnal ──────────│ og'ir ishlar  │
            └──────┬───────┘                              └───────┬───────┘
                   │                                              │
             PostgreSQL 18 + pgvector                        MinIO (S3)
             (bilim, vektor, tarix, pul)              (asl fayllar, fragment,
                                                        shablon, zaxira)
```

- **web** — holatsiz, bir necha nusxada ishlay oladi; hech qanday og'ir ish
  qilmaydi, faqat navbatga qo'yadi.
- **worker** — ketma-ket bitta job bajaradi: majlis, ingest (audio STT / PDF OCR /
  PPTX→rasm / web), fragment kesish, kurs qurish, vazifa tekshirish, maqsad
  rejasi va yakuni, obuna nazorati, zaxira.
- **Navbat** — Postgres `jobs` jadvali: `FOR UPDATE SKIP LOCKED`, eksponensial
  qayta urinish, muhlat oshsa reaper qaytaradi, `job_loglar` UI'ga jonli oqadi.
  Noma'lum job turi **xato emas** — qayta navbatga tushadi (rolling deploy paytida
  eski worker yangi turni ko'rmasligi mumkin).

## Rollar

| Rol | Qanday kiradi | Nima qiladi |
|---|---|---|
| `client` | **Telegram** | savol beradi, o'z tarixini ko'radi |
| `egasi` | **Telegram** | o'z twinining bilimi, xulqi, skilllari, shablonlari |
| `admin` | **Telegram** | hammasi + moliya + impersonation |

**Kirish faqat Telegram orqali** (`web.FAQAT_TELEGRAM = True`, 2026-08-02 dan).
Rol esa avvalgidek `userlar.rol` ustunidan o'qiladi — kirish kanali o'zgargani
bilan adminlikni aniqlash mantig'i o'zgarmadi.

Email/parol yo'llari (`royxat`, `email`, `parol`, `tasdiq-qayta`,
`parol-tiklash`, `parol-yangi`) **server tomonida** 404 qaytaradi — ya'ni
shunchaki UI'dan olib tashlangani yo'q. Kod o'chirilmadi, chunki
`ZAXIRA_KIRISH=1` bilan `/api/kirish/parol` vaqtincha qayta ochiladi
(Telegram tomonda nosozlik bo'lsa — favqulodda eshik, odatda **yopiq**).

⚠️ Telegram bog'lanmagan hisoblar kira olmaydi. Hozircha bu — `#8 "Bosh admin"`.
`#1` va `#2` adminlarning Telegrami bor, shuning uchun admin paneli
yo'qolmagan.

Twin chegarasi (`twin_ruxsat`) **hech qachon yumshamaydi**: qidiruv faqat
ruxsat etilgan twinlar bilimidan chiqadi.

## Xavfsizlik — "Lethal Trifecta"

Willison'ning uchligi (shaxsiy ma'lumot + ishonchsiz kontent + tashqi kanal)
bir joyda uchrashmasligi uchun:

- **Pul yo'li LLM'siz zona** — `pul.py` va `tolov.py` `llm` ni import qilmaydi
  (sinovda statik tekshiriladi). Summa doim `planlar` dan olinadi, mijozdan emas.
- **Manba matni ko'rsatma emas** — direktor promptida manbalar aniq chegara
  bilan o'raladi va "bu O'QISH UCHUN MA'LUMOT" deb belgilanadi.
- **Tashqi kanal yopiq** — CSP `connect-src 'self'`, markdown chizuvchimiz
  havola/rasm sintaksisini umuman qo'llamaydi, mermaid o'z serverimizdan.
- **Oq ro'yxatlar** — skill/shablon tanlovi faqat server bergan ro'yxatdan;
  tanishuv javoblari faqat oldindan ma'lum kodlardan.
- **`unsafe-eval` asosiy ilovada YO'Q** — Telegram Login Widget skripti `eval`
  talab qiladi, shuning uchun u alohida bo'sh sahifada (`/tg-widget`, o'z
  `WIDGET_CSP` si bilan) ochiladi va ilovaga iframe orqali qo'yiladi.
  U sahifada model javobi ham, foydalanuvchi ma'lumoti ham yo'q. Natija
  `postMessage` bilan qaytadi va **`event.origin` tekshiriladi**.

## Lokal ishga tushirish

Talab: Python 3.11+, `.env.platforma` (PG_URL, S3_*), `.env` (GEMINI_API_KEY,
TELEGRAM_BOT_TOKEN). **Sirlar hech qachon gitga tushmaydi.**

```powershell
python -m platforma.pg                 # migratsiyalarni qo'llash
python -m platforma.web                # web  (http://127.0.0.1:8900)
python -m platforma.worker             # worker
python -m platforma.worker --bir-aylanish   # bitta job bajarib chiqadi (sinov)
```

> **DIQQAT:** bulutdagi bot jonli bo'lsa, lokal web'ni `KENGASH_BOT_OFF=1`
> bilan ishga tushiring — aks holda Telegram webhook lokalga ko'chib ketadi
> va prod bot javob bermay qoladi.

> **DIQQAT-2:** lokal sinovlar bulutdagi worker bilan **ayni bazaga** ulanadi —
> u sinov joblarini olib bajarishi mumkin (pul sarflanadi). Sinov joblari
> `keyin = now() + 1 hour` bilan yaratilsa worker ularni ko'rmaydi.

## Foydali buyruqlar

```powershell
# admin yasash / rol berish / twinga egasi biriktirish
python -m platforma.boshqaruv admin-yasa --login admin --parol XXX --ism "Admin"
python -m platforma.boshqaruv rol --user 5 --rol egasi
python -m platforma.boshqaruv twin-egasi --twin 2 --user 5
python -m platforma.boshqaruv royxat

# eski tizimdan ko'chirish
python -m platforma.migratsiya_eski                 # hammasi (bir martalik)
python -m platforma.migratsiya_eski --bilim         # faqat twin/bilim
python -m platforma.migratsiya_eski --tarix --db ... --chiqish ...   # cutover kuni

# cutover oldidan tayyorlik ko'rigi
python -m platforma.tayyorlik
```

## Modullar

| Fayl | Vazifa |
|---|---|
| `sozlama.py` | muhit (`.env.platforma` lokal, env Railway), `log` |
| `pg.py` | ulanish puli + `migratsiyalar/*.sql` runner |
| `jobs.py` | navbat: `qoshish/talab/tayyor/yiqildi/qotganlarni_qaytar/holat` |
| `worker.py` | `@handler` registri, davriy ishlar rejasi |
| `storage.py` | S3/MinIO |
| `db.py` | domen so'rovlari (twin, manba, bo'lak, suhbat, majlis) |
| `llm.py` | Gemini chaqiruvlari + xarajat daftariga yozish |
| `qidiruv.py` | pgvector + BM25 → RRF, `twin_ruxsat` chegarasi |
| `yordamchi.py` | **chat yadrosi**: RAG + bitta model + SSE oqim, iqtibos yig'ish |
| `oquv.py` | **o'quv dasturi**: kurs qurish jobi + shaxsiy reja (LLM'siz qarorlar) |
| `mentor.py` | **dars oqimi**: mavzu bo'laklariga tayangan SSE suhbat |
| `vazifa.py` | uy vazifasi: berish, rubrika bo'yicha tekshirish, eslatma |
| `maqsad.py` | **maqsad sikli**: holat mashinasi, reja/yakun joblari, foiz (LLM'siz qarorlar) |
| `maqsad_oqim.py` | maqsad suhbati: intervyu va harakat rejimlari (SSE) |
| `pochta.py` | tasdiq/tiklash xatlari (Resend yoki SMTP) |
| `agentlar.py` | direktor/RAIS promptlari, yo'naltirish (chuqur rejim) |
| `majlis.py` | kengash job'i (chuqur rejim orkestri) |
| `ingest.py` / `oquvchi.py` | manba o'qish → bo'laklash → embedding |
| `fragment.py` | audio oralig'ini kesish (ffmpeg + S3 range) |
| `skilllar.py` / `shablon.py` | skill registri, Excel shablon to'ldirish |
| `profil.py` / `tanishuv.py` | foydalanuvchi profili va tanishuv testi |
| `pul.py` / `tolov.py` | xarajat, kvota, obuna / **Paylov**, Click, Payme |
| `sinov_paylov.py` | to'lov yo'lining sinovlari (`python -m platforma.sinov_paylov`) |
| `cheklov.py` | tezlik chegarasi (rate limit) |
| `b2b.py` | **B2B yadrosi**: API kalitlari, tashkilot izolyatsiyasi, balans daftari |
| `api_v1.py` | **B2B API** `/api/v1/*` — hamkorlar yuzasi (SSE hodisalari tozalanadi) |
| `sinov_b2b.py` | B2B sinovlari (`python -m platforma.sinov_b2b`) |
| `manba_yukla.py` | papkadagi fayllarni ommaviy yuklash (kabinet oqimining konsol nusxasi) |
| `monitoring.py` | jiddiy xatolar → admin Telegram |
| `zaxira.py` | haftalik `pg_dump` → MinIO |
| `tayyorlik.py` | cutover oldidan to'liq ko'rik |
| `web.py` / `admin.py` / `kabinet.py` / `tolov.py` | HTTP yuzalari |
| `web/ui.css`, `web/ui.js` | **umumiy dizayn tizimi** (tokenlar, jadval, modal, holatlar) |
| `web/index.html`, `admin.html`, `kabinet.html` | uchta sahifa (har biri bitta fayl) |
| `web/tg_widget.html` | **faqat** Telegram tugmasi (o'z `WIDGET_CSP` si, `postMessage`) |
| `web/eski_v1/` | 2026-07-31 gacha bo'lgan UI zaxirasi |

Ustoz surati: `twinlar.avatar` — S3 kaliti (`avatarlar/<id>.jpg`), `GET
/api/twin/{id}/avatar` orqali beriladi (1 kun kesh). Surat bo'lmasa yoki
yuklanmasa UI ism harfiga qaytadi.

## Muhit o'zgaruvchilari (yangilari)

| Nom | Nima uchun |
|---|---|
| `PAYLOV_MERCHANT_ID` | Paylov merchant UUID (kabinetdan) |
| `PAYLOV_CALLBACK_LOGIN` / `PAYLOV_CALLBACK_PAROL` | callback Basic Auth — **kabinetda ham xuddi shunday** yozilishi shart |
| `PAYLOV_TIYINDA=1` | checkout havolasida summa tiyinda (`0` — so'mda). Jonli sinovda tasdiqlanadi |
| `PAYLOV_IP` | vergul bilan ajratilgan callback IP oq ro'yxati (bo'sh = filtr o'chiq) |
| `PAYLOV_CHECKOUT`, `PAYLOV_VALYUTA` | odatda tegilmaydi (`https://my.paylov.uz/checkout/create/`, `860`) |
| `RESEND_API_KEY` + `POCHTA_FROM` | tasdiq/tiklash xatlari (tavsiya etiladi) |
| `SMTP_HOST/PORT/USER/PAROL` + `POCHTA_FROM` | Resend o'rniga SMTP |
| `EMAIL_TASDIQ=0` | tasdiqlashni ataylab o'chirish (faqat sinov) |
| `PROD=1` | **jonli muhit bayrog'i** — o'z serverimizda majburiy |
| `ZAXIRA_KIRISH=1` | favqulodda login+parol eshigi (odatda **qo'yilmaydi**) |

`PROD` platformaga bog'liq emas: Railway o'zining `RAILWAY_ENVIRONMENT`
o'zgaruvchisini qo'yadi, boshqa joyda `PROD=1` qo'lda beriladi. Unga
xavfsizlik qarori bog'langan — `auth.dev_rejim()` jonli muhitda hech qachon
yoqilmaydi. Shart ataylab bot tokeniga bog'liq EMAS: token tushib qolsa ham
`/api/kirish/dev` teshigi ochilmasligi kerak (2026-07-31 da aynan shu xato
bo'lgan edi). `S3_ENDPOINT` ham shu bayroq bo'yicha tanlanadi — jonli
serverda konteyner nomi (`http://twin-minio:9000`), lokalda esa
`S3_ENDPOINT_TASHQI` (TCP proksi).

Pochta sozlanmasa ro'yxatdan o'tish ishlaydi, lekin **email tasdiqlanmaydi** —
3 ta bepul savol soxta manzillar bilan olinishi mumkin. Kvota yoqilgunga qadar
bu xavf amaliy emas.

## To'lov (Paylov)

To'liq protokol va reja: `PAYLOV_REJA.md`.

Oqim: mijoz «Rejalar» dan planni tanlaydi → `POST /api/tolov/boshla` kutilayotgan
to'lov yozadi va `my.paylov.uz/checkout/create/<base64>` havolasini qaytaradi →
Paylov `transaction.check` / `transaction.perform` ni **`POST /tolov/paylov`**
ga yuboradi (JSON-RPC 2.0 + Basic Auth) → `pul.tolandi` obunani ochadi →
mijoz `/?tolov=<uuid>` ga qaytadi va sahifa holatni so'rab turadi.

Muhim jihatlar:

- **Summa hech qachon so'rovdan olinmaydi** — `planlar.oylik_narx_som` dan.
  Callbackdagi `amount`/`amount_tiyin`/`currency` faqat solishtiriladi;
  mos kelmasa status `5` va holat o'zgarmaydi.
- **Buyurtma raqami — UUID** (`tolovlar.tashqi_id`), ketma-ket `id` emas.
- **Idempotent uch qatlamda**: `paylov_tranzaksiyalar` PK, `tolovlar(provayder,
  provayder_id)` unikal indeksi, `pul.tolandi` ichidagi `FOR UPDATE`.
- **Muddat**: to'lanmagan yozuv `tolov_muddat_soat` (default 24) dan keyin
  soatlik `tolov_tozala` jobi bilan bekor qilinadi; kechikkan callback ham
  qabul qilinmaydi.
- **Pul qaytarish (refund)** protokolda yo'q: Paylov kabinetida qilinadi,
  so'ng admin panelda «To'lovlar → ✕» bosiladi (bu bizdagi holatni haqiqatga
  moslaydi, pulni qaytarmaydi).

Sinov: `python -m platforma.sinov_paylov` — 30+ tekshiruv (auth, summa,
idempotentlik, konkurent `perform`, muddat, kvota darvozasi). Skript o'z sinov
useri/planini yaratadi va oxirida o'chiradi; `sozlamalar` jadvaliga tegmaydi.

## Deploy

**Domen: https://twin.virtaks.uz** (hozir offline — DO ga noldan ko'chmoqda)

Deploy artefaktlarining hammasi repoda, `joylash/` papkasida — Dockerfile,
docker-compose.yml, Caddyfile va uchta skript. To'liq runbook:
[`../DEPLOY_DO.md`](../DEPLOY_DO.md).

```
caddy (80/443, avtomatik TLS)
  └── web (FastAPI, 8900)        ── db (pgvector/pgvector:pg18)
      ishchi (worker)            ── minio (S3)
```

Tashqariga faqat `caddy` chiqadi; `db` va `minio` host portlari `127.0.0.1`
da (SSH tunnel orqali xizmat ko'rsatiladi).

```bash
cd joylash
bash yangilash.sh --tort     # git pull + build + servislarni almashtirish
bash holat.sh                # ko'rik: servislar, navbat, zaxira, xatolar
bash tikla.sh --dump <fayl> --ombor <papka>   # eski serverdan ko'chirish
```

Imij ikki nishonli (`joylash/Dockerfile`):

| Nishon | Nima bor | Kim ishlatadi |
|---|---|---|
| `web` | python + kutubxonalar + kod | `web` servisi (~640 MB) |
| `ishchi` | + ffmpeg, LibreOffice, postgresql-client-18 | `ishchi` servisi (~1.8 GB) |

Ajratishning sababi: og'ir ish faqat worker'da bajariladi, web'da ffmpeg
ham, LibreOffice ham chaqirilmaydi — bitta og'ir imijni ikkalasiga berish
har deployda 1.1 GB ni bekorga ko'chirish demakdi.

Migratsiyalar konteyner ishga tushganda o'zi qo'llanadi. Web va ishchi bir
vaqtda ko'tarilgani uchun `pg.migratsiya()` konsultativ qulf ostida ishlaydi
(`pg.QULF_KALIT`) — ikkovi bir xil `.sql` ni parallel qo'llab yiqilmaydi.

### Bo'sh bazani to'ldirish

Eski server (169.58.79.192) butunlay o'chgan va bazadan zaxira qolmagan,
shuning uchun yangi o'rnatish lokal materiallardan urug'lantiriladi:
`joylash/urugla.ps1` (Windowsdan, SSH tunnel orqali) — 2 twin, 7 direktor,
**2897 bo'lak va ularning vektorlari** (qayta embedding YO'Q), 13 shablon,
eski suhbat/majlis tarixi. 926 CJM/EJM savoli migratsiya bilan o'zi tushadi.
Ixtiyoriy bosqichlar: asl media -> MinIO, 36 PDF qayta ingest (~$7).
Batafsil: `../DEPLOY_DO.md` §6.

Ommaviy fayl yuklash uchun alohida vosita bor — `manba_yukla.py`
(kabinetdagi yuklash oqimining konsol nusxasi, qayta yugurtirish xavfsiz).

### Railway (eski, zaxira sifatida saqlanadi)

`pure-optimism` loyihasi: `twin-web` va `worker` **Offline**, Postgres va
MinIO ma'lumoti joyida. Rollback faqat ko'chish kunida xavfsiz — keyin
yangi serverda paydo bo'lgan ma'lumot u yerda bo'lmaydi.

```powershell
$env:RAILWAY_TOKEN = "<token>"          # faqat shu sessiyada, saqlanmaydi
Set-Location ..\deploy_platforma
railway up --service twin-web --detach
```
