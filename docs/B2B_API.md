# Virtaks API — hamkorlar uchun qo'llanma

Virtaks — ustoz bilimidan qurilgan raqamli egizak. API orqali siz o'z
ilovangizga «raqamli ustoz» qatlamini ulaysiz: mijozingiz savol beradi,
javob **faqat o'sha ustozning darslariga tayanib** yoziladi va har da'voda
manbaga iqtibos bo'ladi.

- **Manzil**: `https://twin.virtaks.uz/api/v1`
- **Hujjat (Swagger)**: https://twin.virtaks.uz/api/v1/docs

> Endpoint manzillari inglizcha (`/ask`, `/mentors`, ...). Ilgari berilgan
> o'zbekcha manzillar (`/savol`, `/twinlar`, ...) **ishlashda davom etadi** —
> ulangan integratsiyangizni o'zgartirish shart emas.
- **Format**: JSON (UTF-8)
- **Autentifikatsiya**: `Authorization: Bearer <kalit>`

---

## 1. Kalit

Kalit sizga bir marta beriladi va **qayta ko'rsatilmaydi** — darhol
xavfsiz joyga saqlang. Yo'qotsangiz eskisi bekor qilinib, yangisi
beriladi.

```
vk_live_7f3a2c_9K2mQxR4tN8vB1sL6wZ0pY5jH3dF7gA2
```

Kalitni **faqat server tomonida** saqlang. Brauzer yoki mobil ilovaga
qo'ymang: undan foydalangan har kim sizning hisobingizdan pul sarflaydi.

Kerak bo'lsa kalitga IP oq ro'yxati qo'yiladi — u holda so'rov faqat
kelishilgan IP lardan qabul qilinadi.

Integratsiyani tekshirish (pul sarflamaydi):

```bash
curl -H "Authorization: Bearer $VIRTAKS_KALIT" \
     https://twin.virtaks.uz/api/v1/health
```

```json
{"holat": "ok", "tashkilot": "Sizning kompaniyangiz", "twinlar": 2}
```

---

## 2. Qaysi ustozlar ochiq

```bash
curl -H "Authorization: Bearer $VIRTAKS_KALIT" \
     https://twin.virtaks.uz/api/v1/mentors
```

```json
{"royxat": [
  {"slug": "axrolxoja", "nom": "Axrolxo'ja", "tavsif": "Biznes va sotuv"}
]}
```

Ro'yxatdagi `slug` ni `/savol` da ishlatasiz. Ro'yxatda yo'q ustoz uchun
so'rov `404` qaytaradi.

---

## 3. Mijozingizni ro'yxatga olish

Har mijozingizga o'z ichki ID ingizni bering — biz suhbat tarixini,
profilni va iqtiboslarni shu bo'yicha ajratamiz.

```bash
curl -X POST https://twin.virtaks.uz/api/v1/customer \
  -H "Authorization: Bearer $VIRTAKS_KALIT" \
  -H "Content-Type: application/json" \
  -d '{"tashqi_id": "user-8891", "ism": "Aziz"}'
```

```json
{"id": 4821, "tashqi_id": "user-8891", "yangi": true}
```

Takroriy so'rov ayni yozuvni qaytaradi (`yangi: false`) — oldindan
tekshirish shart emas. `/savol` ham mijozni o'zi yaratadi, ya'ni bu
qadamni umuman o'tkazib yuborish mumkin.

**`tashqi_id`** hech qachon modelga berilmaydi. **`ism`** faqat murojaat
uchun; u modelga *ma'lumot* sifatida uzatiladi, ko'rsatma sifatida emas.

---

## 4. Savol berish

Ikki rejim bor. Boshlash uchun **`oqim: false`** qulayroq.

### 4.1. To'liq javob (`oqim: false`)

```bash
curl -X POST https://twin.virtaks.uz/api/v1/ask \
  -H "Authorization: Bearer $VIRTAKS_KALIT" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: 5f1c8e0a-2b41-4c9e-9f3a-77d0c1e2b845" \
  -d '{
        "tashqi_id": "user-8891",
        "twin": "axrolxoja",
        "savol": "Sotuv bo'\''limini qanday tuzaman?",
        "oqim": false
      }'
```

```json
{
  "suhbat": 1204,
  "javob_id": 88213,
  "javob": "Sotuv bo'limi uch bosqichda quriladi [1]. Birinchi ... [2]",
  "manbalar": [
    {"n": 1, "bolak": 88213, "manba": "05.Dars. Sotuv bo'limi tashkil qilish",
     "joy": "[0:12:30–0:14:05]", "tur": "audio", "dars": "Manbalar",
     "audio": true, "sahifa": false}
  ],
  "hisob": {"sarf_usd": 0.019, "balans_usd": 41.62}
}
```

