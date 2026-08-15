# -*- coding: utf-8 -*-
"""Tizimlashtirish halqasi sinovlari (TIZIM_REJA.md, 13-bo'lim).

    python -m platforma.sinov_tizim

Chiqish kodi: bironta sinov yiqilsa 1.

BAZAGA TEGISH QOIDASI — bu skript LOKALDA ham PROD bazaga ulanishi mumkin
(CLAUDE.md ogohlantirishi). Shuning uchun:

  * O'zining sinov useri (`tg_id = -999101`) va sinov twinini
    (`slug = 'sinov-tizim'`) yaratadi, oxirida HAMMASINI o'chiradi.
  * HECH QANDAY JOB yaratmaydi: `jobs.qoshish` shu jarayonda sanagichga
    almashtiriladi — bulutdagi worker sinov ishini olib pul sarflamaydi.
  * LLM chaqirilmaydi: sinovlar faqat MEXANIKA qatlamini tekshiradi (foiz,
    oq ro'yxatlar, SMART qoidalari, yig'indilar, holat mashinasi).
"""
import os
import sys

# KENGASH_BOT_OFF: `platforma.web` import qilinganda Telegram webhook'i
# lokalga ko'chib, prod bot o'lib qolmasin (CLAUDE.md).
os.environ["KENGASH_BOT_OFF"] = "1"

from fastapi.testclient import TestClient           # noqa: E402

from . import db, jobs, pg, skilllar, tizim, web    # noqa: E402

KLIENT = TestClient(web.app)
OK, YIQILDI = [], []
JOBLAR = []                       # ushlab qolingan job chaqiruvlari

TG = -999101
SLUG = "sinov-tizim"


def tek(shart, nom: str, izoh: str = ""):
    belgi = "OK  " if shart else "XATO"
    print(f"  [{belgi}] {nom}" + (f" — {izoh}" if izoh else ""))
    (OK if shart else YIQILDI).append(nom)
    return bool(shart)


def bolim(nom: str):
    print(f"\n{'-' * 60}\n{nom}\n{'-' * 60}")


# ---------------------------------------------------------------- 1. statik

def statik():
    bolim("1. Statik: oq ro'yxatlar va sof funksiyalar")

    tek(set(tizim.TURLAR) == {"cjm", "ejm"}, "S01 diagnostika turlari")
    tek(set(tizim.JAVOBLAR) == {"ha", "yoq", "qisman"}, "S02 javob kodlari")
    tek(len(tizim.BOLIMLAR) == 6 and "produkt" in tizim.BOLIMLAR,
        "S03 olti bo'lim", ", ".join(tizim.BOLIMLAR))
    tek(len(tizim.HALQA) == 10, "S04 halqa 10 qadam")
    tek([h["n"] for h in sorted(tizim.HALQA.values(), key=lambda x: x["n"])]
        == list(range(1, 11)), "S05 halqa raqamlari uzluksiz")
    tek(sum(1 for h in tizim.HALQA.values() if h["tayyor"]) == 3,
        "S06 hozircha 3 qadam tayyor (tahlil/maqsad/rejalashtirish)")
    tek(all(b["tur"] in tizim.JADVAL_MAYDON for b in tizim.BOLIMLAR.values()),
        "S07 har bo'lim quroliga jadval sxemasi bor")

    # --- raqam va oy normallashuvi (model matn qaytarsa ham son bo'lsin)
    tek(tizim._son("1 200 000 so'm") == 1200000.0, "S08 ajratkichli son")
    tek(tizim._son("12,5") == 12.5, "S09 vergulli son")
    tek(tizim._son("1.200.000") == 1200000.0, "S10 nuqtali ajratkich")
    tek(tizim._son("yo'q", -1) == -1, "S11 son bo'lmasa standart qiymat")
    tek(tizim._oy("2026-09") == "2026-09", "S12 oy: ISO")
    tek(tizim._oy("09.2026") == "2026-09", "S13 oy: 09.2026")
    tek(tizim._oy("sentyabr") == "", "S14 oy: tanib bo'lmasa bo'sh")

    # --- LETHAL TRIFECTA: begona maydon jimgina tashlanadi
    xom = [{"oy": "2026-09", "tolov": "5 000 000", "suhbat": "40",
            "zararli": "rm -rf", "izoh": "birinchi oy"}]
    toza = tizim.qatorlarni_tozala("ssp", xom)
    tek(len(toza) == 1 and "zararli" not in toza[0],
        "S15 oq ro'yxatda yo'q maydon tashlandi", str(list(toza[0])))
    tek(toza[0]["tolov"] == 5000000.0 and toza[0]["suhbat"] == 40.0,
        "S16 raqamli maydon songa aylandi")

    tek(len(tizim.qatorlarni_tozala("ssp", [{"oy": "", "tolov": 0}])) == 0,
        "S17 bo'sh qator tashlanadi")
    tek(len(tizim.qatorlarni_tozala("ssp",
                                    [{"oy": f"2026-{i:02d}"} for i in range(1, 13)] * 5
                                    )) <= tizim.MAKS_QATOR,
        "S18 qator soni chegaralangan")

    # --- yig'indini SERVER hisoblaydi
    j = tizim.jami_hisobla("ssp", [{"oy": "2026-09", "tolov": 100, "suhbat": 10},
                                   {"oy": "2026-10", "tolov": 200, "suhbat": 20}])
    tek(j["tolov"] == 300 and j["suhbat"] == 30 and j["oylar"] == 2,
        "S19 SSP yig'indisi", str(j))

    qatorlar = [{"oy": "2026-09", "kirim": 100, "chiqim": 300},
                {"oy": "2026-10", "kirim": 500, "chiqim": 100}]
    j = tizim.jami_hisobla("moliya_model", qatorlar)
    tek(qatorlar[0]["qoldiq"] == -200 and qatorlar[1]["qoldiq"] == 200,
        "S20 moliya modeli qoldiqni to'playdi", str([q["qoldiq"] for q in qatorlar]))
    tek(j["eng_past_qoldiq"] == -200 and j["chidam_oy"] == 1,
        "S21 eng past qoldiq va chidam oyi", str(j))


