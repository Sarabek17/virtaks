-- 13-bosqich: B2B API — tashkilot izolyatsiyasi va tashkilot bo'yicha hisob.
-- Reja: B2B_API_REJA.md
--
-- XAVFSIZLIK QOIDASI (Lethal Trifecta): bu jadvallardagi hech bir qiymat LLM
-- javobidan kelmaydi va LLM promptiga kirmaydi. Balans faqat `balans_harakat`
-- daftari orqali o'zgaradi, hisob esa faqat provayder qaytargan
-- usage_metadata dan hisoblanadi.
--
-- Migratsiya ADDITIV: `tashkilot_id IS NULL` bo'lgan mavjud B2C oqimi
-- bugungidek ishlaydi, bitta ham so'rov o'zgarmaydi.

-- ------------------------------------------------------------ tashkilotlar
-- Bitta B2B hamkor = bitta qator.
CREATE TABLE IF NOT EXISTS tashkilotlar(
  id                  bigserial PRIMARY KEY,
  nom                 text NOT NULL,
  slug                text NOT NULL UNIQUE,
  aloqa_email         text NOT NULL DEFAULT '',
  aloqa_tg            bigint,                                 -- ogohlantirishlar

  -- pul
  -- Tannarxga koeffitsient. Hamkordan olinadigan summa = narx_usd * ustama.
  -- Qiymat sarf yozilayotgan paytda `xarajatlar.hisob_usd` ga QOTIRILADI —
  -- shartnoma o'zgarsa o'tgan oyning hisobi o'zgarib ketmasin.
  ustama              numeric(6,3)  NOT NULL DEFAULT 3.000,
  balans_usd          numeric(14,6) NOT NULL DEFAULT 0,
  -- Postpaid hamkor uchun: balans shu qiymatgacha minusga tushishi mumkin.
  -- Standart 0 = qat'iy prepaid.
  kredit_chegara_usd  numeric(14,6) NOT NULL DEFAULT 0,
  ogohlantirish_usd   numeric(14,6) NOT NULL DEFAULT 5,

  -- cheklovlar
  oqim_limit          int NOT NULL DEFAULT 5,     -- bir vaqtda ochiq SSE oqim
  daqiqa_limit        int NOT NULL DEFAULT 60,    -- daqiqasiga so'rov
  oylik_chegara_usd   numeric(14,6) NOT NULL DEFAULT 0,  -- 0 = cheksiz

  faol                boolean NOT NULL DEFAULT true,
  izoh                text NOT NULL DEFAULT '',
  yaratilgan          timestamptz NOT NULL DEFAULT now()
);

