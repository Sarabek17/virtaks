# OVOZ_KOCHIRISH.md — «Madina» ovozini boshqa loyihaga ko'chirish

**Kim uchun:** Claude Code (yoki dasturchi) — boshqa loyihada AYNAN shu
loyihadagidek gapiradigan o'zbek ovozli yordamchi kerak bo'lganda.
Manba repo: `git@github.com:Sarabek17/geminaiVoiceChat.git` (`main`).

## 1. Natija qanday bo'lishi kerak

Ovoz **Gemini Live modelining o'z ovozi** (TTS yo'q, Azure yo'q). Egasi
tanlagan retsept (2026-08-29):

| Parametr | Qiymat | Izoh |
|---|---|---|
| Model | `gemini-3.1-flash-live-preview` | `.env: GEMINI_LIVE_MODEL` |
| Ovoz | **`Zephyr`** | `.env: GEMINI_VOICE` — Google tavsifi «bright», ayol |
| Ism | `Madina` | `.env: ASSISTANT_NAME` — promptga kiradi |
| Balandlik / tezlik | `+0%` / `+0%` | DSP o'chiq — ovoz aynan modeldan chiqqanidek |
| Uslub qatori | bo'sh | `OVOZ_USLUBI` ishlatilmaydi |
| Prompt | `core/config.py` → `prompt_yasa("Madina")` | XARAKTER + QOIDALAR + TALAFFUZ bloklari, **o'zgartirilmaydi** |
| Modallik | `AUDIO` + `output_audio_transcription` | TEXT rad etiladi (1011) |
| Fikrlash | `thinking_budget=0` | yoqilsa kechikish 3× va fikr matni oqadi |
| Affektiv dialog | o'chiq | 3.1-flash-live rad etadi (1011) |
| Audio format | 24 kHz, PCM16, mono | to'g'ridan-to'g'ri karnay/WebSocket/telefoniyaga |

Etalon yozuv (shu ovoz, shu model): `aksent_test/gemini_g31_Zephyr.wav`
(gitda yo'q — WAV'lar ignore qilingan; kerak bo'lsa `aksent_test/gemini_kasting.py`
qayta yozdiradi). Ko'chirilgan loyiha shu bilan bir xil eshitilishi kerak.

## 2. Olinadigan fayllar

### Majburiy (ovozning o'zi uchun shu ikkitasi yetadi)

