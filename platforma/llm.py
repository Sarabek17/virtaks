# -*- coding: utf-8 -*-
"""Gemini bilan ishlash: model zanjiri, qayta urinish, token/xarajat hisobi.

Har chaqiruv `pul.xarajat_yoz` orqali `xarajatlar` jadvaliga yoziladi.
Token soni FAQAT provayderning `usage_metadata` sidan olinadi — model matnidan emas
(pul qarori LLM chiqishiga bog'liq bo'lmasligi kerak, qarang: pul.py).
"""
import os
import threading
import time

from google import genai
from google.genai import types

from . import pul
from .sozlama import LOYIHA, log

MUHLAT_MS = 180_000        # bitta LLM chaqiruvi chegarasi (yarim o'lik ulanish qotirmasin)
URINISH = 3

# Model zanjirlari: birinchi ishlagan javob olinadi, xatoda keyingisiga o'tiladi.
#
# DIQQAT (2026-08-05): zanjirda FAQAT joriy kalit chaqira oladigan modellar
# turishi kerak. Google 2.5 oilasini yangi hisoblarga yopdi ("no longer
# available to new users", 404) — o'lik model zanjirda qolsa, har chaqiruv
# `qayta_urinib` ichida 3 marta urinib, 5 va 10 soniya kutib, keyin
# keyingisiga o'tadi: bitta OCR sahifasi uchun ~15 soniya behuda ketadi.
# Kalit almashtirilganda `scratchpad/modellar.py` bilan zanjirni qayta
# tekshiring.
_ASOSIY = "gemini-3.5-flash"          # barcha zanjirlarning birinchisi
_ZAXIRA = "gemini-3-flash-preview"    # 3.5 tushib qolsa
_YENGIL = "gemini-3.1-flash-lite-preview"   # arzon/tez ishlar uchun zaxira

AGENT_MODELLAR = [_ASOSIY, _ZAXIRA]
RAIS_MODELLAR = [_ASOSIY, _ZAXIRA]
# Chat (yordamchi) — birinchi so'z tez chiqishi eng muhim mezon.
CHAT_MODELLAR = [_ASOSIY, _ZAXIRA]
TEZ_MODELLAR = [_ASOSIY, _YENGIL]
STT_MODELLAR = [_ASOSIY, _ZAXIRA]
OCR_MODELLAR = [_ASOSIY, _ZAXIRA]
EMBED_MODEL = "gemini-embedding-001"
EMBED_OLCHAM = 3072

_kesh = {}
_qulf = threading.Lock()


def klient():
    with _qulf:
        if "cl" not in _kesh:
            kalit = os.environ.get("GEMINI_API_KEY", "")
            if not kalit:
                # eski .env dan ham qaraymiz (lokal ish uchun)
                from dotenv import load_dotenv
                load_dotenv(LOYIHA / ".env")
                kalit = os.environ.get("GEMINI_API_KEY", "")
            if not kalit:
                raise SystemExit("GEMINI_API_KEY topilmadi")
            _kesh["cl"] = genai.Client(
                api_key=kalit, http_options=types.HttpOptions(timeout=MUHLAT_MS))
    return _kesh["cl"]


# ---------------------------------------------------------------- xarajat
# Daftar va kontekst pul.py da (ContextVar) — ThreadPoolExecutor ichidagi
# direktorlar ham shu daftarga yozadi. Quyidagilar — eski nomlarning ko'prigi.

def yigich_boshla(user_id: int | None = None, twin_id: int | None = None,
                  job_id: int | None = None):
    return pul.kontekst_boshla(user_id=user_id, twin_id=twin_id, job_id=job_id)


def yigich_ol() -> list[dict]:
    return pul.royxat()


def yigich_narx() -> float:
    return pul.joriy_narx()


