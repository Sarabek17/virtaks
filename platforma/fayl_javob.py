# -*- coding: utf-8 -*-
"""S3 dagi faylni HTTP javobiga aylantirish (Range qo'llab-quvvatlanadi).

Nega alohida modul: ayni shu mantiq IKKI yuzaga kerak — `web.py` (brauzer
audio pleeri) va `api_v1.py` (B2B hamkor). Ikki nusxa bo'lsa, birida
tuzatilgan Range xatosi ikkinchisida qolib ketardi.

Bu modul `web` ni ham, `api_v1` ni ham import QILMAYDI — aks holda aylanma
import bo'lardi (`web` -> `api_v1` -> `web`).
"""
import re

from fastapi import Request
from fastapi.responses import Response

from . import storage

_ORALIQ = re.compile(r"bytes=(\d+)-(\d*)")


def javob(yol: str, request: Request, mime: str, nom: str,
          kesh: str = "private, max-age=86400") -> Response | None:
    """S3 obyektini qaytaradi; `Range` bo'lsa 206 bilan faqat so'ralgan qismi.

    Fayl o'qilmasa **None** — chaqiruvchi o'z yuzasining 404 ini qaytaradi
    (web va B2B da xato JSON shakli boshqacha).
    """
    try:
        tarkib = storage.ol(yol)
    except Exception:                                        # noqa: BLE001
        return None
    jami = len(tarkib)
    bosh_h = {"Content-Disposition": f'inline; filename="{nom}"',
              "Accept-Ranges": "bytes", "Cache-Control": kesh}
    m = _ORALIQ.match(request.headers.get("range", ""))
    if m:
        b1 = int(m.group(1))
        b2 = int(m.group(2)) if m.group(2) else jami - 1
        b2 = min(b2, jami - 1)
        if b1 > b2:
            return Response(status_code=416)
        return Response(tarkib[b1:b2 + 1], status_code=206, media_type=mime,
                        headers={**bosh_h, "Content-Range": f"bytes {b1}-{b2}/{jami}"})
    return Response(tarkib, media_type=mime, headers=bosh_h)
