# -*- coding: utf-8 -*-
"""Pul qatlami: xarajat daftari, bepul promptlar, kvota, obunalar.

XAVFSIZLIK — "Lethal Trifecta" (Simon Willison) qoidasi:
Agent xavfli bo'ladigan uchlik = (1) shaxsiy ma'lumotga kirish +
(2) ishonchsiz kontent + (3) tashqariga xabar yuborish imkoni.
Shu modul UCHINCHI oyoqni uzadi: BU YERDA LLM YO'Q.

  * Bu fayl `llm` ni import QILMAYDI va hech qachon qilmasligi kerak
    (sinov `sinov_3bosqich.py` da statik tekshiriladi).
  * Xarajat faqat provayder qaytargan `usage_metadata` dan yoziladi —
    modelning "men shuncha sarfladim" degan matnidan EMAS.
  * Kvota qarori faqat SQL dan chiqadi: bepul_qolgan, obunalar.tugash,
    ishlatilgan_usd. Model javobi bu qarorga ta'sir qila olmaydi.
  * Bu jadvallardagi hech narsa promptga qaytib kirmaydi.

Xarajat konteksti ContextVar orqali uzatiladi — ThreadPoolExecutor ichidagi
direktorlar ham AYNAN SHU daftarga yozishi uchun (majlis.py `copy_context`
bilan yuboradi; threading.local bunda ishlamaydi — xarajat yo'qolib ketardi).
"""
import contextvars
import time
import uuid
from decimal import Decimal

from . import pg
from .sozlama import log

BEPUL_JAMI = 3               # yangi userga beriladigan bepul prompt
TAXMINIY_MIN = 0.01          # bitta majlisning eng kam taxminiy narxi ($)
NARX_KESH_S = 300
OGOHLANTIRISH_ULUSH = 0.85   # kvotaning shu ulushidan oshsa — eslatma

# Narx bazadan o'qiladi; baza bo'sh bo'lsa shu zaxira ishlatiladi.
ZAXIRA_NARX = (0.30, 2.50)

_narx_kesh = {"vaqt": 0.0, "xarita": {}}
_KONTEKST = contextvars.ContextVar("xarajat_kontekst", default=None)


def _son(q) -> float:
    return float(q) if isinstance(q, Decimal) else float(q or 0)


# ---------------------------------------------------------------- sozlamalar

def sozlama(kalit: str, zaxira: str = "") -> str:
    r = pg.bitta("SELECT qiymat FROM sozlamalar WHERE kalit=%s", kalit)
    return r[0] if r else zaxira


def sozlama_yoz(kalit: str, qiymat: str):
    pg.bajar(
        """INSERT INTO sozlamalar(kalit, qiymat, yangilangan) VALUES(%s,%s,now())
           ON CONFLICT(kalit) DO UPDATE SET qiymat=EXCLUDED.qiymat,
                                            yangilangan=now()""", kalit, qiymat)


def kvota_faolmi() -> bool:
    """Kvota nazorati yoqilganmi. O'chiq bo'lsa xarajat yoziladi, lekin to'siq yo'q."""
    return sozlama("kvota_faol", "0") == "1"


# ---------------------------------------------------------------- xarajat konteksti

def kontekst_boshla(user_id: int | None = None, twin_id: int | None = None,
                    job_id: int | None = None, majlis_id: int | None = None) -> dict:
    """Joriy oqim uchun xarajat daftarini ochadi (job boshida chaqiriladi)."""
    k = {"user_id": user_id, "twin_id": twin_id, "job_id": job_id,
         "majlis_id": majlis_id, "royxat": []}
    _KONTEKST.set(k)
    return k


def kontekst() -> dict | None:
    return _KONTEKST.get()


def royxat() -> list[dict]:
    k = kontekst()
    return list(k["royxat"]) if k else []


def joriy_narx() -> float:
    """Shu kontekstda hozirgacha yig'ilgan narx (DB'ga yozilmagan bo'lsa ham)."""
    return round(sum(x["narx"] for x in royxat()), 6)


# ---------------------------------------------------------------- narxlar

