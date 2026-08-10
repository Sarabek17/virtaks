# -*- coding: utf-8 -*-
"""Telegram — webhook rejimi (long-polling emas: ko'p nusxa bilan ham ishlaydi).

Webhook /tg/webhook/{sir} manziliga keladi; sir = bot tokendan hosil qilingan
qisqa hash (begona so'rov kirmasin).
"""
import hashlib

import requests

from . import auth, db
from .sozlama import log


def _api(metod: str, **kw):
    token = auth.bot_token()
    if not token:
        return None
    r = requests.post(f"https://api.telegram.org/bot{token}/{metod}",
                      json=kw, timeout=30)
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(f"TG {metod}: {j.get('description', r.status_code)}")
    return j["result"]


_kesh = {}


def bot_username() -> str | None:
    if not auth.bot_token():
        return None
    if "username" not in _kesh:
        try:
            _kesh["username"] = _api("getMe")["username"]
        except Exception as e:
            log(f"TG getMe xatosi: {str(e)[:100]}")
            return None
    return _kesh["username"]


def webhook_sir() -> str:
    return hashlib.sha256(("wh:" + auth.bot_token()).encode()).hexdigest()[:32]


def webhook_ornat() -> bool:
    """Webhook manzilini o'rnatadi (server ishga tushganda)."""
    url = auth.public_url()
    if not url.startswith("https://") or not auth.bot_token():
        log("TG webhook o'rnatilmadi (PUBLIC_URL yoki token yo'q)")
        return False
    try:
        _api("setWebhook", url=f"{url}/tg/webhook/{webhook_sir()}",
             allowed_updates=["message"], drop_pending_updates=False)
        log(f"TG webhook o'rnatildi: @{bot_username()}")
        return True
    except Exception as e:
        log(f"TG webhook xatosi: {str(e)[:120]}")
        return False


def _app_tugma():
    url = auth.public_url()
    if url.startswith("https://"):
        return {"inline_keyboard": [[{"text": "🏛 Ilovani ochish",
                                      "web_app": {"url": url}}]]}
    return None


def yubor(chat_id: int, matn: str, klaviatura=None):
    kw = {"chat_id": chat_id, "text": matn, "parse_mode": "HTML"}
    if klaviatura:
        kw["reply_markup"] = klaviatura
    try:
        _api("sendMessage", **kw)
    except Exception as e:
        log(f"TG yuborish xatosi: {str(e)[:100]}")


def _tg_id(user_id: int) -> int | None:
    u = db.user_ol(user_id)
    return u.get("tg_id") if u else None


def _fayl_yubor(user_id: int, metod: str, maydon: str, nom: str, tarkib: bytes,
                izoh: str = "", qoshimcha: dict | None = None) -> bool:
    """Faylni userning TG chatiga yuboradi (bog'lanmagan bo'lsa jimgina o'tadi)."""
    token = auth.bot_token()
    chat = _tg_id(user_id) if token else None
    if not chat:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/{metod}",
            data={"chat_id": chat, "caption": izoh[:1000], "parse_mode": "HTML",
                  **(qoshimcha or {})},
            files={maydon: (nom, tarkib)}, timeout=180)
        if not r.json().get("ok"):
            log(f"TG {metod} yuborilmadi: {str(r.text)[:150]}")
            return False
        return True
    except Exception as e:
        log(f"TG {metod} xatosi: {str(e)[:100]}")
        return False


def hujjat_yubor(user_id: int, nom: str, tarkib: bytes, izoh: str = ""):
    return _fayl_yubor(user_id, "sendDocument", "document", nom, tarkib,
                       izoh or "📎 Tayyor fayl")


def audio_yubor(user_id: int, nom: str, tarkib: bytes, sarlavha: str, izoh: str = ""):
    """Dars yozuvining aynan kesilgan qismi."""
    matn = f"🎧 <b>{sarlavha}</b>" + (f"\n{izoh}" if izoh else "")
    return _fayl_yubor(user_id, "sendAudio", "audio", nom, tarkib, matn,
                       {"title": sarlavha[:60], "performer": "Virtaks"})


def rasm_yubor(user_id: int, nom: str, tarkib: bytes, sarlavha: str, izoh: str = ""):
    matn = f"🖼 <b>{sarlavha}</b>" + (f"\n{izoh}" if izoh else "")
    return _fayl_yubor(user_id, "sendPhoto", "photo", nom, tarkib, matn)


def matn_yubor(user_id: int, matn: str) -> bool:
    chat = _tg_id(user_id)
    if not chat or not auth.bot_token():
        return False
    yubor(chat, matn)
    return True


def xabar(m: dict):
    """Kelgan xabarni qayta ishlaydi (webhook'dan)."""
    chat_id = m["chat"]["id"]
    kimdan = m.get("from", {})
    matn = (m.get("text") or "").strip()

    if "contact" in m:
        k = m["contact"]
        if k.get("user_id") != kimdan.get("id"):
            yubor(chat_id, "⚠️ Faqat <b>o'zingizning</b> kontaktingiz qabul qilinadi.")
            return
        u = db.user_tg({"id": kimdan["id"],
                        "first_name": kimdan.get("first_name", "") or k.get("first_name", ""),
                        "last_name": kimdan.get("last_name", ""),
                        "username": kimdan.get("username", ""),
                        "telefon": k.get("phone_number", "")})
        yubor(chat_id, f"✅ Akkauntingiz tayyor, <b>{u['ism']}</b>!\n"
                       f"Endi ilovada ishlashingiz mumkin — suhbat tarixingiz "
                       f"faqat sizga ko'rinadi.",
              _app_tugma() or {"remove_keyboard": True})
        return

    if matn.startswith("/start"):
        db.user_tg({"id": kimdan["id"], "first_name": kimdan.get("first_name", ""),
                    "last_name": kimdan.get("last_name", ""),
                    "username": kimdan.get("username", "")})
        yubor(chat_id,
              "🎓 <b>Virtaks</b> — ustozlaringizning raqamli nusxasi\n\n"
              "Savol bering — javob faqat ustozning yuklangan darslari va "
              "hujjatlariga tayanadi, har da'voda manba ko'rsatiladi. "
              "Kerak bo'lsa dars yozuvining aynan o'sha qismini shu yerga "
              "yuborib beramiz.\n\n"
              "📱 Akkauntni telefon raqamingizga bog'lash uchun kontaktingizni yuboring:",
              {"keyboard": [[{"text": "📱 Kontaktimni yuborish", "request_contact": True}]],
               "resize_keyboard": True, "one_time_keyboard": True})
        t = _app_tugma()
        if t:
            yubor(chat_id, "Yoki ilovani darhol oching:", t)
        return

    t = _app_tugma()
    if t:
        yubor(chat_id, "Savollarni ilova ichida bering — javob yozilayotganini "
                       "jonli ko'rasiz va har manbani bosib tekshira olasiz:", t)
