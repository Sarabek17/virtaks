# -*- coding: utf-8 -*-
"""Eski tizimdagi shablon fayllarni omborga ko'chirish.

  python -m platforma.migratsiya_shablon --papka kengash/shablonlar

Standart holda UMUMIY shablon sifatida qo'shiladi (twin_id NULL) — barcha
twinlar foydalanadi. `--twin <id>` bilan bitta twinga bog'lash mumkin.
Qayta ishga tushirish xavfsiz: bir xil nomli yozuv o'tkazib yuboriladi.
"""
import argparse
from pathlib import Path

from . import pg, storage
from .sozlama import log


def main():
    p = argparse.ArgumentParser(description="Shablonlarni S3 ga ko'chirish")
    p.add_argument("--papka", required=True, help="shablon fayllar papkasi")
    p.add_argument("--twin", type=int, default=None,
                   help="twin id (berilmasa — umumiy shablon)")
    args = p.parse_args()

    papka = Path(args.papka)
    if not papka.is_dir():
        raise SystemExit(f"papka topilmadi: {papka}")

    storage.baket_tayyorla()
    fayllar = sorted(f for f in papka.glob("*.xls*") if f.is_file())
    log(f"{len(fayllar)} fayl topildi")

    qoshildi = otkazildi = 0
    for f in fayllar:
        bor = pg.bitta(
            "SELECT id FROM shablonlar WHERE nom=%s AND twin_id IS NOT DISTINCT FROM %s",
            f.name, args.twin)
        if bor:
            otkazildi += 1
            continue
        joy = args.twin if args.twin else 0
        s3_yol = f"shablonlar/{joy}/{f.name}"
        storage.yukla_fayl(
            s3_yol, str(f),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        pg.bajar(
            """INSERT INTO shablonlar(nom, s3_yol, tur, twin_id, izoh)
               VALUES(%s,%s,'xlsx',%s,%s)""",
            f.name, s3_yol, args.twin, "eski tizimdan ko'chirildi")
        qoshildi += 1
        log(f"  + {f.name} ({f.stat().st_size / 1024:.0f} KB)")

    log(f"TUGADI: {qoshildi} qo'shildi, {otkazildi} allaqachon bor edi")
    log(f"ombordagi jami shablonlar: "
        f"{pg.bitta('SELECT count(*) FROM shablonlar')[0]}")


if __name__ == "__main__":
    main()