Javob matnidagi `[1]`, `[2]` — `manbalar` ro'yxatidagi `n` ga ishora.
Ularni o'z UI ingizda havolaga aylantirishingiz mumkin.

### 4.2. Oqim (`oqim: true`)

`text/event-stream`. Javob token-token keladi — foydalanuvchi kutib
o'tirmaydi (birinchi so'z ~3 soniyada).

```
data: {"tur":"boshlandi","suhbat":1204,"javob_id":88213}
data: {"tur":"holat","matn":"manbalar qidirilmoqda"}
data: {"tur":"matn","q":"Sotuv "}
data: {"tur":"matn","q":"bo'limi "}
data: {"tur":"manbalar","royxat":[...]}
data: {"tur":"tayyor","javob_id":88213,"davomiylik":7,"manbalar":[...],
       "hisob":{"sarf_usd":0.019,"balans_usd":41.62}}
```

| Hodisa | Ma'no |
|---|---|
| `boshlandi` | qator yaratildi, `suhbat` va `javob_id` ma'lum |
| `holat` | ichki bosqich (ixtiyoriy, ko'rsatmasangiz ham bo'ladi) |
| `matn` | javobning navbatdagi bo'lagi (`q`) |
| `manbalar` | ishlatilgan iqtiboslar |
| `tayyor` | yakun: davomiylik, iqtiboslar, hisob |
| `xato` | javob tayyorlanmadi |

Ulanishni uzsangiz model **darhol to'xtaydi** va o'sha paytgacha
sarflangani hisoblanadi.

### 4.3. Suhbatni davom ettirish

Javobdagi `suhbat` qiymatini keyingi so'rovga qo'shing — twin oldingi
gaplarni hisobga oladi:

```json
{"tashqi_id": "user-8891", "savol": "Birinchi qadamni batafsil ayt",
 "suhbat": 1204, "oqim": false}
```

### 4.4. Maydonlar

| Maydon | Majburiy | Izoh |
|---|---|---|
| `tashqi_id` | ha | sizning mijoz ID ingiz |
| `savol` | ha | 4000 belgigacha |
| `twin` | yo'q | `slug`; berilmasa birinchi ochiq ustoz |
| `suhbat` | yo'q | davom ettirish uchun |
| `oqim` | yo'q | `true` (standart) yoki `false` |
| `ism` | yo'q | mijoz ismi (birinchi so'rovda) |

---

## 5. Suhbat tarixi

```bash
curl -H "Authorization: Bearer $VIRTAKS_KALIT" \
  "https://twin.virtaks.uz/api/v1/conversations?tashqi_id=user-8891"

curl -H "Authorization: Bearer $VIRTAKS_KALIT" \
  https://twin.virtaks.uz/api/v1/conversation/1204
```

---

## 6. Audio fragment

Iqtibosda `audio: true` bo'lsa, darsning **aynan o'sha daqiqasini**
kesib olish mumkin:

```bash
curl -X POST -H "Authorization: Bearer $VIRTAKS_KALIT" \
  https://twin.virtaks.uz/api/v1/chunk/88213/fragment
```

```json
{"holat": "ketmoqda", "bolak": 88213}
```

Tayyor bo'lgach ayni so'rov `{"holat": "tayyor"}` qaytaradi (odatda
10–15 soniya). Fragment fayliga havola olish hozircha kelishuv bo'yicha
beriladi — bog'laning.

---

## 7. Hisob

```bash
curl -H "Authorization: Bearer $VIRTAKS_KALIT" \
     https://twin.virtaks.uz/api/v1/account
```

```json
{
  "balans_usd": 41.62,
  "oylik_chegara_usd": 0,
  "joriy_oy": {"sarf_usd": 8.38, "savollar": 441},
  "ogohlantirish_usd": 5,
  "balans_past": false,
  "harakatlar": [
    {"vaqt": "...", "tur": "sarf", "summa_usd": -0.019,
     "qoldiq_usd": 41.62, "izoh": "chat"}
  ]
}
```

Hisob **oldindan to'lov** asosida: balans tugasa so'rovlar `402` bilan
to'xtaydi. `balans_past: true` bo'lganda to'ldirishni boshlang.

Har savolning narxi savol va javob uzunligiga bog'liq. O'lchangan
namuna: 8 iqtibosli, ~3800 belgilik javob — **$0.074**. Aniq summa har
javobning `hisob.sarf_usd` maydonida, ya'ni oldindan taxmin qilish shart
emas.

