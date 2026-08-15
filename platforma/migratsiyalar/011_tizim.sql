-- Tizimlashtirish halqasi (biznes): diagnostika -> SMART maqsad -> bo'lim rejalari.
--
-- Manba: ustozning ovozli tushuntirishi (2026-08-14) va ikkita diagnostika
-- quroli — CJM (mijoz yo'li, 560 savol) va EJM (xodim yo'li, 366 savol).
--
-- TO'LIQ ADDITIV: faqat yangi jadval. Mavjud `maqsadlar` jadvaliga TEGILMAYDI —
-- undagi `idx_maqsad_fokus` unikal indeksi "bitta user+twin = bitta ochiq
-- maqsad" deydi. Biznes maqsadi o'sha jadvalga yozilsa, shaxsiy maqsad halqasi
-- (11-bosqich, jonli) bloklanib qolardi. Shuning uchun biznes halqasi o'z
-- jadvallarida yashaydi.

-- ---------------------------------------------------------------- savol banki
-- 926 savol. Matn QOTIRILGAN: savol tahrirlansa `versiya` oshadi va eski
-- diagnostika eski versiyaga bog'liq qoladi — aks holda o'tkazilgan
-- diagnostikaning foizi keyinchalik o'z-o'zidan "o'zgarib" ketardi.
CREATE TABLE IF NOT EXISTS diag_savollar(
  id       bigserial PRIMARY KEY,
  tur      text NOT NULL,              -- 'cjm' | 'ejm'
  bosqich  text NOT NULL,              -- 'Tanilish', 'Sotuv', ...
  blok     text NOT NULL,              -- 'INSTAGRAM', 'CRM', ...
  tartib   int  NOT NULL,              -- blok ichidagi tartib raqami
  matn     text NOT NULL,
  versiya  int  NOT NULL DEFAULT 1,
  ixtiyoriy boolean NOT NULL DEFAULT false,  -- masalan CJM "Muhit" (onlayn biznes)
  UNIQUE (tur, versiya, bosqich, blok, tartib)
);
CREATE INDEX IF NOT EXISTS idx_savol_tur
  ON diag_savollar(tur, versiya, bosqich, blok, tartib);

-- ---------------------------------------------------------------- diagnostika
CREATE TABLE IF NOT EXISTS diagnostikalar(
  id       bigserial PRIMARY KEY,
  user_id  bigint NOT NULL REFERENCES userlar(id) ON DELETE CASCADE,
  twin_id  bigint NOT NULL REFERENCES twinlar(id) ON DELETE CASCADE,
  korxona  text NOT NULL DEFAULT '',
  tur      text NOT NULL,                    -- 'cjm' | 'ejm'
  versiya  int  NOT NULL DEFAULT 1,          -- savol banki versiyasi (muzlatilgan)
  onlayn   boolean NOT NULL DEFAULT false,   -- true -> ixtiyoriy bloklar chiqmaydi
  holat    text NOT NULL DEFAULT 'toldirilmoqda',
    -- toldirilmoqda | xulosa_kutilmoqda | tayyor | bekor
  foiz         int,                            -- SERVER hisoblaydi (0-100)
  foiz_bosqich jsonb NOT NULL DEFAULT '{}',    -- {"Tanilish": 42, ...}
  sifat_ortacha numeric(4,2),                  -- "Ha" javoblar sifati (1-3)
  xulosa       jsonb NOT NULL DEFAULT '{}',    -- {matn, zaif:[], ogriqli:[]}
  narx_usd     numeric(12,6) NOT NULL DEFAULT 0,
  boshlangan   timestamptz NOT NULL DEFAULT now(),
  yangilangan  timestamptz NOT NULL DEFAULT now(),
  tugallangan  timestamptz
);
-- Fokus qoidasi: bitta user+twin+tur bo'yicha bitta tugallanmagan diagnostika.
-- API tekshiruvi emas — baza kafolati (maqsad halqasidagi naqsh).
CREATE UNIQUE INDEX IF NOT EXISTS idx_diag_fokus
  ON diagnostikalar(user_id, twin_id, tur)
  WHERE holat NOT IN ('tayyor', 'bekor');
CREATE INDEX IF NOT EXISTS idx_diag_user
  ON diagnostikalar(user_id, twin_id, id DESC);

