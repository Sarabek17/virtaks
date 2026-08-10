# -*- coding: utf-8 -*-
"""Ingest — bilim manbasini bazaga kiritish (WORKER job).

Oqim: asl fayl S3 dan -> o'quvchi (STT/OCR/parser) -> bo'laklash -> teglash ->
embedding -> bolaklar jadvali. Slayd rasmlari S3 ga, audio vaqt oralig'i bo'lakka
yoziladi — keyin "aynan olingan fragment" shulardan qaytariladi.

Har og'ir qadam S3 keshiga yoziladi: job qayta urinilsa STT/OCR takrorlanmaydi
(pul va vaqt tejaladi).
"""
import json
import re
import tempfile
import time
from pathlib import Path

from . import db, llm, oquvchi, pg, pul, storage
from .sozlama import log

TEGLAR = ["strategiya", "moliya", "sotuv", "marketing", "operatsiya",
          "huquq", "texnologiya", "hr", "umumiy"]
TEG_GURUH = 25
EMBED_GURUH = 20

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


class Kesh:
    """Manba bo'yicha oraliq natijalar keshi (S3 da — worker qayta ishga tushsa ham qoladi)."""

    def __init__(self, manba_id: int):
        self.prefiks = f"kesh/{manba_id}/"

    def ol(self, nom: str) -> str | None:
        try:
            return storage.ol(self.prefiks + nom).decode("utf-8")
        except Exception:
            return None

    def yoz(self, nom: str, matn: str):
        try:
            storage.yukla(self.prefiks + nom, matn.encode("utf-8"),
                          "text/plain; charset=utf-8")
        except Exception as e:
            log(f"kesh yozilmadi ({nom}): {str(e)[:80]}")

    def tozala(self):
        try:
            storage.prefiks_ochir(self.prefiks)
        except Exception:
            pass


# ---------------------------------------------------------------- teglash / embedding

def _json_royxat(matn: str) -> list:
    """LLM javobidan JSON massiv ajratadi (oldin/keyin ortiqcha matn bo'lsa ham)."""
    matn = (matn or "").strip()
    for urinish in (lambda: json.loads(matn),
                    lambda: json.JSONDecoder().raw_decode(matn)[0],
                    lambda: json.loads(re.search(r"\[[\s\S]*\]", matn).group(0))):
        try:
            n = urinish()
            if isinstance(n, list):
                return n
        except Exception:
            continue
    return []


def _teglash(bolaklar: list[dict], yoz):
    for i in range(0, len(bolaklar), TEG_GURUH):
        guruh = bolaklar[i:i + TEG_GURUH]
        royxat = "\n".join(f"{n + 1}. {b['matn'][:400]}" for n, b in enumerate(guruh))
        prompt = TEG_PROMPT.format(teglar=", ".join(TEGLAR), bolaklar=royxat)
        teg_royxat = []
        for urinish in range(2):
            try:
                javob = llm.generatsiya(llm.AGENT_MODELLAR, prompt, json_rejim=True,
                                        harorat=0.0 if urinish == 0 else 0.2,
                                        bosqich="teglash")
                teg_royxat = _json_royxat(javob)
                if len(teg_royxat) >= len(guruh) // 2:
                    break
                yoz(f"  teglash javobi to'liq emas ({len(teg_royxat)}/{len(guruh)})"
                    f"{' — qayta' if urinish == 0 else ''}")
            except Exception as e:
                yoz(f"  teglash xatosi ({str(e)[:80]})"
                    f"{' — qayta' if urinish == 0 else ''}")
        for b, teglar in zip(guruh, teg_royxat if isinstance(teg_royxat, list) else []):
            toza = [t for t in teglar if t in TEGLAR] if isinstance(teglar, list) else []
            b["teglar"] = toza or ["umumiy"]
        for b in guruh:
            b.setdefault("teglar", ["umumiy"])
        yoz(f"  teglash: {min(i + TEG_GURUH, len(bolaklar))}/{len(bolaklar)}")


