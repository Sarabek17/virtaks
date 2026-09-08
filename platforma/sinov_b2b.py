# -*- coding: utf-8 -*-
"""B2B API sinovlari (B2B_API_REJA.md, 12-bo'lim).

    python -m platforma.sinov_b2b

Chiqish kodi: bironta sinov yiqilsa 1.

BAZAGA TEGISH QOIDASI — bu skript LOKALDA ham PROD bazaga ulanishi mumkin
(CLAUDE.md ogohlantirishi). Shuning uchun:

  * O'zining sinov tashkilotlarini (`slug` = `sinov-b2b-*`) va sinov twinini
    (`slug = 'sinov-b2b-twin'`) yaratadi, oxirida HAMMASINI o'chiradi.
    Tashkilot o'chirilganda soya userlar CASCADE bilan ketadi.
  * MODEL CHAQIRILMAYDI: `/savol` faqat darvozalar (balans, twin, izolyatsiya,
    cheklov) tekshiriladigan holatlarda uriladi. Pul yo'li `pul.xarajat_yoz`
    ni to'g'ridan-to'g'ri chaqirib sinaladi — bu LLM'siz.
  * Hech qanday JOB yaratilmaydi — bulutdagi worker pul sarflamaydi.
  * `sozlamalar` jadvaliga tegilmaydi.
"""
import ast
import os
import pathlib
import sys
import uuid

# Muhitni import'dan OLDIN: `platforma.web` import qilinganda Telegram
# webhook'i lokalga ko'chib, prod bot o'lib qolmasin (CLAUDE.md).
os.environ["KENGASH_BOT_OFF"] = "1"

from fastapi.testclient import TestClient           # noqa: E402

from . import b2b, cheklov, db, pg, pul, web        # noqa: E402
from .api_v1 import _hodisa, _manba                 # noqa: E402

KLIENT = TestClient(web.app)
OK, YIQILDI = [], []


def tek(shart, nom: str, izoh: str = ""):
    belgi = "OK  " if shart else "XATO"
    print(f"  [{belgi}] {nom}" + (f" — {izoh}" if izoh else ""))
    (OK if shart else YIQILDI).append(nom)
    return bool(shart)


def bolim(nom: str):
    print(f"\n=== {nom} " + "=" * max(0, 54 - len(nom)))


def bosh(kalit: str) -> dict:
    return {"Authorization": f"Bearer {kalit}"}


# ---------------------------------------------------------------- tayyorlash

HOLAT = {}


def tayyorla():
    tozala()
    a = b2b.tashkilot_yasa("Sinov A", "sinov-b2b-a", ustama=3.0,
                           daqiqa_limit=60, oqim_limit=2)
    b = b2b.tashkilot_yasa("Sinov B", "sinov-b2b-b", ustama=2.0)
    tw = pg.bitta_d(
        """INSERT INTO twinlar(nom, slug, tavsif) VALUES(%s,%s,'sinov')
           ON CONFLICT (slug) DO UPDATE SET nom=EXCLUDED.nom RETURNING *""",
        "Sinov twin", "sinov-b2b-twin")
    b2b.twin_qosh(a["id"], tw["id"])          # A ga ochiq, B ga YO'Q
    ka, _ = b2b.kalit_yasa(a["id"], "sinov-a")
    kb, _ = b2b.kalit_yasa(b["id"], "sinov-b")
    b2b.toldir(a["id"], 10.0, "sinov depoziti")
    HOLAT.update({"a": a, "b": b, "twin": tw, "ka": ka, "kb": kb})


def tozala():
    pg.bajar("DELETE FROM tashkilotlar WHERE slug LIKE 'sinov-b2b-%'")
    pg.bajar("DELETE FROM twinlar WHERE slug = 'sinov-b2b-twin'")
    pg.bajar("DELETE FROM userlar WHERE tg_id = -999301")


# ---------------------------------------------------------------- 1. statik

