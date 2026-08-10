# -*- coding: utf-8 -*-
"""Xato monitoringi — jiddiy xatolar admin Telegramiga.

Qoidalar:
  * Bir xil xato takror-takror yuborilmaydi (kalit bo'yicha 10 daqiqada bir marta).
  * Soatiga umumiy chegara — xato bo'roni admin chatini ko'mib tashlamasin.
  * Xabar matni FAQAT shu koddan va xato matnidan tuziladi; foydalanuvchi
    matni qisqartirilib, HTML ekranlanadi (Lethal Trifecta: tashqi kanalga
    ketayotgan matnni model yoki foydalanuvchi boshqarmasin).
  * Yuborish xatosi hech qachon asosiy oqimni buzmaydi.

Manzil: `XATO_TG_KANAL` env (chat id) yoki adminlarning tg_id si.
"""
import hashlib
import os
import threading
import time

from .sozlama import log

TAKROR_S = 600          # bir xil xato shu muddatda qayta yuborilmaydi
SOATLIK_CHEGARA = 20    # umumiy chegara
MAKS_MATN = 700

_oxirgi: dict[str, float] = {}
_soat: list[float] = []
_qulf = threading.Lock()


def _qoch(s: str) -> str:
    return (str(s) or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _manzillar() -> list[int]:
    kanal = os.environ.get("XATO_TG_KANAL", "").strip()
    if kanal:
        try:
            return [int(kanal)]
        except ValueError:
            log("XATO_TG_KANAL noto'g'ri format")
    from . import pg
    try:
        return [q[0] for q in pg.hammasi(
            "SELECT tg_id FROM userlar WHERE rol='admin' AND tg_id IS NOT NULL")]
    except Exception:                                        # noqa: BLE001
        return []


def _ruxsat(kalit: str) -> bool:
    hozir = time.time()
    with _qulf:
        _soat[:] = [t for t in _soat if hozir - t < 3600]
        if len(_soat) >= SOATLIK_CHEGARA:
            return False
        if hozir - _oxirgi.get(kalit, 0) < TAKROR_S:
            return False
        _oxirgi[kalit] = hozir
        _soat.append(hozir)
        return True


def xato(sarlavha: str, tafsilot: str = "", kalit: str = "", jimgina: bool = False):
    """Jiddiy xatoni adminga yuboradi (fonda, bloklamasdan)."""
    kalit = kalit or hashlib.sha256(
        f"{sarlavha}|{tafsilot[:200]}".encode()).hexdigest()[:16]
    if not _ruxsat(kalit):
        return False
    matn = (f"🚨 <b>{_qoch(sarlavha)[:150]}</b>\n"
            f"<code>{_qoch(tafsilot)[:MAKS_MATN]}</code>")
    if not jimgina:
        log(f"MONITORING: {sarlavha} — {tafsilot[:120]}")

    def yubor():
        from . import tg
        for chat in _manzillar():
            try:
                tg.yubor(chat, matn)
            except Exception as e:                           # noqa: BLE001
                log(f"monitoring yuborilmadi: {str(e)[:80]}")

    threading.Thread(target=yubor, daemon=True).start()
    return True


def job_xatosi(job: dict, sabab: str):
    """Job yakuniy yiqilganda (qayta urinishlar tugagach)."""
    xato(f"Job #{job['id']} yiqildi — {job['tur']}",
         f"user={job.get('user_id')} twin={job.get('twin_id')}\n{sabab}",
         kalit=f"job:{job['tur']}:{sabab[:80]}")


def web_xatosi(yol: str, sabab: str):
    xato(f"WEB xatosi: {yol}", sabab, kalit=f"web:{yol}:{sabab[:80]}")
