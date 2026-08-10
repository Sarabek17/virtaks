# -*- coding: utf-8 -*-
"""Tekshiruv — grounding nazorati.

1. iqtibos_tekshir: javobdagi [n] raqamlari haqiqiy manbalarga mos kelishini tekshiradi.
2. global_raqamlash: har direktorning lokal [n] raqamlarini yagona global raqamlashga o'tkazadi,
   shunda yakuniy hisobotda bitta [n] = bitta aniq manba (fayl + joy).
"""
import re

# [1], [2, 5] ko'rinishidagi iqtiboslar; vaqt belgilariga ([0:34:12]) tegmaydi
IQTIBOS = re.compile(r"\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]")


def _raqamlar(matn: str) -> list[int]:
    nat = []
    for m in IQTIBOS.finditer(matn):
        nat += [int(r) for r in m.group(1).split(",")]
    return nat


def iqtibos_tekshir(javob: str, manba_soni: int) -> str | None:
    """Xato bo'lsa izohini, hammasi joyida bo'lsa None qaytaradi."""
    r = _raqamlar(javob)
    notogri = sorted({n for n in r if n < 1 or n > manba_soni})
    if notogri:
        return (f"mavjud bo'lmagan manba raqamlari ishlatilgan: {notogri} "
                f"(haqiqiy oraliq: 1–{manba_soni})")
    # apostrof variantlari (’ ʻ ') farq qilmasin
    toza = re.sub(r"[’ʻ`']", "", javob.upper())
    if not r and "MANBADA YO" not in toza:
        return "birorta [n] iqtibos yo'q va 'MANBADA YO'Q' ham aytilmagan"
    return None


def global_raqamlash(javoblar: list[dict]) -> list[dict]:
    """Direktorlar javoblaridagi lokal [n] larni yagona global raqamlashga almashtiradi.

    javoblar o'zgartiriladi (javob matni + 'global' ro'yxati qo'shiladi).
    Qaytaradi: global manbalar reestri [{g, id, manba, joy, tur, dars}, ...] tartib bilan.
    """
    reestr: dict[str, dict] = {}   # bo'lak id -> global yozuv
    tartib: list[dict] = []

    for j in javoblar:
        xarita = {}   # lokal n -> global g
        for m in j["manbalar"]:
            kalit = m["id"]
            if kalit not in reestr:
                reestr[kalit] = {**m, "g": len(tartib) + 1}
                tartib.append(reestr[kalit])
            xarita[m["n"]] = reestr[kalit]["g"]

        def almashtir(mo):
            yangi = []
            for r in mo.group(1).split(","):
                n = int(r)
                yangi.append(str(xarita[n]) if n in xarita else "?")
            return "[" + ", ".join(yangi) + "]"

        j["javob"] = IQTIBOS.sub(almashtir, j["javob"])
        j["global"] = sorted(set(xarita.values()))
    return tartib