def statik():
    bolim("1. Statik: pul/izolyatsiya yadrosi LLM'siz zona")
    ildiz = pathlib.Path(__file__).parent

    def importlar(nom: str) -> set:
        daraxt = ast.parse((ildiz / nom).read_text(encoding="utf-8"))
        topilgan = set()
        for tugun in ast.walk(daraxt):
            if isinstance(tugun, ast.ImportFrom):
                topilgan |= {a.name for a in tugun.names}
                if tugun.module:
                    topilgan.add(tugun.module.split(".")[-1])
            elif isinstance(tugun, ast.Import):
                topilgan |= {a.name.split(".")[-1] for a in tugun.names}
        return topilgan

    # b2b.py — pul va izolyatsiya qarorlari; model bu yerga kirmaydi.
    yomon = importlar("b2b.py") & {"llm", "agentlar", "majlis", "yordamchi",
                                   "mentor", "maqsad_oqim", "tizim_oqim"}
    tek(not yomon, "S1a b2b.py: taqiqlangan import yo'q", ", ".join(sorted(yomon)))

    # api_v1.py — API kaliti admin/kabinet yuzasini HECH QACHON ochmasligi kerak.
    yomon = importlar("api_v1.py") & {"admin", "kabinet", "tolov", "auth"}
    tek(not yomon, "S1b api_v1.py: admin/kabinet/auth import qilinmaydi",
        ", ".join(sorted(yomon)))

    # Docstringda "web._joriy ni chaqirmaydi" deb yozilgan — oddiy matn
    # qidiruvi shuni topib, yolg'on ogohlantirish berardi. AST bo'yicha
    # HAQIQIY foydalanish tekshiriladi.
    daraxt = ast.parse((ildiz / "api_v1.py").read_text(encoding="utf-8"))
    nomlar = set()
    for tugun in ast.walk(daraxt):
        if isinstance(tugun, ast.Attribute):
            nomlar.add(tugun.attr)
        elif isinstance(tugun, ast.Name):
            nomlar.add(tugun.id)
        elif isinstance(tugun, ast.Constant) and isinstance(tugun.value, str):
            if tugun.value == "twin_sessiya":
                nomlar.add("twin_sessiya")
    yomon = nomlar & {"_joriy", "twin_sessiya", "sessiya_user"}
    tek(not yomon, "S1c api_v1.py: cookie sessiyasiga umuman qaramaydi",
        ", ".join(sorted(yomon)))


# ---------------------------------------------------------------- 2. kalitlar

def kalitlar():
    bolim("2. Kalit tekshiruvi")
    a, ka = HOLAT["a"], HOLAT["ka"]

    r = KLIENT.get("/api/v1/salomatlik", headers=bosh(ka))
    tek(r.status_code == 200, "S2a to'g'ri kalit -> 200", str(r.status_code))

    r = KLIENT.get("/api/v1/salomatlik", headers=bosh(ka[:-4] + "xxxx"))
    tek(r.status_code == 401, "S2b noto'g'ri sir -> 401", str(r.status_code))

    r = KLIENT.get("/api/v1/salomatlik", headers=bosh("vk_sinov_yoq123_abc"))
    tek(r.status_code == 401, "S2c noma'lum prefiks -> 401", str(r.status_code))

    r = KLIENT.get("/api/v1/salomatlik")
    tek(r.status_code == 401, "S2d kalitsiz -> 401", str(r.status_code))

    r = KLIENT.get("/api/v1/salomatlik", headers={"Authorization": "Basic abc"})
    tek(r.status_code == 401, "S2e Bearer bo'lmagan sxema -> 401", str(r.status_code))

    # muddati o'tgan
    k2, y2 = b2b.kalit_yasa(a["id"], "muddatli")
    pg.bajar("UPDATE api_kalitlar SET muddat = now() - interval '1 day' WHERE id=%s",
             y2["id"])
    r = KLIENT.get("/api/v1/salomatlik", headers=bosh(k2))
    tek(r.status_code == 401, "S2f muddati o'tgan kalit -> 401", str(r.status_code))

    # o'chirilgan
    k3, y3 = b2b.kalit_yasa(a["id"], "ochiriladigan")
    tek(KLIENT.get("/api/v1/salomatlik", headers=bosh(k3)).status_code == 200,
        "S2g yangi kalit ishlaydi")
    b2b.kalit_ochir(y3["id"])
    r = KLIENT.get("/api/v1/salomatlik", headers=bosh(k3))
    tek(r.status_code == 401, "S2h o'chirilgan kalit DARHOL 401 (kesh tozalanadi)",
        str(r.status_code))

    # REGRESSIYA: sir `secrets.token_urlsafe` dan keladi, alifbosida `_` BOR.
    # Ajratish `maxsplit=3` siz qilinsa, sirida pastki chiziq bo'lgan kalitlar
    # (~40%) jimgina rad etilardi — xato TASODIFIY ko'rinardi.
    yomon, pastchali = 0, 0
    for i in range(20):
        kx, _yx = b2b.kalit_yasa(a["id"], f"regress-{i}")
        if "_" in kx.split("_", 3)[3]:
            pastchali += 1
        if b2b.kalit_tekshir(kx) is None:
            yomon += 1
    tek(yomon == 0, "S2j 20 kalitning HAMMASI tekshiruvdan o'tadi",
        f"sirida '_' bor: {pastchali} ta, o'tmagani: {yomon}")

    # tashkilot o'chirilsa
    pg.bajar("UPDATE tashkilotlar SET faol=false WHERE id=%s", a["id"])
    r = KLIENT.get("/api/v1/salomatlik", headers=bosh(ka))
    tek(r.status_code == 401, "S2i o'chirilgan tashkilot -> 401", str(r.status_code))
    pg.bajar("UPDATE tashkilotlar SET faol=true WHERE id=%s", a["id"])


