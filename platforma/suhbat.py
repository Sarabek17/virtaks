# -*- coding: utf-8 -*-
"""Suhbat konteksti — bitta chat-sessiya ichidagi savol-javoblar.

kontekst() — shu sessiyaning oxirgi n majlisi (savol + xulosa);
mustaqil() — follow-up savolni RAG uchun mustaqil shaklga keltiradi.
"""
from . import db, llm
from .sozlama import log


def kontekst(uid: int, suhbat_id: int | None, n: int = 3) -> list[dict]:
    if not suhbat_id:
        return []
    majlislar = db.suhbat_majlislari(uid, suhbat_id)[-n:]
    return [{"savol": m["savol"], "xulosa": (m["xulosa"] or "")[:1500]}
            for m in majlislar]


def formatla(ktx: list[dict]) -> str:
    if not ktx:
        return ""
    return "\n\n".join(
        f"[Oldingi savol {i}]: {k['savol']}\n"
        f"[Javob {i} — qisqartirilgan]:\n{k['xulosa'] or '(javob saqlanmagan)'}"
        for i, k in enumerate(ktx, 1))


def mustaqil(savol: str, ktx: list[dict]) -> str:
    """Follow-up savolni suhbatsiz ham tushunarli mustaqil savolga aylantiradi."""
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
        yangi = llm.generatsiya(llm.TEZ_MODELLAR, prompt, harorat=0.0,
                                bosqich="mustaqil").strip().strip('"')
        if yangi and len(yangi) < 600:
            if yangi != savol:
                log(f"Savol mustaqil shaklga keltirildi: {yangi[:120]}")
            return yangi
    except Exception as e:
        log(f"Savolni qayta yozish xatosi ({str(e)[:80]}) — asl savol ishlatiladi")
    return savol
