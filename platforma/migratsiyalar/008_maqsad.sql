-- Maqsad halqasi: foydalanuvchining bitta maqsadi bo'yicha to'liq sikl.
-- Additiv: mavjud jadvallarga faqat ustun qo'shiladi, hech narsa o'zgarmaydi.

-- ---------------------------------------------------------------- maqsad
-- Sikl: intervyu -> reja_kutilmoqda -> reja_qoralama -> faol
--       -> yakun_kutilmoqda -> tugallangan (yoki istalgan nuqtada bekor).
CREATE TABLE IF NOT EXISTS maqsadlar(
  id          bigserial PRIMARY KEY,
  user_id     bigint NOT NULL REFERENCES userlar(id) ON DELETE CASCADE,
  twin_id     bigint NOT NULL REFERENCES twinlar(id) ON DELETE CASCADE,
  sarlavha    text NOT NULL DEFAULT '',
  tafsilot    jsonb NOT NULL DEFAULT '{}',   -- {matn, olchov, muddat, motiv, boshlangich}
  tahlil      jsonb NOT NULL DEFAULT '{}',   -- {kerak:[], bor:[], yetishmaydi:[], qamrov}
  holat       text NOT NULL DEFAULT 'intervyu',
  suhbat_id   bigint REFERENCES suhbatlar(id) ON DELETE SET NULL,
  foiz        int,                           -- SERVER hisoblaydi (0-100)
  yakun       jsonb NOT NULL DEFAULT '{}',   -- {xulosa, saboqlar:[], takliflar:[]}
  narx_usd    numeric(12,6) NOT NULL DEFAULT 0,
  boshlangan  timestamptz NOT NULL DEFAULT now(),
  yangilangan timestamptz NOT NULL DEFAULT now(),
  tugallangan timestamptz,
  eslatma_yuborilgan timestamptz
);
-- FOKUS QOIDASI (metodikaning o'zagi): bitta user+twin'da BITTA tugallanmagan
-- maqsad. Yangi maqsadga sakrash shu index tufayli texnik jihatdan imkonsiz —
-- API tekshiruvi emas, baza kafolati.
CREATE UNIQUE INDEX IF NOT EXISTS idx_maqsad_fokus
  ON maqsadlar(user_id, twin_id)
  WHERE holat NOT IN ('tugallangan', 'bekor');
CREATE INDEX IF NOT EXISTS idx_maqsad_user ON maqsadlar(user_id, twin_id, id);
CREATE INDEX IF NOT EXISTS idx_maqsad_holat ON maqsadlar(holat, yangilangan);

-- ---------------------------------------------------------------- qadamlar
CREATE TABLE IF NOT EXISTS maqsad_qadamlar(
  id           bigserial PRIMARY KEY,
  maqsad_id    bigint NOT NULL REFERENCES maqsadlar(id) ON DELETE CASCADE,
  nom          text NOT NULL,
  nima_uchun   text NOT NULL DEFAULT '',     -- bu qadam maqsadga nima beradi
  mezon        text NOT NULL DEFAULT '',     -- "tayyor" mezoni
  metodika     text NOT NULL DEFAULT '',     -- BTM halqasi tegi (oq ro'yxat, 10 ta)
  bolaklar     bigint[] NOT NULL DEFAULT '{}',  -- grounding (faqat qidiruvdan)
  umumiy       boolean NOT NULL DEFAULT false,  -- bilim yetmadi: "umumiy tavsiya"
  holat        text NOT NULL DEFAULT 'kutmoqda',
    -- kutmoqda | joriy | bajarildi | otkazildi
  dalil        text NOT NULL DEFAULT '',     -- foydalanuvchi yozgan natija
  muddat_kun   int NOT NULL DEFAULT 3,
  muddat       date,
  tartib       int NOT NULL DEFAULT 100,
  bajarilgan   timestamptz,
  eslatma_yuborilgan timestamptz
);
CREATE INDEX IF NOT EXISTS idx_qadam_maqsad
  ON maqsad_qadamlar(maqsad_id, tartib, id);
CREATE INDEX IF NOT EXISTS idx_qadam_muddat
  ON maqsad_qadamlar(holat, muddat) WHERE holat = 'joriy';

-- ---------------------------------------------------------------- bog'lanish
-- Maqsad suhbati — oddiy suhbat, faqat maqsadga bog'langan (mentor naqshi):
-- chat UI, tarix, iqtiboslar va "to'xtatish" o'zgarishsiz ishlaydi.
ALTER TABLE suhbatlar ADD COLUMN IF NOT EXISTS maqsad_id bigint
  REFERENCES maqsadlar(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_suhbat_maqsad ON suhbatlar(user_id, maqsad_id);