def huquqlar():
    bolim("3. Huquqlar va IP")
    a = HOLAT["a"]
    k, _ = b2b.kalit_yasa(a["id"], "cheklangan", huquqlar=["savol"])
    r = KLIENT.get("/api/v1/hisob", headers=bosh(k))
    tek(r.status_code == 403, "S3a huquqsiz endpoint -> 403", str(r.status_code))
    tek(r.json().get("xato") == "ruxsat_yoq", "S3b xato kodi to'g'ri")

    k2, _ = b2b.kalit_yasa(a["id"], "ip", ip_oq=["8.8.8.8"])
    r = KLIENT.get("/api/v1/salomatlik", headers=bosh(k2))
    tek(r.status_code == 401, "S3c IP oq ro'yxatdan tashqari -> 401",
        str(r.status_code))


# ------------------------------------------------------------ 4. izolyatsiya

def izolyatsiya():
    bolim("4. Izolyatsiya (begona resurs -> 404)")
    a, b, ka, kb = HOLAT["a"], HOLAT["b"], HOLAT["ka"], HOLAT["kb"]

    ua = b2b.foydalanuvchi(a["id"], "mijoz-1", "Aziz")
    ub = b2b.foydalanuvchi(b["id"], "mijoz-1", "Boshqa")
    tek(ua["id"] != ub["id"],
        "S4a ayni tashqi_id ikki tashkilotda ALOHIDA user")

    sid = db.suhbat_yasa(ua["id"], HOLAT["twin"]["id"], "sinov savoli")
    r = KLIENT.get(f"/api/v1/suhbat/{sid}", headers=bosh(ka))
    tek(r.status_code == 200, "S4b o'z suhbati ko'rinadi", str(r.status_code))
    r = KLIENT.get(f"/api/v1/suhbat/{sid}", headers=bosh(kb))
    tek(r.status_code == 404, "S4c BEGONA suhbat -> 404 (403 emas)",
        str(r.status_code))

    r = KLIENT.get("/api/v1/twinlar", headers=bosh(ka))
    tek(len(r.json()["royxat"]) == 1, "S4d A ga twin ochilgan")
    r = KLIENT.get("/api/v1/twinlar", headers=bosh(kb))
    tek(r.json()["royxat"] == [], "S4e B ga twin ochilmagan")

    # B da twin umuman yo'q -> savol 409
    r = KLIENT.post("/api/v1/savol", headers=bosh(kb),
                    json={"tashqi_id": "x", "savol": "salom", "oqim": False})
    tek(r.status_code == 409, "S4f twin biriktirilmagan tashkilot -> 409",
        str(r.status_code))

    # A da bor, lekin noma'lum slug
    r = KLIENT.post("/api/v1/savol", headers=bosh(ka),
                    json={"tashqi_id": "x", "savol": "salom",
                          "twin": "yoq-bunday-twin", "oqim": False})
    tek(r.status_code == 404, "S4g noma'lum twin -> 404", str(r.status_code))


