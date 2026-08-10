-- Chat v2: yagona yordamchi rejimi + web (email) ro'yxatdan o'tish
--
-- `majlislar` jadvali nomi tarixiy (eski "direktorlar majlisi" rejimidan) —
-- endi u CHAT NAVBATINI saqlaydi: har qator = bitta savol-javob. `rejim`
-- ustuni qaysi dvigatel javob berganini ko'rsatadi:
--   'yordamchi' — yangi standart: bitta model, oqim bilan (Claude uslubi)
--   'kengash'   — eski direktorlar quvuri (ixtiyoriy "chuqur tahlil")

ALTER TABLE majlislar ADD COLUMN IF NOT EXISTS rejim text NOT NULL DEFAULT 'kengash';
ALTER TABLE majlislar ADD COLUMN IF NOT EXISTS toxtatildi boolean NOT NULL DEFAULT false;
ALTER TABLE majlislar ADD COLUMN IF NOT EXISTS tugallandi boolean NOT NULL DEFAULT true;

-- Eski qatorlar aynan eski rejimda yaratilgan — standart qiymat to'g'ri.
-- Yangi chat qatorlari 'yordamchi' bilan yoziladi.

-- ---------------------------------------------------------------- web kirish
-- Klientlar endi Telegramsiz ham kira oladi: email + parol.
-- `login` ustuni egasi/admin uchun qoladi; email alohida (ikkisi chalkashmasin).
ALTER TABLE userlar ADD COLUMN IF NOT EXISTS email text;
ALTER TABLE userlar ADD COLUMN IF NOT EXISTS email_tasdiq boolean NOT NULL DEFAULT false;
ALTER TABLE userlar ADD COLUMN IF NOT EXISTS manba text NOT NULL DEFAULT '';  -- tg|web|admin

-- Email noyob bo'lsin, lekin NULL lar cheklanmaydi (TG userlarida email yo'q).
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_email ON userlar(lower(email))
  WHERE email IS NOT NULL;

-- Tasdiqlash va parol tiklash tokenlari. Bir martalik, muddatli.
CREATE TABLE IF NOT EXISTS email_tokenlar(
  token      text PRIMARY KEY,
  user_id    bigint NOT NULL REFERENCES userlar(id) ON DELETE CASCADE,
  tur        text NOT NULL,                      -- tasdiq|tiklash
  muddat     timestamptz NOT NULL,
  ishlatilgan timestamptz,
  yaratilgan timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_token_user ON email_tokenlar(user_id, tur);

-- Suhbatni arxivlash (Claude uslubidagi "o'chirish" — qaytarib bo'ladigan)
ALTER TABLE suhbatlar ADD COLUMN IF NOT EXISTS arxiv boolean NOT NULL DEFAULT false;

-- Chat navbatini suhbat bo'yicha tez o'qish uchun
CREATE INDEX IF NOT EXISTS idx_majlis_rejim ON majlislar(user_id, rejim, id);
