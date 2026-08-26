# O'zbek ovozli AI-assistent — test stendi

**Gemini Live API + Azure TTS** juftligi o'zbek tilidagi telefon suhbatlarini
qay darajada uddalashini tekshirish uchun stend. Ikki rejimda ishlaydi:

- **Konsol** (`main.py`) — kompyuter mikrofoni bilan lokal test
- **Web** (`server.py`) — brauzer orqali, chiroyli interfeys va jonli statistika

Arxitektura kelajakdagi telefoniya (SIP/Asterisk) versiyasi bilan **bir xil**:
audio manba almashtiriladigan yagona nuqta qilib ajratilgan.

## Arxitektura

```
Audio manba (16 kHz PCM mono)          <- mikrofon / brauzer / kelajakda AudioSocket
   │
   ▼
core.AssistantPipeline
   │   Gemini Live API — o'zbek nutqini tushunadi (STT keraksiz),
   │   javob MATN ko'rinishida olinadi
   ▼
core.normalize — "AKSENT" ALGORITMI
   │   raqamlar -> so'z, kirill -> lotin, markdown/emoji tozalash,
   │   qisqartmalar, vaqt/foiz  (TTS toza adabiy lotin-o'zbek oladi)
   ▼
core.tts — Azure TTS (uz-UZ-SardorNeural), SSML, jumlama-jumla striming
   │
   ▼
Chiqish: karnay (konsol) yoki 24 kHz PCM oqimi (web/telefoniya)
```

### Uzilishlarga chidamlilik (production talablari)

- **Session resumption** — Gemini uzilsa (keepalive timeout, GoAway, tarmoq),
  yangi ulanish **suhbat kontekstini saqlagan holda** davom etadi
- **Context window compression** — sessiya muddati cheklovi yo'q (kontekst
  avtomatik siqiladi)
- **Eksponensial backoff** bilan avtomatik qayta ulanish (1s → 15s)
- Mikrofon oqimi o'z-o'zini tiklaydi (Windows audio-reset holatlari)
- Thinking o'chirilgan (`thinking_budget=0`) — latency 2-3 barobar past

