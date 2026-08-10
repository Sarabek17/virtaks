# -*- coding: utf-8 -*-
"""Ingest — istalgan manba faylni kanonik qatlamga aylantiradi.

Foydalanish:
  python -m kengash.ingest "papka yoki fayl" --ustoz "Abdulloh" [--qayta]

--ustoz MAJBURIY: bilim qaysi ustozning darslaridan ekanini belgilaydi
(ruxsat etilgan nomlar sozlama.USTOZLAR da).

Har manba uchun kanonik/ ichida:
  <slug>.md     — odam o'qiydigan to'liq matn
  <slug>.jsonl  — RAG bo'laklari (id, manba, tur, joy, matn, teglar, ustoz)
"""
import argparse
import json
import re
import sys
from pathlib import Path

from google.genai import types

from . import oquvchi_audio, oquvchi_jadval, oquvchi_matn, oquvchi_pdf
from .sozlama import (AGENT_MODELLAR, KANONIK, TEGLAR, USTOZLAR, klient, log,
                      qayta_urinib, slug)

AUDIO_TURLAR = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac",
                ".mp4", ".mkv", ".avi", ".mov", ".webm"}
MAKS_BOLAK = 1200   # belgi — audio/matn bo'laklari uchun


# ---------- bo'laklash ----------

VAQT = re.compile(r"\[(\d+:\d{2}:\d{2})\]")


def _audio_bolaklar(matn: str) -> list[dict]:
    """Vaqt belgili transkriptni ~MAKS_BOLAK belgili bo'laklarga yig'adi.

    joy = bo'lakning vaqt ORALIG'I: [boshi–oxiri] (birinchi va oxirgi abzats vaqtidan).
    """
    abzatslar = [a.strip() for a in matn.split("\n") if a.strip()]
    bolaklar, joriy = [], []

    def qoshish(qatorlar):
        vaqtlar = [m.group(1) for m in (VAQT.match(q) for q in qatorlar) if m]
        if not vaqtlar:
            joy = "[0:00:00]"
        elif vaqtlar[0] == vaqtlar[-1]:
            joy = f"[{vaqtlar[0]}]"
        else:
            joy = f"[{vaqtlar[0]}–{vaqtlar[-1]}]"
        bolaklar.append({"joy": joy, "matn": "\n".join(qatorlar)})

    for a in abzatslar:
        joriy.append(a)
        if sum(len(x) for x in joriy) >= MAKS_BOLAK:
            qoshish(joriy)
            joriy = [joriy[-1]]   # 1 abzats ustma-ust (kontekst uzilmasin)
    if len(joriy) > 1 or (joriy and not bolaklar):
        qoshish(joriy)
    return bolaklar


def _matn_bolaklar(matn: str) -> list[dict]:
    abzatslar = [a.strip() for a in matn.split("\n\n") if a.strip()]
    bolaklar, joriy = [], []
    for a in abzatslar:
        joriy.append(a)
        if sum(len(x) for x in joriy) >= MAKS_BOLAK:
            bolaklar.append({"joy": f"{len(bolaklar) + 1}-qism", "matn": "\n\n".join(joriy)})
            joriy = []
    if joriy:
        bolaklar.append({"joy": f"{len(bolaklar) + 1}-qism", "matn": "\n\n".join(joriy)})
    return bolaklar


# ---------- teglash ----------

TEG_PROMPT = """Quyida bilim bazasi bo'laklari berilgan. Har biriga mos teglarni tanla.

Teglar: {teglar}

Qoidalar:
- Har bo'lakka 1-3 ta teg. Aniq soha bilinmasa "umumiy" qo'y.
- moliya: pul, narx, byudjet, kirim-chiqim, ROI. sotuv: sotuv texnikasi, mijoz, kanal.
- marketing: reklama, brend, auditoriya. strategiya: maqsad, vizyon, biznes model.
- operatsiya: jarayon, jamoa boshqaruvi. texnologiya: IT, dastur, avtomatlashtirish.
- huquq: shartnoma, qonun. hr: xodim yollash, motivatsiya.

Javob: faqat JSON massiv, har element — teglar massivi. Masalan: [["sotuv","marketing"],["umumiy"]]

BO'LAKLAR:
{bolaklar}"""


