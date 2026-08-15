# TIZIMLASHTIRISH HALQASI (biznes) — to'liq ishlab chiqish rejasi

Manba: ustozning ovozli tushuntirishi (2026-08-14, 8 daqiqa) va ikkita
diagnostika quroli — `CJM yangi.xlsx`, `EJM yangi.xlsx`.

Mavjud **maqsad halqasi** (`MAQSAD_REJA.md`) — bitta odamning shaxsiy
maqsadi uchun. Bu reja esa **korxona** uchun: twin biznesni diagnostika
qiladi, xulosa chiqaradi, SMART maqsad qo'yadi va bo'limlar kesimida reja
tuzadi. Ikkalasi bir xil mexanikaga (holat mashinasi + `yordamchi.navbatga`
ko'prigi) quriladi, lekin alohida jadvallarda yashaydi.

Bu bosqichda halqaning **1-3 qadami** quriladi (egasi shu uchtasini
ko'rsatdi). 4-10 qadamlar — keyingi bosqich, 2-bo'limda xaritada.

---

## 1. Maqsad — egasi talablari

Audiodan olingan ketma-ketlik (ustozning so'zlari bilan):

1. **Tahlil** — CJM va EJM diagnostikasi. «To'liq ishlarni bormi-bormi-bormi
   deb turib birinchi tekshirib chiqamiz. Keyin ha yoki yo'qligiga qarab,
   borlarini qanaqa holatda, bor bo'lsa ham **to'g'ri ketma-ketlik bo'yicha
   ishlatishyaptimi**, u narsani ko'rib chiqamiz.» Natija: qaysi qismda xato
   borligi yozib olinadi.
2. **Maqsad** — rahbar bilan, **SMART** mezonlari bo'yicha. Maqsad moliyaviy
   holat va resurslarga solishtiriladi: «ko'rpasiga qarab oyoq uzatishini
   ta'minlab beradi… byudjet shuni ko'taradimi, resurslar shuni ko'taradimi».
3. **Rejalashtirish** — bo'limlar kesimida, har biriga o'z quroli.

Halqa aylanma: «shu ketma-ketlik asosida doimiy ravishda aylanib, aylanib,
aylanib, ishlar doim tarzda amalga oshirib boriladi».

---

## 2. Metodika qatlami — mavjud BTM halqasi bilan bog'lanish

`maqsad.py` dagi `METODIKA` lug'ati (10 teg: maqsad, rejalashtirish,
intizom, raqamlashtirish, avtomatlashtirish, muhit, moliya, harakat, tahlil,
optimizatsiya) — **shaxsiy** halqa. Audiodagi **biznes** halqasi boshqa
tartibda va boshqa nomlar bilan:

| # | Biznes halqasi (audio) | Quroli | Shu rejada |
|---|---|---|---|
| 1 | Tahlil | CJM + EJM diagnostikasi | ✅ quriladi |
| 2 | Maqsad | SMART | ✅ quriladi |
| 3 | Rejalashtirish | SSP, mediaplan, moliya modeli, Gantt | ✅ quriladi |
| 4 | Standartlar | org model, biznes-protsess, lavozim vazifasi, cheklist | keyingi bosqich |
| 5 | Onlaynlashtirish / raqamlashtirish | amoCRM, Sheets | keyingi bosqich |
| 6 | Avtomatlashtirish | AI agentlar | keyingi bosqich |
| 7 | Jamoa to'plash | EJM standarti | keyingi bosqich |
| 8 | Moliyalashtirish | — | keyingi bosqich |
| 9 | Amalga oshirish | — | keyingi bosqich |
| 10 | Nazorat | task-menejment, Gantt | keyingi bosqich |

Shuning uchun **yangi oq ro'yxat** `HALQA` kiritiladi (10 ta biznes tegi),
mavjud `METODIKA` ga TEGILMAYDI — shaxsiy maqsad halqasi o'zgarishsiz
ishlaydi.

---

## 3. Diagnostika qurollari — nima bor

| | CJM (mijoz yo'li) | EJM (xodim yo'li) |
|---|---|---|
| Bosqich | 7 | 5 (+ kesuvchi bloklar) |
| Blok | 30 | 29 |
| Savol | **560** | **366** |

CJM: Tanilish 102, Ishonch 97, Sotuv 139, Qayta sotuv 50, Tavsiya 50,
Raqamli muloqot va AI 32, Muhit 90.

EJM: Tanilish 45, Saralash 54, Moslashtirish 47, Ishlash 64, Sodiqlik 44,
kesuvchi bloklar 112 (HR hujjatlari, Davomat, Ta'til, Ish sifati, Mijoz
natijasi, Mijozlar bilan aloqa, Rahbarlik sifati, Zaxira kadrlar, Xodimlar
AI'ni bilish darajasi).

**Jami 926 savol.** Ikkala fayl ham hozir bo'sh shablon — birorta javob
to'ldirilmagan.

Excel'dagi ballash: javob `F` ustuniga «Ha» deb yoziladi, foiz
`=COUNTIF(F;"Ha")/savollar_soni`, Dashboard bosqich kesimida foiz beradi.
Shu formula serverga aynan ko'chiriladi.

---

## 4. Bosh tamoyillar (prod-darajaning asosi)

1. **Ball va foizni SERVER hisoblaydi.** LLM birorta ballga, foizga yoki
   holatga ta'sir qila olmaydi (CLAUDE.md 2-qoida).
2. **Savol banki — qotirilgan ma'lumot.** Savol matni o'zgarsa `versiya`
   oshadi; eski diagnostika eski versiyaga bog'liq qoladi, aks holda uning
   foizi keyin «o'zgarib» ketardi.
3. **Grounding.** Xulosa va tavsiyalardagi har da'voda `[n]` iqtibos;
   bo'lak ID'lari faqat `qidiruv.qidir` dan. Bilim yetmasa — `umumiy=true`
   yorlig'i, taxmin yo'q.
4. **Diagnostika — chat emas, ro'yxat.** 926 savolni suhbatda so'rash
   mumkin emas; kabinetda cheklist UI, har javob darhol saqlanadi.
5. **Additiv migratsiya.** `011_tizim.sql` faqat yangi jadval va ustun
   qo'shadi; `maqsadlar`, `suhbatlar`, `majlislar` sxemasi buzilmaydi.
6. **Ikki qatlam** (maqsad halqasidan meros): MEXANIKA — holat mashinasi,
   foiz, o'tish qoidalari (SQL); KONTENT — matn (LLM).

---

## 5. Foydalanuvchi tajribasi (qanday ko'rinadi)

**Kirish.** Kabinetda yangi bo'lim: «Biznesni tizimlashtirish».
Foydalanuvchi korxona nomini kiritadi va diagnostika turini tanlaydi: CJM,
EJM yoki ikkalasi.

**1-qadam: Diagnostika.** Bosqich va blok bo'yicha akkordeon: masalan
«Tanilish → INSTAGRAM (32 savol)». Har savolda uchta tugma:

- **Ha** — bor
- **Yo'q** — yo'q
- **Qisman** — bor, lekin to'liq emas

«Ha» bosilganda ixtiyoriy **sifat darajasi** ochiladi (1-3): «bor, lekin
tartibsiz» / «bor, standart bo'yicha» / «bor, o'lchanadi va yaxshilanadi».
Bu audiodagi ikkinchi talabni — «bor bo'lsa ham to'g'ri ketma-ketlik
bo'yicha ishlatishyaptimi» — o'lchash uchun. Excel shablonida bu yo'q edi.

Yuqorida jonli progress: umumiy foiz va bosqich kesimidagi foizlar
(Dashboard varag'ining o'rnini bosadi). Javoblar avtosaqlanadi, yarim
tashlab ketib qaytish mumkin.

**2-qadam: Xulosa.** Diagnostika yakunlangach twin xulosa yozadi: eng zaif
bosqichlar, «yo'q» javoblar ichidan eng og'riqli 10 tasi, har biriga ustoz
darslaridan iqtibosli izoh. Foizlar serverdan, matn modeldan.

**3-qadam: SMART maqsad.** Suhbat rejimida: twin savol beradi, foydalanuvchi
javob beradi. Server har mezonni alohida tekshiradi va qizil-yashil
ko'rsatadi.

**4-qadam: Bo'lim rejalari.** Maqsad tasdiqlangach twin har bo'lim uchun
qoralama tuzadi; foydalanuvchi tahrirlaydi va tasdiqlaydi:

| Bo'lim | Quroli | Ko'rinishi |
|---|---|---|
| Sotuv | SSP jadvali | oy/kun × to'lov summasi × kerakli suhbat soni |
| Marketing | Mediaplan + kontent-plan | sana × kanal × format × lid rejasi |
| Moliya | Moliya modeli | oy × kirim × chiqim × qoldiq × «qachongacha chidaymiz» |
| HR | Xodim rejasi | lavozim × qachon kerak × rekruting boshlanishi |
| Boshqaruv | Gantt | qadamlar vaqt o'qida (mavjud `maqsad_qadamlar` dan) |
| Produkt | — | ⚠️ 12-bo'limga qarang |

SSP va moliya modeli o'zaro bog'liq: SSP dagi to'lov rejasi moliya
modelining kirim qatoriga tushadi — **server** ko'chiradi, model emas.

---

## 6. Ma'lumotlar modeli — `migratsiyalar/011_tizim.sql`

```sql
-- Savol banki: CJM 560 + EJM 366 = 926 savol. Matn qotirilgan.
CREATE TABLE IF NOT EXISTS diag_savollar(
  id        bigserial PRIMARY KEY,
  tur       text NOT NULL,              -- 'cjm' | 'ejm'
  bosqich   text NOT NULL,              -- 'Tanilish', 'Sotuv', ...
  blok      text NOT NULL,              -- 'INSTAGRAM', 'CRM', ...
  tartib    int  NOT NULL,
  matn      text NOT NULL,
  versiya   int  NOT NULL DEFAULT 1,
  UNIQUE (tur, bosqich, blok, tartib, versiya)
);

CREATE TABLE IF NOT EXISTS diagnostikalar(
  id         bigserial PRIMARY KEY,
  user_id    bigint NOT NULL REFERENCES userlar(id) ON DELETE CASCADE,
  twin_id    bigint NOT NULL REFERENCES twinlar(id) ON DELETE CASCADE,
  korxona    text NOT NULL DEFAULT '',
  tur        text NOT NULL,             -- 'cjm' | 'ejm'
  versiya    int  NOT NULL DEFAULT 1,   -- savol banki versiyasi (muzlatilgan)
  holat      text NOT NULL DEFAULT 'toldirilmoqda',
    -- toldirilmoqda | xulosa_kutilmoqda | tayyor | bekor
  foiz       int,                       -- SERVER hisoblaydi (0-100)
  foiz_bosqich jsonb NOT NULL DEFAULT '{}',  -- {"Tanilish": 42, ...}
  xulosa     jsonb NOT NULL DEFAULT '{}',    -- {matn, zaif:[], ogriqli:[]}
  narx_usd   numeric(12,6) NOT NULL DEFAULT 0,
  boshlangan  timestamptz NOT NULL DEFAULT now(),
  yangilangan timestamptz NOT NULL DEFAULT now(),
  tugallangan timestamptz
);
-- Bitta korxona+tur bo'yicha bitta tugallanmagan diagnostika (fokus qoidasi).
CREATE UNIQUE INDEX IF NOT EXISTS idx_diag_fokus
  ON diagnostikalar(user_id, twin_id, tur)
  WHERE holat NOT IN ('tayyor', 'bekor');

CREATE TABLE IF NOT EXISTS diag_javoblar(
  diagnostika_id bigint NOT NULL REFERENCES diagnostikalar(id) ON DELETE CASCADE,
  savol_id       bigint NOT NULL REFERENCES diag_savollar(id),
  javob          text NOT NULL,         -- 'ha' | 'yoq' | 'qisman'
  sifat          int,                   -- 1-3, faqat javob='ha' bo'lganda
  izoh           text NOT NULL DEFAULT '',
  yangilangan    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (diagnostika_id, savol_id)
);

-- Bo'lim rejalari. Har qurol — bitta qator, jadvali jsonb ichida
-- (shakli qurolga qarab farq qiladi, server sxema bo'yicha tekshiradi).
CREATE TABLE IF NOT EXISTS bolim_rejalar(
  id        bigserial PRIMARY KEY,
  maqsad_id bigint NOT NULL REFERENCES tizim_maqsadlar(id) ON DELETE CASCADE,
  bolim     text NOT NULL,   -- sotuv|marketing|moliya|hr|boshqaruv|produkt
  tur       text NOT NULL,   -- ssp|mediaplan|kontentplan|moliya_model|hr_reja|gantt
  sarlavha  text NOT NULL DEFAULT '',
  jadval    jsonb NOT NULL DEFAULT '[]',   -- qatorlar massivi
  jami      jsonb NOT NULL DEFAULT '{}',   -- SERVER hisoblagan yig'indilar
  holat     text NOT NULL DEFAULT 'qoralama',  -- qoralama|tasdiqlangan
  yaratilgan timestamptz NOT NULL DEFAULT now(),
  UNIQUE (maqsad_id, bolim, tur)
);

-- Biznes maqsadi — SHAXSIY `maqsadlar` dan mustaqil jadval.
CREATE TABLE IF NOT EXISTS tizim_maqsadlar(
  id       bigserial PRIMARY KEY,
  user_id  bigint NOT NULL REFERENCES userlar(id) ON DELETE CASCADE,
  twin_id  bigint NOT NULL REFERENCES twinlar(id) ON DELETE CASCADE,
  diagnostika_id bigint REFERENCES diagnostikalar(id) ON DELETE SET NULL,
  korxona  text NOT NULL DEFAULT '',
  sarlavha text NOT NULL DEFAULT '',
  tafsilot jsonb NOT NULL DEFAULT '{}',  -- {matn, olchov, muddat, byudjet, resurs}
  smart    jsonb NOT NULL DEFAULT '{}',  -- SERVER bahosi (5 mezon)
  holat    text NOT NULL DEFAULT 'intervyu',
  suhbat_id bigint REFERENCES suhbatlar(id) ON DELETE SET NULL,
  ...
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tizim_maqsad_fokus
  ON tizim_maqsadlar(user_id, twin_id)
  WHERE holat NOT IN ('tugallangan', 'bekor');

ALTER TABLE suhbatlar ADD COLUMN IF NOT EXISTS tizim_maqsad_id bigint
  REFERENCES tizim_maqsadlar(id) ON DELETE SET NULL;
```

**Nega `maqsadlar` QAYTA ISHLATILMADI** (rejadagi dastlabki qarordan voz
kechildi): shaxsiy maqsad halqasida `idx_maqsad_fokus` unikal indeksi
«bitta user+twin = bitta ochiq maqsad» deydi. Biznes maqsadi o'sha jadvalga
yozilsa, foydalanuvchi biznes maqsadi ustida ishlayotgan paytda **jonli**
shaxsiy maqsad halqasi bloklanib qolardi (va aksincha). Fokus qoidasi
ikkalasida ham kerak, lekin ular BIR-BIRINI to'smasligi shart — shuning
uchun biznes halqasi o'z jadvallarida yashaydi, fokus indeksi ham o'zining
(`idx_tizim_maqsad_fokus`). Qadam/ish mexanikasi biznesda ishlatilmaydi:
u yerda qadam o'rniga BO'LIM REJALARI (jadvallar) turadi.

---

## 7. Yangi modullar va o'zgarishlar

| Fayl | Nima |
|---|---|
| `platforma/tizim.py` | halqa mexanikasi: savol banki, foiz, holat mashinasi, SMART tekshiruvi |
| `platforma/tizim_oqim.py` | SMART intervyusi (SSE), `yordamchi.navbatga` ko'prigi |
| `platforma/savol_yukla.py` | xlsx → `diag_savollar`; `--sql` bilan migratsiya urug'i |
| `platforma/migratsiyalar/011_tizim.sql` | yuqoridagi sxema |
| `platforma/migratsiyalar/012_savollar.sql` | 926 savol urug'i (avtomatik yaratilgan) |
| `platforma/worker.py` | +2 handler: `tizim_xulosa`, `tizim_reja` |
| `platforma/web.py` | +14 marshrut (9-bo'lim) |
| `platforma/web/index.html` | diagnostika cheklisti, foiz paneli, SMART karta, reja jadvallari |
| `platforma/web/ui.css` | `tz-*` komponentlari (cheklist, jadval, halqa) |
| `platforma/db.py` | `suhbatlar` ro'yxatiga `tizim_maqsad_id` |
| `platforma/tayyorlik.py` | +3 tekshiruv (savol banki to'liqmi, foiz formulasi, oq ro'yxatlar) |

Yangi framework kiritilmaydi (CLAUDE.md 5-qoida): jadval va modal
`ui.css`/`ui.js` dagi mavjud komponentlardan.

---

## 8. Oqimlar batafsil

### 8.1 Savol bankini yuklash — `savol_yukla.py`

`CJM yangi.xlsx` va `EJM yangi.xlsx` o'qiladi (openpyxl), bosqich/blok/matn
ajratiladi, `diag_savollar` ga `UNIQUE` bo'yicha upsert qilinadi. Skript
**idempotent**: ikki marta ishlatilsa dubl chiqmaydi. Manba fayllar
`materiallar/diagnostika/` ga ko'chiriladi (savol banki — mahsulot mazmuni).

### 8.2 Diagnostika — LLM'siz

Javob yozilganda server darhol foizni qayta hisoblaydi:

```
foiz = ha_soni / savollar_soni          -- Excel formulasining aynan o'zi
```

`qisman` — 0.5 emas, **0** (Excel bilan bir xil qolishi uchun), lekin
xulosada alohida ro'yxat bo'lib chiqadi. Sifat darajasi foizga ta'sir
qilmaydi — u ikkinchi o'lchov (`sifat_ortacha`) sifatida ko'rsatiladi.

### 8.3 Xulosa — worker job `tizim_xulosa`

Kirish: diagnostika ID. Server «yo'q» va «qisman» javoblarni bosqich
kesimida yig'adi, eng past foizli 3 bosqich va eng og'riqli 10 savolni
**o'zi tanlaydi** (LLM emas). Keyin model faqat matn yozadi: har bandga
nima uchun muhimligi va birinchi qadam, ustoz darslaridan `[n]` iqtibos
bilan. Sxema bilan majburlangan JSON.

### 8.4 SMART maqsad — `tizim_oqim.suhbat_oqimi`

Mavjud `maqsad_oqim` naqshi: suhbat SSE bilan oqadi, oxirida sxemali xulosa.
Farqi — server beshta mezonni alohida baholaydi:

| Mezon | Server nimaga qaraydi |
|---|---|
| Aniq | maqsad matnida raqam va obyekt bormi |
| O'lchanadigan | `olchov` maydoni to'ldirilganmi (birlik + qiymat) |
| Erishsa bo'ladigan | kerakli summa ≤ moliya modelidagi mavjud resurs |
| Ahamiyatli | diagnostikadagi zaif bosqich bilan bog'liqmi |
| Muddatli | `muddat` sana bormi va kelajakdami |

Mezon qizil bo'lsa maqsad `faol` holatga **o'ta olmaydi** — bu SQL cheklovi,
LLM'ning fikri emas.

### 8.5 Bo'lim rejalari — worker job `tizim_reja`

Har bo'lim uchun alohida job (6 tagacha, parallel). Model jadval qatorlarini
qoralama qilib qaytaradi (sxemali JSON), server:

- summalarni **o'zi** hisoblaydi (`jami`),
- SSP kirimini moliya modeliga ko'chiradi,
- oq ro'yxatdan tashqari bo'lim/tur nomini jimgina tashlaydi.

Foydalanuvchi tahrirlaydi va `tasdiqlangan` holatiga o'tkazadi. Tasdiqlangan
reja qatorlari `maqsad_qadamlar` ga (`bolim` tegi bilan) tushadi — shundan
Gantt va eslatmalar avtomatik ishlaydi.

---

## 9. API yuzasi

```
GET    /api/tizim                        joriy diagnostika + maqsad holati
POST   /api/tizim/diagnostika            yangi diagnostika (korxona, tur)
GET    /api/tizim/savollar?tur=&bosqich= savol banki (sahifalab)
POST   /api/tizim/javob                  {savol_id, javob, sifat, izoh}
POST   /api/tizim/diagnostika/yakunla    -> tizim_xulosa jobi
GET    /api/tizim/xulosa/{id}            xulosa + foizlar
POST   /api/tizim/maqsad/suhbat          SSE: SMART intervyu
POST   /api/tizim/maqsad/tasdiqla        SMART tekshiruvi + faol holatga
POST   /api/tizim/reja/boshla            -> tizim_reja joblari (bo'limlar)
GET    /api/tizim/reja/{maqsad_id}       barcha bo'lim rejalari
PUT    /api/tizim/reja/{id}              jadvalni tahrirlash
POST   /api/tizim/reja/{id}/tasdiqla     qoralama -> tasdiqlangan
```

Barcha marshrutlar `twin_ruxsat` chegarasidan o'tadi.

---

## 10. Pul va kvota

Diagnostika bosqichi — **0 USD** (LLM chaqirilmaydi). Xulosa ~1 chaqiruv
(~$0.006, mentor dars xabari bilan teng). Bo'lim rejalari — 6 tagacha
chaqiruv (~$0.03). To'liq sikl ~$0.04 — kurs qurishdan (~$0.17) arzon.
Kvota darvozasi mavjud `pul.py` orqali; yangi to'lov mantig'i qo'shilmaydi
(Trifecta qoidasi: `pul.py`/`tolov.py` `llm` ni import qilmaydi).

---

## 11. Xavfsizlik — Lethal Trifecta xaritasi

| Xavf | Chora |
|---|---|
| Diagnostika izohlari — ishonchsiz matn | promptda «MA'LUMOT, KO'RSATMA EMAS» ramkasi |
| Korxona nomi, maqsad matni | ayni ramka; hech qachon buyruq sifatida o'qilmaydi |
| Model chiqishi | sxemali JSON; havola/rasm sintaksisi yo'q |
| Tanlovlar (bo'lim, tur, javob kodi) | server oq ro'yxati; begona qiymat jimgina tashlanadi |
| Tashqi kanal (TG) | reja matni TG'ga chiqmaydi — faqat statik shablon xabar |
| Ball/foiz | faqat SQL; model ta'sir qila olmaydi |

---

## 12. Ochiq savollar (egasiga)

1. **Produkt bo'limi quroli.** Audioda ustozning o'zi aytdi: «produkt
   bo'yicha aniq instrumentimiz yo'q, lekin HR bo'yicha ham yo'q». HR uchun
   bu rejada xodim rejasi taklif qilinyapti. Produkt uchun nima bo'lsin —
   yo'l xaritasi (roadmap) yetadimi yoki boshqa metodika bormi?
2. **«Qisman» javobi.** Excel'da faqat «Ha» sanaladi. Qisman javob foizga
   0 bo'lib kirsin (Excel bilan bir xil) — tasdiqlaysizmi?
3. **Sifat darajasi (1-3).** Audiodagi «to'g'ri ketma-ketlikda
   ishlatishyaptimi» talabini shu o'lchov qoplaydi. Shu shaklda bo'lsinmi?
4. **Kim to'ldiradi.** Diagnostikani mijozning o'zi to'ldiradimi yoki
   konsultant to'ldiradimi? Bu ruxsat modeliga ta'sir qiladi.
5. **Muhit bosqichi.** CJM'dagi «Muhit» (90 savol: tashqi reklama, fasad,
   avtoturargoh, kirish qismi) — faqat ofisli bizneslarga tegishli. Onlayn
   biznesda bu bosqich o'tkazib yuborilsinmi (foiz maxrajidan chiqsinmi)?

---

## 13. Bajarish bosqichlari va «tayyor» mezonlari

| # | Ish | «Tayyor» mezoni |
|---|---|---|
| 1 | `011_tizim.sql` + `savol_yukla.py` | `SELECT count(*) FROM diag_savollar` = 926; ikki marta yuklansa ham 926 |
| 2 | `tizim.py` mexanikasi | foiz Excel formulasi bilan bit-ma-bit teng (sinov: 20 javob, qo'lda hisob) |
| 3 | Diagnostika UI | 926 savolli ro'yxat silliq aylanadi, javob 200 ms ichida saqlanadi |
| 4 | `tizim_xulosa` jobi | xulosadagi har band `[n]` iqtibosli; iqtibossiz band `tekshiruv.iqtibos_tekshir` dan o'tmaydi |
| 5 | SMART tekshiruvi | qizil mezonda `faol` ga o'tish 409 qaytaradi (SQL cheklovi) |
| 6 | `tizim_reja` joblari | 6 bo'lim, har biri sxemali JSON; SSP → moliya modeli ko'chirish server tomonda |
| 7 | Regressiya | mavjud sinovlar (69 + maqsad halqasi) yashil qoladi |
| 8 | `tayyorlik.py` | 3 yangi tekshiruv yashil |

Yangi sinov fayli: `platforma/sinov_tizim.py` (~40 tekshiruv), naqsh
`sinov_paylov.py` dan.

---

## 14. Risklar va qarshi choralar

| Risk | Qarshi chora |
|---|---|
| 926 savol foydalanuvchini charchatadi | bosqichma-bosqich, avtosaqlash, «keyin davom ettirish»; xulosa qisman javoblar bilan ham chiqadi |
| Savol matni keyin o'zgaradi | `versiya` ustuni: eski diagnostika eski matnga bog'liq qoladi |
| Model reja jadvaliga o'ylab topilgan raqam yozadi | summalar server tomonda; model faqat qatorlarni taklif qiladi |
| Ikkita halqa (shaxsiy/biznes) chalkashadi | alohida jadval, alohida oq ro'yxat, UI'da alohida bo'lim; `METODIKA` ga tegilmaydi |
| Job yarim yiqiladi | mavjud qoida: noma'lum/yiqilgan job qayta navbatga, javoblar bazada qoladi |

---

## 15. Hajm bahosi

| Qism | Qator (taxminan) |
|---|---|
| `011_tizim.sql` | 90 |
| `savol_yukla.py` | 150 |
| `tizim.py` | 700 |
| `tizim_oqim.py` | 300 |
| `web.py` qo'shimchasi | 350 |
| `worker.py` qo'shimchasi | 40 |
| `index.html` + `ui.css` qo'shimchasi | 800 |
| `sinov_tizim.py` | 400 |
| **Jami** | **~2800 qator** |

Maqsad halqasi (11-bosqich) hajmiga yaqin.

---

## 16. Bajarildi (2026-08-15)

Halqaning 1-3 qadami to'liq qurildi va prodga chiqarildi.

| Qism | Fayl | Holat |
|---|---|---|
| Sxema | `migratsiyalar/011_tizim.sql` | 5 jadval, 2 fokus indeksi, to'liq additiv |
| Savol banki | `migratsiyalar/012_savollar.sql` | CJM 560 + EJM 366 = **926**; `savol_yukla.py --sql` bilan yaratiladi |
| Mexanika | `tizim.py` | foiz (Excel formulasi, bitta SQL), SMART qoidalari, jadval yig'indilari, SSP → moliya ko'chirishi |
| Intervyu | `tizim_oqim.py` | SSE, `rejim='tizim'`, karta faqat sxemali JSON |
| Joblar | `worker.py` | `tizim_xulosa`, `tizim_reja` + yakuniy yiqilishda `diag_qaytar` |
| API | `web.py` | 14 marshrut, chat oqimida `tizim_maqsad_id` yo'nalishi |
| UI | `web/index.html`, `web/ui.css` | «Biznes tizimi» bo'limi: halqa, cheklist (avtosaqlash), xulosa, SMART karta, 6 bo'lim jadvali |
| Sinovlar | `sinov_tizim.py` | 73 tekshiruv; job yaratmaydi (`jobs.qoshish` ushlab qolinadi) |
| Ko'rik | `tayyorlik.py` | 10-bo'lim: bank to'liqligi, foiz formulasi, oq ro'yxatlar, yig'indi mosligi |

Rejadan chetlanishlar (sabab bilan):

1. **`tizim_maqsadlar` alohida jadval** — 6-bo'limga qarang (fokus indeksi
   shaxsiy maqsad halqasini bloklab qo'yardi).
2. **UI `index.html` da**, `kabinet.html` da emas — cheklist va SMART karta
   foydalanuvchi (rahbar) quroli, kabinet esa TWIN EGASI konsoli. Dars va
   maqsad halqasi ham shu sahifada yashaydi, naqsh bir xil qoldi.
3. **Savol banki migratsiya bo'lib ketdi** — `materiallar/*.xlsx` deploy
   paketiga kirmaydi; urug' fayl har muhitda `python -m platforma.pg`
   bilan o'z-o'zidan yuklanadi va takror ishga tushirilsa dubl bermaydi.

Keyingi bosqich — halqaning 4-10 qadami (Standartlar, Raqamlashtirish,
Avtomatlashtirish, Jamoa, Moliyalashtirish, Amalga oshirish, Nazorat).
UI'da ular hozir «keyingi bosqichda ochiladi» bo'lib turadi.