def _embedding(bolaklar: list[dict], yoz):
    for i in range(0, len(bolaklar), EMBED_GURUH):
        guruh = bolaklar[i:i + EMBED_GURUH]
        vektorlar = llm.embed([b["matn"][:8000] for b in guruh])
        for b, v in zip(guruh, vektorlar):
            b["embedding"] = v
        yoz(f"  embedding: {min(i + EMBED_GURUH, len(bolaklar))}/{len(bolaklar)}")


def _rasmlarni_yukla(manba_id: int, rasmlar: list, bolaklar: list[dict], yoz):
    """Sahifa suratlarini S3 ga yozadi va bo'laklarga yo'lini bog'laydi."""
    if not rasmlar:
        return 0
    yollar = {}
    for idx, bayt, mime in rasmlar:
        yol = f"sahifalar/{manba_id}/{idx:03d}.jpg"
        storage.yukla(yol, bayt, mime)
        yollar[idx] = yol
    for b in bolaklar:
        if b.get("sahifa") is not None:
            b["sahifa_png"] = yollar.get(b["sahifa"], "")
    yoz(f"  {len(yollar)} sahifa surati omborga yozildi")
    return len(yollar)


# ---------------------------------------------------------------- asosiy oqim

def _oqi(manba: dict, kesh: Kesh, yoz) -> dict:
    """Manba turiga qarab mos o'quvchini chaqiradi."""
    if manba["tur"] == "web" or (not manba["s3_yol"] and manba["manba_url"]):
        return oquvchi.web_oqi(manba["manba_url"], yoz)

    if not manba["s3_yol"]:
        raise RuntimeError("manbada na fayl, na URL bor")

    asl = manba["asl_nom"] or manba["nom"] or manba["s3_yol"].split("/")[-1]
    suffix = Path(asl).suffix.lower() or Path(manba["s3_yol"]).suffix.lower()
    with tempfile.TemporaryDirectory(prefix="twin_ingest_") as tdir:
        yol = Path(tdir) / f"manba{suffix}"
        yoz(f"asl fayl olinmoqda: {manba['s3_yol']}")
        storage.ol_faylga(manba["s3_yol"], str(yol))   # to'g'ridan-to'g'ri diskka
        yoz(f"  {yol.stat().st_size / 1e6:.1f} MB")

        if suffix in oquvchi.AUDIO_TURLAR:
            return oquvchi.audio_oqi(yol, kesh, yoz)
        if suffix in {".pptx", ".ppt"}:
            yoz("PPTX -> PDF (LibreOffice)...")
            pdf = oquvchi.pptx_pdfga(yol, Path(tdir))
            return oquvchi.pdf_oqi(pdf, kesh, yoz, atama="slayd")
        if suffix == ".pdf":
            return oquvchi.pdf_oqi(yol, kesh, yoz,
                                   atama="slayd" if manba["tur"] == "slayd" else "sahifa")
        if suffix in oquvchi.JADVAL_TURLAR:
            return oquvchi.jadval_oqi(yol, yoz)
        if suffix in oquvchi.HUJJAT_TURLAR:
            return oquvchi.hujjat_oqi(yol, yoz)
    raise RuntimeError(f"qo'llab-quvvatlanmaydigan format: {suffix or '(nomalum)'}")


_SAHIFA_RAQAM = re.compile(r"^(\d+)-(slayd|sahifa|qism)")


