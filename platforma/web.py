# -*- coding: utf-8 -*-
"""WEB servis — klient API + UI. Og'ir ish yo'q: hammasi worker'ga job bo'lib ketadi.

  python -m platforma.web    # lokal 127.0.0.1:8900; Railway'da PORT env
"""
import json
import os
import re
import time

from fastapi import FastAPI, Request
from fastapi.responses import (FileResponse, JSONResponse, Response,
                               StreamingResponse)
from pydantic import BaseModel

from . import (admin, aniqlik, auth, cheklov, db, fragment, jobs, kabinet,
               maqsad, maqsad_oqim, mentor, monitoring, oquv, pg, pochta,
               profil, pul, skilllar, storage, suhbat, tanishuv, tg, tizim,
               tizim_oqim, tolov, vazifa, yordamchi)
from .sozlama import ILDIZ, MUHIT, log

app = FastAPI(title="Virtaks platformasi")
app.include_router(admin.router)
app.include_router(kabinet.router)
app.include_router(tolov.router)
WEB = ILDIZ / "web"
COOKIE = "twin_sessiya"
BOSHLANGAN = time.time()
STAT = {}

# --- Content-Security-Policy -------------------------------------------------
# "Lethal Trifecta" ning UCHINCHI oyog'ini (tashqariga ma'lumot chiqarish) yopadi.
# Javob matni LLM dan keladi va unga manba fayllar ichidagi ishonchsiz matn ta'sir
# qilishi mumkin. Markdown chizuvchimiz havola/rasm sintaksisini umuman qo'llamaydi,
# CSP esa ikkinchi qator himoya: brauzer begona hostga so'rov yubora olmaydi.
CSP = "; ".join([
    "default-src 'self'",
    # butun ilova bitta faylda — inline skript/uslub kerak.
    # mermaid endi o'z serverimizdan ('self'); tashqi CDN ro'yxatda YO'Q.
    "script-src 'self' 'unsafe-inline' https://telegram.org",
    "style-src 'self' 'unsafe-inline'",
    # rasm faqat o'zimizdan va Telegram avatarlaridan
    "img-src 'self' data: https://t.me https://*.telegram-cdn.org "
    "https://*.telesco.pe https://*.cdn-telegram.org",
    "font-src 'self' data:",
    "connect-src 'self'",                       # fetch/XHR faqat o'z domeniga
    # 'self' — /tg-widget sahifasi uchun (pastdagi WIDGET_CSP izohiga qarang)
    "frame-src 'self' https://oauth.telegram.org https://telegram.org",
    "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org",
    "base-uri 'none'", "form-action 'self'", "object-src 'none'",
])

# --- Telegram Login Widget sahifasining ALOHIDA CSP'si ---------------------
# telegram-widget.js ichida `eval` bor — u yuqoridagi CSP'da bloklanadi
# (brauzer "EvalError: ... 'unsafe-eval' is not an allowed source" beradi va
# tugma umuman chizilmaydi). Butun ilovaga `unsafe-eval` berish o'rniga
# widget alohida kichkina sahifada (`/tg-widget`) ochiladi va faqat o'shanga
# ruxsat beriladi: u sahifada model javobi ham, foydalanuvchi ma'lumoti ham,
# ilova kodi ham yo'q — o'g'irlanadigan narsa yo'q. Asosiy ilova uni iframe
# bilan qo'yadi, natijani postMessage orqali oladi.
WIDGET_CSP = "; ".join([
    "default-src 'none'",
    "script-src 'unsafe-inline' 'unsafe-eval' https://telegram.org",
    "style-src 'unsafe-inline'",
    "img-src https://t.me https://*.telegram-cdn.org https://*.telesco.pe data:",
    "connect-src 'self'",                       # faqat o'z API'mizga
    "frame-src https://oauth.telegram.org",
    "frame-ancestors 'self'",                   # faqat o'z ilovamiz ichida
    "base-uri 'none'", "form-action 'none'", "object-src 'none'",
])


@app.middleware("http")
async def xavfsizlik_boshlari(request: Request, call_next):
    yol = request.url.path
    try:
        javob = await call_next(request)
    except Exception as e:
        # Kutilmagan xato — adminga xabar (matn qisqartirilgan, sirlarsiz)
        monitoring.web_xatosi(yol, f"{type(e).__name__}: {str(e)[:300]}")
        raise
    # Marshrut o'zi CSP qo'ygan bo'lsa (masalan /tg-widget) — tegilmaydi.
    if (not yol.startswith(("/api/", "/tg/", "/tolov/"))
            and "Content-Security-Policy" not in javob.headers):
        javob.headers["Content-Security-Policy"] = CSP
    javob.headers["X-Content-Type-Options"] = "nosniff"
    javob.headers["Referrer-Policy"] = "same-origin"
    return javob


def _429(xabar: str = "Juda ko'p urinish — biroz kuting"):
    return JSONResponse({"xato": xabar}, status_code=429)


# ---------------------------------------------------------------- yordamchilar

def _joriy(request: Request) -> dict | None:
    return db.sessiya_user(request.cookies.get(COOKIE, ""))


def _401():
    return JSONResponse({"xato": "kirish kerak"}, status_code=401)


def _404():
    return JSONResponse({"xato": "topilmadi"}, status_code=404)


def _user_json(u: dict) -> dict:
    return {"id": u["id"], "ism": u["ism"], "familiya": u["familiya"],
            "username": u["username"], "foto": u["foto"], "rol": u["rol"],
            "telefon": bool(u["telefon"]), "twin": u.get("joriy_twin"),
            "impersonator": u.get("impersonator_id"),
            "email": u.get("email") or "",
            "email_tasdiq": bool(u.get("email_tasdiq")),
            "tg_bogliq": bool(u.get("tg_id"))}


def _kirish_javobi(u: dict, impersonator: int | None = None) -> JSONResponse:
    r = JSONResponse({"ok": True, "user": _user_json(u)})
    r.set_cookie(COOKIE, db.sessiya_yasa(u["id"], impersonator),
                 max_age=db.SESSIYA_KUN * 86400, httponly=True, samesite="lax")
    return r


def _twin_tanla(u: dict) -> int | None:
    """Userning joriy twini; tanlanmagan bo'lsa birinchi faol twin."""
    if u.get("joriy_twin"):
        t = db.twin_ol(u["joriy_twin"])
        if t and t["faol"]:
            return t["id"]
    royxat = db.twinlar()
    return royxat[0]["id"] if royxat else None


# ---------------------------------------------------------------- salomatlik

@app.get("/salomatlik")
def salomatlik():
    holat = {"muhit": MUHIT, "ishlagan_s": round(time.time() - BOSHLANGAN)}
    try:
        pg.bitta("SELECT 1")
        holat["pg"] = "ok"
    except Exception as e:
        holat["pg"] = f"xato: {str(e)[:80]}"
    return JSONResponse(holat, status_code=200 if holat["pg"] == "ok" else 503)


# ---------------------------------------------------------------- kirish

# Kirish FAQAT Telegram orqali (egasi qarori, 2026-08-02). Email+parol bilan
# ro'yxatdan o'tish/kirish va parolni tiklash yo'llari yopilgan: UI'da ham yo'q,
# endpointlar ham 404 qaytaradi (aks holda cheklov faqat ko'zga bo'lardi —
# API'ga to'g'ridan-to'g'ri murojaat qilib akkaunt ochish mumkin edi).
#
# `ZAXIRA_KIRISH=1` — FAVQULODDA eshik: admin Telegramdan ayrilib qolsa,
# `.env` ga shu o'zgaruvchi qo'yiladi va login/parol bilan kirish vaqtincha
# ochiladi. Standart holatda O'CHIQ.
FAQAT_TELEGRAM = True


def _kirish_yopiq():
    return JSONResponse({"xato": "Kirish faqat Telegram orqali amalga oshiriladi"},
                        status_code=404)


def _zaxira_kirish() -> bool:
    return os.environ.get("ZAXIRA_KIRISH", "").strip() == "1"


@app.get("/api/konfig")
def konfig(request: Request):
    u = _joriy(request)
    javob = {"dev": auth.dev_rejim(), "bot": tg.bot_username(),
             "email_kirish": not FAQAT_TELEGRAM,
             "zaxira_kirish": _zaxira_kirish(),
             "tasdiq_shart": auth.tasdiq_shart(),
             "twinlar": [{"id": t["id"], "nom": t["nom"], "slug": t["slug"],
                          "tavsif": t["tavsif"], "kategoriya": t["kategoriya"],
                          "avatar": bool(t.get("avatar")),
                          "bolak_soni": t["bolak_soni"]} for t in db.twinlar()],
             "user": _user_json(u) if u else None}
    if u:
        javob["pul"] = pul.holat(u["id"])
        javob["tanishuv_kerak"] = profil.kerakmi(u)
    return javob


# ---------------------------------------------------------------- tanishuv testi

@app.get("/api/tanishuv")
def tanishuv_ol(request: Request):
    """Savollar + oldingi javoblar (qayta topshirish uchun)."""
    u = _joriy(request)
    if not u:
        return _401()
    hozirgi = profil.tuzilgan(u)
    return {"savollar": tanishuv.savollar_royxati(hozirgi, hammasi=True),
            "javoblar": {k: v for k, v in hozirgi.items()
                         if k not in ("tugallangan", "otkazildi", "vaqt")},
            "kerak": profil.kerakmi(u)}


class TanishuvJavob(BaseModel):
    javoblar: dict


