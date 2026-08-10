# -*- coding: utf-8 -*-
"""Suhbat konteksti — foydalanuvchi bitta chatda oldingi savol-javobga ishora
qilib yangi savol berishi mumkin ("buni batafsilroq", "o'sha narxni qayta hisobla").

Ikki vazifa:
  kontekst()  — oxirgi majlislarning savol+xulosalarini olib beradi;
  mustaqil()  — follow-up savolni suhbatsiz ham tushunarli MUSTAQIL savolga
                aylantiradi (RAG qidiruv to'g'ri ishlashi uchun shart).
"""
import re

from . import db
from .agentlar import _generatsiya
from .sozlama import AGENT_MODELLAR, CHIQISH, log

XULOSA_RE = re.compile(
    r"# YAKUNIY XULOSA \(RAIS\)\n(.*?)"
    r"(?=\n## MANBALAR \(yagona|\n---\n\n# DIREKTORLAR|\Z)", re.S)


def kontekst(uid: int, suhbat_id: int | None = None, n: int = 3) -> list[dict]:
    """Oxirgi n majlis: [{savol, xulosa}] (eskidan yangiga).

    suhbat_id berilsa — FAQAT o'sha chat-sessiya ichidagi majlislar (Claude'dagi
    kabi har chat o'z tarixini eslaydi, boshqa chatlar aralashmaydi)."""
    if suhbat_id:
        royxat = db.suhbat_majlislari(uid, suhbat_id)
    else:
        royxat = db.majlislar(uid)
    nat = []
    for r in royxat[-n:]:
        xulosa = ""
        try:
            m = XULOSA_RE.search((CHIQISH / r["fayl"]).read_text(encoding="utf-8"))
            if m:
                xulosa = m.group(1).strip()
        except Exception:
            pass
        nat.append({"savol": r["savol"], "xulosa": xulosa[:1500]})
    return nat


def formatla(ktx: list[dict]) -> str:
    if not ktx:
        return ""
    return "\n\n".join(
        f"[Oldingi savol {i}]: {k['savol']}\n"
        f"[Kengash javobi {i} — qisqartirilgan]:\n{k['xulosa'] or '(xulosa saqlanmagan)'}"
        for i, k in enumerate(ktx, 1))


def mustaqil(savol: str, ktx: list[dict]) -> str:
    """Follow-up savolni mustaqil shaklga keltiradi (kontekst bo'lmasa — o'zi)."""
    if not ktx:
        return savol
    prompt = f"""Quyida foydalanuvchi bilan suhbat tarixi va uning YANGI savoli.
Agar yangi savol oldingi suhbatga ishora qilsa (masalan: "buni", "o'shani",
"batafsilroq tushuntir", "unda qancha edi") — uni suhbatni ko'rmagan odam ham
to'liq tushunadigan MUSTAQIL savolga aylantir.
Agar savol allaqachon mustaqil bo'lsa — AYNAN o'zini qaytar, bir harfini ham o'zgartirma.
Ma'nosini kengaytirma, yangi mavzu qo'shma.

SUHBAT:
{formatla(ktx)}

YANGI SAVOL: {savol}

Javobing FAQAT yakuniy savol matnining o'zi bo'lsin."""
    try:
        yangi = _generatsiya(AGENT_MODELLAR, prompt, harorat=0.0).strip().strip('"')
        if yangi and len(yangi) < 600:
            if yangi != savol:
                log(f"Savol mustaqil shaklga keltirildi: {yangi[:120]}")
            return yangi
    except Exception as e:
        log(f"Savolni qayta yozish xatosi ({str(e)[:80]}) — asl savol ishlatiladi")
    return savol
