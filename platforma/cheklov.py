# -*- coding: utf-8 -*-
"""Tezlik chegarasi (rate limit) — sirg'aluvchi oyna, xotirada.

Nima uchun xotirada: chegara asosan BRUTE-FORCE va spamga qarshi, ya'ni
tez-tez takrorlanadigan urinishlarni bir nusxada ham to'sib qo'yish yetarli.
Web bir necha nusxada ishlasa chegara har nusxada alohida hisoblanadi —
bu kamchilik hujjatlashtirilgan (haqiqiy taqsimlangan chegara kerak bo'lsa
Postgres yoki Redis asosiga o'tkaziladi).

Qoidalar bitta joyda (`QOIDA`) — endpointlar faqat nomini aytadi.
"""
import threading
import time

from fastapi import Request

# nom -> (nechta urinish, necha soniyada)
QOIDA = {
    "kirish_parol": (8, 300),      # parol bilan kirish — brute-force to'sig'i
    "kirish_tg": (20, 300),        # imzo tekshiruvi
    "kirish_dev": (20, 300),
    "royxat": (5, 3600),           # bitta IP dan soatiga 5 akkaunt (bepul
                                   # promptlarni soxta email bilan olmasin)
    "tiklash": (5, 900),           # parol tiklash xati
    "boshla": (20, 60),            # savol yuborish
    "tanishuv": (20, 60),
    "mentor": (30, 60),            # reja/dars/test amallari
    "maqsad": (30, 60),            # sikl amallari (holat o'zgarishlari)
    "maqsad_llm": (10, 300),       # xulosa chiqarish — LLM chaqiradi
    "diag_javob": (240, 60),       # diagnostika cheklisti: 926 savol tez
                                   # belgilanadi, LLM chaqirilmaydi — keng oyna
    "vazifa": (10, 300),           # uy vazifasini topshirish (LLM tekshiradi)
    "kurs_qur": (3, 3600),         # kurs qurish — qimmat, egasi tashabbusi
    "tolov": (10, 60),             # to'lov yozuvi yaratish
    "preview": (10, 300),          # xulq preview — LLM chaqiradi, pul sarflaydi
    "tg_yubor": (20, 300),         # fragmentni Telegramga yuborish

    # --- B2B API (b2b.py, api_v1.py) ---------------------------------------
    # Tashkilot bo'yicha chegara `tashkilotlar.daqiqa_limit` da ham bor;
    # bu yerdagisi UMUMIY tom (shartnomadagi qiymat undan past bo'lishi mumkin).
    "api_umumiy": (300, 60),       # bitta tashkilotning har xil so'rovlari
    "api_savol": (60, 60),         # savol yuborish — tashkilot bo'yicha
    "api_user": (20, 60),          # hamkorning BITTA mijozi bo'yicha
    "api_kalit": (10, 300),        # noto'g'ri kalit bilan urinish (brute-force)
}

TOZALASH_S = 600                   # eskirgan kalitlarni tozalash oralig'i

_urinishlar: dict[tuple[str, str], list[float]] = {}
_qulf = threading.Lock()
_oxirgi_tozalash = 0.0


def ip(request: Request) -> str:
    """Mijoz IP si (Railway proksisi orqasida X-Forwarded-For birinchi qadami)."""
    bosh = request.headers.get("x-forwarded-for", "")
    if bosh:
        return bosh.split(",")[0].strip()[:45]
    return (request.client.host if request.client else "?")[:45]


def _tozala(hozir: float):
    global _oxirgi_tozalash
    if hozir - _oxirgi_tozalash < TOZALASH_S:
        return
    _oxirgi_tozalash = hozir
    for k in [k for k, v in _urinishlar.items() if not v or hozir - v[-1] > 3600]:
        _urinishlar.pop(k, None)


def ruxsat(nom: str, kalit: str) -> bool:
    """True = o'tkazamiz. Chaqirilishi urinish deb hisoblanadi."""
    soni, oyna = QOIDA.get(nom, (60, 60))
    hozir = time.time()
    with _qulf:
        _tozala(hozir)
        k = (nom, kalit)
        oqim = [t for t in _urinishlar.get(k, []) if hozir - t < oyna]
        oqim.append(hozir)
        _urinishlar[k] = oqim
        return len(oqim) <= soni


def qoldi(nom: str, kalit: str) -> int:
    """Nechta urinish qoldi (javob sarlavhasi uchun)."""
    soni, oyna = QOIDA.get(nom, (60, 60))
    hozir = time.time()
    with _qulf:
        oqim = [t for t in _urinishlar.get((nom, kalit), []) if hozir - t < oyna]
    return max(0, soni - len(oqim))


def tozala_hammasi():
    """Sinovlar uchun: hisoblagichlarni nolga qaytaradi."""
    with _qulf:
        _urinishlar.clear()
