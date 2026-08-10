# -*- coding: utf-8 -*-
"""Autentifikatsiya: email+parol (klient), Telegram (Widget + Mini App),
login+parol (egasi/admin).

2026-07-31 dan klientlar Telegramsiz ham kira oladi: email + parol bilan
ro'yxatdan o'tadi, xat orqali tasdiqlaydi. Telegram endi IXTIYORIY kanal
(fragment yuborish, bildirishnoma) — akkauntga keyin bog'lanadi.
Twin egasi va admin login/parol bilan kiradi (kabinet/admin panel).
"""
import hashlib
import hmac
import json
import os
import re
import time
import urllib.parse

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from . import db
from .sozlama import LOYIHA, PROD

MUDDAT = 2 * 86400        # TG imzosi eskirish muddati
_ph = PasswordHasher()
_env_kesh = {"mtime": None}


def _env(nom: str) -> str:
    """Muhit o'zgaruvchisi; lokalda eski .env dan ham o'qiladi (mtime-kesh bilan)."""
    qiymat = os.environ.get(nom, "").strip()
    if qiymat:
        return qiymat
    yol = LOYIHA / ".env"
    try:
        mtime = os.path.getmtime(yol)
    except OSError:
        return ""
    if _env_kesh["mtime"] != mtime:
        from dotenv import load_dotenv
        load_dotenv(yol, override=False)
        _env_kesh["mtime"] = mtime
    return os.environ.get(nom, "").strip()


def bot_token() -> str:
    if os.environ.get("KENGASH_BOT_OFF", "").strip():
        return ""
    return _env("TELEGRAM_BOT_TOKEN")


def public_url() -> str:
    return _env("PUBLIC_URL").rstrip("/")


def dev_rejim() -> bool:
    """Parolsiz "dev" kirish — FAQAT lokal ishlab chiqishda.

    DIQQAT (2026-07-31 da topilgan teshik): avval shart faqat "bot tokeni yo'q"
    edi. Bulutdagi yangi web'da bot ATAYLAB o'chirilgan (`KENGASH_BOT_OFF=1` —
    eski servis bilan webhook to'qnashmasin), shuning uchun jonli URL'da
    `/api/kirish/dev` ochilib qolgandi: istalgan odam ism yozib klient
    sessiyasini olardi. Endi HAR QANDAY jonli muhitda (`sozlama.PROD` —
    Railway yoki o'z serverimiz) dev-rejim yoqilmaydi; zarur bo'lsa
    `DEV_KIRISH=1` bilan ATAYLAB ochiladi.

    Shart ataylab bot tokeniga bog'liq EMAS: token tushib qolsa yoki
    KENGASH_BOT_OFF qo'yilsa ham jonli serverda teshik ochilmasligi kerak.
    """
    if _env("DEV_KIRISH") == "1":
        return True
    if PROD:
        return False
    return not bot_token()


# ---------------------------------------------------------------- Telegram

def widget_tekshir(data: dict) -> dict | None:
    token = bot_token()
    if not token or "hash" not in data:
        return None
    kelgan = data["hash"]
    dcs = "\n".join(sorted(f"{k}={v}" for k, v in data.items()
                           if k != "hash" and v is not None))
    sirli = hashlib.sha256(token.encode()).digest()
    if not hmac.compare_digest(
            hmac.new(sirli, dcs.encode(), hashlib.sha256).hexdigest(), kelgan):
        return None
    try:
        if time.time() - int(data.get("auth_date", 0)) > MUDDAT:
            return None
        return {"id": int(data["id"]), "first_name": data.get("first_name", ""),
                "last_name": data.get("last_name", ""),
                "username": data.get("username", ""),
                "photo_url": data.get("photo_url", "")}
    except (KeyError, ValueError):
        return None


def webapp_tekshir(init_data: str) -> dict | None:
    token = bot_token()
    if not token or not init_data:
        return None
    data = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    kelgan = data.pop("hash", None)
    if not kelgan:
        return None
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    sirli = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(
            hmac.new(sirli, dcs.encode(), hashlib.sha256).hexdigest(), kelgan):
        return None
    try:
        if time.time() - int(data.get("auth_date", 0)) > MUDDAT:
            return None
        u = json.loads(data.get("user", "{}"))
        return {"id": int(u["id"]), "first_name": u.get("first_name", ""),
                "last_name": u.get("last_name", ""),
                "username": u.get("username", ""),
                "photo_url": u.get("photo_url", "")}
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------- email (klient)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]{2,}$")
PAROL_MIN = 8
TASDIQ_SOAT = 48
TIKLASH_SOAT = 2


def email_tugri(email: str) -> bool:
    e = (email or "").strip()
    return bool(e) and len(e) <= 160 and bool(EMAIL_RE.match(e))


def parol_kuchi(parol: str) -> str:
    """Bo'sh satr = mos. Aks holda — foydalanuvchiga ko'rsatiladigan sabab."""
    p = parol or ""
    if len(p) < PAROL_MIN:
        return f"Parol kamida {PAROL_MIN} belgi bo'lsin"
    if len(p) > 200:
        return "Parol juda uzun"
    if p.isdigit() or p.isalpha():
        return "Parolda harf ham, raqam ham bo'lsin"
    return ""


def tasdiq_shart() -> bool:
    """Email tasdiqlash majburiymi.

    Pochta sozlanmagan bo'lsa xat yubora olmaymiz — bunday holda akkaunt
    darhol ochiladi (aks holda tizim umuman ishlamay qoladi). Jonli muhitda
    bu holat monitoring orqali ko'rinadi: `pochta.sozlangan()` False bo'lsa
    3 ta bepul prompt soxta emaillar bilan suiiste'mol qilinishi mumkin.
    """
    from . import pochta
    if _env("EMAIL_TASDIQ") == "0":
        return False
    return pochta.sozlangan()


def parol_bilan_email(email: str, parol: str) -> dict | None:
    """Email + parol bilan kirish (klient yo'li)."""
    u = db.user_email_ol(email)
    if not u or not u.get("parol_hash") or u.get("bloklangan"):
        return None
    try:
        _ph.verify(u["parol_hash"], parol)
    except Exception:                                         # noqa: BLE001
        return None
    if _ph.check_needs_rehash(u["parol_hash"]):
        db.parol_yangila(u["id"], _ph.hash(parol))
    return u


# ---------------------------------------------------------------- parol (egasi/admin)

def parol_hash(parol: str) -> str:
    return _ph.hash(parol)


def parol_tekshir(login: str, parol: str) -> dict | None:
    u = db.user_login_ol(login)
    if not u or not u.get("parol_hash") or u.get("bloklangan"):
        return None
    try:
        _ph.verify(u["parol_hash"], parol)
    except VerifyMismatchError:
        return None
    except Exception:
        return None
    if _ph.check_needs_rehash(u["parol_hash"]):
        db.user_yangila(u["id"], parol_hash=_ph.hash(parol))
    return u


# ---------------------------------------------------------------- rollar

def admin_mi(u: dict | None) -> bool:
    return bool(u) and u.get("rol") == "admin"


def egasi_mi(u: dict | None) -> bool:
    return bool(u) and u.get("rol") in ("egasi", "admin")


def twin_egasi_mi(u: dict | None, twin_id: int) -> bool:
    """Admin — hamma twinga; egasi — faqat o'zinikiga."""
    if admin_mi(u):
        return True
    if not u or u.get("rol") != "egasi":
        return False
    t = db.twin_ol(twin_id)
    return bool(t) and t.get("egasi_id") == u["id"]
