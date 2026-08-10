# KENGASH — AI Direktorlar Kengashi (RAG asosida)

Siz bergan manbalar (audio, video, PDF slayd, Excel, Word) asosida ishlaydigan
6 direktor (CEO, CTO, CFO, COO, CLO, CMO) + Rais tizimi. Har javob manbaga
tayanadi va citation ko'rsatadi; manbada yo'q narsani to'qimaydi.

## Arxitektura

```
manbalar (mp3/mp4/pdf/xlsx/docx/txt)
   │  ingest.py — turiga qarab o'qish:
   │    audio/video -> STT (vaqt belgili, 10 daq bo'laklar, parallel)
   │    PDF slayd   -> Gemini vision OCR (sahifama-sahifa Markdown)
   │    XLSX        -> Markdown jadval
   │    DOCX/TXT    -> matn
   ▼
kanonik/  — <slug>.md (odam uchun) + <slug>.jsonl (RAG bo'laklari + teglar)
   │  indeks.py — gemini-embedding-001 (3072) -> Qdrant (lokal) + BM25
   ▼
baza/     — vektor + kalit-so'z indekslari
   │  qidiruv.py — hybrid (vektor+BM25, RRF) + rol filtri
   ▼
majlis.py — savol -> RAIS yo'naltiradi -> direktorlar parallel javob
            (har biri o'z sohasi RAG'i bilan, citation majburiy)
            -> RAIS sintez -> chiqish/majlis_NNN.md
```

## Foydalanish

```powershell
$py = "E:\NewOffice\Labaratoriya\VoIpTelefoniya\.venv\Scripts\python.exe"

# 1. Manba qo'shish (fayl yoki butun papka) — --ustoz MAJBURIY:
#    bilim qaysi ustozniki ekanini belgilaydi (sozlama.USTOZLAR ro'yxatidan)
& $py -m kengash.ingest "D:\manbalar\yangi_dars" --ustoz "Axrolxo'ja"   # --qayta = qayta o'qish

# 2. Indeksni yangilash (har yangi manbadan keyin)
& $py -m kengash.indeks

# 3. Kengashga savol berish
& $py -m kengash.majlis "Sotuvni oshirish uchun nima qilaylik?"
& $py -m kengash.majlis "Savol" --hamma                  # 6 direktor majburiy
& $py -m kengash.majlis "Savol" --ustoz "Abdulloh"       # faqat shu ustoz bilimidan

# 4. YOKI brauzerda ishlash (tavsiya qilinadi)
& $py -m kengash.server        # keyin brauzerda: http://127.0.0.1:8765
```

Web-interfeys (kengash/web/index.html): chat ko'rinishi — jonli direktor chiplari,
RAIS/direktor tab'lari, bosiladigan [n] iqtiboslar (manba ro'yxatiga sakraydi),
tarixdan qidiruv (Ctrl+K). Faqat 127.0.0.1 (lokal) — tashqariga HTTPS tunel orqali
chiqariladi (pastga qarang).
Eslatma: server ishlayotgan payt `indeks` qurmoqchi bo'lsangiz, avval serverni
to'xtating (majlis ketayotganda Qdrant bandligi mumkin).

## Ko'p foydalanuvchi + Telegram (2026-07-23)

- **Akkauntlar**: har user faqat O'Z suhbat tarixini ko'radi (SQLite: `baza/kengash.db`
  — userlar, sessiyalar, majlis egaligi). Birinchi ro'yxatdan o'tgan user tizim
  egasi — eski majlislar unga meros bo'ladi. Hisobot API'si egalikni tekshiradi.
- **Kirish**: faqat Telegram orqali (HMAC imzo tekshiruvi, `auth.py`):
  - saytda — Telegram Login Widget;
  - Telegram ichida — Mini App (initData bilan avtomatik kirish);
  - botda kontakt yuborilsa — akkaunt telefon raqamiga bog'lanadi (`tg.py`;
    faqat o'z kontakti qabul qilinadi).
  - `TELEGRAM_BOT_TOKEN` .env da bo'lmasa DEV-REJIM: ism bilan kirish (faqat sinov).
- **Navbat** (`navbat.py`): majlislar bitta ishchi oqimda tartib bilan; har userda
  bitta faol so'rov; UI navbatdagi o'rinni ko'rsatadi.
- **Savol aniqligi** (`aniqlik.py`): tushunarsiz/juda umumiy savolda majlis
  boshlanmaydi — "Siz shuni so'ramoqchimidingiz?" deb 3-4 aniq variant tugma
  chiqadi (Claude uslubi); "baribir yuborish" ham mumkin.
- **User o'rganish** (`profil.py`): har majlisdan keyin user profili (mavzular,
  ehtimoliy rol, uslub) fonda yangilanadi; keyingi javob uslubini moslashtiradi
  va variantlarni shaxsiylashtiradi. Profil FAKT MANBASI EMAS — grounding buzilmaydi.

## Ustozlar bo'yicha bilim kategoriyalari (2026-07-26)

Har bilim bo'lagi qaysi ustozning darslaridan ekanini biladi (`ustoz` maydoni):
eski butun baza — **Abdulloh**, yangi bilimlar ingest'da `--ustoz` bilan belgilanadi.
Ro'yxat `sozlama.USTOZLAR` da ("Abdulloh", "Axrolxo'ja") — yangi ustoz kelsa shu
ro'yxatga bitta qator qo'shiladi.

- **UI sozlama** (yon panel, "Bilim manbasi"): har user o'zi tanlaydi —
  1) Abdulloh ustoz, 2) Axrolxo'ja ustoz, 3) Barcha ustozlar bilimi. Tanlov
  `userlar.ustoz` ustunida saqlanadi (`/api/ustoz`), har ustoz yonida bo'lak soni.
