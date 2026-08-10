# -*- coding: utf-8 -*-
"""Asl fayllarni omborga ko'chirish — eski (migratsiya qilingan) manbalar uchun.

Eski bilim bazasi bo'laklarida vaqt oralig'i bor, lekin ASL audio/PDF fayl
omborda yo'q edi — shuning uchun "aynan olingan fragment" ishlamaydi. Bu skript
lokal papkalardan fayllarni topib omborga yuklaydi va manbaga bog'laydi.

  python -m platforma.migratsiya_asl --papka "C:\\...\\Рабочий стол"
  python -m platforma.migratsiya_asl --papka ... --tur audio --render

--render: PDF/PPTX manbalar uchun sahifa suratlarini tayyorlash jobini navbatga qo'yadi.
Qayta ishga tushirish xavfsiz: allaqachon yuklangan manba o'tkazib yuboriladi.
"""
import argparse
import mimetypes
import time
from pathlib import Path

from . import db, jobs, pg, storage
from .sozlama import log

E_TASHLAB = {".venv", "node_modules", "__pycache__", ".git", ".kesh"}


def _indeks(papkalar: list[Path]) -> dict:
    """Lokal fayllar indeksi: nom(kichik harf) -> [yo'llar]."""
    xarita: dict[str, list[Path]] = {}
    for ildiz in papkalar:
        if not ildiz.exists():
            log(f"papka topilmadi: {ildiz}")
            continue
        for yol in ildiz.rglob("*"):
            if not yol.is_file() or any(q in E_TASHLAB for q in yol.parts):
                continue
            xarita.setdefault(yol.name.lower(), []).append(yol)
    log(f"indeks: {sum(len(v) for v in xarita.values())} fayl, "
        f"{len(xarita)} noyob nom")
    return xarita


def _topilsin(manba: dict, xarita: dict) -> tuple[Path | None, str]:
    """(yo'l, izoh). Bir nechta bir xil nomli fayl bo'lsa — papka nomi hal qiladi;
    aniqlanmasa TAXMIN QILMAYMIZ (noto'g'ri fayl bilan bog'lanib qolmasin)."""
    nomzodlar = xarita.get((manba["nom"] or "").lower(), [])
    if not nomzodlar:
        return None, "topilmadi"
    if len(nomzodlar) == 1:
        return nomzodlar[0], ""
    papka = (manba["papka"] or "").lower()
    mos = [y for y in nomzodlar if y.parent.name.lower() == papka]
    if len(mos) == 1:
        return mos[0], ""
    if mos:
        return mos[0], f"{len(mos)} nomzod, birinchisi olindi"
    return None, f"noaniq: {len(nomzodlar)} xil joyda bir xil nom, papka mos kelmadi"


def main():
    p = argparse.ArgumentParser(description="Asl fayllarni S3 ga ko'chirish")
    p.add_argument("--papka", action="append", required=True,
                   help="qidiriladigan papka (bir nechta bo'lishi mumkin)")
    p.add_argument("--tur", default="", help="faqat shu tur (audio/slayd/jadval/hujjat)")
    p.add_argument("--render", action="store_true",
                   help="PDF/PPTX uchun sahifa render jobini navbatga qo'yish")
    p.add_argument("--chegara", type=int, default=0, help="nechta fayl bilan cheklash")
    args = p.parse_args()

    storage.baket_tayyorla()
    xarita = _indeks([Path(q) for q in args.papka])

    shart = "WHERE m.s3_yol = ''"
    qiymatlar = []
    if args.tur:
        shart += " AND m.tur = %s"
        qiymatlar.append(args.tur)
    manbalar = pg.hammasi_d(
        f"""SELECT m.*, t.nom AS twin_nom FROM manbalar m
            JOIN twinlar t ON t.id = m.twin_id {shart} ORDER BY m.id""", *qiymatlar)
    log(f"{len(manbalar)} ta manba asl faylsiz")

    yuklandi = topilmadi = 0
    jami_bayt = 0
    bosh = time.time()
    for i, m in enumerate(manbalar, 1):
        if args.chegara and yuklandi >= args.chegara:
            log(f"chegara ({args.chegara}) — to'xtatildi")
            break
        yol, izoh = _topilsin(m, xarita)
        if not yol:
            log(f"  [{i}/{len(manbalar)}] O'TKAZILDI ({izoh}): {m['twin_nom']} / "
                f"{m['papka']} / {m['nom']}")
            topilmadi += 1
            continue
        if izoh:
            log(f"       diqqat: {izoh} -> {yol}")

        hajm = yol.stat().st_size
        s3_yol = f"manbalar/{m['twin_id']}/{m['id']}_{yol.name}"
        mime = mimetypes.guess_type(yol.name)[0] or "application/octet-stream"
        t0 = time.time()
        storage.yukla_fayl(s3_yol, str(yol), mime)
        pg.bajar("""UPDATE manbalar SET s3_yol=%s, asl_nom=%s, hajm=%s, mime=%s
                    WHERE id=%s""", s3_yol, yol.name, hajm, mime, m["id"])
        yuklandi += 1
        jami_bayt += hajm
        tez = hajm / max(0.1, time.time() - t0) / 1e6
        log(f"  [{i}/{len(manbalar)}] {yol.name} — {hajm / 1e6:.1f} MB "
            f"({tez:.1f} MB/s) -> {s3_yol}")

        if args.render and yol.suffix.lower() in {".pdf", ".pptx", ".ppt"}:
            jid = jobs.qoshish("sahifa_render", {"manba_id": m["id"]},
                               twin_id=m["twin_id"], ustunlik=8, muhlat_s=1800)
            log(f"       sahifa_render job #{jid}")

    log(f"TUGADI: {yuklandi} yuklandi ({jami_bayt / 1e9:.2f} GB, "
        f"{time.time() - bosh:.0f}s), {topilmadi} topilmadi")
    qolgan = pg.bitta("SELECT count(*) FROM manbalar WHERE s3_yol = ''")[0]
    log(f"asl faylsiz qolgan manbalar: {qolgan}")


if __name__ == "__main__":
    main()