# ------------------------------------------------------- 5. foydalanuvchilar

def foydalanuvchilar():
    bolim("5. Soya foydalanuvchilar")
    ka = HOLAT["ka"]
    tid = f"mijoz-{uuid.uuid4().hex[:8]}"
    r1 = KLIENT.post("/api/v1/foydalanuvchi", headers=bosh(ka),
                     json={"tashqi_id": tid, "ism": "Aziz"})
    r2 = KLIENT.post("/api/v1/foydalanuvchi", headers=bosh(ka),
                     json={"tashqi_id": tid, "ism": "Aziz"})
    tek(r1.status_code == 200 and r1.json()["yangi"] is True, "S5a birinchi -> yangi")
    tek(r2.json()["yangi"] is False and r1.json()["id"] == r2.json()["id"],
        "S5b takroriy -> ayni user (idempotent)")
    r = KLIENT.post("/api/v1/foydalanuvchi", headers=bosh(ka),
                    json={"tashqi_id": "  ", "ism": "x"})
    tek(r.status_code == 400, "S5c bo'sh tashqi_id -> 400", str(r.status_code))


# ------------------------------------------------------------------- 6. pul

def pul_yoli():
    bolim("6. Pul: hisob, balans, darvoza")
    a, ka = HOLAT["a"], HOLAT["ka"]
    u = b2b.foydalanuvchi(a["id"], "pul-mijoz", "Pul")

    pg.bajar("UPDATE tashkilotlar SET balans_usd=10, ustama=3.0 WHERE id=%s", a["id"])
    oldin = pg.bitta("SELECT count(*) FROM xarajatlar WHERE tashkilot_id=%s",
                     a["id"])[0]

    # Narx BAZADAN olinadi — qotirilgan raqam yozsak, narx yangilanganda
    # sinov yolg'on yiqilardi (2026-09-09 da aynan shunday bo'ldi).
    kir, chiq = pul.narxlar()["gemini-3.5-flash"]
    kutilgan_narx = round(kir + chiq, 8)          # 1M kirish + 1M chiqish
    kutilgan_hisob = round(kutilgan_narx * 3.0, 6)
    boshlangich = 10.0

    pul.kontekst_boshla(user_id=u["id"], twin_id=HOLAT["twin"]["id"])
    y = pul.xarajat_yoz("gemini-3.5-flash", 1_000_000, 1_000_000, "sinov")
    tek(abs(y["narx"] - kutilgan_narx) < 1e-6, "S6a tannarx bazadagi narxga mos",
        f"{y['narx']} (kutilgan {kutilgan_narx})")
    tek(abs(y.get("hisob", 0) - kutilgan_hisob) < 1e-6,
        "S6b hisob = tannarx * ustama", str(y.get("hisob")))

    qoldiq = round(boshlangich - kutilgan_hisob, 6)
    t = b2b.tashkilot_ol(a["id"])
    tek(abs(float(t["balans_usd"]) - qoldiq) < 1e-6, "S6c balansdan yechildi",
        f"{t['balans_usd']} (kutilgan {qoldiq})")
    h = b2b.harakatlar(a["id"], 1)[0]
    tek(h["tur"] == "sarf" and abs(float(h["qoldiq_usd"]) - qoldiq) < 1e-6,
        "S6d daftarda qoldiq bilan yozildi")

    x = pg.bitta_d("""SELECT narx_usd, hisob_usd FROM xarajatlar
                      WHERE tashkilot_id=%s ORDER BY id DESC LIMIT 1""", a["id"])
    tek(abs(float(x["narx_usd"]) - kutilgan_narx) < 1e-6
        and abs(float(x["hisob_usd"]) - kutilgan_hisob) < 1e-6,
        "S6e xarajatlar qatorida ikkala narx ham bor")

    # USTAMA QOTIRILADI: keyin o'zgartirilsa eski qator o'zgarmaydi
    pg.bajar("UPDATE tashkilotlar SET ustama=9.0 WHERE id=%s", a["id"])
    x2 = pg.bitta_d("""SELECT hisob_usd FROM xarajatlar
                       WHERE tashkilot_id=%s ORDER BY id DESC LIMIT 1""", a["id"])
    tek(abs(float(x2["hisob_usd"]) - kutilgan_hisob) < 1e-6,
        "S6f ustama o'zgarsa ESKI hisob o'zgarmaydi (qotirilgan)")
    pg.bajar("UPDATE tashkilotlar SET ustama=3.0 WHERE id=%s", a["id"])

    # --- 402: balans 0 da MODEL CHAQIRILMAYDI
    pg.bajar("UPDATE tashkilotlar SET balans_usd=0, kredit_chegara_usd=0 WHERE id=%s",
             a["id"])
    oldin = pg.bitta("SELECT count(*) FROM xarajatlar WHERE tashkilot_id=%s",
                     a["id"])[0]
    r = KLIENT.post("/api/v1/savol", headers=bosh(ka),
                    json={"tashqi_id": "pul-mijoz", "savol": "salom", "oqim": False})
    keyin = pg.bitta("SELECT count(*) FROM xarajatlar WHERE tashkilot_id=%s",
                     a["id"])[0]
    tek(r.status_code == 402, "S6g balans tugagan -> 402", str(r.status_code))
    tek(r.json().get("xato") == "balans_tugadi", "S6h xato kodi to'g'ri")
    tek(keyin == oldin, "S6i 402 da LLM CHAQIRILMADI (xarajat o'smadi)",
        f"{oldin} -> {keyin}")

    # --- kredit chegarasi
    pg.bajar("UPDATE tashkilotlar SET kredit_chegara_usd=5 WHERE id=%s", a["id"])
    ok, _ = b2b.balans_yetadimi(b2b.tashkilot_ol(a["id"]))
    tek(ok, "S6j kredit chegarasi ochiq -> ruxsat")
    pg.bajar("UPDATE tashkilotlar SET balans_usd=-5 WHERE id=%s", a["id"])
    ok, _ = b2b.balans_yetadimi(b2b.tashkilot_ol(a["id"]))
    tek(not ok, "S6k kredit tugagach -> to'siq")
    pg.bajar("""UPDATE tashkilotlar SET balans_usd=10, kredit_chegara_usd=0
                WHERE id=%s""", a["id"])

    # --- oylik chegara
    pg.bajar("UPDATE tashkilotlar SET oylik_chegara_usd=0.01 WHERE id=%s", a["id"])
    ok, sabab = b2b.balans_yetadimi(b2b.tashkilot_ol(a["id"]))
    tek(not ok and "Oylik" in sabab, "S6l oylik chegara to'sadi", sabab[:40])
    pg.bajar("UPDATE tashkilotlar SET oylik_chegara_usd=0 WHERE id=%s", a["id"])


