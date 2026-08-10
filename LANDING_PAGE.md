# LANDING PAGE — to'liq kontent va tuzilma rejasi
*(Digital Twin platformasi uchun, 2026-07-29)*

Bu hujjat: landing page'da **nima bo'lishi**, **qanday tartibda**, **qanday matn bilan** va
**qaysi tugma qayerga olib borishi** — to'liq yozilgan. Dizayner/frontend shu hujjatdan
to'g'ridan-to'g'ri ishlay oladi.

---

## 0. LANDING NIMA UCHUN KERAK (maqsad)

Bitta asosiy maqsad: **notanish odam 60 soniyada tushunsin va Telegram botga o'tsin.**

| Maqsad | O'lchov (KPI) |
|---|---|
| Asosiy konversiya | "Telegramda boshlash" bosilishi → bot `/start` |
| Ikkilamchi konversiya | Ekspert/kompaniya "O'z twiningizni yarating" → ariza formasi |
| Ishonch | Demo videoni oxirigacha ko'rish, "manba isboti" blokida o'ynatish |
| Ushlab qolish | Narx bo'limigacha scroll (>50%) |

**Auditoriya 3 xil, sahifada 3 tasiga ham javob bo'lishi shart:**
1. **Oddiy foydalanuvchi** (tadbirkor, o'quvchi) — "menga savolimga ustoz darajasida javob kerak".
2. **Ekspert / ustoz / murabbiy** — "mening bilimim 24/7 ishlasin va daromad keltirsin".
3. **Kompaniya / bo'lim rahbari** — "kompaniya bilimini bir joyga yig'ay, xodimlar undan so'rasin".

---

## 1. POZITSIYA VA ASOSIY VA'DA (hero matni)

**Bir jumlali ta'rif (tanlash uchun variantlar):**

- A) *"Ekspert bilimini raqamli egizakka aylantiramiz — u sizga 24/7, aynan manbaga tayanib javob beradi."*
- B) *"Sizning savolingizga bitta AI emas, butun boshqaruv kengashi javob beradi — har biri o'z yo'nalishi bo'yicha."*
- C) *"Ustozning javobi, ustozning ovozi bilan isbotlangan holda."* ← **tavsiya**: eng kuchli farqimiz shu

**Sub-sarlavha (hero ostida, 2 qator):**
> Audio darslar, kitoblar, shablonlar va hujjatlardan raqamli egizak quramiz.
> Har bir javob manbadan olinadi — dars yozuvining aynan o'sha daqiqasini eshitasiz.

**Hero CTA:**
- Birlamchi tugma: **"Telegramda bepul sinash"** → `https://t.me/<bot_username>?start=landing`
- Ikkilamchi tugma: **"Qanday ishlaydi — 90 soniya"** → demo video modal
- Tugma ostida mayda yozuv: *"Ro'yxatdan o'tish shart emas — 3 ta savol bepul."*

**Hero vizuali:** telefon mockup — chapda foydalanuvchi savoli, o'ngda javob va uning
ichida ✅ manba karta (audio player + "05:12–07:40" + slayd rasm). Statik rasm emas,
2-3 soniyalik loop animatsiya bo'lsa yaxshi.

---

## 2. SAHIFA TUZILMASI (bloklar ketma-ketligi)

Tartib ataylab shunday: **va'da → isbot → qanday ishlaydi → kimga → imkoniyatlar →
ishonch → narx → FAQ → CTA**. Isbot (manba) yuqoriga chiqarilgan, chunki asosiy raqobat
ustunligimiz — "o'ylab topmaydi, isbotlaydi".

| № | Blok | Maqsad | Balandlik |
|---|---|---|---|
| 1 | Hero | Va'da + CTA | to'liq ekran |
| 2 | "Muammo" | Og'riqni tan olish | qisqa |
| 3 | **Manba isboti (differensiator)** | Ishonch | katta, interaktiv |
| 4 | Qanday ishlaydi (3 qadam) | Tushuntirish | o'rta |
| 5 | **Direktorlar kengashi** | Farqimiz #2 | katta |
| 6 | Bilim manbalari (formatlar) | Qamrov | o'rta |
| 7 | Shablon → tayyor fayl | Amaliy foyda | o'rta |
| 8 | Kimga mo'ljallangan (3 tab) | Segmentatsiya | o'rta |
| 9 | Ekspertlar uchun ("twiningizni yarating") | 2-konversiya | katta |
| 10 | Xavfsizlik va nazorat | E'tirozni yopish | qisqa |
| 11 | Narxlar | Konversiya | katta |
| 12 | FAQ | E'tirozni yopish | o'rta |
| 13 | Yakuniy CTA | Konversiya | qisqa |
| 14 | Footer | Huquqiy/aloqa | qisqa |

