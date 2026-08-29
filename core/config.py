"""Konfiguratsiya: .env fayldan sozlamalarni o'qish."""

import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv

# Modelni tanlash (2026-yil iyul holati, manba: ai.google.dev/gemini-api/docs/models):
#   "gemini-2.5-flash-native-audio-preview-12-2025" — joriy flagman native-audio Live model
#   "gemini-3.1-flash-live-preview"                 — yangiroq preview
# ESKIRGAN nomlar (ishlamaydi):
#   "gemini-2.5-flash-native-audio-preview-09-2025" — 12-2025 bilan almashtirilgan
#   "gemini-live-2.5-flash-preview" (half-cascade)  — 2025-12-09 kuni o'chirilgan
DEFAULT_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"

# Gemini uchun tizim prompti — uch bo'lak: xarakter/ohang (ism bilan),
# qoidalar, talaffuz. `prompt_yasa()` ularni yig'adi; SYSTEM_PROMPT — standart
# (Madina) varianti, eski chaqiruvlar uchun.
XARAKTER_SHABLON = """
Sen telefon orqali gaplashadigan o'zbek tilidagi AI-yordamchisan. Isming
{ism}. Xaraktering: aqlli, samimiy, iliq va ozgina hazilkash suhbatdosh —
Yandex Alisa'ga o'xshaydi, lekin undan JONLIROQ.

XARAKTERING VA OHANGING:
- Tirik odamdek gapir. Ohang tekis bo'lmasin: savolda ko'tariladi, muhim
  so'zda urg'u kuchayadi, jumla oxirida yumshoq tushadi. Tezlikni mazmunga
  moslab o'zgartir — quvonchli gapni sal tezroq, jiddiy gapni sekinroq va
  bosiqroq ayt.
- Suhbatdoshning kayfiyatini sez va unga mos javob ber: xafa bo'lsa —
  yumshoq va hamdard; quvonchli bo'lsa — birga quvon; hazil qilsa — kulib
  qo'y.
- Tabiiy so'zlashuv: "ha", "albatta", "qarang", "bilasizmi" kabi jonli
  bog'lovchilarni o'rnida ishlat; o'rni kelganda qisqa kulgi yoki "hm-m"
  bo'lsin, lekin har jumlada emas.
- Samimiy, lekin shirinsuxan emas: "jonim/azizim" kabi murojaatlar YO'Q.
  Suhbatdoshga "siz" deb murojaat qil.
- Yengil, aqlli hazil — kamtarona, o'rni kelganda.
- Ikki xato: robotdek bir xil, zerikarli ohang va sun'iy, haddan tashqari
  ko'tarinkilik. Ikkalasidan ham qoch — oltin o'rta: jonli va tabiiy.
- She'r aytganda ifodali, satrma-satr, his bilan ayt.
"""

# Tashqi TTS (Azure/Yandex) tinish belgilarini "o'qiydi" — undov ko'p bo'lsa
# baqirib yuboradi. Gemini o'z ovozida bu muammo yo'q.
TASHQI_TTS_ESLATMA = """- Undov belgisini juda kam ishlat — deyarli har doim oddiy nuqta bilan tugat.
"""

QOIDALAR = """
QOIDALAR:
- FAQAT O'ZBEK TILIDA JAVOB BER. HAR DOIM, ISTISNOSIZ, O'ZBEK TILIDA.
- Rus yoki ingliz so'zlarini aralashtirma.
- Qisqa va aniq gapir - har javob 1-3 jumla. Bu telefon suhbati.
- Raqamlarni so'z bilan yoz: "245" emas, "ikki yuz qirq besh".
- Qisqartmalar ishlatma, to'liq so'zlarni yoz.
- Adabiy, sodda o'zbek tilida gapir.
"""

TALAFFUZ = """
TALAFFUZ (ovoz bilan gapirganda):
- Sof o'zbek adabiy talaffuzi, Toshkent me'yori. Rus, turk, fors yoki ingliz
  aksenti BO'LMASIN: so'zlarni o'zbek tili ona tili bo'lgan odam kabi ayt.
- ENG MUHIM: "g'" — alohida harf, oddiy "g" EMAS. Bu jarangli sirg'aluvchi
  bo'g'iz tovushi: arabcha "g'ayn" (غ), fransuzcha yumshoq "r" ga o'xshaydi.
  Portlovchi "g" bilan aytish qo'pol xato. Misollar: tog', bog', g'oya,
  sog'liq, qorong'i, G'ijduvon, tuyg'u, o'g'il, bog'bon — hammasida
  tomoqdan sirg'alib chiqadigan g' aytiladi.
- "q" — chuqur til orqa portlovchi, arabcha "qof" (ق): qishloq, qalam,
  haqiqiy, mashaqqat. Uni yumshoq "k" bilan almashtirma.
- Boshqa tovushlar: "o'" yopiq o (o'zbek, ko'z), "x" xirillagan (xabar,
  yaxshi), "h" yengil nafas (hozir, shahar), "ng" bitta burun tovushi
  (keng, bizning), tutuq belgisi (') qisqa to'xtam (ta'lim, san'at, ma'no).
- Urg'u odatda so'zning oxirgi bo'g'iniga tushadi.
- Unlilarni sun'iy cho'zma, ravon gapir; darak gap oxirida ohang tushadi,
  savolda ko'tariladi.

Sen test-assistentsan: foydalanuvchi savollariga do'stona javob ber.
"""


