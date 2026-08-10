-- 005: cutover uchun — eski tizim yozuvlarini belgilash.
--
-- Nima uchun: cutover kuni eski servisdan YANGI kengash.db olinadi va
-- foydalanuvchi tarixi qayta ko'chiriladi. `eski_id` bo'lmasa qayta ishga
-- tushirish barcha suhbat/majlisni IKKILANTIRIB yuboradi. Endi ko'chirish
-- avval `eski_id IS NOT NULL` qatorlarni tozalaydi, keyin yangisini yozadi —
-- yangi platformada tug'ilgan yozuvlar (eski_id IS NULL) tegilmaydi.

ALTER TABLE suhbatlar ADD COLUMN IF NOT EXISTS eski_id bigint;
ALTER TABLE majlislar ADD COLUMN IF NOT EXISTS eski_id bigint;

CREATE UNIQUE INDEX IF NOT EXISTS idx_suhbat_eski
  ON suhbatlar(eski_id) WHERE eski_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_majlis_eski
  ON majlislar(eski_id) WHERE eski_id IS NOT NULL;
