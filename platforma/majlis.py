# -*- coding: utf-8 -*-
"""Majlis (orkestr) — worker job sifatida.

Oqim: profil+suhbat konteksti -> mustaqil savol -> rais yo'naltirish ->
direktorlar parallel -> yagona raqamlash -> rais sintez -> DB ga yozish ->
skill'lar (shablon fayl) -> profil yangilash.
"""
import contextvars
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout

from . import agentlar, db, profil, pul, skilllar, suhbat
from .tekshiruv import global_raqamlash

AGENT_MUHLAT = 900     # barcha direktorlar javobiga umumiy chegara


def bajar(job: dict, yoz) -> dict:
    """job.kirish: {savol, suhbat_id, twin_id, hamma}"""
    bosh = time.time()
    k = job["kirish"]
    uid = job["user_id"]
    savol = k["savol"]
    suhbat_id = k.get("suhbat_id")
    twin = db.twin_ol(k["twin_id"])
    if not twin:
        raise RuntimeError("twin topilmadi")
    pul.kontekst_boshla(user_id=uid, twin_id=twin["id"], job_id=job["id"])

    yoz(f"=== MAJLIS: {twin['nom']} ===")
    yoz(f"Savol: {savol}")
    skill_holati = skilllar.faollar(twin["id"])
    ochiq = [k for k, v in skill_holati.items() if not v]
    if ochiq:
        yoz(f"O'chirilgan skilllar: {', '.join(ochiq)}")

    # --- kontekst: profil + shu sessiya suhbati ---
    user = db.user_ol(uid) or {}
    ktx = suhbat.kontekst(uid, suhbat_id)
    savol_m = suhbat.mustaqil(savol, ktx)
    if savol_m != savol:
        yoz(f"Mustaqil savol: {savol_m[:150]}")
    suhbat_matni = suhbat.formatla(ktx)

    # Profil 2.0: tuzilgan profil javob uzunligi/atama darajasini boshqaradi,
    # matnli profil esa kontekst beradi (ikkalasi ham FAKT MANBASI EMAS).
    moslashuv = profil.moslashuv_bloki(user)
    uzunlik = profil.uzunlik_qoidasi(user)
    tuzilma = profil.rais_tuzilmasi(user)
    if profil.uslub_kodi(user) != profil.STANDART_USLUB:
        yoz(f"Javob uslubi profilga moslandi: {profil.uslub_kodi(user)}")

    qismlar = []
    if suhbat_matni:
        qismlar.append(f"SUHBAT TARIXI (savol shunga ishora qilishi mumkin; "
                       f"fakt manbasi EMAS):\n{suhbat_matni}")
    kontekst = "\n\n".join(qismlar)

    # --- direktorlar ---
    hammasi = db.direktorlar(twin["id"])
    rais = next((d for d in hammasi if d["rais"]), None)
    direktorlar = [d for d in hammasi if not d["rais"]]
    if not direktorlar:
        raise RuntimeError("faol direktor yo'q — admin paneldan qo'shing")
    if not rais:
        raise RuntimeError("RAIS direktori sozlanmagan")

    tanlov = direktorlar if k.get("hamma") else \
        agentlar.rais_yonaltirish(rais, direktorlar, savol_m)
    yoz(f"RAIS yo'naltirdi: {', '.join(d['kod'] for d in tanlov)}")

    javoblar = []
    ex = ThreadPoolExecutor(max_workers=max(1, len(tanlov)))
    # Xarajat konteksti oqimlarga NUSXA bilan uzatiladi — aks holda direktorlar
    # sarflagan pul daftarga tushmay qolardi (threading.local oqimni kesib o'tmaydi).
    # Har oqimga ALOHIDA nusxa: bitta Context obyektini ikki oqim bir vaqtda
    # ishlata olmaydi, lekin nusxalar ayni bir daftar ro'yxatiga yozadi.
    fut = {ex.submit(contextvars.copy_context().run,
                     agentlar.direktor_javobi, d, savol_m, twin, kontekst,
                     uzunlik, moslashuv): d
           for d in tanlov}
    try:
        for f in as_completed(fut, timeout=AGENT_MUHLAT):
            try:
                j = f.result()
                javoblar.append(j)
                yoz(f"{j['rol']} javob berdi ({len(j['javob'])} belgi, "
                    f"{len(j['manbalar'])} manba)")
            except Exception as e:
                yoz(f"{fut[f]['kod']} XATO: {str(e)[:120]}")
    except FuturesTimeout:
        qoldi = [d["kod"] for f, d in fut.items() if not f.done()]
        yoz(f"MUHLAT TUGADI ({AGENT_MUHLAT}s): {', '.join(qoldi)} javobsiz")
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

    if not javoblar:
        raise RuntimeError("birorta direktor javob bermadi")
    tartib = {d["kod"]: i for i, d in enumerate(direktorlar)}
    javoblar.sort(key=lambda j: tartib.get(j["rol"], 99))

    # --- yagona raqamlash + sintez ---
    reestr = global_raqamlash(javoblar)
    manba_royxati = "\n".join(f"[{m['g']}] {m['manba']} — {m['joy']}" for m in reestr)
    yoz(f"Manbalar birlashtirildi: {len(reestr)} noyob bo'lak")

    yoz("RAIS sintez qilmoqda...")
    xulosa = agentlar.rais_sintez(rais, savol_m, javoblar, twin,
                                  manba_royxati, len(reestr), suhbat=suhbat_matni,
                                  tuzilma=tuzilma, moslashuv=moslashuv,
                                  diagramma=skill_holati.get("diagramma", True))

    # --- saqlash ---
    davomiylik = round(time.time() - bosh)
    hisobot = {"direktorlar": [{"rol": j["rol"], "nom": j["nom"], "rang": j["rang"],
                                "javob": j["javob"], "global": j["global"]}
                               for j in javoblar],
               "manbalar": reestr,
               "twin": {"id": twin["id"], "nom": twin["nom"]}}
    mid = db.majlis_yoz(uid, suhbat_id, twin["id"], savol, savol_m, xulosa,
                        hisobot, davomiylik, job_id=job["id"])

    # --- skilllar (orkestr faqat YOQILGANLARIDAN tanlaydi) ---
    faol_amallar = [k for k, v in skill_holati.items()
                    if v and skilllar.REGISTR[k]["tur"] == "amal"]
    tanlangan = skilllar.tanla(savol_m, xulosa, faol_amallar, yoz) if faol_amallar \
        else []
    if not faol_amallar:
        yoz("Skilllar o'chirilgan — orkestr chaqirilmadi")
    natijalar = skilllar.bajar(tanlangan, {
        "savol": savol_m, "xulosa": xulosa, "twin_id": twin["id"],
        "majlis_id": mid, "user_id": uid}, yoz)
    if natijalar:
        hisobot["skilllar"] = natijalar
        db.majlis_hisobot(mid, hisobot)

    # Narx daftardan (xarajatlar jadvali) olinadi — oqimlararo yo'qolmaydi.
    narx = pul.majlis_yakunla(job, mid)
    yoz(f"TAYYOR ({davomiylik}s, ${narx:.4f}): majlis #{mid}")

    # --- fonda: user profilini o'rganish ---
    threading.Thread(target=profil.yangila, args=(uid,), daemon=True).start()

    return {"majlis_id": mid, "davomiylik": davomiylik, "narx_usd": narx,
            "direktorlar": [j["rol"] for j in javoblar],
            "skilllar": list(natijalar)}
