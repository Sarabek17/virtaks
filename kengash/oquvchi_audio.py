# -*- coding: utf-8 -*-
"""Audio/video -> vaqt belgili matn (STT). 10 daqiqalik bo'laklar, parallel."""
import re
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from google.genai import types

from .sozlama import KANONIK, STT_MODELLAR, PARALLEL, klient, log, qayta_urinib, slug

BOLAK_DAQIQA = 10

PROMPT = """Sen professional o'zbek tili transkripsiya mutaxassisisan. Ushbu audiodagi BARCHA gaplarni so'zma-so'z yozib chiq.

QOIDALAR:
1. O'zbek lotin alifbosida yoz.
2. So'zlovchi qanday gapirsa, SHUNDAY yoz — adabiy tilga "tuzatma". Sheva so'zlarini (qanaqa, shetta, bo'ganda, qiganda...) aslidek qoldir.
3. Ruscha so'zlarni aslidek qoldir (lyuboy, srazu, chto-to, uje...).
4. Arabcha oyat/duo bo'lsa, lotin transliteratsiyada yoz.
5. Tushunarsiz joyni [tushunarsiz] deb belgila.
6. Tinish belgilarini to'g'ri qo'y, har gapni bosh harf bilan boshla.
7. VAQT BELGISI: har abzats boshiga audiodagi vaqtni [MM:SS] ko'rinishida yoz (masalan [03:45]). Har 2-4 gapda yangi abzats boshla. Vaqtni shu audio bo'lagining boshidan hisobla ([00:00] dan boshlanadi).
8. FAQAT transkript matnini chiqar — hech qanday izoh, sarlavha, xulosa yozma."""


def _ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def davomiylik(fayl: Path) -> float:
    """Sekundlarda davomiylik (ffmpeg Duration qatoridan)."""
    r = subprocess.run([_ffmpeg(), "-i", str(fayl)], capture_output=True, text=True, errors="replace")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
    if not m:
        raise RuntimeError(f"Davomiylik aniqlanmadi: {fayl}")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def bolaklash(fayl: Path, papka: Path, bolak_daqiqa: int = BOLAK_DAQIQA) -> list[Path]:
    """Audio/videoni N daqiqalik mp3 bo'laklarga bo'ladi (video bo'lsa audio ajratiladi)."""
    papka.mkdir(parents=True, exist_ok=True)
    if fayl.suffix.lower() == ".mp3":
        kodlash = ["-c", "copy"]
    else:
        kodlash = ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "64k"]
    shablon = str(papka / "b_%03d.mp3")
    cmd = [_ffmpeg(), "-y", "-i", str(fayl), *kodlash,
           "-f", "segment", "-segment_time", str(bolak_daqiqa * 60), shablon]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg xatosi: {r.stderr[-400:]}")
    return sorted(papka.glob("b_*.mp3"))


def _vaqt_qoshish(matn: str, ofset_s: int) -> str:
    """Bo'lak ichidagi [MM:SS] belgilarga bo'lak boshlanish vaqtini qo'shib [H:MM:SS] qiladi."""
    def alm(m):
        s = int(m.group(1)) * 60 + int(m.group(2)) + ofset_s
        return f"[{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}]"
    return re.sub(r"\[(\d{1,2}):(\d{2})\]", alm, matn)


def _model_sozlama(model: str) -> "types.GenerateContentConfig":
    # 2.5-pro thinking'ni to'liq o'chirishga ruxsat bermaydi — minimal 128
    budjet = 128 if "pro" in model else 0
    return types.GenerateContentConfig(
        temperature=0.2,
        max_output_tokens=65535,
        thinking_config=types.ThinkingConfig(thinking_budget=budjet),
    )