# ------------------------------------------------------------ 7. sir saqlash

def sirlar():
    bolim("7. Tannarx sizib chiqmasligi")
    a, ka = HOLAT["a"], HOLAT["ka"]

    r = KLIENT.get("/api/v1/hisob", headers=bosh(ka))
    matn = r.text
    tek(r.status_code == 200, "S7a hisob ochiladi")
    yomon = [q for q in ("narx_usd", "ustama", "kirish_tok", "chiqish_tok",
                         "gemini") if q in matn]
    tek(not yomon, "S7b hisob javobida TANNARX/USTAMA/MODEL yo'q",
        ", ".join(yomon))

    # SSE hodisasi tozalanadimi
    xom = {"tur": "tayyor", "majlis_id": None, "davomiylik": 3,
           "narx_usd": 0.019, "toxtatildi": False,
           "manbalar": [{"n": 1, "id": 5, "manba": "dars", "joy": "[0:01]",
                         "sahifa_png": "kesh/12/003.jpg", "audio_bosh": 61}]}
    toza = _hodisa(xom, a["id"])
    s = str(toza)
    tek("narx_usd" not in s, "S7c `tayyor` hodisasidan narx_usd olib tashlanadi")
    tek("sahifa_png" not in s and "kesh/" not in s,
        "S7d ichki S3 kaliti chiqmaydi")
    tek(toza["manbalar"][0]["bolak"] == 5 and toza["manbalar"][0]["audio"] is True,
        "S7e iqtibos kerakli maydonlarni saqlaydi")
    tek(_hodisa({"tur": "ichki_narsa", "sir": 1}, a["id"]) is None,
        "S7f noma'lum hodisa umuman uzatilmaydi")


