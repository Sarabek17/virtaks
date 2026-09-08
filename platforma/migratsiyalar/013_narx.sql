-- 0-bosqich (B2B tayyorgarligi): zanjirdagi zaxira modellarning narxi.
--
-- MUAMMO: `llm.py` uchta modelni ishlatadi (_ASOSIY, _ZAXIRA, _YENGIL),
-- `model_narxlar` da esa faqat asosiysi bor edi. Narxi yo'q model
-- `pul.ZAXIRA_NARX` bilan hisoblanadi — bu jimgina taxmin. B2C da bu
-- hisobotni bir oz noto'g'ri qiladi, B2B da esa HAMKORGA CHIQARILADIGAN
-- HISOB noto'g'ri bo'ladi.
--
-- ⚠️ Quyidagi ikki qatorning narxi ASOSIY MODELNIKIGA teng qilib qo'yilgan —
-- bu TASDIQLANMAGAN taxmin, o'ylab topilgan raqam emas. Google narxini
-- tekshirib, admin panelidan tuzating (deploy shart emas). `tayyorlik.py`
-- shu izoh turgani uchun ogohlantirib turadi.
INSERT INTO model_narxlar(model, kirish_1m_usd, chiqish_1m_usd, izoh) VALUES
  ('gemini-3-flash-preview',       0.30, 2.50,
   'TASDIQLANMAGAN NARX - chat/agent zaxirasi, Google narxi bilan solishtiring'),
  ('gemini-3.1-flash-lite-preview', 0.30, 2.50,
   'TASDIQLANMAGAN NARX - tez/arzon ishlar zaxirasi, Google narxi bilan solishtiring')
ON CONFLICT (model) DO NOTHING;