def _teglash(bolaklar: list[dict]) -> None:
    """Har bo'lakka LLM orqali soha teglarini qo'yadi (25 talik guruhlarda)."""
    cl = klient()
    for i in range(0, len(bolaklar), 25):
        guruh = bolaklar[i:i + 25]
        royxat = "\n".join(f"{n + 1}. {b['matn'][:400]}" for n, b in enumerate(guruh))
        prompt = TEG_PROMPT.format(teglar=", ".join(TEGLAR), bolaklar=royxat)

        def sorov():
            for model in AGENT_MODELLAR:
                try:
                    j = cl.models.generate_content(
                        model=model, contents=[prompt],
                        config=types.GenerateContentConfig(
                            temperature=0.0, max_output_tokens=4096,
                            response_mime_type="application/json",
                            thinking_config=types.ThinkingConfig(thinking_budget=0)))
                    return json.loads(j.text)
                except Exception as e:
                    oxirgi = e
            raise oxirgi

        try:
            teg_royxat = qayta_urinib(sorov, f"teglash {i}-{i + len(guruh)}")
        except Exception:
            teg_royxat = [["umumiy"]] * len(guruh)
        for b, teglar in zip(guruh, teg_royxat if isinstance(teg_royxat, list) else []):
            toza = [t for t in teglar if t in TEGLAR] if isinstance(teglar, list) else []
            b["teglar"] = toza or ["umumiy"]
        for b in guruh:
            b.setdefault("teglar", ["umumiy"])
        log(f"  teglash: {min(i + 25, len(bolaklar))}/{len(bolaklar)}")


# ---------- asosiy ----------

def fayl_ingest(fayl: Path, qayta: bool = False, ustoz: str = "") -> Path | None:
    # ustoz majburiy va ro'yxatdan bo'lishi shart — xato yozuv keyin
    # qidiruv filtridan butunlay chiqib qoladi
    if ustoz not in USTOZLAR:
        raise ValueError(f"ustoz noto'g'ri: {ustoz!r} — ruxsat: {', '.join(USTOZLAR)}")
    s = slug(f"{fayl.stem}_{fayl.suffix.lstrip('.')}")   # 1.pdf va 1.xlsx to'qnashmasin
    jsonl_yol = KANONIK / f"{s}.jsonl"
    if jsonl_yol.exists() and not qayta:
        log(f"O'TKAZILDI (allaqachon bor): {fayl.name} — qayta o'qish uchun --qayta")
        return jsonl_yol

    suffix = fayl.suffix.lower()
    dars = fayl.parent.name
    log(f"=== INGEST: {fayl.name} (tur: {suffix}) ===")

    if suffix in AUDIO_TURLAR:
        n = oquvchi_audio.oqi(fayl)
        bolaklar = _audio_bolaklar(n["matn"])
        tur, toliq = "audio", n["matn"]
    elif suffix == ".pdf":
        n = oquvchi_pdf.oqi(fayl)
        bolaklar = [{"joy": f"{i + 1}-slayd", "matn": s_}
                    for i, s_ in enumerate(n["sahifalar"]) if s_.strip()]
        tur, toliq = "slayd", "\n\n---\n\n".join(n["sahifalar"])
    elif suffix in {".xlsx", ".xlsm"}:
        n = oquvchi_jadval.oqi(fayl)
        bolaklar = [{"joy": f"varaq: {v['nom']}", "matn": v["markdown"]} for v in n["varaqlar"]]
        tur, toliq = "jadval", "\n\n".join(v["markdown"] for v in n["varaqlar"])
    elif suffix in {".docx", ".txt", ".md"}:
        n = oquvchi_matn.oqi(fayl)
        bolaklar = _matn_bolaklar(n["matn"])
        tur, toliq = "hujjat", n["matn"]
    else:
        log(f"O'TKAZILDI (nomalum tur): {fayl.name}")
        return None

    log(f"{len(bolaklar)} bo'lak, teglash boshlanadi...")
    _teglash(bolaklar)

    KANONIK.mkdir(parents=True, exist_ok=True)
    (KANONIK / f"{s}.md").write_text(
        f"# MANBA: {fayl.name}\n# TUR: {tur} | PAPKA: {dars} | USTOZ: {ustoz}\n\n{toliq}",
        encoding="utf-8")
    with open(jsonl_yol, "w", encoding="utf-8") as f:
        for i, b in enumerate(bolaklar):
            f.write(json.dumps({
                "id": f"{s}_{i:04d}", "manba": fayl.name, "tur": tur,
                "dars": dars, "joy": b["joy"], "matn": b["matn"],
                "teglar": b["teglar"], "ustoz": ustoz,
            }, ensure_ascii=False) + "\n")
    log(f"TAYYOR: {fayl.name} -> {len(bolaklar)} bo'lak ({jsonl_yol.name})")
    return jsonl_yol


def main():
    p = argparse.ArgumentParser(description="Manbalarni kanonik qatlamga o'qish")
    p.add_argument("yol", help="fayl yoki papka")
    p.add_argument("--ustoz", required=True,
                   help="bilim kimning darslaridan: " + ", ".join(USTOZLAR))
    p.add_argument("--qayta", action="store_true", help="mavjud bo'lsa ham qayta o'qish")
    args = p.parse_args()

    yol = Path(args.yol)
    fayllar = sorted(yol.iterdir()) if yol.is_dir() else [yol]
    for f in fayllar:
        if f.is_file():
            try:
                fayl_ingest(f, qayta=args.qayta, ustoz=args.ustoz.strip())
            except Exception as e:
                log(f"XATO ({f.name}): {e}")
                import traceback; traceback.print_exc()


if __name__ == "__main__":
    main()
