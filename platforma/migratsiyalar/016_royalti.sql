-- Ustozga ulush (royalti) — B2B sotuvidan twin egasiga tegadigan ulush.
--
-- NEGA HOZIR: bilim ustozniki, B2B da u qayta sotiladi. Ulush foizi
-- shartnoma masalasi va hali kelishilmagan, LEKIN hisoblash uchun kerakli
-- ma'lumot (`xarajatlar.twin_id` + `hisob_usd`) allaqachon yozilib turibdi.
-- Shuning uchun bu migratsiya XULQNI O'ZGARTIRMAYDI: standart 0%, ya'ni
-- hech kimga hech narsa hisoblanmaydi. Foiz kelishilgach admin paneldan
-- qo'yiladi va hisobot O'TGAN davrlar uchun ham to'g'ri chiqadi.
--
-- Ataylab jadval EMAS, ustun: royalti to'lovi hali yo'q, faqat HISOBOT.
-- To'lov oqimi kerak bo'lganda alohida jadval qo'shiladi.
ALTER TABLE twinlar ADD COLUMN IF NOT EXISTS royalti_foiz numeric(5,2)
  NOT NULL DEFAULT 0;

COMMENT ON COLUMN twinlar.royalti_foiz IS
  'B2B hisobidan (hisob_usd) twin egasiga tegadigan foiz. 0 = ulush yo''q.';
