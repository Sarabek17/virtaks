# -*- coding: utf-8 -*-
"""Lokal papkadagi fayllarni twin bilimiga ommaviy yuklash (konsoldan).

  python -m platforma.manba_yukla --twin 2 --papka "E:\\Zakazlar\\Muslim aka" --quruq
  python -m platforma.manba_yukla --twin 2 --papka "E:\\Zakazlar\\Muslim aka" --render

Bu `kabinet.yukla` endpointining AYNI oqimi, faqat HTTP'siz: fayl S3 ga
oqim bilan yoziladi -> `manbalar` yozuvi -> `ingest_fayl` job navbatga
tushadi. Og'ir ishni worker qiladi, bu skript hech narsa o'qimaydi.

Nega alohida vosita: brauzerdan 40 ta PDF ni birma-bir tashlash uzoq va
uzilib qoladi; bu yerda esa qayta ishga tushirish xavfsiz — allaqachon
yuklangan nom o'tkazib yuboriladi.

DIQQAT — PUL: har PDF sahifasi vision-OCR dan o'tadi (taxminan $0.002).
3595 sahifalik to'plam ≈ $7. Shuning uchun skript avval ro'yxatni
ko'rsatadi va tasdiq so'raydi (`--tasdiq` bilan so'ramaydi).
"""
import argparse
import sys
import time
from pathlib import Path

from . import db, jobs, oquvchi, pg, storage
from .sozlama import log

MAKS_HAJM = 512 * 1024 * 1024      # kabinet.MAKS_HAJM bilan bir xil
INGEST_MUHLAT = 4 * 3600
E_TASHLAB = {".venv", "node_modules", "__pycache__", ".git", ".kesh"}


def _tozalash(nom: str) -> str:
    """Fayl nomini xavfsiz holga keltiradi (kabinet._tozalash bilan bir mantiq)."""
    nom = Path(nom).name.replace("\\", "_").replace("/", "_")
    return nom.strip()[:200] or "fayl"


def _fayllar(papkalar: list[Path]) -> list[tuple[Path, str]]:
    """(yo'l, papka_tegi) ro'yxati. Teg — ildizdan keyingi BIRINCHI papka nomi
    (`manbalar.papka` ustuni shu bilan to'ladi: "Marketing", "SotuvBolimi"...)."""
    topildi: list[tuple[Path, str]] = []
    for ildiz in papkalar:
        if not ildiz.is_dir():
            log(f"papka topilmadi: {ildiz}")
            continue
        for yol in sorted(ildiz.rglob("*")):
            if not yol.is_file() or any(q in E_TASHLAB for q in yol.parts):
                continue
            if yol.name.startswith("~$"):          # Office vaqtinchalik fayli
                continue
            nisbiy = yol.relative_to(ildiz)
            teg = nisbiy.parts[0] if len(nisbiy.parts) > 1 else ildiz.name
            topildi.append((yol, teg[:80]))
    return topildi