-- --------------------------------------------------------------- kalitlar
-- Kalitning O'ZI saqlanmaydi: faqat prefiks (indeks bo'yicha topish uchun)
-- va sirning argon2 xeshi. Kalit bir marta ko'rsatiladi, keyin qayta
-- ko'rsatib bo'lmaydi — o'g'irlangan baza kalitlarni bermaydi.
CREATE TABLE IF NOT EXISTS api_kalitlar(
  id            bigserial PRIMARY KEY,
  tashkilot_id  bigint NOT NULL REFERENCES tashkilotlar(id) ON DELETE CASCADE,
  nom           text NOT NULL DEFAULT '',         -- "prod", "sinov", "mobil"
  prefiks       text NOT NULL UNIQUE,             -- vk_live_7f3a2c
  hash          text NOT NULL,                    -- argon2(sir)
  huquqlar      text[] NOT NULL DEFAULT '{savol,suhbat,fragment,hisob}',
  ip_oq         text[] NOT NULL DEFAULT '{}',     -- bo'sh = filtr o'chiq
  faol          boolean NOT NULL DEFAULT true,
  muddat        timestamptz,                      -- NULL = muddatsiz
  oxirgi_ishlatilgan timestamptz,
  yaratilgan    timestamptz NOT NULL DEFAULT now(),
  yaratgan_id   bigint REFERENCES userlar(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_kalit_tashkilot
  ON api_kalitlar(tashkilot_id, faol);

-- ------------------------------------------------------ tashkilot -> twin
-- Hamkor twinni O'ZI TANLAMAYDI. Bu ro'yxatda yo'q twin API uchun umuman
-- mavjud emas (404). `twin_ruxsat` ni ALMASHTIRMAYDI — ustiga qo'shiladi.
CREATE TABLE IF NOT EXISTS tashkilot_twin(
  tashkilot_id bigint NOT NULL REFERENCES tashkilotlar(id) ON DELETE CASCADE,
  twin_id      bigint NOT NULL REFERENCES twinlar(id) ON DELETE CASCADE,
  faol         boolean NOT NULL DEFAULT true,
  PRIMARY KEY (tashkilot_id, twin_id)
);

-- --------------------------------------------- userlar: soya foydalanuvchi
-- Hamkorning mijozi ALOHIDA jadvalga emas, shu yerga tushadi: suhbat,
-- iqtibos, profil — hammasi `user_id` ga bog'langan, ikkinchi foydalanuvchi
-- turi butun kodni ikkiga bo'lardi.
ALTER TABLE userlar ADD COLUMN IF NOT EXISTS tashkilot_id bigint
  REFERENCES tashkilotlar(id) ON DELETE CASCADE;
ALTER TABLE userlar ADD COLUMN IF NOT EXISTS tashqi_id text NOT NULL DEFAULT '';
-- `manba` ustuni 006_chat.sql da bor (tg|web|admin). B2B mijozlariga
-- 'api' qiymati yoziladi — yangi ustun kerak emas.
-- Hamkorning bitta mijozi = bitta qator. API tekshiruvi emas, INDEKS:
-- parallel so'rov ham ikkinchi yozuvni ocholmaydi (idx_maqsad_fokus naqshi).
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_tashqi
  ON userlar(tashkilot_id, tashqi_id) WHERE tashkilot_id IS NOT NULL;

-- --------------------------------------------------------- xarajat ustuni
ALTER TABLE xarajatlar ADD COLUMN IF NOT EXISTS tashkilot_id bigint
  REFERENCES tashkilotlar(id) ON DELETE SET NULL;
-- Hamkordan olinadigan summa. `narx_usd` (tannarx) hamkorga HECH QACHON
-- ko'rsatilmaydi — bu marja siri.
ALTER TABLE xarajatlar ADD COLUMN IF NOT EXISTS hisob_usd numeric(12,6)
  NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_xarajat_tashkilot
  ON xarajatlar(tashkilot_id, vaqt DESC) WHERE tashkilot_id IS NOT NULL;

-- Worker jobi ham tashkilotga tegishli bo'lishi mumkin (fragment, ingest).
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS tashkilot_id bigint
  REFERENCES tashkilotlar(id) ON DELETE SET NULL;

-- ----------------------------------------------------- balans harakatlari
-- Balans HECH QACHON to'g'ridan-to'g'ri UPDATE qilinmaydi — faqat shu daftar
-- orqali, `qoldiq_usd` bilan. Shunda "pul qayerga ketdi?" savoliga har doim
-- javob bor va hisob-fakturani qayta hisoblash shart emas.
CREATE TABLE IF NOT EXISTS balans_harakat(
  id           bigserial PRIMARY KEY,
  tashkilot_id bigint NOT NULL REFERENCES tashkilotlar(id) ON DELETE CASCADE,
  vaqt         timestamptz NOT NULL DEFAULT now(),
  tur          text NOT NULL,               -- toldirish|sarf|tuzatish|qaytarish
  summa_usd    numeric(14,6) NOT NULL,      -- + to'ldirish, - sarf
  qoldiq_usd   numeric(14,6) NOT NULL,      -- harakatdan keyingi balans
  xarajat_id   bigint REFERENCES xarajatlar(id) ON DELETE SET NULL,
  izoh         text NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_balans_tashkilot
  ON balans_harakat(tashkilot_id, id DESC);

-- ---------------------------------------------------------- idempotentlik
-- Hamkor tarmoq uzilganda so'rovni takrorlaydi — ikki marta pul olmaymiz va
-- ikki marta javob yozmaymiz.
CREATE TABLE IF NOT EXISTS api_idempotent(
  tashkilot_id bigint NOT NULL REFERENCES tashkilotlar(id) ON DELETE CASCADE,
  kalit        text NOT NULL,
  javob        jsonb NOT NULL DEFAULT '{}',
  holat        int NOT NULL DEFAULT 200,
  vaqt         timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tashkilot_id, kalit)
);
CREATE INDEX IF NOT EXISTS idx_idempotent_vaqt ON api_idempotent(vaqt);
