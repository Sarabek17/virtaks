# -*- coding: utf-8 -*-
"""Cutover oldidan tayyorlik ko'rigi — "hammasi joyidami?" degan savolga javob.

  python -m platforma.tayyorlik            # to'liq ko'rik
  python -m platforma.tayyorlik --tez      # S3 yozish sinovisiz

Har tekshiruv uch holatdan biri: OK / OGOH (ishlaydi, lekin e'tibor bering) /
XATO (cutover qilinmaydi). Chiqish kodi: XATO bo'lsa 1.

SIRLAR HECH QACHON CHOP ETILMAYDI — faqat "bor/yo'q" va uzunlik ko'rsatiladi.
"""
import argparse
import os
import sys

from . import auth, llm, pg, pul, storage, zaxira
from .sozlama import log

XATO, OGOH = [], []


def _bel(holat: str) -> str:
    return {"ok": "OK  ", "ogoh": "OGOH", "xato": "XATO"}[holat]


def tek(shart, izoh: str, qosh: str = "", muhim: bool = True):
    """muhim=False -> muvaffaqiyatsizlik ogohlantirish (cutoverni to'xtatmaydi)."""
    holat = "ok" if shart else ("xato" if muhim else "ogoh")
    print(f"  [{_bel(holat)}] {izoh}" + (f" — {qosh}" if qosh else ""))
    if holat == "xato":
        XATO.append(izoh)
    elif holat == "ogoh":
        OGOH.append(izoh)


def bolim(nom: str):
    print(f"\n=== {nom} " + "=" * max(0, 54 - len(nom)))


def _env_bor(nom: str) -> tuple[bool, str]:
    """Qiymat BOR-YO'Qligi. Qiymatning o'zi hech qachon chop etilmaydi.

    auth._env lokalda `.env` faylidan ham o'qiydi — bulutda esa faqat
    muhit o'zgaruvchisidan; ikkalasi ham shu yerdan ko'rinadi.
    """
    q = auth._env(nom)
    return bool(q), (f"{len(q)} belgi" if q else "yo'q")


# ---------------------------------------------------------------- 1. muhit

def muhit():
    bolim("1. Muhit o'zgaruvchilari")
    from .sozlama import PG_URL, S3_BAKET, S3_ENDPOINT, S3_KIRISH, S3_MAXFIY
    for nom, qiymat in (("PG_URL", PG_URL), ("S3_ENDPOINT", S3_ENDPOINT),
                        ("S3_KIRISH", S3_KIRISH), ("S3_MAXFIY", S3_MAXFIY),
                        ("S3_BAKET", S3_BAKET)):
        tek(bool(qiymat), f"{nom} sozlangan",
            f"{len(qiymat)} belgi" if qiymat else "yo'q")
    for nom in ("GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN"):
        bor, izoh = _env_bor(nom)
        tek(bor, f"{nom} sozlangan", izoh)
    tek(not auth.dev_rejim(), "dev-rejim O'CHIQ (prodda parolsiz kirish bo'lmaydi)",
        "bot tokeni bor bo'lsa avtomatik o'chadi")
    tek(bool(auth.public_url()), "PUBLIC_URL sozlangan (TG widget/webhook uchun)",
        auth.public_url() or "yo'q", muhim=False)

    bot_off = (os.environ.get("KENGASH_BOT_OFF") or "").strip() == "1"
    print(f"       KENGASH_BOT_OFF={'1' if bot_off else '0'} — cutover kuni YANGI "
          f"web'da 0, ESKI servisda bot to'xtatilgan bo'lishi kerak")

    tolov_muhiti()