def xarajat_qayd(model: str, kirish_tok: int, chiqish_tok: int, bosqich: str):
    """Tashqi modul (ingest) o'z chaqiruvini daftarga qo'shishi uchun."""
    return pul.xarajat_yoz(model, kirish_tok, chiqish_tok, bosqich)


def _javob_qayd(javob, model: str, bosqich: str):
    """Token soni faqat provayder metadatasidan olinadi."""
    um = getattr(javob, "usage_metadata", None)
    if um:
        pul.xarajat_yoz(model, um.prompt_token_count or 0,
                        (um.candidates_token_count or 0) +
                        (getattr(um, "thoughts_token_count", 0) or 0), bosqich)


# ---------------------------------------------------------------- generatsiya

def qayta_urinib(fn, izoh: str = "", tez: bool = False):
    marta = 1 if tez else URINISH
    oxirgi = None
    for n in range(1, marta + 1):
        try:
            return fn()
        except Exception as e:
            oxirgi = e
            if n == marta:
                break
            matn = str(e)
            kutish = 2 if tez else (
                20 * n if ("429" in matn or "RESOURCE_EXHAUSTED" in matn) else 5 * n)
            log(f"  LLM xato ({izoh}, {n}/{marta}): {matn[:120]} — {kutish}s")
            time.sleep(kutish)
    raise oxirgi


def generatsiya(modellar: list[str], prompt: str, json_rejim: bool = False,
                harorat: float = 0.3, tez: bool = False,
                bosqich: str = "generatsiya",
                json_sxema: dict | None = None) -> str:
    """Model zanjiri bo'ylab birinchi ishlagan javob. Tokenlar qayd etiladi.

    `json_sxema` — javob TUZILISHINI provayder darajasida majburlaydi.
    Nima uchun kerak: promptdagi "javob shu ko'rinishda bo'lsin" ko'rsatmasi
    javob uzayganda buziladi — model kalit nomlarini o'zgartirib yuboradi
    (`savollar` -> `test_savollari`, ro'yxat o'rniga obyekt va h.k.). Sxema
    berilganda bunday chetga chiqish imkonsiz bo'ladi.
    """
    cl = klient()
    oxirgi = None
    for model in modellar:
        def sorov():
            cfg = types.GenerateContentConfig(
                temperature=harorat, max_output_tokens=16384,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=256 if "pro" in model else 0))
            if json_rejim or json_sxema:
                cfg.response_mime_type = "application/json"
            if json_sxema:
                cfg.response_schema = json_sxema
            return cl.models.generate_content(model=model, contents=[prompt], config=cfg)
        try:
            javob = qayta_urinib(sorov, f"{bosqich}/{model}", tez=tez)
            _javob_qayd(javob, model, bosqich)
            matn = (javob.text or "").strip()
            # JSON kutilayotganda kesilgan javob YAROQSIZ: uni qaytarish
            # chaqiruvchida tushunarsiz "Expecting ',' delimiter" xatosiga
            # aylanadi. Kesilganini shu yerda aytamiz — zanjir keyingi
            # modelga o'tadi yoki chaqiruvchi qayta uradi.
            tugash = str(javob.candidates[0].finish_reason) if javob.candidates else ""
            if (json_rejim or json_sxema) and tugash.endswith("MAX_TOKENS"):
                raise RuntimeError(
                    f"javob token chegarasida kesildi ({len(matn)} belgi)")
            return matn
        except Exception as e:
            oxirgi = e
            log(f"  {model} ishlamadi ({str(e)[:80]}) — keyingi model...")
    raise oxirgi


