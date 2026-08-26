# ORFOEPIYA — talaffuz qatlamini kuchaytirish rejasi

> Holat: **🟡 B1–B3 BAJARILDI (2026-08-25), B4 eshitish sinovi egasini kutmoqda.**
> Kod: `core/normalize.py` (5–7-bo'limlar), `talaffuz.txt`, `talaffuz_oltin.txt`,
> `sinov_talaffuz.py`, `talaffuz_korpus.py`. Qisqa qo'llanma: `README.md` →
> «Orfoepiya». Sinov: `python sinov_talaffuz.py` — 70/70 yashil, 0,6 ms/jumla.
>
> Rejadan farqlar (amalda tuzatildi):
> - `g → k` qoidasi «ng» digrafini buzardi (`eng → enk`, `bizning → biznink`) —
>   korpus hisoboti birinchi ishga tushirishdayoq ko'rsatdi; `n` dan keyingi `g`
>   istisno qilindi.
> - `t` tushish qoidasi «rt» birikmasida haddan oshardi (`buyurtma → buyurma`,
>   `shartli → sharli`) — oldingi undosh s/sh/x/f/n/k/q bilan cheklandi, `r` dan
>   keyin faqat `tt` da (`to'rtta → to'rta`).
> - Eski qoida `strategiya → srategiya`, `elektr → elekr` qilardi — keyingi
>   undosh qo'shimcha boshlovchilar (l d n m g s t) bilan cheklandi.

## 1. Maqsad — egasi talabi

Madina/Sardor ovozi matnni **yozilishi** bo'yicha emas, adabiy o'zbek
**talaffuzi** bo'yicha o'qisin: kamida 10 000 kundalik so'z qamrovi, real-time
(jumla < 1 ms), egasi eshitib tasdiqlagan qoidalar. «Aksent»ning qolgan
manbai — TTS ning harfma-harf o'qishi — shu qatlam bilan yopiladi.

## 2. Bosh tamoyillar

| # | Tamoyil | Amalda |
|---|---|---|
| P1 | **Qoida — asosiy kuch, lug'at — istisno** | O'zbek tili agglyutinativ: `kitob` = kitobim, kitoblar, kitobingizdan... 10 000 o'zak × qo'shimchalar = 200 000+ shakl. Bitta «so'z oxirida b → p» qoidasi hammasini qamraydi; lug'at faqat qoida tushuntira olmagan so'zlar uchun (`mashhur → mas-hur`). |
| P2 | **Har qoida nomlangan va alohida o'chiriladi** | `UZ_ORTHOEPY_SKIP=shs,d_t` — eshitish A/B sinovi qoidama-qoida qilinadi. «Ko'proq qoida = yaxshiroq» emas, «tasdiqlangan qoida = yaxshiroq». |
| P3 | **Lug'at qoidadan ustun** | `talaffuz.txt` dagi so'zga qoida tegmaydi — egasining qulog'i qoidadan ustun. Qoida buzgan so'zni `abstrakt = abstrakt` deb himoya qilish ham mumkin. |
| P4 | **Chiziqli tezlik** | Matn so'zlarga bo'linadi, har so'z bir marta ko'riladi: lug'at hajmi latency'ga ta'sir qilmaydi (10 000 yozuv bilan 0,6 ms/jumla). Eski `for ... re.sub` sikli 10 000 da yuzlab ms berardi (Python `re` keshi 512 ta). |
| P5 | **Oltin fayl — regressiya** | Har qoida uchun misollar `talaffuz_oltin.txt` da; qoida qo'shilsa/o'zgarsa sinov yashil bo'lishi shart. |
| P6 | **Ovoz modeli — shift** | Urg'u, intonatsiya, unli sifati harf bilan yozilmaydi — bu Madina modelining ichida. Matn qatlami faqat undosh/harf darajasini tuzatadi. |

## 3. Qoidalar (tartib muhim — `ORTHOEPY_RULES`)

So'z darajasida qo'llanadi; yagona so'zlararo kontekst — keyingi so'z unli
bilan boshlanishi (oradagi bo'shliqdan boshqa belgi bo'lmasa). `h` ataylab
jarangsizlar qatorida yo'q — zaif tovush, oldingi undoshni o'zgartirmaydi
(`mazhab`, `is'hoq`).

| # | Nom | Qoida | Misollar | Holat |
|---|---|---|---|---|
| 1 | `ch_sh` | ch → sh, t/d oldida | uchta → ushta, nechta → neshta, ochdi → oshdi (→ 4 bilan oshti) | yangi — eshitish kutilmoqda |
| 2 | `jarangsiz_oldida` | b/d/g/z/v → p/t/k/s/f jarangsiz undosh (p t k q s f x ch sh) oldida; «ng» dagi g tegmaydi | avtobus → aftobus, yozsa → yossa, mazkur → maskur, sakkizta → sakkista, umidsiz → umitsiz | v → f eski (tasdiqlangan), b/d/g/z yangi |
| 3 | `oxiri_jarangsiz` | so'z oxirida b/d/g → p/t/k; keyingi so'z unli bilan boshlansa jarangli qoladi; `g'` va «ng» tegmaydi | kitob → kitop, *kitob oldim* o'zgarmaydi, olib keldi → olip keldi, Murod → Murot, pedagog → pedagok, eng/bizning o'zgarmaydi | b/d eski (tasdiqlangan), g yangi |
| 4 | `d_t` | d → t jarangsiz undoshdan (sh/ch ham) keyin — `-di`, `-da/-dan`, `-dir`, `-dek` | ketdi → ketti, chiqdi → chiqti, ofisda → ofista, ishdan → ishtan, tushdi → tushti, itdek → ittek | yangi — **eng ta'sirli** (306 marta/24 200) |
| 5 | `n_m` | n → m lab undoshi (b/p) oldida | shanba → shamba, manba → mamba | b eski (tasdiqlangan), p yangi |
| 6 | `shs` | sh + s → shsh | ishsiz → ishshiz, gaplashsak → gaplashshak | yangi — **eng shubhali**, avval shuni eshiting |
| 7 | `t_tushadi` | s/sh/x/f/n/k/q dan keyingi t qo'shimcha boshlovchi undosh (l d n m g s t) oldida tushadi; r dan keyin faqat tt da | do'stlar → do'slar, baxtli → baxli, to'rtta → to'rta, Toshkentga → Toshkenga, vaqtli → vaqli, aktsiya → aksiya, klientlar → klienlar | eski, **toraytirildi** |

### Ko'rib chiqilgan, KIRITILMAGAN (ishonch yetarli emas)

| Hodisa | Misol | Nega kiritilmadi |
|---|---|---|
| b → p qo'shimcha oldida | kitoblar → kitoplar, maktabda → maktapta | sonor (l, r, m, n) oldida jarangli qoladi (`ibrat`, `sabr`); chegara aniq emas |
| j → sh so'z oxirida | garaj → garash | o'zlashma so'zlar; nutqda ikkala variant ham bor |
| n → ng | menga → mengga | TTS «ng» ni qattiq g bilan o'qishi mumkin — teskari natija xavfi |
| unli qisqarishi | bilan → blan, kishi → kshi | og'zaki, adabiy me'yor emas |
| h ta'siri | mazhab → mashab | noto'g'ri — h zaif tovush |

Eshitish sinovida kerak bo'lsa qo'shiladi — qoida bitta regex + oltin faylga
misol, boshqa hech narsa o'zgarmaydi.

## 4. Lug'at — `talaffuz.txt`

```
so'z  = talaffuz     # faqat shu so'z:        mashhur = mas-hur
so'z* = talaffuz     # o'zak, qo'shimcha saqlanadi: mashhur* = mas-hur
                     #   mashhurlik -> mas-hurlik, Is'hoqov -> Is-hoqov
```

- Registrga sezgir emas; so'z bosh harf bilan bo'lsa talaffuz ham bosh harf.
- Lug'at qoidalardan **oldin** qo'llanadi va topilgan so'z yakuniy — qoida
  tegmaydi (P3). Eski mexanizmda lug'at qoidadan keyin edi: `avtobus` kaliti
  matnda allaqachon `aftobus` bo'lgani uchun topilmasdi.
- Fayl mtime bo'yicha kuzatiladi — o'zgarish restart'siz kuchga kiradi.
- Kod ichidagi asos lug'at (`PRONUNCIATION_FIXES`): `alaykum → aleykum`.
- Bo'g'inlab aytish: `aeroport = a-eroport` (chiziqcha TTS ga kichik pauza).
- IPA/`<phoneme>` lug'atdan berilmaydi — SSML `escape()` bilan kiradi (B5 ga
  qarang).

