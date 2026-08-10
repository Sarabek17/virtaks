-- Manba fayllari va fragmentlar (aynan olingan qismni qaytarish)
ALTER TABLE manbalar ADD COLUMN IF NOT EXISTS asl_nom text NOT NULL DEFAULT '';
ALTER TABLE manbalar ADD COLUMN IF NOT EXISTS hajm bigint NOT NULL DEFAULT 0;
ALTER TABLE manbalar ADD COLUMN IF NOT EXISTS mime text NOT NULL DEFAULT '';
ALTER TABLE manbalar ADD COLUMN IF NOT EXISTS sahifa_soni int NOT NULL DEFAULT 0;

-- kesilgan audio / tayyorlangan rasm — bir marta yasaladi, keyin keshdan
CREATE TABLE IF NOT EXISTS fragmentlar(
  id         bigserial PRIMARY KEY,
  bolak_id   bigint NOT NULL REFERENCES bolaklar(id) ON DELETE CASCADE,
  tur        text NOT NULL,                  -- audio|rasm
  s3_yol     text NOT NULL DEFAULT '',
  holat      text NOT NULL DEFAULT 'navbatda',  -- navbatda|tayyor|xato
  xato       text NOT NULL DEFAULT '',
  davomiylik int,
  yaratilgan timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_fragment_bolak ON fragmentlar(bolak_id, tur);
