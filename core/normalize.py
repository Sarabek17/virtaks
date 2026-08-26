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
  6. ORFOEPIYA      — yozilishi != aytilishi: kitob -> kitop, ketdi -> ketti,
                      uchta -> ushta (nomlangan qoidalar, alohida o'chiriladi)
  7. LUG'AT         — qoida bilan tushuntirib bo'lmaydigan istisnolar
                      (talaffuz.txt: mashhur = mas-hur), qoidadan ustun
  8. IMLO           — o'/g' va tutuq rasmiy belgilar bilan (oʻ gʻ ʼ) — Azure
                      ovozi shu imloda o'qitilgan

Bu qatlam LLM chiqishi bilan TTS orasida turadi va har bir jumlaga qo'llanadi.
Sinov: python sinov_talaffuz.py (oltin fayl: talaffuz_oltin.txt).
Reja va qoidalar asosi: ORFOEPIYA_REJA.md.
"""

import re
from typing import Callable

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
# 5. TALAFFUZ LUG'ATI — istisnolar (qoida bilan tushuntirib bo'lmaydigan so'zlar)
# ---------------------------------------------------------------------------
# Lug'at so'zma-so'z ishlaydi va orfoepiya QOIDALARIDAN OLDIN qo'llanadi:
# lug'atda topilgan so'z yakuniy hisoblanadi, unga qoida tegmaydi (egasining
# qulog'i qoidadan ustun). Ikki xil yozuv:
#   so'z  = talaffuz     — faqat shu so'zning o'zi (mashhur = mas-hur)
#   so'z* = talaffuz     — O'ZAK: shu bilan boshlangan hamma shakl, qo'shimcha
#                          saqlanadi (mashhur* = mas-hur  ->  mashhurlik = mas-hurlik)
# Kalitlar registrga sezgir emas; so'z bosh harf bilan yozilgan bo'lsa,
# talaffuz ham bosh harf bilan chiqadi.
#
# Kod ichidagi asos lug'at — YOZILISHI emas, odamlar OG'ZAKI nutqda qanday
# talaffuz qilishiga qarab. Foydalanuvchi lug'ati (talaffuz.txt) ustun.

import os as _os

PRONUNCIATION_FIXES: dict[str, str] = {
    # Salomlashuv: odamlar "alaykum" emas, "aleykum" deb talaffuz qiladi
    "alaykum": "aleykum",
    "vaalaykum": "vaaleykum",
}

# Foydalanuvchi to'ldiradigan lug'at: loyiha ildizidagi talaffuz.txt.
# O'zgarish DARHOL kuchga kiradi (restart shart emas — fayl har o'zgarganda
# qayta o'qiladi).
_USER_DICT_PATH = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "talaffuz.txt"
)
_dict_cache: dict = {"mtime": None, "exact": {}, "stems": {}}


def parse_pronunciation_lines(lines) -> tuple[dict[str, str], dict[str, str]]:
    """Lug'at qatorlarini (exact, stems) juftligiga ajratadi.

    Apostroflar ' ga keltiriladi (matn ham bu bosqichda shu ko'rinishda),
    kalitlar kichik harfga. Bir harfli o'zak ma'nosiz — tashlab yuboriladi.
    """
    exact: dict[str, str] = {}
    stems: dict[str, str] = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().translate(_APOSTROPHES).lower()
        v = v.strip().translate(_APOSTROPHES)
        if k.endswith("*"):
            k = k[:-1].strip()
            if len(k) >= 2:
                stems[k] = v
        elif k:
            exact[k] = v
    return exact, stems


def _dictionaries() -> tuple[dict[str, str], dict[str, str]]:
    try:
        mtime = _os.path.getmtime(_USER_DICT_PATH)
    except OSError:
        mtime = None
    if _dict_cache["mtime"] != mtime or (mtime is None and not _dict_cache["exact"]):
        exact, stems = {}, {}
        if mtime is not None:
            try:
                with open(_USER_DICT_PATH, encoding="utf-8") as f:
                    exact, stems = parse_pronunciation_lines(f)
            except OSError:
                return _dict_cache["exact"], _dict_cache["stems"]
        _dict_cache["mtime"] = mtime
        _dict_cache["exact"] = {**PRONUNCIATION_FIXES, **exact}
        _dict_cache["stems"] = stems
    return _dict_cache["exact"], _dict_cache["stems"]


def lookup_pronunciation(word: str) -> str | None:
    """So'z lug'atda bo'lsa talaffuzini qaytaradi (o'zak bo'yicha ham), aks holda None."""
    exact, stems = _dictionaries()
    low = word.lower()
    hit = exact.get(low)
    if hit is None and stems:
        # Eng uzun o'zak birinchi: "mashhurlik" uchun "mashhur*" > "mash*"
        for i in range(len(low), 1, -1):
            stem = stems.get(low[:i])
            if stem is not None:
                hit = stem + low[i:]
                break
    if hit is None:
        return None
    if word[:1].isupper() and hit:
        hit = hit[:1].upper() + hit[1:]
    return hit


