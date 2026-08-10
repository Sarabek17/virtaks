# -*- coding: utf-8 -*-
"""Paylov to'lov yo'lining sinovlari (PAYLOV_REJA.md, 10-bo'lim).

    python -m platforma.sinov_paylov

Chiqish kodi: bironta sinov yiqilsa 1.

BAZAGA TEGISH QOIDASI — bu skript LOKALDA ham PROD bazaga ulanishi mumkin
(CLAUDE.md ogohlantirishi). Shuning uchun:

  * O'zining sinov useri (`tg_id = -999001/-999002`) va sinov planini
    (`kod = 'sinov_paylov'`) yaratadi, oxirida HAMMASINI o'chiradi.
  * Hech qanday JOB yaratmaydi — bulutdagi worker pul sarflamaydi.
  * `sozlamalar` jadvalidagi umumiy kalitlarga (`kvota_faol`) TEGMAYDI:
    kvota darvozasi `pul.kvota_faolmi` ni jarayon ichida almashtirib
    sinaladi, ya'ni boshqa foydalanuvchilarga ta'sir qilmaydi.
  * Telegram'ga xabar ketmaydi (`_obuna_xabar` va `monitoring.xato`
    sanagichga almashtiriladi).
"""
import base64
import os
import sys
import threading
import uuid
from urllib.parse import parse_qs, unquote

# --- Muhitni import'dan OLDIN sozlaymiz -------------------------------------
# KENGASH_BOT_OFF: `platforma.web` import qilinganda Telegram webhook'i
# lokalga ko'chib, prod bot o'lib qolmasin (CLAUDE.md).
os.environ["KENGASH_BOT_OFF"] = "1"
os.environ["PAYLOV_MERCHANT_ID"] = "2ef4a896-8da2-48a4-9af3-2607e69210ec"
os.environ["PAYLOV_CALLBACK_LOGIN"] = "sinov_login"
os.environ["PAYLOV_CALLBACK_PAROL"] = "sinov-parol-9f3a"
os.environ["PAYLOV_TIYINDA"] = "1"
os.environ["PAYLOV_IP"] = ""
os.environ.setdefault("PUBLIC_URL", "https://twin.bmslab.uz")

from fastapi.testclient import TestClient           # noqa: E402

from . import db, monitoring, pg, pul, tolov, web   # noqa: E402

LOGIN = os.environ["PAYLOV_CALLBACK_LOGIN"]
PAROL = os.environ["PAYLOV_CALLBACK_PAROL"]
NARX = 1000                       # sinov planining narxi (so'm)
KUN = 30

KLIENT = TestClient(web.app)
OK, YIQILDI = [], []
TG_XABAR = []                     # _obuna_xabar chaqiruvlari


# ---------------------------------------------------------------- ko'rsatkichlar

def tek(shart, nom: str, izoh: str = ""):
    belgi = "OK  " if shart else "XATO"
    print(f"  [{belgi}] {nom}" + (f" — {izoh}" if izoh else ""))
    (OK if shart else YIQILDI).append(nom)
    return bool(shart)


def bolim(nom: str):
    print(f"\n=== {nom} " + "=" * max(0, 54 - len(nom)))


# ---------------------------------------------------------------- yordamchilar

def _auth(login: str | None = None, parol: str | None = None) -> dict:
    xom = f"{LOGIN if login is None else login}:{PAROL if parol is None else parol}"
    return {"Authorization": "Basic " + base64.b64encode(xom.encode()).decode()}


def _params(t: dict, tr_id: str | None = None, summa=None, tiyin=None,
            valyuta: int = 860, order_id: str | None = None) -> dict:
    som = int(t["summa_som"])
    p = {"account": {"order_id": order_id or str(t["tashqi_id"])},
         "amount": som if summa is None else summa,
         "amount_tiyin": som * 100 if tiyin is None else tiyin,
         "currency": valyuta}
    if tr_id:
        p["transaction_id"] = tr_id
    return p


def _call(metod: str, params: dict, sarlavha: dict | None = None):
    return KLIENT.post("/tolov/paylov", headers=sarlavha or _auth(),
                       json={"jsonrpc": "2.0", "id": 777,
                             "method": metod, "params": params})


def _status(javob) -> str:
    try:
        return javob.json()["result"]["status"]
    except Exception:                                        # noqa: BLE001
        return f"<javob o'qilmadi: {javob.status_code}>"