def tolov_muhiti():
    """To'lov provayderlari. Kvota yoqilgan bo'lsa — bu MAJBURIY tekshiruv."""
    from . import pul
    paylov = all(_env_bor(n)[0] for n in
                 ("PAYLOV_MERCHANT_ID", "PAYLOV_CALLBACK_LOGIN",
                  "PAYLOV_CALLBACK_PAROL"))
    click = all(_env_bor(n)[0] for n in
                ("CLICK_SERVICE_ID", "CLICK_MERCHANT_ID", "CLICK_SECRET"))
    payme = all(_env_bor(n)[0] for n in ("PAYME_MERCHANT_ID", "PAYME_KEY"))

    # Kvota yoqiq bo'lsa mijoz to'lay olmasa — bu jonli tizimda XATO,
    # o'chiq bo'lsa hali hech kim to'siqqa uchramaydi (ogohlantirish yetarli).
    try:
        kvota = pul.kvota_faolmi()
    except Exception:                                        # noqa: BLE001
        kvota = False
    tek(paylov or click or payme, "kamida bitta to'lov provayderi sozlangan",
        f"paylov={'ha' if paylov else 'yo’q'} click={'ha' if click else 'yo’q'} "
        f"payme={'ha' if payme else 'yo’q'}"
        + (" · kvota YOQILGAN" if kvota else " · kvota o'chiq"),
        muhim=kvota)

    if paylov:
        tiyinda = (os.environ.get("PAYLOV_TIYINDA") or "1").strip() == "1"
        print(f"       Paylov summani {'TIYINDA' if tiyinda else 'SO‘MDA'} "
              f"yuboradi (PAYLOV_TIYINDA) — jonli sinovda 1 000 so'mlik "
              f"to'lov bilan tasdiqlang")
        tek(bool(auth.public_url()),
            "Paylov uchun PUBLIC_URL kerak (return_url shundan quriladi)",
            auth.public_url() or "yo'q")
        print(f"       Callback URL: {auth.public_url()}/tolov/paylov")


# ---------------------------------------------------------------- 2. baza

def baza():
    bolim("2. Baza va migratsiyalar")
    fayllar = sorted(p.name for p in pg.MIGRATSIYALAR.glob("*.sql"))
    qollangan = {r[0] for r in pg.hammasi("SELECT nom FROM migratsiyalar")}
    yetmagan = [f for f in fayllar if f not in qollangan]
    tek(not yetmagan, f"{len(fayllar)} migratsiya qo'llangan",
        ("yetmagan: " + ", ".join(yetmagan)) if yetmagan else "")

    v = pg.bitta("SELECT extversion FROM pg_extension WHERE extname='vector'")
    tek(bool(v), "pgvector kengaytmasi o'rnatilgan", v[0] if v else "yo'q")

    ind = pg.bitta("""SELECT indexname FROM pg_indexes
                      WHERE tablename='bolaklar' AND indexdef ILIKE '%hnsw%'""")
    tek(bool(ind), "HNSW vektor indeksi bor", ind[0] if ind else "yo'q")

    n = pg.bitta("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()")[0]
    tek(n < 80, "ulanishlar soni normal", f"{n} ta", muhim=False)


# ---------------------------------------------------------------- 3. ombor

def ombor(tez: bool):
    bolim("3. Ombor (MinIO/S3)")
    try:
        storage.baket_tayyorla()
        tek(True, "baketga ulanildi")
    except Exception as e:                                   # noqa: BLE001
        tek(False, "baketga ulanildi", f"{type(e).__name__}: {str(e)[:80]}")
        return
    if tez:
        print("       (--tez: yozish sinovi o'tkazib yuborildi)")
        return
    yol = "tayyorlik/sinov.txt"
    try:
        storage.yukla(yol, b"tayyorlik", "text/plain")
        ok = storage.bormi(yol) and storage.ol(yol) == b"tayyorlik"
        storage.ochir(yol)
        tek(ok and not storage.bormi(yol), "yozish/o'qish/o'chirish ishlaydi")
    except Exception as e:                                   # noqa: BLE001
        tek(False, "yozish/o'qish/o'chirish ishlaydi",
            f"{type(e).__name__}: {str(e)[:80]}")


# ---------------------------------------------------------------- 4. bilim

