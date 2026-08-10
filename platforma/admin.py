# -*- coding: utf-8 -*-
"""Admin API — to'liq huquq: twinlar, direktorlar, kategoriyalar, ruxsatlar,
userlar, impersonation (twin egasi akkauntiga kirish), jobs monitor.

Har endpoint admin rolini talab qiladi (bitta joyda — _admin).
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import auth, db, pg, pul, tolov

router = APIRouter(prefix="/api/admin")
COOKIE = "twin_sessiya"


def _admin(request: Request) -> dict | None:
    u = db.sessiya_user(request.cookies.get(COOKIE, ""))
    # impersonation paytida ham admin huquqi impersonator'da qoladi
    if u and u.get("impersonator_id"):
        asl = db.user_ol(u["impersonator_id"])
        return asl if auth.admin_mi(asl) else None
    return u if auth.admin_mi(u) else None


def _403():
    return JSONResponse({"xato": "ruxsat yo'q"}, status_code=403)


# ---------------------------------------------------------------- xulosa

@router.get("/xulosa")
def xulosa(request: Request):
    if not _admin(request):
        return _403()
    q = lambda s, *a: pg.bitta(s, *a)[0]      # noqa: E731
    return {
        "userlar": q("SELECT count(*) FROM userlar"),
        "twinlar": q("SELECT count(*) FROM twinlar"),
        "direktorlar": q("SELECT count(*) FROM direktorlar WHERE faol"),
        "manbalar": q("SELECT count(*) FROM manbalar"),
        "bolaklar": q("SELECT count(*) FROM bolaklar"),
        "majlislar": q("SELECT count(*) FROM majlislar"),
        "jobs_navbatda": q("SELECT count(*) FROM jobs WHERE holat='navbatda'"),
        "jobs_ketmoqda": q("SELECT count(*) FROM jobs WHERE holat='ketmoqda'"),
        "jobs_xato": q("SELECT count(*) FROM jobs WHERE holat='xato'"),
        "narx_jami": float(q("SELECT COALESCE(sum(narx_usd),0) FROM majlislar")),
    }


@router.get("/mentor")
def mentor_statistika(request: Request):
    """Mentorlik rejimi bo'yicha umumiy manzara (kurslar, o'quvchilar, vazifalar)."""
    if not _admin(request):
        return _403()
    q = lambda s, *a: pg.bitta(s, *a)[0]      # noqa: E731
    return {
        "kurs_faol": q("SELECT count(*) FROM kurslar WHERE holat='faol'"),
        "kurs_qoralama": q("SELECT count(*) FROM kurslar WHERE holat='qoralama'"),
        "mavzu": q("""SELECT count(*) FROM mavzular s
                      JOIN modullar m ON m.id = s.modul_id
                      JOIN kurslar k ON k.id = m.kurs_id
                      WHERE k.holat='faol' AND s.faol"""),
        "oquvchi": q("SELECT count(*) FROM oquv_reja"),
        "tugallangan_mavzu": q(
            "SELECT count(*) FROM oquv_holat WHERE holat='tugallangan'"),
        "dars_xabar": q("SELECT count(*) FROM majlislar WHERE rejim='mentor'"),
        "vazifa_jami": q("SELECT count(*) FROM vazifalar"),
        "vazifa_ochiq": q("SELECT count(*) FROM vazifalar WHERE holat='berildi'"),
        "vazifa_tekshirilgan": q(
            "SELECT count(*) FROM vazifalar WHERE holat='tekshirildi'"),
        "ortacha_baho": (lambda v: round(float(v), 1) if v is not None else None)(
            q("SELECT avg(baho) FROM vazifalar WHERE baho IS NOT NULL")),
        "mentor_narx": float(q(
            "SELECT COALESCE(sum(narx_usd),0) FROM majlislar WHERE rejim='mentor'")),
        "vazifa_narx": float(q("SELECT COALESCE(sum(narx_usd),0) FROM vazifalar")),
        "kurs_narx": float(q(
            """SELECT COALESCE(sum(narx_usd),0) FROM xarajatlar
               WHERE bosqich LIKE 'kurs\\_%'""")),
        "twinlar": pg.hammasi_d(
            """SELECT t.id, t.nom, k.versiya, k.holat,
                      (SELECT count(*) FROM oquv_reja r WHERE r.kurs_id = k.id) AS oquvchi,
                      (SELECT count(*) FROM mavzular s
                        JOIN modullar m ON m.id = s.modul_id
                       WHERE m.kurs_id = k.id AND s.faol) AS mavzu
               FROM kurslar k JOIN twinlar t ON t.id = k.twin_id
               WHERE k.holat IN ('faol','qoralama')
               ORDER BY t.nom"""),
    }


@router.get("/maqsad")
def maqsad_statistika(request: Request):
    """Maqsad halqasi bo'yicha manzara (sikllar, qadamlar, xarajat)."""
    if not _admin(request):
        return _403()
    q = lambda s, *a: pg.bitta(s, *a)[0]      # noqa: E731
    tugagan = q("SELECT count(*) FROM maqsadlar WHERE holat='tugallangan'")
    return {
        "jami": q("SELECT count(*) FROM maqsadlar"),
        "faol": q("""SELECT count(*) FROM maqsadlar
                     WHERE holat NOT IN ('tugallangan','bekor')"""),
        "tugallangan": tugagan,
        "bekor": q("SELECT count(*) FROM maqsadlar WHERE holat='bekor'"),
        "ortacha_foiz": (lambda v: round(float(v)) if v is not None else None)(
            q("SELECT avg(foiz) FROM maqsadlar WHERE holat='tugallangan'")),
        "qadam_jami": q("SELECT count(*) FROM maqsad_qadamlar"),
        "qadam_bajarildi": q(
            "SELECT count(*) FROM maqsad_qadamlar WHERE holat='bajarildi'"),
        "suhbat_xabar": q("SELECT count(*) FROM majlislar WHERE rejim='maqsad'"),
        "suhbat_narx": float(q(
            "SELECT COALESCE(sum(narx_usd),0) FROM majlislar WHERE rejim='maqsad'")),
        "sikl_narx": float(q(
            "SELECT COALESCE(sum(narx_usd),0) FROM maqsadlar")),
        "bosqichlar": pg.hammasi_d(
            """SELECT holat, count(*) AS soni FROM maqsadlar
               GROUP BY holat ORDER BY soni DESC"""),
        "twinlar": pg.hammasi_d(
            """SELECT t.id, t.nom,
                      count(*) FILTER (WHERE m.holat NOT IN
                            ('tugallangan','bekor')) AS faol,
                      count(*) FILTER (WHERE m.holat = 'tugallangan') AS tugagan
               FROM maqsadlar m JOIN twinlar t ON t.id = m.twin_id
               GROUP BY t.id, t.nom ORDER BY t.nom"""),
    }


