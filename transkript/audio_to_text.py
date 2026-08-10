# -*- coding: utf-8 -*-
"""
Audio YOKI video faylni 10 daqiqalik bo'laklarga bo'lib, Gemini orqali o'zbekcha matnga aylantiradi.
Video berilsa, avval ichidan audio ajratib olinadi (kadrlar ishlatilmaydi — arzon va tez).
Sheva va og'zaki nutq aynan aytilganidek yoziladi (adabiy tilga normallashtirilmaydi).

Ishlatish:
    python transkript\\audio_to_text.py "C:\\yo'l\\audio.mp3"  [--bolak 10]
    python transkript\\audio_to_text.py "C:\\yo'l\\video.mp4"  [--bolak 10]
    (mp3, wav, m4a, ogg, mp4, mkv, avi, mov, webm va boshqalar)

Natija:
    transkript\\chiqish\\<fayl_nomi>\\qism_NN.txt   — har bir bo'lak matni
    transkript\\chiqish\\<fayl_nomi>\\toliq_matn.txt — birlashtirilgan to'liq matn
"""
import argparse
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import imageio_ffmpeg
from dotenv import load_dotenv
from google import genai
from google.genai import types

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

LOYIHA = Path(__file__).resolve().parent.parent
load_dotenv(LOYIHA / ".env")

MODELLAR = ["gemini-3.5-flash", "gemini-2.5-flash"]  # birinchisi ishlamasa keyingisi
PARALLEL = 3          # bir vaqtda nechta bo'lak yuboriladi
URINISH = 3           # har bir bo'lak uchun qayta urinishlar soni

PROMPT = """Bu — o'zbek tilidagi audio yozuv (dars/ma'ruza bo'lishi mumkin). Vazifang: uni so'zma-so'z, TO'LIQ transkripsiya qilish.

QOIDALAR:
1. Faqat o'zbek lotin alifbosida yoz (oʻ va gʻ uchun to'g'ri apostrof ishlat: o', g').
2. Sheva va og'zaki nutqni AYNAN aytilganidek yoz — adabiy tilga o'girma, so'zlarni "to'g'irlama".
3. Arabcha oyat, duo yoki iboralar bo'lsa, eshitilganicha lotin harflarida transliteratsiya qil.
4. Hech narsani tarjima qilma, qisqartirma, umumlashtirma, izoh qo'shma.
5. Gaplarni to'g'ri tinish belgilari bilan yoz, har 30-60 soniyalik nutqni alohida xatboshi qil.
6. Aniq eshitilmagan joyni [tushunarsiz] deb belgila — taxmin qilib to'ldirma.
7. Javobingda FAQAT transkripsiya matni bo'lsin — kirish so'z, sarlavha, izoh yozma."""

_lock = threading.Lock()


def log(msg: str) -> None:
    with _lock:
        print(msg, flush=True)