### 7.1. Oylik hisob-faktura

```bash
curl -H "Authorization: Bearer $VIRTAKS_KALIT" \
     "https://twin.virtaks.uz/api/v1/report?oy=2026-09"
```

```json
{
  "tashkilot": "Sizning kompaniyangiz",
  "davr": "2026-09",
  "savollar": 441, "mijozlar": 63, "chaqiruvlar": 882,
  "jami_usd": 32.6,
  "twinlar": [{"nom": "Axrolxo'ja", "savollar": 441, "usd": 32.6}],
  "balans_usd": 41.62
}
```

`oy` berilmasa joriy oy qaytadi.

---

## 8. Xatolar

| Kod | `xato` | Nima qilish |
|---|---|---|
| 400 | `notogri` | so'rov maydonlarini tekshiring |
| 401 | `kalit_notogri` | kalit yaroqsiz, muddati o'tgan yoki IP mos emas |
| 402 | `balans_tugadi` | hisobni to'ldiring |
| 403 | `ruxsat_yoq` | kalitda bu huquq yo'q |
| 404 | `topilmadi` | resurs yo'q yoki sizga ochilmagan |
| 409 | `twin_yoq` | hali twin biriktirilmagan — bog'laning |
| 429 | `tashkilot_tez` / `mijoz_tez` / `parallel_oqim` | `Retry-After` sarlavhasini kuting |
| 503 | `model` | vaqtinchalik; qayta urinish mumkin |

Barcha xatolar bir xil shaklda:

```json
{"xato": "balans_tugadi", "xabar": "Balans tugadi (0.00 USD). Hisobni to'ldiring."}
```

---

## 9. Cheklovlar

| Nima | Standart |
|---|---|
| So'rov (tashkilot bo'yicha) | 60 / daqiqa |
| So'rov (bitta mijoz bo'yicha) | 20 / daqiqa |
| Bir vaqtda ochiq oqim | 5 |
| Savol uzunligi | 4000 belgi |

Chegaralar shartnoma bo'yicha oshiriladi.

---

## 10. Takroriy so'rov (idempotentlik)

Tarmoq uzilib, so'rovni takrorlashingiz mumkin. Ikki marta pul
to'lamaslik uchun `Idempotency-Key` sarlavhasini bering (UUID):

```
Idempotency-Key: 5f1c8e0a-2b41-4c9e-9f3a-77d0c1e2b845
```

Ayni kalit bilan kelgan ikkinchi so'rov saqlangan javobni qaytaradi va
`Idempotent-Takror: 1` sarlavhasini qo'yadi. Kalitlar 24 soat saqlanadi.

⚠️ Idempotentlik **faqat `oqim: false`** rejimida ishlaydi — oqimni
takrorlab bo'lmaydi.

---

## 11. Javob matni haqida

- Markdownning **havola va rasm sintaksisi ishlatilmaydi** — javobga
  begona URL tushmaydi. Matnni o'z sahifangizga xavfsiz joylashtira
  olasiz (baribir HTML-ekranlashni unutmang).
- Iqtiboslar **faqat haqiqiy bo'laklarga** ishora qiladi; model o'zi
  o'ylab topgan raqam ro'yxatga tushmaydi.
- Bilim yetmasa twin buni **ochiq aytadi**, taxmin qilmaydi.

---

## 12. Namuna (Python)

```python
import os, requests

ASOS = "https://twin.virtaks.uz/api/v1"
BOSH = {"Authorization": f"Bearer {os.environ['VIRTAKS_KALIT']}"}


def sora(tashqi_id: str, savol: str, suhbat: int | None = None) -> dict:
    r = requests.post(f"{ASOS}/ask", headers=BOSH, timeout=120, json={
        "tashqi_id": tashqi_id, "savol": savol,
        "suhbat": suhbat, "oqim": False,
    })
    if r.status_code == 402:
        raise RuntimeError("Virtaks balansi tugadi")
    if r.status_code == 429:
        raise RuntimeError(f"chegara; {r.headers.get('Retry-After')} s kuting")
    r.raise_for_status()
    return r.json()


j = sora("user-8891", "Sotuv bo'limini qanday tuzaman?")
print(j["javob"])
for m in j["manbalar"]:
    print(f"  [{m['n']}] {m['manba']} {m['joy']}")
```

---

## 13. Aloqa

Kalit, twin biriktirish, chegaralarni oshirish va hisobni to'ldirish —
shartnomangizdagi menejer orqali.
