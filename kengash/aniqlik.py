# -*- coding: utf-8 -*-
"""Savol aniqligi tekshiruvi — tushunarsiz savolga "Siz buni so'ramoqchimidingiz?"
variantlarini taklif qiladi (majlis boshlanishidan OLDIN, tez flash model bilan).

Xato bo'lsa hech qachon bloklamaydi — {"aniq": True} qaytaradi.
"""
import json

from .agentlar import _generatsiya
from .sozlama import AGENT_MODELLAR, log

BILIM_SOHASI = """Kengash bilim bazasi: sotuv va marketing darslari (audio + slaydlar),
narxlash, mijoz bilan ishlash, jamoa/HR, gipoteza va biznes jarayonlar, moliya,
huquqiy shablonlar (mehnat shartnomasi, ichki tartib-qoidalar, KP/tijoriy taklif),
vaqt boshqaruvi (Eyzenxauer matritsasi, Gantt chart, vaqt jadvali), SSP/KPI,
tashkiliy tuzilma (ORG chart/model), biznes atamalar lug'ati. Kengash mos shablon
asosida to'ldirilgan tayyor Excel fayl ham tuzib bera oladi."""


def tekshir(savol: str, profil: str = "", suhbat: str = "") -> dict:
    """-> {"aniq": True} yoki {"aniq": False, "izoh": "...", "variantlar": [...]}"""
    prompt = f"""Sen savol sifatini tekshiruvchi yordamchisan. Quyida foydalanuvchi AI direktorlar
kengashiga bergan savol. Kengash faqat o'z bilim bazasidagi mavzularda maslahat beradi.

{BILIM_SOHASI}

{f"FOYDALANUVCHI HAQIDA (oldingi savollaridan o'rganilgan): {profil}" if profil else ""}

{f'''SUHBAT TARIXI (yangi savol shunga ishora qilishi mumkin):
{suhbat}''' if suhbat else ''}

SAVOL: {savol}

Vazifa: savol ANIQ va javob berishga tayyormi, yoki TUSHUNARSIZ/juda umumiy/chalami?

Qoidalar:
- Savol aniq mavzu va maqsadga ega bo'lsa -> aniq=true (shubhada bo'lsang ham aniq=true).
- Savol suhbat tarixidagi oldingi javobga ishora qilsa (masalan "buni batafsilroq
  tushuntir", "o'shani davom ettir", "unda qancha edi") — bu ANIQ savol (aniq=true).
- Faqat quyidagilar tushunarsiz: salomlashish/bo'sh gap ("salom", "qalaysan"), bir-ikki
  so'zli mavhum savol ("narx?", "sotuv") suhbatda ham izohi bo'lmasa, nima
  so'ralayotgani umuman noaniq bo'lgan gap.
- Tushunarsiz bo'lsa: foydalanuvchi nimani nazarda tutgan bo'lishi mumkinligini o'ylab,
  bilim bazasiga mos 3-4 ta ANIQ, to'liq savol varianti taklif qil (o'zbek tilida,
  har biri mustaqil yuborishga tayyor savol bo'lsin).

Javob — faqat JSON:
{{"aniq": true}} yoki
{{"aniq": false, "izoh": "1 jumlali izoh nimasi tushunarsiz", "variantlar": ["...", "...", "..."]}}"""
    try:
        # tez=True: bu tekshiruv HTTP so'rov oqimida ishlaydi — uzun retry
        # kutishlari threadpool'ni band qilib butun serverni sekinlatardi
        j = json.loads(_generatsiya(AGENT_MODELLAR, prompt, json_rejim=True,
                                    harorat=0.0, tez=True))
        if j.get("aniq", True):
            return {"aniq": True}
        variantlar = [str(v).strip() for v in j.get("variantlar", []) if str(v).strip()][:4]
        if not variantlar:
            return {"aniq": True}
        return {"aniq": False, "izoh": str(j.get("izoh", "")).strip(),
                "variantlar": variantlar}
    except Exception as e:
        log(f"Aniqlik tekshiruvi xatosi ({str(e)[:80]}) — savol qabul qilinadi")
        return {"aniq": True}
