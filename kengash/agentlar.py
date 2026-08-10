# -*- coding: utf-8 -*-
"""Agentlar — har direktor: persona + rol filtrlangan RAG + manba-majburiy javob."""
import json

from google.genai import types

from .qidiruv import qidir
from .sozlama import (AGENT_MODELLAR, AGENT_TEGLARI, PERSONAS, RAIS_MODELLAR,
                      klient, log, qayta_urinib)
from .tekshiruv import iqtibos_tekshir

_kesh = {}


def persona(nom: str) -> str:
    if nom not in _kesh:
        _kesh[nom] = (PERSONAS / f"{nom}.md").read_text(encoding="utf-8")
    return _kesh[nom]


def _generatsiya(modellar: list[str], prompt: str, json_rejim: bool = False,
                 harorat: float = 0.3, tez: bool = False) -> str:
    """Model zanjiri bo'ylab birinchi ishlagan javobni qaytaradi.

    tez=True — HTTP so'rov ichidan chaqiriladigan yo'l (masalan aniqlik
    tekshiruvi): uzun retry-kutishlarsiz, tez muvaffaqiyatsiz bo'ladi.
    """
    # setdefault EMAS: uning argumenti har doim hisoblanadi — har chaqiruvda
    # yangi klient yaratilib tashlanardi
    if "cl" not in _kesh:
        _kesh["cl"] = klient()
    cl = _kesh["cl"]
    oxirgi = None
    for model in modellar:
        def sorov():
            cfg = types.GenerateContentConfig(
                temperature=harorat, max_output_tokens=16384,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=256 if "pro" in model else 0))
            if json_rejim:
                cfg.response_mime_type = "application/json"
            return cl.models.generate_content(model=model, contents=[prompt], config=cfg)
        try:
            javob = qayta_urinib(sorov, model, tez=tez)
            return (javob.text or "").strip()
        except Exception as e:
            oxirgi = e
            log(f"  {model} ishlamadi, keyingi model...")
    raise oxirgi


JAVOB_QOIDA = """QAT'IY QOIDALAR (grounding):
1. FAQAT quyidagi MANBALAR bo'limidagi ma'lumotlarga asoslan. O'z umumiy bilimingdan fakt QO'SHMA.
2. Har asosiy da'vodan keyin manba raqamini ko'rsat: [1], [2]... Faqat MANBALAR ro'yxatida bor
   raqamlarni ishlat. Oraliq yozma ("[1-3]" EMAS) — har raqamni alohida: [1], [2], [3].
3. Savolga manbalarda javob topilmasa, ochiq yoz: "MANBADA YO'Q: ..." — va taxmin qilma.
4. O'zbek tilida, aniq va ishbilarmon uslubda javob ber. Rolingga xos nuqtai nazardan yondash.
5. Javob BATAFSIL va to'liq bo'lsin — mavzuni chuqur yorit. Yuzaki 2-3 jumlalik javob
   YETARLI EMAS. Tuzilishi: qisqa xulosa -> batafsil tahlil (manbalardagi misollar,
   raqamlar, bosqichlar bilan; taqqoslash bo'lsa Markdown jadval qo'sh) ->
   amaliy tavsiyalar (qadam-baqadam) -> risklar.
6. SUHBAT TARIXI berilgan bo'lsa u savolni TUSHUNISH uchun — undagi gaplarni fakt
   sifatida keltirma, faktni faqat MANBALAR bo'limidan olib [n] bilan ko'rsat."""


def _nazorat_bilan(modellar: list[str], prompt: str, manba_soni: int,
                   izoh: str, harorat: float = 0.3) -> str:
    """Generatsiya + iqtibos nazorati: xato topilsa bir marta tuzatish talabi bilan qayta."""
    javob = _generatsiya(modellar, prompt, harorat=harorat)
    xato = iqtibos_tekshir(javob, manba_soni)
    if xato:
        log(f"  {izoh}: iqtibos xatosi ({xato}) — qayta so'raladi")
        javob = _generatsiya(modellar, prompt + f"""

OGOHLANTIRISH: Avvalgi urinishda xato bor edi — {xato}.
Qoidaga qat'iy amal qil: faqat [1]–[{manba_soni}] oralig'idagi raqamlarni ishlat,
har asosiy da'voga iqtibos qo'y, manbada bo'lmasa "MANBADA YO'Q" deb yoz.""", harorat=harorat)
        xato2 = iqtibos_tekshir(javob, manba_soni)
        if xato2:
            log(f"  {izoh}: iqtibos xatosi qoldi ({xato2})")
    return javob


