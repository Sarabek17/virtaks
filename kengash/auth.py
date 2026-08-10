# -*- coding: utf-8 -*-
"""Telegram autentifikatsiya: Login Widget (sayt) + Mini App initData tekshiruvi.

Ikkalasi ham HMAC imzo bilan tekshiriladi — soxta login mumkin emas:
  Widget:  secret = SHA256(bot_token)
  WebApp:  secret = HMAC_SHA256(key="WebAppData", msg=bot_token)
Bot token bo'lmasa tizim DEV-REJIMda ishlaydi (faqat lokal sinov uchun).
"""
import hashlib
import hmac
import json
import os
import time
import urllib.parse

from .sozlama import LOYIHA

MUDDAT = 2 * 86400        # login imzosi eskirish muddati (soniya)


_env_kesh = {"mtime": None}


def _env(nom: str) -> str:
    """.env dan qiymat. Fayl faqat o'zgargandagina qayta o'qiladi —
    ilgari HAR chaqiruvda (har HTTP so'rovda) fayl to'liq o'qilardi."""
    from dotenv import load_dotenv
    yol = LOYIHA / ".env"
    try:
        mtime = os.path.getmtime(yol)
    except OSError:
        mtime = None      # fayl yo'q (masalan Railway — env o'zgaruvchilar to'g'ridan)
    if mtime is not None and _env_kesh["mtime"] != mtime:
        load_dotenv(yol, override=True)
        _env_kesh["mtime"] = mtime
    return os.environ.get(nom, "").strip()


def bot_token() -> str:
    # KENGASH_BOT_OFF=1 — lokal sinov rejimi: bot va TG kirish o'chiq (dev-rejim).
    # .env dagi haqiqiy token o'qilmaydi -> bulutdagi bot bilan getUpdates
    # konflikti bo'lmaydi (_env override=True bo'lgani uchun env-hiyla ishlamaydi)
    if os.environ.get("KENGASH_BOT_OFF", "").strip():
        return ""
    return _env("TELEGRAM_BOT_TOKEN")


def public_url() -> str:
    return _env("PUBLIC_URL").rstrip("/")


def dev_rejim() -> bool:
    return not bot_token()


def widget_tekshir(data: dict) -> dict | None:
    """Telegram Login Widget ma'lumotini tekshiradi -> tg user dict yoki None."""
    token = bot_token()
    if not token or "hash" not in data:
        return None
    kelgan = data["hash"]
    juftlar = sorted(f"{k}={v}" for k, v in data.items()
                     if k != "hash" and v is not None)
    dcs = "\n".join(juftlar)
    sirli = hashlib.sha256(token.encode()).digest()
    kutilgan = hmac.new(sirli, dcs.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(kutilgan, kelgan):
        return None
    try:
        if time.time() - int(data.get("auth_date", 0)) > MUDDAT:
            return None
        return {"id": int(data["id"]),
                "first_name": data.get("first_name", ""),
                "last_name": data.get("last_name", ""),
                "username": data.get("username", ""),
                "photo_url": data.get("photo_url", "")}
    except (KeyError, ValueError):
        return None


def webapp_tekshir(init_data: str) -> dict | None:
    """Mini App initData qatorini tekshiradi -> tg user dict yoki None."""
    token = bot_token()
    if not token or not init_data:
        return None
    juftlar = urllib.parse.parse_qsl(init_data, keep_blank_values=True)
    data = dict(juftlar)
    kelgan = data.pop("hash", None)
    if not kelgan:
        return None
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    sirli = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    kutilgan = hmac.new(sirli, dcs.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(kutilgan, kelgan):
        return None
    try:
        if time.time() - int(data.get("auth_date", 0)) > MUDDAT:
            return None
        u = json.loads(data.get("user", "{}"))
        return {"id": int(u["id"]),
                "first_name": u.get("first_name", ""),
                "last_name": u.get("last_name", ""),
                "username": u.get("username", ""),
                "photo_url": u.get("photo_url", "")}
    except (KeyError, ValueError, json.JSONDecodeError):
        return None
