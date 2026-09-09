# -*- coding: utf-8 -*-
"""B2B API v1 — hamkorlar uchun tashqi yuza.

Reja: `B2B_API_REJA.md`. Yadro: `b2b.py`.

Bu qatlam javob DVIGATELINI QAYTA YOZMAYDI — `yordamchi.oqim_navbat` ayni
o'sha, faqat ustidagi autentifikatsiya, izolyatsiya, cheklov va hisob
boshqacha. Shuning uchun chatdagi har yaxshilanish API ga ham o'zi tegadi.

UCH QOIDA:

1. **Tannarx sizib chiqmaydi.** Ichki `narx_usd`, model nomi va token soni
   javobga TUSHMAYDI — hamkor faqat `hisob_usd` ni ko'radi. `tayyor`
   hodisasi ichkarida `narx_usd` bilan keladi, shu yerda tozalanadi.
2. **Begona resurs 404.** Boshqa tashkilotning suhbati/useri/twini uchun
   403 emas, 404 — mavjudligini ham oshkor qilmaymiz.
3. **Cookie yo'q.** Bu router `web._joriy` ni chaqirmaydi; API kaliti
   hech qachon admin yoki kabinet yuzasini ocholmaydi.
"""
import json
import threading
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from . import b2b, cheklov, db, fragment, jobs, pg, pul, yordamchi
from .sozlama import log

router = APIRouter(prefix="/api/v1")

# --- Har endpointning IKKI manzili bor ---------------------------------------
# Asosiy manzil INGLIZCHA (/ask, /mentors, ...) — hamkorlar xalqaro, hujjat ham
# shu nomlar bilan chiqadi. O'zbekchasi (/savol, /twinlar, ...) esa
# `include_in_schema=False` bilan yonida turadi: sxemada KO'RINMAYDI, lekin
# ishlayveradi.
#
# O'zbekcha manzillar O'CHIRILMAYDI — ular allaqachon e'lon qilingan
# (`docs/B2B_API.md`) va ulangan hamkorning kodini buzardi. Bu ilova ichidagi
# `twin`/`suhbat` atamalariga tegmaydi: jadval nomlari, funksiya nomlari va
# ichki API (`/api/twin/...`) o'zbekcha qoladi (CLAUDE.md, «Til qoidasi»).

SAVOL_MAKS = 4000
INGEST_MUHLAT = 4 * 3600

# Tashkilot bo'yicha parallel oqim chegarasi. SSE uzoq yashaydi — cheklovsiz
# bitta hamkor butun web jarayonining threadlarini band qilib qo'yardi.
_semafor: dict[int, threading.BoundedSemaphore] = {}
_semafor_qulf = threading.Lock()


def _oqim_semafori(t: dict) -> threading.BoundedSemaphore:
    with _semafor_qulf:
        s = _semafor.get(t["id"])
        if s is None:
            s = threading.BoundedSemaphore(max(1, int(t["oqim_limit"] or 5)))
            _semafor[t["id"]] = s
        return s


# ---------------------------------------------------------------- javoblar

def _xato(kod: str, xabar: str, holat: int, **qosh):
    return JSONResponse({"xato": kod, "xabar": xabar, **qosh}, status_code=holat)


def _401():
    return _xato("kalit_notogri", "API kaliti yaroqsiz yoki muddati o'tgan", 401)


def _403():
    return _xato("ruxsat_yoq", "Bu kalitda bunday huquq yo'q", 403)


def _404():
    return _xato("topilmadi", "Bunday resurs yo'q", 404)


def _429(kod: str = "tez", qayta: int = 60):
    r = _xato(kod, "So'rovlar chegarasi oshdi", 429)
    r.headers["Retry-After"] = str(qayta)
    return r


# ------------------------------------------------------------ kirish eshigi

def _kirish(request: Request, huquq: str):
    """(kontekst, xato_javobi). Har endpoint shu bittasidan boshlanadi."""
    k = b2b.tekshir(request)
    if not k:
        # Kalit taxmin qilib urinishlarni ham cheklaymiz (IP bo'yicha).
        cheklov.ruxsat("api_kalit", b2b._ip(request))
        return None, _401()
    if not k.huquq(huquq):
        return None, _403()
    if not cheklov.ruxsat("api_umumiy", str(k.tashkilot_id)):
        return None, _429()
    return k, None


# --------------------------------------------------------- hodisa tozalash

