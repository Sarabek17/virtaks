"""O'zbekcha TTS uchun matn normalizatsiyasi — "aksent" algoritmi.

Azure uz-UZ neyro-ovozlari SOF ADABIY LOTIN-O'ZBEK matnini eng toza talaffuz
qiladi. Aksent/buzilish asosan matndagi "begona" elementlardan kelib chiqadi:

  1. RAQAMLAR       — TTS ularni ruscha/inglizcha ohangda o'qib yuborishi mumkin
                      -> to'liq o'zbekcha so'zlarga aylantiramiz
  2. KIRILL HARFLAR — rus so'zlari va kirill-o'zbek matn ruscha aksent beradi
                      -> lotinga transliteratsiya (rus so'zi ham o'zbek
                         fonetikasida o'qiladi: "заявка" -> "zayavka")
  3. MARKDOWN/EMOJI — yulduzcha, panjara va emoji "tovush" sifatida o'qilishi
                      yoki g'alati pauzalar berishi mumkin -> olib tashlaymiz
  4. QISQARTMALAR   — "kg", "km" kabilar noto'g'ri o'qiladi -> to'liq so'z
  5. VAQT/FOIZ      — "14:30", "50%" -> "o'n to'rt soat o'ttiz daqiqa", "ellik foiz"

Bu qatlam LLM chiqishi bilan TTS orasida turadi va har bir jumlaga qo'llanadi.
"""

import re

# ---------------------------------------------------------------------------
# 1. Markdown / emoji / texnik belgilarni tozalash
# ---------------------------------------------------------------------------

_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")          # [matn](url) -> matn
_URL = re.compile(r"https?://\S+")
_MD_MARKS = re.compile(r"[*_`#>|~]+")
_BULLET = re.compile(r"^\s*[-•]\s+", re.MULTILINE)
# Emoji va boshqa piktogramma bloklari
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF←-⇿⬀-⯿]+"
)


# O'zbek lotinidagi apostrof variantlari (o', g', tutuq belgisi) — Gemini turli
# belgilarni ishlatishi mumkin (’ ʻ ʼ ` ´). Azure TTS bir xil belgi kutadi,
# aralash apostroflar talaffuzni buzadi ("aksent" beradi) — hammasini ' ga
# keltiramiz.
_APOSTROPHES = str.maketrans({c: "'" for c in "’‘ʻʼ`´ʹʽ"})


def strip_markup(text: str) -> str:
    text = text.translate(_APOSTROPHES)
    text = _MD_LINK.sub(r"\1", text)
    text = _URL.sub("", text)
    text = _BULLET.sub("", text)
    text = _MD_MARKS.sub(" ", text)
    text = _EMOJI.sub("", text)
    text = text.replace("…", ".")
    return text


# ---------------------------------------------------------------------------
# 2. Kirill -> lotin transliteratsiya (o'zbek kirill + rus harflari)
# ---------------------------------------------------------------------------

_CYR2LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ё": "yo", "ж": "j",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
    "х": "x", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "'", "ы": "i",
    "ь": "", "э": "e", "ю": "yu", "я": "ya",
    # O'zbek kirillidagi maxsus harflar
    "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h",
}
_CYRILLIC_CHAR = re.compile(r"[Ѐ-ӿ]")


def translit_cyr_to_lat(text: str) -> str:
    if not _CYRILLIC_CHAR.search(text):
        return text
    out = []
    for i, ch in enumerate(text):
        low = ch.lower()
        if low == "е":
            # So'z boshida yoki unlidan keyin "ye", aks holda "e"
            prev = text[i - 1].lower() if i > 0 else " "
            lat = "ye" if (not prev.isalpha() or prev in "аеёиоуыэюяўъь") else "e"
        elif low in _CYR2LAT:
            lat = _CYR2LAT[low]
        else:
            out.append(ch)
            continue
        if ch.isupper() and lat:
            lat = lat[0].upper() + lat[1:]
        out.append(lat)
    return "".join(out)


# ---------------------------------------------------------------------------
# 3. Raqamlarni o'zbekcha so'zlarga aylantirish
# ---------------------------------------------------------------------------

