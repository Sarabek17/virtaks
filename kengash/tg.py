# -*- coding: utf-8 -*-
"""Telegram bot — kirish nuqtasi: kontakt orqali ro'yxat + Mini App tugmasi.

Long-polling rejimda server jarayoni ichida daemon-oqim bo'lib ishlaydi.
TELEGRAM_BOT_TOKEN .env da bo'lmasa bot yoqilmaydi (dev-rejim).
"""
import threading
import time

import requests

from . import auth, db
from .sozlama import log

_kesh = {}


def _api(metod: str, **kw):
    token = auth.bot_token()
    r = requests.post(f"https://api.telegram.org/bot{token}/{metod}",
                      json=kw, timeout=75)
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(f"TG {metod}: {j.get('description', r.status_code)}")
    return j["result"]


def bot_username() -> str | None:
    """Bot @username (Login Widget uchun). Token yo'q/xato bo'lsa None."""
    if not auth.bot_token():
        return None
    if "username" not in _kesh:
        try:
            _kesh["username"] = _api("getMe")["username"]
        except Exception as e:
            log(f"TG getMe xatosi: {str(e)[:100]}")
            return None
    return _kesh["username"]


def _app_tugma():
    """Mini App ochish tugmasi (PUBLIC_URL https bo'lsa)."""
    url = auth.public_url()
    if url.startswith("https://"):
        return {"inline_keyboard": [[{"text": "🏛 Kengashni ochish",
                                      "web_app": {"url": url}}]]}
    return None


def _kontakt_klaviatura():
    return {"keyboard": [[{"text": "📱 Kontaktimni yuborish", "request_contact": True}]],
            "resize_keyboard": True, "one_time_keyboard": True}


def _yubor(chat_id: int, matn: str, klaviatura=None):
    kw = {"chat_id": chat_id, "text": matn, "parse_mode": "HTML"}
    if klaviatura:
        kw["reply_markup"] = klaviatura
    _api("sendMessage", **kw)


def _xabar(m: dict):
    chat_id = m["chat"]["id"]
    kimdan = m.get("from", {})
    matn = (m.get("text") or "").strip()

    # --- kontakt yuborildi -> akkaunt ochiladi/bog'lanadi ---
    if "contact" in m:
        k = m["contact"]
        # faqat O'ZINING kontakti qabul qilinadi (begona kontakt bilan kirib bo'lmaydi)
        if k.get("user_id") != kimdan.get("id"):
            _yubor(chat_id, "⚠️ Faqat <b>o'zingizning</b> kontaktingiz qabul qilinadi.")
            return
        u = db.user_tg({"id": kimdan["id"],
                        "first_name": kimdan.get("first_name", "") or k.get("first_name", ""),
                        "last_name": kimdan.get("last_name", ""),
                        "username": kimdan.get("username", ""),
                        "telefon": k.get("phone_number", "")})
        _yubor(chat_id,
               f"✅ Akkauntingiz tayyor, <b>{u['ism']}</b>!\n"
               f"Endi Kengash bilan ishlashingiz mumkin — suhbat tarixingiz "
               f"faqat sizga ko'rinadi.",
               _app_tugma() or {"remove_keyboard": True})
        return

    # --- /start ---
    if matn.startswith("/start"):
        # tg_id bilan yozamiz — kontakt bo'lmasa ham akkaunt ochiladi
        db.user_tg({"id": kimdan["id"],
                    "first_name": kimdan.get("first_name", ""),
                    "last_name": kimdan.get("last_name", ""),
                    "username": kimdan.get("username", "")})
        _yubor(chat_id,
               "🏛 <b>KENGASH</b> — AI direktorlar kengashi\n\n"
               "6 direktor (CEO, CTO, CFO, COO, CLO, CMO) + Rais sizning "
               "savolingizni faqat yuklangan bilim bazasi asosida muhokama qiladi.\n\n"
               "📱 Akkauntni telefon raqamingizga bog'lash uchun kontaktingizni yuboring:",
               _kontakt_klaviatura())
        tugma = _app_tugma()
        if tugma:
            _yubor(chat_id, "Yoki ilovani darhol oching:", tugma)
        return

    # --- boshqa har qanday xabar ---
    tugma = _app_tugma()
    if tugma:
        _yubor(chat_id, "Savollarni ilova ichida bering — javoblar manbalar "
                        "bilan chiroyli ko'rinishda chiqadi:", tugma)
    else:
        _yubor(chat_id, "Kengash ilovasi hozircha faqat brauzerda: sayt manzilini "
                        "administratordan oling. Akkauntingiz allaqachon tayyor ✓")


def _sikl():
    log(f"TG bot ishga tushdi: @{bot_username()}")
    try:
        _api("deleteWebhook", drop_pending_updates=False)
    except Exception:
        pass
    ofset = 0
    while True:
        try:
            for up in _api("getUpdates", offset=ofset, timeout=50,
                           allowed_updates=["message"]):
                ofset = up["update_id"] + 1
                if "message" in up:
                    try:
                        _xabar(up["message"])
                    except Exception as e:
                        log(f"TG xabar xatosi: {str(e)[:120]}")
        except Exception as e:
            log(f"TG polling xatosi: {str(e)[:120]} — 10s kutamiz")
            time.sleep(10)


def hujjat_yubor(user_id: int, yol, izoh: str = ""):
    """Tayyor faylni userning Telegram chatiga yuboradi (iloji bo'lsa).

    Token yo'q / user TG bilan bog'lanmagan / bot bloklangan — jimgina o'tadi."""
    token = auth.bot_token()
    if not token:
        return
    u = db.user_ol(user_id)
    if not u or not u.get("tg_id"):
        return
    try:
        with open(yol, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendDocument",
                data={"chat_id": u["tg_id"],
                      "caption": izoh or "📎 Kengash siz uchun tayyorlagan fayl"},
                files={"document": (yol.name, f)}, timeout=120)
        j = r.json()
        if j.get("ok"):
            log(f"TG hujjat yuborildi: {yol.name}")
        else:
            log(f"TG hujjat yuborilmadi: {str(j.get('description', ''))[:80]}")
    except Exception as e:
        log(f"TG hujjat xatosi: {str(e)[:80]}")


def yurgiz():
    """Bot oqimini yurgizadi (token bo'lsa). Server main() dan chaqiriladi."""
    if not auth.bot_token():
        log("TG bot: TELEGRAM_BOT_TOKEN yo'q — dev-rejim (bot o'chiq)")
        return
    threading.Thread(target=_sikl, daemon=True).start()
