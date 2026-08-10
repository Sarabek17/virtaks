-- Fon-ishlar navbati (jobs) va loglari
CREATE TABLE IF NOT EXISTS jobs(
  id          bigserial PRIMARY KEY,
  tur         text NOT NULL,
  holat       text NOT NULL DEFAULT 'navbatda',   -- navbatda|ketmoqda|tayyor|xato
  ustunlik    int  NOT NULL DEFAULT 5,             -- kichik = muhimroq
  user_id     bigint,
  twin_id     bigint,
  kirish      jsonb NOT NULL DEFAULT '{}',
  natija      jsonb,
  xato        text,
  urinish     int NOT NULL DEFAULT 0,
  max_urinish int NOT NULL DEFAULT 3,
  muhlat_s    int NOT NULL DEFAULT 900,            -- shu vaqtdan oshsa qotgan deb qaytariladi
  keyin       timestamptz NOT NULL DEFAULT now(),  -- keyingi urinish vaqti
  yaratilgan  timestamptz NOT NULL DEFAULT now(),
  boshlangan  timestamptz,
  tugagan     timestamptz
);
CREATE INDEX IF NOT EXISTS idx_jobs_navbat
  ON jobs(holat, ustunlik, keyin) WHERE holat = 'navbatda';
CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id);

CREATE TABLE IF NOT EXISTS job_loglar(
  id     bigserial PRIMARY KEY,
  job_id bigint NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  vaqt   timestamptz NOT NULL DEFAULT now(),
  qator  text NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_job_loglar ON job_loglar(job_id, id);