# ---------------------------------------------------------------- twinlar

class TwinKirish(BaseModel):
    nom: str
    slug: str = ""
    kategoriya_id: int | None = None
    egasi_id: int | None = None
    tavsif: str = ""
    xulq: str = ""
    tartib: int = 100


@router.get("/twinlar")
def twinlar(request: Request):
    if not _admin(request):
        return _403()
    return db.twinlar(faqat_faol=False)


@router.post("/twin")
def twin_yasa(s: TwinKirish, request: Request):
    if not _admin(request):
        return _403()
    slug = (s.slug or s.nom).lower().replace(" ", "-").replace("'", "")
    tid = db.twin_yasa(s.nom, slug, kategoriya_id=s.kategoriya_id,
                       egasi_id=s.egasi_id, tavsif=s.tavsif, xulq=s.xulq,
                       tartib=s.tartib)
    return {"ok": True, "id": tid}


class TwinYangi(BaseModel):
    nom: str | None = None
    kategoriya_id: int | None = None
    egasi_id: int | None = None
    tavsif: str | None = None
    xulq: str | None = None
    faol: bool | None = None
    tartib: int | None = None


@router.put("/twin/{tid}")
def twin_yangila(tid: int, s: TwinYangi, request: Request):
    if not _admin(request):
        return _403()
    db.twin_yangila(tid, **{k: v for k, v in s.model_dump().items() if v is not None})
    return {"ok": True}