---

## 3. HAR BIR BLOK — KONTENT VA MATN

### Blok 2 — "Muammo" (qisqa, 3 ta karta)
Sarlavha: **"Bilim bor — lekin kerak paytda qo'lda yo'q"**

| Karta | Matn |
|---|---|
| 🎧 30 soat dars | "Kerakli gap qaysi darsning qaysi daqiqasida edi — hech kim eslamaydi." |
| 🤖 Oddiy AI | "Chiroyli javob beradi, lekin manbasi yo'q — ishonib bo'lmaydi." |
| 👤 Ekspert | "Bitta odam kuniga 10 ta odamga javob bera oladi, 1000 taga emas." |

### Blok 3 — MANBA ISBOTI *(eng muhim blok)*
Sarlavha: **"Har bir jumla ortida — aynan manba"**

Matn:
> Javobdagi har bir fikr [1], [2] belgilari bilan raqamlangan. Bosasiz —
> dars yozuvining aynan o'sha qismi ochiladi va eshitiladi. Slayd bo'lsa —
> o'sha sahifaning rasmi chiqadi. Hech narsa o'ylab topilmaydi.

Interaktiv demo (haqiqiy, sahifa ichida ishlaydigan):
- Tayyor savol-javob namunasi ko'rsatiladi;
- `[2]` bosilganda o'ngda audio player ochiladi: **"Abdulloh ustoz — 4-dars, 12:35–14:02"**, play tugmasi;
- Yonida "Slayd 17" rasm karta.

Blok ostida kichik izoh:
> *Javobda manbaga tayanmagan jumla bo'lsa, tizim uni javobdan chiqarib tashlaydi.*

### Blok 4 — Qanday ishlaydi (3 qadam, ikonlar bilan)
1. **Bilim yuklanadi** — audio, PDF, PowerPoint, Excel, Word, veb-sahifa. Tizim matnga
   aylantiradi, mavzularga bo'ladi, indekslaydi.
2. **Savol beriladi** — Telegram yoki saytdan. Tizim savolni tahlil qiladi va kerakli
   bo'limlarni topadi.
3. **Kengash javob beradi** — mutaxassislar o'z yo'nalishi bo'yicha javob yozadi, Rais
   ularni yagona xulosaga jamlaydi, manbalar bilan.

### Blok 5 — DIREKTORLAR KENGASHI *(differensiator #2)*
Sarlavha: **"Bitta savol — bir necha mutaxassis nigohi"**

Matn:
> Savolingizni faqat bitta model o'qimaydi. Uni tegishli yo'nalish direktorlari
> ko'rib chiqadi — strategiya, moliya, huquq, operatsiya, marketing, texnologiya.
> Rais ularning fikrini solishtiradi, ziddiyat bo'lsa ochiq aytadi va yakuniy
> tavsiyani beradi.

Vizual: doira bo'ylab 6 ta rol ikoni, markazda "Rais", strelkalar markazga.
Har rol ustiga hover — o'sha direktor nima qilishi haqida 1 jumla.

Muhim qo'shimcha (kompaniyalar uchun sotuv argumenti):
> Direktorlar tarkibi va ularning xarakteri sozlanadi — sizning sohangizga moslanadi.

### Blok 6 — Bilim manbalari
Sarlavha: **"Bilim qaysi ko'rinishda bo'lsa ham qabul qilamiz"**

Logotip/ikon qatori: 🎧 Audio (MP3/M4A) · 🎬 Video · 📄 PDF · 📝 Word · 📊 PowerPoint ·
📈 Excel · 🌐 Veb-sahifa · 💬 Matn