| Fayl | Nima uchun |
|---|---|
| `core/config.py` | Prompt bloklari (`XARAKTER_SHABLON`, `QOIDALAR`, `TALAFFUZ`), `prompt_yasa()`, `Settings` (.env o'qish, `system_prompt`, `voice_label`) |
| `ovoz_namuna.py` | Eng kichik ishlaydigan namuna: ulanadi, savol yuboradi, javobni WAV'ga yozadi. `live_config()` funksiyasi — ovoz retseptining o'zi |

`core/config.py` faqat `python-dotenv` ga bog'liq. Azure/Yandex maydonlari
ichida bor, lekin `TTS_PROVIDER=gemini` bo'lsa ularning kalitlari talab
qilinmaydi — tegmasdan ko'chirish mumkin. Yangi loyihada `core/__init__.py`
bo'sh bo'lsin (bizdagisi `pipeline` ni import qiladi).

### Real vaqt suhbat kerak bo'lsa (mikrofon / telefon / brauzer)

| Fayl | Nima uchun |
|---|---|
| `core/pipeline.py` | `AssistantPipeline`: Live sessiya, audio kirish oqimi, barge-in, `session_resumption`, uzilishda qayta ulanish, **`receive()` per-turn tuzog'i tuzatilgan** (`_receive` dagi `while True`) |
| `core/audio.py` | Audio yordamchilari (8 kHz telefon simulyatsiyasi, VAD) |
| `core/tts.py` → faqat `GeminiVoice` sinfi + `create_tts` | Modeldan kelgan bo'laklarni karnay/sink'ka uzatish, `stop()` (barge-in), `flush_audio()`. Fayl boshida `azure.cognitiveservices.speech` va `core.normalize` import bor — Azure kerak bo'lmasa `GeminiVoice` ni alohida faylga ko'chirib, `AudioSink`/`EventCallback` tiplarini birga oling |
| `server.py` + `static/` | FastAPI + WebSocket web-mijoz (brauzer mikrofoni → 16 kHz PCM → Gemini → 24 kHz PCM → brauzer) |

### Ixtiyoriy

| Fayl | Nima uchun |
|---|---|
| `core/ovoz_sozlash.py` | Pitch/rate (Azure `TTS_PITCH`/`TTS_RATE` analogi, DSP). Hozirgi tanlovda 0/0 — kerak emas, lekin keyin sozlash uchun turadi |
| `aksent_test/gemini_kasting.py`, `sinov_ovoz_sozlash.py` | Ovoz kastingi va pitch/rate tinglash sahifalari |

Olinmaydi: `core/normalize.py`, `talaffuz.txt` (orfoepiya — faqat Azure
rejimi uchun, Gemini ovoziga ta'sir qilmaydi), `platforma/`, `kengash/`.

## 3. `.env`

```
GEMINI_API_KEY=...                         # https://aistudio.google.com/apikey
TTS_PROVIDER=gemini
GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview
GEMINI_VOICE=Zephyr
ASSISTANT_NAME=Madina
GEMINI_PITCH=+0%
GEMINI_RATE=+0%
# OVOZ_USLUBI=            # bo'sh qoladi
# GEMINI_AFFECTIVE=       # yoqilmaydi
```

`requirements`: `google-genai>=2.12.0`, `python-dotenv>=1.0.0`; real vaqt
uchun qo'shimcha `numpy`, `websockets`, `fastapi`, `uvicorn[standard]`,
konsol mikrofoni uchun `pyaudio` (Python 3.11 — 3.13 da `audioop` yo'q).

## 4. Claude uchun qadamlar

1. Manba repodan 2-bo'limdagi fayllarni ko'chir (`core/config.py` va
   `ovoz_namuna.py` — majburiy). Prompt bloklarini **so'zma-so'z** saqla:
   ohang va talaffuz (g', q, o', tutuq) aynan shu matn bilan sozlangan.
2. `.env` ni 3-bo'limdagidek to'ldir.
3. Tekshir: `python ovoz_namuna.py "Salom! O'zingni qisqacha tanishtir."`
   → `namuna.wav` + transkript. Ovoz ayol, yorqin, Madina deb tanishadi,
   o'zbekcha, 1–3 jumla.
4. Loyihaga ulaganda `ovoz_namuna.live_config()` dagi to'rt sozlamani
   (AUDIO + transkript, `thinking_budget=0`, `system_instruction`,
   `speech_config` Zephyr) aynan takrorla. Real vaqt kerak bo'lsa
   `core/pipeline.py` ni ol, o'zing yangidan yozma — undagi tuzoqlar
   (5-bo'lim) allaqachon hal qilingan.
5. Ovozni boshqa loyihaning o'z persona/qoidalari bilan birlashtirish kerak
   bo'lsa: `QOIDALAR` blokini kengaytir, `XARAKTER_SHABLON` va `TALAFFUZ`
   ni o'zgartirma. Modelga «holat o'zgartirish» huquqi berilmaydi —
   qarorlar server tomonida.

## 5. Tuzoqlar (hammasi tekshirilgan, takrorlanmasin)

- `response_modalities=["TEXT"]` → `1011 Internal error`. Faqat AUDIO +
  `output_audio_transcription`; matn kerak bo'lsa transkriptdan olinadi.
- `session.receive()` google-genai'da **bitta navbat** iteratori:
  `turn_complete` da tugaydi. Uzoq sessiyada `while True:` ichida qayta
  ochilmasa, websocket o'qilmay qoladi → ~40–50 s dan keyin keepalive 1011.
- `thinking_budget` 0 dan katta bo'lsa: kechikish ~3×, «fikr» matni
  transkriptga oqadi.
- `enable_affective_dialog=True` → 3.1-flash-live'da 1011. Faqat
  `gemini-2.5-flash-native-audio-preview-12-2025` qabul qiladi.
- Chiqish 24 kHz; kirish 16 kHz PCM16 (`send_realtime_input`). Telefoniya
  (8 kHz, G.711) uchun resample — `core/audio.py`.
- Gemini ovozida `core/normalize.py` (orfoepiya) ishlamaydi — talaffuz
  faqat prompt TALAFFUZ bloki bilan boshqariladi.
- Ovoz nomlari registrga sezgir (`Zephyr`, `Puck`, `Achernar`…). Xato nom —
  ulanish xatosi.
- Bu mashinada 8000 port Docker/WSL'da — web stend `WEB_PORT=8010`.

## 6. Narx (2026-08 rasmiy jadval)

Audio kirish $3/1M token (~$0.005/min), audio chiqish $12/1M (~$0.018/min),
25 token/s. Bitta gaplashish daqiqasi ≈ $0.023. Gemini ovozi Azure
kaskadidan (~$0.037) arzon — Gemini audio-chiqishi baribir hisoblanadi.
