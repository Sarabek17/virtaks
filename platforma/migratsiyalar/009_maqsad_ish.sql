-- Qadam ichidagi ANIQ ISHLAR (checklist).
--
-- Qadam — bu yirik bo'lak ("CRM joriy qilish", 10 kun). Foydalanuvchi uni
-- ertaga nimadan boshlashini bilishi uchun har qadam bir o'tirishda
-- bajariladigan aniq ishlarga bo'linadi. Ishlar reja qurilayotganda
-- (`maqsad_reja` jobi) bitta LLM chaqiruvida qadam bilan birga chiqadi —
-- qo'shimcha xarajat yo'q.
--
-- Belgilashni FAQAT foydalanuvchi qiladi (model emas) — qolgan hamma joydagi
-- kabi: holat serverda, kontent modelda.
CREATE TABLE IF NOT EXISTS maqsad_ishlar(
  id         bigserial PRIMARY KEY,
  qadam_id   bigint NOT NULL REFERENCES maqsad_qadamlar(id) ON DELETE CASCADE,
  matn       text NOT NULL,                   -- fe'l bilan boshlanadigan aniq ish
  izoh       text NOT NULL DEFAULT '',        -- qanday qilinadi / nimaga e'tibor
  bajarildi  boolean NOT NULL DEFAULT false,
  ozim       boolean NOT NULL DEFAULT false,  -- foydalanuvchi o'zi qo'shgan
  tartib     int NOT NULL DEFAULT 100,
  bajarilgan timestamptz,
  yaratilgan timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ish_qadam
  ON maqsad_ishlar(qadam_id, tartib, id);