def sahifa_render(job: dict, yoz) -> dict:
    """Bo'laklari allaqachon bazada bo'lgan manbaning sahifa suratlarini tayyorlaydi.

    Eski (migratsiya qilingan) slaydlar uchun: OCR qaytadan qilinmaydi — faqat
    rasm chiqariladi va `joy` ("8-slayd") bo'yicha bo'lakka bog'lanadi.
    """
    mid = int(job["kirish"]["manba_id"])
    manba = db.manba_ol(mid)
    if not manba:
        raise RuntimeError(f"manba #{mid} topilmadi")
    if not manba["s3_yol"]:
        raise RuntimeError("asl fayl omborda yo'q")

    suffix = Path(manba["asl_nom"] or manba["nom"]).suffix.lower()
    yoz(f"=== SAHIFA RENDER: {manba['nom']} ===")
    with tempfile.TemporaryDirectory(prefix="twin_render_") as tdir:
        yol = Path(tdir) / f"manba{suffix}"
        storage.ol_faylga(manba["s3_yol"], str(yol))
        if suffix in {".pptx", ".ppt"}:
            yol = oquvchi.pptx_pdfga(yol, Path(tdir))
        elif suffix != ".pdf":
            raise RuntimeError(f"sahifa renderi faqat PDF/PPTX uchun ({suffix})")

        import fitz
        hujjat = fitz.open(str(yol))
        yollar = {}
        for i in range(len(hujjat)):
            piks = hujjat[i].get_pixmap(
                matrix=fitz.Matrix(oquvchi.RASM_MASSHTAB, oquvchi.RASM_MASSHTAB))
            s3_yol = f"sahifalar/{mid}/{i:03d}.jpg"
            storage.yukla(s3_yol, piks.tobytes("jpeg", jpg_quality=oquvchi.JPEG_SIFAT),
                          "image/jpeg")
            yollar[i] = s3_yol
        hujjat.close()
    yoz(f"  {len(yollar)} sahifa surati yozildi")

    bogliq = 0
    for b in pg.hammasi_d("SELECT id, joy FROM bolaklar WHERE manba_id=%s", mid):
        m = _SAHIFA_RAQAM.match((b["joy"] or "").strip())
        if not m:
            continue
        s3_yol = yollar.get(int(m.group(1)) - 1)
        if s3_yol:
            pg.bajar("UPDATE bolaklar SET sahifa_png=%s WHERE id=%s", s3_yol, b["id"])
            bogliq += 1
    pg.bajar("UPDATE manbalar SET sahifa_soni=%s WHERE id=%s", len(yollar), mid)
    yoz(f"TAYYOR: {bogliq} bo'lak sahifa surati bilan bog'landi")
    return {"manba_id": mid, "sahifalar": len(yollar), "bolaklar": bogliq}


def bajar(job: dict, yoz) -> dict:
    """job.kirish: {manba_id}. ingest_fayl va ingest_url uchun umumiy."""
    bosh = time.time()
    mid = int(job["kirish"]["manba_id"])
    manba = db.manba_ol(mid)
    if not manba:
        raise RuntimeError(f"manba #{mid} topilmadi")
    # Ingest xarajati platformaniki — daftarga yoziladi, lekin mijoz kvotasidan
    # yechilmaydi (kvota faqat majlis uchun, qarang pul.majlis_yakunla).
    llm.yigich_boshla(user_id=job.get("user_id"), twin_id=manba["twin_id"],
                      job_id=job["id"])

    yoz(f"=== INGEST: {manba['nom']} (tur: {manba['tur']}) ===")
    db.manba_holat(mid, "ishlanmoqda")
    kesh = Kesh(mid)
    try:
        n = _oqi(manba, kesh, yoz)
        bolaklar = [b for b in n["bolaklar"] if b.get("matn", "").strip()]
        if not bolaklar:
            raise RuntimeError("matn ajratilmadi — bo'lak yo'q")
        yoz(f"{len(bolaklar)} bo'lak tayyorlandi")

        sahifa_soni = _rasmlarni_yukla(mid, n.get("rasmlar") or [], bolaklar, yoz)
        _teglash(bolaklar, yoz)
        _embedding(bolaklar, yoz)

        db.bolaklar_almashtir(mid, manba["twin_id"], bolaklar)
        db.manba_tayyor(mid, len(bolaklar), n.get("davomiylik"), sahifa_soni)
        kesh.tozala()

        narx = pul.job_narxi(job["id"])
        davom = round(time.time() - bosh)
        yoz(f"TAYYOR ({davom}s, ${narx:.4f}): {len(bolaklar)} bo'lak bazaga yozildi")
        return {"manba_id": mid, "bolaklar": len(bolaklar), "sahifalar": sahifa_soni,
                "davomiylik": davom, "narx_usd": narx}
    except Exception as e:
        db.manba_holat(mid, "xato", str(e))
        raise
