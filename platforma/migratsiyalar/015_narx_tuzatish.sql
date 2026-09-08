-- Model narxlarini HAQIQIY qiymatga keltirish (2026-09-09, tekshirilgan).
--
-- ⚠️ JIDDIY XATO TUZATILMOQDA. `004_pul.sql` da `gemini-3.5-flash` narxi
-- 0.30/2.50 deb yozilgan edi; Google narxi esa **1.50/9.00** (ai.google.dev
-- va mustaqil manbalar bilan tasdiqlangan). Ya'ni kirish bo'yicha 5x,
-- chiqish bo'yicha 3.6x KAM hisoblangan.
--
-- Oqibatlari:
--   * B2C — xarajat hisoboti past ko'rsatgan; kvota ($ chegarasi) mo'ljaldan
--     ~4x saxiyroq bo'lgan. Mijoz to'silmagan, chunki `kvota_faol=0`.
--   * B2B — `hisob_usd = narx_usd * ustama` bo'lgani uchun 3.0x ustama bilan
--     ham HAQIQIY TANNARXDAN PAST hisob chiqarardi: har so'rovda zarar.
--     Aynan shuning uchun bu tuzatish B2B sotuvidan OLDIN kiritildi.
--
-- 013_narx.sql dagi "TASDIQLANMAGAN" belgilari ham olib tashlanadi —
-- endi uchala narx ham tekshirilgan.
--
-- ESLATMA (bilib turilgan cheklov): `model_narxlar` da bitta kirish narxi
-- bor, Google esa AUDIO kirishni qimmatroq oladi (3-flash: matn $0.50,
-- audio $1.00). STT faqat ingest'da (worker) ishlaydi va B2B hamkorlar
-- yo'lida uchramaydi, shuning uchun matn narxi qo'yildi. Audio ingest
-- hajmi o'ssa — modallik bo'yicha narx kerak bo'ladi.
UPDATE model_narxlar SET
  kirish_1m_usd = 1.50, chiqish_1m_usd = 9.00,
  izoh = 'asosiy: chat/agent/rais/STT/OCR (tekshirilgan 2026-09-09)',
  yangilangan = now()
WHERE model = 'gemini-3.5-flash';

UPDATE model_narxlar SET
  kirish_1m_usd = 0.50, chiqish_1m_usd = 3.00,
  izoh = 'zaxira: 3.5 tushib qolsa (tekshirilgan 2026-09-09; audio kirish $1.00)',
  yangilangan = now()
WHERE model = 'gemini-3-flash-preview';

UPDATE model_narxlar SET
  kirish_1m_usd = 0.25, chiqish_1m_usd = 1.50,
  izoh = 'yengil zaxira: tez/arzon ishlar (tekshirilgan 2026-09-09)',
  yangilangan = now()
WHERE model = 'gemini-3.1-flash-lite-preview';

-- Embedding narxi to'g'ri edi, faqat izohni aniqlaymiz.
UPDATE model_narxlar SET
  izoh = 'embedding, faqat kirish (tekshirilgan 2026-09-09)', yangilangan = now()
WHERE model = 'gemini-embedding-001';

-- Yangi o'rnatishda ham to'g'ri narx tushsin (004 va 013 dan keyin qo'llanadi).
INSERT INTO model_narxlar(model, kirish_1m_usd, chiqish_1m_usd, izoh) VALUES
  ('gemini-3.6-flash', 1.50, 7.50,
   'hozircha ishlatilmaydi — 3.5 o‘rniga o‘tilsa chiqish 17% arzon')
ON CONFLICT (model) DO NOTHING;