def _matn(javob) -> str:
    try:
        return javob.json()["result"]["statusText"]
    except Exception:                                        # noqa: BLE001
        return ""


def _holat(tid: int) -> str:
    r = pg.bitta("SELECT holat FROM tolovlar WHERE id=%s", tid)
    return r[0] if r else "<yo'q>"


def _obuna_soni(uid: int) -> int:
    return pg.bitta("SELECT count(*) FROM obunalar WHERE user_id=%s", uid)[0]


def _tolov(uid: int, provayder: str = "paylov") -> dict:
    """Yangi kutilayotgan to'lov (summa PLANDAN olinadi)."""
    t = pul.tolov_yasa(uid, PLAN_ID, provayder)
    return pul.tolov_ol(t["id"])


def _tozala_obuna(uid: int):
    pg.bajar("DELETE FROM obunalar WHERE user_id=%s", uid)


# ---------------------------------------------------------------- 1. statik

def statik():
    bolim("1. Statik: to'lov yo'li LLM'siz zona")
    import ast
    import pathlib
    taqiq = {"llm", "agentlar", "majlis", "yordamchi", "mentor", "maqsad_oqim"}
    for nom in ("tolov.py", "pul.py"):
        yol = pathlib.Path(__file__).parent / nom
        daraxt = ast.parse(yol.read_text(encoding="utf-8"))
        topilgan = set()
        for tugun in ast.walk(daraxt):
            if isinstance(tugun, ast.ImportFrom):
                topilgan |= {a.name for a in tugun.names}
                if tugun.module:
                    topilgan.add(tugun.module.split(".")[-1])
            elif isinstance(tugun, ast.Import):
                topilgan |= {a.name.split(".")[-1] for a in tugun.names}
        yomon = topilgan & taqiq
        tek(not yomon, f"S1 {nom}: taqiqlangan import yo'q",
            ", ".join(sorted(yomon)) if yomon else "")


# ---------------------------------------------------------------- 2. havola

def havola():
    bolim("2. Checkout havolasi")
    t = {"summa_som": NARX, "tashqi_id": uuid.uuid4()}
    qaytish = "https://twin.bmslab.uz/?tolov=" + str(t["tashqi_id"])
    h = tolov._paylov_havola(t, qaytish)

    tek(h.startswith(tolov.PAYLOV_CHECKOUT), "S2a havola checkout manzilidan boshlanadi", h[:48])
    xom = base64.b64decode(h[len(tolov.PAYLOV_CHECKOUT):]).decode()
    q = {k: v[0] for k, v in parse_qs(xom).items()}
    tek(q.get("merchant_id") == os.environ["PAYLOV_MERCHANT_ID"],
        "S2b merchant_id to'g'ri")
    tek(q.get("currency_id") == "860", "S2c currency_id = 860")
    tek(q.get("account.order_id") == str(t["tashqi_id"]),
        "S2d account.order_id = tashqi_id")
    tek(unquote(q.get("return_url", "")) == qaytish, "S2e return_url qaytadi")
    tek("%3A%2F%2F" in xom, "S3 return_url URL-encoded (hujjatdagidek)",
        xom[:60])

    # S4 — tiyin/so'm bayrog'i
    tek(q.get("amount") == str(NARX * 100) and q.get("amount_in_tiyin") == "True",
        "S4a PAYLOV_TIYINDA=1 -> amount tiyinda", q.get("amount", ""))
    os.environ["PAYLOV_TIYINDA"] = "0"
    try:
        xom2 = base64.b64decode(
            tolov._paylov_havola(t, qaytish)[len(tolov.PAYLOV_CHECKOUT):]).decode()
        q2 = {k: v[0] for k, v in parse_qs(xom2).items()}
        tek(q2.get("amount") == str(NARX) and q2.get("amount_in_tiyin") == "False",
            "S4b PAYLOV_TIYINDA=0 -> amount so'mda", q2.get("amount", ""))
    finally:
        os.environ["PAYLOV_TIYINDA"] = "1"

    # S5 — base64 URL yo'li uchun toza bo'lishi kerak
    nopok = 0
    for _ in range(50):
        s = tolov._paylov_havola(
            {"summa_som": NARX, "tashqi_id": uuid.uuid4()}, qaytish)
        quyruq = s[len(tolov.PAYLOV_CHECKOUT):]
        if "/" in quyruq or "+" in quyruq:
            nopok += 1
    tek(nopok == 0, "S5 50 ta havolada base64 toza ('/' va '+' yo'q)",
        f"{nopok} ta nopok")


