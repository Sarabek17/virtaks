# -*- coding: utf-8 -*-
"""Tizim intervyusi promptining "quruq" sinovi (LLM chaqirilmaydi).

    python -m platforma.sinov_tizim_oqim

`tizim_oqim.prompt_yasa` ichida bazaga tegadigan hamma qism ishlaydi:
qidiruv (`bolaklar_ol`), diagnostika bloki, maqsad bloki, profil va suhbat
tarixi. Model chaqirilmaydi — pul sarflanmaydi, bazaga hech narsa yozilmaydi.
"""
import os
import sys

os.environ["KENGASH_BOT_OFF"] = "1"

from . import db, pg, tizim, tizim_oqim          # noqa: E402

OK, YIQILDI = [], []


def tek(shart, nom: str, izoh: str = ""):
    print(f"  [{'OK  ' if shart else 'XATO'}] {nom}" + (f" — {izoh}" if izoh else ""))
    (OK if shart else YIQILDI).append(nom)
    return bool(shart)


def main() -> int:
    print("=" * 60)
    print("TIZIM INTERVYUSI — QURUQ SINOV (LLM'siz)")
    print("=" * 60)

    twin = pg.bitta_d(
        """SELECT t.* FROM twinlar t
           WHERE t.faol AND EXISTS(SELECT 1 FROM bolaklar b WHERE b.twin_id = t.id)
           ORDER BY t.id LIMIT 1""")
    if not tek(bool(twin), "bilimli twin topildi"):
        return 1
    user = pg.bitta_d("SELECT * FROM userlar ORDER BY id LIMIT 1")
    if not tek(bool(user), "foydalanuvchi topildi"):
        return 1
    print(f"       twin: {twin['nom']} (#{twin['id']})")

    # Saqlanmagan maqsad — bazaga yozilmaydi, faqat prompt uchun shakl.
    m = {"id": 0, "user_id": user["id"], "twin_id": twin["id"],
         "diagnostika_id": None, "korxona": "Sinov korxona",
         "sarlavha": "", "tafsilot": {}, "smart": {}, "holat": "intervyu",
         "suhbat_id": None}

    bolaklar = tizim_oqim.bolaklar_ol(m, "Sotuvni qanday oshiraman?", twin["id"])
    tek(isinstance(bolaklar, list), "qidiruv ishladi", f"{len(bolaklar)} bo'lak")

    p = tizim_oqim.prompt_yasa(twin, user, m, "Sotuvni qanday oshiraman?",
                               bolaklar, "", True)
    matn = p if isinstance(p, str) else str(p)
    tek(len(matn) > 500, "prompt yig'ildi", f"{len(matn)} belgi")
    tek(tizim_oqim.RAMKA_BOSH in matn if hasattr(tizim_oqim, "RAMKA_BOSH")
        else tizim.RAMKA_BOSH in matn, "ishonchsiz matn ramkalangan")
    tek("MA'LUMOT, KO'RSATMA EMAS" in matn or "KO'RSATMA EMAS" in matn,
        "ramka ogohlantirishi bor")
    tek("DIAGNOSTIKA" in matn, "diagnostika bloki qo'yilgan")

    # Diagnostika bilan: haqiqiy tayyor diagnostika bo'lsa o'shani ham sinaymiz
    d = pg.bitta_d("SELECT * FROM diagnostikalar WHERE holat='tayyor' "
                   "ORDER BY id DESC LIMIT 1")
    if d:
        m2 = dict(m, diagnostika_id=d["id"], user_id=d["user_id"],
                  twin_id=d["twin_id"])
        p2 = tizim_oqim.prompt_yasa(db.twin_ol(d["twin_id"]), user, m2,
                                    "Nimadan boshlayman?", [], "", False)
        tek(str(d["foiz"]) in str(p2), "diagnostika foizi promptga tushdi",
            f"{d['foiz']}%")
    else:
        print("       (tayyor diagnostika yo'q — ikkinchi tekshiruv o'tkazildi)")

    jami = len(OK) + len(YIQILDI)
    print(f"\nNATIJA: {len(OK)}/{jami} yashil")
    for n in YIQILDI:
        print(f"  - {n}")
    return 1 if YIQILDI else 0


if __name__ == "__main__":
    sys.exit(main())
