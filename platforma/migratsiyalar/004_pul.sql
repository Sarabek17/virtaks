-- 3-bosqich: pul — xarajat hisobi, planlar, obunalar, to'lovlar
--
-- XAVFSIZLIK QOIDASI (Lethal Trifecta): bu jadvallardagi hech bir qiymat
-- LLM javobidan kelmaydi va LLM promptiga kirmaydi. Xarajat faqat provayder
-- qaytargan usage_metadata dan, to'lov holati faqat imzosi tekshirilgan
-- callbackdan o'zgaradi.

-- ---------------------------------------------------------------- model narxlari
-- Kodda qattiq yozilgan narx emas — admin tahrirlaydi (narx o'zgarsa deploy shart emas).
CREATE TABLE IF NOT EXISTS model_narxlar(
  model          text PRIMARY KEY,
  kirish_1m_usd  numeric(10,4) NOT NULL DEFAULT 0,
  chiqish_1m_usd numeric(10,4) NOT NULL DEFAULT 0,
  izoh           text NOT NULL DEFAULT '',
  yangilangan    timestamptz NOT NULL DEFAULT now()
);

INSERT INTO model_narxlar(model, kirish_1m_usd, chiqish_1m_usd, izoh) VALUES
  ('gemini-3.5-flash',      0.30,  2.50, 'agent/rais/STT'),
  ('gemini-2.5-flash',      0.30,  2.50, 'OCR/agent zaxira'),
  ('gemini-2.5-pro',        1.25, 10.00, 'rais zaxira'),
  ('gemini-embedding-001',  0.15,  0.00, 'embedding (faqat kirish)')
ON CONFLICT (model) DO NOTHING;

-- ---------------------------------------------------------------- xarajat daftari
-- Har LLM/embedding chaqiruvi bitta qator. Manba: provayderning usage_metadata si.
CREATE TABLE IF NOT EXISTS xarajatlar(
  id          bigserial PRIMARY KEY,
  vaqt        timestamptz NOT NULL DEFAULT now(),
  user_id     bigint REFERENCES userlar(id) ON DELETE SET NULL,
  twin_id     bigint REFERENCES twinlar(id) ON DELETE SET NULL,
  majlis_id   bigint,
  job_id      bigint,
  bosqich     text NOT NULL DEFAULT '',     -- CEO, RAIS, stt, ocr, embedding...
  model       text NOT NULL DEFAULT '',
  kirish_tok  int  NOT NULL DEFAULT 0,
  chiqish_tok int  NOT NULL DEFAULT 0,
  narx_usd    numeric(12,6) NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_xarajat_user ON xarajatlar(user_id, vaqt DESC);
CREATE INDEX IF NOT EXISTS idx_xarajat_job  ON xarajatlar(job_id);
CREATE INDEX IF NOT EXISTS idx_xarajat_vaqt ON xarajatlar(vaqt DESC);

-- ---------------------------------------------------------------- planlar
CREATE TABLE IF NOT EXISTS planlar(
  id             bigserial PRIMARY KEY,
  kod            text NOT NULL UNIQUE,
  nom            text NOT NULL,
  tavsif         text NOT NULL DEFAULT '',
  oylik_narx_som bigint NOT NULL DEFAULT 0,        -- so'm, butun
  kvota_usd      numeric(10,4) NOT NULL DEFAULT 0, -- davr ichidagi LLM xarajat chegarasi
  kun_soni       int NOT NULL DEFAULT 30,
  twinlar        bigint[] NOT NULL DEFAULT '{}',   -- bo'sh = barcha faol twinlar
  funksiyalar    text[] NOT NULL DEFAULT '{}',
  faol           boolean NOT NULL DEFAULT false,   -- admin narxni belgilagach yoqadi
  tartib         int NOT NULL DEFAULT 100,
  yaratilgan     timestamptz NOT NULL DEFAULT now()
);

-- TAXMINIY narxlar (2026-07-30). Asos: bitta majlis o'lchangan narxi ~$0.038,
-- kvota shu xarajatni cheklaydi -> mijoz kvotani to'liq ishlatsa ham foyda qoladi
-- (bazaviy ~3.8x, pro ~2.9x; kurs taxmini 1$ ~ 13 000 so'm).
-- Yakuniy narxni biznes tomoni tasdiqlaydi — admin paneldan deploysiz o'zgaradi.
-- Mijoz baribir to'siq ko'rmaydi: `sozlamalar.kvota_faol = '0'`.
INSERT INTO planlar(kod, nom, tavsif, oylik_narx_som, kvota_usd, kun_soni, tartib, faol)
VALUES
  ('bazaviy', 'Bazaviy',
   'Kunlik ish uchun: oyiga ~80 ta savol-javob, to''liq manba isboti bilan.',
   149000, 3.0000, 30, 10, true),
  ('pro', 'Professional',
   'Faol foydalanish uchun: oyiga ~320 ta savol-javob, hajm chegarasi keng.',
   449000, 12.0000, 30, 20, true)
ON CONFLICT (kod) DO NOTHING;

-- ---------------------------------------------------------------- obunalar
CREATE TABLE IF NOT EXISTS obunalar(
  id              bigserial PRIMARY KEY,
  user_id         bigint NOT NULL REFERENCES userlar(id) ON DELETE CASCADE,
  plan_id         bigint NOT NULL REFERENCES planlar(id),
  boshlanish      timestamptz NOT NULL DEFAULT now(),
  tugash          timestamptz NOT NULL,
  holat           text NOT NULL DEFAULT 'faol',   -- faol|tugagan|bekor
  ishlatilgan_usd numeric(12,6) NOT NULL DEFAULT 0,
  eslatmalar      text[] NOT NULL DEFAULT '{}',   -- yuborilgan eslatmalar: 3kun,1kun,tugadi,kvota
  tolov_id        bigint,
  yaratilgan      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_obuna_user ON obunalar(user_id, holat);
CREATE INDEX IF NOT EXISTS idx_obuna_tugash ON obunalar(tugash) WHERE holat = 'faol';
-- Bitta userda ayni paytda faqat bitta faol obuna (ikki marta faollashtirishga to'siq)
CREATE UNIQUE INDEX IF NOT EXISTS idx_obuna_bitta_faol
  ON obunalar(user_id) WHERE holat = 'faol';

-- ---------------------------------------------------------------- to'lovlar
CREATE TABLE IF NOT EXISTS tolovlar(
  id            bigserial PRIMARY KEY,
  user_id       bigint NOT NULL REFERENCES userlar(id) ON DELETE CASCADE,
  plan_id       bigint NOT NULL REFERENCES planlar(id),
  summa_som     bigint NOT NULL,                    -- biz kutayotgan summa (so'm)
  provayder     text NOT NULL,                      -- click|payme|qolda
  provayder_id  text NOT NULL DEFAULT '',           -- click_trans_id / payme _id
  holat         text NOT NULL DEFAULT 'kutilmoqda', -- kutilmoqda|tayyorlangan|tolangan|bekor
  xom           jsonb NOT NULL DEFAULT '[]',        -- barcha xom callbacklar (audit)
  izoh          text NOT NULL DEFAULT '',
  yaratilgan    timestamptz NOT NULL DEFAULT now(),
  tolangan      timestamptz
);
CREATE INDEX IF NOT EXISTS idx_tolov_user ON tolovlar(user_id, id DESC);
-- Bitta provayder tranzaksiyasi ikki marta hisoblanmasin (idempotentlik)
CREATE UNIQUE INDEX IF NOT EXISTS idx_tolov_provayder
  ON tolovlar(provayder, provayder_id) WHERE provayder_id <> '';

-- Payme protokoli tranzaksiya holatini alohida talab qiladi (CheckTransaction, GetStatement)
CREATE TABLE IF NOT EXISTS payme_tranzaksiyalar(
  id            text PRIMARY KEY,                   -- Payme tranzaksiya id
  tolov_id      bigint NOT NULL REFERENCES tolovlar(id) ON DELETE CASCADE,
  summa_tiyin   bigint NOT NULL,
  holat         int NOT NULL DEFAULT 1,             -- 1 yaratilgan, 2 to'langan, -1/-2 bekor
  sabab         int,
  yaratilgan_ms bigint NOT NULL DEFAULT 0,
  bajarilgan_ms bigint NOT NULL DEFAULT 0,
  bekor_ms      bigint NOT NULL DEFAULT 0,
  vaqt          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_payme_tolov ON payme_tranzaksiyalar(tolov_id);

-- ---------------------------------------------------------------- bepul promptlar
ALTER TABLE userlar ADD COLUMN IF NOT EXISTS bepul_qolgan int NOT NULL DEFAULT 3;

-- ---------------------------------------------------------------- platforma sozlamalari
-- Deploysiz o'zgaradigan kalitlar (admin paneldan). LLM bu jadvalga yozmaydi.
CREATE TABLE IF NOT EXISTS sozlamalar(
  kalit       text PRIMARY KEY,
  qiymat      text NOT NULL DEFAULT '',
  izoh        text NOT NULL DEFAULT '',
  yangilangan timestamptz NOT NULL DEFAULT now()
);

-- Kvota nazorati DASTLAB O'CHIQ: narxlar biznes qarori bo'lgunga qadar hech kim
-- to'siqqa uchramasin. Xarajat baribir yozib boriladi — yoqilganda tarix tayyor.
INSERT INTO sozlamalar(kalit, qiymat, izoh) VALUES
  ('kvota_faol', '0',
   'Kvota/obuna nazorati (1=yoqilgan). Planlar narxi belgilanib, faol qilingach yoqiladi.')
ON CONFLICT (kalit) DO NOTHING;