Matn:
> Audio va videodan nutq matnga o'giriladi, taqdimotdan slaydlar rasm sifatida saqlanadi,
> jadvallardan tuzilmali ma'lumot olinadi. Har bir bo'lakning qayerdan olingani
> (fayl, sahifa, daqiqa) yozib qo'yiladi.

### Blok 7 — Shablonlar → tayyor fayl
Sarlavha: **"Javob emas, tayyor hujjat"**

Matn:
> Savolingiz shablonga tegishli bo'lsa — masalan biznes-reja, hisob-kitob jadvali,
> tahlil formasi — tizim shablonni sizning ma'lumotingiz bilan **to'ldirib**, tayyor
> Excel faylni yuboradi. Nusxa ko'chirib o'tirish shart emas.

Vizual: chat oynasi ichida "📎 gipoteza_desk.xlsx" biriktirmasi + faylning ochilgan ko'rinishi.

### Blok 8 — Kimga mo'ljallangan (3 ta tab yoki 3 ta ustun)

**Tab 1 — Tadbirkor / o'rganuvchi**
- Ustoz darslaridan chiqmagan holda javob;
- Uy vazifasi emas, amaliy qadamlar;
- Telegramda, istalgan vaqtda.

**Tab 2 — Ekspert / murabbiy / ustoz**
- Bilimingiz 1000 odamga bir vaqtda yetadi;
- Xarakteringiz va uslubingiz saqlanadi;
- Kim, nima so'ragani statistikada ko'rinadi;
- Obunadan daromad.

**Tab 3 — Kompaniya**
- Ichki qoidalar, reglament, treninglar bitta bazada;
- Yangi xodim savolini AI javob beradi, rahbar vaqti tejaydi;
- Kim qaysi bilimga kira olishi — matritsa bilan boshqariladi.

### Blok 9 — EKSPERTLAR UCHUN CTA bloki
Sarlavha: **"O'z raqamli egizagingizni yarating"**

3 qadam:
1. Bilimingizni yuklaysiz (biz yordam beramiz);
2. Xarakter va uslubni sozlaysiz — qanday gapirishi, nimani aytmasligi;
3. Egizak ishga tushadi, siz kabinetdan hammasini kuzatasiz.