def agent_javobi(rol: str, savol: str, kontekst: str = "", ustoz: str = "") -> dict:
    """Bitta direktor javobi: rol teglariga mos RAG + persona + grounding.

    ustoz berilsa faqat shu ustoz bilimidan qidiriladi."""
    teglar = AGENT_TEGLARI[rol]
    bolaklar = qidir(savol, teglar=teglar, top=10, ustoz=ustoz)
    manbalar = "\n\n".join(
        f"[{i + 1}] ({b['manba']}, {b['joy']}):\n{b['matn']}"
        for i, b in enumerate(bolaklar))

    prompt = f"""{persona(rol)}

{JAVOB_QOIDA}

{f'KENGASH KONTEKSTI: {kontekst}' if kontekst else ''}

MANBALAR:
{manbalar if manbalar else '(manba topilmadi)'}

SAVOL: {savol}

{rol} sifatida javobing:"""

    javob = _nazorat_bilan(AGENT_MODELLAR, prompt, len(bolaklar), rol)
    log(f"  {rol} javob berdi ({len(javob)} belgi, {len(bolaklar)} manba)")
    return {"rol": rol, "javob": javob,
            "manbalar": [{"n": i + 1, "id": b["id"], "manba": b["manba"],
                          "joy": b["joy"], "tur": b.get("tur", ""),
                          "dars": b.get("dars", "")}
                         for i, b in enumerate(bolaklar)]}


def rais_yonaltirish(savol: str) -> list[str]:
    """Rais savolga qarab qaysi direktorlar kerakligini aniqlaydi."""
    prompt = f"""{persona('RAIS')}

Direktorlar: CEO (strategiya), CTO (texnologiya), CFO (moliya), COO (operatsiya/HR), CLO (huquq), CMO (marketing/sotuv).

Savol: {savol}

Bu savolga qaysi direktorlar javob berishi kerak? Faqat haqiqatan tegishlilarini tanla (1-6 ta).
Javob — faqat JSON: {{"agentlar": ["CFO", ...], "sabab": "qisqa izoh"}}"""
    try:
        j = json.loads(_generatsiya(AGENT_MODELLAR, prompt, json_rejim=True, harorat=0.0))
        tanlov = [a for a in j.get("agentlar", []) if a in AGENT_TEGLARI]
        if tanlov:
            log(f"RAIS yo'naltirdi: {', '.join(tanlov)} — {j.get('sabab', '')}")
            return tanlov
    except Exception as e:
        log(f"Yo'naltirish xatosi ({str(e)[:80]}) — hamma direktor chaqiriladi")
    return list(AGENT_TEGLARI)


def rais_sintez(savol: str, javoblar: list[dict],
                manba_royxati: str = "", manba_soni: int = 0,
                suhbat: str = "") -> str:
    """Rais barcha javoblarni yagona qarorga birlashtiradi (yagona [n] raqamlash bilan)."""
    blok = "\n\n".join(f"===== {j['rol']} =====\n{j['javob']}" for j in javoblar)
    prompt = f"""{persona('RAIS')}

{f'''SUHBAT TARIXI (foydalanuvchi oldingi savol-javoblarga ishora qilishi mumkin;
bu faqat savolni tushunish uchun — fakt manbasi EMAS):
{suhbat}

''' if suhbat else ''}SAVOL: {savol}

YAGONA MANBALAR RO'YXATI (direktorlar javoblaridagi [n] raqamlari AYNAN shu ro'yxatga ishora qiladi):
{manba_royxati if manba_royxati else "(royxat berilmadi)"}

DIREKTORLAR JAVOBLARI:
{blok}

Endi rais sifatida YAKUNIY XULOSA yoz (o'zbek tilida, Markdown). BATAFSIL bo'lsin —
foydalanuvchi to'liq, chuqur yoritilgan javob kutadi, yuzaki emas:
## Qisqa javob — 3-5 jumla, eng muhimi
## Batafsil tahlil — mavzuni TO'LIQ yoritib ber: har muhim jihatni alohida kichik
   sarlavha yoki band bilan, manbalardagi misollar va raqamlar bilan; taqqoslash
   yoki variantlar bo'lsa Markdown jadval qo'sh
## Kengash fikri — har direktordan asosiy nuqtalar
## Kelishmovchiliklar — bo'lsa ochiq ko'rsat, bo'lmasa "yo'q" de
## Yakuniy tavsiya — aniq, bajariladigan qadamlar (raqamlangan ro'yxat, har qadam izohli)
## Manba holati — javob manbalarga qanchalik tayanadi; "MANBADA YO'Q" belgilari bo'lsa sanab o't

DIAGRAMMA: agar javobda jarayon, bosqichlar ketma-ketligi, voronka yoki tuzilma
tushuntirilayotgan bo'lsa va chizma chindan tushunishni osonlashtirsa — mos joyga
mermaid diagramma qo'sh (majburiy emas, faqat foydali bo'lsa):
```mermaid
flowchart TD
    A[Birinchi bosqich] --> B[Ikkinchi bosqich]
```
Diagramma matnlari o'zbekcha bo'lsin; node ichida qo'shtirnoq va [n] iqtibos ishlatma.

QAT'IY: har asosiy da'vo yonida [n] iqtibosni saqla — faqat yuqoridagi YAGONA RO'YXATDAGI
raqamlarni ishlat. Direktorlar aytmagan yangi fakt QO'SHMA."""
    if manba_soni:
        return _nazorat_bilan(RAIS_MODELLAR, prompt, manba_soni, "RAIS", harorat=0.2)
    return _generatsiya(RAIS_MODELLAR, prompt, harorat=0.2)