def oqim(modellar: list[str], prompt: str, harorat: float = 0.3,
         bosqich: str = "oqim", toxtat=None):
    """Javobni BO'LAK-BO'LAK qaytaradi (generator) — chat oqimi uchun.

    `toxtat` — threading.Event: foydalanuvchi "To'xtat" bosganda o'rnatiladi,
    shundan keyin model javobi tashlanadi (pul baribir sarflangani uchun
    tokenlar daftarga yoziladi).

    Model zanjiri: xato BIRINCHI bo'lakdan OLDIN bo'lsa keyingi modelga o'tamiz;
    matn boshlangandan keyin bo'lsa — bor javob bilan qaytamiz (foydalanuvchi
    yarim javobni ikki marta ko'rmasin).
    """
    cl = klient()
    oxirgi = None
    for model in modellar:
        boshlandi = False
        javob = None
        try:
            cfg = types.GenerateContentConfig(
                temperature=harorat, max_output_tokens=16384,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=256 if "pro" in model else 0))
            for bolak in cl.models.generate_content_stream(
                    model=model, contents=[prompt], config=cfg):
                javob = bolak
                if toxtat is not None and toxtat.is_set():
                    break
                matn = bolak.text or ""
                if matn:
                    boshlandi = True
                    yield matn
            _javob_qayd(javob, model, bosqich)
            return
        except Exception as e:
            oxirgi = e
            _javob_qayd(javob, model, bosqich)     # sarflangani yozilsin
            if boshlandi:
                log(f"  {model} oqimi uzildi ({str(e)[:80]}) — bor javob qoldi")
                return
            log(f"  {model} oqimi ishlamadi ({str(e)[:80]}) — keyingi model...")
    raise oxirgi or RuntimeError("model ro'yxati bo'sh")


def generatsiya_qismlar(modellar: list[str], qismlar: list, harorat: float = 0.2,
                        maks_token: int = 32768, bosqich: str = "multimodal") -> str:
    """Multimodal chaqiruv (audio fayl, rasm + matn) — ingest uchun.

    qismlar: genai Part / yuklangan fayl / matn ro'yxati.
    """
    cl = klient()
    oxirgi = None
    for model in modellar:
        def sorov():
            return cl.models.generate_content(
                model=model, contents=list(qismlar),
                config=types.GenerateContentConfig(
                    temperature=harorat, max_output_tokens=maks_token,
                    thinking_config=types.ThinkingConfig(
                        thinking_budget=128 if "pro" in model else 0)))
        try:
            javob = qayta_urinib(sorov, f"{bosqich}/{model}")
            _javob_qayd(javob, model, bosqich)
            tugash = javob.candidates[0].finish_reason if javob.candidates else None
            matn = (javob.text or "").strip()
            if tugash and str(tugash).endswith("MAX_TOKENS"):
                log(f"  {bosqich}: DIQQAT — matn limitga yetdi, oxiri kesilgan bo'lishi mumkin")
            if not matn:
                raise RuntimeError(f"bo'sh javob ({tugash})")
            return matn
        except Exception as e:
            oxirgi = e
            log(f"  {model} ishlamadi ({str(e)[:80]}) — keyingi model...")
    raise oxirgi


def embed(matnlar: list[str], turi: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    def sorov():
        return klient().models.embed_content(
            model=EMBED_MODEL, contents=matnlar,
            config=types.EmbedContentConfig(task_type=turi,
                                            output_dimensionality=EMBED_OLCHAM))
    r = qayta_urinib(sorov, f"embedding x{len(matnlar)}")
    # Embedding javobida `usage_metadata` yo'q — SDK `metadata.billable_character_count`
    # beradi. U ham bo'lmasa matn uzunligidan taxmin qilamiz (~4 belgi = 1 token).
    # Embedding arzon ($0.15/1M), shuning uchun taxmin xatosi $ da sezilmaydi.
    um = getattr(r, "usage_metadata", None)
    tok = (getattr(um, "prompt_token_count", 0) or 0) if um else 0
    if not tok:
        meta = getattr(r, "metadata", None)
        belgi = (getattr(meta, "billable_character_count", 0) or 0) if meta else 0
        tok = max(1, round((belgi or sum(len(m) for m in matnlar)) / 4))
    pul.xarajat_yoz(EMBED_MODEL, tok, 0, "embedding")
    return [e.values for e in r.embeddings]