_ONES = ["nol", "bir", "ikki", "uch", "to'rt", "besh", "olti", "yetti", "sakkiz", "to'qqiz"]
_TENS = ["", "o'n", "yigirma", "o'ttiz", "qirq", "ellik", "oltmish", "yetmish", "sakson", "to'qson"]
_SCALES = [(10**12, "trillion"), (10**9, "milliard"), (10**6, "million"), (10**3, "ming")]


def int_to_uz(n: int) -> str:
    """Butun sonni o'zbekcha so'zlarga aylantiradi: 245 -> "ikki yuz qirq besh"."""
    if n < 0:
        return "minus " + int_to_uz(-n)
    if n < 10:
        return _ONES[n]
    parts: list[str] = []
    for scale, name in _SCALES:
        if n >= scale:
            count = n // scale
            n %= scale
            # O'zbekchada "bir ming" emas, shunchaki "ming" deyiladi
            if scale == 1000 and count == 1:
                parts.append(name)
            else:
                parts.append(f"{int_to_uz(count)} {name}")
    if n >= 100:
        h = n // 100
        n %= 100
        parts.append("yuz" if h == 1 else f"{_ONES[h]} yuz")
    if n >= 10:
        parts.append(_TENS[n // 10])
        n %= 10
    if n > 0:
        parts.append(_ONES[n])
    return " ".join(parts)


def _ordinal(word: str) -> str:
    """So'z-son -> tartib son: "besh" -> "beshinchi", "yigirma" -> "yigirmanchi"."""
    return word + ("nchi" if word[-1] in "aeiou'" else "inchi")


_DECIMAL_DENOM = {1: "o'ndan", 2: "yuzdan", 3: "mingdan"}

_TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
_PERCENT_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*%")
_ORDINAL_RE = re.compile(r"\b(\d+)\s*-\s*(?=[A-Za-z'oOʻЀ-ӿ])")
_DECIMAL_RE = re.compile(r"\b(\d+)[.,](\d{1,3})\b")
_INT_RE = re.compile(r"\b\d+\b")


def _num_str_to_words(s: str) -> str:
    if "." in s or "," in s:
        whole, frac = re.split(r"[.,]", s, maxsplit=1)
        return _decimal_words(whole, frac)
    return int_to_uz(int(s))


def _decimal_words(whole: str, frac: str) -> str:
    denom = _DECIMAL_DENOM.get(len(frac), "mingdan")
    return f"{int_to_uz(int(whole))} butun {denom} {int_to_uz(int(frac))}"


def numbers_to_words(text: str) -> str:
    # 14:30 -> "o'n to'rt soat o'ttiz daqiqa" (00 daqiqa tushirib qoldiriladi)
    def _time(m: re.Match) -> str:
        h, mnt = int(m.group(1)), int(m.group(2))
        words = f"{int_to_uz(h)} soat"
        if mnt:
            words += f" {int_to_uz(mnt)} daqiqa"
        return words

    text = _TIME_RE.sub(_time, text)
    # 50% -> "ellik foiz"
    text = _PERCENT_RE.sub(lambda m: _num_str_to_words(m.group(1)) + " foiz", text)
    # 5-savol -> "beshinchi savol"
    text = _ORDINAL_RE.sub(lambda m: _ordinal(int_to_uz(int(m.group(1)))) + " ", text)
    # 2.5 -> "ikki butun o'ndan besh"
    text = _DECIMAL_RE.sub(lambda m: _decimal_words(m.group(1), m.group(2)), text)
    # 245 -> "ikki yuz qirq besh"
    text = _INT_RE.sub(lambda m: int_to_uz(int(m.group(0))), text)
    return text


# ---------------------------------------------------------------------------
# 4. Qisqartmalar
# ---------------------------------------------------------------------------

_ABBREVIATIONS = {
    "kg": "kilogramm",
    "km": "kilometr",
    "sm": "santimetr",
    "mm": "millimetr",
    "gr": "gramm",
    "mln": "million",
    "mlrd": "milliard",
}
# Eslatma: nuqta qisqartmaga qo'shilmaydi ("5 kg." -> "5 kilogramm.") — jumla
# oxiridagi nuqta saqlanib qolishi kerak
_ABBR_RE = re.compile(
    r"\b(" + "|".join(re.escape(a) for a in _ABBREVIATIONS) + r")\b", re.IGNORECASE
)


def expand_abbreviations(text: str) -> str:
    return _ABBR_RE.sub(lambda m: _ABBREVIATIONS[m.group(1).lower()], text)


# ---------------------------------------------------------------------------
# 5. O'zbek harflari: o'/g' va tutuq belgisini RASMIY imlo belgilariga keltirish
# ---------------------------------------------------------------------------
# Rasmiy o'zbek lotin imlosida:
#   oʻ, gʻ  — U+02BB (MODIFIER LETTER TURNED COMMA) bilan yoziladi
#   tutuq   — ʼ U+02BC (MODIFIER LETTER APOSTROPHE):  aʼlo, maʼno
# Azure uz-UZ ovozi shu imloda o'qitilgan. Oddiy ' (U+0027) berilsa, TTS uni
# TINISH BELGISI deb qabul qilib, "o'" birikmali so'zlarni buzib o'qiydi —
# foydalanuvchi sezgan "aksent"ning asosiy manbasi shu.
# Belgi turini .env dagi UZ_APOSTROPHE bilan almashtirish mumkin:
#   official (standart) = ʻ/ʼ,  straight = ',  right = ’

import os as _os

_APOSTROPHE_STYLES = {
    "official": ("ʻ", "ʼ"),   # oʻ gʻ / tutuq ʼ  (rasmiy imlo)
    "straight": ("'", "'"),
    "right": ("’", "’"),      # ’
}
_OG_RE = re.compile(r"([oOgG])'")
_TUTUQ_RE = re.compile(r"(?<=[a-zA-Z])'(?=[a-zA-Z])")

# Muammoli so'zlar uchun qo'lda talaffuz lug'ati — YOZILISHI emas, odamlar
# OG'ZAKI nutqda qanday talaffuz qilishiga qarab (kerak bo'lsa to'ldiriladi).
# Kalit — normalizatsiyadan keyingi so'z, qiymat — TTS ga beriladigan shakl.
PRONUNCIATION_FIXES: dict[str, str] = {
    # Salomlashuv: odamlar "alaykum" emas, "aleykum" deb talaffuz qiladi
    "alaykum": "aleykum",
    "vaalaykum": "vaaleykum",
}

# ---------------------------------------------------------------------------
# 6. ORFOEPIYA — o'zbek talaffuz grammatikasi (yozilishi != o'qilishi)
# ---------------------------------------------------------------------------
# Adabiy o'zbek orfoepiyasida ayrim harflar kontekstga qarab boshqacha
# talaffuz qilinadi. TTS harfma-harf o'qib yubormasligi uchun matnni
# TALAFFUZ shakliga keltiramiz:
#   - so'z oxiridagi "b"/"d" jarangsizlanadi (kitob -> kitop, ozod -> ozot),
#     LEKIN keyingi so'z UNLI bilan boshlansa jarangli qoladi ("aniqlab olamiz")
#   - jarangsiz undoshdan OLDINGI "v" -> "f":       avtobus -> aftobus, zayavka -> zayafka
#   - "n" + "b" assimilyatsiyasi -> "mb":           shanba -> shamba, dushanba -> dushamba
# .env da UZ_ORTHOEPY=off qilib o'chirish mumkin.

# b/d so'z oxirida, faqat keyin unli KELMASA (jumla oxiri, tinish belgisi,
# undosh bilan boshlanadigan so'z) jarangsizlanadi
_FINAL_B = re.compile(r"b\b(?!\s+[aeiouAEIOU])")
_FINAL_D = re.compile(r"d\b(?!\s+[aeiouAEIOU])")
_V_BEFORE_VOICELESS = re.compile(r"v(?=[ptkqsfxhc])")  # c: ch/ts digraflari boshi
_N_BEFORE_B = re.compile(r"n(?=b)")
# Ikki undosh orasidagi "t" og'zaki nutqda tushadi (adabiy orfoepiya):
# do'stlar -> do'slar, baxtli -> baxli, to'rtta -> to'rta
_T_BETWEEN_CONS = re.compile(r"(?<=[bcdfghjklmnpqrsvxz])t(?=[bcdfghjklmnpqrsvxz])")


def apply_orthoepy(text: str) -> str:
    if _os.getenv("UZ_ORTHOEPY", "on").lower() == "off":
        return text
    text = _FINAL_B.sub("p", text)
    text = _FINAL_D.sub("t", text)
    text = _V_BEFORE_VOICELESS.sub("f", text)
    text = _N_BEFORE_B.sub("m", text)
    text = _T_BETWEEN_CONS.sub("", text)
    return text


def fix_uzbek_letters(text: str) -> str:
    style = _os.getenv("UZ_APOSTROPHE", "official")
    og_mark, tutuq_mark = _APOSTROPHE_STYLES.get(style, _APOSTROPHE_STYLES["official"])
    # o' / g' -> oʻ / gʻ
    text = _OG_RE.sub(lambda m: m.group(1) + og_mark, text)
    # harflar orasida qolgan ' — tutuq belgisi (a'lo, ma'no)
    text = _TUTUQ_RE.sub(tutuq_mark, text)
    return text


# Foydalanuvchi to'ldiradigan talaffuz lug'ati: loyiha ildizidagi talaffuz.txt
# Har qator: "so'z = talaffuz". O'zgarish DARHOL kuchga kiradi (restart shart
# emas — fayl har o'zgarganda qayta o'qiladi).
_USER_DICT_PATH = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "talaffuz.txt"
)
_user_dict_cache: dict = {"mtime": None, "data": {}}


def _load_user_fixes() -> dict[str, str]:
    try:
        mtime = _os.path.getmtime(_USER_DICT_PATH)
    except OSError:
        return {}
    if _user_dict_cache["mtime"] != mtime:
        data = {}
        try:
            with open(_USER_DICT_PATH, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    # Kalit va qiymatni ham rasmiy imlo apostrofiga keltiramiz,
                    # chunki matn bu bosqichda allaqachon oʻ/gʻ ko'rinishida
                    k = fix_uzbek_letters(k.strip().translate(_APOSTROPHES))
                    v = fix_uzbek_letters(v.strip().translate(_APOSTROPHES))
                    if k:
                        data[k] = v
        except OSError:
            return _user_dict_cache["data"]
        _user_dict_cache["mtime"] = mtime
        _user_dict_cache["data"] = data
    return _user_dict_cache["data"]


def apply_pronunciation_fixes(text: str) -> str:
    fixes = {**PRONUNCIATION_FIXES, **_load_user_fixes()}
    for wrong, right in fixes.items():
        text = re.sub(rf"\b{re.escape(wrong)}\b", right, text, flags=re.IGNORECASE)
    return text


# ---------------------------------------------------------------------------
# Asosiy kirish nuqtasi
# ---------------------------------------------------------------------------

_MULTI_SPACE = re.compile(r"\s{2,}")
_MULTI_PUNCT = re.compile(r"([.!?,;:])\1+")


def normalize_for_tts(text: str) -> str:
    """LLM matnini Azure uz-UZ TTS uchun toza adabiy lotin-o'zbekka keltiradi."""
    text = strip_markup(text)          # markdown/emoji + apostroflarni ' ga birlashtirish
    text = translit_cyr_to_lat(text)   # kirill -> lotin
    text = expand_abbreviations(text)  # kg -> kilogramm
    text = numbers_to_words(text)      # 245 -> ikki yuz qirq besh
    text = apply_orthoepy(text)        # kitob -> kitop (talaffuz grammatikasi)
    text = fix_uzbek_letters(text)     # o' -> oʻ, g' -> gʻ, tutuq -> ʼ (rasmiy imlo)
    text = apply_pronunciation_fixes(text)
    text = _MULTI_PUNCT.sub(r"\1", text)
    text = _MULTI_SPACE.sub(" ", text)
    return text.strip()