# ---------------------------------------------------------------- 2. SMART

def smart():
    bolim("2. SMART mezonlari — server qoidasi (LLM emas)")

    asos = {"id": 0, "diagnostika_id": 7, "tafsilot": {
        "matn": "Oylik sotuvni 40 mln so'mga yetkazish",
        "olchov": {"birlik": "mln so'm", "qiymat": 40, "hozir": 20},
        "muddat": (pg.bitta("SELECT (now() + interval '120 days')::date")[0]
                   ).isoformat(),
        "byudjet": 15000000, "resurs": "3 sotuvchi, CRM bor",
        "bosqichlar": ["Sotuv"]}}
    s = tizim.smart_bahola(asos)
    tek(s["hammasi"], "S22 to'liq karta — hamma mezon yashil",
        ", ".join(k for k, v in s.items() if k != "hammasi" and not v["ok"]))

    # Audiodagi "Elon Musk" filtri: hozirgi holatdan 10 barobardan katta maqsad
    katta = {**asos, "tafsilot": {**asos["tafsilot"],
                                  "olchov": {"birlik": "mln so'm", "qiymat": 5000,
                                             "hozir": 20}}}
    s2 = tizim.smart_bahola(katta)
    tek(not s2["erishsa"]["ok"] and not s2["hammasi"],
        "S23 resursga sig'maydigan maqsad qizil", s2["erishsa"]["izoh"][:60])

    tek(not tizim.smart_bahola(
        {**asos, "tafsilot": {**asos["tafsilot"], "matn": "ko'proq sotamiz"}}
    )["aniq"]["ok"], "S24 sonsiz maqsad — 'aniq' qizil")

    tek(not tizim.smart_bahola(
        {**asos, "tafsilot": {**asos["tafsilot"], "muddat": "2020-01-01"}}
    )["muddat"]["ok"], "S25 o'tgan sana — 'muddat' qizil")

    tek(not tizim.smart_bahola({**asos, "diagnostika_id": None})["ahamiyat"]["ok"],
        "S26 diagnostikasiz maqsad — 'ahamiyat' qizil")

    tek(not tizim.smart_bahola(
        {**asos, "tafsilot": {**asos["tafsilot"], "byudjet": 0}}
    )["erishsa"]["ok"], "S27 byudjetsiz maqsad — 'erishsa' qizil")


# ---------------------------------------------------------------- 3. bank