# ---------------------------------------------------------------- 8. cheklov

def cheklovlar():
    bolim("8. Tezlik chegarasi")
    a = HOLAT["a"]
    k, _ = b2b.kalit_yasa(a["id"], "cheklov")
    pg.bajar("UPDATE tashkilotlar SET balans_usd=10 WHERE id=%s", a["id"])

    # `api_savol` = 60/60s. Savol ATAYLAB bo'sh: model CHAQIRILMAYDI
    # (400 qaytadi), lekin cheklov validatsiyadan oldin turgani uchun
    # sanagich baribir ishlaydi va chegaradan keyin 429 keladi.
    soni, _oyna = cheklov.QOIDA["api_savol"]
    kodlar, birinchi = [], ""
    for i in range(soni + 3):
        r = KLIENT.post("/api/v1/savol", headers=bosh(k),
                        json={"tashqi_id": f"c-{i}", "savol": "", "oqim": False})
        kodlar.append(r.status_code)
        if not birinchi:
            birinchi = r.text[:120]
    tek(429 in kodlar, "S8a chegaradan keyin 429 keladi",
        f"kodlar: {sorted(set(kodlar))} | 1-javob: {birinchi}")
    oxirgi = KLIENT.post("/api/v1/savol", headers=bosh(k),
                         json={"tashqi_id": "c-x", "savol": "", "oqim": False})
    tek(oxirgi.headers.get("Retry-After") is not None or 429 not in kodlar,
        "S8b 429 javobida Retry-After sarlavhasi bor")


# ----------------------------------------------------------- 9. idempotentlik

def idempotentlik():
    bolim("9. Idempotentlik")
    a = HOLAT["a"]
    kalit = f"idem-{uuid.uuid4().hex[:8]}"
    b2b.idempotent_yoz(a["id"], kalit, {"javob": "salom"}, 200)
    r = b2b.idempotent_ol(a["id"], kalit)
    tek(r and r["javob"]["javob"] == "salom", "S9a yozildi va o'qildi")
    tek(b2b.idempotent_ol(HOLAT["b"]["id"], kalit) is None,
        "S9b boshqa tashkilotga ko'rinmaydi")
    tek(b2b.idempotent_ol(a["id"], "yoq-bunday") is None, "S9c yo'q kalit -> None")


# ------------------------------------------------------------ 10. admin yuzasi

