# -*- coding: utf-8 -*-
"""Savol aniqligi — tushunarsiz savolga "Siz buni so'ramoqchimidingiz?" variantlari.

HTTP so'rov oqimida ishlaydi: tez=True (uzun retry kutishlari serverni bo'g'masin).
Xato bo'lsa hech qachon bloklamaydi.
"""
import json

from . import llm
from .sozlama import log


def tekshir(savol: str, twin: dict | None = None, profil: str = "",
            suhbat: str = "") -> dict:
    """-> {"aniq": True} yoki {"aniq": False, "izoh", "variantlar": [...]}"""
    soha = (twin or {}).get("tavsif") or "biznes, sotuv, marketing va boshqaruv darslari"
    prompt = f"""Sen savol sifatini tekshiruvchi yordamchisan. Quyida foydalanuvchi
raqamli ustozga bergan savol. Ustoz faqat o'z bilim bazasidagi mavzularda
maslahat beradi.

BILIM SOHASI: {soha}

{f"FOYDALANUVCHI HAQIDA (oldingi savollaridan o'rganilgan): {profil}" if profil else ""}

{f'''SUHBAT TARIXI (yangi savol shunga ishora qilishi mumkin):
{suhbat}''' if suhbat else ''}

SAVOL: {savol}

Vazifa: savol ANIQ va javob berishga tayyormi, yoki TUSHUNARSIZ/juda umumiy/chalami?

Qoidalar:
- Savol aniq mavzu va maqsadga ega bo'lsa -> aniq=true (shubhada bo'lsang ham aniq=true).
- Savol suhbat tarixidagi oldingi javobga ishora qilsa (masalan "buni batafsilroq
  tushuntir", "o'shani davom ettir") — bu ANIQ savol (aniq=true).
- Faqat quyidagilar tushunarsiz: salomlashish/bo'sh gap ("salom", "qalaysan"), bir-ikki
  so'zli mavhum savol ("narx?", "sotuv") suhbatda ham izohi bo'lmasa.
- Tushunarsiz bo'lsa: bilim sohasiga mos 3-4 ta ANIQ, to'liq savol varianti taklif qil
  (o'zbek tilida, har biri mustaqil yuborishga tayyor savol bo'lsin).

Javob — faqat JSON:
{{"aniq": true}} yoki
{{"aniq": false, "izoh": "1 jumlali izoh", "variantlar": ["...", "...", "..."]}}"""
    try:
        j = json.JSONDecoder().raw_decode(
            llm.generatsiya(llm.TEZ_MODELLAR, prompt, json_rejim=True, harorat=0.0,
                            tez=True, bosqich="aniqlik").strip())[0]
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
