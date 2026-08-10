# -*- coding: utf-8 -*-
"""Bazaning zaxira nusxasi — `pg_dump` -> MinIO (haftalik worker job).

Format `-Fc` (custom, siqilgan) — `pg_restore` bilan tiklanadi:
    pg_restore -d "$PG_URL" --clean --if-exists zaxira.dump

Eski nusxalar SAQLASH_SONI dan oshsa o'chiriladi.
Parol jurnalga chiqmaydi: `pg_dump` ulanish satrini env orqali oladi.
"""
import os
import subprocess
import tempfile
import time
from pathlib import Path

from . import storage
from .sozlama import PG_URL, log

PREFIKS = "zaxira/"
SAQLASH_SONI = 8            # oxirgi 8 ta nusxa (≈2 oy haftalik)
MUHLAT_S = 1800


def _pg_dump_yoli() -> str:
    """pg_dump yo'li.

    pg_dump SERVERDAN ESKI bo'lsa ishlashdan bosh tortadi ("server version
    mismatch"), shuning uchun avval versiyalangan nusxalar (eng yangisidan)
    qidiriladi — PGDG paketlari ularni /usr/lib/postgresql/NN/bin/ ga qo'yadi.
    """
    from shutil import which
    for nom in ("pg_dump18", "pg_dump-18"):
        yol = which(nom)
        if yol:
            return yol
    for kat in sorted(Path("/usr/lib/postgresql").glob("*/bin/pg_dump"),
                      key=lambda p: int(p.parent.parent.name)
                      if p.parent.parent.name.isdigit() else 0, reverse=True):
        return str(kat)
    yol = which("pg_dump")
    if not yol:
        raise RuntimeError(
            "pg_dump topilmadi — worker imijiga postgresql-client-18 kerak")
    return yol


def _eskilarni_ochir(yoz) -> int:
    """Eng eski nusxalarni o'chiradi (SAQLASH_SONI tadan ortig'i)."""
    fayllar = sorted(storage.royxat(PREFIKS))
    ortiqcha = fayllar[:-SAQLASH_SONI] if len(fayllar) > SAQLASH_SONI else []
    for f in ortiqcha:
        storage.ochir(f)
        yoz(f"eski nusxa o'chirildi: {f}")
    return len(ortiqcha)


def bajar(job: dict, yoz) -> dict:
    """Zaxira job: pg_dump -> S3. Xato bo'lsa job yiqiladi (monitoringga tushadi)."""
    if not PG_URL:
        raise RuntimeError("PG_URL yo'q")
    dump = _pg_dump_yoli()
    nom = f"{time.strftime('%Y%m%d_%H%M%S')}.dump"
    yol = PREFIKS + nom
    bosh = time.time()

    with tempfile.TemporaryDirectory() as vaqt:
        chiqish = Path(vaqt) / nom
        yoz("pg_dump boshlandi...")
        muhit = {**os.environ, "PGCONNECT_TIMEOUT": "30"}
        r = subprocess.run(
            [dump, "--dbname", PG_URL, "-Fc", "--no-owner", "--no-privileges",
             "-f", str(chiqish)],
            capture_output=True, text=True, errors="replace", env=muhit,
            timeout=MUHLAT_S)
        if r.returncode != 0:
            # PG_URL ichida parol bor — xato matnini tozalab yozamiz
            xato = (r.stderr or "")[-500:].replace(PG_URL, "<PG_URL>")
            raise RuntimeError(f"pg_dump xatosi ({r.returncode}): {xato}")
        hajm = chiqish.stat().st_size
        if hajm < 1024:
            raise RuntimeError(f"zaxira juda kichik ({hajm} bayt) — shubhali")
        yoz(f"dump tayyor: {hajm / 1e6:.1f} MB, yuklanmoqda...")
        storage.yukla_fayl(yol, str(chiqish), "application/octet-stream")

    ochirilgan = _eskilarni_ochir(yoz)
    davom = round(time.time() - bosh)
    yoz(f"TAYYOR ({davom}s): {yol} — {hajm / 1e6:.1f} MB, "
        f"{ochirilgan} eski nusxa o'chirildi")
    return {"yol": yol, "hajm": hajm, "davomiylik": davom,
            "ochirilgan": ochirilgan}


def royxat() -> list[dict]:
    """Admin panel uchun: mavjud zaxiralar."""
    return [{"yol": y, "nom": y.split("/")[-1]} for y in
            sorted(storage.royxat(PREFIKS), reverse=True)]


if __name__ == "__main__":
    print(bajar({"id": 0}, log))