def bilim():
    bolim("4. Bilim bazasi")
    t = pg.hammasi_d("""SELECT t.id, t.nom, t.faol,
             (SELECT count(*) FROM manbalar m WHERE m.twin_id=t.id) manba,
             (SELECT count(*) FROM bolaklar b WHERE b.twin_id=t.id) bolak,
             (SELECT count(*) FROM direktorlar d
                WHERE d.twin_id=t.id OR d.twin_id IS NULL) direktor
           FROM twinlar t ORDER BY t.id""")
    for x in t:
        print(f"       twin #{x['id']} {x['nom']}: {x['manba']} manba, "
              f"{x['bolak']} bo'lak, {x['direktor']} direktor, "
              f"{'faol' if x['faol'] else 'O‘CHIQ'}")
    tek(any(x["faol"] and x["bolak"] > 0 for x in t),
        "kamida bitta faol twinda bilim bor")

    yoq = pg.bitta("SELECT count(*) FROM bolaklar WHERE embedding IS NULL")[0]
    jami = pg.bitta("SELECT count(*) FROM bolaklar")[0]
    tek(yoq == 0, f"barcha bo'laklarda vektor bor ({jami} ta)", f"{yoq} ta vektorsiz")

    rais = pg.bitta("SELECT count(*) FROM direktorlar WHERE kod='RAIS' AND faol")[0]
    tek(rais >= 1, "RAIS personasi faol", f"{rais} ta")

    # asl fayl = fragment/slayd uchun kerak (web manbalarida bo'lmasligi tabiiy)
    aslsiz = pg.hammasi("""SELECT id, nom FROM manbalar
                           WHERE tur <> 'web' AND COALESCE(s3_yol,'')=''
                           ORDER BY id""")
    tek(not aslsiz, "har manbaning asl fayli omborda",
        f"{len(aslsiz)} ta asl faylsiz", muhim=False)

    xato_m = pg.bitta("SELECT count(*) FROM manbalar WHERE holat='xato'")[0]
    tek(xato_m == 0, "xato holatida qolgan manba yo'q", f"{xato_m} ta", muhim=False)


# ---------------------------------------------------------------- 5. userlar

def userlar():
    bolim("5. Foydalanuvchilar va rollar")
    a = pg.hammasi_d("""SELECT id, ism, login, parol_hash IS NOT NULL parolli
                        FROM userlar WHERE rol='admin' ORDER BY id""")
    for x in a:
        print(f"       admin #{x['id']} {x['ism']} "
              f"({'parolli' if x['parolli'] else 'PAROLSIZ'})")
    tek(bool(a), "kamida bitta admin bor")
    tek(any(x["parolli"] for x in a), "kamida bitta admin parol bilan kira oladi")

    e = pg.bitta("SELECT count(*) FROM twinlar WHERE egasi_id IS NOT NULL")[0]
    tek(e > 0, "twinlarga egasi biriktirilgan", f"{e} ta", muhim=False)

    s = pg.bitta("SELECT count(*) FROM sessiyalar WHERE muddat < now()")[0]
    tek(True, "muddati o'tgan sessiyalar", f"{s} ta (avtomatik tozalanadi)")


# ---------------------------------------------------------------- 6. pul

def pullar():
    bolim("6. Pul: narxlar, planlar, kvota")
    modellar = set(llm.AGENT_MODELLAR + llm.RAIS_MODELLAR + llm.TEZ_MODELLAR
                   + llm.STT_MODELLAR + llm.OCR_MODELLAR + [llm.EMBED_MODEL])
    bor = {r[0] for r in pg.hammasi("SELECT model FROM model_narxlar")}
    yoq = sorted(modellar - bor)
    tek(not yoq, f"ishlatiladigan {len(modellar)} model narxi bazada",
        ("narxsiz: " + ", ".join(yoq)) if yoq else "")

    p = pg.hammasi_d("""SELECT nom, oylik_narx_som, kvota_usd, kun_soni, faol
                        FROM planlar ORDER BY tartib, id""")
    for x in p:
        print(f"       plan «{x['nom']}»: {x['oylik_narx_som']} so'm / "
              f"{x['kun_soni']} kun, kvota ${x['kvota_usd']}, "
              f"{'faol' if x['faol'] else 'o‘chiq'}")
    tek(any(x["faol"] for x in p), "kamida bitta faol plan bor")
    tek(all(x["oylik_narx_som"] > 0 and x["kvota_usd"] > 0 for x in p if x["faol"]),
        "faol planlarda narx va kvota belgilangan")

    x = pul.moliya_xulosa(30)
    print(f"       kvota nazorati: {'YOQIQ' if x['kvota_faol'] else 'o‘chiq'} | "
          f"jami xarajat ${x['xarajat_jami_usd']} | "
          f"daromad {x['daromad_som']} so'm | "
          f"faol obuna {x['obuna_faol']} | "
          f"1 majlis ≈ ${x['taxminiy_majlis_usd']}")
    tek(True, "moliya xulosasi o'qildi",
        "kvota nazorati narx tasdiqlangach admin paneldan yoqiladi")


# ---------------------------------------------------------------- 7. navbat

