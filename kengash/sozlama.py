# -*- coding: utf-8 -*-
"""Kengash tizimi umumiy sozlamalari: yo'llar, modellar, klient, retry."""
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ILDIZ = Path(__file__).resolve().parent          # kengash/
LOYIHA = ILDIZ.parent                             # VoIpTelefoniya/
KANONIK = ILDIZ / "kanonik"                       # o'qilgan manbalar (md + jsonl)
PERSONAS = ILDIZ / "personas"

# Bulutda (Railway) doimiy disk: KENGASH_DATA=/data bo'lsa o'zgaruvchan
# ma'lumotlar (indeks, hisobotlar, userlar DB) volume'da yashaydi —
# redeploy'da yo'qolmaydi. Birinchi ishga tushishda tayyor nusxa ko'chiriladi.
_DATA = os.environ.get("KENGASH_DATA", "").strip()
if _DATA:
    _d = Path(_DATA)
    BAZA = _d / "baza"                            # qdrant + bm25 + kengash.db
    CHIQISH = _d / "chiqish"                      # majlis natijalari
    import shutil

    def _indeks_seed():
        """Image'dagi tayyor indeksni volume'ga ko'chiradi.

        Yangi deploy'da indeks o'zgargan bo'lsa (bm25.pkl hajmi farq qiladi)
        volume'dagi indeks almashtiriladi; kengash.db (userlar!) HECH QACHON
        ustidan yozilmaydi."""
        manba = ILDIZ / "baza"
        if not (manba / "bm25.pkl").exists():
            return
        hozirgi = BAZA / "bm25.pkl"
        if hozirgi.exists() and hozirgi.stat().st_size == (manba / "bm25.pkl").stat().st_size:
            return
        BAZA.mkdir(parents=True, exist_ok=True)
        if (BAZA / "qdrant").exists():
            shutil.rmtree(BAZA / "qdrant")        # eski segmentlar qolmasin
        shutil.copytree(manba, BAZA, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("kengash.db"))

    _indeks_seed()
    if not (CHIQISH / "tarix.jsonl").exists() and (ILDIZ / "chiqish").exists():
        shutil.copytree(ILDIZ / "chiqish", CHIQISH, dirs_exist_ok=True)
else:
    BAZA = ILDIZ / "baza"
    CHIQISH = ILDIZ / "chiqish"

# Model zanjirlari: birinchisi ishlamasa keyingisi
STT_MODELLAR = ["gemini-3.5-flash", "gemini-2.5-pro", "gemini-2.5-flash"]
# OCR: 2.5-flash birinchi — slayd OCR uchun sifati yetarli, kvotasi keng
# (3.5-flash kvotasi tor — 429 bo'roni ingestni sekinlashtiradi)
OCR_MODELLAR = ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-2.5-pro"]
AGENT_MODELLAR = ["gemini-3.5-flash", "gemini-2.5-flash"]
RAIS_MODELLAR = ["gemini-3.5-flash", "gemini-2.5-pro", "gemini-2.5-flash"]
EMBED_MODEL = "gemini-embedding-001"
EMBED_OLCHAM = 3072

# RAG teglari — har bo'lak shu teglardan bir nechtasini oladi
TEGLAR = ["strategiya", "moliya", "sotuv", "marketing", "operatsiya",
          "huquq", "texnologiya", "hr", "umumiy"]

# Agent -> qaysi teglardagi bilimlarni o'qiydi
AGENT_TEGLARI = {
    "CEO": ["strategiya", "umumiy"],
    "CTO": ["texnologiya", "umumiy"],
    "CFO": ["moliya", "umumiy"],
    "COO": ["operatsiya", "hr", "umumiy"],
    "CLO": ["huquq", "umumiy"],
    "CMO": ["marketing", "sotuv", "umumiy"],
}

# Ustozlar — har bilim bo'lagi qaysi ustozning darslaridan ekanini bildiradi.
# Yangi ustoz paydo bo'lsa shu ro'yxatga qo'shiladi (ingest --ustoz shu ro'yxatdan
# tekshiradi, UI sozlamasi ham shundan quriladi). User tanlovida "" = barchasi.
USTOZLAR = ["Abdulloh", "Axrolxo'ja"]
USTOZ_STANDART = "Abdulloh"   # ustoz belgisi bo'lmagan eski bo'laklar kimniki
USTOZ_YANGI = "Axrolxo'ja"    # yangi ro'yxatdan o'tgan user uchun standart tanlov

PARALLEL = 4      # bir vaqtda nechta so'rov
URINISH = 3       # xato bo'lsa necha marta qayta urinish
LLM_MUHLAT_MS = 180_000   # har LLM chaqiruvi uchun chegara (3 daqiqa, millisekund)


def klient():
    """Gemini klientini .env dan kalit bilan yaratadi."""
    from dotenv import load_dotenv
    from google import genai
    from google.genai import types
    load_dotenv(LOYIHA / ".env")
    kalit = os.environ.get("GEMINI_API_KEY")
    if not kalit:
        raise SystemExit("XATO: GEMINI_API_KEY topilmadi (.env faylini tekshiring)")
    # timeout SHART: usiz "yarim o'lik" TCP ulanishda generate_content abadiy
    # kutadi — majlis tugamaydi va bitta ishchi oqimli navbat butunlay qotadi
    return genai.Client(api_key=kalit,
                        http_options=types.HttpOptions(timeout=LLM_MUHLAT_MS))


LOG_TINGLOVCHILAR = []   # web-server kabi tashqi kuzatuvchilar log oqimiga ulanadi


def log(xabar: str):
    qator = f"[{time.strftime('%H:%M:%S')}] {xabar}"
    print(qator, flush=True)
    for t in list(LOG_TINGLOVCHILAR):
        try:
            t(qator)
        except Exception:
            pass


def qayta_urinib(fn, izoh="", tez=False):
    """fn() ni qayta urinish bilan bajaradi (429 uchun uzunroq kutish).

    tez=True — interaktiv yo'l (HTTP so'rov ichida ishlaydigan chaqiruvlar):
    bitta urinish, qisqa kutish. Aks holda 429 bo'ronida bitta so'rov FastAPI
    threadpool oqimini daqiqalab band qilib, server javob bermay qoladi.
    """
    marta = 1 if tez else URINISH
    oxirgi = None
    for n in range(1, marta + 1):
        try:
            return fn()
        except Exception as e:
            oxirgi = e
            if n == marta:
                break     # oxirgi urinishdan keyin kutish behuda
            matn = str(e)
            if tez:
                kutish = 2
            else:
                kutish = 20 * n if ("429" in matn or "RESOURCE_EXHAUSTED" in matn) else 5 * n
            log(f"  xato ({izoh}, {n}/{marta}): {matn[:140]} — {kutish}s kutamiz")
            time.sleep(kutish)
    raise oxirgi


def slug(nom: str) -> str:
    """Fayl nomidan xavfsiz identifikator yasaydi (kirill harflar ham saqlanadi)."""
    import re
    s = re.sub(r"[^\w]+", "_", nom).strip("_")
    return re.sub(r"_+", "_", s)