# ---------------------------------------------------------------- 3. auth

def auth_sinov():
    bolim("3. Callback: sozlanish va auth")
    saqlangan = os.environ["PAYLOV_MERCHANT_ID"]
    os.environ["PAYLOV_MERCHANT_ID"] = ""
    try:
        r = _call("transaction.check", {})
        tek(r.status_code == 404, "S6 sozlanmagan bo'lsa endpoint 404", str(r.status_code))
    finally:
        os.environ["PAYLOV_MERCHANT_ID"] = saqlangan

    t = _tolov(USER_ID)
    r = KLIENT.post("/tolov/paylov", json={"jsonrpc": "2.0", "id": 1,
                                           "method": "transaction.check",
                                           "params": _params(t)})
    tek(r.status_code == 401 and _holat(t["id"]) == "kutilmoqda",
        "S7 auth sarlavhasiz -> 401, holat o'zgarmadi", str(r.status_code))

    r = _call("transaction.check", _params(t), _auth(parol="boshqa-parol"))
    tek(r.status_code == 401, "S8 noto'g'ri parol -> 401", str(r.status_code))

    r = _call("transaction.check", _params(t), _auth(login="boshqa"))
    tek(r.status_code == 401, "S9 noto'g'ri login -> 401", str(r.status_code))

    r = _call("transaction.hech_narsa", _params(t))
    tek(_status(r) == tolov.PL_TEXNIK, "S10 noma'lum metod -> 3", _status(r))

    r = KLIENT.post("/tolov/paylov", headers=_auth(), content=b"{buzuq json")
    tek(_status(r) == tolov.PL_TEXNIK, "S11 buzuq JSON -> 3", _status(r))


# ---------------------------------------------------------------- 4. check

def check_sinov():
    bolim("4. transaction.check")
    t = _tolov(USER_ID)

    r = _call("transaction.check", _params(t, order_id=str(uuid.uuid4())))
    tek(_status(r) == tolov.PL_TOPILMADI, "S12 order topilmadi -> 303", _status(r))

    r = _call("transaction.check", _params(t, order_id="men-uuid-emasman"))
    tek(_status(r) == tolov.PL_TOPILMADI, "S12b order_id UUID emas -> 303", _status(r))

    kt = _tolov(USER_ID, provayder="click")
    r = _call("transaction.check", _params(kt))
    tek(_status(r) == tolov.PL_TOPILMADI,
        "S13 boshqa provayder to'lovi -> 303", _status(r))

    r = _call("transaction.check", _params(t, summa=NARX + 1))
    tek(_status(r) == tolov.PL_SUMMA and _holat(t["id"]) == "kutilmoqda",
        "S14 noto'g'ri summa (so'm) -> 5, holat o'zgarmadi", _status(r))

    r = _call("transaction.check", _params(t, tiyin=NARX * 100 + 1))
    tek(_status(r) == tolov.PL_SUMMA, "S15 noto'g'ri amount_tiyin -> 5", _status(r))

    r = _call("transaction.check", _params(t, valyuta=840))
    tek(_status(r) == tolov.PL_SUMMA, "S16 valyuta 840 -> 5", _status(r))

    p = _params(t)
    del p["amount"], p["amount_tiyin"]
    r = _call("transaction.check", p)
    tek(_status(r) == tolov.PL_SUMMA, "S16b summasiz so'rov -> 5", _status(r))

    # Tiyindagi `amount` ham qabul qilinadi (hujjat noaniqligiga chidamlilik),
    # lekin bu BIR XIL pulning ikkinchi o'lchovi — boshqa summa o'tmaydi.
    r = _call("transaction.check", _params(t, summa=NARX * 100))
    tek(_status(r) == tolov.PL_OK, "S17a amount tiyinda kelsa ham o'tadi", _status(r))

    r = _call("transaction.check", _params(t))
    tek(_status(r) == tolov.PL_OK and _holat(t["id"]) == "tayyorlangan",
        "S17 check OK -> 0, holat 'tayyorlangan'", _holat(t["id"]))

    # S18 — muddati o'tgan
    m = _tolov(USER_ID)
    pg.bajar("UPDATE tolovlar SET muddat = now() - interval '1 hour' WHERE id=%s",
             m["id"])
    r = _call("transaction.check", _params(pul.tolov_ol(m["id"])))
    tek(_status(r) == tolov.PL_OZ and _matn(r) == "order_expired"
        and _holat(m["id"]) == "bekor",
        "S18 muddati o'tgan -> +1 order_expired, holat 'bekor'", _matn(r))


