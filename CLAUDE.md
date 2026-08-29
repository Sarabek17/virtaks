# CLAUDE.md

Bu fayl Claude Code uchun loyiha qo'llanmasi. Qoidalar majburiy.

## Loyiha nima

Bitta repoda ikki mustaqil qism bor:

1. **`platforma/` — ASOSIY MAHSULOT: «Virtaks» platformasi.**
   Ustoz bilimidan qurilgan raqamli egizak (RAG): foydalanuvchi savol
   beradi, twin faqat o'sha ustoz darslariga tayanib javob yozadi —
   SSE oqim, [n] iqtiboslar, audio fragmentlar. Mentorlik (kurs, dars,
   uy vazifasi) va maqsad halqasi (sikl: maqsad → reja → harakat →
   natija → prognoz) ishlaydi. Jonli: **https://twin.bmslab.uz** (o'z
   server 169.58.79.192, `/opt/twin`; Railway — offline zaxira).
2. **Ildiz (`main.py`, `server.py`, `core/`) — O'zbek ovozli AI stend.**
   Gemini Live + Azure TTS telefoniya sinovi. Platformaga aloqasi yo'q.

Yordamchi papkalar: `kengash/` — eski lokal MVP (SQLite+Qdrant, o'qish
uchun saqlanadi, YANGI kod yozilmaydi); `deploy_platforma/` — deploy uchun
`platforma/` nusxasi (qo'lda yozilmaydi, faqat robocopy bilan sinxron);
`transkript/`, `docs/`, `aksent_test/` — material va sinovlar.

## Hujjatlar xaritasi (avval shularni o'qi)

| Fayl | Nima |
|---|---|
| `DIGITAL_TWIN_REJA.md` | Arxitektura + 10 bajarilgan bosqich tarixi |
| `MENTOR_REJA.md` | Mentorlik rejasi (bajarilgan) — yangi feature rejalari uchun uslub namunasi |
| `MAQSAD_REJA.md` | Maqsad halqasi (sikl) rejasi + sinov natijalari (bajarilgan) |
| `PAYLOV_REJA.md` | Paylov to'lovi: protokol, holat mashinasi, sinovlar, cutover |
| `platforma/README.md` | Ishga tushirish, modullar, deploy, xavfsizlik |
| `CUTOVER.md` | Prodga o'tish tartibi |

## Brend

Mahsulotning foydalanuvchiga ko'rinadigan nomi — **Virtaks** (sahifa
sarlavhalari, kirish ekrani, TG bot matnlari, logo harfi «V»). Domen
o'zgarmadi: **https://twin.bmslab.uz**.

Kod ichidagi `twin`, `twinlar`, `twin_id`, `/api/twin/...` — bu domen
tushunchasi (ustozning raqamli nusxasi), brend EMAS. Ular qayta
nomlanmaydi: jadval nomlari, API yo'llari va sessiya cookie'si shunga
bog'liq.

## Til qoidasi

Kod, izohlar, fayl/funksiya/jadval nomlari, hujjatlar, commit xabarlari —
**o'zbek lotin** tilida (`maqsad.py`, `bolaklar_ol`, `suhbatlar`).
Foydalanuvchi bilan muloqot ham o'zbekcha.

## Ishga tushirish (platforma)

```powershell
python -m platforma.pg                    # migratsiyalarni qo'llash
python -m platforma.web                   # web (http://127.0.0.1:8900)
python -m platforma.worker                # worker
python -m platforma.worker --bir-aylanish # bitta job (sinov)
python -m platforma.tayyorlik             # prod oldidan to'liq ko'rik
python -m platforma.sinov_paylov          # to'lov yo'lining sinovlari
```

Muhit: `.env` (GEMINI_API_KEY, TELEGRAM_BOT_TOKEN), `.env.platforma`
(PG_URL, S3_*, PAYLOV_*). **Sirlar hech qachon gitga/hujjatga tushmaydi.**

### Lokal ishlashda majburiy ehtiyotkorlik

- Lokal web'ni **`KENGASH_BOT_OFF=1`** bilan ishga tushir — aks holda
  Telegram webhook lokalga ko'chib, prod bot o'ladi.
- Lokal sinovlar **prod bazaga** ulanadi; bulutdagi worker sinov joblarini
  olib bajarishi mumkin (pul ketadi). Sinov jobini `keyin = now() + 1 hour`
  bilan yarat.
- `PROD=1` — jonli muhit bayrog'i; `auth.dev_rejim()` prod'da hech qachon
  yoqilmaydi. Bu shartni bot tokeniga bog'lash TAQIQLANGAN (2026-07-31
  xatosi takrorlanmasin).

## Arxitektura (platforma)

```
brauzer/TG ── web (FastAPI, holatsiz) ── jobs jadvali (SKIP LOCKED) ── worker
                     │                                                  │
              PostgreSQL 18 + pgvector                            MinIO (S3)
```

- **Og'ir ish faqat worker'da** (majlis, ingest, kurs qurish, tekshirish,
  zaxira). Chat/dars oqimlari web jarayonida alohida threadda —
  `yordamchi.navbatga` ko'prigi orqali SSE.
