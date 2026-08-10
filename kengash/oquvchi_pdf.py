# -*- coding: utf-8 -*-
"""PDF (slayd/skan) -> Markdown. Har sahifa rasmga aylantirilib Gemini vision bilan o'qiladi.

Nega vision? Bu PDF'lar rasm-slaydlar: matn qatlami singan (harflar tushib qolgan).
Oddiy parser buzuq matn beradi — vision esa slayddagi hamma narsani to'g'ri o'qiydi.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from google.genai import types

from .sozlama import KANONIK, OCR_MODELLAR, PARALLEL, klient, log, qayta_urinib, slug

PROMPT = """Bu o'quv kursi slaydining rasmi. Undagi BARCHA mazmunni to'liq Markdown formatida chiqar.

QOIDALAR:
1. Slayd sarlavhasini `#` bilan boshla.
2. Barcha matnni aslidek yoz (o'zbek/rus/ingliz — qanday bo'lsa shunday). Hech narsani tashlab ketma.
3. Jadval bo'lsa — Markdown jadval qil.
4. Diagramma, sxema, rasm bo'lsa — mazmunini 1-3 jumlada tavsifla: `[RASM: ...]`.
5. Slayd raqami, kolontitul, suv belgisi kabi bezaklarni YOZMA.
6. FAQAT slayd mazmunini chiqar — o'z izohingni qo'shma."""

MASSHTAB = 2.0     # 144 dpi — slayd matni uchun yetarli
JPEG_SIFAT = 80


def _sahifa_rasm(sahifa) -> bytes:
    import fitz  # PyMuPDF
    piks = sahifa.get_pixmap(matrix=fitz.Matrix(MASSHTAB, MASSHTAB))
    return piks.tobytes("jpeg", jpg_quality=JPEG_SIFAT)


def _sahifa_oqi(cl, rasm: bytes, idx: int, jami: int, kesh: Path) -> str:
    # checkpoint: oldin o'qilgan sahifa qayta OCR qilinmaydi
    kesh_yol = kesh / f"p_{idx:03d}.md"
    if kesh_yol.exists():
        log(f"  [{idx + 1}/{jami}] keshdan olindi ✓")
        return kesh_yol.read_text(encoding="utf-8")

    qism = types.Part.from_bytes(data=rasm, mime_type="image/jpeg")

    def sorov(model):
        return cl.models.generate_content(
            model=model, contents=[qism, PROMPT],
            config=types.GenerateContentConfig(
                temperature=0.1, max_output_tokens=8192,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=128 if "pro" in model else 0),
            ))

    oxirgi = None
    for model in OCR_MODELLAR:
        try:
            javob = qayta_urinib(lambda: sorov(model), f"sahifa {idx + 1} ({model})")
            matn = (javob.text or "").strip()
            kesh_yol.write_text(matn, encoding="utf-8")   # checkpoint
            log(f"  [{idx + 1}/{jami}] sahifa tayyor ✓ ({len(matn)} belgi)")
            return matn
        except Exception as e:
            oxirgi = e
            log(f"  [{idx + 1}/{jami}] {model} ishlamadi, keyingi model...")
    raise oxirgi


def oqi(fayl: Path) -> dict:
    """PDF ni to'liq o'qiydi -> {"sahifalar": [markdown, ...]}"""
    import fitz
    hujjat = fitz.open(str(fayl))
    jami = len(hujjat)
    log(f"PDF: {fayl.name} | {jami} sahifa | vision OCR, parallel {PARALLEL}")

    # rasmlarni oldindan tayyorlaymiz (fitz thread-safe emas — asosiy oqimda)
    rasmlar = []
    for i in range(jami):
        rasmlar.append(_sahifa_rasm(hujjat[i]))
    hujjat.close()
    log(f"  {jami} sahifa rasmga aylantirildi, OCR boshlanadi...")

    kesh = KANONIK / ".kesh" / slug(f"{fayl.stem}_{fayl.suffix.lstrip('.')}")
    kesh.mkdir(parents=True, exist_ok=True)

    cl = klient()
    natijalar: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=PARALLEL) as ex:
        fut = {ex.submit(_sahifa_oqi, cl, r, i, jami, kesh): i for i, r in enumerate(rasmlar)}
        for f in as_completed(fut):
            natijalar[fut[f]] = f.result()

    return {"sahifalar": [natijalar[i] for i in sorted(natijalar)]}