# ---------------------------------------------------------------- 5. perform

def perform_sinov():
    bolim("5. transaction.perform")
    _tozala_obuna(USER_ID)
    TG_XABAR.clear()

    t = _tolov(USER_ID)
    tr = str(uuid.uuid4())
    _call("transaction.check", _params(t))
    r = _call("transaction.perform", _params(t, tr_id=tr))
    o = pul.obuna_ol(USER_ID)
    tek(_status(r) == tolov.PL_OK and _holat(t["id"]) == "tolangan" and o is not None,
        "S19 perform OK -> 0, to'landi, obuna faol", _status(r))
    if o:
        tek(KUN - 1 <= int(o["kun_qoldi"]) <= KUN + 1,
            f"S19b obuna muddati ~{KUN} kun", f"{o['kun_qoldi']} kun")
    tek(len(TG_XABAR) == 1, "S19c foydalanuvchiga bitta xabar ketdi",
        f"{len(TG_XABAR)} ta")

    r = _call("transaction.perform", _params(t, tr_id=tr))
    tek(_status(r) == tolov.PL_OK and _obuna_soni(USER_ID) == 1 and len(TG_XABAR) == 1,
        "S20 takroriy perform (bir xil tr) -> 0, ikkinchi obuna YO'Q",
        f"obuna={_obuna_soni(USER_ID)} xabar={len(TG_XABAR)}")

    r = _call("transaction.perform", _params(t, tr_id=str(uuid.uuid4())))
    tek(_status(r) == tolov.PL_OZ and _matn(r) == "already_paid"
        and _obuna_soni(USER_ID) == 1,
        "S21 to'langan buyurtmaga BOSHQA tranzaksiya -> +1 already_paid", _matn(r))

    r = _call("transaction.check", _params(t))
    tek(_status(r) == tolov.PL_OZ and _matn(r) == "already_paid",
        "S21b to'langan buyurtmaga check -> +1 already_paid", _matn(r))

    # S22 — check'siz to'g'ridan-to'g'ri perform
    _tozala_obuna(USER_ID)
    t2 = _tolov(USER_ID)
    r = _call("transaction.perform", _params(t2, tr_id=str(uuid.uuid4())))
    tek(_status(r) == tolov.PL_OK and _holat(t2["id"]) == "tolangan",
        "S22 check'siz perform ham ishlaydi", _status(r))

    # S23 — noto'g'ri summa holatni o'zgartirmaydi
    t3 = _tolov(USER_ID)
    _call("transaction.check", _params(t3))
    r = _call("transaction.perform", _params(t3, tr_id=str(uuid.uuid4()),
                                             summa=NARX * 7))
    tek(_status(r) == tolov.PL_SUMMA and _holat(t3["id"]) == "tayyorlangan",
        "S23 perform noto'g'ri summa -> 5, holat o'zgarmadi", _holat(t3["id"]))

    # S24 — bekor qilingan to'lovga perform
    pul.bekor(t3["id"], "sinov")
    r = _call("transaction.perform", _params(t3, tr_id=str(uuid.uuid4())))
    tek(_status(r) == tolov.PL_OZ and _matn(r) == "order_cancelled",
        "S24 bekor qilingan to'lovga perform -> +1 order_cancelled", _matn(r))

    # S25 — xom callbacklar audit uchun yozildi
    xom = pg.bitta("SELECT jsonb_array_length(xom) FROM tolovlar WHERE id=%s", t3["id"])
    tek(xom and int(xom[0]) >= 3, "S25 xom callbacklar tolovlar.xom ga yozildi",
        f"{xom[0] if xom else 0} ta")


# ---------------------------------------------------------------- 6. konkurentlik