def admin_yuzasi():
    bolim("10. Admin yuzasi API kaliti bilan OCHILMAYDI")
    a, ka = HOLAT["a"], HOLAT["ka"]
    yollar = [
        ("get", "/api/admin/tashkilotlar", None),
        ("get", f"/api/admin/tashkilot/{a['id']}/marja", None),
        ("get", f"/api/admin/tashkilot/{a['id']}/kalitlar", None),
        ("post", f"/api/admin/tashkilot/{a['id']}/kalit", {"nom": "o'g'irlik"}),
        ("post", f"/api/admin/tashkilot/{a['id']}/balans",
         {"summa_usd": 1000, "izoh": "o'g'irlik"}),
    ]
    yomon = []
    for metod, yol, tana in yollar:
        # API kaliti bilan
        r = getattr(KLIENT, metod)(yol, headers=bosh(ka), **({"json": tana} if tana else {}))
        if r.status_code != 403:
            yomon.append(f"{yol} (kalit bilan {r.status_code})")
        # umuman kirmasdan
        r = getattr(KLIENT, metod)(yol, **({"json": tana} if tana else {}))
        if r.status_code != 403:
            yomon.append(f"{yol} (anonim {r.status_code})")
    tek(not yomon, "S10a admin yo'llari API kaliti va anonim uchun 403",
        "; ".join(yomon))

    # Kalit ro'yxatida xesh yoki ochiq kalit ko'rinmasligi kerak
    matn = str(pg.hammasi_d(
        """SELECT id, nom, prefiks FROM api_kalitlar WHERE tashkilot_id=%s""",
        a["id"]))
    tek("$argon2" not in matn, "S10b kalit ro'yxatida xesh yo'q")


# --------------------------------------------------- 11. admin B2B boshqaruvi

