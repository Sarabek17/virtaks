"""Talaffuz qatlamining sinovlari: oltin fayl, muhit bayroqlari, lug'at, tezlik.

    python sinov_talaffuz.py

.venv shart emas — core/normalize.py to'g'ridan-to'g'ri yuklanadi (core paketi
google-genai talab qiladi, normalizatorga u kerak emas). Chiqish kodi 0 —
hammasi yashil.
"""

import importlib.util
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
OLTIN = os.path.join(ROOT, "talaffuz_oltin.txt")


def _yukla():
    spec = importlib.util.spec_from_file_location(
        "normalize", os.path.join(ROOT, "core", "normalize.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_TEKIS = str.maketrans({"ʻ": "'", "ʼ": "'", "’": "'", "‘": "'"})


def _tekis(s: str) -> str:
    return s.translate(_TEKIS)


def oltin_sinov(n) -> list[str]:
    xatolar = []
    soni = 0
    with open(OLTIN, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=>" not in line:
                continue
            kirish, kutilgan = (s.strip() for s in line.split("=>", 1))
            soni += 1
            olindi = _tekis(n.normalize_for_tts(kirish))
            if olindi != _tekis(kutilgan):
                xatolar.append(f"  {kirish!r}: kutilgan {kutilgan!r}, olindi {olindi!r}")
    print(f"oltin fayl: {soni - len(xatolar)}/{soni}")
    return xatolar


def _muhit_bilan(n, key, value, fn):
    old = os.environ.get(key)
    os.environ[key] = value
    try:
        return fn()
    finally:
        if old is None:
            del os.environ[key]
        else:
            os.environ[key] = old


def muhit_sinov(n) -> list[str]:
    xatolar = []
    off = _muhit_bilan(n, "UZ_ORTHOEPY", "off", lambda: n.normalize_for_tts("kitob ketdi"))
    if _tekis(off) != "kitob ketdi":
        xatolar.append(f"  UZ_ORTHOEPY=off ishlamadi: {off!r}")
    skip = _muhit_bilan(n, "UZ_ORTHOEPY_SKIP", "d_t, shs", lambda: n.normalize_for_tts("ketdi ishsiz kitob"))
    if _tekis(skip) != "ketdi ishsiz kitop":
        xatolar.append(f"  UZ_ORTHOEPY_SKIP ishlamadi: {skip!r}")
    rasmiy = n.normalize_for_tts("to'g'ri ma'no")
    if rasmiy != "toʻgʻri maʼno":
        xatolar.append(f"  rasmiy imlo belgisi noto'g'ri: {rasmiy!r}")
    tekis = _muhit_bilan(n, "UZ_APOSTROPHE", "straight", lambda: n.normalize_for_tts("to'g'ri"))
    if tekis != "to'g'ri":
        xatolar.append(f"  UZ_APOSTROPHE=straight ishlamadi: {tekis!r}")
    nomlar = [nom for nom, _ in n.ORTHOEPY_RULES]
    if len(set(nomlar)) != len(nomlar):
        xatolar.append("  qoida nomlari takrorlanadi")
    print(f"muhit bayroqlari: {4 - len(xatolar)}/4, qoidalar: {', '.join(nomlar)}")
    return xatolar


def _lugat_qoy(n, exact: dict, stems: dict):
    """Sinov lug'atini keshga qo'yadi; fayl mtime'i saqlanadi — qayta o'qilmaydi."""
    try:
        mtime = os.path.getmtime(n._USER_DICT_PATH)
    except OSError:
        mtime = None
    n._dict_cache.update(mtime=mtime, exact={**n.PRONUNCIATION_FIXES, **exact}, stems=stems)


def _lugat_tikla(n):
    n._dict_cache.update(mtime="sinov", exact={}, stems={})


def lugat_sinov(n) -> list[str]:
    xatolar = []
    _lugat_qoy(n, {"kitob": "KITOB"}, {"telefon": "tilifon"})
    try:
        holatlar = [
            ("kitob keldi", "KITOB keldi"),          # lug'at qoidadan ustun (b -> p bo'lmaydi)
            ("Kitob.", "KITOB."),
            ("telefonim yo'q", "tilifonim yo'q"),     # o'zak + qo'shimcha
            ("Telefon", "Tilifon"),                   # bosh harf saqlanadi
            ("telefo", "telefo"),                     # o'zakdan qisqa — tegmaydi
        ]
        for kirish, kutilgan in holatlar:
            olindi = _tekis(n.normalize_for_tts(kirish))
            if olindi != kutilgan:
                xatolar.append(f"  lug'at {kirish!r}: kutilgan {kutilgan!r}, olindi {olindi!r}")
        exact, stems = n.parse_pronunciation_lines(
            ["# izoh", "Salom = salam", "kitob* = kitab", "a* = b", "", "bo'sh"]
        )
        if exact != {"salom": "salam"} or stems != {"kitob": "kitab"}:
            xatolar.append(f"  parse_pronunciation_lines: {exact!r} {stems!r}")
    finally:
        _lugat_tikla(n)
    print(f"lug'at: {6 - len(xatolar)}/6")
    return xatolar


def tezlik_sinov(n) -> list[str]:
    """10 000 yozuvli lug'at bilan ham jumla < 2 ms (real-time talab)."""
    xatolar = []
    exact = {f"soz{i}": f"talaffuz{i}" for i in range(9000)}
    stems = {f"ozak{i}": f"o{i}" for i in range(1000)}
    _lugat_qoy(n, exact, stems)
    try:
        jumla = ("Assalomu alaykum, men sizga kitob haqida gapirib beraman: "
                 "ochdi, ketdi, do'stlar bilan avtobusda Toshkentga bordik, soz42 ozak7lar.")
        n.normalize_for_tts(jumla)
        t0 = time.perf_counter()
        for _ in range(300):
            n.normalize_for_tts(jumla)
        ms = (time.perf_counter() - t0) * 1000 / 300
        if ms > 2.0:
            xatolar.append(f"  sekin: {ms:.2f} ms/jumla (chegara 2 ms)")
        print(f"tezlik: {ms:.3f} ms/jumla (10 000 yozuvli lug'at bilan)")
    finally:
        _lugat_tikla(n)
    return xatolar


def main() -> int:
    n = _yukla()
    xatolar = []
    for sinov in (oltin_sinov, muhit_sinov, lugat_sinov, tezlik_sinov):
        xatolar += sinov(n)
    if xatolar:
        print("\nXATOLAR:")
        print("\n".join(xatolar))
        return 1
    print("\nHammasi yashil.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