def konkurent():
    bolim("6. Konkurentlik va obuna uzayishi")
    _tozala_obuna(USER_ID)
    TG_XABAR.clear()

    t = _tolov(USER_ID)
    params = _params(t, tr_id=str(uuid.uuid4()))
    natijalar = []

    def bir():
        # Handler'ni to'g'ridan-to'g'ri chaqiramiz: bu yerda tekshirilayotgan
        # narsa HTTP emas, bazadagi qulf (pul.tolandi -> FOR UPDATE).
        try:
            natijalar.append(tolov._pl_perform(dict(params), 1))
        except Exception as e:                               # noqa: BLE001
            natijalar.append({"xato": str(e)})

    oqimlar = [threading.Thread(target=bir) for _ in range(2)]
    for o in oqimlar:
        o.start()
    for o in oqimlar:
        o.join()

    statuslar = [(n.get("result") or {}).get("status") for n in natijalar
                 if isinstance(n, dict)]
    tek(_obuna_soni(USER_ID) == 1 and len(TG_XABAR) == 1
        and statuslar.count(tolov.PL_OK) == 2,
        "S26 ikkita parallel perform -> bitta obuna, bitta xabar",
        f"obuna={_obuna_soni(USER_ID)} xabar={len(TG_XABAR)} status={statuslar}")

    # S27 — faol obunasi bor userga ikkinchi to'lov obunani UZAYTIRADI
    oldin = pul.obuna_ol(USER_ID)
    t2 = _tolov(USER_ID)
    _call("transaction.perform", _params(t2, tr_id=str(uuid.uuid4())))
    keyin = pul.obuna_ol(USER_ID)
    tek(_obuna_soni(USER_ID) == 1 and oldin and keyin
        and keyin["id"] == oldin["id"] and keyin["tugash"] > oldin["tugash"],
        "S27 ikkinchi to'lov obunani uzaytiradi (yangi qator yo'q)",
        f"obuna_soni={_obuna_soni(USER_ID)}")


# ---------------------------------------------------------------- 7. mijoz API

def mijoz_api():
    bolim("7. Mijoz API va kvota darvozasi")
    KLIENT.cookies.clear()
    r = KLIENT.post("/api/tolov/boshla", json={"plan_id": PLAN_ID})
    tek(r.status_code == 401, "S29 kirmagan user -> 401", str(r.status_code))

    KLIENT.cookies.set("twin_sessiya", TOKEN)
    r = KLIENT.post("/api/tolov/boshla", json={"plan_id": PLAN_ID})
    d = r.json() if r.status_code == 200 else {}
    tek(r.status_code == 200 and d.get("usul") == "paylov"
        and str(d.get("havola", "")).startswith(tolov.PAYLOV_CHECKOUT),
        "S28 usulsiz so'rov -> yagona usul (paylov) tanlandi",
        d.get("usul") or str(r.status_code))

    tashqi = d.get("tashqi_id") or ""
    r = KLIENT.get("/api/tolov/" + tashqi)
    tek(r.status_code == 200 and r.json().get("holat") == "kutilmoqda",
        "S30a o'z to'lovining holati ko'rinadi", str(r.status_code))

    KLIENT.cookies.set("twin_sessiya", TOKEN2)
    r = KLIENT.get("/api/tolov/" + tashqi)
    tek(r.status_code == 404, "S30 boshqa userning to'lovi -> 404", str(r.status_code))
    KLIENT.cookies.set("twin_sessiya", TOKEN)

    # S31 — kvota darvozasi. `sozlamalar` jadvaliga TEGMAYMIZ: umumiy kalitni
    # o'zgartirish prodda barcha foydalanuvchilarni bloklab qo'yishi mumkin.
    asl = pul.kvota_faolmi
    pul.kvota_faolmi = lambda: True
    try:
        _tozala_obuna(USER_ID)
        pg.bajar("UPDATE userlar SET bepul_qolgan=0 WHERE id=%s", USER_ID)
        ok1, kod1, _ = pul.tekshir(USER_ID)
        t = _tolov(USER_ID)
        _call("transaction.perform", _params(t, tr_id=str(uuid.uuid4())))
        ok2, kod2, _ = pul.tekshir(USER_ID)
        tek(not ok1 and kod1 == "obuna_yoq" and ok2 and kod2 == "obuna",
            "S31 kvota yoqilganda: to'lovdan oldin rad, keyin ruxsat",
            f"{kod1} -> {kod2}")
    finally:
        pul.kvota_faolmi = asl
        pg.bajar("UPDATE userlar SET bepul_qolgan=3 WHERE id=%s", USER_ID)


# ---------------------------------------------------------------- 8. tozalash jobi