# ---------------------------------------------------------------------------
# 6. ORFOEPIYA — o'zbek talaffuz grammatikasi (yozilishi != o'qilishi)
# ---------------------------------------------------------------------------
# Adabiy o'zbek orfoepiyasida ayrim harflar kontekstga qarab boshqacha
# talaffuz qilinadi. TTS harfma-harf o'qib yubormasligi uchun so'zni TALAFFUZ
# shakliga keltiramiz. Qoidalar SO'Z darajasida, ko'rsatilgan TARTIBDA
# qo'llanadi (ochdi -> oshdi -> oshti); yagona so'zlararo kontekst — keyingi
# so'z unli bilan boshlanishi (so'z oxiridagi b/d/g jarangli qoladi).
#
# "h" ataylab jarangsizlar qatorida YO'Q: u zaif tovush, undan oldingi
# undoshni o'zgartirmaydi (mazhab, is'hoq).
#
# Har qoidaning nomi bor — eshitish sinovida birma-bir o'chirib ko'rish uchun:
#   UZ_ORTHOEPY=off                — hammasi o'chadi
#   UZ_ORTHOEPY_SKIP=shs,d_t       — faqat sanalganlari o'chadi

_VOWELS = "aeiou"
_DEVOICE = {"b": "p", "d": "t", "g": "k", "z": "s", "v": "f"}

# ch -> sh (t/d oldida): ochdi -> oshdi, uchta -> ushta, nechta -> neshta
_R_CH_SH = re.compile(r"ch(?=[td])")
# Jarangsiz undosh oldida jarangli jarangsizlanadi (c — ch boshi):
# avtobus -> aftobus, yozsa -> yossa, mazkur -> maskur, ovchi -> ofchi.
# "ng" — bitta tovush (eng, tengsiz, bizning): undagi g ga tegilmaydi.
_R_BEFORE_VOICELESS = re.compile(r"[bdzv](?=[ptkqsfxc])|(?<!n)g(?=[ptkqsfxc])")
# So'z oxirida b/d/g -> p/t/k (keyingi so'z unli bilan boshlanmasa):
# kitob -> kitop, ozod -> ozot, pedagog -> pedagok; "bog'" tegmaydi (g' alohida
# harf), "eng"/"qarang"/"bizning" tegmaydi (ng digrafi)
_R_FINAL_VOICED = re.compile(r"[bd]$|(?<!n)g$")
# d -> t jarangsiz undoshdan (shu jumladan sh/ch) keyin: ketdi -> ketti,
# otda -> otta, ishdan -> ishtan, tushdi -> tushti
_R_D_AFTER_VOICELESS = re.compile(r"(?<=[ptkqsfx])d|(?<=[sc]h)d")
# n -> m lab undoshlari oldida: shanba -> shamba, yonbosh -> yombosh
_R_N_M = re.compile(r"n(?=[bp])")
# sh + s -> shsh: ishsiz -> ishshiz, tushsa -> tushsha (allaqachon shsh bo'lsa tegmaydi)
_R_SHS = re.compile(r"shs(?!h)")
# s/sh/x/f/n/k/q dan keyingi "t" qo'shimcha boshlovchi undosh (l d n m g s t)
# oldida tushadi: do'stlar -> do'slar, baxtli -> baxli, Toshkentga ->
# Toshkenga, vaqtli -> vaqli, aktsiya -> aksiya. "r" dan keyin faqat ikkinchi
# "t" oldida: to'rtta -> to'rta (buyurtma, shartli, partnyor buzilmaydi).
# Boshqa undosh oldida QOLADI — aks holda o'zlashma so'zlar buziladi
# (strategiya, elektr, instrument).
_R_T_DROP = re.compile(r"(?<=[sxfnkqh])t(?=[ldnmgst])|(?<=r)t(?=t)")


