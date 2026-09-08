# Virtaks — DigitalOcean'ga joylashtirish

Bu hujjat **noldan jonli saytgacha** bo'lgan yo'lni oxirigacha yozib beradi.
Barcha fayllar `joylash/` papkasida.

> **Holat (2026-09-08)**: eski server `169.58.79.192` butunlay o'chgan,
> bazadan zaxira nusxa qolmagan — ya'ni bu ko'chirish emas, **noldan qurish**.
> Bilim bazasi ishchi kompyuterdagi materiallardan tiklanadi (§6): 2897 bo'lak
> va ularning vektorlari saqlanib qolgan, shuning uchun qayta embedding
> uchun pul ketmaydi.

| Fayl | Nima qiladi |
|---|---|
| `joylash/Dockerfile` | ikki nishonli imij: `web` (yengil) va `ishchi` (ffmpeg + LibreOffice + pg_dump) |
| `joylash/docker-compose.yml` | 5 servis: caddy, web, ishchi, db, minio |
| `joylash/Caddyfile` | reverse-proxy, avtomatik Let's Encrypt TLS |
| `joylash/env.namuna` | muhit namunasi — `.env` shundan yasaladi |
| `joylash/boshlash.sh` | dropletni bir marta sozlaydi (docker, swap, ufw) |
| `joylash/yangilash.sh` | deploy va har safargi yangilash |
| `joylash/urugla.ps1` | **bo'sh dropletni lokal materiallardan to'ldirish** (Windowsdan) |
| `joylash/tikla.sh` | zaxira `.dump` dan tiklash (kelajakdagi avariyalar uchun) |
| `joylash/holat.sh` | tizim ko'rigi (o'zgartirmaydi, faqat o'qiydi) |
| `joylash/sinov.override.yml` | lokal sinov ustqurmasi (portlar surilgan, caddy'siz) |

---

## 0. Nimalar kerak

- **Droplet**: Ubuntu 24.04 LTS, kamida **4 GB RAM / 2 vCPU / 80 GB SSD**.
  Kamrog'i bilan ham ko'tariladi, lekin PPTX konvertatsiyasi (LibreOffice)
  va HNSW indeksini qurish xotira talab qiladi.
  Ko'p foydalanuvchi kutilsa — 8 GB / 4 vCPU.
- **Region**: `fra1` (Frankfurt) yoki `ams3` — O'zbekistonga eng past kechikish.
- **Domen**: `twin.virtaks.uz` (yoki boshqasi) va uning DNS boshqaruvi.
- **Kalitlar**: `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, Paylov merchant ma'lumotlari.

Taxminiy narx: droplet $24/oy + zaxira nusxa (+20%) ≈ **$29/oy**.

---

## 1. Droplet yaratish

DigitalOcean panelida: **Create → Droplets**

| Sozlama | Qiymat |
|---|---|
| Region | Frankfurt (fra1) |
| Image | Ubuntu 24.04 (LTS) x64 |
| Size | Basic → Regular SSD → 4 GB / 2 vCPU |
| Authentication | **SSH key** (parol EMAS) |
| Backups | yoqing (haftalik snapshot) |
| Monitoring | yoqing |
| Hostname | `virtaks-prod` |

Yaratilgach:

1. **Reserved IP** biriktiring (Networking → Reserved IPs). Shunda droplet
   qayta qurilsa ham IP o'zgarmaydi va DNS ni qayta sozlash kerak bo'lmaydi.
2. **Cloud Firewall** yarating: kiruvchi — `22/tcp`, `80/tcp`, `443/tcp`,
   `443/udp`; chiquvchi — hammasi. Dropletga biriktiring.

> Dropletdagi `ufw` ham sozlanadi, lekin **Docker o'z qoidalarini ufw'dan
> chetlab o'tadi**. Shuning uchun DO Cloud Firewall — asosiy himoya qatlami,
> `docker-compose.yml` da esa `db` va `minio` portlari ataylab `127.0.0.1` ga
> bog'langan.

---

## 2. DNS

Domen provayderida **A-yozuv**:

```
twin.virtaks.uz.   A   <reserved IP>   TTL 300
```

Tarqalganini tekshiring (davom etishdan oldin **majburiy**, aks holda Caddy
sertifikat ololmaydi):

```bash
dig +short twin.virtaks.uz
```

---

## 3. Dropletni sozlash

```bash
ssh root@<IP>

git clone https://github.com/Sarabek17/virtaks.git /opt/virtaks
cd /opt/virtaks
bash joylash/boshlash.sh
```

Skript: tizimni yangilaydi, Docker o'rnatadi, **4 GB swap** yaratadi, `ufw`
va `fail2ban` ni yoqadi, docker loglariga rotatsiya qo'yadi. Qayta ishga
tushirish xavfsiz.

> Repo yopiq bo'lsa: dropletda `ssh-keygen -t ed25519` bilan kalit yasang va
> ochiq qismini GitHub → repo → **Settings → Deploy keys** ga qo'shing
> (read-only yetarli). Keyin `git clone git@github.com:Sarabek17/virtaks.git`.

---

## 4. Muhitni to'ldirish

```bash
cd /opt/virtaks/joylash
cp env.namuna .env
nano .env
```

Parollarni **generatsiya qiling**, o'ylab topmang:

```bash
openssl rand -base64 30 | tr -d '/+=' | cut -c1-32
```

Majburiy maydonlar: `DOMEN`, `PUBLIC_URL`, `ACME_EMAIL`, `PG_PAROL`,
`S3_MAXFIY`, `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`.

**Uchta bayroq bo'sh qolishi shart** — har biri jonli tizimda teshik:
`DEV_KIRISH` (parolsiz kirish), `ZAXIRA_KIRISH` (login/parol eshigi),
`KENGASH_BOT_OFF` (bot va webhook o'chadi).

`.env` qiymatlarida **bo'shliq, tirnoq va dollar belgisi bo'lmasin** —
docker compose dollarni o'zgaruvchi deb o'qiydi, `bash` esa tirnoqda qoqiladi.

---

## 5. Ishga tushirish

```bash
cd /opt/virtaks/joylash
bash yangilash.sh --toza
```

Skript ketma-ket: muhitni tekshiradi (`PUBLIC_URL` va `DOMEN` mosligi, DNS,
bo'sh maydonlar) → imijlarni yig'adi → `db` va `minio` ni ko'taradi va
sog'lomlashguncha kutadi → web/ishchi ni almashtiradi →
`https://<domen>/salomatlik` ni so'raydi → eski imijlarni tozalaydi.

Birinchi build **10–20 daqiqa** oladi (LibreOffice ~1 GB). Keyingilari
1–2 daqiqa: bog'liqliklar alohida qatlamda, kod o'zgarishi `pip install` ni
qayta ishga tushirmaydi.

Sertifikat 30–60 soniyada olinadi. Kutish:

```bash
docker compose logs -f caddy
```

---

## 5.1. Lokal sinov (ixtiyoriy, lekin tavsiya etiladi)

Butun stekni dropletga tegmasdan o'z kompyuteringizda ko'tarib ko'rish mumkin —
`joylash/sinov.override.yml` portlarni surib qo'yadi va `caddy` ni chetlab
o'tadi (lokalda sertifikat olinmaydi):

```bash
cd joylash
cp env.namuna .env          # PG_PAROL va S3_MAXFIY ga istalgan qiymat yetarli
docker compose -f docker-compose.yml -f sinov.override.yml up -d db minio web ishchi
curl http://127.0.0.1:58900/salomatlik
bash holat.sh
docker compose -f docker-compose.yml -f sinov.override.yml down -v
```

Bu stek **o'z bazasini** ko'taradi va prod bazaga ulanmaydi — shuning bilan
`python -m platforma.web` ni lokal ishga tushirishdan farq qiladi.

---

## 6. Bilim bazasini tiklash (urug'lantirish)

Eski server (169.58.79.192) **butunlay o'chgan**, bazadan zaxira nusxa
qolmagan. Lekin bilim bazasining MANBASI ishchi kompyuterda saqlanib
qolgan, shuning uchun platforma noldan to'ldiriladi.

### 6.1. Nima qaytadi, nima qaytmaydi

| Qaytadi | Qaytmaydi |
|---|---|
| 2 twin («Abdulloh», «Axrolxo'ja») + 7 direktor personasi | Telegram orqali kirgan foydalanuvchilar |
| **2897 bo'lak + 3072-o'lchamli vektorlar** — qayta embedding YO'Q, pul ketmaydi | 2026-07-26 dan keyingi chat tarixi |
| 13 Excel shablon | obunalar va to'lov holati |
| 926 CJM/EJM savoli — `012_savollar.sql` migratsiyasi bilan **o'zi tushadi** | qurilgan kurslar, maqsad sikllari, biznes diagnostikalari |
| eski kengash tarixi (19 suhbat, 20 majlis) | ustoz surati (avatar) — kabinetdan qayta yuklanadi |
| 36 PDF / 3595 sahifa — qayta ingest bilan (~$7) | |

Foydalanuvchilar yo'qolgani halokat emas: kirish Telegram orqali, birinchi
kirishda akkaunt o'zi ochiladi. Lekin **obunalar tiklanmaydi** — to'lagan
mijoz bo'lsa, admin paneldan qo'lda ochib berish kerak.

### 6.2. Bosqichlar

Urug'lantirish **ishchi kompyuterdan** bajariladi (ma'lumot shu yerda),
dropletga SSH tunnel orqali — `db` va `minio` tashqariga chiqmaydi.

```powershell
# loyiha ildizidan, PowerShell
.\joylash\urugla.ps1 -IP <droplet-ip> -Asos -Quruq    # avval ulanishni tekshirish
.\joylash\urugla.ps1 -IP <droplet-ip> -Asos           # 1-bosqich
.\joylash\urugla.ps1 -IP <droplet-ip> -Media          # 2-bosqich (ixtiyoriy)
.\joylash\urugla.ps1 -IP <droplet-ip> -Pdf            # 3-bosqich (~$7)
```

| Bosqich | Nima | Narx | Vaqt |
|---|---|---|---|
| `-Asos` | twin, direktor, 2897 bo'lak + vektor, 13 shablon, eski tarix | **0** | ~1 daqiqa |
| `-Media` | asl audio/PDF fayllar -> MinIO (audio fragment ishlashi uchun) | 0 | uplinkka bog'liq, soatlab |
| `-Pdf` | `E:\Zakazlar\Muslim aka` dagi 43 fayl (36 PDF, 3595 sahifa) -> ingest navbati | ~$7 | worker'da bir necha soat |

Uchalasi **mustaqil** va qayta ishga tushirish xavfsiz: allaqachon
ko'chirilgan yozuv/fayl ikkinchi marta qo'shilmaydi. Hozircha bo'sh
qoldirib, keyinroq bosqichma-bosqich yugurtirish ham mumkin.

Skript dropletning `.env` faylini SSH orqali o'qiydi — sirlar ishchi
kompyuterga nusxalanmaydi, faqat jarayon muhitida turadi.

Faqat PDF ro'yxatini ko'rish (hech narsa yuborilmaydi, pul ketmaydi):

```powershell
.venv\Scripts\python.exe -m platforma.manba_yukla --twin 2 `
  --papka "E:\Zakazlar\Muslim aka" --quruq
```

### 6.3. Tekshirish

`-Asos` oxirida raqamlar o'zi chiqadi (`migratsiya_eski.hisob`). Lokal
sinovda o'lchangan kutilgan natija:

```
  twinlar     : 2
  direktorlar : 7
  manbalar    : 56
  bolaklar    : 2897
    vektorli  : 2897        <- qayta embedding qilinmagan
  shablonlar  : 13
  diag_savollar: 926
  userlar     : 7
  suhbatlar   : 19
  majlislar   : 20
```

Keyin to'liq ko'rik:

```bash
ssh root@<IP> "cd /opt/virtaks/joylash && docker compose exec -T web python -m platforma.tayyorlik"
```

B2B yo'li ham sinaladi (`B2B_API_REJA.md`):

```bash
docker compose exec -T web python -m platforma.sinov_b2b     # 72 tekshiruv, MODELSIZ
docker compose exec -T web python -m platforma.sinov_jonli   # jonli, bir necha sent
```

---

## 7. Jonli holatga o'tish

Eski server yo'q, shuning uchun cutover oddiy — muvofiqlashtiradigan
ikkinchi tomon qolmagan.

1. **DNS**: `twin.virtaks.uz` (va `twin.bmslab.uz`) A-yozuvini yangi
   dropletning IP siga o'tkazing. Hozir ikkalasi ham o'lik `169.58.79.192`
   ga qarab turibdi.
2. Caddy sertifikatni 30–60 soniyada oladi: `docker compose logs -f caddy`.
3. **Telegram webhook o'zi o'rnatiladi** (`tg.webhook_ornat()` har ishga
   tushishda ishlaydi). Tekshirish:
   ```bash
   docker compose logs web | grep -i webhook
   ```
   Eski webhook o'lik serverga qarab turgan bo'lsa ham muammo yo'q —
   `setWebhook` uni almashtiradi.
4. BotFather -> `/setdomain` -> yangi domen (Telegram Login Widget uchun).
5. **Birinchi admin**: botdan bir marta kiring, keyin:
   ```bash
   docker compose exec db psql -U virtaks -d virtaks \
     -c "UPDATE userlar SET rol='admin' WHERE tg_id=<sizning telegram id>;"
   ```
   Busiz admin panel ham, kabinet ham ochilmaydi.
6. **Ustoz suratini** kabinetdan qayta yuklang — avatar S3 da edi, u yo'qoldi.
7. Paylov kabinetida callback URL: `https://<domen>/tolov/paylov`
   (login/parol `.env` dagi bilan **aynan bir xil**), keyin 1000 so'mlik
   jonli to'lov bilan tekshiring.
8. Kvota holatini tekshiring: `sozlamalar.kvota_faol` yangi bazada `0` —
   mijozlar to'siqqa uchramaydi. Narx tasdiqlangach admin paneldan yoqiladi.

---

## 8. Kundalik ish

```bash
cd /opt/virtaks/joylash

bash holat.sh                       # umumiy ko'rik
docker compose logs -f web          # jonli loglar
docker compose logs -f ishchi
docker compose restart web          # faqat web'ni qayta ko'tarish
bash yangilash.sh --tort            # git pull + deploy
docker compose exec web python -m platforma.tayyorlik    # to'liq ko'rik
```

Bazaga kirish:

```bash
docker compose exec db psql -U virtaks -d virtaks
```

Birinchi adminni tayinlash (Telegram orqali bir marta kirgandan keyin):

```bash
docker compose exec db psql -U virtaks -d virtaks \
  -c "UPDATE userlar SET rol='admin' WHERE tg_id=<sizning telegram id>;"
```

MinIO konsoli (SSH tunnel orqali, o'z kompyuteringizdan):

```bash
ssh -L 9001:127.0.0.1:9001 root@<IP>
# keyin brauzerda http://localhost:9001
```

---

## 9. Zaxira nusxa

Uch qatlam:

1. **Haftalik `pg_dump` → MinIO** — worker o'zi qiladi (`zaxira` job,
   oxirgi 8 nusxa saqlanadi). Ro'yxat: `bash holat.sh`.
2. **DO snapshot** — droplet yaratishda yoqilgan haftalik zaxira.
3. **Droplet tashqarisiga** — MinIO bilan bir dropletda turgan zaxira
   droplet yo'qolsa birga yo'qoladi. Oyiga bir marta o'z kompyuteringizga
   tushiring:

```bash
ssh root@<IP> "cd /opt/virtaks/joylash && docker compose exec -T db \
  pg_dump -U virtaks -d virtaks -Fc --no-owner" > virtaks_$(date +%F).dump
```

Tiklash: `bash tikla.sh --dump <fayl>`.

---

## 10. Orqaga qaytish (rollback)

Deploydan keyin muammo chiqsa — kodni orqaga qaytarish yetarli, ma'lumotga
tegilmaydi:

```bash
cd /opt/virtaks/joylash
cat .oldingi_commit                 # yangilash.sh oldingi commitni shu yerga yozadi
git -C .. checkout <commit>
bash yangilash.sh
```

Migratsiyalar **additiv** (faqat yangi jadval/ustun), shuning uchun eski kod
yangi sxema ustida ishlayveradi — baza qaytarilmaydi.

Baza haqiqatan buzilgan bo'lsagina zaxiradan tiklanadi:

```bash
bash tikla.sh --dump /root/zaxira/<sana>.dump
```

---

## 11. Nosozliklar

| Belgi | Sabab va yechim |
|---|---|
| Sayt ochilmaydi, `caddy` logida `could not get certificate` | DNS hali yangi IP ga qaramagan yoki 80-port yopiq. `dig +short <domen>` va DO Firewall'ni tekshiring |
| `web` `unhealthy` | `docker compose logs web`. Odatda `PG_URL` yoki `GEMINI_API_KEY` xato |
| Chat javobi bo'lak-bo'lak, kechikib keladi | Caddy oldida yana bir proksi bor va SSE ni buferlayapti. `Caddyfile` dagi `flush_interval -1` faqat bizning qatlamga tegishli |
| Bot javob bermaydi | `PUBLIC_URL` noto'g'ri yoki `KENGASH_BOT_OFF` qo'yilgan. `docker compose logs web` da `webhook` qatorini qidiring |
| PPTX manba "PPTX->PDF bo'lmadi" beradi | LibreOffice `$HOME` ga yozolmagan. `ishchi` imijini qayta yig'ing (`--toza`) |
| `pg_dump: server version mismatch` | `ishchi` imijida PGDG mijozi o'rnatilmagan — `bash yangilash.sh --toza` |
| `db` cheksiz qayta ko'tariladi, logda `unused mount/volume` | PG 18 imiji volumeni `/var/lib/postgresql` da kutadi, `/var/lib/postgresql/data` da EMAS. `docker-compose.yml` dagi yo'lni o'zgartirmang |
| Disk to'ldi | `docker system prune -af --volumes` **QILMANG** (volumelarda ma'lumot!). To'g'risi: `docker image prune -af` |
| OOM, konteyner o'ladi | swap bormi: `swapon --show`. Yo'q bo'lsa `boshlash.sh` ni qayta ishga tushiring |