def tozalash_jobi():
    bolim("8. tolov_tozala jobi")
    eski = _tolov(USER_ID)
    yangi = _tolov(USER_ID)
    pg.bajar("UPDATE tolovlar SET muddat = now() - interval '1 hour' WHERE id=%s",
             eski["id"])
    pul.tolov_tozala(yoz=lambda s: None)
    tek(_holat(eski["id"]) == "bekor" and _holat(yangi["id"]) == "kutilmoqda",
        "S32 muddati o'tgan bekor, yangisi tegilmagan",
        f"eski={_holat(eski['id'])} yangi={_holat(yangi['id'])}")


# ---------------------------------------------------------------- tayyorgarlik

USER_ID = USER2_ID = PLAN_ID = 0
TOKEN = TOKEN2 = ""


def tayyorla():
    global USER_ID, USER2_ID, PLAN_ID, TOKEN, TOKEN2

    # 010 migratsiyasisiz sinovning ma'nosi yo'q — aniq xabar bilan to'xtaymiz.
    if not pg.bitta("""SELECT 1 FROM information_schema.columns
                       WHERE table_name='tolovlar' AND column_name='tashqi_id'"""):
        raise SystemExit("010_paylov.sql qo'llanmagan — avval: python -m platforma.pg")

    # Sinov "yagona usul" xulqini tekshiradi: mahalliy .env da Click/Payme
    # sozlangan bo'lsa ham shu jarayonda faqat Paylov ko'rinsin.
    for nom in ("CLICK_SERVICE_ID", "CLICK_MERCHANT_ID", "CLICK_SECRET",
                "PAYME_MERCHANT_ID", "PAYME_KEY"):
        os.environ[nom] = ""

    tozala()                       # oldingi yiqilgan yugurishdan qolgani bo'lsa

    u1 = db.user_tg({"id": -999001, "first_name": "Sinov Paylov"})
    u2 = db.user_tg({"id": -999002, "first_name": "Sinov Paylov 2"})
    USER_ID, USER2_ID = u1["id"], u2["id"]
    TOKEN, TOKEN2 = db.sessiya_yasa(USER_ID), db.sessiya_yasa(USER2_ID)
    PLAN_ID = pg.bitta(
        """INSERT INTO planlar(kod, nom, tavsif, oylik_narx_som, kvota_usd,
                               kun_soni, tartib, faol)
           VALUES('sinov_paylov','Sinov (Paylov)','avtomatik sinov uchun',
                  %s, 100.0, %s, 999, true)
           ON CONFLICT (kod) DO UPDATE SET faol=true, oylik_narx_som=EXCLUDED.oylik_narx_som
           RETURNING id""", NARX, KUN)[0]

    # Telegram'ga hech narsa ketmasin.
    tolov._obuna_xabar = lambda t, oid: TG_XABAR.append((t or {}).get("id"))
    monitoring.xato = lambda *a, **k: None


def tozala():
    """Sinov qoldiqlarini o'chiradi (FK tartibida)."""
    pg.bajar("""DELETE FROM obunalar WHERE user_id IN
                (SELECT id FROM userlar WHERE tg_id IN (-999001,-999002))""")
    pg.bajar("""DELETE FROM obunalar WHERE plan_id IN
                (SELECT id FROM planlar WHERE kod='sinov_paylov')""")
    pg.bajar("""DELETE FROM tolovlar WHERE user_id IN
                (SELECT id FROM userlar WHERE tg_id IN (-999001,-999002))""")
    pg.bajar("""DELETE FROM tolovlar WHERE plan_id IN
                (SELECT id FROM planlar WHERE kod='sinov_paylov')""")
    pg.bajar("DELETE FROM userlar WHERE tg_id IN (-999001,-999002)")
    pg.bajar("DELETE FROM planlar WHERE kod='sinov_paylov'")


# ---------------------------------------------------------------- main

def main() -> int:
    print("Paylov sinovlari — PAYLOV_REJA.md 10-bo'lim")
    print("DIQQAT: sinov ulangan bazaga o'z yozuvlarini yaratadi va oxirida "
          "o'chiradi.")
    print("DIQQAT: sinov davomida (~10 soniya) «Sinov (Paylov) — 1 000 so'm» "
          "plani\n         «Rejalar» ro'yxatida KO'RINADI. Jonli bazada "
          "kam bandlik paytida yugurting.")
    try:
        tayyorla()
        statik()
        havola()
        auth_sinov()
        check_sinov()
        perform_sinov()
        konkurent()
        mijoz_api()
        tozalash_jobi()
    finally:
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