def _rule_final_voiced(word: str, next_vowel: bool) -> str:
    if next_vowel:
        return word
    return _R_FINAL_VOICED.sub(lambda m: _DEVOICE[m.group(0)], word)


# (nom, funksiya) — TARTIB MUHIM
OrthoepyRule = Callable[[str, bool], str]
ORTHOEPY_RULES: list[tuple[str, OrthoepyRule]] = [
    ("ch_sh", lambda w, nv: _R_CH_SH.sub("sh", w)),
    ("jarangsiz_oldida", lambda w, nv: _R_BEFORE_VOICELESS.sub(lambda m: _DEVOICE[m.group(0)], w)),
    ("oxiri_jarangsiz", _rule_final_voiced),
    ("d_t", lambda w, nv: _R_D_AFTER_VOICELESS.sub("t", w)),
    ("n_m", lambda w, nv: _R_N_M.sub("m", w)),
    ("shs", lambda w, nv: _R_SHS.sub("shsh", w)),
    ("t_tushadi", lambda w, nv: _R_T_DROP.sub("", w)),
]


def active_orthoepy_rules() -> list[tuple[str, OrthoepyRule]]:
    if _os.getenv("UZ_ORTHOEPY", "on").lower() == "off":
        return []
    skip = {s.strip() for s in _os.getenv("UZ_ORTHOEPY_SKIP", "").split(",") if s.strip()}
    return [(n, f) for n, f in ORTHOEPY_RULES if n not in skip]


def orthoepy_word(word: str, next_vowel: bool = False, rules=None) -> str:
    """Bitta so'zni talaffuz shakliga keltiradi (lug'atsiz, faqat qoidalar)."""
    for _, fn in (active_orthoepy_rules() if rules is None else rules):
        word = fn(word, next_vowel)
    return word


def orthoepy_trace(word: str, next_vowel: bool = False) -> list[tuple[str, str]]:
    """Qaysi qoida so'zni o'zgartirganini ko'rsatadi: [(qoida_nomi, natija), ...]."""
    trace = []
    for name, fn in active_orthoepy_rules():
        new = fn(word, next_vowel)
        if new != word:
            trace.append((name, new))
            word = new
    return trace


# So'z: harflar, ichida yoki oxirida ' bo'lishi mumkin (to'g'ri, bog', a'lo).
# Raqamlar bu bosqichda allaqachon so'zga aylangan.
_WORD_RE = re.compile(r"[^\W\d_]+(?:'[^\W\d_]*)*")


