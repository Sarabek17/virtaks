# -*- coding: utf-8 -*-
"""B2B ning JONLI (uchidan-uchiga) sinovi — deploydan keyingi tutun sinovi.

    python -m platforma.sinov_jonli

⚠️ BU SINOV MODELNI HAQIQATAN CHAQIRADI va bir necha sent sarflaydi.
Qolgan sinovlar (`sinov_b2b`) modelsiz ishlaydi — kundalik ish uchun
o'shalar. Bu esa deploydan keyin bir marta: zanjir butunmi?

    kalit -> izolyatsiya -> qidiruv -> model -> iqtibos -> hisob -> balans

O'zining sinov tashkilotini (`slug='jonli-sinov'`) yaratadi va oxirida
o'chiradi; bazadagi mavjud twin va bilimdan foydalanadi, hech narsani
o'zgartirmaydi. Twin va bo'lak bo'lmasa — tushunarli xato bilan chiqadi.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
os.environ["KENGASH_BOT_OFF"] = "1"

from fastapi.testclient import TestClient                      # noqa: E402

from . import b2b, db, pg, web                                 # noqa: E402

K = TestClient(web.app)
OK = XATO = 0


def tek(shart, izoh, qosh=""):
    global OK, XATO
    print(f"  [{'OK  ' if shart else 'XATO'}] {izoh}" + (f" — {qosh}" if qosh else ""))
    if shart:
        OK += 1
    else:
        XATO += 1


pg.bajar("DELETE FROM tashkilotlar WHERE slug='jonli-sinov'")

twin = pg.bitta_d(
    """SELECT t.* FROM twinlar t WHERE t.faol
        AND EXISTS (SELECT 1 FROM bolaklar b WHERE b.twin_id = t.id)
        ORDER BY t.id LIMIT 1""")
if not twin:
    sys.exit("Bilimi bor faol twin topilmadi — avval bilim bazasini to'ldiring "
             "(DEPLOY_DO.md §6).")
bolak = pg.bitta("SELECT count(*) FROM bolaklar WHERE twin_id=%s", twin["id"])[0]
print(f"\nTwin: «{twin['nom']}» ({bolak} bo'lak)\n")

t = b2b.tashkilot_yasa("Jonli sinov", "jonli-sinov", ustama=3.0)
b2b.twin_qosh(t["id"], twin["id"])
b2b.toldir(t["id"], 5.0, "jonli sinov depoziti")
kalit, _ = b2b.kalit_yasa(t["id"], "jonli")
bosh = {"Authorization": f"Bearer {kalit}"}

balans_oldin = float(b2b.tashkilot_ol(t["id"])["balans_usd"])

print("Savol yuborilmoqda (model chaqiriladi)...\n")
r = K.post("/api/v1/savol", headers=bosh, timeout=180, json={
    "tashqi_id": "jonli-mijoz-1",
    "ism": "Sinov mijoz",
    "savol": "Sotuv bo'limini qanday tashkil qilaman?",
    "twin": twin["slug"],
    "oqim": False,
})

tek(r.status_code == 200, "so'rov 200 qaytardi", str(r.status_code))
if r.status_code != 200:
    print("  tana:", r.text[:400])
    pg.bajar("DELETE FROM tashkilotlar WHERE slug='jonli-sinov'")
    sys.exit(1)

j = r.json()
javob = j.get("javob", "")
print("\n--- JAVOB (birinchi 400 belgi) ---")
print(javob[:400])
print("--- /JAVOB ---\n")

tek(len(javob) > 100, "javob matni bor", f"{len(javob)} belgi")
tek(bool(j.get("manbalar")), "iqtiboslar qaytdi", f"{len(j.get('manbalar', []))} ta")
tek("](" not in javob, "javobda markdown HAVOLA sintaksisi yo'q")
tek(j.get("suhbat") and j.get("javob_id"), "suhbat va javob_id berildi",
    f"suhbat={j.get('suhbat')} javob={j.get('javob_id')}")

hisob = j.get("hisob", {})
tek(hisob.get("sarf_usd", 0) > 0, "hamkorga hisob yozildi",
    f"${hisob.get('sarf_usd')}")

balans_keyin = float(b2b.tashkilot_ol(t["id"])["balans_usd"])
tek(abs((balans_oldin - balans_keyin) - hisob["sarf_usd"]) < 1e-4,
    "balansdan AYNAN shu summa yechildi",
    f"{balans_oldin} -> {balans_keyin}")

x = pg.hammasi_d(
    """SELECT model, bosqich, narx_usd, hisob_usd, tashkilot_id
       FROM xarajatlar WHERE tashkilot_id=%s ORDER BY id""", t["id"])
tek(len(x) > 0, "xarajatlar yozildi", f"{len(x)} chaqiruv")
tannarx = sum(float(q["narx_usd"]) for q in x)
hisob_jami = sum(float(q["hisob_usd"]) for q in x)
tek(abs(hisob_jami - tannarx * 3.0) < 1e-4, "hisob = tannarx * 3.0",
    f"tannarx ${tannarx:.5f} -> hisob ${hisob_jami:.5f}")
for q in x:
    print(f"       {q['bosqich']:12} {q['model']:24} ${float(q['narx_usd']):.6f} "
          f"-> ${float(q['hisob_usd']):.6f}")

# Iqtibos haqiqiy bo'lakka ishora qiladimi
for m in j.get("manbalar", [])[:3]:
    b = db.bolak_ol(m["bolak"])
    tek(b is not None and b["twin_id"] == twin["id"],
        f"iqtibos [{m['n']}] haqiqiy bo'lak va SHU twinniki", m["manba"][:40])

# Tannarx sizib chiqmaganini tekshiramiz
tek("narx_usd" not in r.text and "gemini" not in r.text.lower(),
    "javobda TANNARX va MODEL nomi yo'q")

# Suhbatni davom ettirish
r2 = K.get(f"/api/v1/suhbat/{j['suhbat']}", headers=bosh)
tek(r2.status_code == 200 and len(r2.json()["xabarlar"]) == 1,
    "suhbat tarixi API dan o'qildi")

# Hisobot
r3 = K.get("/api/v1/hisobot", headers=bosh)
tek(r3.status_code == 200 and r3.json()["savollar"] >= 1,
    "oylik hisobotda savol ko'rindi", f"{r3.json().get('savollar')} savol")

pg.bajar("DELETE FROM tashkilotlar WHERE slug='jonli-sinov'")
print(f"\nNATIJA: {OK} o'tdi, {XATO} yiqildi")
sys.exit(1 if XATO else 0)