> **Texnik eslatma (2026-iyul):** hozirgi native-audio Live modellar sof
> `TEXT` javob modalligini rad etadi (1011 xato). Shuning uchun `AUDIO`
> modallik + `output_audio_transcription` ishlatiladi: Gemini'ning o'z ovozi
> tashlab yuboriladi, faqat matn Azure TTS ga boradi. `--text-mode` flagi
> kelajak uchun qoldirilgan.
>
> **`TTS_PROVIDER=gemini` (2026-08-25):** modelning o'z ovozi tashlanmaydi —
> to'g'ridan-to'g'ri karnay/WebSocket'ga uzatiladi (`core/tts.py`
> `GeminiVoice`). Azure kaliti shart emas, zaxirada qoladi. Bu rejimda
> talaffuz qatlami (orfoepiya, lug'at) ovozga ta'sir qilmaydi — ular faqat
> Azure/Yandex sintezida ishlaydi.

## O'rnatish

Talab: **Python 3.11+**

```bash
python -m venv .venv

# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### PyAudio (faqat konsol rejimi uchun)

| OS | Buyruq |
|---|---|
| **Windows** | `pip install pyaudio` — tayyor wheel bor |
| **macOS** | avval `brew install portaudio`, keyin `pip install pyaudio` |
| **Ubuntu/Debian** | avval `sudo apt install portaudio19-dev python3-dev`, keyin `pip install pyaudio` |

### API kalitlari

1. **Gemini:** [aistudio.google.com/apikey](https://aistudio.google.com/apikey) — bepul kalit
2. **Azure Speech:** [portal.azure.com](https://portal.azure.com) da **Speech
   service** resursi (bepul **F0** tarifi yetarli — oyiga 0,5 mln belgi neyro-TTS)
3. `.env` sozlash: `copy .env.example .env` (Windows) va kalitlarni yozish

## Ishga tushirish

### Web rejimi (tavsiya etiladi)

```bash
python server.py
```

Brauzerda **http://localhost:8000** oching → «Boshlash» → gapiring.
Interfeys: jonli suhbat, latency statistika, telefon-simulyatsiya
tugmasi, barge-in indikatori.

> Mikrofon faqat **localhost** yoki **HTTPS** sahifada ishlaydi. Boshqa
> kompyuterdan foydalanish uchun reverse-proxy (nginx/caddy) + TLS kerak.

### Konsol rejimi

```bash
python main.py            # to'liq sifat (16 kHz)
python main.py --phone    # telefon simulyatsiyasi (8 kHz + G.711)
```

`--phone` / web'dagi «Telefon simulyatsiyasi» — audioni telefon liniyasi
sifatiga tushiradi: telefoniyadagi eng katta xavfni (tor polosali audio) SIP
trunk sotib olishdan OLDIN tekshiradi.

## "Aksent" algoritmi (core/normalize.py)

Azure uz-UZ ovozi **sof adabiy lotin-o'zbek** matnini eng toza talaffuz
qiladi. Har jumla TTS dan oldin shu bosqichlardan o'tadi:

| Muammo | Yechim | Misol |
|---|---|---|
| Raqamlar ruscha o'qiladi | so'zga aylantirish | `245` → `ikki yuz qirq besh` |
| Kirill (rus so'zlari) | lotin transliteratsiya | `заявка` → `zayavka` |
| Markdown/emoji | tozalash | `**Salom!**` → `Salom!` |
| Vaqt | so'zga | `14:30` → `o'n to'rt soat o'ttiz daqiqa` |
| Foiz | so'zga | `50%` → `ellik foiz` |
| Tartib son | so'zga | `5-savol` → `beshinchi savol` |
| Qisqartmalar | to'liq so'z | `kg` → `kilogramm` |
| Yozilishi ≠ aytilishi | orfoepiya qoidalari | `kitob` → `kitop`, `ketdi` → `ketti`, `uchta` → `ushta` |
| Istisno so'zlar | `talaffuz.txt` lug'ati | `mashhur` → `mas-hur` |
| Apostrof | rasmiy imlo belgisi | `o'` → `oʻ`, `ma'no` → `maʼno` |

Qo'shimcha: SSML `<prosody rate>` orqali gapirish tezligi sozlanadi
(`.env` da `TTS_RATE=-10%` — sekinroq, tabiiyroq telefon nutqi uchun).

### Orfoepiya (talaffuz qoidalari)

Adabiy o'zbek talaffuzi asosan **qoidaviy**: 7 ta nomlangan qoida so'z
darajasida, belgilangan tartibda qo'llanadi (`core/normalize.py`,
`ORTHOEPY_RULES`). Har birini eshitish sinovida alohida o'chirib ko'rish
mumkin:

```
UZ_ORTHOEPY=off                 # hammasi o'chadi
UZ_ORTHOEPY_SKIP=shs,d_t        # faqat sanalganlari o'chadi
```

| Nom | Qoida | Misol |
|---|---|---|
| `ch_sh` | ch → sh (t/d oldida) | uchta → ushta, ochdi → oshti |
| `jarangsiz_oldida` | b/d/g/z/v → p/t/k/s/f jarangsiz undosh oldida | avtobus → aftobus, yozsa → yossa |
| `oxiri_jarangsiz` | so'z oxirida b/d/g → p/t/k (keyingi so'z unli bo'lmasa) | kitob → kitop, *kitob oldim* o'zgarmaydi |
| `d_t` | d → t jarangsizdan keyin | ketdi → ketti, ishdan → ishtan |
| `n_m` | n → m b/p oldida | shanba → shamba |
| `shs` | sh + s → shsh | ishsiz → ishshiz |
| `t_tushadi` | s/sh/x/n/k/q dan keyingi t qo'shimcha oldida tushadi | do'stlar → do'slar, to'rtta → to'rta |