def _manba(b: dict) -> dict:
    """Iqtibosni hamkorga ko'rsatiladigan shaklga keltiradi.

    Ichki S3 kalitlari (`sahifa_png`) chiqmaydi — ular bizning ombor
    tuzilishimiz haqida ma'lumot berardi.
    """
    return {
        "n": b.get("n"),
        "bolak": b.get("id"),
        "manba": b.get("manba", ""),
        "joy": b.get("joy", ""),
        "tur": b.get("tur", ""),
        "dars": b.get("dars", ""),
        "audio": b.get("audio_bosh") is not None,
        "sahifa": bool(b.get("sahifa_png")),
    }


def _hodisa(h: dict, tashkilot_id: int) -> dict | None:
    """SSE hodisasini hamkor uchun tozalaydi. None = yubormaymiz."""
    tur = h.get("tur")
    if tur == "matn":
        return {"tur": "matn", "q": h.get("q", "")}
    if tur == "boshlandi":
        return {"tur": "boshlandi", "suhbat": h.get("suhbat_id"),
                "javob_id": h.get("majlis_id")}
    if tur == "holat":
        return {"tur": "holat", "matn": h.get("matn", "")}
    if tur == "manbalar":
        return {"tur": "manbalar",
                "royxat": [_manba(b) for b in (h.get("royxat") or [])]}
    if tur == "tayyor":
        mid = h.get("majlis_id")
        return {"tur": "tayyor", "javob_id": mid,
                "davomiylik": h.get("davomiylik"),
                "toxtatildi": bool(h.get("toxtatildi")),
                "manbalar": [_manba(b) for b in (h.get("manbalar") or [])],
                "hisob": _javob_hisobi(tashkilot_id, mid)}
    if tur == "xato":
        return {"tur": "xato", "xabar": h.get("xabar", "Xatolik")}
    return None                      # noma'lum hodisa tashqariga chiqmaydi


def _javob_hisobi(tashkilot_id: int, majlis_id) -> dict:
    """Shu javobning hamkorga tushgan narxi + qolgan balans. TANNARX YO'Q."""
    sarf = 0.0
    if majlis_id:
        r = pg.bitta(
            """SELECT COALESCE(sum(hisob_usd), 0) FROM xarajatlar
               WHERE majlis_id=%s AND tashkilot_id=%s""", majlis_id, tashkilot_id)
        sarf = float(r[0]) if r else 0.0
    t = b2b.tashkilot_ol(tashkilot_id)
    return {"sarf_usd": round(sarf, 6),
            "balans_usd": round(float(t["balans_usd"]), 4) if t else 0.0}


# ------------------------------------------------------------ foydalanuvchi

class FoydalanuvchiSorov(BaseModel):
    tashqi_id: str
    ism: str = ""


@router.post("/customer", summary="Register a customer")
@router.post("/foydalanuvchi", include_in_schema=False)
def foydalanuvchi(s: FoydalanuvchiSorov, request: Request):
    """Hamkorning mijozini ro'yxatga oladi (idempotent)."""
    k, xato = _kirish(request, "savol")
    if xato:
        return xato
    tid = (s.tashqi_id or "").strip()
    if not tid:
        return _xato("notogri", "tashqi_id bo'sh", 400)
    u = b2b.foydalanuvchi(k.tashkilot_id, tid, s.ism)
    return {"id": u["id"], "tashqi_id": u["tashqi_id"], "yangi": bool(u["yangi"])}


# ------------------------------------------------------------------ twinlar

@router.get("/mentors", summary="List available mentors")
@router.get("/twinlar", include_in_schema=False)
def twinlar(request: Request):
    k, xato = _kirish(request, "twinlar")
    if xato:
        return xato
    return {"royxat": [{"slug": t["slug"], "nom": t["nom"], "tavsif": t["tavsif"]}
                       for t in b2b.twinlar(k.tashkilot_id)]}


# -------------------------------------------------------------------- savol

class SavolSorov(BaseModel):
    tashqi_id: str
    savol: str
    twin: str | None = None
    suhbat: int | None = None
    oqim: bool = True
    ism: str = ""