@router.delete("/twin/{tid}")
def twin_ochir(tid: int, request: Request):
    if not _admin(request):
        return _403()
    db.twin_ochir(tid)
    return {"ok": True}


class RuxsatKirish(BaseModel):
    manbalar: list[int]


@router.get("/twin/{tid}/ruxsat")
def ruxsat_ol(tid: int, request: Request):
    if not _admin(request):
        return _403()
    return {"twin_id": tid, "manbalar": db.ruxsat_royxat(tid)}


@router.put("/twin/{tid}/ruxsat")
def ruxsat_yoz(tid: int, s: RuxsatKirish, request: Request):
    if not _admin(request):
        return _403()
    db.ruxsat_yoz(tid, s.manbalar)
    return {"ok": True, "manbalar": db.ruxsat_royxat(tid)}


# ---------------------------------------------------------------- direktorlar

class DirektorKirish(BaseModel):
    kod: str
    nom: str
    persona: str
    teglar: list[str] = ["umumiy"]
    rang: str = "#5b8cff"
    twin_id: int | None = None
    rais: bool = False
    tartib: int = 100


@router.get("/direktorlar")
def direktorlar(request: Request, twin_id: int | None = None):
    if not _admin(request):
        return _403()
    if twin_id:
        return db.direktorlar(twin_id, faqat_faol=False)
    return pg.hammasi_d("SELECT * FROM direktorlar ORDER BY rais, tartib, kod")


@router.post("/direktor")
def direktor_yasa(s: DirektorKirish, request: Request):
    if not _admin(request):
        return _403()
    did = db.direktor_yasa(s.kod.upper(), s.nom, s.persona, s.teglar, rang=s.rang,
                           twin_id=s.twin_id, rais=s.rais, tartib=s.tartib)
    return {"ok": True, "id": did}


class DirektorYangi(BaseModel):
    kod: str | None = None
    nom: str | None = None
    persona: str | None = None
    teglar: list[str] | None = None
    rang: str | None = None
    faol: bool | None = None
    rais: bool | None = None
    tartib: int | None = None


@router.put("/direktor/{did}")
def direktor_yangila(did: int, s: DirektorYangi, request: Request):
    if not _admin(request):
        return _403()
    db.direktor_yangila(did, **{k: v for k, v in s.model_dump().items() if v is not None})
    return {"ok": True}


@router.delete("/direktor/{did}")
def direktor_ochir(did: int, request: Request):
    if not _admin(request):
        return _403()
    db.direktor_ochir(did)
    return {"ok": True}


# ---------------------------------------------------------------- kategoriyalar

class KategoriyaKirish(BaseModel):
    nom: str
    izoh: str = ""
    tartib: int = 100


@router.get("/kategoriyalar")
def kategoriyalar(request: Request):
    if not _admin(request):
        return _403()
    return db.kategoriyalar()


@router.post("/kategoriya")
def kategoriya_yasa(s: KategoriyaKirish, request: Request):
    if not _admin(request):
        return _403()
    return {"ok": True, "id": db.kategoriya_yasa(s.nom, s.izoh, s.tartib)}


# ---------------------------------------------------------------- userlar

@router.get("/userlar")
def userlar(request: Request, q: str = "", limit: int = 100):
    if not _admin(request):
        return _403()
    return [{k: v for k, v in u.items() if k != "parol_hash"}
            for u in db.userlar(q, limit)]


class UserYangi(BaseModel):
    rol: str | None = None
    bloklangan: bool | None = None
    login: str | None = None
    parol: str | None = None
    ism: str | None = None