CREATE TABLE IF NOT EXISTS diag_javoblar(
  diagnostika_id bigint NOT NULL REFERENCES diagnostikalar(id) ON DELETE CASCADE,
  savol_id       bigint NOT NULL REFERENCES diag_savollar(id),
  javob          text NOT NULL,          -- 'ha' | 'yoq' | 'qisman'
  sifat          int,                    -- 1-3, faqat javob='ha' bo'lganda
  izoh           text NOT NULL DEFAULT '',
  yangilangan    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (diagnostika_id, savol_id),
  CONSTRAINT javob_kodi CHECK (javob IN ('ha', 'yoq', 'qisman')),
  CONSTRAINT sifat_oraliq CHECK (sifat IS NULL OR sifat BETWEEN 1 AND 3)
);
CREATE INDEX IF NOT EXISTS idx_javob_diag ON diag_javoblar(diagnostika_id);

-- ---------------------------------------------------------------- SMART maqsad
-- Biznes maqsadi. Shaxsiy `maqsadlar` jadvalidan MUSTAQIL.
CREATE TABLE IF NOT EXISTS tizim_maqsadlar(
  id       bigserial PRIMARY KEY,
  user_id  bigint NOT NULL REFERENCES userlar(id) ON DELETE CASCADE,
  twin_id  bigint NOT NULL REFERENCES twinlar(id) ON DELETE CASCADE,
  diagnostika_id bigint REFERENCES diagnostikalar(id) ON DELETE SET NULL,
  korxona  text NOT NULL DEFAULT '',
  sarlavha text NOT NULL DEFAULT '',
  tafsilot jsonb NOT NULL DEFAULT '{}',
    -- {matn, olchov:{birlik,qiymat,hozir}, muddat, byudjet, resurs, ahamiyat}
  smart    jsonb NOT NULL DEFAULT '{}',
    -- SERVER bahosi: {aniq:{ok,izoh}, olchov:{...}, erishsa:{...},
    --                 ahamiyat:{...}, muddat:{...}}
  holat    text NOT NULL DEFAULT 'intervyu',
    -- intervyu | tekshirildi | faol | tugallangan | bekor
  suhbat_id bigint REFERENCES suhbatlar(id) ON DELETE SET NULL,
  narx_usd numeric(12,6) NOT NULL DEFAULT 0,
  boshlangan  timestamptz NOT NULL DEFAULT now(),
  yangilangan timestamptz NOT NULL DEFAULT now(),
  tugallangan timestamptz
);
-- Fokus: bitta user+twin da bitta ochiq biznes maqsadi.
CREATE UNIQUE INDEX IF NOT EXISTS idx_tizim_maqsad_fokus
  ON tizim_maqsadlar(user_id, twin_id)
  WHERE holat NOT IN ('tugallangan', 'bekor');

-- Biznes maqsadi suhbati — oddiy suhbat, faqat maqsadga bog'langan
-- (mentor/maqsad naqshi: chat UI, tarix, iqtiboslar o'zgarishsiz ishlaydi).
ALTER TABLE suhbatlar ADD COLUMN IF NOT EXISTS tizim_maqsad_id bigint
  REFERENCES tizim_maqsadlar(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_suhbat_tizim
  ON suhbatlar(user_id, tizim_maqsad_id);

-- ---------------------------------------------------------------- bo'lim rejalari
-- Har qurol — bitta qator; jadval qatorlari jsonb ichida (shakli qurolga
-- qarab farq qiladi, server sxema bo'yicha tekshiradi va yig'indini O'ZI
-- hisoblaydi — model raqam yig'masin).
CREATE TABLE IF NOT EXISTS bolim_rejalar(
  id        bigserial PRIMARY KEY,
  maqsad_id bigint NOT NULL REFERENCES tizim_maqsadlar(id) ON DELETE CASCADE,
  bolim     text NOT NULL,   -- sotuv|marketing|moliya|hr|boshqaruv|produkt
  tur       text NOT NULL,   -- ssp|mediaplan|moliya_model|hr_reja|gantt|roadmap
  sarlavha  text NOT NULL DEFAULT '',
  izoh      text NOT NULL DEFAULT '',
  jadval    jsonb NOT NULL DEFAULT '[]',
  jami      jsonb NOT NULL DEFAULT '{}',     -- SERVER hisoblagan yig'indilar
  bolaklar  bigint[] NOT NULL DEFAULT '{}',  -- grounding (faqat qidiruvdan)
  umumiy    boolean NOT NULL DEFAULT false,  -- bilim yetmadi -> ochiq yorliq
  holat     text NOT NULL DEFAULT 'qoralama',  -- qoralama | tasdiqlangan
  yaratilgan  timestamptz NOT NULL DEFAULT now(),
  yangilangan timestamptz NOT NULL DEFAULT now(),
  UNIQUE (maqsad_id, bolim, tur)
);
CREATE INDEX IF NOT EXISTS idx_reja_maqsad ON bolim_rejalar(maqsad_id, bolim);