Forma (4 maydon, ko'p emas): Ism · Telegram/telefon · Yo'nalish · Bilim hajmi (taxminan).
Tugma: **"Ariza qoldirish"**. Ostida: *"24 soat ichida bog'lanamiz."*

### Blok 10 — Xavfsizlik va nazorat
| Ikon | Sarlavha | Matn |
|---|---|---|
| 🔒 | Bilimingiz sizniki | "Yuklangan materiallar faqat sizning egizagingiz uchun ishlatiladi." |
| 🧭 | Chegara aniq | "Egizak faqat unga ruxsat etilgan bilimdan javob beradi — boshqasidan emas." |
| 👁 | Har javob tekshiriladi | "Manbasi yo'q jumla javobga tushmaydi." |
| 🇺🇿 | O'zbek tilida | "Savol ham, javob ham, manba ham o'zbekcha." |

### Blok 11 — NARXLAR
Sarlavha: **"Avval sinab ko'ring — keyin tanlang"**

| | **Bepul** | **Shaxsiy** | **Pro** | **Kompaniya** |
|---|---|---|---|---|
| Savollar | 3 ta savol | oylik limit | kengaytirilgan limit | kelishuv asosida |
| Egizaklar | 1 ta | 1 ta | barchasi | o'zingizniki + umumiy |
| Manba isboti (audio/slayd) | ✅ | ✅ | ✅ | ✅ |
| Tayyor fayl (shablon) | — | ✅ | ✅ | ✅ |
| Suhbat tarixi | ✅ | ✅ | ✅ | ✅ |
| Ustuvor navbat | — | — | ✅ | ✅ |
| Shaxsiy egizak (o'zingiz uchun) | — | — | — | ✅ |
| Narx | 0 so'm | *(to'ldiriladi)* | *(to'ldiriladi)* | Aloqaga chiqing |

Jadval ostida:
- To'lov: **Click** va **Payme** logolari;
- *"Limit foydalanish hajmiga qarab hisoblanadi — ishlatmasangiz sarflanmaydi."*
- *"Istalgan vaqtda bekor qilasiz."*

> ⚠️ Aniq raqamlar biznes tomonidan tasdiqlangach qo'yiladi. Landing'ni raqamsiz
> chiqarib bo'lmaydi — "Aloqaga chiqing" varianti faqat Kompaniya tarifida qolsin.

### Blok 12 — FAQ (akkordeon)
1. **Bu oddiy ChatGPT'dan nimasi bilan farq qiladi?** — Javob faqat yuklangan manbadan
   olinadi va har bir fikr manbaga bog'lanadi; javobni tekshirib ko'rish mumkin.
2. **Ustozning aynan gapini eshita olamanmi?** — Ha, javobdagi havolani bossangiz dars
   yozuvining o'sha qismi ochiladi.
3. **Bilimim boshqalarga o'tib ketmaydimi?** — Yo'q. Har egizakning bilimi ajratilgan,
   ruxsat matritsasi bilan boshqariladi.
4. **Ro'yxatdan qanday o'taman?** — Telegram orqali, bir bosishda. Alohida parol kerak emas.
5. **Qaysi tillarda ishlaydi?** — O'zbek tili asosiy; rus va ingliz tilidagi manbalardan
   ham o'qiy oladi.
6. **Javob qancha vaqtda keladi?** — Oddiy savol tez, chuqur tahlil talab qiladiganiga
   bir necha o'n soniya (kengash bosqichma-bosqich ishlaydi, jarayon jonli ko'rinadi).
7. **Xato javob bersa-chi?** — Har javobda manba bor, darrov tekshirasiz; xato haqida
   bitta bosishda xabar berasiz, u tuzatishga tushadi.
8. **To'lovni qanday qilaman?** — Click yoki Payme. Obuna avtomatik uzaymaydi — o'zingiz
   tasdiqlaysiz.
9. **Bilimimni o'chira olamanmi?** — Ha, kabinetdan istalgan manbani o'chirasiz, u bilan
   birga undan olingan javob asoslari ham chiqib ketadi.

### Blok 13 — Yakuniy CTA
> **"3 ta savolingizni bepul bering — farqini o'zingiz ko'rasiz."**
> [Telegramda boshlash] [Ekspert sifatida qo'shilish]

### Blok 14 — Footer
Logotip · Qisqa ta'rif · Aloqa (Telegram, email, telefon) · Manzil ·
Havolalar: Ommaviy oferta · Maxfiylik siyosati · Qaytarish shartlari (to'lov tizimlari talabi) ·
© 2026 <Kompaniya nomi>

---

## 4. TUGMALAR QAYERGA OLIB BORADI (texnik bog'lanish)

| Tugma | Harakat |
|---|---|
| "Telegramda bepul sinash" | `https://t.me/<bot>?start=landing_hero` (UTM = start param) |
| "Saytda kirish" (header) | `/` → platforma UI, Telegram login orqali |
| "Ekspert sifatida qo'shilish" | Forma → `POST /api/ariza` → adminga TG bildirishnoma |
| "Demo ko'rish" | Modal video (o'z hostimizda, YouTube emas — tezlik uchun) |
| Narx jadvalidagi "Tanlash" | Telegram bot → to'lov oqimi (Click/Payme) |
| Manba demo `[2]` | Statik demo ma'lumot (landing backend'ga bog'lanmaydi) |

`start` parametrlari bo'yicha bot qaysi blokdan kelganini yozib boradi → qaysi blok
sotayotganini bilamiz.

---

## 5. TEXNIK TALABLAR

- **Bir sahifa**, statik (HTML+CSS+minimal JS). Build-toolchain shart emas — hozirgi uslubda.
- **Mobil birinchi**: trafikning katta qismi Telegramdan, ya'ni telefondan keladi.
  Telegram ichki brauzerida ham tekshiriladi.
- **Tez**: LCP < 2.0s, umumiy og'irlik < 1 MB. Rasmlar WebP, video lazy.
- **Til**: UZ (asosiy) → keyin RU. Til almashtirgich header'da. Kirill/lotin — lotin asosiy.
- **Dark/light**: sistemaga moslashadi (platforma UI bilan bir xil ranglar).
- **SEO**: `title`, `description`, OG-rasm (Telegramda havola chiroyli ko'rinishi uchun —
  bu muhim, chunki havola asosan Telegramda tarqaladi), `schema.org/SoftwareApplication` + FAQPage.
- **Analitika**: Yandex Metrika (O'zbekistonda kuchli) + o'z hodisalarimiz
  (`cta_bosildi`, `demo_ochildi`, `narx_korildi`, `ariza_yuborildi`).
- **Ko'chirish**: `platforma/web/landing.html` sifatida, `GET /` marshrutida
  (hozirgi ilova `/app` ga o'tadi) yoki alohida statik domen.

---

## 6. NIMANI YOZMASLIK KERAK (muhim!)

Bularni yozsak — keyin isbotlay olmaymiz yoki muammo chiqadi:

- ❌ "100% aniq", "xato qilmaydi" — hech qanday AI bunday emas.
- ❌ Tasdiqlanmagan raqamlar: "10 000 foydalanuvchi", "500 kompaniya".
- ❌ Ustozlarning ismi va surati — **yozma ruxsatsiz ishlatilmaydi**. Landing'da
  ekspert ismi/ovozi/fotosi chiqishi uchun shartnoma bo'lishi shart.
- ❌ Boshqa brendlar bilan to'g'ridan-to'g'ri taqqoslash jadvali (huquqiy risk) —
  o'rniga "biz nima qilamiz" tarzida yozamiz.
- ❌ Soxta sharhlar/testimoniallar. Haqiqiysi bo'lmaguncha, blokni umuman qo'ymaymiz.
- ❌ "Bepul cheksiz" — 3 ta bepul prompt, shuni aniq yozamiz.
- ⚠️ Narx jadvalidagi bo'sh joylar chiqishdan oldin to'ldirilishi shart.

---

## 7. KERAK BO'LADIGAN MATERIALLAR (kimdan)

| Material | Kimdan | Holat |
|---|---|---|
| Kompaniya nomi, logo, brend ranglari | Biznes | ⬜ |
| Demo video 60–90s (ekran yozuvi + ovoz) | Biz yozamiz | ⬜ |
| Real skrinshotlar (chat, manba isboti, kabinet) | Platformadan | ⬜ |
| Tarif narxlari (so'mda) | Biznes | ⬜ |
| Ekspertlardan ism/foto/ovoz ishlatishga ruxsat | Huquq | ⬜ |
| Ommaviy oferta, maxfiylik siyosati matni | Huquq | ⬜ |
| Aloqa: telefon, email, manzil, Telegram | Biznes | ⬜ |
| Bot username (`t.me/...`) | Bor | ✅ |

---

## 8. YOZISH USLUBI (copy qoidalari)

- **Siz**ga murojaat, "biz" kam. Sotuvchi emas, yordamchi ohangi.
- Qisqa jumla. Bitta blokda 1 ta fikr.
- Texnik atama yo'q: "vektor qidiruv", "RAG", "embedding", "LLM" — landing'da **ishlatilmaydi**.
  Ular o'rniga: "kerakli joyni topadi", "manbaga tayanadi".
- Har sarlavha — foyda haqida, funksiya haqida emas.
  ❌ "pgvector asosidagi qidiruv" → ✅ "30 soatlik darsdan kerakli daqiqani topadi".
- Raqam ishlatilsa — isbotlanadigan bo'lsin.

---

## 9. ISHGA TUSHIRISH TARTIBI

1. **v0 (1 kun)** — matn tayyor, bitta HTML, hero + 3 blok + CTA. Telegram havolasi ishlaydi.
   Maqsad: havola tarqatsa bo'ladigan holat.
2. **v1** — barcha bloklar, interaktiv manba demosi, forma + adminga bildirishnoma, analitika.
3. **v2** — demo video, real skrinshotlar, RU tili, narxlar, huquqiy hujjatlar.
4. **Keyin** — A/B: hero sarlavhasining 2 varianti (C vs B), CTA matni.

> Landing platformaning 3-bosqichiga (to'lov/tarif) bog'liq: narxlar shu bosqichda
> aniqlanadi. Shuning uchun **v0 va v1 hozir**, narx bloki **3-bosqichdan keyin** yakunlanadi.
