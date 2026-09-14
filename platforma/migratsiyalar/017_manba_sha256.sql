-- Manba faylining SHA-256 xeshi: bir xil fayl (boshqa nom yoki papkada)
-- ikkinchi marta ingest qilinmasin — pul va vaqt. Faqat manba_yukla
-- (ommaviy yuklash) to'ldiradi; eski yozuvlarda NULL qoladi.
ALTER TABLE manbalar ADD COLUMN IF NOT EXISTS sha256 text;
CREATE INDEX IF NOT EXISTS idx_manba_sha256 ON manbalar(twin_id, sha256)
    WHERE sha256 IS NOT NULL;
