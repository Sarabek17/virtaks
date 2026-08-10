# -*- coding: utf-8 -*-
"""Elektron pochta — tasdiqlash va parol tiklash xatlari.

Ikki yo'l qo'llab-quvvatlanadi (birinchi sozlangani ishlatiladi):
  1. RESEND_API_KEY (+ POCHTA_FROM) — HTTPS API, Railway'da SMTP portlari
     yopiq bo'lsa ham ishlaydi;
  2. SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PAROL (+ POCHTA_FROM).

Hech biri sozlanmagan bo'lsa `sozlangan()` False qaytaradi va tizim
"tasdiqsiz rejim"ga o'tadi (qarang: auth.tasdiq_shart) — havola loglarga
yoziladi, xat yuborilmaydi. Bu LOKAL ish uchun; jonli muhitda sozlanmasa
monitoring orqali ogohlantiriladi.

Xat matnida foydalanuvchi kiritgan hech qanday erkin matn ISHLATILMAYDI
(faqat ism — HTML dan qochirilgan holda), model chiqishi esa umuman yo'q:
pochta — tashqi kanal, unga LLM matni chiqmasligi kerak.
"""
import html
import os
import smtplib
from email.message import EmailMessage

import requests

from .sozlama import log

MUHLAT = 20


def _env(nom: str, zaxira: str = "") -> str:
    return (os.environ.get(nom, "") or zaxira).strip()


def kimdan() -> str:
    return _env("POCHTA_FROM") or _env("SMTP_USER")


def usul() -> str:
    """'resend' | 'smtp' | '' (sozlanmagan)."""
    if _env("RESEND_API_KEY") and kimdan():
        return "resend"
    if _env("SMTP_HOST") and kimdan():
        return "smtp"
    return ""


def sozlangan() -> bool:
    return bool(usul())


def _resend(manzil: str, mavzu: str, matn: str, html_matn: str) -> bool:
    r = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {_env('RESEND_API_KEY')}"},
        json={"from": kimdan(), "to": [manzil], "subject": mavzu,
              "text": matn, "html": html_matn},
        timeout=MUHLAT)
    if r.status_code >= 300:
        log(f"pochta (resend) xatosi {r.status_code}: {r.text[:200]}")
        return False
    return True


def _smtp(manzil: str, mavzu: str, matn: str, html_matn: str) -> bool:
    xat = EmailMessage()
    xat["Subject"] = mavzu
    xat["From"] = kimdan()
    xat["To"] = manzil
    xat.set_content(matn)
    xat.add_alternative(html_matn, subtype="html")
    port = int(_env("SMTP_PORT", "587"))
    host = _env("SMTP_HOST")
    if port == 465:
        s = smtplib.SMTP_SSL(host, port, timeout=MUHLAT)
    else:
        s = smtplib.SMTP(host, port, timeout=MUHLAT)
    with s:
        if port != 465:
            s.starttls()
        if _env("SMTP_USER"):
            s.login(_env("SMTP_USER"), _env("SMTP_PAROL"))
        s.send_message(xat)
    return True


def yubor(manzil: str, mavzu: str, matn: str, html_matn: str = "") -> bool:
    """Xat yuboradi. Sozlanmagan bo'lsa False (chaqiruvchi qaror qiladi)."""
    u = usul()
    if not u:
        log(f"POCHTA SOZLANMAGAN — xat yuborilmadi ({manzil}): {mavzu}")
        return False
    html_matn = html_matn or f"<pre>{html.escape(matn)}</pre>"
    try:
        return _resend(manzil, mavzu, matn, html_matn) if u == "resend" \
            else _smtp(manzil, mavzu, matn, html_matn)
    except Exception as e:                                    # noqa: BLE001
        log(f"pochta yuborilmadi ({manzil}): {type(e).__name__}: {str(e)[:150]}")
        return False


# ---------------------------------------------------------------- shablonlar

_QOLIP = """<!doctype html>
<div style="font-family:system-ui,Segoe UI,sans-serif;background:#f6f7fb;
            padding:32px 16px">
  <div style="max-width:520px;margin:0 auto;background:#fff;border-radius:14px;
              padding:32px;border:1px solid #e6e8f0">
    <div style="font-size:20px;font-weight:700;color:#1a1d29">{sarlavha}</div>
    <div style="margin:16px 0;color:#41475c;line-height:1.6">{tan}</div>
    <a href="{havola}" style="display:inline-block;background:#5b5bd6;color:#fff;
       text-decoration:none;padding:12px 22px;border-radius:9px;font-weight:600">
       {tugma}</a>
    <div style="margin-top:20px;color:#7b8194;font-size:13px;line-height:1.6">
      Tugma ishlamasa, shu manzilni brauzerga nusxalang:<br>
      <span style="color:#5b5bd6;word-break:break-all">{havola}</span>
    </div>
    <div style="margin-top:24px;padding-top:16px;border-top:1px solid #eceef4;
                color:#9aa0b0;font-size:12px">
      Bu xatni siz so'ramagan bo'lsangiz — e'tiborsiz qoldiring.
      Havola {soat} soatdan keyin ishlamaydi.
    </div>
  </div>
</div>"""


def tasdiq_xati(manzil: str, ism: str, havola: str, soat: int = 48) -> bool:
    matn = (f"Assalomu alaykum, {ism}!\n\n"
            f"Akkauntingizni tasdiqlash uchun havolani oching:\n{havola}\n\n"
            f"Havola {soat} soat amal qiladi.")
    return yubor(manzil, "Akkauntingizni tasdiqlang", matn,
                 _QOLIP.format(sarlavha="Akkauntingizni tasdiqlang",
                               tan=f"Assalomu alaykum, {html.escape(ism)}! "
                                   f"Ro'yxatdan o'tishni yakunlash uchun "
                                   f"quyidagi tugmani bosing.",
                               havola=html.escape(havola, quote=True),
                               tugma="Akkauntni tasdiqlash", soat=soat))


def tiklash_xati(manzil: str, ism: str, havola: str, soat: int = 2) -> bool:
    matn = (f"Assalomu alaykum, {ism}!\n\n"
            f"Parolni tiklash uchun havolani oching:\n{havola}\n\n"
            f"Havola {soat} soat amal qiladi. Siz so'ramagan bo'lsangiz — "
            f"e'tiborsiz qoldiring, parolingiz o'zgarmaydi.")
    return yubor(manzil, "Parolni tiklash", matn,
                 _QOLIP.format(sarlavha="Parolni tiklash",
                               tan=f"Assalomu alaykum, {html.escape(ism)}! "
                                   f"Yangi parol o'rnatish uchun quyidagi "
                                   f"tugmani bosing.",
                               havola=html.escape(havola, quote=True),
                               tugma="Yangi parol o'rnatish", soat=soat))