@router.post("/ask", summary="Ask a question - main endpoint")
@router.post("/savol", include_in_schema=False)
def savol(s: SavolSorov, request: Request):
    """Asosiy endpoint: savol -> manbaga tayangan javob + iqtiboslar."""
    k, xato = _kirish(request, "savol")
    if xato:
        return xato

    # --- tezlik chegarasi VALIDATSIYADAN OLDIN: aks holda noto'g'ri shakldagi
    #     so'rovlarni cheksiz yuborib, savol chegarasini umuman aylanib o'tish
    #     mumkin edi (sinovda topilgan).
    if not cheklov.ruxsat("api_savol", str(k.tashkilot_id)):
        return _429("tashkilot_tez")
    if not cheklov.ruxsat("api_user", f"{k.tashkilot_id}:{s.tashqi_id}"):
        return _429("mijoz_tez")

    matn = (s.savol or "").strip()
    if not matn:
        return _xato("notogri", "savol bo'sh", 400)
    if len(matn) > SAVOL_MAKS:
        return _xato("notogri", f"savol juda uzun ({SAVOL_MAKS} belgi chegara)", 400)

    # --- idempotentlik (faqat to'liq javob rejimida: oqimni takrorlab bo'lmaydi)
    idem = (request.headers.get("idempotency-key") or "").strip()
    if idem and not s.oqim:
        eski = b2b.idempotent_ol(k.tashkilot_id, idem)
        if eski:
            return JSONResponse(eski["javob"], status_code=eski["holat"],
                                headers={"Idempotent-Takror": "1"})

    # --- twin: FAQAT shu tashkilotga ochilganlaridan
    twinlar_r = b2b.twinlar(k.tashkilot_id)
    if not twinlar_r:
        return _xato("twin_yoq", "Bu tashkilotga hali twin biriktirilmagan", 409)
    twin = (b2b.twin_ruxsat(k.tashkilot_id, s.twin) if s.twin
            else db.twin_ol(twinlar_r[0]["id"]))
    if not twin:
        return _404()

    u = b2b.foydalanuvchi(k.tashkilot_id, s.tashqi_id, s.ism)

    # --- pul darvozasi: balans yetmasa MODEL UMUMAN CHAQIRILMAYDI
    ok, sabab = b2b.balans_yetadimi(k.tashkilot)
    if not ok:
        return _xato("balans_tugadi", sabab, 402,
                     balans_usd=round(float(k.tashkilot["balans_usd"]), 4))

    # --- suhbat: mavjud bo'lsa EGALIGI tekshiriladi
    sid = s.suhbat
    if sid is not None:
        sq = db.suhbat_ol(sid)
        if not sq or sq["user_id"] != u["id"]:
            return _404()          # begona suhbat — mavjudligini bildirmaymiz
    else:
        sid = db.suhbat_yasa(u["id"], twin["id"], matn)

    sem = _oqim_semafori(k.tashkilot)
    if not sem.acquire(blocking=False):
        return _429("parallel_oqim")

    try:
        hodisalar, toxtat = yordamchi.oqim_navbat(u, twin, matn, sid, bepul=False)
    except Exception:                                        # noqa: BLE001
        sem.release()
        raise

    if s.oqim:
        return _oqim_javob(hodisalar, toxtat, sem, k.tashkilot_id, sid)
    return _toliq_javob(hodisalar, toxtat, sem, k, sid, idem)


def _oqim_javob(hodisalar, toxtat, sem, tashkilot_id: int, sid: int):
    """SSE — hodisalar tozalanib uzatiladi."""
    def chiqish():
        try:
            for h in hodisalar:
                toza = _hodisa(h, tashkilot_id)
                if toza is not None:
                    if toza.get("tur") == "boshlandi":
                        toza["suhbat"] = sid
                    yield f"data: {json.dumps(toza, ensure_ascii=False)}\n\n".encode()
        except GeneratorExit:
            toxtat.set()             # mijoz uzildi — modelni bekorga ishlatmaymiz
            raise
        finally:
            sem.release()

    return StreamingResponse(
        chiqish(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform",
                 "X-Accel-Buffering": "no", "Connection": "keep-alive"})


def _toliq_javob(hodisalar, toxtat, sem, k, sid: int, idem: str):
    """`oqim=false` — oqim yig'ilib, bitta JSON qaytadi (integratsiya oson)."""
    javob, manbalar, hisob, xato_matn, jid = [], [], {}, "", None
    try:
        for h in hodisalar:
            tur = h.get("tur")
            if tur == "matn":
                javob.append(h.get("q", ""))
            elif tur == "manbalar":
                manbalar = [_manba(b) for b in (h.get("royxat") or [])]
            elif tur == "tayyor":
                jid = h.get("majlis_id")
                if h.get("manbalar"):
                    manbalar = [_manba(b) for b in h["manbalar"]]
                hisob = _javob_hisobi(k.tashkilot_id, jid)
            elif tur == "xato":
                xato_matn = h.get("xabar", "Xatolik")
    finally:
        toxtat.set()
        sem.release()

    if xato_matn:
        return _xato("model", xato_matn, 503)

    natija = {"suhbat": sid, "javob_id": jid, "javob": "".join(javob),
              "manbalar": manbalar, "hisob": hisob}
    if idem:
        b2b.idempotent_yoz(k.tashkilot_id, idem, natija, 200)
    return natija


# ----------------------------------------------------------------- suhbatlar

