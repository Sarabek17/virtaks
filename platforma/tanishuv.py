# -*- coding: utf-8 -*-
"""Tanishuv testi — foydalanuvchini bir marta so'rab, javob uslubini moslash.

Savollar KODDA STATIK va javoblar VARIANTLI (bitta erkin matn maydonidan tashqari):
  * LLM chaqirilmaydi — test bepul va har doim bir xil ishlaydi;
  * foydalanuvchi kiritgan matn promptga ko'rsatma sifatida tusha olmaydi —
    faqat oldindan ma'lum kodlar profilga yoziladi (Lethal Trifecta: ishonchsiz
    kirishni struktura bilan cheklash).

Erkin matn faqat "maqsad" maydonida: 200 belgigacha, boshqaruv belgilaridan
tozalanadi va promptga "FAKT MANBASI EMAS" blokida qo'yiladi.
"""
import re
from datetime import datetime, timezone

MAKS_MAQSAD = 200

SAVOLLAR = [
    {"kod": "rol", "savol": "O'zingizni qanday ta'riflaysiz?",
     "javoblar": [
         ("tadbirkor", "Tadbirkor / biznes egasi"),
         ("rahbar", "Rahbar yoki menejer"),
         ("mutaxassis", "Mutaxassis (sotuv, marketing, moliya...)"),
         ("oquvchi", "O'rganyapman — hali ishni boshlamadim")]},

    {"kod": "soha", "savol": "Asosan qaysi sohada ishlaysiz?",
     "javoblar": [
         ("savdo", "Savdo va marketing"),
         ("xizmat", "Xizmat ko'rsatish"),
         ("ishlab_chiqarish", "Ishlab chiqarish"),
         ("talim", "Ta'lim / o'quv markazi"),
         ("raqamli", "IT va raqamli xizmatlar"),
         ("boshqa", "Boshqa soha")]},

    {"kod": "daraja", "savol": "Shu sohadagi tajribangiz qancha?",
     "javoblar": [
         ("boshlangich", "Endi boshlayapman"),
         ("orta", "1–3 yil"),
         ("tajribali", "3 yildan ko'p")]},

    {"kod": "uslub", "savol": "Javoblar qanday bo'lishini xohlaysiz?",
     "javoblar": [
         ("qisqa", "Qisqa va aniq — vaqtim kam"),
         ("muvozanat", "O'rtacha — asosiylari yoritilsin"),
         ("batafsil", "Batafsil — mavzu to'liq ochilsin")]},

    {"kod": "yondashuv", "savol": "Sizga ko'proq nima kerak?",
     "javoblar": [
         ("amaliy", "Amaliy qadamlar — nima qilishim kerak"),
         ("nazariy", "Tushuntirish — nima uchun shunday"),
         ("aralash", "Ikkalasi ham")]},

    # Faqat tajribalilardan so'raladi — boshlang'ichga atama darajasi avtomatik "sodda"
    {"kod": "atama", "savol": "Kasbiy atamalarni qanday ishlatay?",
     "shart": {"daraja": ["orta", "tajribali"]},
     "javoblar": [
         ("erkin", "Erkin ishlat — tushunaman"),
         ("izohli", "Ishlat, lekin qisqa izoh bilan")]},

    {"kod": "maqsad", "tur": "matn", "ixtiyoriy": True,
     "savol": "Hozirgi asosiy maqsadingiz nima? (ixtiyoriy)",
     "izoh": "Masalan: “3 oyda sotuvni ikki barobar oshirish” yoki "
             "“jamoani qayta tuzish”. Javoblar shunga qarab yo'naltiriladi."},
]

_KODLAR = {s["kod"]: {j[0] for j in s.get("javoblar", [])} for s in SAVOLLAR}


def mos_keladimi(s: dict, javoblar: dict) -> bool:
    shart = s.get("shart")
    return not shart or all(javoblar.get(k) in v for k, v in shart.items())


def savollar_royxati(javoblar: dict | None = None,
                     hammasi: bool = False) -> list[dict]:
    """UI uchun savollar.

    hammasi=False — `shart` bajarilmaganlari tushirib qoldiriladi (server tomoni).
    hammasi=True  — barchasi `shart` bilan qaytadi, UI javob berilgan sari
                    o'zi ochib boradi (savol oqimi jonli tarmoqlanadi).
    """
    javoblar = javoblar or {}
    natija = []
    for s in SAVOLLAR:
        if not hammasi and not mos_keladimi(s, javoblar):
            continue
        natija.append({"kod": s["kod"], "savol": s["savol"],
                       "tur": s.get("tur", "variant"),
                       "izoh": s.get("izoh", ""),
                       "ixtiyoriy": bool(s.get("ixtiyoriy")),
                       "shart": s.get("shart") or {},
                       "javoblar": [{"kod": k, "matn": m}
                                    for k, m in s.get("javoblar", [])]})
    return natija


def _tozala(matn: str) -> str:
    """Erkin matnni xavfsiz holga keltiradi (boshqaruv belgilari, uzunlik)."""
    matn = re.sub(r"[\x00-\x1f\x7f]", " ", str(matn or ""))
    return re.sub(r"\s+", " ", matn).strip()[:MAKS_MAQSAD]


def javoblarni_tekshir(kelgan: dict) -> dict:
    """Faqat OLDINDAN MA'LUM kodlarni qabul qiladi. Noma'lumi tashlanadi."""
    toza = {}
    for s in SAVOLLAR:
        kod = s["kod"]
        qiymat = kelgan.get(kod)
        if qiymat is None:
            continue
        if s.get("tur") == "matn":
            m = _tozala(qiymat)
            if m:
                toza[kod] = m
        elif str(qiymat) in _KODLAR[kod]:
            toza[kod] = str(qiymat)
    return toza


def profil_yasa(javoblar: dict) -> dict:
    """Javoblardan tuzilgan profil (LLM'siz, deterministik)."""
    j = javoblarni_tekshir(javoblar)
    if j.get("daraja") == "boshlangich":
        j.setdefault("atama", "izohli")     # yangi boshlovchiga atama izohlanadi
    j["tugallangan"] = True
    j["vaqt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return j


ROL_MATN = {"tadbirkor": "tadbirkor / biznes egasi", "rahbar": "rahbar-menejer",
            "mutaxassis": "soha mutaxassisi", "oquvchi": "o'rganuvchi"}
SOHA_MATN = {"savdo": "savdo va marketing", "xizmat": "xizmat ko'rsatish",
             "ishlab_chiqarish": "ishlab chiqarish", "talim": "ta'lim",
             "raqamli": "IT va raqamli xizmatlar", "boshqa": "boshqa soha"}
DARAJA_MATN = {"boshlangich": "yangi boshlovchi", "orta": "1–3 yillik tajriba",
               "tajribali": "3+ yillik tajriba"}


def matn_yasa(p: dict) -> str:
    """Profilning odam o'qiydigan qisqa tavsifi (admin va promptlar uchun)."""
    if not p:
        return ""
    qismlar = []
    if p.get("rol"):
        qismlar.append(ROL_MATN.get(p["rol"], p["rol"]))
    if p.get("soha"):
        qismlar.append(SOHA_MATN.get(p["soha"], p["soha"]) + " sohasida")
    if p.get("daraja"):
        qismlar.append(DARAJA_MATN.get(p["daraja"], p["daraja"]))
    matn = ", ".join(qismlar).capitalize()
    if p.get("maqsad"):
        matn += f". Maqsadi: {p['maqsad']}"
    return matn.strip(". ") + "." if matn else ""
