-- Mentorlik rejimi: kurs xaritasi, shaxsiy o'quv reja, uy vazifalari.
-- Additiv: mavjud jadvallarga faqat ustun qo'shiladi, hech narsa o'zgarmaydi.

-- ---------------------------------------------------------------- kurs
-- Twin bilim bazasidan BIR MARTA quriladi (worker job), egasi tasdiqlaydi.
-- Versiyalanadi: bilim o'zgarsa yangi qoralama quriladi, eskisi arxivga.
CREATE TABLE IF NOT EXISTS kurslar(
  id         bigserial PRIMARY KEY,
  twin_id    bigint NOT NULL REFERENCES twinlar(id) ON DELETE CASCADE,
  versiya    int NOT NULL DEFAULT 1,
  holat      text NOT NULL DEFAULT 'qoralama',   -- qoralama|faol|arxiv
  izoh       text NOT NULL DEFAULT '',
  manba_soni int NOT NULL DEFAULT 0,             -- qurilgandagi bilim hajmi
  bolak_soni int NOT NULL DEFAULT 0,
  yaratilgan timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_kurs_twin ON kurslar(twin_id, holat);
-- Bitta twinda BITTA faol kurs (qoralama nechta bo'lsa ham mayli)
CREATE UNIQUE INDEX IF NOT EXISTS idx_kurs_faol
  ON kurslar(twin_id) WHERE holat = 'faol';

CREATE TABLE IF NOT EXISTS modullar(
  id      bigserial PRIMARY KEY,
  kurs_id bigint NOT NULL REFERENCES kurslar(id) ON DELETE CASCADE,
  nom     text NOT NULL,
  tavsif  text NOT NULL DEFAULT '',
  tartib  int NOT NULL DEFAULT 100
);
CREATE INDEX IF NOT EXISTS idx_modul_kurs ON modullar(kurs_id, tartib);

CREATE TABLE IF NOT EXISTS mavzular(
  id              bigserial PRIMARY KEY,
  modul_id        bigint NOT NULL REFERENCES modullar(id) ON DELETE CASCADE,
  nom             text NOT NULL,
  tavsif          text NOT NULL DEFAULT '',
  maqsadlar       text[] NOT NULL DEFAULT '{}',   -- o'rganish natijalari
  bolaklar        bigint[] NOT NULL DEFAULT '{}', -- bilim bo'laklari (server tekshiradi)
  savollar        jsonb NOT NULL DEFAULT '[]',    -- variantli savollar (diagnostika + mini-test)
  vazifa_shabloni jsonb NOT NULL DEFAULT '{}',    -- {topshiriq, rubrika:[...]}
  faol            boolean NOT NULL DEFAULT true,
  tartib          int NOT NULL DEFAULT 100
);
CREATE INDEX IF NOT EXISTS idx_mavzu_modul ON mavzular(modul_id, tartib);

-- ---------------------------------------------------------------- shaxsiy reja
CREATE TABLE IF NOT EXISTS oquv_reja(
  user_id      bigint NOT NULL REFERENCES userlar(id) ON DELETE CASCADE,
  twin_id      bigint NOT NULL REFERENCES twinlar(id) ON DELETE CASCADE,
  kurs_id      bigint NOT NULL REFERENCES kurslar(id) ON DELETE CASCADE,
  joriy_mavzu  bigint REFERENCES mavzular(id) ON DELETE SET NULL,
  diagnostika  jsonb NOT NULL DEFAULT '{}',       -- {mavzu_id: 0|1, ...}
  boshlangan   timestamptz NOT NULL DEFAULT now(),
  yangilangan  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(user_id, twin_id)
);
CREATE INDEX IF NOT EXISTS idx_reja_kurs ON oquv_reja(kurs_id);

CREATE TABLE IF NOT EXISTS oquv_holat(
  user_id     bigint NOT NULL REFERENCES userlar(id) ON DELETE CASCADE,
  mavzu_id    bigint NOT NULL REFERENCES mavzular(id) ON DELETE CASCADE,
  holat       text NOT NULL DEFAULT 'kutmoqda',
    -- kutmoqda | joriy | vazifada | tugallangan | otkazilgan | majburan_otildi
  test_natija jsonb NOT NULL DEFAULT '{}',
  suhbat_id   bigint REFERENCES suhbatlar(id) ON DELETE SET NULL,
  yangilangan timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(user_id, mavzu_id)
);
CREATE INDEX IF NOT EXISTS idx_oquv_holat_user ON oquv_holat(user_id, holat);

-- ---------------------------------------------------------------- vazifalar
CREATE TABLE IF NOT EXISTS vazifalar(
  id                 bigserial PRIMARY KEY,
  user_id            bigint NOT NULL REFERENCES userlar(id) ON DELETE CASCADE,
  twin_id            bigint NOT NULL REFERENCES twinlar(id) ON DELETE CASCADE,
  mavzu_id           bigint NOT NULL REFERENCES mavzular(id) ON DELETE CASCADE,
  topshiriq          text NOT NULL,
  rubrika            jsonb NOT NULL DEFAULT '[]',  -- berilgan paytda QOTIRILADI
  muddat             timestamptz,
  holat              text NOT NULL DEFAULT 'berildi',
    -- berildi | tekshirilmoqda | tekshirildi
  urinish            int NOT NULL DEFAULT 0,
  javob              text NOT NULL DEFAULT '',
  tekshiruv          jsonb NOT NULL DEFAULT '{}',  -- {xulosa, xatolar, takliflar, baho}
  baho               int,                           -- 0-100
  narx_usd           numeric(12,6) NOT NULL DEFAULT 0,
  eslatma_yuborilgan timestamptz,
  yaratilgan         timestamptz NOT NULL DEFAULT now(),
  topshirilgan       timestamptz,
  tekshirilgan       timestamptz
);
CREATE INDEX IF NOT EXISTS idx_vazifa_user ON vazifalar(user_id, holat, id);
CREATE INDEX IF NOT EXISTS idx_vazifa_mavzu ON vazifalar(user_id, mavzu_id, id);
CREATE INDEX IF NOT EXISTS idx_vazifa_muddat ON vazifalar(holat, muddat)
  WHERE holat = 'berildi';

-- ---------------------------------------------------------------- bog'lanish
-- Dars — oddiy suhbat, faqat mavzuga bog'langan (chat UI o'zgarishsiz ishlaydi).
ALTER TABLE suhbatlar ADD COLUMN IF NOT EXISTS mavzu_id bigint
  REFERENCES mavzular(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_suhbat_mavzu ON suhbatlar(user_id, mavzu_id);
