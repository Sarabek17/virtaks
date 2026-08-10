-- Yadro sxemasi: odamlar, twinlar, direktorlar, bilim, suhbatlar
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------- odamlar
CREATE TABLE IF NOT EXISTS userlar(
  id            bigserial PRIMARY KEY,
  tg_id         bigint UNIQUE,
  ism           text NOT NULL DEFAULT 'Foydalanuvchi',
  familiya      text NOT NULL DEFAULT '',
  username      text NOT NULL DEFAULT '',
  telefon       text NOT NULL DEFAULT '',
  foto          text NOT NULL DEFAULT '',
  rol           text NOT NULL DEFAULT 'client',   -- client|egasi|admin
  parol_hash    text,                              -- egasi/admin uchun (TG'siz kirish)
  login         text UNIQUE,                       -- egasi/admin login
  profil        text NOT NULL DEFAULT '',          -- o'rganilgan profil (matn)
  profil_jsonb  jsonb NOT NULL DEFAULT '{}',       -- tuzilgan profil (4-bosqich)
  profil_tarix  jsonb NOT NULL DEFAULT '[]',       -- dinamika
  joriy_twin    bigint,                            -- oxirgi tanlangan twin
  bloklangan    boolean NOT NULL DEFAULT false,
  yaratilgan    timestamptz NOT NULL DEFAULT now(),
  oxirgi_kirish timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessiyalar(
  token           text PRIMARY KEY,
  user_id         bigint NOT NULL REFERENCES userlar(id) ON DELETE CASCADE,
  impersonator_id bigint REFERENCES userlar(id) ON DELETE SET NULL,  -- admin kirgan bo'lsa
  yaratilgan      timestamptz NOT NULL DEFAULT now(),
  muddat          timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessiya_user ON sessiyalar(user_id);

-- ---------------------------------------------------------------- twinlar
CREATE TABLE IF NOT EXISTS kategoriyalar(
  id     bigserial PRIMARY KEY,
  nom    text NOT NULL UNIQUE,
  izoh   text NOT NULL DEFAULT '',
  tartib int NOT NULL DEFAULT 100
);

CREATE TABLE IF NOT EXISTS twinlar(
  id           bigserial PRIMARY KEY,
  nom          text NOT NULL,
  slug         text NOT NULL UNIQUE,
  kategoriya_id bigint REFERENCES kategoriyalar(id) ON DELETE SET NULL,
  egasi_id     bigint REFERENCES userlar(id) ON DELETE SET NULL,
  tavsif       text NOT NULL DEFAULT '',
  xulq         text NOT NULL DEFAULT '',      -- xarakter/uslub (egasi yoki admin yozadi)
  uslub        jsonb NOT NULL DEFAULT '{}',   -- {hazil: 2, chuqurlik: 4, ...}
  avatar       text NOT NULL DEFAULT '',
  faol         boolean NOT NULL DEFAULT true,
  tartib       int NOT NULL DEFAULT 100,
  yaratilgan   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_twin_egasi ON twinlar(egasi_id);

-- qaysi twin qaysi twinning bilimidan foydalana oladi (admin boshqaradi)
CREATE TABLE IF NOT EXISTS twin_ruxsat(
  twin_id       bigint NOT NULL REFERENCES twinlar(id) ON DELETE CASCADE,
  manba_twin_id bigint NOT NULL REFERENCES twinlar(id) ON DELETE CASCADE,
  PRIMARY KEY(twin_id, manba_twin_id)
);

-- ---------------------------------------------------------------- direktorlar (admin CRUD)
CREATE TABLE IF NOT EXISTS direktorlar(
  id       bigserial PRIMARY KEY,
  kod      text NOT NULL,                    -- CEO, CFO... (hisobot sarlavhasi)
  nom      text NOT NULL,                    -- "Bosh moliya direktori"
  persona  text NOT NULL,                    -- to'liq prompt (qanday fikrlaydi)
  teglar   text[] NOT NULL DEFAULT '{umumiy}',
  rang     text NOT NULL DEFAULT '#5b8cff',
  twin_id  bigint REFERENCES twinlar(id) ON DELETE CASCADE,  -- NULL = barcha twinlar
  rais     boolean NOT NULL DEFAULT false,   -- true = sintez qiluvchi (RAIS)
  faol     boolean NOT NULL DEFAULT true,
  tartib   int NOT NULL DEFAULT 100
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_direktor_kod
  ON direktorlar(kod, COALESCE(twin_id, 0));

CREATE TABLE IF NOT EXISTS twin_skilllar(
  twin_id  bigint NOT NULL REFERENCES twinlar(id) ON DELETE CASCADE,
  skill    text NOT NULL,                    -- shablon_fayl|diagramma|...
  faol     boolean NOT NULL DEFAULT true,
  sozlama  jsonb NOT NULL DEFAULT '{}',
  PRIMARY KEY(twin_id, skill)
);

CREATE TABLE IF NOT EXISTS shablonlar(
  id        bigserial PRIMARY KEY,
  nom       text NOT NULL,
  s3_yol    text NOT NULL,
  tur       text NOT NULL DEFAULT 'xlsx',
  twin_id   bigint REFERENCES twinlar(id) ON DELETE CASCADE,  -- NULL = umumiy
  izoh      text NOT NULL DEFAULT '',
  faol      boolean NOT NULL DEFAULT true,
  yaratilgan timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- bilim
CREATE TABLE IF NOT EXISTS manbalar(
  id          bigserial PRIMARY KEY,
  twin_id     bigint NOT NULL REFERENCES twinlar(id) ON DELETE CASCADE,
  nom         text NOT NULL,
  tur         text NOT NULL,                 -- audio|slayd|jadval|hujjat|web
  s3_yol      text NOT NULL DEFAULT '',      -- asl fayl (audio/pdf/pptx)
  manba_url   text NOT NULL DEFAULT '',      -- web bo'lsa
  papka       text NOT NULL DEFAULT '',
  holat       text NOT NULL DEFAULT 'navbatda',  -- navbatda|ishlanmoqda|tayyor|xato
  xato        text NOT NULL DEFAULT '',
  bolak_soni  int NOT NULL DEFAULT 0,
  davomiylik  int,                            -- audio soniya
  yuklagan_id bigint REFERENCES userlar(id) ON DELETE SET NULL,
  yaratilgan  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_manba_twin ON manbalar(twin_id);

CREATE TABLE IF NOT EXISTS bolaklar(
  id          bigserial PRIMARY KEY,
  manba_id    bigint NOT NULL REFERENCES manbalar(id) ON DELETE CASCADE,
  twin_id     bigint NOT NULL REFERENCES twinlar(id) ON DELETE CASCADE,
  tartib      int NOT NULL DEFAULT 0,
  matn        text NOT NULL,
  joy         text NOT NULL DEFAULT '',      -- "[0:34:12–0:39:45]" yoki "8-slayd"
  teglar      text[] NOT NULL DEFAULT '{umumiy}',
  embedding   vector(3072),
  -- aynan olingan qismni qaytarish uchun (2-bosqich)
  sahifa_png  text NOT NULL DEFAULT '',      -- s3 yo'l (slayd rasmi)
  audio_bosh  int,                            -- soniya
  audio_oxir  int,
  eski_id     text                            -- migratsiya uchun (kanonik id)
);
CREATE INDEX IF NOT EXISTS idx_bolak_twin ON bolaklar(twin_id);
CREATE INDEX IF NOT EXISTS idx_bolak_manba ON bolaklar(manba_id);
CREATE INDEX IF NOT EXISTS idx_bolak_teglar ON bolaklar USING gin(teglar);
-- 3072-dim: HNSW to'g'ridan-to'g'ri 2000 dim gacha; halfvec ifodasi bilan 4000 gacha
CREATE INDEX IF NOT EXISTS idx_bolak_vektor
  ON bolaklar USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops);

-- ---------------------------------------------------------------- suhbatlar
CREATE TABLE IF NOT EXISTS suhbatlar(
  id         bigserial PRIMARY KEY,
  user_id    bigint NOT NULL REFERENCES userlar(id) ON DELETE CASCADE,
  twin_id    bigint REFERENCES twinlar(id) ON DELETE SET NULL,
  sarlavha   text NOT NULL DEFAULT '',
  yaratilgan timestamptz NOT NULL DEFAULT now(),
  yangilangan timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_suhbat_user ON suhbatlar(user_id, yangilangan);

CREATE TABLE IF NOT EXISTS majlislar(
  id           bigserial PRIMARY KEY,
  suhbat_id    bigint REFERENCES suhbatlar(id) ON DELETE CASCADE,
  user_id      bigint NOT NULL REFERENCES userlar(id) ON DELETE CASCADE,
  twin_id      bigint REFERENCES twinlar(id) ON DELETE SET NULL,
  job_id       bigint,
  savol        text NOT NULL,
  savol_mustaqil text NOT NULL DEFAULT '',
  xulosa       text NOT NULL DEFAULT '',      -- RAIS xulosasi (markdown)
  hisobot      jsonb NOT NULL DEFAULT '{}',   -- {direktorlar:[...], manbalar:[...]}
  biriktirma   text NOT NULL DEFAULT '',      -- s3 yo'l (to'ldirilgan shablon)
  davomiylik   int,
  narx_usd     numeric(12,6) NOT NULL DEFAULT 0,
  vaqt         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_majlis_suhbat ON majlislar(suhbat_id, id);
CREATE INDEX IF NOT EXISTS idx_majlis_user ON majlislar(user_id, id);