@router.put("/user/{uid}")
def user_yangila(uid: int, s: UserYangi, request: Request):
    a = _admin(request)
    if not a:
        return _403()
    d = {k: v for k, v in s.model_dump().items() if v is not None and k != "parol"}
    if s.parol:
        d["parol_hash"] = auth.parol_hash(s.parol)
    if s.login:
        d["login"] = s.login.strip().lower()
    db.user_yangila(uid, **d)
    return {"ok": True}


@router.get("/user/{uid}/profil")
def user_profil(uid: int, request: Request):
    """Profil 2.0: tuzilgan profil + matn + o'zgarishlar tarixi."""
    if not _admin(request):
        return _403()
    u = pg.bitta_d(
        "SELECT id, ism, username, profil, profil_jsonb, profil_tarix FROM userlar "
        "WHERE id=%s", uid)
    if not u:
        return JSONResponse({"xato": "topilmadi"}, status_code=404)
    from . import tanishuv
    u["tavsif"] = tanishuv.matn_yasa(u["profil_jsonb"] or {})
    return u


@router.post("/impersonate/{uid}")
def impersonate(uid: int, request: Request):
    """Admin boshqa user nomidan kiradi (twin egasi akkauntini sozlash uchun)."""
    a = _admin(request)
    if not a:
        return _403()
    u = db.user_ol(uid)
    if not u:
        return JSONResponse({"xato": "topilmadi"}, status_code=404)
    r = JSONResponse({"ok": True, "user": {"id": u["id"], "ism": u["ism"],
                                           "rol": u["rol"]}})
    r.set_cookie(COOKIE, db.sessiya_yasa(u["id"], impersonator_id=a["id"]),
                 max_age=db.SESSIYA_KUN * 86400, httponly=True, samesite="lax")
    return r


# ---------------------------------------------------------------- jobs monitor

@router.get("/jobs")
def jobs_royxat(request: Request, holat: str = "", limit: int = 50):
    if not _admin(request):
        return _403()
    if holat:
        return pg.hammasi_d(
            """SELECT id, tur, holat, user_id, twin_id, urinish, xato,
                      yaratilgan, boshlangan, tugagan
               FROM jobs WHERE holat=%s ORDER BY id DESC LIMIT %s""", holat, limit)
    return pg.hammasi_d(
        """SELECT id, tur, holat, user_id, twin_id, urinish, xato,
                  yaratilgan, boshlangan, tugagan
           FROM jobs ORDER BY id DESC LIMIT %s""", limit)


@router.get("/job/{jid}")
def job_ol(jid: int, request: Request):
    if not _admin(request):
        return _403()
    from . import jobs as J
    h = J.holat(jid)
    return h or JSONResponse({"xato": "topilmadi"}, status_code=404)


# ---------------------------------------------------------------- moliya
# Bu bo'limda LLM yo'q: barcha raqamlar `xarajatlar`/`tolovlar` jadvallaridan.

@router.get("/moliya")
def moliya(request: Request, kun: int = 30):
    if not _admin(request):
        return _403()
    d = pul.moliya_xulosa(max(1, min(365, kun)))
    d["provayderlar"] = tolov.sozlama_holati()      # sirlar emas, faqat bor/yo'q
    return d


@router.get("/xarajatlar")
def xarajatlar(request: Request, user_id: int = 0, majlis_id: int = 0,
               limit: int = 100):
    """Prompt darajasida drill-down."""
    if not _admin(request):
        return _403()
    shart, args = [], []
    if user_id:
        shart.append("x.user_id=%s")
        args.append(user_id)
    if majlis_id:
        shart.append("x.majlis_id=%s")
        args.append(majlis_id)
    w = ("WHERE " + " AND ".join(shart)) if shart else ""
    return pg.hammasi_d(
        f"""SELECT x.id, x.vaqt, x.user_id, x.majlis_id, x.job_id, x.bosqich,
                   x.model, x.kirish_tok, x.chiqish_tok, x.narx_usd, u.ism
            FROM xarajatlar x LEFT JOIN userlar u ON u.id = x.user_id
            {w} ORDER BY x.id DESC LIMIT %s""", *args, max(1, min(500, limit)))


# ---------------------------------------------------------------- planlar