def bank():
    bolim("3. Savol banki")

    holat = tizim.bank_holati()
    jami = sum(r["soni"] for r in holat)
    tek(jami > 0, "S28 savol banki bo'sh emas", f"{jami} savol")
    if not jami:
        return
    turlar = {r["tur"]: r["soni"] for r in holat}
    tek(turlar.get("cjm", 0) == 560, "S29 CJM 560 savol", str(turlar.get("cjm")))
    tek(turlar.get("ejm", 0) == 366, "S30 EJM 366 savol", str(turlar.get("ejm")))
    tek(jami == 926, "S31 jami 926 savol", str(jami))

    s = tizim.savollar("cjm")
    onlayn = tizim.savollar("cjm", onlayn=True)
    tek(len(onlayn) < len(s), "S32 onlayn rejimda 'Muhit' chiqmaydi",
        f"{len(s)} -> {len(onlayn)}")
    tek(all(not x["ixtiyoriy"] for x in onlayn),
        "S33 onlayn ro'yxatda ixtiyoriy savol yo'q")


# ---------------------------------------------------------------- 4. diagnostika

def diagnostika():
    bolim("4. Diagnostika: foiz formulasi va fokus qoidasi")

    if not tizim.savollar("ejm"):
        tek(False, "S34 savol banki yuklanmagan — diagnostika sinovlari o'tkazildi")
        return None

    d = tizim.diag_boshla(USER_ID, TWIN_ID, "ejm", "Sinov korxona")
    tek(d["holat"] == "toldirilmoqda" and d["foiz"] is None,
        "S34 diagnostika ochildi")

    try:
        tizim.diag_boshla(USER_ID, TWIN_ID, "ejm", "Ikkinchi")
        tek(False, "S35 fokus qoidasi: ikkinchi diagnostika ochilmaydi")
    except tizim.Fokus:
        tek(True, "S35 fokus qoidasi: ikkinchi diagnostika ochilmaydi")

    savollar = tizim.savollar("ejm")
    jami = len(savollar)

    # 10 ta "ha", 5 ta "yoq", 5 ta "qisman"
    for x in savollar[:10]:
        tizim.javob_yoz(d, x["id"], "ha", sifat=2)
    for x in savollar[10:15]:
        tizim.javob_yoz(d, x["id"], "yoq")
    o = None
    for x in savollar[15:20]:
        o = tizim.javob_yoz(d, x["id"], "qisman")

    kutilgan = round(100 * 10 / jami)
    tek(o["foiz"] == kutilgan, "S36 foiz = ha / BARCHA savollar (Excel formulasi)",
        f"{o['foiz']}% (kutilgan {kutilgan}%)")
    tek(o["qisman"] == 5, "S37 'qisman' alohida sanaladi, foizga kirmaydi")
    tek(o["javobli"] == 20 and o["progress"] == round(100 * 20 / jami),
        "S38 progress javob berilganlar bo'yicha")
    tek(o["sifat_ortacha"] == 2.0, "S39 sifat o'rtachasi", str(o["sifat_ortacha"]))

    # Javobsiz savol "yo'q" kabi hisoblanadi (bo'sh katak "Ha" emas)
    tek(o["ha"] == 10 and o["jami"] == jami,
        "S40 javobsiz savol maxrajda qoladi", f"{o['ha']}/{o['jami']}")

    try:
        tizim.javob_yoz(d, savollar[0]["id"], "balki")
        tek(False, "S41 begona javob kodi rad etiladi")
    except ValueError:
        tek(True, "S41 begona javob kodi rad etiladi")

    begona = tizim.savollar("cjm")
    if begona:
        try:
            tizim.javob_yoz(d, begona[0]["id"], "ha")
            tek(False, "S42 boshqa turdagi savolga javob yozilmaydi")
        except ValueError:
            tek(True, "S42 boshqa turdagi savolga javob yozilmaydi")

    # Sifat faqat "ha" bilan; begona daraja tashlanadi
    tizim.javob_yoz(d, savollar[0]["id"], "ha", sifat=99)
    j = tizim.javoblar(d["id"])
    tek(j[savollar[0]["id"]]["sifat"] is None,
        "S43 oq ro'yxatdan tashqari sifat darajasi tashlandi")

    # Yakunlash -> job (ushlab qolinadi)
    JOBLAR.clear()
    n = tizim.diag_yakunla(d)
    tek(n["holat"] == "xulosa_kutilmoqda" and len(JOBLAR) == 1
        and JOBLAR[0][0] == "tizim_xulosa", "S44 yakunlash xulosa jobini qo'ydi")

    tek(tizim.diag_ol(d["id"])["foiz"] == kutilgan,
        "S45 foiz bazaga yozildi")

    # Job yiqilsa ma'lumot yo'qolmaydi (CLAUDE.md 6-qoidasi)
    tizim.diag_qaytar(d["id"])
    qaytgan = tizim.diag_ol(d["id"])
    tek(qaytgan["holat"] == "toldirilmoqda" and qaytgan["foiz"] == kutilgan,
        "S46 job yiqilsa diagnostika qaytadi, javoblar joyida")
    tek(len(tizim.javoblar(d["id"])) == 20, "S47 javoblar yo'qolmadi")
    return d