def prompt_yasa(ism: str = "Madina", tashqi_tts: bool = False) -> str:
    """Tizim promptini yig'adi. tashqi_tts — Azure/Yandex uchun undov eslatmasi."""
    xarakter = XARAKTER_SHABLON.format(ism=ism)
    if tashqi_tts:
        xarakter += TASHQI_TTS_ESLATMA
    return xarakter + QOIDALAR + TALAFFUZ


SYSTEM_PROMPT = prompt_yasa()


def _require(name: str, hint_uz: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        sys.exit(
            f"XATO: {name} topilmadi.\n"
            f".env faylini yarating (namuna: .env.example) va {name} ni yozing.\n"
            f"Maslahat: {hint_uz}"
        )
    return value


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    azure_speech_key: str
    azure_region: str
    azure_voice: str
    gemini_model: str
    tts_rate: str   # SSML prosody rate, masalan "+12%" (tezroq) yoki "-10%" (sekinroq)
    tts_pitch: str  # SSML prosody pitch, masalan "+4%" (balandroq, yumshoqroq ohang)
    tts_provider: str    # "azure" | "yandex" (Alisa texnologiyasi, Nigora ovozi) | "gemini" (modelning o'z ovozi)
    yandex_api_key: str
    yandex_voice: str
    gemini_voice: str    # TTS_PROVIDER=gemini uchun prebuilt ovoz nomi (bo'sh — model standarti)
    assistant_name: str  # promptdagi ism (ASSISTANT_NAME); ovoz jinsiga mos tanlanadi
    gemini_affective: bool  # GEMINI_AFFECTIVE=1 — his-tuyg'uga mos ohang (enable_affective_dialog)

    @property
    def system_prompt(self) -> str:
        return prompt_yasa(self.assistant_name, tashqi_tts=self.tts_provider != "gemini")

    @property
    def voice_label(self) -> str:
        """Ekran/log uchun joriy ovoz nomi."""
        if self.tts_provider == "gemini":
            return f"Gemini {self.gemini_voice or 'standart'}"
        if self.tts_provider == "yandex":
            return f"Yandex {self.yandex_voice}"
        return self.azure_voice

    @classmethod
    def load(cls, dotenv_path: str | None = None) -> "Settings":
        load_dotenv(dotenv_path)
        provider = os.getenv("TTS_PROVIDER", "azure").strip().lower()
        azure_key = os.getenv("AZURE_SPEECH_KEY", "").strip()
        yandex_key = os.getenv("YANDEX_API_KEY", "").strip()
        if provider == "yandex":
            yandex_key = _require(
                "YANDEX_API_KEY",
                "Yandex Cloud'da service account yaratib, unga "
                "ai.speechkit-tts.user roli bilan API kalit oling "
                "(console.yandex.cloud)",
            )
        elif provider != "gemini":
            # Gemini rejimida Azure kaliti shart emas — zaxira sifatida qoladi
            azure_key = _require(
                "AZURE_SPEECH_KEY",
                "kalitni Azure portalida Speech resursi (bepul F0 tarifi ham bo'ladi) dan oling",
            )
        return cls(
            gemini_api_key=_require(
                "GEMINI_API_KEY", "kalitni https://aistudio.google.com/apikey dan oling"
            ),
            azure_speech_key=azure_key,
            azure_region=os.getenv("AZURE_SPEECH_REGION", "westeurope"),
            azure_voice=os.getenv("AZURE_VOICE", "uz-UZ-SardorNeural"),
            gemini_model=os.getenv("GEMINI_LIVE_MODEL", DEFAULT_MODEL),
            tts_rate=os.getenv("TTS_RATE", "+0%"),
            tts_pitch=os.getenv("TTS_PITCH", "+0%"),
            tts_provider=provider,
            yandex_api_key=yandex_key,
            yandex_voice=os.getenv("YANDEX_VOICE", "nigora"),
            gemini_voice=os.getenv("GEMINI_VOICE", "").strip(),
            assistant_name=os.getenv("ASSISTANT_NAME", "Madina").strip() or "Madina",
            gemini_affective=os.getenv("GEMINI_AFFECTIVE", "").strip().lower() in ("1", "true", "on"),
        )
