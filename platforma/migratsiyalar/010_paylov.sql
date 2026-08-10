-- Paylov to'lov provayderi (PAYLOV_REJA.md, 5-bo'lim)
--
-- Additiv: faqat yangi ustun/jadval. Click/Payme yo'llari o'zgarmaydi.
--
-- XAVFSIZLIK QOIDASI (Lethal Trifecta): bu jadvallardagi hech bir qiymat
-- LLM javobidan kelmaydi va LLM promptiga kirmaydi. To'lov holati faqat
-- Basic Auth bilan tekshirilgan callbackdan o'zgaradi.

-- ---------------------------------------------------------------- tolovlar
-- Paylov havolasidagi `account.order_id` sifatida ketma-ket `id` emas, UUID
-- ishlatiladi: tashqi tomon boshqa foydalanuvchining buyurtmasini taxmin qila
-- olmaydi va bizning to'lov hajmimiz havolada ko'rinmaydi.
ALTER TABLE tolovlar ADD COLUMN IF NOT EXISTS tashqi_id uuid
  NOT NULL DEFAULT gen_random_uuid();
CREATE UNIQUE INDEX IF NOT EXISTS idx_tolov_tashqi ON tolovlar(tashqi_id);

-- Kutilayotgan to'lovning amal qilish muddati. NULL = eski yozuvlar (cheksiz).
-- Muddati o'tgan to'lov `tolov_tozala` jobi bilan bekor qilinadi va callback
-- kelsa ham qabul qilinmaydi — "yarim yildan keyin to'ladim" holati bo'lmasin.
ALTER TABLE tolovlar ADD COLUMN IF NOT EXISTS muddat timestamptz;
CREATE INDEX IF NOT EXISTS idx_tolov_muddat
  ON tolovlar(muddat) WHERE holat IN ('kutilmoqda', 'tayyorlangan');

-- ---------------------------------------------------------------- Paylov tranzaksiyalari
-- Idempotentlikning 2-qatlami: PK ustidagi ON CONFLICT DO NOTHING takroriy
-- `transaction.perform` ni bazaning o'zida ushlaydi (1-qatlam —
-- tolovlar(provayder, provayder_id) unikal indeksi, 3-qatlam — pul.tolandi
-- ichidagi SELECT ... FOR UPDATE).
CREATE TABLE IF NOT EXISTS paylov_tranzaksiyalar(
  id          text PRIMARY KEY,                  -- Paylov transaction_id (UUID)
  tolov_id    bigint NOT NULL REFERENCES tolovlar(id) ON DELETE CASCADE,
  summa_som   bigint NOT NULL,
  summa_tiyin bigint NOT NULL DEFAULT 0,
  valyuta     int    NOT NULL DEFAULT 860,
  holat       text   NOT NULL DEFAULT 'bajarildi',  -- bajarildi|bekor
  vaqt        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_paylov_tolov ON paylov_tranzaksiyalar(tolov_id);

-- ---------------------------------------------------------------- sozlamalar
INSERT INTO sozlamalar(kalit, qiymat, izoh) VALUES
  ('tolov_muddat_soat', '24',
   'Kutilayotgan to''lov necha soatdan keyin avtomatik bekor qilinadi')
ON CONFLICT (kalit) DO NOTHING;