class PlanKirish(BaseModel):
    kod: str
    nom: str
    tavsif: str = ""
    oylik_narx_som: int = 0
    kvota_usd: float = 0
    kun_soni: int = 30
    twinlar: list[int] = []
    funksiyalar: list[str] = []
    faol: bool = False
    tartib: int = 100


@router.get("/planlar")
def planlar(request: Request):
    if not _admin(request):
        return _403()
    return pul.planlar(faqat_faol=False)


@router.post("/plan")
def plan_yasa(s: PlanKirish, request: Request):
    if not _admin(request):
        return _403()
    r = pg.bitta(
        """INSERT INTO planlar(kod, nom, tavsif, oylik_narx_som, kvota_usd,
                               kun_soni, twinlar, funksiyalar, faol, tartib)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT(kod) DO UPDATE SET nom=EXCLUDED.nom RETURNING id""",
        s.kod.strip().lower(), s.nom, s.tavsif, s.oylik_narx_som, s.kvota_usd,
        s.kun_soni, s.twinlar, s.funksiyalar, s.faol, s.tartib)
    return {"ok": True, "id": r[0]}


class PlanYangi(BaseModel):
    nom: str | None = None
    tavsif: str | None = None
    oylik_narx_som: int | None = None
    kvota_usd: float | None = None
    kun_soni: int | None = None
    twinlar: list[int] | None = None
    funksiyalar: list[str] | None = None
    faol: bool | None = None
    tartib: int | None = None


@router.put("/plan/{pid}")
def plan_yangila(pid: int, s: PlanYangi, request: Request):
    if not _admin(request):
        return _403()
    ruxsat = {"nom", "tavsif", "oylik_narx_som", "kvota_usd", "kun_soni",
              "twinlar", "funksiyalar", "faol", "tartib"}
    d = {k: v for k, v in s.model_dump().items() if v is not None and k in ruxsat}
    if not d:
        return {"ok": True}
    qismlar = ", ".join(f"{k}=%s" for k in d)
    pg.bajar(f"UPDATE planlar SET {qismlar} WHERE id=%s", *d.values(), pid)
    return {"ok": True}


# ---------------------------------------------------------------- obunalar / to'lovlar

@router.get("/obunalar")
def obunalar(request: Request, limit: int = 100):
    if not _admin(request):
        return _403()
    return pg.hammasi_d(
        """SELECT o.*, p.nom AS plan_nom, u.ism, u.username
           FROM obunalar o JOIN planlar p ON p.id = o.plan_id
           LEFT JOIN userlar u ON u.id = o.user_id
           ORDER BY o.id DESC LIMIT %s""", max(1, min(500, limit)))


class QoldaObuna(BaseModel):
    user_id: int
    plan_id: int


@router.post("/obuna")
def obuna_qolda(s: QoldaObuna, request: Request):
    """Qo'lda obuna berish (naqd to'lov, sovg'a, sinov). To'lov yozuvi bilan."""
    a = _admin(request)
    if not a:
        return _403()
    p = pul.plan_ol(s.plan_id)
    if not p:
        return JSONResponse({"xato": "plan topilmadi"}, status_code=404)
    r = pg.bitta(
        """INSERT INTO tolovlar(user_id, plan_id, summa_som, provayder, izoh)
           VALUES(%s,%s,%s,'qolda',%s) RETURNING id""",
        s.user_id, s.plan_id, int(p["oylik_narx_som"]), f"admin #{a['id']}")
    obuna_id = pul.tolandi(r[0])
    return {"ok": True, "tolov_id": r[0], "obuna_id": obuna_id}


@router.delete("/obuna/{oid}")
def obuna_bekor(oid: int, request: Request):
    if not _admin(request):
        return _403()
    pg.bajar("UPDATE obunalar SET holat='bekor' WHERE id=%s", oid)
    return {"ok": True}