def narxlar() -> dict[str, tuple[float, float]]:
    """model -> (kirish $/1M, chiqish $/1M). 5 daqiqalik kesh bilan."""
    if time.time() - _narx_kesh["vaqt"] < NARX_KESH_S and _narx_kesh["xarita"]:
        return _narx_kesh["xarita"]
    try:
        qatorlar = pg.hammasi(
            "SELECT model, kirish_1m_usd, chiqish_1m_usd FROM model_narxlar")
        _narx_kesh["xarita"] = {q[0]: (_son(q[1]), _son(q[2])) for q in qatorlar}
        _narx_kesh["vaqt"] = time.time()
    except Exception as e:                                    # noqa: BLE001
        log(f"model_narxlar o'qilmadi ({str(e)[:80]}) — zaxira narx")
    return _narx_kesh["xarita"]


def narx_hisobla(model: str, kirish_tok: int, chiqish_tok: int) -> float:
    kir, chiq = narxlar().get(model, ZAXIRA_NARX)
    return round(kirish_tok / 1e6 * kir + chiqish_tok / 1e6 * chiq, 8)


def xarajat_yoz(model: str, kirish_tok: int, chiqish_tok: int,
                bosqich: str = "") -> dict:
    """Bitta LLM chaqiruvini daftarga yozadi. Faqat llm.py chaqiradi."""
    narx = narx_hisobla(model, kirish_tok, chiqish_tok)
    k = kontekst()
    yozuv = {"model": model, "bosqich": bosqich, "kirish": kirish_tok,
             "chiqish": chiqish_tok, "narx": narx}
    if k is not None:
        k["royxat"].append(yozuv)
    try:
        pg.bajar(
            """INSERT INTO xarajatlar(user_id, twin_id, majlis_id, job_id,
                                      bosqich, model, kirish_tok, chiqish_tok, narx_usd)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (k or {}).get("user_id"), (k or {}).get("twin_id"),
            (k or {}).get("majlis_id"), (k or {}).get("job_id"),
            bosqich[:60], model[:60], kirish_tok, chiqish_tok, narx)
    except Exception as e:                                    # noqa: BLE001
        # Daftar yozilmasa ham asosiy ish to'xtamasin — lekin ko'rinsin.
        log(f"xarajat yozilmadi ({str(e)[:100]})")
    return yozuv


def job_narxi(job_id: int) -> float:
    r = pg.bitta("SELECT COALESCE(sum(narx_usd),0) FROM xarajatlar WHERE job_id=%s",
                 job_id)
    return round(_son(r[0]), 6) if r else 0.0


def majlisga_bogla(job_id: int, majlis_id: int):
    """Job davomidagi xarajatlarni majlisga bog'laydi (majlis id keyin ma'lum bo'ladi)."""
    pg.bajar("UPDATE xarajatlar SET majlis_id=%s WHERE job_id=%s AND majlis_id IS NULL",
             majlis_id, job_id)


def taxminiy_narx() -> float:
    """Keyingi majlis taxminan qancha turadi — oxirgi 20 majlis o'rtachasi."""
    r = pg.bitta("""SELECT COALESCE(avg(narx_usd),0) FROM
                      (SELECT narx_usd FROM majlislar WHERE narx_usd > 0
                       ORDER BY id DESC LIMIT 20) s""")
    return max(TAXMINIY_MIN, round(_son(r[0]) if r else 0, 6))


# ---------------------------------------------------------------- obuna holati

# Qolgan kun HAR DOIM SQL da hisoblanadi: lokal soat bilan baza soati farq qilsa
# (Railway PG masofada) chegara noto'g'ri ishlab ketardi. CEIL — "1.2 kun qoldi"
# foydalanuvchi uchun "2 kun qoldi" degani.
KUN_QOLDI = ("GREATEST(0, CEIL(EXTRACT(EPOCH FROM (o.tugash - now())) / 86400.0))::int"
             " AS kun_qoldi")


def obuna_ol(user_id: int) -> dict | None:
    """Userning faol obunasi (muddati o'tgan bo'lsa — None)."""
    return pg.bitta_d(
        f"""SELECT o.*, p.nom AS plan_nom, p.kod AS plan_kod, p.kvota_usd,
                   p.twinlar AS plan_twinlar, p.funksiyalar, p.oylik_narx_som,
                   {KUN_QOLDI}
            FROM obunalar o JOIN planlar p ON p.id = o.plan_id
            WHERE o.user_id=%s AND o.holat='faol' AND o.tugash > now()
            LIMIT 1""", user_id)


def holat(user_id: int) -> dict:
    """UI uchun to'liq manzara: bepul promptlar, obuna, kvota."""
    u = pg.bitta("SELECT bepul_qolgan FROM userlar WHERE id=%s", user_id)
    bepul = int(u[0]) if u else 0
    o = obuna_ol(user_id)
    javob = {"kvota_faol": kvota_faolmi(), "bepul_qolgan": bepul,
             "bepul_jami": BEPUL_JAMI, "obuna": None}
    if o:
        kvota = _son(o["kvota_usd"])
        ishlatilgan = _son(o["ishlatilgan_usd"])
        javob["obuna"] = {
            "plan": o["plan_nom"], "plan_kod": o["plan_kod"],
            "tugash": o["tugash"].isoformat(),
            "kun_qoldi": int(o["kun_qoldi"]),
            "kvota_usd": kvota, "ishlatilgan_usd": round(ishlatilgan, 4),
            "ulush": round(ishlatilgan / kvota, 3) if kvota > 0 else 0.0,
        }
    return javob


# ---------------------------------------------------------------- kvota darvozasi

def tekshir(user_id: int, twin_id: int | None = None) -> tuple[bool, str, str]:
    """Majlis boshlashga ruxsat bormi. (ok, kod, xabar) — hech narsa sarflamaydi.

    Tartib (rejadagi 6-bo'lim): bepul prompt -> faol obuna -> plan twin'ga
    ruxsat beradimi -> kvota yetadimi.
    """
    if not kvota_faolmi():
        return True, "nazorat_ochiq", ""

    u = pg.bitta("SELECT bepul_qolgan FROM userlar WHERE id=%s", user_id)
    if u and int(u[0]) > 0:
        return True, "bepul", ""

    o = obuna_ol(user_id)
    if not o:
        return False, "obuna_yoq", (
            f"{BEPUL_JAMI} ta bepul savolingiz tugadi. Davom etish uchun "
            f"obuna tanlang.")

    plan_twinlar = list(o["plan_twinlar"] or [])
    if twin_id and plan_twinlar and twin_id not in plan_twinlar:
        return False, "twin_ruxsat_yoq", (
            f"«{o['plan_nom']}» rejangiz bu ustozni qamrab olmaydi — "
            f"rejani kengaytiring.")

    kvota = _son(o["kvota_usd"])
    ishlatilgan = _son(o["ishlatilgan_usd"])
    if kvota > 0 and ishlatilgan + taxminiy_narx() > kvota:
        return False, "kvota_tugadi", (
            f"«{o['plan_nom']}» rejasidagi hajm tugadi "
            f"({ishlatilgan:.2f}/{kvota:.2f}). Rejani yangilang yoki "
            f"keyingi davrni kuting.")
    return True, "obuna", ""


def bepul_band(user_id: int) -> bool:
    """Bitta bepul promptni atomar band qiladi (poyga bo'lmasin). True = band qilindi."""
    if not kvota_faolmi():
        return False
    r = pg.bitta(
        """UPDATE userlar SET bepul_qolgan = bepul_qolgan - 1
           WHERE id=%s AND bepul_qolgan > 0 RETURNING bepul_qolgan""", user_id)
    return bool(r)


def bepul_qaytar(user_id: int):
    """Majlis yiqilsa bepul promptni qaytaramiz (foydalanuvchi aybdor emas)."""
    pg.bajar(
        """UPDATE userlar SET bepul_qolgan = LEAST(bepul_qolgan + 1, %s)
           WHERE id=%s""", BEPUL_JAMI, user_id)


def obuna_ishlat(user_id: int, narx: float):
    """Sarflangan $ ni faol obunaga qo'shadi."""
    if narx <= 0:
        return
    pg.bajar(
        """UPDATE obunalar SET ishlatilgan_usd = ishlatilgan_usd + %s
           WHERE user_id=%s AND holat='faol'""", narx, user_id)


def majlis_yakunla(job: dict, majlis_id: int) -> float:
    """Majlis tugagach: xarajatni bog'lash, narxni yozish, obunadan yechish."""
    jid = job["id"]
    narx = job_narxi(jid)
    majlisga_bogla(jid, majlis_id)
    pg.bajar("UPDATE majlislar SET narx_usd=%s WHERE id=%s", narx, majlis_id)
    if not (job.get("kirish") or {}).get("bepul") and job.get("user_id"):
        obuna_ishlat(job["user_id"], narx)
    return narx


# ---------------------------------------------------------------- to'lov -> obuna

def plan_ol(plan_id: int) -> dict | None:
    return pg.bitta_d("SELECT * FROM planlar WHERE id=%s", plan_id)


def planlar(faqat_faol: bool = True) -> list[dict]:
    shart = "WHERE faol = true" if faqat_faol else ""
    return pg.hammasi_d(f"SELECT * FROM planlar {shart} ORDER BY tartib, id")


def tolov_muddat_soat() -> int:
    """Kutilayotgan to'lov necha soat amal qiladi (admin sozlamasi)."""
    try:
        return max(1, int(sozlama("tolov_muddat_soat", "24")))
    except (TypeError, ValueError):
        return 24


def tolov_yasa(user_id: int, plan_id: int, provayder: str) -> dict:
    """Kutilayotgan to'lov yozuvi. Summa PLANDAN olinadi — mijoz yubormaydi.

    Muddat ham SERVERDA qo'yiladi: muddati o'tgan to'lovga callback kelsa
    qabul qilinmaydi (eski havolani qayta ishlatishga to'siq).
    """
    p = plan_ol(plan_id)
    if not p or not p["faol"]:
        raise ValueError("plan topilmadi yoki faol emas")
    if p["oylik_narx_som"] <= 0:
        raise ValueError("plan narxi belgilanmagan")
    r = pg.bitta_d(
        """INSERT INTO tolovlar(user_id, plan_id, summa_som, provayder, muddat)
           VALUES(%s,%s,%s,%s, now() + make_interval(hours => %s)) RETURNING *""",
        user_id, plan_id, int(p["oylik_narx_som"]), provayder, tolov_muddat_soat())
    return r


_TOLOV_SELECT = """SELECT t.*, p.nom AS plan_nom, p.kun_soni, p.kvota_usd,
                          (t.muddat IS NOT NULL AND t.muddat <= now()) AS muddati_otdi
                   FROM tolovlar t JOIN planlar p ON p.id = t.plan_id"""


def tolov_ol(tid: int) -> dict | None:
    return pg.bitta_d(f"{_TOLOV_SELECT} WHERE t.id=%s", tid)


def tolov_tashqi_ol(tashqi_id: str) -> dict | None:
    """To'lovni tashqi UUID bo'yicha topadi (Paylov `account.order_id`).

    Noto'g'ri formatdagi qiymat — oddiy "topilmadi", xato emas: bu yerga
    ishonchsiz tashqi matn keladi.
    """
    try:
        uuid.UUID(str(tashqi_id))
    except (TypeError, ValueError, AttributeError):
        return None
    return pg.bitta_d(f"{_TOLOV_SELECT} WHERE t.tashqi_id=%s", str(tashqi_id))


def xom_qosh(tolov_id: int, yozuv: dict):
    """Provayderdan kelgan xom so'rovni audit uchun saqlaydi.

    DIQQAT: bu JSON ishonchsiz kontent — hech qachon promptga qo'shilmaydi va
    UI'da faqat ekranlangan matn sifatida ko'rsatiladi.
    """
    import json
    pg.bajar("UPDATE tolovlar SET xom = xom || %s::jsonb WHERE id=%s",
             json.dumps([yozuv], ensure_ascii=False), tolov_id)


def tolandi(tolov_id: int, provayder_id: str = "") -> int | None:
    """To'lovni 'tolangan' qilib obunani ochadi/uzaytiradi. IDEMPOTENT.

    Qayta kelgan callback ikkinchi marta obuna bermaydi (bitta tranzaksiyada
    SELECT ... FOR UPDATE bilan qulflanadi).
    """
    with pg.ulanish() as u, u.cursor() as k:
        k.execute("""SELECT t.holat, t.user_id, t.plan_id, p.kun_soni
                     FROM tolovlar t JOIN planlar p ON p.id = t.plan_id
                     WHERE t.id=%s FOR UPDATE OF t""", (tolov_id,))
        r = k.fetchone()
        if not r:
            return None
        holat_, uid, plan_id, kun = r
        if holat_ == "tolangan":
            k.execute("SELECT id FROM obunalar WHERE tolov_id=%s LIMIT 1", (tolov_id,))
            bor = k.fetchone()
            return bor[0] if bor else None

        k.execute("""UPDATE tolovlar SET holat='tolangan', tolangan=now(),
                     provayder_id = CASE WHEN %s <> '' THEN %s ELSE provayder_id END
                     WHERE id=%s""", (provayder_id, provayder_id, tolov_id))

        # Shu planda faol obuna bo'lsa — uzaytiramiz, bo'lmasa yangisi.
        k.execute("""SELECT id FROM obunalar
                     WHERE user_id=%s AND plan_id=%s AND holat='faol'
                     FOR UPDATE""", (uid, plan_id))
        bor = k.fetchone()
        if bor:
            k.execute("""UPDATE obunalar
                         SET tugash = GREATEST(tugash, now()) + make_interval(days => %s),
                             eslatmalar = '{}', tolov_id = %s
                         WHERE id=%s RETURNING id""", (kun, tolov_id, bor[0]))
            return k.fetchone()[0]
        k.execute("""UPDATE obunalar SET holat='tugagan'
                     WHERE user_id=%s AND holat='faol'""", (uid,))
        k.execute("""INSERT INTO obunalar(user_id, plan_id, tugash, tolov_id)
                     VALUES(%s,%s, now() + make_interval(days => %s), %s)
                     RETURNING id""", (uid, plan_id, kun, tolov_id))
        return k.fetchone()[0]


def bekor(tolov_id: int, izoh: str = ""):
    """To'lovni bekor qiladi va shu to'lovdan ochilgan obunani yopadi."""
    with pg.ulanish() as u, u.cursor() as k:
        k.execute("UPDATE tolovlar SET holat='bekor', izoh=%s WHERE id=%s",
                  (izoh[:200], tolov_id))
        k.execute("UPDATE obunalar SET holat='bekor' WHERE tolov_id=%s AND holat='faol'",
                  (tolov_id,))


def tolov_tozala(yoz=log) -> dict:
    """Muddati o'tgan kutilayotgan to'lovlarni bekor qiladi. Soatlik job.

    Faqat to'lanmagan yozuvlarga tegadi — 'tolangan' holat hech qachon
    orqaga qaytmaydi (pul olingandan keyin bekor qilish faqat admin qo'li
    bilan, refunddan so'ng).
    """
    qatorlar = pg.hammasi(
        """UPDATE tolovlar SET holat='bekor',
                  izoh = CASE WHEN izoh = '' THEN 'muddati o''tdi' ELSE izoh END
           WHERE holat IN ('kutilmoqda','tayyorlangan')
             AND muddat IS NOT NULL AND muddat <= now()
           RETURNING id""")
    natija = {"bekor": len(qatorlar)}
    yoz(f"to'lov tozalash: {natija['bekor']} ta muddati o'tgan to'lov bekor qilindi")
    return natija


# ---------------------------------------------------------------- obuna nazorati (job)

def _xabar(user_id: int, matn: str):
    """TG orqali eslatma. Matn FAQAT shu koddan va DB qiymatlaridan tuziladi."""
    from . import tg
    try:
        tg.matn_yubor(user_id, matn)
    except Exception as e:                                    # noqa: BLE001
        log(f"eslatma yuborilmadi (user {user_id}): {str(e)[:80]}")


def _qoch(s: str) -> str:
    """TG HTML uchun ekranlash (plan nomi admin kiritadi — xom qo'yilmaydi)."""
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def nazorat(yoz=log) -> dict:
    """Obuna lifecycle: muddati tugaganlarni yopish + eslatmalar. Har soat job."""
    natija = {"tugadi": 0, "eslatma": 0}

    tugaganlar = pg.hammasi_d(
        """UPDATE obunalar o SET holat='tugagan'
           WHERE o.holat='faol' AND o.tugash <= now()
           RETURNING o.user_id, o.plan_id""")
    for t in tugaganlar:
        p = plan_ol(t["plan_id"]) or {}
        _xabar(t["user_id"],
               f"⏳ <b>{_qoch(p.get('nom', 'Obuna'))}</b> obunangiz muddati tugadi.\n"
               f"Davom etish uchun ilovadan rejani yangilang.")
        natija["tugadi"] += 1

    # 3 kun / 1 kun qolganda va kvota tugayotganda — bir martadan
    faollar = pg.hammasi_d(
        f"""SELECT o.id, o.user_id, o.tugash, o.ishlatilgan_usd, o.eslatmalar,
                   p.nom AS plan_nom, p.kvota_usd, {KUN_QOLDI}
            FROM obunalar o JOIN planlar p ON p.id = o.plan_id
            WHERE o.holat='faol'""")
    for o in faollar:
        yuborilgan = set(o["eslatmalar"] or [])
        kun = int(o["kun_qoldi"])
        yangi = None
        if kun <= 1 and "1kun" not in yuborilgan:
            yangi, matn = "1kun", (
                f"⚠️ <b>{_qoch(o['plan_nom'])}</b> obunangizga <b>1 kun</b> qoldi.")
        elif kun <= 3 and "3kun" not in yuborilgan:
            yangi, matn = "3kun", (
                f"🔔 <b>{_qoch(o['plan_nom'])}</b> obunangizga <b>{kun} kun</b> qoldi.")
        if yangi is None:
            kvota = _son(o["kvota_usd"])
            ishl = _son(o["ishlatilgan_usd"])
            if kvota > 0 and ishl >= kvota * OGOHLANTIRISH_ULUSH \
                    and "kvota" not in yuborilgan:
                yangi, matn = "kvota", (
                    f"📊 <b>{_qoch(o['plan_nom'])}</b> rejangiz hajmining "
                    f"{int(ishl / kvota * 100)}% ishlatildi.")
        if yangi:
            _xabar(o["user_id"], matn)
            pg.bajar("UPDATE obunalar SET eslatmalar = eslatmalar || %s WHERE id=%s",
                     [yangi], o["id"])
            natija["eslatma"] += 1

    yoz(f"obuna nazorati: {natija['tugadi']} tugadi, {natija['eslatma']} eslatma")
    return natija


# ---------------------------------------------------------------- hisobotlar (admin)

def moliya_xulosa(kun: int = 30) -> dict:
    """Admin dashboard: xarajat/daromad manzarasi."""
    x = pg.bitta_d(
        """SELECT COALESCE(sum(narx_usd),0) AS jami,
                  COALESCE(sum(narx_usd) FILTER (WHERE vaqt > now() - interval '1 day'),0) AS kun,
                  COALESCE(sum(narx_usd) FILTER (WHERE vaqt > now() - interval '30 days'),0) AS oy,
                  count(*) AS chaqiruv
           FROM xarajatlar""")
    d = pg.bitta_d(
        """SELECT COALESCE(sum(summa_som),0) AS jami,
                  count(*) AS soni
           FROM tolovlar WHERE holat='tolangan'""")
    return {
        "xarajat_jami_usd": round(_son(x["jami"]), 4),
        "xarajat_kun_usd": round(_son(x["kun"]), 4),
        "xarajat_oy_usd": round(_son(x["oy"]), 4),
        "chaqiruvlar": int(x["chaqiruv"]),
        "daromad_som": int(d["jami"]), "tolovlar": int(d["soni"]),
        "obuna_faol": pg.bitta(
            "SELECT count(*) FROM obunalar WHERE holat='faol' AND tugash > now()")[0],
        "kvota_faol": kvota_faolmi(),
        "taxminiy_majlis_usd": taxminiy_narx(),
        "kunlar": pg.hammasi_d(
            """SELECT date_trunc('day', vaqt)::date AS kun,
                      round(sum(narx_usd), 4) AS narx, count(*) AS soni
               FROM xarajatlar WHERE vaqt > now() - make_interval(days => %s)
               GROUP BY 1 ORDER BY 1""", kun),
        "modellar": pg.hammasi_d(
            """SELECT model, round(sum(narx_usd), 4) AS narx, count(*) AS soni,
                      sum(kirish_tok) AS kirish, sum(chiqish_tok) AS chiqish
               FROM xarajatlar WHERE vaqt > now() - make_interval(days => %s)
               GROUP BY 1 ORDER BY 2 DESC""", kun),
        "userlar": pg.hammasi_d(
            """SELECT x.user_id, u.ism, u.username,
                      round(sum(x.narx_usd), 4) AS narx, count(*) AS chaqiruv
               FROM xarajatlar x LEFT JOIN userlar u ON u.id = x.user_id
               WHERE x.vaqt > now() - make_interval(days => %s)
               GROUP BY 1,2,3 ORDER BY 4 DESC LIMIT 20""", kun),
    }