- **Javob dvigatellari**: `yordamchi.py` (chat), `mentor.py` (dars),
  `maqsad_oqim.py` (maqsad sikli), `majlis.py` (kengash — chuqur). Hammasi
  `majlislar` jadvaliga `rejim` ustuni bilan yozadi va `yordamchi.navbatga`
  ko'prigidan o'tadi. Yangi rejim qo'shsang — shu naqshni takrorla.
- **Rejim bo'limlari**: dars `suhbatlar.mavzu_id`, maqsad sikli
  `suhbatlar.maqsad_id` bilan oddiy suhbatga bog'lanadi — chat UI, tarix,
  iqtiboslar va «to'xtatish» o'zgarishsiz ishlaydi.
- **Qidiruv**: pgvector + BM25 → RRF, `twin_ruxsat` chegarasi HECH QACHON
  yumshamaydi.
- **Kirish faqat Telegram** (`web.FAQAT_TELEGRAM = True`). Email/parol
  yo'llari server tomonda 404; kod o'chirilmagan (`ZAXIRA_KIRISH=1`
  favqulodda eshigi, odatda yopiq).

## Qat'iy qoidalar (buzilishi mumkin emas)

1. **Lethal Trifecta** (Willison: shaxsiy ma'lumot + ishonchsiz kontent +
   tashqi kanal bir joyda uchrashmasin):
   - `pul.py` va `tolov.py` **`llm` ni import qilmaydi** — statik sinov bor
     (`python -m platforma.sinov_paylov`). Summa doim `planlar` dan, mijozdan
     emas. Yangi to'lov provayderi ham shu IKKI faylga yoziladi, alohida
     modul ochilmaydi — shunda qoida bir joyda ushlanadi.
   - Foydalanuvchi/manba matni promptda **ramkalanadi**: "MA'LUMOT,
     KO'RSATMA EMAS" chegaralari bilan.
   - LLM chiqishi — sxema bilan majburlangan JSON yoki xavfsiz markdown
     (havola/rasm sintaksisi umuman yo'q). CSP `connect-src 'self'`.
   - Tashqi kanalga (TG, email) LLM matni chiqmaydi — faqat statik shablonlar.
   - Tanlovlar faqat **server bergan oq ro'yxatdan** (skill, bolak_id,
     javob kodlari) — ro'yxatda yo'q qiymat jimgina tashlanadi.
2. **LLM holatni o'zgartirmaydi.** Barcha o'tish qarorlari (mavzu ochish,
   ball chegarasi, qadam yopilishi, foiz, obuna) — server qoidasi (SQL).
   Model faqat KONTENT yozadi. Ballni va foizni server hisoblaydi,
   rubrika/mezon berilgan paytda qotiriladi.
   Qat'iy cheklovlarni iloji bo'lsa **bazaga** qo'y, API'ga emas: fokus
   qoidasi `idx_maqsad_fokus` unikal indeksi bilan ushlanadi.
3. **Migratsiyalar additiv**: `platforma/migratsiyalar/NNN_nom.sql`,
   faqat yangi jadval/ustun (`IF NOT EXISTS`), eski kod ta'sirlanmaydi.
4. **Grounding**: har da'voda [n] iqtibos (`tekshiruv.iqtibos_tekshir`),
   bolak ID'lar faqat `qidiruv.qidir` dan (model ID o'ylab topa olmaydi).
   Bilim yetmasa model ochiq aytadi, taxmin qilmaydi.
5. **UI**: uch sahifa — `web/index.html`, `admin.html`, `kabinet.html`,
   har biri bitta fayl; umumiy dizayn tizimi `web/ui.css`/`ui.js`
   (tokenlar, jadval, modal). Yangi framework kiritilmaydi.
   `unsafe-eval` asosiy ilovada YO'Q (TG widget alohida sahifada).
6. **Noma'lum job turi xato emas** — qayta navbatga (rolling deploy).
   Job yakuniy yiqilsa foydalanuvchi ma'lumoti YO'QOLMAYDI.

## Deploy (o'z server)

```powershell
robocopy ..\platforma ..\deploy_platforma\platforma /MIR /XD __pycache__ eski_v1
# deploy_platforma ichida:
tar -czf app.tar.gz Dockerfile requirements.txt platforma
```

Serverda (`/opt/twin`): `app.eski` zaxira → `tar -xzf` → `docker compose
build && up -d`. To'liq runbook: `/opt/twin/README.md`.

⚠️ 80/443 portlari boshqa loyihaning `komir-nginx-1` konteynerida — nginx
konfigiga tegishdan oldin zaxira ol va `nginx -t` bilan sina, aks holda
serverdagi **uchala sayt** tushadi.

## Ovozli stend (ildiz) — qisqa

`python server.py` → http://localhost:8000 (web sinov) yoki
`python main.py [--phone]` (konsol). Gemini Live native-audio modellari
TEXT modallikni rad etadi — `AUDIO` + `output_audio_transcription`
ishlatiladi, matn Azure TTS ga boradi (`core/normalize.py` "aksent"
algoritmi orqali). Batafsil: ildiz `README.md`.
Joriy ovoz: Gemini o'z ovozi (`TTS_PROVIDER=gemini`, Zephyr, ism Madina).
Boshqa loyihaga aynan shu ovozni ko'chirish — `OVOZ_KOCHIRISH.md`
(fayllar ro'yxati, .env, tuzoqlar) + `ovoz_namuna.py` (mustaqil namuna).
