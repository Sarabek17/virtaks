"""Korpusdan talaffuz ro'yxati: so'z chastotasi + orfoepiya qoidalari ta'siri.

    python talaffuz_korpus.py                          # transkript/chiqish/*/toliq_matn.txt
    python talaffuz_korpus.py matn.txt papka/ ...      # qo'shimcha manbalar (.txt, rekursiv)
    python talaffuz_korpus.py --chiqish royxat.tsv --eng-kop 10000

Natija — TSV (so'z, soni, talaffuz, qoidalar, manba): eng ko'p uchraydigan
so'zdan boshlab ko'rib chiqiladigan ro'yxat. Har qator uchun uch xil qaror:
  (a) qoida to'g'ri            — hech narsa qilinmaydi
  (b) qoida noto'g'ri          — .env da UZ_ORTHOEPY_SKIP=nom, ORFOEPIYA_REJA.md ga yozuv
  (c) so'z istisno             — talaffuz.txt ga qator
So'z yakka holda ko'riladi (keyingi so'z yo'q deb), shuning uchun so'z
oxiridagi b/d/g doim jarangsiz ko'rsatiladi.
"""

import argparse
import collections
import glob
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
STANDART_MANBA = os.path.join(ROOT, "transkript", "chiqish", "*", "toliq_matn.txt")


def _yukla():
    spec = importlib.util.spec_from_file_location(
        "normalize", os.path.join(ROOT, "core", "normalize.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fayllar(manbalar: list[str]) -> list[str]:
    if not manbalar:
        return sorted(glob.glob(STANDART_MANBA))
    out = []
    for m in manbalar:
        if os.path.isdir(m):
            out += sorted(glob.glob(os.path.join(m, "**", "*.txt"), recursive=True))
        else:
            out += sorted(glob.glob(m)) or [m]
    return out


def sozlar(n, yollar: list[str]) -> collections.Counter:
    soni: collections.Counter = collections.Counter()
    for yol in yollar:
        with open(yol, encoding="utf-8") as f:
            matn = n.strip_markup(f.read()).lower()
        matn = n.translit_cyr_to_lat(matn)
        for m in n._WORD_RE.finditer(matn):
            w = m.group(0).strip("'")
            if len(w) > 1:
                soni[w] += 1
    return soni


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("manbalar", nargs="*", help=".txt fayl yoki papka (standart: transkript)")
    p.add_argument("--chiqish", default=os.path.join(ROOT, "talaffuz_korpus.tsv"))
    p.add_argument("--eng-kop", type=int, default=10000, help="ro'yxatga nechta so'z (chastota bo'yicha)")
    args = p.parse_args()

    n = _yukla()
    yollar = fayllar(args.manbalar)
    if not yollar:
        print("Manba topilmadi.")
        return 1
    soni = sozlar(n, yollar)
    jami = sum(soni.values())
    print(f"manbalar: {len(yollar)} fayl | jami so'z: {jami} | noyob: {len(soni)}")

    qoida_noyob: collections.Counter = collections.Counter()
    qoida_jami: collections.Counter = collections.Counter()
    ozgargan = []          # (so'z, soni, talaffuz, qoidalar, manba)
    lugat_soni = 0
    qatorlar = []
    for w, c in soni.most_common(args.eng_kop):
        lugat = n.lookup_pronunciation(w)
        if lugat is not None:
            talaffuz, qoidalar, manba = lugat, "", "lug'at"
            lugat_soni += 1
        else:
            iz = n.orthoepy_trace(w)
            talaffuz = iz[-1][1] if iz else w
            qoidalar = ",".join(q for q, _ in iz)
            manba = "qoida" if iz else ""
            for q, _ in iz:
                qoida_noyob[q] += 1
                qoida_jami[q] += c
        qatorlar.append((w, c, talaffuz, qoidalar, manba))
        if manba:
            ozgargan.append(qatorlar[-1])

    with open(args.chiqish, "w", encoding="utf-8", newline="") as f:
        f.write("soz\tsoni\ttalaffuz\tqoidalar\tmanba\n")
        for q in qatorlar:
            f.write("\t".join(str(x) for x in q) + "\n")

    korilgan = len(qatorlar)
    korilgan_jami = sum(c for _, c, *_ in qatorlar)
    ozg_jami = sum(c for _, c, *_ in ozgargan)
    print(f"ro'yxat: {korilgan} so'z -> {args.chiqish}")
    print(f"o'zgargan: {len(ozgargan)} noyob so'z ({100 * len(ozgargan) / max(korilgan, 1):.1f}%), "
          f"matnda {ozg_jami} marta ({100 * ozg_jami / max(korilgan_jami, 1):.1f}%), lug'atdan: {lugat_soni}")
    print("\nqoida            noyob    matnda")
    for q, _ in n.ORTHOEPY_RULES:
        print(f"{q:<16} {qoida_noyob[q]:>6} {qoida_jami[q]:>9}")

    print("\nEng ko'p uchraydigan o'zgargan so'zlar (eshitish sinovi uchun):")
    for w, c, t, q, m in ozgargan[:40]:
        print(f"  {c:>5}  {w:<18} -> {t:<18} [{q or m}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