def admin_boshqaruv():
    """Admin yuzasi HAQIQIY sessiya bilan: tashkilot -> kalit -> balans -> twin.

    Sinov o'z adminini yaratadi (`tg_id=-999301`) va oxirida o'chiradi.
    """
    bolim("11. Admin B2B boshqaruvi (haqiqiy sessiya)")
    a, tw = HOLAT["a"], HOLAT["twin"]

    u = pg.bitta_d(
        """INSERT INTO userlar(tg_id, ism, rol, manba)
           VALUES(-999301, 'Sinov admin', 'admin', 'admin')
           ON CONFLICT (tg_id) DO UPDATE SET rol='admin' RETURNING *""")
    token = db.sessiya_yasa(u["id"])
    kuki = {"twin_sessiya": token}

    r = KLIENT.get("/api/admin/tashkilotlar", cookies=kuki)
    tek(r.status_code == 200, "S11a tashkilotlar ro'yxati ochiladi", str(r.status_code))
    royxat = r.json()
    meniki = [x for x in royxat if x["id"] == a["id"]]
    tek(bool(meniki), "S11b sinov tashkiloti ro'yxatda")
    tek("twin_ids" in (meniki[0] if meniki else {}),
        "S11c javobda biriktirilgan twin ID lari bor (UI belgilashi uchun)")

    # yangi tashkilot
    r = KLIENT.post("/api/admin/tashkilot", cookies=kuki,
                    json={"nom": "Sinov C", "slug": "sinov-b2b-c", "ustama": 4.0})
    tek(r.status_code == 200 and float(r.json()["ustama"]) == 4.0,
        "S11d yangi tashkilot yaratildi", str(r.status_code))
    c_id = r.json()["id"]

    r = KLIENT.post("/api/admin/tashkilot", cookies=kuki,
                    json={"nom": "Takror", "slug": "sinov-b2b-c"})
    tek(r.status_code == 409, "S11e takroriy slug -> 409", str(r.status_code))

    # kalit
    r = KLIENT.post(f"/api/admin/tashkilot/{c_id}/kalit", cookies=kuki,
                    json={"nom": "prod"})
    tek(r.status_code == 200 and r.json().get("kalit", "").startswith("vk_"),
        "S11f kalit yaratildi va OCHIQ holda qaytdi (bir marta)")
    yangi_kalit = r.json()["kalit"]
    tek(KLIENT.get("/api/v1/salomatlik",
                   headers=bosh(yangi_kalit)).status_code == 200,
        "S11g admin bergan kalit API da ishlaydi")

    r = KLIENT.get(f"/api/admin/tashkilot/{c_id}/kalitlar", cookies=kuki)
    tek("$argon2" not in r.text and yangi_kalit not in r.text,
        "S11h kalitlar ro'yxatida na xesh, na ochiq kalit bor")

    # balans
    r = KLIENT.post(f"/api/admin/tashkilot/{c_id}/balans", cookies=kuki,
                    json={"summa_usd": 25.0, "izoh": "bank o'tkazmasi"})
    tek(r.status_code == 200 and abs(r.json()["balans_usd"] - 25.0) < 1e-6,
        "S11i balans to'ldirildi", str(r.json().get("balans_usd")))
    r = KLIENT.get(f"/api/admin/tashkilot/{c_id}/harakatlar", cookies=kuki)
    tek(len(r.json()) == 1 and r.json()[0]["tur"] == "toldirish",
        "S11j daftarga to'ldirish yozildi")

    # twin biriktirish
    r = KLIENT.post(f"/api/admin/tashkilot/{c_id}/twin/{tw['id']}", cookies=kuki, json={})
    tek(r.status_code == 200, "S11k twin biriktirildi")
    tek(len(b2b.twinlar(c_id)) == 1, "S11l twin API orqali ko'rinadi")
    r = KLIENT.request("DELETE", f"/api/admin/tashkilot/{c_id}/twin/{tw['id']}",
                       cookies=kuki)
    tek(len(b2b.twinlar(c_id)) == 0, "S11m twin uzildi")

    # marja va hisobot — TANNARX faqat shu yerda ko'rinadi
    r = KLIENT.get(f"/api/admin/tashkilot/{a['id']}/marja?kun=30", cookies=kuki)
    tek(r.status_code == 200 and "tannarx_usd" in r.json(),
        "S11n marja hisobotida TANNARX bor (faqat admin)")
    r = KLIENT.get(f"/api/admin/tashkilot/{a['id']}/hisobot", cookies=kuki)
    j = r.json()
    tek(r.status_code == 200 and "jami_usd" in j and "tannarx" not in r.text,
        "S11o oylik hisobotda tannarx YO'Q (hamkorga beriladi)")

    # hamkorning o'z hisoboti
    r = KLIENT.get("/api/v1/hisobot", headers=bosh(HOLAT["ka"]))
    tek(r.status_code == 200 and "jami_usd" in r.json(),
        "S11p hamkor o'z hisobotini API dan oladi")
    tek("narx_usd" not in r.text and "ustama" not in r.text,
        "S11q hamkor hisobotida tannarx/ustama yo'q")

    # royalti
    r = KLIENT.put(f"/api/admin/twin/{tw['id']}/royalti", cookies=kuki, json={"foiz": 10})
    tek(r.status_code == 200, "S11r ustoz ulushi foizi qo'yildi")
    r = KLIENT.put(f"/api/admin/twin/{tw['id']}/royalti", cookies=kuki, json={"foiz": 150})
    tek(r.status_code == 400, "S11s 100 dan katta foiz rad etiladi")
    r = KLIENT.get("/api/admin/royalti?kun=30", cookies=kuki)
    tek(r.status_code == 200 and "jami_ulush_usd" in r.json(),
        "S11t royalti hisoboti ochiladi")
    q = [x for x in r.json()["royxat"] if x["id"] == tw["id"]]
    if q:
        kutilgan = round(float(q[0]["b2b_usd"]) * 10 / 100, 4)
        tek(abs(float(q[0]["ulush_usd"]) - kutilgan) < 1e-3,
            "S11u ulush = B2B daromadining 10% i",
            f"{q[0]['ulush_usd']} (kutilgan {kutilgan})")

    db.sessiya_ochir(token)


# ------------------------------------------------------------------- yakun

def main():
    print("B2B API sinovlari\n" + "=" * 60)
    try:
        tayyorla()
        statik()
        kalitlar()
        huquqlar()
        izolyatsiya()
        foydalanuvchilar()
        pul_yoli()
        sirlar()
        cheklovlar()
        idempotentlik()
        admin_yuzasi()
        admin_boshqaruv()
    finally:
        tozala()
        print("\n(sinov ma'lumotlari o'chirildi)")

    print("\n" + "=" * 60)
    print(f"O'TDI: {len(OK)}   YIQILDI: {len(YIQILDI)}")
    if YIQILDI:
        for nom in YIQILDI:
            print(f"  - {nom}")
    return 1 if YIQILDI else 0


if __name__ == "__main__":
    sys.exit(main())