# ---------------------------------------------------------------- 5. maqsad + reja

def maqsad_reja(d):
    bolim("5. Maqsad va bo'lim rejalari")

    m = tizim.maqsad_boshla(USER_ID, TWIN_ID, d["id"] if d else None, "Sinov korxona")
    tek(m["holat"] == "intervyu", "S48 maqsad ochildi")

    try:
        tizim.maqsad_boshla(USER_ID, TWIN_ID, None, "Ikkinchi")
        tek(False, "S49 fokus qoidasi: ikkinchi maqsad ochilmaydi")
    except tizim.Fokus:
        tek(True, "S49 fokus qoidasi: ikkinchi maqsad ochilmaydi")

    # Qizil karta -> tasdiqlash MUMKIN EMAS (server qoidasi)
    m = tizim.maqsad_saqla(m, {"matn": "ko'proq sotamiz"})
    tek(m["holat"] == "intervyu", "S50 to'liqsiz karta 'intervyu' da qoladi")
    JOBLAR.clear()
    try:
        tizim.maqsad_tasdiqla(m)
        tek(False, "S51 SMART qizil bo'lsa tasdiqlanmaydi")
    except ValueError:
        tek(len(JOBLAR) == 0, "S51 SMART qizil bo'lsa tasdiqlanmaydi (job ham yo'q)")

    sana = pg.bitta("SELECT (now() + interval '150 days')::date")[0].isoformat()
    m = tizim.maqsad_saqla(m, {
        "matn": "Oylik sotuvni 40 mln so'mga yetkazish",
        "olchov": {"birlik": "mln so'm", "qiymat": "40", "hozir": "20"},
        "muddat": sana, "byudjet": "15000000",
        "resurs": "3 sotuvchi, CRM bor", "bosqichlar": ["Tanilish"]})
    tek(m["holat"] == "tekshirildi", "S52 to'liq karta 'tekshirildi' ga o'tdi",
        m["holat"])
    tek(m["tafsilot"]["olchov"]["qiymat"] == 40.0,
        "S53 matn ko'rinishidagi son songa aylandi")

    JOBLAR.clear()
    n = tizim.maqsad_tasdiqla(m)
    tek(n["holat"] == "faol" and len(JOBLAR) == 6,
        "S54 tasdiqlashda 6 bo'lim jobi qo'yildi", f"{len(JOBLAR)} job")
    tek({j[1]["bolim"] for j in JOBLAR} == set(tizim.BOLIMLAR),
        "S55 har bo'lim uchun bittadan job")

    # --- reja qatorlari va SSP -> moliya ko'chirishi
    pg.bajar("""INSERT INTO bolim_rejalar(maqsad_id, bolim, tur, jadval, jami)
                VALUES(%s,'sotuv','ssp','[]','{}')
                ON CONFLICT (maqsad_id, bolim, tur) DO NOTHING""", m["id"])
    pg.bajar("""INSERT INTO bolim_rejalar(maqsad_id, bolim, tur, jadval, jami)
                VALUES(%s,'moliya','moliya_model','[]','{}')
                ON CONFLICT (maqsad_id, bolim, tur) DO NOTHING""", m["id"])
    ssp = pg.bitta_d("SELECT * FROM bolim_rejalar WHERE maqsad_id=%s AND tur='ssp'",
                     m["id"])
    ssp = tizim.reja_saqla(ssp, [{"oy": "2026-09", "tolov": 10_000_000, "suhbat": 50},
                                 {"oy": "2026-10", "tolov": 20_000_000, "suhbat": 80}])
    tek(ssp["jami"]["tolov"] == 30_000_000,
        "S56 reja yig'indisini server hisobladi", str(ssp["jami"]))

    mol = pg.bitta_d("SELECT * FROM bolim_rejalar WHERE maqsad_id=%s "
                     "AND tur='moliya_model'", m["id"])
    tizim.reja_saqla(mol, [{"oy": "2026-09", "kirim": 0, "chiqim": 4_000_000},
                           {"oy": "2026-10", "kirim": 0, "chiqim": 4_000_000}])
    tizim.reja_tasdiqla(ssp)
    mol = pg.bitta_d("SELECT * FROM bolim_rejalar WHERE maqsad_id=%s "
                     "AND tur='moliya_model'", m["id"])
    kirim = {q["oy"]: q["kirim"] for q in mol["jadval"]}
    tek(kirim.get("2026-09") == 10_000_000 and kirim.get("2026-10") == 20_000_000,
        "S57 SSP to'lovlari moliya modeliga SERVER tomonidan ko'chdi", str(kirim))
    tek(mol["jami"]["qoldiq"] == 22_000_000,
        "S58 moliya modeli qoldiqni qayta hisobladi", str(mol["jami"]))
    return m