def _bolak_transkript(cl, modellar: list[str], bolak: Path, idx: int, jami: int,
                      kesh: Path) -> str:
    # checkpoint: oldin transkript qilingan bo'lak qayta ishlanmaydi
    kesh_yol = kesh / f"b_{idx:03d}.txt"
    if kesh_yol.exists():
        log(f"  [{idx + 1}/{jami}] keshdan olindi ✓")
        return kesh_yol.read_text(encoding="utf-8")

    log(f"  [{idx + 1}/{jami}] yuklanmoqda... ({bolak.stat().st_size / 1e6:.1f} MB)")
    up = qayta_urinib(lambda: cl.files.upload(file=str(bolak)), f"yuklash {idx + 1}")
    while up.state and up.state.name == "PROCESSING":
        time.sleep(2)
        up = cl.files.get(name=up.name)

    # model zanjiri: birinchisi (retry bilan) yiqilsa — keyingisiga o'tamiz
    javob, oxirgi = None, None
    for model in modellar:
        log(f"  [{idx + 1}/{jami}] transkripsiya ({model})...")

        def sorov():
            return cl.models.generate_content(
                model=model, contents=[up, PROMPT], config=_model_sozlama(model))

        try:
            javob = qayta_urinib(sorov, f"transkript {idx + 1} ({model})")
            break
        except Exception as e:
            oxirgi = e
            log(f"  [{idx + 1}/{jami}] {model} yiqildi — keyingi model...")
    if javob is None:
        raise oxirgi
    try:
        cl.files.delete(name=up.name)
    except Exception:
        pass
    tugash = javob.candidates[0].finish_reason if javob.candidates else None
    if tugash and str(tugash).endswith("MAX_TOKENS"):
        log(f"  [{idx + 1}/{jami}] DIQQAT: matn limitga yetdi — oxiri kesilgan bo'lishi mumkin")
    matn = _vaqt_qoshish((javob.text or "").strip(), idx * BOLAK_DAQIQA * 60)
    kesh_yol.write_text(matn, encoding="utf-8")   # checkpoint
    log(f"  [{idx + 1}/{jami}] tayyor ✓ ({len(matn)} belgi)")
    return matn


def _ishlaydigan_model(cl) -> list[str]:
    """Zanjirni birinchi javob beradigan modeldan boshlab qaytaradi (1s tekshiruv so'rovi)."""
    for i, model in enumerate(STT_MODELLAR):
        try:
            cl.models.generate_content(model=model, contents=["salom"],
                                       config=types.GenerateContentConfig(max_output_tokens=5))
            return STT_MODELLAR[i:]
        except Exception as e:
            log(f"Model {model} ishlamadi ({str(e)[:100]}), keyingisini sinaymiz...")
    raise SystemExit("XATO: birorta STT model ishlamadi")


def oqi(fayl: Path) -> dict:
    """Audio/video faylni to'liq o'qiydi -> {"matn": vaqt belgili transkript, "davomiylik_s": ...}"""
    dav = davomiylik(fayl)
    log(f"Audio: {fayl.name} | davomiylik {int(dav // 3600)}:{int(dav % 3600 // 60):02d}:{int(dav % 60):02d}")
    cl = klient()
    modellar = _ishlaydigan_model(cl)
    log(f"Model zanjiri: {' -> '.join(modellar)}")

    kesh = KANONIK / ".kesh" / slug(f"{fayl.stem}_{fayl.suffix.lstrip('.')}")
    kesh.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="kengash_stt_") as tdir:
        bolaklar = bolaklash(fayl, Path(tdir))
        log(f"{len(bolaklar)} ta bo'lak, parallel {PARALLEL}")
        natijalar: dict[int, str] = {}
        with ThreadPoolExecutor(max_workers=PARALLEL) as ex:
            fut = {ex.submit(_bolak_transkript, cl, modellar, b, i, len(bolaklar), kesh): i
                   for i, b in enumerate(bolaklar)}
            for f in as_completed(fut):
                natijalar[fut[f]] = f.result()

    matn = "\n\n".join(natijalar[i] for i in sorted(natijalar))
    return {"matn": matn, "davomiylik_s": int(dav), "model": modellar[0]}