## 5. Korpus va «10 000 so'z»

10 000 so'z — almashtirish jadvali emas, **sinov korpusi**: qoidalar to'g'ri
ishlayotganini tekshirish va istisnolarni topish uchun.

```
python talaffuz_korpus.py                       # transkript/chiqish/*/toliq_matn.txt
python talaffuz_korpus.py matn.txt papka/       # qo'shimcha manbalar
python talaffuz_korpus.py --eng-kop 10000 --chiqish royxat.tsv
```

Chiqish `talaffuz_korpus.tsv` (gitga tushmaydi): `so'z | soni | talaffuz |
qoidalar | manba` — chastota bo'yicha. Har qator uchun uch qaror:

- (a) qoida to'g'ri — hech narsa;
- (b) qoida noto'g'ri — `.env` da `UZ_ORTHOEPY_SKIP=nom`, shu hujjatga yozuv;
- (c) so'z istisno — `talaffuz.txt` ga qator.

**Birinchi hisobot (2026-08-25, 3 transkript, og'zaki ustoz nutqi):**
24 200 so'z, 5 093 noyob; qoida 545 noyob so'zga (10,7 %) ta'sir qildi,
matnda 1 921 marta (7,9 %).

| Qoida | Noyob so'z | Matnda |
|---|---|---|
| `oxiri_jarangsiz` | 228 | 1 263 (qilib → qilip 163, deb → dep 92, olib → olip 88) |
| `d_t` | 167 | 306 (ketdi → ketti 22, aytdim → ayttim 18) |
| `t_tushadi` | 80 | 166 (klientlar → klienlar 11, to'rtta → to'rta 9) |
| `jarangsiz_oldida` | 68 | 113 (sotuvchi → sotufchi 7, sakkizta → sakkista 3) |
| `ch_sh` | 18 | 99 (uchta → ushta 49, nechta → neshta 17) |
| `shs` | 6 | 7 |
| `n_m` | 4 | 9 |

Keyingi manbalar: prod bazadagi ustoz darslari (ancha katta, ayni janr),
Wikipedia/yangiliklar chastota ro'yxati, rasmiy «O'zbek tilining orfoepik
lug'ati» (istisnolar uchun).

## 6. Sinov — `python sinov_talaffuz.py`

| Bo'lim | Nima tekshiradi |
|---|---|
| oltin fayl | `talaffuz_oltin.txt` — har qoida, so'zlararo kontekst, lug'at, 1–5 bosqichlar regressiyasi (70 holat) |
| muhit bayroqlari | `UZ_ORTHOEPY=off`, `UZ_ORTHOEPY_SKIP`, `UZ_APOSTROPHE` (rasmiy ʻ/ʼ belgilari aynan) |
| lug'at | qoidadan ustunlik, o'zak + qo'shimcha, bosh harf, qisqa so'zga tegmaslik, fayl formati |
| tezlik | 10 000 yozuvli lug'at bilan jumla < 2 ms (hozir 0,6 ms) |

`.venv` shart emas — `core/normalize.py` to'g'ridan-to'g'ri yuklanadi (paket
`google-genai` talab qiladi, normalizatorga u kerak emas).

## 7. Bosqichlar

| Bosqich | Mazmun | Holat |
|---|---|---|
| B1 | Qoida dvigateli: token asosida, 7 nomlangan qoida, alohida o'chirish, oltin fayl | ✅ |
| B2 | Lug'at: o'zak (`*`), qoidadan oldin va ustun, bosh harf, chiziqli tezlik | ✅ |
| B3 | Korpus skripti + birinchi hisobot | ✅ |
| B4 | **Eshitish sinovi** — egasi (8-bo'lim protokoli) | ⏳ |
| B5 | IPA sinovi: `<phoneme alphabet="ipa">` uz-UZ ovozida ishlaydimi (`aksent_test/17_q_ipa.wav` qayta, natija yozilmagan). Ishlasa — lug'atga `ipa:` yozuv turi, urg'uli so'zlar va ismlar shu kanalga | ⏳ |
| B6 | Korpusni kengaytirish: prod darslar matni → 10 000+ so'z, istisnolar lug'ati | ⏳ |

## 8. Eshitish protokoli (B4)

Madina modeli ba'zi qoidalarni **o'zi** qo'llashi mumkin; ortiqcha «fonetik
yozuv» model uchun notanish so'z bo'lib ohangni buzishi ham mumkin. Shuning
uchun har yangi qoida alohida tekshiriladi:

1. Qoida uchun 5 jumla tanlang (korpus hisobotidagi eng ko'p uchraydiganlar:
   `d_t` uchun «ketdi, ofisda, ishdan, chiqdi, aytdim»).
2. Ikki wav: `UZ_ORTHOEPY_SKIP=<nom>` bilan va usiz — `aksent_test/` ga
   `23_d_t_siz.wav` / `24_d_t_bilan.wav` uslubida saqlang.
3. Qaror: qoldirish / o'chirish (`.env` da `UZ_ORTHOEPY_SKIP`) / toraytirish.
   Natijani 3-bo'lim jadvalining «Holat» ustuniga yozing.
4. Tartib: avval `shs` (eng shubhali), keyin `d_t` (eng ta'sirli), keyin
   `ch_sh`, `jarangsiz_oldida` (b/d/g/z qismi), `oxiri_jarangsiz` (g qismi).
   `v → f`, `b/d` oxiri, `n → b`, `do'stlar` — avval tasdiqlangan.

## 9. Chegaralar — matn qatlami hal qilmaydigan narsalar

- **Urg'u** (so'zda urg'u o'rni), **intonatsiya**, **unli sifati** — Madina
  modelining ichida; harf bilan yozib bo'lmaydi. Yo'l: B5 (IPA) yoki Azure
  Custom Neural Voice (haqiqiy diktor yozuvida o'qitilgan ovoz).
- **Grammatika** — Gemini'ning ishi (`SYSTEM_PROMPT`); lug'at ham, qoida ham
  jumla tuzilishiga tegmaydi.
- **Ingliz so'zlari** — transkriptda ko'p (`and → ant`, `good → goot`); qoida
  ularga ham tegadi, lekin prompt ingliz so'zini taqiqlaydi, TTS ularni
  baribir o'zbekcha o'qiydi — alohida ish qilinmaydi.