# ---------------------------------------------------------------- 6. API

def api(d, m):
    bolim("6. API yuzasi va ruxsatlar")

    KLIENT.cookies.clear()
    r = KLIENT.get("/api/tizim")
    tek(r.status_code == 401, "S59 kirishsiz 401", str(r.status_code))

    KLIENT.cookies.set(web.COOKIE, TOKEN)
    r = KLIENT.get(f"/api/tizim?twin_id={TWIN_ID}")
    tek(r.status_code == 200 and "halqa" in r.json(),
        "S60 manzara qaytdi", str(r.status_code))
    if r.status_code == 200:
        j = r.json()
        tek(len(j["halqa"]) == 10 and len(j["bolimlar"]) == 6,
            "S61 manzarada halqa va bo'limlar")

    if d:
        r = KLIENT.get(f"/api/tizim/savollar?diagnostika_id={d['id']}")
        tek(r.status_code == 200 and len(r.json()["savollar"]) > 300,
            "S62 savol ro'yxati + javoblar bitta so'rovda")

        r = KLIENT.post("/api/tizim/javob", json={
            "diagnostika_id": d["id"], "savol_id": r.json()["savollar"][0]["id"],
            "javob": "xato_kod"})
        tek(r.status_code == 400, "S63 begona javob kodi API'da 400",
            str(r.status_code))

    # Begona foydalanuvchi ko'ra olmaydi
    KLIENT.cookies.set(web.COOKIE, TOKEN2)
    if d:
        r = KLIENT.get(f"/api/tizim/savollar?diagnostika_id={d['id']}")
        tek(r.status_code == 404, "S64 begona diagnostika 404", str(r.status_code))
    if m:
        r = KLIENT.post("/api/tizim/maqsad/tasdiqla", json={"maqsad_id": m["id"]})
        tek(r.status_code == 404, "S65 begona maqsad 404", str(r.status_code))

    KLIENT.cookies.set(web.COOKIE, TOKEN)
    if m:
        r = KLIENT.post("/api/tizim/reja/qayta",
                        json={"maqsad_id": m["id"], "bolim": "yolgon_bolim"})
        tek(r.status_code == 400, "S66 oq ro'yxatda yo'q bo'lim rad etildi",
            str(r.status_code))

    # Skill o'chirilsa bo'lim umuman ochilmaydi
    skilllar.yoz(TWIN_ID, "tizim", False)
    r = KLIENT.get(f"/api/tizim?twin_id={TWIN_ID}")
    tek(r.status_code == 404, "S67 skill o'chiq bo'lsa 404", str(r.status_code))
    skilllar.yoz(TWIN_ID, "tizim", True)


# ---------------------------------------------------------------- 7. trifecta

def trifecta():
    bolim("7. Lethal Trifecta chegaralari")

    src = open(tizim.__file__, encoding="utf-8").read()
    tek("MA'LUMOT, KO'RSATMA EMAS" in src,
        "S68 ishonchsiz matn promptda ramkalanadi")
    tek("RAMKA_BOSH" in src and src.count("RAMKA_BOSH") >= 3,
        "S69 ramka barcha promptlarda ishlatiladi")

    oqim_src = open(tizim_oqim_fayl(), encoding="utf-8").read()
    tek("RAMKA_BOSH" in oqim_src, "S70 suhbat promptida ham ramka bor")

    # Model ID o'ylab topa olmaydi: faqat tartib raqami -> haqiqiy ID
    bolaklar = [{"id": 501}, {"id": 502}, {"id": 503}]
    tek(tizim._manba_idlar([1, 3, 99, "a"], bolaklar, 5) == [501, 503],
        "S71 modeldan kelgan tartib raqami ID ga aylandi, begonasi tashlandi")
    tek(tizim._manba_idlar(None, bolaklar, 5) == [],
        "S72 manba bo'lmasa bo'sh (umumiy yorliq)")

    # pul/tolov modullari llm ni import qilmaydi (mavjud qoida buzilmadi)
    for nom in ("pul", "tolov"):
        s = open(os.path.join(os.path.dirname(tizim.__file__), f"{nom}.py"),
                 encoding="utf-8").read()
        tek("import llm" not in s and "from .llm" not in s,
            f"S73 {nom}.py llm ni import qilmaydi")