---

## 12. Xavfsizlik — o'zgartirilmaydigan qoidalar

- `PROD: "1"` — `docker-compose.yml` da qotirilgan. Buni olib tashlash
  `auth.dev_rejim()` ni ochib yuborishi mumkin (2026-07-31 xatosi).
- **`Caddyfile` ga `servers { trusted_proxies ... }` QO'SHILMAYDI.**
  Caddy standart holatda `X-Forwarded-For` ni mijoz nima yuborganidan qat'iy
  nazar o'zi ko'rgan IP ga qayta yozadi — soxtalashtirib bo'lmaydi (sinovda
  tekshirilgan). `trusted_proxies` esa aksincha: Caddy mijoz sarlavhasiga
  ishonadi va o'zinikini **qo'shib** qo'yadi (`1.2.3.4, <haqiqiy>`), ilova esa
  birinchi qadamni oladi (`cheklov.py`, `tolov.py`) — ya'ni istalgan odam
  soxta IP yozib Paylov IP oq ro'yxatini va tezlik chegarasini aylanib o'tardi.
  Oldga CDN yoki yana bir proksi qo'yilsa — avval shu joyni qayta o'ylang.
- `db` va `minio` host portlari faqat `127.0.0.1` da.
- `.env` gitga tushmaydi; imij ichiga ham tushmaydi (`.dockerignore`).
- Konteynerlar `root` bo'lib ishlamaydi (`USER virtaks`, uid 10001).

---

## 13. Eski yo'l bilan farqi

Avval deploy `deploy_platforma/` papkasiga `robocopy` qilish, `tar.gz`
yasash va serverga qo'lda ko'chirish orqali bo'lardi; `docker-compose.yml`
esa faqat serverda, repodan tashqarida turardi. Aynan shuning uchun server
yo'qolganda konfiguratsiya ham u bilan birga ketdi.

Endi: **repo — yagona manba**. Build konteksti repo ildizi, imij
`platforma/` ni to'g'ridan-to'g'ri oladi, compose/Caddy/skriptlarning
hammasi `joylash/` da va gitda.

`deploy_platforma/` endi ishlatilmaydi (gitga ham tushmaydi) — o'chirib
yuborish mumkin.

Ikkinchi saboq: **zaxira faqat MinIO da turgan edi, MinIO esa o'sha
serverda**. Haftalik `zaxira` job'i ishlab turardi, lekin nusxalar
dropletdan tashqariga chiqmagan. Shuning uchun §9 da uchinchi qatlam bor:
oyiga bir marta dump ni o'z kompyuteringizga tushiring.