- **Qat'iy filtr**: tanlangan ustoz qidiruvda ham vektor (Qdrant payload), ham
  BM25 tomonda filtrlaydi; teg-fallback ham ustoz chegarasidan chiqmaydi. Tanlangan
  ustozda javob bo'lmasa kengash halol "MANBADA YO'Q" deydi.
- Hisobotda **Bilim manbasi:** qatori bor — UI kartochka sarlavhasida ko'rinadi.

## Shablon xizmati — tayyor Excel fayllar (2026-07-26)

`kengash/shablonlar/*.xlsx` — 13 shablon/namuna (Gantt chart, Eyzenxauer matritsasi,
Vaqt jadvali, SSP/КПI, ORG chart/model, Gipoteza, Biznes jarayon...). Savol hujjat
TUZIShNI so'rasa (`shablon.mos` flash-tekshiruv), majlisdan keyin kengash xulosasi
asosida shablon nusxasi to'ldiriladi (`shablon.toldir`, openpyxl — tuzilish/format
saqlanadi) va:
- majlis kartasida 📎 yuklab olish tugmasi chiqadi (`/api/fayl/{nom}`, egalik tekshiriladi);
- user Telegram bilan bog'langan bo'lsa fayl botdan chatiga ham boradi (`tg.hujjat_yubor`).
Fayllar `chiqish/fayllar/` da (volume'da saqlanadi). Xato majlisni hech qachon buzmaydi.
DIQQAT: `db.majlis_yoz` UPSERT — INSERT OR REPLACE ishlatilsa biriktirma yo'qoladi.

## Lokal sinov (bulutdagi bot bilan konfliktsiz)

`$env:KENGASH_BOT_OFF="1"` bilan server yurgizilsa bot va TG kirish o'chadi (dev-rejim).
Eski `$env:TELEGRAM_BOT_TOKEN=" "` hiylasi ISHLAMAYDI — auth._env() .env ni
override=True bilan qayta yuklaydi.

## Bulutda (Railway) — production

Ilova Railway'da yashaydi: **https://kengash-production.up.railway.app**
(loyiha: pure-optimism, servis: kengash, volume: /data — userlar va majlislar
redeploy'da saqlanadi).

- Server `PORT` env bo'lsa 0.0.0.0 ga bog'lanadi (Railway), bo'lmasa 127.0.0.1 (lokal).
- `KENGASH_DATA=/data` — indeks/hisobot/DB volume'da; birinchi startda image'dagi
  tayyor indeks volume'ga ko'chiriladi. Indeks yangilansa (bm25.pkl hajmi farq)
  avtomatik almashtiriladi, `kengash.db` (userlar) esa hech qachon o'chmaydi.
- Yangi bilim qo'shish: lokalda `ingest` + `indeks`, keyin:
  ```powershell
  robocopy kengash deploy\kengash /E /XD __pycache__ .kesh
  cd deploy; $env:RAILWAY_TOKEN="<project-token>"; railway up --service kengash --detach
  ```
- Muhim: bot bir vaqtda faqat BITTA joydan ishlaydi — bulut ishlayotganda
  lokal serverni yoqmang (Telegram getUpdates konflikti).

### Telegram sozlash (bir marta)

1. @BotFather: `/newbot` -> token -> `.env` dagi `TELEGRAM_BOT_TOKEN=` ga yozing.
2. Tashqi HTTPS manzil oching: `cloudflared tunnel --url http://127.0.0.1:8765`
   (yoki doimiy domen) -> chiqqan `https://...` ni `.env` dagi `PUBLIC_URL=` ga yozing.
3. @BotFather: `/setdomain` -> o'sha domen (saytdagi Login Widget uchun).
4. Serverni qayta ishga tushiring. Botga `/start` yozilsa kontakt so'raydi va
   "Kengashni ochish" Mini App tugmasini beradi.

## Sozlash

- `personas/*.md` — direktor xarakterlari; xohlagancha tahrirlang.
- `sozlama.py` — model zanjirlari, teglar, agent-teg bog'lanishi, parallellik.
- Kalit: loyiha ildizidagi `.env` (`GEMINI_API_KEY`). Hech qachon commit qilinmaydi.

## Kafolatlar (production)

- **Grounding**: agent faqat topilgan bo'laklardan javob beradi; javob topilmasa
  "MANBADA YO'Q" deb aytadi. O'z bilimidan fakt qo'shish taqiqlangan (prompt qoidasi
  + `tekshiruv.py` nazorati).
- **Citation**: har da'vo [n] bilan manba. Manba ko'rinishi:
  - audio/video: fayl + vaqt oralig'i `[0:34:12–0:39:45]`
  - PDF slayd: fayl + `12-slayd`
  - Excel: fayl + `varaq: nomi`
  - Word/matn: fayl + `3-qism`
- **Yagona raqamlash**: hisobotda barcha direktorlarning [n] raqamlari bitta global
  MANBALAR ro'yxatiga keltiriladi — bitta [n] = bitta aniq fayl+joy (`tekshiruv.global_raqamlash`).
- **Iqtibos nazorati**: javobdagi har [n] haqiqiy manbaga tekshiriladi; mavjud bo'lmagan
  raqam yoki iqtibossiz javob aniqlansa — model bir marta tuzatish talabi bilan qayta chaqiriladi.
- **Model zanjiri**: 3.5-flash -> 2.5-pro -> 2.5-flash — birinchisi ishlamasa
  keyingisi avtomatik.
- **Retry**: 429/503 da eksponensial kutish bilan 3 urinish.
- **Idempotent ingest**: bir fayl ikki marta o'qilmaydi (--qayta bundan mustasno);
  STT/OCR natijalari `kanonik/.kesh/` da — jarayon o'lsa davomidan tiklanadi.