**Lug'at** (`talaffuz.txt`) qoidadan ustun: `so'z = talaffuz` (aniq so'z)
yoki `so'z* = talaffuz` (o'zak — qo'shimchali shakllar ham). Fayl har
o'zgarganda qayta o'qiladi, restart shart emas.

**Sinov va korpus:**

```
python sinov_talaffuz.py     # oltin fayl (talaffuz_oltin.txt) + lug'at + tezlik
python talaffuz_korpus.py    # transkriptlardan so'z ro'yxati -> talaffuz_korpus.tsv
```

Qoidalar asosi, eshitish protokoli va bosqichlar: `ORFOEPIYA_REJA.md`.

## Konsol log formati (test ma'lumotlari)

```
------------------------------------------------------------
  [SIZ]  Toshkentda ob-havo qanday?
  [LATENCY] nutq tugashi -> birinchi token: 820 ms (OK)
  [TTS #1] "Kechirasiz, menda ob-havo ma'lumoti yo'q." | birinchi bayt: 160 ms | sintez+ijro: 2100 ms
  [AI]   Kechirasiz, menda ob-havo ma'lumoti yo'q.
  [BARGE-IN] foydalanuvchi gapni bo'ldi — TTS to'xtatildi, bufer tozalandi
  [ULANISH] aloqa uzildi — 1 soniyadan keyin qayta ulanamiz (kontekst saqlanadi)...
```

## Test rejasi (7 band)

Har bandni oddiy va telefon-simulyatsiya rejimida takrorlang.

1. **Oddiy savollar.** "Salom, ishlaring qalay?", "O'zbekiston poytaxti qayer?"
   — javob mantiqli, faqat o'zbekcha, 1-3 jumla.
2. **Raqamlar.** "Ikki yuz qirq beshga o'n uchni qo'shsak nechchi bo'ladi?"
   — javobda raqamlar so'z bilan (normalizator raqam qolsa ham o'zi so'zga aylantiradi).
3. **Atoqli otlar.** "Alisher Navoiy kim bo'lgan?", "Samarqand haqida gapir"
   — `[SIZ]` qatorida ismlar to'g'ri tanilganini tekshiring.
4. **Tez nutq.** Savolni ataylab tez ayting — transkripsiya buziladimi?
5. **Barge-in.** AI uzun javob berayotganda gapini bo'ling — ovoz darhol
   (< 1 soniya) to'xtashi kerak.
6. **Aralash rus-o'zbek.** "Zayavka qoldirmoqchi edim" — tushunishi va sof
   o'zbekchada javob berishi kerak.
7. **Kechikish.** Kamida 10 navbatda `[LATENCY]` yig'ing (web'da avtomatik
   o'rtacha hisoblanadi). Maqsad: **birinchi token < 1500 ms**, TTS birinchi
   bayt < 500 ms.

## Production joylashtirish (websayt) uchun tekshiruv ro'yxati

- [ ] TLS: nginx/caddy reverse-proxy (`wss://` uchun majburiy)
- [ ] `WEB_HOST=0.0.0.0` faqat proxy ortida; autentifikatsiya qo'shing
- [ ] API kalitlarni muhit o'zgaruvchisi/secret-manager orqali bering (.env ni git'ga qo'ymang!)
- [ ] Bir vaqtda ko'p foydalanuvchi = har ulanishga alohida Gemini sessiya —
  kvota va narxni hisoblang (Azure F0: 0,5 mln belgi/oy)
- [ ] Monitoring: `/healthz` endpoint tayyor

## Kelajak: telefoniyaga o'tish

Yagona almashtirish nuqtasi — **audio manba factory** (`main.py` dagi
`mic_source` yoki `server.py` dagi WebSocket navbati o'rniga Asterisk
AudioSocket'dan 16 kHz PCM o'qiydigan generator). TTS chiqishi allaqachon
baytlar oqimi sifatida ishlaydi (`tts_audio_sink`) — SIP kanalga yo'naltirish
kifoya. `core/` ga tegilmaydi.