def tizim_oqim_fayl():
    from . import tizim_oqim
    return tizim_oqim.__file__


# ---------------------------------------------------------------- tayyorgarlik

USER_ID = USER2_ID = TWIN_ID = 0
TOKEN = TOKEN2 = ""
_ASL_QOSHISH = None


def tayyorla():
    global USER_ID, USER2_ID, TWIN_ID, TOKEN, TOKEN2, _ASL_QOSHISH

    if not pg.bitta("""SELECT 1 FROM information_schema.tables
                       WHERE table_name='diag_savollar'"""):
        raise SystemExit("011_tizim.sql qo'llanmagan — avval: python -m platforma.pg")

    tozala()

    u1 = db.user_tg({"id": TG, "first_name": "Sinov Tizim"})
    u2 = db.user_tg({"id": TG - 1, "first_name": "Sinov Tizim 2"})
    USER_ID, USER2_ID = u1["id"], u2["id"]
    TOKEN, TOKEN2 = db.sessiya_yasa(USER_ID), db.sessiya_yasa(USER2_ID)
    TWIN_ID = db.twin_yasa("Sinov Tizim Twin", SLUG, egasi_id=USER_ID)
    skilllar.yoz(TWIN_ID, "tizim", True)

    # JOB YARATILMAYDI: bulutdagi worker sinov ishini olib pul sarflamasin.
    _ASL_QOSHISH = jobs.qoshish

    def ushla(tur, kirish=None, **kw):
        JOBLAR.append((tur, kirish or {}, kw))
        return -1
    jobs.qoshish = ushla
    tizim.jobs.qoshish = ushla
    web.jobs.qoshish = ushla


def tozala():
    """Sinov qoldiqlarini o'chiradi (FK tartibida)."""
    pg.bajar("""DELETE FROM diagnostikalar WHERE user_id IN
                (SELECT id FROM userlar WHERE tg_id IN (%s,%s))""", TG, TG - 1)
    pg.bajar("""DELETE FROM tizim_maqsadlar WHERE user_id IN
                (SELECT id FROM userlar WHERE tg_id IN (%s,%s))""", TG, TG - 1)
    pg.bajar("""DELETE FROM majlislar WHERE user_id IN
                (SELECT id FROM userlar WHERE tg_id IN (%s,%s))""", TG, TG - 1)
    pg.bajar("""DELETE FROM suhbatlar WHERE user_id IN
                (SELECT id FROM userlar WHERE tg_id IN (%s,%s))""", TG, TG - 1)
    pg.bajar("DELETE FROM twinlar WHERE slug=%s", SLUG)
    pg.bajar("DELETE FROM userlar WHERE tg_id IN (%s,%s)", TG, TG - 1)


def tiklash():
    if _ASL_QOSHISH:
        jobs.qoshish = _ASL_QOSHISH
        tizim.jobs.qoshish = _ASL_QOSHISH
        web.jobs.qoshish = _ASL_QOSHISH


# ---------------------------------------------------------------- main

def main() -> int:
    print("=" * 60)
    print("TIZIMLASHTIRISH HALQASI — SINOVLAR")
    print("=" * 60)
    statik()
    smart()
    try:
        tayyorla()
        bank()
        d = diagnostika()
        m = maqsad_reja(d)
        api(d, m)
        trifecta()
    finally:
        tiklash()
        try:
            tozala()
            print("\n  sinov ma'lumotlari tozalandi")
        except Exception as e:                               # noqa: BLE001
            print(f"\n  DIQQAT: tozalash yiqildi — {str(e)[:200]}")

    jami = len(OK) + len(YIQILDI)
    print(f"\n{'=' * 60}\nNATIJA: {len(OK)}/{jami} yashil")
    if YIQILDI:
        print("Yiqilganlar:")
        for n in YIQILDI:
            print(f"  - {n}")
        return 1
    print("Hammasi yashil.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