@router.get("/conversations", summary="List customer conversations")
@router.get("/suhbatlar", include_in_schema=False)
def suhbatlar(request: Request, tashqi_id: str = ""):
    k, xato = _kirish(request, "suhbat")
    if xato:
        return xato
    if not tashqi_id.strip():
        return _xato("notogri", "tashqi_id kerak", 400)
    u = pg.bitta_d(
        "SELECT id FROM userlar WHERE tashkilot_id=%s AND tashqi_id=%s",
        k.tashkilot_id, tashqi_id.strip())
    if not u:
        return _404()
    return {"royxat": [{"id": q["id"], "sarlavha": q["sarlavha"],
                        "yangilangan": q["yangilangan"], "soni": q["soni"]}
                       for q in db.suhbatlar(u["id"])]}


@router.get("/conversation/{sid}", summary="Get one conversation")
@router.get("/suhbat/{sid}", include_in_schema=False)
def suhbat(sid: int, request: Request):
    k, xato = _kirish(request, "suhbat")
    if xato:
        return xato
    sq = db.suhbat_ol(sid)
    if not sq:
        return _404()
    # Suhbat egasi shu tashkilotnikimi — izolyatsiyaning asosiy tekshiruvi
    if not b2b.foydalanuvchi_ol(k.tashkilot_id, sq["user_id"]):
        return _404()
    xabarlar = []
    for m in db.suhbat_majlislari(sq["user_id"], sid):
        xabarlar.append({
            "javob_id": m["id"], "savol": m["savol"], "javob": m["xulosa"],
            "vaqt": m["vaqt"], "toxtatildi": bool(m["toxtatildi"]),
            "manbalar": [_manba(b) for b in
                         ((m["hisobot"] or {}).get("manbalar") or [])],
        })
    return {"id": sid, "sarlavha": sq["sarlavha"], "xabarlar": xabarlar}


# ------------------------------------------------------------------ fragment

@router.post("/chunk/{bid}/fragment", summary="Request an audio fragment")
@router.post("/bolak/{bid}/fragment", include_in_schema=False)
def bolak_fragment(bid: int, request: Request):
    """Iqtibosning audio kesmasini tayyorlashni buyuradi."""
    k, xato = _kirish(request, "fragment")
    if xato:
        return xato
    b = db.bolak_ol(bid)
    # `bolaklar.twin_id` bevosita bor — manbani qidirish shart emas.
    if not b or not b2b.twin_ruxsat(k.tashkilot_id, b["twin_id"]):
        return _404()

    h = fragment.holat(b)
    if not h["audio"]:
        return _xato("audio_yoq", "Bu bo'lakda audio yo'q", 400)
    fr = db.fragment_ol(bid, "audio")
    if fr and fr["holat"] == "tayyor":
        return {"holat": "tayyor", "bolak": bid}
    bor = pg.bitta(
        """SELECT id FROM jobs WHERE tur='fragment' AND holat IN ('navbatda','ketmoqda')
           AND (kirish->>'bolak_id')::bigint = %s LIMIT 1""", bid)
    if bor:
        return {"holat": "ketmoqda", "bolak": bid}
    jobs.qoshish("fragment", {"bolak_id": bid}, twin_id=b["twin_id"],
                 ustunlik=6, muhlat_s=900)
    return {"holat": "ketmoqda", "bolak": bid}


# --------------------------------------------------------------------- hisob

@router.get("/account", summary="Balance and usage")
@router.get("/hisob", include_in_schema=False)
def hisob(request: Request):
    k, xato = _kirish(request, "hisob")
    if xato:
        return xato
    natija = b2b.hisob(k.tashkilot_id)
    natija["harakatlar"] = [
        {"vaqt": h["vaqt"], "tur": h["tur"],
         "summa_usd": round(float(h["summa_usd"]), 6),
         "qoldiq_usd": round(float(h["qoldiq_usd"]), 4), "izoh": h["izoh"]}
        for h in b2b.harakatlar(k.tashkilot_id, 20)]
    return natija


@router.get("/report", summary="Monthly report")
@router.get("/hisobot", include_in_schema=False)
def hisobot(request: Request, oy: str = ""):
    """Oylik hisob-faktura: `?oy=2026-09` (bo'sh — joriy oy)."""
    k, xato = _kirish(request, "hisob")
    if xato:
        return xato
    return b2b.hisobot(k.tashkilot_id, oy)


@router.get("/health", summary="Health check - free")
@router.get("/salomatlik", include_in_schema=False)
def salomatlik(request: Request):
    """Hamkor integratsiyani tekshirishi uchun — pul sarflamaydi."""
    k, xato = _kirish(request, "hisob")
    if xato:
        return xato
    return {"holat": "ok", "tashkilot": k.tashkilot["nom"],
            "twinlar": len(b2b.twinlar(k.tashkilot_id)),
            "vaqt": int(time.time())}
