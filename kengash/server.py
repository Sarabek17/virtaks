# -*- coding: utf-8 -*-
"""Kengash web-interfeysi — ko'p foydalanuvchili chat (Telegram login + Mini App).

Ishga tushirish:
  .venv\\Scripts\\python.exe -m kengash.server
Brauzerda: http://127.0.0.1:8765

Server faqat 127.0.0.1 ga bog'lanadi. Telegram Mini App / tashqi kirish uchun
HTTPS tunel ishlating (masalan: cloudflared tunnel --url http://127.0.0.1:8765)
va .env dagi PUBLIC_URL ga tunel manzilini yozing.
"""
import re
import threading

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import aniqlik, auth, db, navbat, suhbat, tg
from .sozlama import CHIQISH, ILDIZ, USTOZ_STANDART, USTOZLAR, log

app = FastAPI(title="Kengash")
WEB = ILDIZ / "web"
COOKIE = "kengash_sessiya"
STAT = {}


# ---------------------------------------------------------------- yordamchilar

def _joriy(request: Request) -> dict | None:
    """Cookie'dagi sessiyadan joriy userni topadi."""
    return db.sessiya_user(request.cookies.get(COOKIE, ""))


def _401():
    return JSONResponse({"xato": "kirish kerak"}, status_code=401)


def _user_json(u: dict) -> dict:
    return {"id": u["id"], "ism": u["ism"], "familiya": u["familiya"],
            "username": u["username"], "foto": u["foto"],
            "telefon": bool(u["telefon"]),
            "ustoz": u.get("ustoz") or ""}


def _kirish_javobi(u: dict) -> JSONResponse:
    r = JSONResponse({"ok": True, "user": _user_json(u)})
    r.set_cookie(COOKIE, db.sessiya_yasa(u["id"]), max_age=db.SESSIYA_KUN * 86400,
                 httponly=True, samesite="lax")
    return r


# ---------------------------------------------------------------- konfig / kirish

@app.get("/api/konfig")
def konfig(request: Request):
    u = _joriy(request)
    return {"dev": auth.dev_rejim(),
            "bot": tg.bot_username(),
            "ustozlar": USTOZLAR,
            "user": _user_json(u) if u else None}


@app.post("/api/kirish/telegram")
async def kirish_telegram(request: Request):
    """Sayt: Telegram Login Widget ma'lumoti."""
    data = await request.json()
    tg_user = auth.widget_tekshir(data if isinstance(data, dict) else {})
    if not tg_user:
        return JSONResponse({"xato": "imzo noto'g'ri"}, status_code=403)
    return _kirish_javobi(db.user_tg(tg_user))


class WebAppKirish(BaseModel):
    init_data: str


@app.post("/api/kirish/webapp")
def kirish_webapp(s: WebAppKirish):
    """Telegram Mini App: initData imzosi bilan kirish."""
    tg_user = auth.webapp_tekshir(s.init_data)
    if not tg_user:
        return JSONResponse({"xato": "imzo noto'g'ri"}, status_code=403)
    return _kirish_javobi(db.user_tg(tg_user))


class DevKirish(BaseModel):
    ism: str


@app.post("/api/kirish/dev")
def kirish_dev(s: DevKirish):
    """Dev-rejim (bot token sozlanmagan payt) — faqat lokal sinov."""
    if not auth.dev_rejim():
        return JSONResponse({"xato": "dev-rejim o'chiq — Telegram orqali kiring"},
                            status_code=403)
    return _kirish_javobi(db.user_dev(s.ism))


@app.post("/api/chiqish")
def chiqish(request: Request):
    db.sessiya_ochir(request.cookies.get(COOKIE, ""))
    r = JSONResponse({"ok": True})
    r.delete_cookie(COOKIE)
    return r


# ---------------------------------------------------------------- sozlamalar

class UstozTanlov(BaseModel):
    ustoz: str = ""       # "" = barcha ustozlar bilimi