def apply_pronunciation(text: str) -> str:
    """Matnni so'zlarga bo'lib: lug'at (ustun) yoki orfoepiya qoidalarini qo'llaydi.

    Chiziqli: har so'z bir marta ko'riladi, lug'at hajmi tezlikka ta'sir
    qilmaydi (10 000 yozuv ham, 100 000 ham).
    """
    rules = active_orthoepy_rules()
    matches = list(_WORD_RE.finditer(text))
    out = []
    pos = 0
    for k, m in enumerate(matches):
        out.append(text[pos:m.start()])
        word = m.group(0)
        fixed = lookup_pronunciation(word)
        if fixed is None:
            next_vowel = False
            if k + 1 < len(matches):
                nxt = matches[k + 1]
                between = text[m.end():nxt.start()]
                # Faqat bo'shliq bo'lsa — bir nafasda aytiladi; tinish belgisi
                # bo'lsa pauza bor, so'z oxiri jarangsizlanadi
                next_vowel = between.isspace() and nxt.group(0)[0].lower() in _VOWELS
            fixed = orthoepy_word(word, next_vowel, rules)
        out.append(fixed)
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


def apply_orthoepy(text: str) -> str:
    """Faqat qoidalar, lug'atsiz (korpus hisobotlari uchun)."""
    rules = active_orthoepy_rules()
    matches = list(_WORD_RE.finditer(text))
    out, pos = [], 0
    for k, m in enumerate(matches):
        out.append(text[pos:m.start()])
        next_vowel = False
        if k + 1 < len(matches):
            nxt = matches[k + 1]
            between = text[m.end():nxt.start()]
            next_vowel = between.isspace() and nxt.group(0)[0].lower() in _VOWELS
        out.append(orthoepy_word(m.group(0), next_vowel, rules))
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


# ---------------------------------------------------------------------------
# 7. O'zbek harflari: o'/g' va tutuq belgisini RASMIY imlo belgilariga keltirish
# ---------------------------------------------------------------------------
# Rasmiy o'zbek lotin imlosida:
#   oʻ, gʻ  — U+02BB (MODIFIER LETTER TURNED COMMA) bilan yoziladi
#   tutuq   — ʼ U+02BC (MODIFIER LETTER APOSTROPHE):  aʼlo, maʼno
# Azure uz-UZ ovozi shu imloda o'qitilgan. Oddiy ' (U+0027) berilsa, TTS uni
# TINISH BELGISI deb qabul qilib, "o'" birikmali so'zlarni buzib o'qiydi —
# foydalanuvchi sezgan "aksent"ning asosiy manbasi shu.
# Belgi turini .env dagi UZ_APOSTROPHE bilan almashtirish mumkin:
#   official (standart) = ʻ/ʼ,  straight = ',  right = ’

_APOSTROPHE_STYLES = {
    "official": ("ʻ", "ʼ"),   # oʻ gʻ / tutuq ʼ  (rasmiy imlo)
    "straight": ("'", "'"),
    "right": ("’", "’"),      # ’
}
_OG_RE = re.compile(r"([oOgG])'")
_TUTUQ_RE = re.compile(r"(?<=[a-zA-Z])'(?=[a-zA-Z])")


def fix_uzbek_letters(text: str) -> str:
    style = _os.getenv("UZ_APOSTROPHE", "official")
    og_mark, tutuq_mark = _APOSTROPHE_STYLES.get(style, _APOSTROPHE_STYLES["official"])
    # o' / g' -> oʻ / gʻ
    text = _OG_RE.sub(lambda m: m.group(1) + og_mark, text)
    # harflar orasida qolgan ' — tutuq belgisi (a'lo, ma'no)
    text = _TUTUQ_RE.sub(tutuq_mark, text)
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
    text = apply_pronunciation(text)   # lug'at (ustun) + orfoepiya: kitob -> kitop
    text = fix_uzbek_letters(text)     # o' -> oʻ, g' -> gʻ, tutuq -> ʼ (rasmiy imlo)
    text = _MULTI_PUNCT.sub(r"\1", text)
    text = _MULTI_SPACE.sub(" ", text)
    return text.strip()