@app.post("/api/tanishuv")
def tanishuv_saqla(s: TanishuvJavob, request: Request):
    """Javoblarni saqlaydi. Faqat oldindan ma'lum kodlar qabul qilinadi."""
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("tanishuv", str(u["id"])):
        return _429()
    p = profil.tanishuv_saqla(u["id"], s.javoblar or {})
    return {"ok": True, "profil": p, "tavsif": tanishuv.matn_yasa(p)}


@app.post("/api/tanishuv/otkaz")
def tanishuv_otkaz(request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    profil.otkaz(u["id"])
    return {"ok": True}


@app.post("/api/kirish/telegram")
async def kirish_telegram(request: Request):
    if not cheklov.ruxsat("kirish_tg", cheklov.ip(request)):
        return _429()
    data = await request.json()
    tgu = auth.widget_tekshir(data if isinstance(data, dict) else {})
    if not tgu:
        return JSONResponse({"xato": "imzo noto'g'ri"}, status_code=403)
    return _kirish_javobi(db.user_tg(tgu))


class WebAppKirish(BaseModel):
    init_data: str


@app.post("/api/kirish/webapp")
def kirish_webapp(s: WebAppKirish, request: Request):
    if not cheklov.ruxsat("kirish_tg", cheklov.ip(request)):
        return _429()
    tgu = auth.webapp_tekshir(s.init_data)
    if not tgu:
        return JSONResponse({"xato": "imzo noto'g'ri"}, status_code=403)
    return _kirish_javobi(db.user_tg(tgu))


# ---------------------------------------------------------------- email akkaunt

class Royxat(BaseModel):
    email: str
    parol: str
    ism: str = ""


def _tasdiq_yubor(u: dict) -> bool:
    token = db.token_yasa(u["id"], "tasdiq", auth.TASDIQ_SOAT)
    havola = f"{auth.public_url() or ''}/tasdiq?token={token}"
    if not auth.public_url():
        log(f"TASDIQ HAVOLASI (PUBLIC_URL yo'q): /tasdiq?token={token}")
    return pochta.tasdiq_xati(u["email"], u["ism"], havola, auth.TASDIQ_SOAT)


@app.post("/api/kirish/royxat")
def kirish_royxat(s: Royxat, request: Request):
    """Web orqali ro'yxatdan o'tish (email + parol) — YOPIQ, qarang FAQAT_TELEGRAM."""
    if FAQAT_TELEGRAM:
        return _kirish_yopiq()
    if not cheklov.ruxsat("royxat", cheklov.ip(request)):
        return _429("Juda ko'p urinish — keyinroq qayta urining")
    email = s.email.strip().lower()
    if not auth.email_tugri(email):
        return JSONResponse({"xato": "Email manzili noto'g'ri"}, status_code=400)
    xato = auth.parol_kuchi(s.parol)
    if xato:
        return JSONResponse({"xato": xato}, status_code=400)

    mavjud = db.user_email_ol(email)
    if mavjud:
        # Akkaunt bor-yo'qligini OSHKOR QILMAYMIZ (email ro'yxatini yig'ish
        # mumkin bo'lmasin) — javob bir xil, tasdiqlanmagan bo'lsa xat qayta
        # yuboriladi.
        if not mavjud["email_tasdiq"]:
            _tasdiq_yubor(mavjud)
        return {"ok": True, "holat": "tasdiq_kutilmoqda", "email": email}

    tasdiq_kerak = auth.tasdiq_shart()
    u = db.user_email_yasa(email, auth.parol_hash(s.parol), s.ism,
                           tasdiq=not tasdiq_kerak)
    if tasdiq_kerak:
        if not _tasdiq_yubor(u):
            monitoring.xato("Tasdiq xati yuborilmadi",
                            f"user={u['id']} pochta usuli={pochta.usul()!r}",
                            kalit="pochta")
        return {"ok": True, "holat": "tasdiq_kutilmoqda", "email": email}
    log(f"Yangi web akkaunt (tasdiqsiz rejim): {email}")
    return _kirish_javobi(u)


class EmailKirish(BaseModel):
    email: str
    parol: str


@app.post("/api/kirish/email")
def kirish_email(s: EmailKirish, request: Request):
    if FAQAT_TELEGRAM:
        return _kirish_yopiq()
    kalit = f"{cheklov.ip(request)}|{s.email.strip().lower()[:80]}"
    if not cheklov.ruxsat("kirish_parol", kalit):
        monitoring.xato("Parol brute-force shubhasi",
                        f"email={s.email[:80]} ip={cheklov.ip(request)}",
                        kalit=f"brute:{kalit}")
        return _429("Juda ko'p urinish — 5 daqiqadan keyin qayta urining")
    u = auth.parol_bilan_email(s.email, s.parol)
    if not u:
        return JSONResponse({"xato": "Email yoki parol noto'g'ri"},
                            status_code=403)
    if not u["email_tasdiq"] and auth.tasdiq_shart():
        return JSONResponse({"xato": "Email hali tasdiqlanmagan",
                             "holat": "tasdiq_kutilmoqda"}, status_code=403)
    db.user_yangila(u["id"])
    return _kirish_javobi(u)


class TasdiqQayta(BaseModel):
    email: str


@app.post("/api/kirish/tasdiq-qayta")
def tasdiq_qayta(s: TasdiqQayta, request: Request):
    """Tasdiq xatini qayta yuborish. Javob har doim bir xil (oshkor qilmaydi)."""
    if FAQAT_TELEGRAM:
        return _kirish_yopiq()
    if not cheklov.ruxsat("royxat", cheklov.ip(request)):
        return _429()
    u = db.user_email_ol(s.email)
    if u and not u["email_tasdiq"]:
        _tasdiq_yubor(u)
    return {"ok": True}


@app.get("/tasdiq")
def tasdiq_sahifa(token: str = ""):
    """Xatdagi havola. Tasdiqlansa — darhol kirgan holda bosh sahifaga."""
    u = db.token_ishlat(token, "tasdiq") if token else None
    if not u:
        return FileResponse(WEB / "index.html", media_type="text/html",
                            headers={"Cache-Control": "no-cache"})
    db.email_tasdiqla(u["id"])
    r = Response(status_code=303, headers={"Location": "/?tasdiq=ok"})
    r.set_cookie(COOKIE, db.sessiya_yasa(u["id"]),
                 max_age=db.SESSIYA_KUN * 86400, httponly=True, samesite="lax")
    return r


class Tiklash(BaseModel):
    email: str


@app.post("/api/kirish/tiklash")
def parol_tiklash(s: Tiklash, request: Request):
    """Parolni tiklash xatini yuboradi. Javob akkaunt bor-yo'qligini aytmaydi."""
    if FAQAT_TELEGRAM:
        return _kirish_yopiq()
    if not cheklov.ruxsat("tiklash", cheklov.ip(request)):
        return _429()
    u = db.user_email_ol(s.email)
    if u:
        token = db.token_yasa(u["id"], "tiklash", auth.TIKLASH_SOAT)
        havola = f"{auth.public_url() or ''}/tiklash?token={token}"
        if not auth.public_url():
            log(f"TIKLASH HAVOLASI (PUBLIC_URL yo'q): /tiklash?token={token}")
        pochta.tiklash_xati(u["email"], u["ism"], havola, auth.TIKLASH_SOAT)
    return {"ok": True}


class ParolYangi(BaseModel):
    token: str
    parol: str


@app.post("/api/kirish/parol-yangi")
def parol_yangi(s: ParolYangi, request: Request):
    if FAQAT_TELEGRAM:
        return _kirish_yopiq()
    if not cheklov.ruxsat("tiklash", cheklov.ip(request)):
        return _429()
    xato = auth.parol_kuchi(s.parol)
    if xato:
        return JSONResponse({"xato": xato}, status_code=400)
    u = db.token_ishlat(s.token, "tiklash")
    if not u:
        return JSONResponse({"xato": "Havola eskirgan yoki allaqachon "
                                     "ishlatilgan"}, status_code=400)
    db.parol_yangila(u["id"], auth.parol_hash(s.parol))
    db.email_tasdiqla(u["id"])     # tiklash havolasi ham egalikni isbotlaydi
    pg.bajar("DELETE FROM sessiyalar WHERE user_id=%s", u["id"])   # eski seanslar
    return _kirish_javobi(db.user_ol(u["id"]))


@app.get("/tiklash")
def tiklash_sahifa():
    return FileResponse(WEB / "index.html", media_type="text/html",
                        headers={"Cache-Control": "no-cache"})


@app.post("/api/telegram/bogla")
async def telegram_bogla(request: Request):
    """Kirgan foydalanuvchi akkauntiga Telegramni bog'laydi (ixtiyoriy)."""
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("kirish_tg", cheklov.ip(request)):
        return _429()
    data = await request.json()
    tgu = auth.widget_tekshir(data if isinstance(data, dict) else {})
    if not tgu:
        return JSONResponse({"xato": "imzo noto'g'ri"}, status_code=403)
    if not db.tg_bogla(u["id"], tgu):
        return JSONResponse(
            {"xato": "Bu Telegram allaqachon boshqa akkauntga bog'langan"},
            status_code=409)
    return {"ok": True, "user": _user_json(db.user_ol(u["id"]))}


class ParolKirish(BaseModel):
    login: str
    parol: str


@app.post("/api/kirish/parol")
def kirish_parol(s: ParolKirish, request: Request):
    """FAVQULODDA eshik: egasi/admin login+parol bilan.

    Odatda YOPIQ — kirish faqat Telegram orqali (qarang FAQAT_TELEGRAM).
    Admin Telegramdan ayrilib qolsa, `.env` ga `ZAXIRA_KIRISH=1` qo'yiladi,
    konteyner qayta ishga tushiriladi va shu yo'l vaqtincha ochiladi.
    """
    if FAQAT_TELEGRAM and not _zaxira_kirish():
        return _kirish_yopiq()
    # Brute-force to'sig'i: IP va login bo'yicha alohida hisoblanadi
    kalit = f"{cheklov.ip(request)}|{(s.login or '').strip().lower()[:60]}"
    if not cheklov.ruxsat("kirish_parol", kalit):
        monitoring.xato("Parol brute-force shubhasi",
                        f"login={s.login[:60]} ip={cheklov.ip(request)}",
                        kalit=f"brute:{kalit}")
        return _429("Juda ko'p urinish — 5 daqiqadan keyin qayta urining")
    u = auth.parol_tekshir(s.login, s.parol)
    if not u or u["rol"] not in ("egasi", "admin"):
        return JSONResponse({"xato": "login yoki parol noto'g'ri"}, status_code=403)
    db.user_yangila(u["id"])   # oxirgi kirish
    return _kirish_javobi(u)


class DevKirish(BaseModel):
    ism: str


@app.post("/api/kirish/dev")
def kirish_dev(s: DevKirish, request: Request):
    """Faqat bot sozlanmagan paytda (lokal sinov). Prodda 403."""
    if not cheklov.ruxsat("kirish_dev", cheklov.ip(request)):
        return _429()
    if not auth.dev_rejim():
        return JSONResponse({"xato": "dev-rejim o'chiq — Telegram orqali kiring"},
                            status_code=403)
    ism = s.ism.strip()[:60] or "Mehmon"
    login = f"dev_{ism.lower()}"
    u = db.user_login_ol(login)
    if not u:
        u = pg.bitta_d(
            "INSERT INTO userlar(ism, login, rol) VALUES(%s,%s,'client') RETURNING *",
            ism, login)
    return _kirish_javobi(u)


@app.post("/api/chiqish")
def chiqish(request: Request):
    db.sessiya_ochir(request.cookies.get(COOKIE, ""))
    r = JSONResponse({"ok": True})
    r.delete_cookie(COOKIE)
    return r


# ---------------------------------------------------------------- twin tanlash

class TwinTanlov(BaseModel):
    twin_id: int


@app.post("/api/twin")
def twin_tanla(s: TwinTanlov, request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    t = db.twin_ol(s.twin_id)
    if not t or not t["faol"]:
        return _404()
    db.user_yangila(u["id"], joriy_twin=s.twin_id)
    return {"ok": True, "twin": {"id": t["id"], "nom": t["nom"]}}


@app.get("/api/twin/{tid}/avatar")
def twin_avatar(tid: int):
    """Ustoz surati. Ataylab OCHIQ: u mahsulotning yuzi, sir emas, va kirish
    ekranida ham ko'rsatiladi. `twinlar.avatar` — S3 kaliti."""
    t = db.twin_ol(tid)
    if not t or not t["faol"] or not t.get("avatar"):
        return _404()
    try:
        tarkib = storage.ol(t["avatar"])
    except Exception:
        return _404()
    tur = "image/png" if t["avatar"].lower().endswith(".png") else "image/jpeg"
    return Response(tarkib, media_type=tur,
                    headers={"Cache-Control": "public, max-age=86400"})


# ---------------------------------------------------------------- suhbatlar

@app.get("/api/suhbatlar")
def suhbatlar(request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    return db.suhbatlar(u["id"])


@app.get("/api/suhbat/{sid}")
def suhbat_majlislari(sid: int, request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    if db.suhbat_egasi(sid) != u["id"]:
        return _404()
    return db.suhbat_majlislari(u["id"], sid)


class SuhbatYangi(BaseModel):
    sarlavha: str


@app.put("/api/suhbat/{sid}")
def suhbat_nomla(sid: int, s: SuhbatYangi, request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    if db.suhbat_egasi(sid) != u["id"]:
        return _404()
    nom = s.sarlavha.strip()[:80]
    if not nom:
        return JSONResponse({"xato": "sarlavha bo'sh"}, status_code=400)
    db.suhbat_sarlavha(sid, nom)
    return {"ok": True, "sarlavha": nom}


@app.delete("/api/suhbat/{sid}")
def suhbat_ochir(sid: int, request: Request, butunlay: bool = False):
    """Standart — arxivga (qaytarish mumkin); ?butunlay=1 — butunlay o'chiradi."""
    u = _joriy(request)
    if not u:
        return _401()
    ok = (db.suhbat_ochir(sid, u["id"]) if butunlay
          else db.suhbat_arxiv(sid, u["id"], True))
    return {"ok": True} if ok else _404()


@app.get("/api/majlis/{mid}")
def majlis_ol(mid: int, request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    m = db.majlis_ol(mid, u["id"])
    if not m:
        return _404()
    return m


@app.get("/api/majlis/{mid}/fayl")
def majlis_fayl(mid: int, request: Request):
    """Majlisga biriktirilgan tayyor fayl (S3 dan, faqat egasiga)."""
    u = _joriy(request)
    if not u:
        return _401()
    m = db.majlis_ol(mid, u["id"])
    if not m or not m["biriktirma"]:
        return _404()
    from . import storage
    try:
        oqim, tur, _ = storage.ol_oqim(m["biriktirma"])
    except Exception:
        return _404()
    nom = m["biriktirma"].split("/")[-1]
    return Response(oqim.read(), media_type=tur,
                    headers={"Content-Disposition": f'attachment; filename="{nom}"'})


# ---------------------------------------------------------------- fragment (aynan manba)

def _bolak_ruxsat(u: dict, bolak: dict) -> bool:
    """Bo'lak shu foydalanuvchiga ko'rsatilishi mumkinmi.

    Klient uchun chegara — joriy twinning ruxsat matritsasi (majlisda ham
    aynan shu chegaradan qidirilgan). Egasi/admin o'z twinini ko'radi.
    """
    if auth.admin_mi(u):
        return True
    t = db.twin_ol(bolak["twin_id"])
    if t and t.get("egasi_id") == u["id"]:
        return True
    joriy = _twin_tanla(u)
    return bool(joriy) and bolak["twin_id"] in db.ruxsat_royxat(joriy)


def _bolak_ol(bid: int, request: Request):
    """(bolak, xato_javobi) — tekshiruvlar bitta joyda."""
    u = _joriy(request)
    if not u:
        return None, _401()
    b = db.bolak_ol(bid)
    if not b:
        return None, _404()
    if not _bolak_ruxsat(u, b):
        return None, JSONResponse({"xato": "ruxsat yo'q"}, status_code=403)
    return b, None


@app.get("/api/bolak/{bid}")
def bolak_ol(bid: int, request: Request):
    """Bo'lak matni + qanday fragment mavjudligi (audio kesmasi / sahifa surati)."""
    b, xato = _bolak_ol(bid, request)
    if xato:
        return xato
    return {"id": b["id"], "matn": b["matn"], "joy": b["joy"],
            "manba": b["manba"], "tur": b["tur"], "papka": b["papka"],
            "twin": b["twin_nom"], "manba_url": b["manba_url"],
            "fragment": fragment.holat(b)}


@app.post("/api/bolak/{bid}/fragment")
def bolak_fragment(bid: int, request: Request):
    """Audio kesmasini tayyorlashni buyuradi (tayyor bo'lsa — darhol 'tayyor')."""
    b, xato = _bolak_ol(bid, request)
    if xato:
        return xato
    h = fragment.holat(b)
    if not h["audio"]:
        return JSONResponse({"xato": "bu bo'lakda audio yo'q"}, status_code=400)
    fr = db.fragment_ol(bid, "audio")
    if fr and fr["holat"] == "tayyor":
        return {"holat": "tayyor"}
    bor = pg.bitta(
        """SELECT id FROM jobs WHERE tur='fragment' AND holat IN ('navbatda','ketmoqda')
           AND (kirish->>'bolak_id')::bigint = %s LIMIT 1""", bid)
    if bor:
        return {"holat": "ketmoqda", "job_id": bor[0]}
    u = _joriy(request)
    jid = jobs.qoshish("fragment", {"bolak_id": bid}, user_id=u["id"],
                       twin_id=b["twin_id"], ustunlik=2, muhlat_s=600)
    return {"holat": "navbatda", "job_id": jid}


def _oqim_javobi(yol: str, request: Request, mime: str, nom: str):
    """S3 dagi faylni qaytaradi; audio uchun Range (pleerda oldinga surish) qo'llanadi."""
    from . import storage
    try:
        tarkib = storage.ol(yol)
    except Exception:
        return _404()
    jami = len(tarkib)
    bosh_h = {"Content-Disposition": f'inline; filename="{nom}"',
              "Accept-Ranges": "bytes", "Cache-Control": "private, max-age=86400"}
    oraliq = request.headers.get("range", "")
    m = re.match(r"bytes=(\d+)-(\d*)", oraliq)
    if m:
        b1 = int(m.group(1))
        b2 = int(m.group(2)) if m.group(2) else jami - 1
        b2 = min(b2, jami - 1)
        if b1 > b2:
            return Response(status_code=416)
        return Response(tarkib[b1:b2 + 1], status_code=206, media_type=mime,
                        headers={**bosh_h, "Content-Range": f"bytes {b1}-{b2}/{jami}"})
    return Response(tarkib, media_type=mime, headers=bosh_h)


@app.get("/api/bolak/{bid}/audio")
def bolak_audio(bid: int, request: Request):
    b, xato = _bolak_ol(bid, request)
    if xato:
        return xato
    fr = db.fragment_ol(bid, "audio")
    if not fr or fr["holat"] != "tayyor":
        return JSONResponse({"xato": "fragment hali tayyor emas"}, status_code=404)
    return _oqim_javobi(fr["s3_yol"], request, "audio/mpeg", f"fragment_{bid}.mp3")


@app.get("/api/bolak/{bid}/rasm")
def bolak_rasm(bid: int, request: Request):
    b, xato = _bolak_ol(bid, request)
    if xato:
        return xato
    if not b.get("sahifa_png"):
        return _404()
    return _oqim_javobi(b["sahifa_png"], request, "image/jpeg", f"sahifa_{bid}.jpg")


@app.post("/api/bolak/{bid}/tg")
def bolak_tg(bid: int, request: Request):
    """Fragmentni foydalanuvchining Telegramiga yuborish (worker bajaradi)."""
    b, xato = _bolak_ol(bid, request)
    if xato:
        return xato
    u = _joriy(request)
    if not cheklov.ruxsat("tg_yubor", str(u["id"])):
        return _429()
    if not u.get("tg_id"):
        return JSONResponse({"xato": "Telegram akkaunt bog'lanmagan"}, status_code=400)
    jid = jobs.qoshish("tg_fragment",
                       {"bolak_id": bid, "izoh": f"{b['manba']} — {b['joy']}"},
                       user_id=u["id"], twin_id=b["twin_id"], ustunlik=3,
                       muhlat_s=900)
    return {"ok": True, "job_id": jid}


# ---------------------------------------------------------------- chat (yordamchi)

class ChatSorov(BaseModel):
    savol: str
    suhbat: int | None = None
    twin_id: int | None = None
    qayta_id: int | None = None       # shu javobni qayta yaratish


def _sse(hodisa: dict) -> bytes:
    """Bitta SSE ramkasi. json.dumps yangi qator chiqarmaydi — ramka buzilmaydi."""
    return f"data: {json.dumps(hodisa, ensure_ascii=False)}\n\n".encode()


@app.post("/api/chat")
def chat(s: ChatSorov, request: Request):
    """Chat javobi — token-token oqim (SSE).

    Kvota/xato javoblari oqim BOSHLANMASDAN oldin oddiy JSON bo'lib qaytadi,
    shunda klient 402 ni odatdagidek ushlaydi.
    """
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("boshla", str(u["id"])):
        return _429()
    savol = s.savol.strip()
    if not savol:
        return JSONResponse({"xato": "Savol bo'sh"}, status_code=400)
    if len(savol) > 4000:
        return JSONResponse({"xato": "Savol juda uzun (4000 belgi chegara)"},
                            status_code=400)

    # --- suhbat turi: dars (mavzu_id), maqsad sikli (maqsad_id), biznes
    #     tizimlashtirish (tizim_maqsad_id) yoki oddiy chat
    sid = s.suhbat
    mavzu = maqsad_q = tizim_q = None
    if sid is not None:
        sq = db.suhbat_ol(sid)
        if not sq or sq["user_id"] != u["id"]:
            return _404()
        if sq.get("mavzu_id"):
            mavzu = oquv.mavzu_ol(sq["mavzu_id"])
        elif sq.get("maqsad_id"):
            maqsad_q = maqsad.ol(sq["maqsad_id"], u["id"])
        elif sq.get("tizim_maqsad_id"):
            tizim_q = tizim.maqsad_ol(sq["tizim_maqsad_id"], u["id"])

    twin_id = ((mavzu["twin_id"] if mavzu else None)
               or (maqsad_q["twin_id"] if maqsad_q else None)
               or (tizim_q["twin_id"] if tizim_q else None)
               or s.twin_id or _twin_tanla(u))
    if not twin_id:
        return JSONResponse({"xato": "Faol ustoz topilmadi"}, status_code=400)
    twin = db.twin_ol(twin_id)
    if not twin or not twin["faol"]:
        return _404()

    # --- kvota darvozasi (faqat SQL; model javobi bu qarorga ta'sir qilmaydi)
    ruxsat, kod, xabar = pul.tekshir(u["id"], twin_id)
    bepul = False
    if ruxsat and kod == "bepul":
        bepul = pul.bepul_band(u["id"])
        if not bepul:
            ruxsat, kod, xabar = pul.tekshir(u["id"], twin_id)
    if not ruxsat:
        return JSONResponse({"ok": False, "holat": "kvota", "kod": kod,
                             "xabar": xabar, "pul": pul.holat(u["id"])},
                            status_code=402)

    # --- qayta yaratish: eski javob o'chadi, savol o'sha bo'ladi
    if s.qayta_id:
        eski = db.majlis_ol(s.qayta_id, u["id"])
        if not eski:
            return _404()
        sid = eski["suhbat_id"]
        savol = eski["savol"]
        # Darsning/maqsadning birinchi xabari foydalanuvchi matni emas — belgi
        # bilan qayta boshlanadi, aks holda u savol bo'lib ketardi.
        if mavzu and savol == mentor.BOSHLASH_MATN:
            savol = mentor.BOSHLASH
        if maqsad_q and savol == maqsad_oqim.BOSHLASH_MATN:
            savol = maqsad_oqim.BOSHLASH
        if tizim_q and savol == tizim_oqim.BOSHLASH_MATN:
            savol = tizim_oqim.BOSHLASH
        db.chat_ochir(s.qayta_id)

    if sid is None:
        sid = db.suhbat_yasa(u["id"], twin_id, savol)

    if mavzu:
        hodisalar, toxtat = mentor.oqim_navbat(u, twin, mavzu, savol, sid,
                                               bepul=bepul)
    elif maqsad_q:
        hodisalar, toxtat = maqsad_oqim.oqim_navbat(u, twin, maqsad_q, savol,
                                                    sid, bepul=bepul)
    elif tizim_q:
        hodisalar, toxtat = tizim_oqim.oqim_navbat(u, twin, tizim_q, savol,
                                                   sid, bepul=bepul)
    else:
        hodisalar, toxtat = yordamchi.oqim_navbat(u, twin, savol, sid,
                                                  bepul=bepul)

    def chiqish():
        yiqildi = False
        try:
            for h in hodisalar:
                if h.get("tur") == "xato":
                    yiqildi = True
                yield _sse(h)
        except GeneratorExit:
            # Klient uzildi ("To'xtat" tugmasi ham shu yo'l bilan keladi) —
            # modelni bekorga ishlatib turmaymiz.
            toxtat.set()
            raise
        finally:
            if yiqildi and bepul:
                pul.bepul_qaytar(u["id"])   # foydalanuvchi aybdor emas

    return StreamingResponse(
        chiqish(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform",
                 "X-Accel-Buffering": "no", "Connection": "keep-alive"})


# ---------------------------------------------------------------- mentor (o'quv reja)
# Bu yuzada LLM YO'Q: diagnostika, mini-test va mavzu holatlari — hammasi
# `oquv.py` dagi SQL qoidalari. Faqat dars matni va vazifa moslashtirish
# modelga boradi, ular esa hech qanday o'quv qarorini o'zgartirmaydi.


def _mentor_twin(u: dict, twin_id: int | None):
    """(twin, xato_javobi) — mentor endpointlari uchun yagona tekshiruv."""
    tid = twin_id or _twin_tanla(u)
    if not tid:
        return None, JSONResponse({"xato": "Faol ustoz topilmadi"},
                                  status_code=400)
    t = db.twin_ol(tid)
    if not t or not t["faol"]:
        return None, _404()
    return t, None


def _mavzu_ruxsat(u: dict, mavzu_id: int):
    """(mavzu, xato) — mavzu faol kursniki va o'quvchiga ochiqmi."""
    m = oquv.mavzu_ol(mavzu_id)
    if not m or not m["faol"] or m["kurs_holat"] != "faol":
        return None, _404()
    reja = oquv.reja_ol(u["id"], m["twin_id"])
    if not reja or reja["kurs_id"] != m["kurs_id"]:
        return None, JSONResponse({"xato": "Avval o'quv rejani boshlang"},
                                  status_code=409)
    holat = (oquv.holatlar(u["id"], m["kurs_id"]).get(mavzu_id) or {})
    if holat.get("holat", "kutmoqda") == "kutmoqda":
        return None, JSONResponse(
            {"xato": "Bu mavzu hali ochilmagan — oldingi mavzularni tugating"},
            status_code=409)
    m["oquv_holat"] = holat.get("holat")
    return m, None


@app.get("/api/mentor")
def mentor_manzara(request: Request, twin_id: int = 0):
    """Mentor bo'limining butun holati — bitta so'rovda."""
    u = _joriy(request)
    if not u:
        return _401()
    t, xato = _mentor_twin(u, twin_id or None)
    if xato:
        return xato
    d = oquv.manzara(u["id"], t["id"])
    d["twin"] = {"id": t["id"], "nom": t["nom"]}
    return d


@app.get("/api/mentor/diagnostika")
def diagnostika_ol(request: Request, twin_id: int = 0):
    """Boshlang'ich test savollari (to'g'ri javoblar YUBORILMAYDI)."""
    u = _joriy(request)
    if not u:
        return _401()
    t, xato = _mentor_twin(u, twin_id or None)
    if xato:
        return xato
    kurs = oquv.faol_kurs(t["id"])
    if not kurs:
        return JSONResponse({"xato": "Bu ustozda hali o'quv dasturi yo'q"},
                            status_code=404)
    return {"twin": {"id": t["id"], "nom": t["nom"]},
            "savollar": oquv.diagnostika_savollari(kurs["id"])}


class Diagnostika(BaseModel):
    twin_id: int | None = None
    javoblar: dict = {}
    otkaz: bool = False


@app.post("/api/mentor/diagnostika")
def diagnostika_saqla(s: Diagnostika, request: Request):
    """Javoblardan shaxsiy reja quriladi. `otkaz` — testsiz boshdan boshlash."""
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("mentor", str(u["id"])):
        return _429()
    t, xato = _mentor_twin(u, s.twin_id)
    if xato:
        return xato
    try:
        n = oquv.reja_yasa(u["id"], t["id"], {} if s.otkaz else s.javoblar)
    except ValueError as e:
        return JSONResponse({"xato": str(e)}, status_code=400)
    return {"ok": True, "natija": n, "manzara": oquv.manzara(u["id"], t["id"])}


class MavzuSorov(BaseModel):
    mavzu_id: int


@app.post("/api/mentor/dars")
def dars_boshla(s: MavzuSorov, request: Request):
    """Mavzu darsi uchun suhbat ochadi (bori qaytariladi)."""
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("mentor", str(u["id"])):
        return _429()
    m, xato = _mavzu_ruxsat(u, s.mavzu_id)
    if xato:
        return xato
    sid = mentor.dars_suhbati(u["id"], m["twin_id"], m)
    return {"ok": True, "suhbat_id": sid, "mavzu_id": m["id"],
            "mavzu": m["nom"], "twin_id": m["twin_id"],
            "yangi": db.suhbat_soni(sid) == 0,
            "boshlash": mentor.BOSHLASH}


@app.get("/api/mentor/test")
def test_ol(request: Request, mavzu_id: int):
    """Dars oxiridagi mini-test (to'g'ri javoblar YUBORILMAYDI)."""
    u = _joriy(request)
    if not u:
        return _401()
    m, xato = _mavzu_ruxsat(u, mavzu_id)
    if xato:
        return xato
    return {"mavzu_id": m["id"], "mavzu": m["nom"],
            "savollar": oquv.test_savollari(m["id"])}


class TestJavob(BaseModel):
    mavzu_id: int
    javoblar: dict = {}


@app.post("/api/mentor/test")
def test_topshir(s: TestJavob, request: Request):
    """Mini-test natijasi + o'tgan bo'lsa uy vazifasi."""
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("mentor", str(u["id"])):
        return _429()
    m, xato = _mavzu_ruxsat(u, s.mavzu_id)
    if xato:
        return xato
    natija = oquv.test_tekshir(m["id"], s.javoblar)
    javob = {"ok": True, "natija": natija, "vazifa": None, "holat": m["oquv_holat"]}
    if not natija["otdi"]:
        return javob

    twin = db.twin_ol(m["twin_id"]) or {}
    oquv.holat_yoz(u["id"], m["id"], m["oquv_holat"] or "joriy",
                   test_natija={"togri": natija["togri"], "jami": natija["jami"]})
    v = vazifa.ber(u["id"], twin, m)
    if v:
        javob["vazifa"] = _vazifa_json(v)
        javob["holat"] = "vazifada"
    else:
        # Bu mavzuda vazifa shabloni yo'q — test o'tgani mavzuni yopadi.
        oquv.holat_yoz(u["id"], m["id"], "tugallangan")
        oquv.keyingi_ochi(u["id"], m["kurs_id"])
        javob["holat"] = "tugallangan"
    javob["manzara"] = oquv.manzara(u["id"], m["twin_id"])
    return javob


# ---------------------------------------------------------------- uy vazifalari

def _vazifa_json(v: dict) -> dict:
    """Vazifa qatorini klient ko'radigan shaklga keltiradi."""
    return {"id": v["id"], "mavzu_id": v["mavzu_id"],
            "mavzu": v.get("mavzu"), "topshiriq": v["topshiriq"],
            "rubrika": v["rubrika"], "muddat": v["muddat"],
            "holat": v["holat"], "urinish": v["urinish"],
            "maks_urinish": vazifa.MAKS_URINISH, "otish_ball": vazifa.OTISH_BALL,
            "javob": v["javob"], "baho": v["baho"],
            "tekshiruv": v["tekshiruv"] or {},
            "qayta_mumkin": vazifa.qayta_topshirish_mumkinmi(v),
            "topshirilgan": v.get("topshirilgan"),
            "tekshirilgan": v.get("tekshirilgan")}


@app.get("/api/vazifalar")
def vazifalar_royxat(request: Request, twin_id: int = 0):
    u = _joriy(request)
    if not u:
        return _401()
    return vazifa.royxat(u["id"], twin_id or None)


@app.get("/api/vazifa/{vid}")
def vazifa_ol(vid: int, request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    v = vazifa.ol(vid, u["id"])
    return _vazifa_json(v) if v else _404()


class VazifaJavob(BaseModel):
    javob: str


@app.post("/api/vazifa/{vid}/topshir")
def vazifa_topshir(vid: int, s: VazifaJavob, request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("vazifa", str(u["id"])):
        return _429("Juda ko'p urinish — biroz kuting")
    try:
        n = vazifa.topshir(vid, u["id"], s.javob)
    except ValueError as e:
        return JSONResponse({"xato": str(e)}, status_code=400)
    return n


# ---------------------------------------------------------------- maqsad halqasi
# Bu yuzada model HOLATNI o'zgartirmaydi: intervyudan rejaga o'tish, qadam
# yopilishi, foiz va sikl yakuni — hammasi `maqsad.py` dagi SQL qoidalari.
# Model faqat kontent yozadi (savol, reja matni, xulosa, prognoz).


def _maqsad_yuza(u: dict, twin_id: int | None):
    """(twin, xato) — maqsad endpointlari uchun yagona tekshiruv.

    Twin egasi rejimni o'chirgan bo'lsa bo'lim umuman ochilmaydi.
    """
    t, xato = _mentor_twin(u, twin_id)
    if xato:
        return None, xato
    if not skilllar.faolmi(t["id"], "maqsad"):
        return None, JSONResponse(
            {"xato": "Bu ustozda maqsad rejimi yoqilmagan", "yoq": True},
            status_code=404)
    return t, None


def _maqsad_ol(u: dict, mid: int):
    """(maqsad, xato) — egalik tekshiruvi bilan."""
    m = maqsad.ol(mid, u["id"])
    return (m, None) if m else (None, _404())


def _qadam_ol(u: dict, qid: int):
    q = maqsad.qadam_ol(qid)
    if not q or q["user_id"] != u["id"]:
        return None, _404()
    return q, None


def _fokus_javobi(e: maqsad.Fokus):
    """409: fokus qoidasi. Joriy maqsad ham beriladi — UI unga yo'naltiradi."""
    m = e.maqsad or {}
    return JSONResponse(
        {"xato": str(e), "kod": "fokus",
         "maqsad": {"id": m.get("id"), "sarlavha": m.get("sarlavha"),
                    "holat": m.get("holat")}}, status_code=409)


@app.get("/api/maqsad")
def maqsad_manzara(request: Request, twin_id: int = 0):
    """Maqsad bo'limining butun holati — bitta so'rovda."""
    u = _joriy(request)
    if not u:
        return _401()
    t, xato = _maqsad_yuza(u, twin_id or None)
    if xato:
        return xato
    d = maqsad.manzara(u["id"], t["id"])
    d["twin"] = {"id": t["id"], "nom": t["nom"]}
    return d


class MaqsadBoshla(BaseModel):
    twin_id: int | None = None
    boshlangich: str = ""


@app.post("/api/maqsad/boshla")
def maqsad_boshla(s: MaqsadBoshla, request: Request):
    """Yangi sikl. Tugallanmagan maqsad bo'lsa 409 (fokus qoidasi)."""
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("maqsad", str(u["id"])):
        return _429()
    t, xato = _maqsad_yuza(u, s.twin_id)
    if xato:
        return xato
    try:
        m = maqsad.boshla(u["id"], t["id"], s.boshlangich)
    except maqsad.Fokus as e:
        return _fokus_javobi(e)
    return {"ok": True, "maqsad_id": m["id"], "suhbat_id": m.get("suhbat_id"),
            "boshlash": maqsad_oqim.BOSHLASH}


class MaqsadId(BaseModel):
    maqsad_id: int


@app.post("/api/maqsad/suhbat")
def maqsad_suhbat(s: MaqsadId, request: Request):
    """Sikl suhbatini ochadi/qaytaradi (dars naqshi bilan bir xil)."""
    u = _joriy(request)
    if not u:
        return _401()
    m, xato = _maqsad_ol(u, s.maqsad_id)
    if xato:
        return xato
    sid = maqsad_oqim.suhbat_ol(m)
    return {"ok": True, "suhbat_id": sid, "maqsad_id": m["id"],
            "yangi": db.suhbat_soni(sid) == 0,
            "boshlash": maqsad_oqim.BOSHLASH}


@app.post("/api/maqsad/xulosa")
def maqsad_xulosa(s: MaqsadId, request: Request):
    """Intervyu suhbatidan maqsad kartasi (sxemali LLM, serverda saqlanadi)."""
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("maqsad_llm", str(u["id"])):
        return _429()
    m, xato = _maqsad_ol(u, s.maqsad_id)
    if xato:
        return xato
    if m["holat"] != "intervyu":
        return JSONResponse({"xato": "Bu maqsad allaqachon tasdiqlangan"},
                            status_code=409)
    ruxsat, kod, xabar = pul.tekshir(u["id"], m["twin_id"])
    if not ruxsat:
        return JSONResponse({"ok": False, "holat": "kvota", "kod": kod,
                             "xabar": xabar, "pul": pul.holat(u["id"])},
                            status_code=402)
    try:
        return maqsad.xulosa_yasa(m)
    except ValueError as e:
        return JSONResponse({"xato": str(e)}, status_code=400)
    except Exception as e:                                     # noqa: BLE001
        log(f"maqsad xulosasi yiqildi (user {u['id']}): {str(e)[:200]}")
        return JSONResponse(
            {"xato": "Xulosa tayyorlanmadi. Qayta urinib ko'ring."},
            status_code=500)


@app.post("/api/maqsad/tasdiqla")
def maqsad_tasdiqla(s: MaqsadId, request: Request):
    """Xulosa tasdiqlandi -> reja jobi navbatga."""
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("maqsad", str(u["id"])):
        return _429()
    m, xato = _maqsad_ol(u, s.maqsad_id)
    if xato:
        return xato
    try:
        return maqsad.tasdiqla(m)
    except ValueError as e:
        return JSONResponse({"xato": str(e)}, status_code=400)


class QadamTahrir(BaseModel):
    nom: str | None = None
    nima_uchun: str | None = None
    mezon: str | None = None
    muddat_kun: int | None = None
    tartib: int | None = None


def _qoralamadami(q: dict):
    if q["maqsad_holat"] != "reja_qoralama":
        return JSONResponse(
            {"xato": "Rejani faqat boshlashdan oldin tahrirlash mumkin"},
            status_code=409)
    return None


@app.put("/api/maqsad/qadam/{qid}")
def maqsad_qadam_tahrir(qid: int, s: QadamTahrir, request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    q, xato = _qadam_ol(u, qid)
    if xato:
        return xato
    xato = _qoralamadami(q)
    if xato:
        return xato
    maqsad.qadam_yangila(qid, **s.model_dump())
    return {"ok": True}


@app.delete("/api/maqsad/qadam/{qid}")
def maqsad_qadam_ochir(qid: int, request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    q, xato = _qadam_ol(u, qid)
    if xato:
        return xato
    xato = _qoralamadami(q)
    if xato:
        return xato
    if len(maqsad.qadamlar(q["maqsad_id"])) <= 1:
        return JSONResponse({"xato": "Rejada kamida bitta qadam qolishi kerak"},
                            status_code=400)
    maqsad.qadam_ochir(qid)
    return {"ok": True}


@app.post("/api/maqsad/reja/boshla")
def maqsad_reja_boshla(s: MaqsadId, request: Request):
    """Qoralama -> faol: birinchi qadam ochiladi."""
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("maqsad", str(u["id"])):
        return _429()
    m, xato = _maqsad_ol(u, s.maqsad_id)
    if xato:
        return xato
    try:
        n = maqsad.reja_boshla(m)
    except ValueError as e:
        return JSONResponse({"xato": str(e)}, status_code=400)
    n["manzara"] = maqsad.manzara(u["id"], m["twin_id"])
    return n


class QadamYopish(BaseModel):
    dalil: str = ""
    sabab: str = ""


@app.post("/api/maqsad/qadam/{qid}/bajarildi")
def maqsad_qadam_bajarildi(qid: int, s: QadamYopish, request: Request):
    """Qadam yopiladi va keyingisi ochiladi — qaror faqat serverda."""
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("maqsad", str(u["id"])):
        return _429()
    q, xato = _qadam_ol(u, qid)
    if xato:
        return xato
    try:
        n = maqsad.qadam_bajarildi(q, s.dalil)
    except ValueError as e:
        return JSONResponse({"xato": str(e)}, status_code=400)
    n["manzara"] = maqsad.manzara(u["id"], q["twin_id"])
    return n


@app.post("/api/maqsad/qadam/{qid}/otkaz")
def maqsad_qadam_otkaz(qid: int, s: QadamYopish, request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("maqsad", str(u["id"])):
        return _429()
    q, xato = _qadam_ol(u, qid)
    if xato:
        return xato
    try:
        n = maqsad.qadam_otkaz(q, s.sabab)
    except ValueError as e:
        return JSONResponse({"xato": str(e)}, status_code=400)
    n["manzara"] = maqsad.manzara(u["id"], q["twin_id"])
    return n


class IshBelgi(BaseModel):
    bajarildi: bool = True


def _ish_ol(u: dict, ish_id: int):
    i = maqsad.ish_ol(ish_id)
    if not i or i["user_id"] != u["id"]:
        return None, _404()
    return i, None


@app.post("/api/maqsad/ish/{ish_id}")
def maqsad_ish_belgi(ish_id: int, s: IshBelgi, request: Request):
    """Qadam ichidagi aniq ishni belgilash — faqat foydalanuvchi qiladi."""
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("maqsad", str(u["id"])):
        return _429()
    i, xato = _ish_ol(u, ish_id)
    if xato:
        return xato
    try:
        n = maqsad.ish_belgi(i, s.bajarildi)
    except ValueError as e:
        return JSONResponse({"xato": str(e)}, status_code=400)
    n["manzara"] = maqsad.manzara(u["id"], i["twin_id"])
    return n


class IshQosh(BaseModel):
    matn: str


@app.post("/api/maqsad/qadam/{qid}/ish")
def maqsad_ish_qosh(qid: int, s: IshQosh, request: Request):
    """Foydalanuvchi o'z ishini qo'shadi (rejasi o'ziniki)."""
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("maqsad", str(u["id"])):
        return _429()
    q, xato = _qadam_ol(u, qid)
    if xato:
        return xato
    try:
        ish = maqsad.ish_qosh(q, s.matn)
    except ValueError as e:
        return JSONResponse({"xato": str(e)}, status_code=400)
    return {"ok": True, "ish": ish,
            "manzara": maqsad.manzara(u["id"], q["twin_id"])}


@app.delete("/api/maqsad/ish/{ish_id}")
def maqsad_ish_ochir(ish_id: int, request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    i, xato = _ish_ol(u, ish_id)
    if xato:
        return xato
    try:
        maqsad.ish_ochir(i)
    except ValueError as e:
        return JSONResponse({"xato": str(e)}, status_code=400)
    return {"ok": True, "manzara": maqsad.manzara(u["id"], i["twin_id"])}


class MaqsadTanlov(BaseModel):
    twin_id: int | None = None
    maqsad_id: int | None = None       # qaysi siklning taklifi
    taklif: int | None = None          # taklif indeksi (0..)
    matn: str = ""                     # yoki o'z maqsadi


@app.post("/api/maqsad/tanla")
def maqsad_tanla(s: MaqsadTanlov, request: Request):
    """Prognoz taklifidan (yoki o'z matnidan) YANGI sikl boshlanadi.

    Taklif matni SERVERDAGI yakun yozuvidan olinadi — klient o'zi yozgan
    "taklif" bilan almashtira olmaydi.
    """
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("maqsad", str(u["id"])):
        return _429()
    t, xato = _maqsad_yuza(u, s.twin_id)
    if xato:
        return xato
    boshlangich = (s.matn or "").strip()[:600]
    if s.maqsad_id is not None and s.taklif is not None:
        eski, xato = _maqsad_ol(u, s.maqsad_id)
        if xato:
            return xato
        takliflar = (eski.get("yakun") or {}).get("takliflar") or []
        if not (0 <= s.taklif < len(takliflar)):
            return JSONResponse({"xato": "Bunday taklif yo'q"}, status_code=400)
        tk = takliflar[s.taklif]
        boshlangich = tk.get("taklif", "")
    if not boshlangich:
        return JSONResponse({"xato": "Maqsadni yozing yoki taklifni tanlang"},
                            status_code=400)
    try:
        m = maqsad.boshla(u["id"], t["id"], boshlangich)
    except maqsad.Fokus as e:
        return _fokus_javobi(e)
    return {"ok": True, "maqsad_id": m["id"], "suhbat_id": m.get("suhbat_id"),
            "boshlash": maqsad_oqim.BOSHLASH}


class MaqsadBekor(BaseModel):
    maqsad_id: int
    sabab: str = ""


@app.post("/api/maqsad/bekor")
def maqsad_bekor(s: MaqsadBekor, request: Request):
    """Siklni yopish — LLM'siz, bepul (fokus qoidasi qamoq emas)."""
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("maqsad", str(u["id"])):
        return _429()
    m, xato = _maqsad_ol(u, s.maqsad_id)
    if xato:
        return xato
    try:
        n = maqsad.bekor(m, s.sabab)
    except ValueError as e:
        return JSONResponse({"xato": str(e)}, status_code=400)
    n["manzara"] = maqsad.manzara(u["id"], m["twin_id"])
    return n


@app.post("/api/maqsad/qayta-tahlil")
def maqsad_qayta_tahlil(s: MaqsadId, request: Request):
    """Texnik xato bilan yopilgan siklning yakun tahlilini qayta so'rash."""
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("maqsad", str(u["id"])):
        return _429()
    m, xato = _maqsad_ol(u, s.maqsad_id)
    if xato:
        return xato
    try:
        return maqsad.qayta_tahlil(m)
    except ValueError as e:
        return JSONResponse({"xato": str(e)}, status_code=400)


# ---------------------------------------------------------------- tizimlashtirish halqasi (biznes)

def _tizim_yuza(u: dict, twin_id: int | None):
    """(twin, xato) — tizim endpointlari uchun yagona tekshiruv."""
    t, xato = _mentor_twin(u, twin_id)
    if xato:
        return None, xato
    if not skilllar.faolmi(t["id"], "tizim"):
        return None, JSONResponse(
            {"xato": "Bu ustozda tizimlashtirish rejimi yoqilmagan", "yoq": True},
            status_code=404)
    return t, None


def _diag_ol(u: dict, did: int):
    d = tizim.diag_ol(did, u["id"])
    if not d:
        return None, _404()
    return d, None


def _tizim_maqsad_ol(u: dict, mid: int):
    m = tizim.maqsad_ol(mid, u["id"])
    if not m:
        return None, _404()
    return m, None


def _tizim_fokus(e: tizim.Fokus):
    y = e.yozuv or {}
    return JSONResponse(
        {"xato": str(e), "fokus": True,
         "joriy": {"id": y.get("id"), "tur": y.get("tur"),
                   "holat": y.get("holat"), "korxona": y.get("korxona")}},
        status_code=409)


@app.get("/api/tizim")
def tizim_manzara(request: Request, twin_id: int = 0):
    """Bo'limning butun holati — bitta so'rovda."""
    u = _joriy(request)
    if not u:
        return _401()
    t, xato = _tizim_yuza(u, twin_id or None)
    if xato:
        return xato
    d = tizim.manzara(u["id"], t["id"])
    d["twin"] = {"id": t["id"], "nom": t["nom"]}
    return d


@app.get("/api/tizim/savollar")
def tizim_savollar(request: Request, diagnostika_id: int):
    """Savol banki + shu diagnostikadagi javoblar (UI bitta so'rovda oladi)."""
    u = _joriy(request)
    if not u:
        return _401()
    d, xato = _diag_ol(u, diagnostika_id)
    if xato:
        return xato
    return {"diagnostika": d,
            "savollar": tizim.savollar(d["tur"], d["versiya"], d["onlayn"]),
            "javoblar": tizim.javoblar(d["id"]),
            "sifat": tizim.SIFAT,
            "olcham": tizim._olcham(d["id"])}


class DiagBoshla(BaseModel):
    twin_id: int | None = None
    tur: str
    korxona: str = ""
    onlayn: bool = False


@app.post("/api/tizim/diagnostika")
def tizim_diag_boshla(s: DiagBoshla, request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("maqsad", str(u["id"])):
        return _429()
    t, xato = _tizim_yuza(u, s.twin_id)
    if xato:
        return xato
    try:
        d = tizim.diag_boshla(u["id"], t["id"], s.tur, s.korxona, s.onlayn)
    except tizim.Fokus as e:
        return _tizim_fokus(e)
    except (ValueError, RuntimeError) as e:
        return JSONResponse({"xato": str(e)}, status_code=400)
    return {"ok": True, "diagnostika": d}


class DiagJavob(BaseModel):
    diagnostika_id: int
    savol_id: int
    javob: str
    sifat: int | None = None
    izoh: str = ""


@app.post("/api/tizim/javob")
def tizim_javob(s: DiagJavob, request: Request):
    """Bitta javob. Foiz shu yerda, SERVERDA qayta hisoblanadi."""
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("diag_javob", str(u["id"])):
        return _429()
    d, xato = _diag_ol(u, s.diagnostika_id)
    if xato:
        return xato
    try:
        olcham = tizim.javob_yoz(d, s.savol_id, s.javob, s.sifat, s.izoh)
    except ValueError as e:
        return JSONResponse({"xato": str(e)}, status_code=400)
    return {"ok": True, "olcham": olcham}


class DiagId(BaseModel):
    diagnostika_id: int


@app.post("/api/tizim/diagnostika/yakunla")
def tizim_diag_yakunla(s: DiagId, request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("maqsad", str(u["id"])):
        return _429()
    d, xato = _diag_ol(u, s.diagnostika_id)
    if xato:
        return xato
    ruxsat, kod, xabar = pul.tekshir(u["id"], d["twin_id"])
    if not ruxsat:
        return JSONResponse({"ok": False, "holat": "kvota", "kod": kod,
                             "xabar": xabar}, status_code=402)
    try:
        return tizim.diag_yakunla(d)
    except ValueError as e:
        return JSONResponse({"xato": str(e)}, status_code=400)


@app.post("/api/tizim/diagnostika/bekor")
def tizim_diag_bekor(s: DiagId, request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    d, xato = _diag_ol(u, s.diagnostika_id)
    if xato:
        return xato
    tizim.diag_bekor(d)
    return {"ok": True, "manzara": tizim.manzara(u["id"], d["twin_id"])}


class TizimMaqsadBoshla(BaseModel):
    twin_id: int | None = None
    diagnostika_id: int | None = None
    korxona: str = ""


@app.post("/api/tizim/maqsad/boshla")
def tizim_maqsad_boshla(s: TizimMaqsadBoshla, request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("maqsad", str(u["id"])):
        return _429()
    t, xato = _tizim_yuza(u, s.twin_id)
    if xato:
        return xato
    try:
        m = tizim.maqsad_boshla(u["id"], t["id"], s.diagnostika_id, s.korxona)
    except tizim.Fokus as e:
        return _tizim_fokus(e)
    return {"ok": True, "maqsad_id": m["id"],
            "boshlash": tizim_oqim.BOSHLASH}


class TizimMaqsadId(BaseModel):
    maqsad_id: int


@app.post("/api/tizim/maqsad/suhbat")
def tizim_maqsad_suhbat(s: TizimMaqsadId, request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    m, xato = _tizim_maqsad_ol(u, s.maqsad_id)
    if xato:
        return xato
    sid = tizim_oqim.suhbat_ol(m)
    return {"ok": True, "suhbat_id": sid, "maqsad_id": m["id"],
            "yangi": db.suhbat_soni(sid) == 0,
            "boshlash": tizim_oqim.BOSHLASH}


@app.post("/api/tizim/maqsad/xulosa")
def tizim_maqsad_xulosa(s: TizimMaqsadId, request: Request):
    """Suhbatdan SMART kartani ajratadi. Bahoni SERVER qo'yadi."""
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("maqsad", str(u["id"])):
        return _429()
    m, xato = _tizim_maqsad_ol(u, s.maqsad_id)
    if xato:
        return xato
    twin = db.twin_ol(m["twin_id"])
    if not twin:
        return _404()
    ruxsat, kod, xabar = pul.tekshir(u["id"], m["twin_id"])
    if not ruxsat:
        return JSONResponse({"ok": False, "holat": "kvota", "kod": kod,
                             "xabar": xabar}, status_code=402)
    try:
        yangi = tizim_oqim.karta_ol(u, twin, m)
    except ValueError as e:
        return JSONResponse({"xato": str(e)}, status_code=400)
    except Exception as e:                                     # noqa: BLE001
        log(f"tizim karta xatosi: {type(e).__name__}: {str(e)[:150]}")
        return JSONResponse({"xato": "Xulosa tayyorlanmadi, qayta urining"},
                            status_code=500)
    return {"ok": True, "maqsad": yangi}


class TizimKarta(BaseModel):
    maqsad_id: int
    tafsilot: dict = {}
    sarlavha: str = ""


@app.post("/api/tizim/maqsad/saqla")
def tizim_maqsad_saqla(s: TizimKarta, request: Request):
    """Kartani qo'lda tahrirlash — LLM'siz, bepul."""
    u = _joriy(request)
    if not u:
        return _401()
    m, xato = _tizim_maqsad_ol(u, s.maqsad_id)
    if xato:
        return xato
    try:
        return {"ok": True,
                "maqsad": tizim.maqsad_saqla(m, s.tafsilot, s.sarlavha)}
    except ValueError as e:
        return JSONResponse({"xato": str(e)}, status_code=400)


@app.post("/api/tizim/maqsad/tasdiqla")
def tizim_maqsad_tasdiqla(s: TizimMaqsadId, request: Request):
    """SMART yashil bo'lsa `faol` ga o'tkazadi va reja joblarini qo'yadi."""
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("maqsad", str(u["id"])):
        return _429()
    m, xato = _tizim_maqsad_ol(u, s.maqsad_id)
    if xato:
        return xato
    ruxsat, kod, xabar = pul.tekshir(u["id"], m["twin_id"])
    if not ruxsat:
        return JSONResponse({"ok": False, "holat": "kvota", "kod": kod,
                             "xabar": xabar}, status_code=402)
    try:
        return tizim.maqsad_tasdiqla(m)
    except ValueError as e:
        # SMART mezoni qizil — bu 409 (holat mos emas), 400 emas
        return JSONResponse({"xato": str(e), "smart": tizim.smart_bahola(m)},
                            status_code=409)


@app.post("/api/tizim/maqsad/bekor")
def tizim_maqsad_bekor(s: TizimMaqsadId, request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    m, xato = _tizim_maqsad_ol(u, s.maqsad_id)
    if xato:
        return xato
    tizim.maqsad_bekor(m)
    return {"ok": True, "manzara": tizim.manzara(u["id"], m["twin_id"])}


@app.get("/api/tizim/reja/{maqsad_id}")
def tizim_reja_royxat(maqsad_id: int, request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    m, xato = _tizim_maqsad_ol(u, maqsad_id)
    if xato:
        return xato
    return {"rejalar": tizim.reja_ol(m["id"]),
            "bolimlar": [dict(v, kod=k) for k, v in tizim.BOLIMLAR.items()]}


class RejaTahrir(BaseModel):
    qatorlar: list = []
    sarlavha: str = ""
    izoh: str = ""


@app.put("/api/tizim/reja/{rid}")
def tizim_reja_saqla(rid: int, s: RejaTahrir, request: Request):
    """Jadval tahriri. Yig'indi baribir serverda qayta hisoblanadi."""
    u = _joriy(request)
    if not u:
        return _401()
    r = tizim.reja_bitta(rid, u["id"])
    if not r:
        return _404()
    return {"ok": True, "reja": tizim.reja_saqla(r, s.qatorlar, s.sarlavha,
                                                 s.izoh)}


@app.post("/api/tizim/reja/{rid}/tasdiqla")
def tizim_reja_tasdiqla(rid: int, request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    r = tizim.reja_bitta(rid, u["id"])
    if not r:
        return _404()
    n = tizim.reja_tasdiqla(r)
    return {"ok": True, "reja": n, "rejalar": tizim.reja_ol(r["maqsad_id"])}


class RejaQayta(BaseModel):
    maqsad_id: int
    bolim: str


@app.post("/api/tizim/reja/qayta")
def tizim_reja_qayta(s: RejaQayta, request: Request):
    """Bitta bo'lim rejasini qaytadan qurish (job)."""
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("maqsad", str(u["id"])):
        return _429()
    m, xato = _tizim_maqsad_ol(u, s.maqsad_id)
    if xato:
        return xato
    if s.bolim not in tizim.BOLIMLAR:
        return JSONResponse({"xato": "noma'lum bo'lim"}, status_code=400)
    ruxsat, kod, xabar = pul.tekshir(u["id"], m["twin_id"])
    if not ruxsat:
        return JSONResponse({"ok": False, "holat": "kvota", "kod": kod,
                             "xabar": xabar}, status_code=402)
    jid = jobs.qoshish("tizim_reja", {"maqsad_id": m["id"], "bolim": s.bolim},
                       user_id=u["id"], twin_id=m["twin_id"],
                       ustunlik=3, muhlat_s=900, max_urinish=2)
    return {"ok": True, "job_id": jid}


# ---------------------------------------------------------------- chuqur tahlil (eski quvur)

class Sorov(BaseModel):
    savol: str
    hamma: bool = False
    majbur: bool = False
    suhbat: int | None = None
    twin_id: int | None = None


@app.post("/api/boshla")
def boshla(s: Sorov, request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    if not cheklov.ruxsat("boshla", str(u["id"])):
        return _429()
    savol = s.savol.strip()
    if not savol:
        return JSONResponse({"ok": False, "xabar": "Savol bo'sh"}, status_code=400)

    sid = s.suhbat
    if sid is not None and db.suhbat_egasi(sid) != u["id"]:
        return JSONResponse({"ok": False, "xabar": "Suhbat topilmadi"}, status_code=404)

    twin_id = s.twin_id or _twin_tanla(u)
    if not twin_id:
        return JSONResponse({"ok": False, "xabar": "Faol twin yo'q"}, status_code=400)
    twin = db.twin_ol(twin_id)

    if not s.majbur:
        ktx = suhbat.formatla(suhbat.kontekst(u["id"], sid)) if sid else ""
        # Aniqlik tekshiruvi ham LLM chaqiradi — xarajat userga bog'lanadi.
        pul.kontekst_boshla(user_id=u["id"], twin_id=twin_id)
        n = aniqlik.tekshir(savol, twin, u.get("profil", ""), ktx)
        if not n.get("aniq"):
            return {"ok": True, "holat": "tushunarsiz", "izoh": n.get("izoh", ""),
                    "variantlar": n.get("variantlar", [])}

    # bitta userda bitta faol majlis
    bor = pg.bitta(
        """SELECT id FROM jobs WHERE user_id=%s AND tur='majlis'
           AND holat IN ('navbatda','ketmoqda') LIMIT 1""", u["id"])
    if bor:
        return JSONResponse({"ok": False,
                             "xabar": "Majlisingiz allaqachon ketmoqda — kuting"},
                            status_code=409)

    # --- kvota darvozasi (faqat SQL; model javobi bu qarorga ta'sir qilmaydi) ---
    ruxsat, kod, xabar = pul.tekshir(u["id"], twin_id)
    bepul = False
    if ruxsat and kod == "bepul":
        bepul = pul.bepul_band(u["id"])
        if not bepul:
            # poyga: oxirgi bepul promptni parallel so'rov olib ketdi — qayta baho
            ruxsat, kod, xabar = pul.tekshir(u["id"], twin_id)
    if not ruxsat:
        return JSONResponse({"ok": False, "holat": "kvota", "kod": kod,
                             "xabar": xabar, "pul": pul.holat(u["id"])},
                            status_code=402)

    if sid is None:
        sid = db.suhbat_yasa(u["id"], twin_id, savol)

    jid = jobs.qoshish("majlis", {"savol": savol, "suhbat_id": sid,
                                  "twin_id": twin_id, "hamma": s.hamma,
                                  "bepul": bepul},
                       user_id=u["id"], twin_id=twin_id, ustunlik=1)
    return {"ok": True, "holat": "navbat",
            "job": {"id": jid, "suhbat": sid, "twin_id": twin_id, "savol": savol}}


def _job_ruxsat(u: dict, j: dict) -> bool:
    """Job holatini/jurnalini kim ko'ra oladi.

    Egasi va admin — doim. Egasiz (user_id IS NULL) tizim joblari FAQAT
    adminga: ularning jurnalida boshqa twinlarning manba nomlari bo'ladi.
    Yagona istisno — 'fragment': u bo'lak bo'yicha ulashiladi (bir bo'lakni
    ikki kishi so'rasa bitta job qaytariladi), shuning uchun bo'lak ruxsati
    bo'yicha tekshiriladi.
    """
    if auth.admin_mi(u):
        return True
    if j.get("user_id") == u["id"]:
        return True
    if j.get("tur") == "fragment":
        b = db.bolak_ol((j.get("kirish") or {}).get("bolak_id") or 0)
        return bool(b) and _bolak_ruxsat(u, b)
    return False


@app.get("/api/holat")
def holat(request: Request, id: int = 0):
    u = _joriy(request)
    if not u:
        return _401()
    if not id:
        r = pg.bitta(
            """SELECT id FROM jobs WHERE user_id=%s AND tur='majlis'
               AND holat IN ('navbatda','ketmoqda') ORDER BY id DESC LIMIT 1""", u["id"])
        if not r:
            return {"holat": "bosh"}
        id = r[0]
    j = pg.bitta_d("SELECT id, tur, user_id, kirish, holat FROM jobs WHERE id=%s", id)
    if not j or not _job_ruxsat(u, j):
        return _404()
    h = jobs.holat(id)
    if not h:
        return _404()
    orin = pg.bitta(
        """SELECT count(*) FROM jobs WHERE tur='majlis' AND holat='navbatda'
           AND id < %s""", id)[0]
    natija = h.get("natija") or {}
    return {"id": id, "holat": h["holat"], "loglar": h["loglar"], "xato": h["xato"],
            "savol": (j["kirish"] or {}).get("savol", ""),
            "suhbat": (j["kirish"] or {}).get("suhbat_id"),
            "navbat_orni": orin + 1 if h["holat"] == "navbatda" else 0,
            "majlis_id": natija.get("majlis_id")}


@app.get("/api/statistika")
def statistika(request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    if "bolaklar" not in STAT or time.time() - STAT.get("vaqt", 0) > 300:
        STAT["bolaklar"] = pg.bitta("SELECT count(*) FROM bolaklar")[0]
        STAT["vaqt"] = time.time()
    return {"majlislar": db.majlis_soni(u["id"]), "bolaklar": STAT["bolaklar"]}


# ---------------------------------------------------------------- Telegram webhook

@app.post("/tg/webhook/{sir}")
async def tg_webhook(sir: str, request: Request):
    if not auth.bot_token() or sir != tg.webhook_sir():
        return _404()
    try:
        up = await request.json()
        if "message" in up:
            tg.xabar(up["message"])
    except Exception as e:
        log(f"TG webhook xatosi: {str(e)[:150]}")
    return {"ok": True}


# ---------------------------------------------------------------- UI

@app.get("/")
def bosh():
    return FileResponse(WEB / "index.html", media_type="text/html",
                        headers={"Cache-Control": "no-cache"})


@app.get("/admin")
def admin_sahifa():
    return FileResponse(WEB / "admin.html", media_type="text/html",
                        headers={"Cache-Control": "no-cache"})


@app.get("/kabinet")
def kabinet_sahifa():
    return FileResponse(WEB / "kabinet.html", media_type="text/html",
                        headers={"Cache-Control": "no-cache"})


@app.get("/tg-widget")
def tg_widget():
    """Telegram Login Widget — asosiy ilova uni iframe bilan qo'yadi.

    Alohida sahifa bo'lishining sababi WIDGET_CSP izohida yozilgan.
    `?rejim=bogla` — mavjud akkauntga Telegramni ulash uchun.
    """
    bot = tg.bot_username()
    if not bot:
        return _404()
    html = (WEB / "tg_widget.html").read_text(encoding="utf-8")
    return Response(html.replace("__BOT__", bot), media_type="text/html",
                    headers={"Content-Security-Policy": WIDGET_CSP,
                             "Cache-Control": "no-store"})


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


# Statik fayllar (mermaid) — faqat oq ro'yxatdagi nomlar, yo'l bo'ylab chiqib
# ketish (path traversal) imkonsiz.
STATIK = {"mermaid.min.js": "application/javascript",
          "ui.css": "text/css",
          "ui.js": "application/javascript"}


@app.get("/static/{nom}")
def statik(nom: str):
    tur = STATIK.get(nom)
    if not tur:
        return _404()
    fayl = WEB / nom
    if not fayl.is_file():
        return _404()
    return FileResponse(fayl, media_type=tur,
                        headers={"Cache-Control": "public, max-age=604800"})


def main():
    import uvicorn
    pg.migratsiya()
    tg.webhook_ornat()
    port = int(os.environ.get("PORT", "8900"))
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    log(f"WEB: http://{host}:{port}  ({MUHIT})")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