def navbat():
    bolim("7. Navbat va davriy ishlar")
    h = pg.hammasi_d("SELECT holat, count(*) n FROM jobs GROUP BY 1 ORDER BY 1")
    print("      ", {x["holat"]: x["n"] for x in h})
    q = pg.bitta("""SELECT count(*) FROM jobs WHERE holat='ketmoqda'
                    AND boshlangan < now() - make_interval(secs => muhlat_s)""")[0]
    tek(q == 0, "qotib qolgan job yo'q", f"{q} ta")
    x = pg.bitta("""SELECT count(*) FROM jobs WHERE holat='xato'
                    AND tugagan > now() - interval '24 hours'""")[0]
    tek(x == 0, "so'nggi sutkada yakuniy xato bo'lgan job yo'q", f"{x} ta",
        muhim=False)
    n = pg.bitta("""SELECT count(*) FROM jobs WHERE holat='navbatda'
                    AND yaratilgan < now() - interval '1 hour'""")[0]
    tek(n == 0, "bir soatdan ko'p navbatda turgan job yo'q", f"{n} ta", muhim=False)

    for tur in ("obuna_nazorat", "zaxira"):
        r = pg.bitta("""SELECT to_char(max(tugagan),'YYYY-MM-DD HH24:MI') FROM jobs
                        WHERE tur=%s AND holat='tayyor'""", tur)
        tek(bool(r and r[0]), f"«{tur}» davriy jobi bajarilgan",
            (r[0] if r and r[0] else "hali bajarilmagan"), muhim=False)


# ---------------------------------------------------------------- 8. zaxira

def zaxiralar():
    bolim("8. Zaxira nusxalari")
    try:
        z = zaxira.royxat()
    except Exception as e:                                   # noqa: BLE001
        tek(False, "zaxira ro'yxati o'qildi", f"{type(e).__name__}: {str(e)[:60]}",
            muhim=False)
        return
    for x in z[:3]:
        print(f"       {x['yol']}")
    tek(bool(z), "kamida bitta zaxira nusxasi bor",
        f"{len(z)} ta", muhim=False)


# ---------------------------------------------------------------- 9. web

def web_ko():
    bolim("9. Web: sarlavhalar va statik")
    from fastapi.testclient import TestClient

    from . import web as W
    k = TestClient(W.app)
    r = k.get("/")
    csp = r.headers.get("content-security-policy", "")
    tek(r.status_code == 200, "bosh sahifa ochiladi", str(r.status_code))
    tek("connect-src 'self'" in csp, "CSP: tashqi kanal yopiq")
    # img-src da Telegram avatar CDN lari bor (bu joiz) — skript manbai muhim
    skript = next((q for q in csp.split("; ") if q.startswith("script-src")), "")
    tek(not any(x in skript for x in ("jsdelivr", "unpkg", "cdnjs")),
        "CSP: skript tashqi CDN dan olinmaydi", skript)
    tek(r.headers.get("x-content-type-options") == "nosniff", "nosniff sarlavhasi")
    tek(k.get("/static/mermaid.min.js").status_code == 200,
        "mermaid o'z serverimizdan beriladi")
    tek(k.get("/static/../web.py").status_code in (400, 404),
        "statik yo'ldan chiqib ketish to'silgan")
    tek(k.get("/api/suhbatlar").status_code == 401, "anonim API yopiq")
    s = k.get("/salomatlik")
    tek(s.status_code == 200, "/salomatlik javob beradi", str(s.status_code))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tez", action="store_true", help="S3 yozish sinovisiz")
    args = p.parse_args()

    print("CUTOVER TAYYORLIK KO'RIGI")
    muhit()
    baza()
    ombor(args.tez)
    bilim()
    userlar()
    pullar()
    navbat()
    zaxiralar()
    web_ko()

    print("\n" + "=" * 60)
    if XATO:
        print(f"NATIJA: {len(XATO)} XATO — cutover QILINMAYDI")
        for x in XATO:
            print(f"  - {x}")
    else:
        print("NATIJA: TO'SIQ YO'Q — cutover mumkin")
    if OGOH:
        print(f"\nOgohlantirish ({len(OGOH)} ta — to'sqinlik qilmaydi):")
        for x in OGOH:
            print(f"  - {x}")
    return 1 if XATO else 0


if __name__ == "__main__":
    log("tayyorlik ko'rigi boshlandi")
    sys.exit(main())