@router.get("/tolovlar")
def tolovlar(request: Request, limit: int = 100):
    if not _admin(request):
        return _403()
    return pg.hammasi_d(
        """SELECT t.id, t.user_id, t.plan_id, t.summa_som, t.provayder,
                  t.provayder_id, t.holat, t.izoh, t.yaratilgan, t.tolangan,
                  p.nom AS plan_nom, u.ism
           FROM tolovlar t JOIN planlar p ON p.id = t.plan_id
           LEFT JOIN userlar u ON u.id = t.user_id
           ORDER BY t.id DESC LIMIT %s""", max(1, min(500, limit)))


@router.get("/tolov/{tid}")
def tolov_bitta(tid: int, request: Request):
    """Bitta to'lov + provayderdan kelgan XOM callbacklar (audit).

    `xom` — ISHONCHSIZ matn: promptga kirmaydi, UI'da ekranlab ko'rsatiladi.
    """
    if not _admin(request):
        return _403()
    t = pg.bitta_d(
        """SELECT t.*, p.nom AS plan_nom, u.ism, u.username
           FROM tolovlar t JOIN planlar p ON p.id = t.plan_id
           LEFT JOIN userlar u ON u.id = t.user_id WHERE t.id=%s""", tid)
    if not t:
        return JSONResponse({"xato": "topilmadi"}, status_code=404)
    t["tashqi_id"] = str(t.get("tashqi_id") or "")
    return t


@router.post("/tolov/{tid}/bekor")
def tolov_bekor(tid: int, request: Request):
    """Qo'lda bekor qilish — provayder kabinetidan PUL QAYTARILGANDAN KEYIN.

    To'lovni ham, undan ochilgan obunani ham yopadi. Bu amal pulni qaytarmaydi:
    qaytarish Paylov kabinetida qilinadi, bu yerda faqat bizdagi holat
    haqiqatga moslanadi.
    """
    a = _admin(request)
    if not a:
        return _403()
    t = pul.tolov_ol(tid)
    if not t:
        return JSONResponse({"xato": "topilmadi"}, status_code=404)
    pul.bekor(tid, f"admin #{a['id']} bekor qildi")
    return {"ok": True}


# ---------------------------------------------------------------- sozlamalar

class SozlamaKirish(BaseModel):
    kalit: str
    qiymat: str


@router.get("/sozlamalar")
def sozlamalar(request: Request):
    if not _admin(request):
        return _403()
    return pg.hammasi_d("SELECT * FROM sozlamalar ORDER BY kalit")


@router.put("/sozlama")
def sozlama_yoz(s: SozlamaKirish, request: Request):
    """Faqat oldindan ma'lum kalitlar (ixtiyoriy kalit yozib bo'lmaydi)."""
    if not _admin(request):
        return _403()
    if s.kalit not in {"kvota_faol"}:
        return JSONResponse({"xato": "noma'lum kalit"}, status_code=400)
    pul.sozlama_yoz(s.kalit, s.qiymat.strip()[:200])
    return {"ok": True, "kalit": s.kalit, "qiymat": s.qiymat}


# ---------------------------------------------------------------- model narxlari

class NarxKirish(BaseModel):
    model: str
    kirish_1m_usd: float
    chiqish_1m_usd: float


@router.get("/narxlar")
def narxlar(request: Request):
    if not _admin(request):
        return _403()
    return pg.hammasi_d("SELECT * FROM model_narxlar ORDER BY model")


@router.put("/narx")
def narx_yoz(s: NarxKirish, request: Request):
    if not _admin(request):
        return _403()
    pg.bajar(
        """INSERT INTO model_narxlar(model, kirish_1m_usd, chiqish_1m_usd, yangilangan)
           VALUES(%s,%s,%s,now())
           ON CONFLICT(model) DO UPDATE SET kirish_1m_usd=EXCLUDED.kirish_1m_usd,
             chiqish_1m_usd=EXCLUDED.chiqish_1m_usd, yangilangan=now()""",
        s.model.strip()[:60], s.kirish_1m_usd, s.chiqish_1m_usd)
    pul._narx_kesh["vaqt"] = 0.0      # keshni bo'shatamiz
    return {"ok": True}