@app.post("/api/ustoz")
def ustoz_qoy(s: UstozTanlov, request: Request):
    """User qaysi ustoz bilimiga tayanishini tanlaydi."""
    u = _joriy(request)
    if not u:
        return _401()
    v = s.ustoz.strip()
    if v and v not in USTOZLAR:
        return JSONResponse({"xato": "noma'lum ustoz"}, status_code=400)
    db.ustoz_yoz(u["id"], v)
    return {"ok": True, "ustoz": v}


# ---------------------------------------------------------------- majlis

class Sorov(BaseModel):
    savol: str
    hamma: bool = False
    majbur: bool = False      # aniqlik tekshiruvisiz yuborish
    suhbat: int | None = None  # qaysi chat-sessiya; None = yangi suhbat ochiladi


@app.post("/api/boshla")
def boshla(s: Sorov, request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    savol = s.savol.strip()
    if not savol:
        return JSONResponse({"ok": False, "xabar": "Savol bo'sh"}, status_code=400)

    sid = s.suhbat
    if sid is not None and db.suhbat_egasi(sid) != u["id"]:
        return JSONResponse({"ok": False, "xabar": "Suhbat topilmadi"}, status_code=404)

    # tushunarsiz savol -> variantlar bilan qaytamiz (majlis ham, suhbat ham ochilmaydi)
    if not s.majbur:
        ktx = suhbat.formatla(suhbat.kontekst(u["id"], sid)) if sid else ""
        n = aniqlik.tekshir(savol, db.profil_ol(u["id"]), ktx)
        if not n.get("aniq"):
            return {"ok": True, "holat": "tushunarsiz",
                    "izoh": n.get("izoh", ""), "variantlar": n.get("variantlar", [])}
    if navbat.faol(u["id"]):
        return JSONResponse(
            {"ok": False,
             "xabar": "Sizning majlisingiz allaqachon ketmoqda — tugashini kuting"},
            status_code=409)
    if sid is None:
        sid = db.suhbat_yasa(u["id"], savol)   # yangi chat — sarlavha birinchi savoldan
    try:
        job = navbat.qoshish(u["id"], savol, s.hamma, sid)
    except ValueError as e:
        return JSONResponse({"ok": False, "xabar": str(e)}, status_code=409)
    return {"ok": True, "holat": "navbat",
            "job": navbat.holat(job["id"], u["id"])}


@app.get("/api/suhbatlar")
def suhbatlar_royxati(request: Request):
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
        return JSONResponse({"xato": "topilmadi"}, status_code=404)
    return db.suhbat_majlislari(u["id"], sid)


@app.get("/api/holat")
def holat(request: Request, id: str = ""):
    u = _joriy(request)
    if not u:
        return _401()
    if id:
        j = navbat.holat(id, u["id"])
        if not j:
            return JSONResponse({"xato": "topilmadi"}, status_code=404)
        return j
    j = navbat.faol(u["id"])
    return navbat.holat(j["id"], u["id"]) if j else {"holat": "bosh"}


@app.get("/api/royxat")
def royxat(request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    return db.majlislar(u["id"])


@app.get("/api/statistika")
def statistika(request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    if "bolaklar" not in STAT:
        try:
            from collections import Counter

            from .qidiruv import _bm25
            b = _bm25()["bolaklar"]
            STAT["bolaklar"] = len(b)
            STAT["ustozlar"] = dict(Counter(
                x.get("ustoz", USTOZ_STANDART) for x in b))
        except Exception:
            STAT["bolaklar"] = 0
            STAT["ustozlar"] = {}
    return {"majlislar": db.majlis_soni(u["id"]), "bolaklar": STAT["bolaklar"],
            "ustozlar": STAT["ustozlar"]}


# ---------------------------------------------------------------- hisobot

def _hisobot_parse(matn: str) -> dict:
    """Majlis hisobotini (md) tuzilgan JSON ga ajratadi. Eski formatga ham chidaydi."""
    sm = re.search(r"\*\*Savol:\*\* (.+)", matn)
    bm = re.search(r"\*\*Bilim manbasi:\*\* (.+)", matn)
    xm = re.search(r"# YAKUNIY XULOSA \(RAIS\)\n(.*?)"
                   r"(?=\n## MANBALAR \(yagona|\n---\n\n# DIREKTORLAR|\Z)", matn, re.S)
    manbalar = [{"g": int(g), "manba": ma, "joy": j, "tur": t, "dars": d}
                for g, ma, j, t, d in re.findall(
                    r"^- \*\*\[(\d+)\]\*\* (.+?) — (.+?) \((.+?), papka: (.*?)\)$", matn, re.M)]
    direktorlar = []
    dq = matn.split("# DIREKTORLAR JAVOBLARI")[-1]
    bolak = re.split(r"\n## (CEO|CTO|CFO|COO|CLO|CMO)\n", dq)
    for i in range(1, len(bolak) - 1, 2):
        rol, tana = bolak[i], bolak[i + 1].strip()
        gl = []
        gm = re.search(r"\n?\*\*O'qigan manbalari:\*\* (.+)\s*$", tana)
        if gm:
            gl = [int(x) for x in re.findall(r"\[(\d+)\]", gm.group(1))]
            tana = tana[:gm.start()].rstrip()
        direktorlar.append({"rol": rol, "javob": tana, "global": gl})
    return {"savol": sm.group(1).strip() if sm else "",
            "bilim": bm.group(1).strip() if bm else "",
            "xulosa": xm.group(1).strip() if xm else matn,
            "manbalar": manbalar, "direktorlar": direktorlar}


@app.get("/api/hisobot/{nom}")
def hisobot(nom: str, request: Request):
    u = _joriy(request)
    if not u:
        return _401()
    yol = CHIQISH / nom
    if ".." in nom or not nom.startswith("majlis_") or not nom.endswith(".md") or not yol.is_file():
        return JSONResponse({"xato": "topilmadi"}, status_code=404)
    # egalik: faqat o'z majlisini o'qiy oladi
    if db.majlis_egasi(nom) != u["id"]:
        return JSONResponse({"xato": "topilmadi"}, status_code=404)
    return {"nom": nom, **_hisobot_parse(yol.read_text(encoding="utf-8"))}


@app.get("/api/fayl/{nom}")
def fayl_yuklab(nom: str, request: Request):
    """Majlisga biriktirilgan tayyor faylni (to'ldirilgan shablon) yuklab beradi."""
    u = _joriy(request)
    if not u:
        return _401()
    yol = CHIQISH / "fayllar" / nom
    if ("/" in nom or "\\" in nom or ".." in nom or not nom.endswith(".xlsx")
            or not yol.is_file()):
        return JSONResponse({"xato": "topilmadi"}, status_code=404)
    if db.biriktirma_egasi(nom) != u["id"]:
        return JSONResponse({"xato": "topilmadi"}, status_code=404)
    return FileResponse(
        yol, filename=nom,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/")
def bosh():
    # no-cache: har ochilishda yangilik tekshiriladi — Telegram webview eski
    # sahifani ushlab qolib, yangi funksiyalar ko'rinmay qolmasin
    return FileResponse(WEB / "index.html", media_type="text/html",
                        headers={"Cache-Control": "no-cache"})


def main():
    import os

    import uvicorn
    tg.yurgiz()
    # Bulutda (Railway) PORT beriladi -> 0.0.0.0; lokalda faqat 127.0.0.1
    port = int(os.environ.get("PORT", "8765"))
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    log(f"Kengash web-interfeysi: http://{host}:{port}")
    if auth.dev_rejim():
        log("DEV-REJIM: Telegram bot sozlanmagan — ism bilan kirish ochiq")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
