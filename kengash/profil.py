# -*- coding: utf-8 -*-
"""User o'rganish — har majlisdan keyin foydalanuvchi profili yangilanadi.

Profil = qiziqish mavzulari, ehtimoliy roli, savol berish uslubi (qisqa matn).
U keyingi majlislarda direktorlarga KONTEKST sifatida beriladi (fakt manbasi EMAS)
va tushunarsiz savol variantlarini shaxsiylashtiradi.
"""
from . import db
from .agentlar import _generatsiya
from .sozlama import AGENT_MODELLAR, log


def yangila(uid: int):
    """Fon oqimida chaqiriladi — xato bo'lsa jimgina o'tadi (majlisga ta'sir yo'q)."""
    try:
        savollar = db.savollar(uid, 15)
        if not savollar:
            return
        eski = db.profil_ol(uid)
        prompt = f"""Sen foydalanuvchi profilini yurituvchi yordamchisan. Quyida foydalanuvchining
AI direktorlar kengashiga bergan savollari (eskidan yangiga) va eski profili.

{f"ESKI PROFIL: {eski}" if eski else "ESKI PROFIL: (hali yo'q)"}

SAVOLLARI:
{chr(10).join(f"- {s}" for s in savollar)}

Yangilangan qisqa profil yoz (o'zbek tilida, MAKSIMUM 60 so'z):
- qiziqish mavzulari (masalan: sotuv, narxlash, jamoa...)
- ehtimoliy roli/darajasi (masalan: tadbirkor, sotuv menejeri — faqat savollardan sezilsa)
- savol uslubi (qisqa/batafsil, amaliy/nazariy)
Taxmin qilishga majbur emassan — faqat savollardan aniq ko'ringanini yoz.

Javobing FAQAT profil matnining o'zi bo'lsin — kirish so'zsiz, izohsiz, qo'shtirnoqsiz."""
        matn = _generatsiya(AGENT_MODELLAR, prompt, harorat=0.2).strip().strip('"')
        if matn:
            db.profil_yoz(uid, matn)
            log(f"  profil yangilandi (user {uid}, {len(matn)} belgi)")
    except Exception as e:
        log(f"  profil yangilash xatosi (user {uid}): {str(e)[:80]}")