def davomiylik(ffmpeg: str, fayl: Path) -> float:
    """Audio davomiyligini soniyalarda qaytaradi (ffmpeg stderr'idan o'qiladi)."""
    p = subprocess.run([ffmpeg, "-i", str(fayl)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", p.stderr)
    if not m:
        raise RuntimeError("Davomiylikni aniqlab bo'lmadi — fayl buzuq bo'lishi mumkin")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def vaqt(s: float) -> str:
    s = int(s)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def bolaklash(ffmpeg: str, fayl: Path, papka: Path, bolak_soniya: int) -> list[Path]:
    """Faylni mp3 bo'laklarga bo'ladi.

    mp3 kirsa — qayta kodlashsiz (tez, sifat yo'qolmaydi).
    Video yoki boshqa audio format kirsa — audio yo'lakcha ajratib olinib,
    16kHz mono 64k mp3 ga siqiladi (STT uchun yetarli, yuklash hajmi kichik).
    """
    papka.mkdir(parents=True, exist_ok=True)
    shablon = papka / "bolak_%03d.mp3"
    if fayl.suffix.lower() == ".mp3":
        kodlash = ["-c", "copy"]
    else:
        kodlash = ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "64k"]
    subprocess.run(
        [ffmpeg, "-y", "-i", str(fayl), *kodlash,
         "-f", "segment", "-segment_time", str(bolak_soniya), str(shablon)],
        capture_output=True, check=True)
    bolaklar = sorted(papka.glob("bolak_*.mp3"))
    if not bolaklar:
        raise RuntimeError("Bo'laklash muvaffaqiyatsiz — faylda audio yo'lakcha bormi?")
    return bolaklar


def transkript(client: genai.Client, model: str, bolak: Path, idx: int, jami: int) -> str:
    """Bitta bo'lakni yuklab, matnga aylantiradi. Xatoda qayta urinadi."""
    oxirgi_xato: Exception | None = None
    for urinish in range(1, URINISH + 1):
        yuklangan = None
        try:
            log(f"  [{idx + 1}/{jami}] yuklanmoqda... ({bolak.stat().st_size / 1e6:.1f} MB)")
            yuklangan = client.files.upload(file=str(bolak))
            while yuklangan.state and yuklangan.state.name == "PROCESSING":
                time.sleep(2)
                yuklangan = client.files.get(name=yuklangan.name)
            log(f"  [{idx + 1}/{jami}] transkripsiya ({model})...")
            javob = client.models.generate_content(
                model=model,
                contents=[yuklangan, PROMPT],
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    # Uzun bo'lakda matn kesilib qolmasligi uchun maksimal chiqish;
                    # "o'ylash" transkripsiyaga kerak emas — tokenni matnga qoldiramiz.
                    max_output_tokens=65535,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            matn = (javob.text or "").strip()
            tugash = javob.candidates[0].finish_reason if javob.candidates else None
            if tugash and str(tugash).endswith("MAX_TOKENS"):
                log(f"  [{idx + 1}/{jami}] DIQQAT: matn limitga yetdi — oxiri kesilgan bo'lishi mumkin")
            if len(matn) < 20:
                raise RuntimeError(f"Javob bo'sh yoki juda qisqa: {matn!r}")
            log(f"  [{idx + 1}/{jami}] tayyor ✓ ({len(matn)} belgi)")
            return matn
        except Exception as e:  # noqa: BLE001 — har qanday xatoda qayta urinamiz
            oxirgi_xato = e
            kutish = 20 * urinish if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) else 5 * urinish
            log(f"  [{idx + 1}/{jami}] xato ({urinish}-urinish): {e} — {kutish}s kutamiz")
            time.sleep(kutish)
        finally:
            if yuklangan is not None:
                try:
                    client.files.delete(name=yuklangan.name)
                except Exception:
                    pass
    return f"[XATO: bu bo'lakni qayta ishlab bo'lmadi — {oxirgi_xato}]"


def main() -> None:
    p = argparse.ArgumentParser(description="Audio → o'zbekcha matn (Gemini)")
    p.add_argument("audio", help="Audio fayl yo'li (mp3/wav/m4a/ogg...)")
    p.add_argument("--bolak", type=int, default=10, help="Bo'lak uzunligi daqiqada (standart: 10)")
    args = p.parse_args()

    fayl = Path(args.audio)
    if not fayl.exists():
        sys.exit(f"Fayl topilmadi: {fayl}")

    kalit = os.environ.get("GEMINI_API_KEY")
    if not kalit:
        sys.exit("GEMINI_API_KEY topilmadi (.env faylini tekshiring)")

    nom = re.sub(r"[^\w\-]+", "_", fayl.stem, flags=re.UNICODE).strip("_")
    chiqish = LOYIHA / "transkript" / "chiqish" / nom
    chiqish.mkdir(parents=True, exist_ok=True)

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    jami_s = davomiylik(ffmpeg, fayl)
    log(f"Audio: {fayl.name}")
    log(f"Davomiylik: {vaqt(jami_s)}  |  Bo'lak: {args.bolak} daqiqa")

    bolaklar = bolaklash(ffmpeg, fayl, chiqish / "bolaklar", args.bolak * 60)
    log(f"{len(bolaklar)} ta bo'lakka bo'lindi.\n")

    client = genai.Client(api_key=kalit)

    # Model tanlash: ro'yxatdagi birinchi ishlaydigan model
    model = MODELLAR[0]
    for nomzod in MODELLAR:
        try:
            client.models.generate_content(model=nomzod, contents="salom")
            model = nomzod
            break
        except Exception as e:
            log(f"Model {nomzod} ishlamadi ({e}), keyingisini sinaymiz...")
    log(f"Model: {model}\n")

    natijalar: list[str] = [""] * len(bolaklar)
    with ThreadPoolExecutor(max_workers=PARALLEL) as ex:
        futures = {ex.submit(transkript, client, model, b, i, len(bolaklar)): i
                   for i, b in enumerate(bolaklar)}
        for f, i in futures.items():
            natijalar[i] = f.result()

    qismlar = []
    for i, matn in enumerate(natijalar):
        bosh, oxir = i * args.bolak * 60, min((i + 1) * args.bolak * 60, jami_s)
        sarlavha = f"===== {i + 1}-qism  [{vaqt(bosh)} – {vaqt(oxir)}] ====="
        (chiqish / f"qism_{i + 1:02d}.txt").write_text(matn, encoding="utf-8")
        qismlar.append(f"{sarlavha}\n\n{matn}")

    toliq = chiqish / "toliq_matn.txt"
    toliq.write_text(
        f"MANBA: {fayl.name}\nDAVOMIYLIK: {vaqt(jami_s)}\nMODEL: {model}\n"
        f"{'=' * 60}\n\n" + "\n\n\n".join(qismlar) + "\n",
        encoding="utf-8")

    xatolar = sum(1 for m in natijalar if m.startswith("[XATO"))
    log(f"\n{'=' * 60}")
    log(f"TAYYOR: {len(bolaklar) - xatolar}/{len(bolaklar)} qism muvaffaqiyatli")
    log(f"To'liq matn: {toliq}")
    if xatolar:
        log(f"DIQQAT: {xatolar} ta qism xato bilan tugadi (matn ichida [XATO] belgisi bor)")


if __name__ == "__main__":
    main()
