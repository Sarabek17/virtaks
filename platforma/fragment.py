# -*- coding: utf-8 -*-
"""Aynan olingan fragment — javobdagi [n] bosilganda AYNAN o'sha joy qaytariladi.

  audio  — dars yozuvining o'sha oralig'i kesib olinadi (ffmpeg, S3 dan HTTP range
           bilan: 100 MB lik darsni to'liq yuklab olmaymiz)
  rasm   — slayd/sahifa surati (ingest paytida saqlangan, kesish shart emas)

Kesilgan audio `fragmentlar` jadvalida keshlanadi: bir marta kesiladi, keyin
hammaga o'sha fayl beriladi.
"""
import subprocess
import tempfile
from pathlib import Path

from . import db, oquvchi, storage
from .sozlama import log

OLDIN = 2        # oraliqdan bir oz oldin boshlaymiz (gap boshi kesilmasin)
KEYIN = 3        # va bir oz keyin tugatamiz
MAKS_UZUNLIK = 900   # bitta fragment eng ko'pi bilan 15 daqiqa


def audio_yol(bolak_id: int) -> str:
    return f"fragmentlar/{bolak_id}.mp3"


def holat(bolak: dict) -> dict:
    """Bo'lak uchun qanday fragment mavjudligi (UI shu bo'yicha tugma ko'rsatadi)."""
    audio_bor = bolak.get("audio_bosh") is not None and bool(bolak.get("manba_s3"))
    fr = db.fragment_ol(bolak["id"], "audio") if audio_bor else None
    return {
        "audio": audio_bor,
        "audio_holat": (fr or {}).get("holat", "yoq" if not audio_bor else "navbatda"),
        "audio_xato": (fr or {}).get("xato", ""),
        "rasm": bool(bolak.get("sahifa_png")),
        "bosh": bolak.get("audio_bosh"), "oxir": bolak.get("audio_oxir"),
    }


def kes(bolak_id: int, yoz=log) -> dict:
    """Audio oraliqni kesib S3 ga yozadi (keshda bo'lsa qayta kesmaydi)."""
    bolak = db.bolak_ol(bolak_id)
    if not bolak:
        raise RuntimeError(f"bo'lak #{bolak_id} topilmadi")
    if bolak.get("audio_bosh") is None:
        raise RuntimeError("bu bo'lak audio manbadan emas")
    if not bolak.get("manba_s3"):
        raise RuntimeError("asl audio fayl omborda yo'q (eski manba)")

    yol = audio_yol(bolak_id)
    bor = db.fragment_ol(bolak_id, "audio")
    if bor and bor["holat"] == "tayyor" and storage.bormi(yol):
        return {"s3_yol": yol, "keshdan": True}

    bosh = max(0, int(bolak["audio_bosh"]) - OLDIN)
    oxir = int(bolak["audio_oxir"] or (bosh + 60)) + KEYIN
    dav = max(5, min(MAKS_UZUNLIK, oxir - bosh))
    db.fragment_yoz(bolak_id, "audio", "ketmoqda")
    yoz(f"fragment kesilmoqda: bo'lak #{bolak_id}, {bosh}s dan {dav}s")

    try:
        manba = storage.havola(bolak["manba_s3"], 3600)
        with tempfile.TemporaryDirectory(prefix="twin_fr_") as tdir:
            chiqish = Path(tdir) / "fragment.mp3"
            # -ss kirishdan OLDIN: ffmpeg faylni boshidan o'qimaydi, HTTP range bilan
            # to'g'ri joyga sakraydi. Qayta kodlash — kesim aniq joyda bo'lsin.
            r = subprocess.run(
                [oquvchi.ffmpeg_yol(), "-y", "-ss", str(bosh), "-t", str(dav),
                 "-i", manba, "-vn", "-ac", "1", "-ar", "24000",
                 "-c:a", "libmp3lame", "-b:a", "64k", str(chiqish)],
                capture_output=True, text=True, errors="replace", timeout=600)
            if r.returncode != 0 or not chiqish.exists():
                raise RuntimeError(f"ffmpeg: {r.stderr[-300:]}")
            storage.yukla_fayl(yol, str(chiqish), "audio/mpeg")
            olcham = chiqish.stat().st_size
    except Exception as e:
        db.fragment_yoz(bolak_id, "audio", "xato", xato=str(e))
        raise

    db.fragment_yoz(bolak_id, "audio", "tayyor", s3_yol=yol, davomiylik=dav)
    yoz(f"fragment tayyor: {yol} ({olcham / 1e6:.2f} MB, {dav}s)")
    return {"s3_yol": yol, "davomiylik": dav, "hajm": olcham, "keshdan": False}


# ---------------------------------------------------------------- worker handlerlari

def bajar(job: dict, yoz) -> dict:
    """job.kirish: {bolak_id}"""
    return kes(int(job["kirish"]["bolak_id"]), yoz)


def tg_yubor(job: dict, yoz) -> dict:
    """job.kirish: {bolak_id, izoh} — fragmentni foydalanuvchining Telegramiga yuboradi."""
    from . import tg
    bid = int(job["kirish"]["bolak_id"])
    uid = job["user_id"]
    bolak = db.bolak_ol(bid)
    if not bolak:
        raise RuntimeError("bo'lak topilmadi")
    sarlavha = f"{bolak['manba']} — {bolak['joy']}"
    izoh = job["kirish"].get("izoh", "")

    if bolak.get("audio_bosh") is not None and bolak.get("manba_s3"):
        kes(bid, yoz)
        bayt = storage.ol(audio_yol(bid))
        tg.audio_yubor(uid, f"{bolak['id']}_fragment.mp3", bayt, sarlavha, izoh)
        yoz(f"audio fragment TG ga yuborildi ({len(bayt) / 1e6:.2f} MB)")
        return {"tur": "audio", "bolak_id": bid}

    if bolak.get("sahifa_png"):
        bayt = storage.ol(bolak["sahifa_png"])
        tg.rasm_yubor(uid, "sahifa.jpg", bayt, sarlavha, izoh)
        yoz("sahifa surati TG ga yuborildi")
        return {"tur": "rasm", "bolak_id": bid}

    tg.matn_yubor(uid, f"<b>{sarlavha}</b>\n\n{bolak['matn'][:3500]}")
    yoz("manba matni TG ga yuborildi (fayl yo'q)")
    return {"tur": "matn", "bolak_id": bid}