def main():
    p = argparse.ArgumentParser(description="Papkadagi fayllarni twin bilimiga yuklash")
    p.add_argument("--twin", type=int, required=True, help="twin id")
    p.add_argument("--papka", action="append", required=True,
                   help="yuklanadigan papka (bir nechta bo'lishi mumkin)")
    p.add_argument("--tur", default="", help="faqat shu tur (audio/slayd/jadval/hujjat)")
    p.add_argument("--chegara", type=int, default=0, help="nechta fayl bilan cheklash")
    p.add_argument("--render", action="store_true",
                   help="PDF/PPTX uchun sahifa suratlari jobini ham navbatga qo'yish")
    p.add_argument("--quruq", action="store_true",
                   help="faqat ko'rsatadi, hech narsa yuklamaydi")
    p.add_argument("--tasdiq", action="store_true", help="savolsiz davom etish")
    args = p.parse_args()

    t = pg.bitta_d("SELECT id, nom FROM twinlar WHERE id=%s", args.twin)
    if not t:
        raise SystemExit(f"twin #{args.twin} topilmadi")

    hammasi = _fayllar([Path(q) for q in args.papka])
    ish: list[tuple[Path, str, str]] = []       # (yo'l, teg, tur)
    otkazildi = {"format": 0, "bor": 0, "katta": 0, "bosh": 0}

    for yol, teg in hammasi:
        nom = _tozalash(yol.name)
        tur = oquvchi.tur_aniqla(nom)
        if not tur or (args.tur and tur != args.tur):
            otkazildi["format"] += 1
            continue
        hajm = yol.stat().st_size
        if not hajm:
            otkazildi["bosh"] += 1
            continue
        if hajm > MAKS_HAJM:
            log(f"  KATTA ({hajm / 1e6:.0f} MB > 512 MB), tashlab ketildi: {nom}")
            otkazildi["katta"] += 1
            continue
        # Qayta ishga tushirish xavfsiz bo'lsin: ayni twinda ayni nomli manba
        # bo'lsa, ikkinchi marta yuklamaymiz (va ikkinchi marta pul sarflamaymiz).
        bor = pg.bitta("SELECT id FROM manbalar WHERE twin_id=%s AND nom=%s",
                       args.twin, nom)
        if bor:
            otkazildi["bor"] += 1
            continue
        ish.append((yol, teg, tur))

    if args.chegara:
        ish = ish[:args.chegara]

    jami_hajm = sum(y.stat().st_size for y, _, _ in ish)
    print(f"\nTwin #{t['id']} «{t['nom']}»")
    print(f"  topildi        : {len(hammasi)} fayl")
    print(f"  yuklanadi      : {len(ish)} fayl, {jami_hajm / 1e6:.0f} MB")
    print(f"  o'tkazildi     : {otkazildi['bor']} allaqachon bor, "
          f"{otkazildi['format']} mos kelmaydigan format, "
          f"{otkazildi['katta']} juda katta, {otkazildi['bosh']} bo'sh")
    turlar: dict[str, int] = {}
    for _, _, tur in ish:
        turlar[tur] = turlar.get(tur, 0) + 1
    print(f"  turlari        : {turlar or '-'}")
    print("  DIQQAT: har sahifa/daqiqa model orqali o'tadi — PDF sahifasi "
          "≈ $0.002, audio daqiqasi ≈ $0.001")

    if not ish:
        print("\nYuklanadigan yangi fayl yo'q.")
        return
    if args.quruq:
        print("\n--quruq: hech narsa yuklanmadi. Ro'yxat:")
        for yol, teg, tur in ish:
            print(f"    [{tur:6}] {teg}/{yol.name}")
        return
    if not args.tasdiq:
        javob = input("\nDavom etilsinmi? (ha / yoq) ").strip().lower()
        if javob != "ha":
            print("bekor qilindi")
            return

    storage.baket_yumshoq()
    qoshildi = xato = 0
    for i, (yol, teg, tur) in enumerate(ish, 1):
        nom = _tozalash(yol.name)
        hajm = yol.stat().st_size
        s3_yol = f"manbalar/{args.twin}/{int(time.time())}_{nom}"
        try:
            with yol.open("rb") as oqim:
                storage.yukla_oqim(s3_yol, oqim, "application/octet-stream")
        except Exception as e:                                   # noqa: BLE001
            log(f"  [{i}/{len(ish)}] S3 XATO {nom}: {str(e)[:120]}")
            xato += 1
            continue
        mid = db.manba_yasa(args.twin, nom, tur, s3_yol=s3_yol, papka=teg,
                            asl_nom=nom, hajm=hajm, mime="")
        jid = jobs.qoshish("ingest_fayl", {"manba_id": mid}, twin_id=args.twin,
                           ustunlik=7, muhlat_s=INGEST_MUHLAT, max_urinish=2)
        qoshildi += 1
        log(f"  [{i}/{len(ish)}] + {teg}/{nom} ({hajm / 1e6:.1f} MB) "
            f"-> manba #{mid}, job #{jid}")
        if args.render and tur in ("slayd", "hujjat"):
            rid = jobs.qoshish("sahifa_render", {"manba_id": mid},
                               twin_id=args.twin, ustunlik=8, muhlat_s=3600)
            log(f"        sahifa_render job #{rid}")

    log(f"TUGADI: {qoshildi} yuklandi, {xato} xato")
    log("Ingest joblari worker'da navbat bilan bajariladi — "
        "kuzatish: kabinet «Jurnal» yoki `bash joylash/holat.sh`")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nto'xtatildi", file=sys.stderr)
