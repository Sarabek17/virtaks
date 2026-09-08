# -*- coding: utf-8 -*-
"""B2B yadrosi: API kalitlari, tashkilot izolyatsiyasi, balans.

Reja: `B2B_API_REJA.md`.

Bu modul `llm` ni IMPORT QILMAYDI — pul yo'lidagi qoida (`pul.py`,
`tolov.py` bilan bir xil, `sinov_b2b.py` statik tekshiradi). Bu yerda
faqat kim so'rayapti, nimaga ruxsati bor va puli yetadimi degan savollarga
javob beriladi.

Uch qat'iy qoida:

1. **Izolyatsiya bitta joyda.** Har so'rov `tekshir()` dan o'tadi va
   `Kontekst` oladi; barcha so'rovlar shu kontekstning `tashkilot_id` si
   bilan filtrlanadi. Boshqa tashkilotning resursi 403 emas, **404**
   qaytaradi — mavjudligini ham oshkor qilmaymiz.
2. **Kalitning o'zi saqlanmaydi** — faqat prefiks va argon2 xeshi.
3. **Balans faqat daftar orqali** (`balans_harakat`) o'zgaradi, hech
   qachon to'g'ridan-to'g'ri UPDATE bilan emas.
"""
import hashlib
import secrets
import time
from dataclasses import dataclass, field

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from . import pg
from .sozlama import PROD, log

_ph = PasswordHasher()

PREFIKS_UZUNLIK = 6          # vk_live_XXXXXX
SIR_UZUNLIK = 32
HUQUQLAR = {"savol", "suhbat", "fragment", "hisob", "twinlar"}

# Kalit tekshiruvining keshi: argon2 ataylab SEKIN (~50 ms), har SSE
# so'rovida uni qayta hisoblash oqim boshlanishini kechiktirardi.
# Kesh faqat MUVAFFAQIYATLI tekshiruvni saqlaydi va qisqa yashaydi —
# kalit o'chirilsa eng ko'pi bilan shuncha vaqt ishlaydi.
#
# ⚠️ KESH KALITI SIRNI HAM O'Z ICHIGA OLADI. Avval u faqat `prefiks` edi va
# bu AUTENTIFIKATSIYA TESHIGI bo'lgan: to'g'ri prefiks + noto'g'ri sir bilan
# kelgan so'rov keshdan o'tib ketardi (sinovda topilgan). sha256 bu yerda
# parol xeshi sifatida emas, faqat kesh kaliti sifatida ishlatiladi —
# haqiqiy tekshiruv baribir argon2 bilan bo'ladi.
_KESH_S = 60
_kesh: dict[str, tuple[float, int]] = {}      # kesh_kaliti -> (vaqt, kalit_id)


def _kesh_kaliti(prefiks: str, sir: str) -> str:
    return prefiks + ":" + hashlib.sha256(sir.encode()).hexdigest()


# ---------------------------------------------------------------- kontekst

@dataclass
class Kontekst:
    """Bitta API so'rovining kimligi. Endpointlar faqat shu bilan ishlaydi."""
    tashkilot_id: int
    tashkilot: dict
    kalit_id: int
    huquqlar: list[str] = field(default_factory=list)

    def huquq(self, nom: str) -> bool:
        return nom in self.huquqlar


# ---------------------------------------------------------------- kalitlar

def kalit_yasa(tashkilot_id: int, nom: str = "", huquqlar: list[str] | None = None,
               ip_oq: list[str] | None = None, muddat=None,
               yaratgan_id: int | None = None) -> tuple[str, dict]:
    """Yangi kalit. (ochiq_kalit, yozuv) — ochiq kalit FAQAT SHU YERDA ko'rinadi.

    Format: vk_live_<prefiks>_<sir>. Prefiks bazada ochiq turadi (indeks
    bo'yicha topamiz), sir esa faqat argon2 xeshi bo'lib saqlanadi.
    """
    muhit = "live" if PROD else "sinov"
    prefiks = secrets.token_hex(PREFIKS_UZUNLIK // 2)
    sir = secrets.token_urlsafe(SIR_UZUNLIK)[:SIR_UZUNLIK]
    ochiq = f"vk_{muhit}_{prefiks}_{sir}"

    h = [q for q in (huquqlar or sorted(HUQUQLAR)) if q in HUQUQLAR]
    r = pg.bitta_d(
        """INSERT INTO api_kalitlar(tashkilot_id, nom, prefiks, hash, huquqlar,
                                    ip_oq, muddat, yaratgan_id)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        tashkilot_id, nom.strip()[:60], prefiks, _ph.hash(sir), h,
        ip_oq or [], muddat, yaratgan_id)
    log(f"B2B kalit yasaldi: tashkilot={tashkilot_id} prefiks={prefiks}")
    return ochiq, r


def _kalitni_ajrat(xom: str) -> tuple[str, str] | None:
    """'vk_live_abc123_SIR' -> ('abc123', 'SIR'). Format buzilsa None.

    DIQQAT — `maxsplit=3` MAJBURIY: sir `secrets.token_urlsafe` dan keladi,
    uning alifbosida `_` BOR. Oddiy `split("_")` bilan bunday kalit 4 dan
    ortiq bo'lakka bo'linib, yaroqli kalit rad etilardi (kalitlarning
    taxminan 40% i). Sinovda topilgan.
    """
    q = (xom or "").strip()
    if not q.startswith("vk_"):
        return None
    bolak = q.split("_", 3)
    if len(bolak) != 4 or not bolak[2] or not bolak[3]:
        return None
    return bolak[2], bolak[3]


def kalit_tekshir(xom: str) -> dict | None:
    """Ochiq kalitdan `api_kalitlar` yozuvini qaytaradi. Yaroqsiz bo'lsa None."""
    juft = _kalitni_ajrat(xom)
    if not juft:
        return None
    prefiks, sir = juft

    r = pg.bitta_d(
        """SELECT k.*, t.faol AS tashkilot_faol
           FROM api_kalitlar k JOIN tashkilotlar t ON t.id = k.tashkilot_id
           WHERE k.prefiks = %s""", prefiks)
    if not r or not r["faol"] or not r["tashkilot_faol"]:
        return None
    if r["muddat"] and r["muddat"].timestamp() < time.time():
        return None

    kk = _kesh_kaliti(prefiks, sir)
    keshda = _kesh.get(kk)
    if keshda and keshda[0] > time.time() and keshda[1] == r["id"]:
        return r
    try:
        _ph.verify(r["hash"], sir)
    except VerifyMismatchError:
        return None
    except Exception as e:                          # noqa: BLE001
        log(f"B2B kalit xeshi o'qilmadi (prefiks={prefiks}): {str(e)[:80]}")
        return None
    _kesh[kk] = (time.time() + _KESH_S, r["id"])
    return r


def kalit_ochir(kalit_id: int):
    r = pg.bitta("UPDATE api_kalitlar SET faol=false WHERE id=%s RETURNING prefiks",
                 kalit_id)
    if r:
        # Kesh kaliti "prefiks:sha256(sir)" — shu prefiksdagi hamma yozuvni
        # tashlaymiz, o'chirilgan kalit bir soniya ham ishlab turmasin.
        bosh = r[0] + ":"
        for k in [q for q in _kesh if q.startswith(bosh)]:
            _kesh.pop(k, None)


def _ip(request) -> str:
    """Mijoz IP si. Caddy `X-Forwarded-For` ni O'ZI qayta yozadi (soxtalashtirib
    bo'lmaydi) — sabab `DEPLOY_DO.md` §12 da."""
    bosh = request.headers.get("x-forwarded-for", "")
    if bosh:
        return bosh.split(",")[0].strip()[:45]
    return (request.client.host if request.client else "")[:45]


def tekshir(request) -> Kontekst | None:
    """So'rovni autentifikatsiya qiladi. Bu YAGONA kirish eshigi.

    Cookie sessiyasiga UMUMAN qaramaydi: API kaliti hech qachon admin yoki
    kabinet yo'llarini ochmasligi kerak.
    """
    bosh = request.headers.get("authorization", "")
    if not bosh.lower().startswith("bearer "):
        return None
    k = kalit_tekshir(bosh[7:].strip())
    if not k:
        return None

    # IP oq ro'yxati (bo'sh bo'lsa filtr o'chiq)
    if k["ip_oq"] and _ip(request) not in k["ip_oq"]:
        log(f"B2B: IP ro'yxatdan tashqari, prefiks={k['prefiks']}")
        return None

    t = pg.bitta_d("SELECT * FROM tashkilotlar WHERE id=%s", k["tashkilot_id"])
    if not t or not t["faol"]:
        return None

    # `oxirgi_ishlatilgan` faqat kuniga bir marta yangilanadi: har so'rovda
    # UPDATE qilish bitta qatorga yozuv poygasini yasab, oqimni sekinlashtiradi.
    if (not k["oxirgi_ishlatilgan"]
            or (time.time() - k["oxirgi_ishlatilgan"].timestamp()) > 86400):
        pg.bajar("UPDATE api_kalitlar SET oxirgi_ishlatilgan=now() WHERE id=%s",
                 k["id"])

    return Kontekst(tashkilot_id=t["id"], tashkilot=t, kalit_id=k["id"],
                    huquqlar=list(k["huquqlar"] or []))


# ------------------------------------------------------------ tashkilotlar

def tashkilot_ol(tid: int) -> dict | None:
    return pg.bitta_d("SELECT * FROM tashkilotlar WHERE id=%s", tid)


def tashkilot_yasa(nom: str, slug: str, **f) -> dict:
    return pg.bitta_d(
        """INSERT INTO tashkilotlar(nom, slug, aloqa_email, aloqa_tg, ustama,
                                    kredit_chegara_usd, ogohlantirish_usd,
                                    oqim_limit, daqiqa_limit, oylik_chegara_usd,
                                    izoh)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        nom.strip()[:120], slug.strip().lower()[:60], f.get("aloqa_email", ""),
        f.get("aloqa_tg"), f.get("ustama", 3.0), f.get("kredit_chegara_usd", 0),
        f.get("ogohlantirish_usd", 5), f.get("oqim_limit", 5),
        f.get("daqiqa_limit", 60), f.get("oylik_chegara_usd", 0),
        f.get("izoh", ""))


def twinlar(tashkilot_id: int) -> list[dict]:
    """Shu tashkilotga ochilgan FAOL twinlar."""
    return pg.hammasi_d(
        """SELECT t.id, t.nom, t.slug, t.tavsif, t.avatar
           FROM tashkilot_twin tt JOIN twinlar t ON t.id = tt.twin_id
           WHERE tt.tashkilot_id=%s AND tt.faol AND t.faol
           ORDER BY t.tartib, t.id""", tashkilot_id)


def twin_ruxsat(tashkilot_id: int, twin: str | int) -> dict | None:
    """Slug yoki id bo'yicha twin — FAQAT shu tashkilotga ochilganlaridan.

    Ro'yxatda yo'q bo'lsa None; chaqiruvchi 404 qaytaradi (403 EMAS —
    twin mavjudligini ham bildirmaymiz).
    """
    if isinstance(twin, int) or (isinstance(twin, str) and twin.isdigit()):
        shart, qiymat = "t.id = %s", int(twin)
    else:
        shart, qiymat = "t.slug = %s", str(twin).strip().lower()
    return pg.bitta_d(
        f"""SELECT t.* FROM tashkilot_twin tt JOIN twinlar t ON t.id = tt.twin_id
            WHERE tt.tashkilot_id=%s AND tt.faol AND t.faol AND {shart}""",
        tashkilot_id, qiymat)


def twin_qosh(tashkilot_id: int, twin_id: int):
    pg.bajar(
        """INSERT INTO tashkilot_twin(tashkilot_id, twin_id) VALUES(%s,%s)
           ON CONFLICT (tashkilot_id, twin_id) DO UPDATE SET faol=true""",
        tashkilot_id, twin_id)


def twin_ochir(tashkilot_id: int, twin_id: int):
    pg.bajar("UPDATE tashkilot_twin SET faol=false WHERE tashkilot_id=%s AND twin_id=%s",
             tashkilot_id, twin_id)


# ----------------------------------------------------- soya foydalanuvchilar

ISM_MAKS = 60
TASHQI_MAKS = 120


def foydalanuvchi(tashkilot_id: int, tashqi_id: str, ism: str = "") -> dict:
    """Hamkorning mijozini topadi yoki yaratadi (idempotent).

    `tashqi_id` — hamkorning O'Z bazasidagi ID si. U promptga HECH QACHON
    kirmaydi; `ism` esa faqat ko'rsatish uchun va promptda ramkalanadi.
    """
    tid = (tashqi_id or "").strip()[:TASHQI_MAKS]
    if not tid:
        raise ValueError("tashqi_id bo'sh")
    ism = (ism or "").strip()[:ISM_MAKS] or "Foydalanuvchi"

    r = pg.bitta_d(
        """INSERT INTO userlar(tashkilot_id, tashqi_id, ism, rol, manba)
           VALUES(%s,%s,%s,'client','api')
           ON CONFLICT (tashkilot_id, tashqi_id)
             WHERE tashkilot_id IS NOT NULL
           DO UPDATE SET oxirgi_kirish = now()
           RETURNING *, (xmax = 0) AS yangi""",
        tashkilot_id, tid, ism)
    return r


def foydalanuvchi_ol(tashkilot_id: int, user_id: int) -> dict | None:
    """User faqat SHU tashkilotniki bo'lsa qaytadi (izolyatsiya)."""
    return pg.bitta_d(
        "SELECT * FROM userlar WHERE id=%s AND tashkilot_id=%s",
        user_id, tashkilot_id)


# ------------------------------------------------------------------- balans

def balans_yetadimi(t: dict) -> tuple[bool, str]:
    """So'rovni boshlashga puli yetadimi. Hech narsa sarflamaydi.

    Tekshiruv LLM chaqirilishidan OLDIN bo'ladi — balans tugagan hamkor
    uchun model umuman ishga tushmaydi.
    """
    balans = float(t["balans_usd"])
    kredit = float(t["kredit_chegara_usd"])
    if balans + kredit <= 0:
        return False, (f"Balans tugadi ({balans:.2f} USD). "
                       f"Hisobni to'ldiring.")
    chegara = float(t["oylik_chegara_usd"] or 0)
    if chegara > 0 and oylik_sarf(t["id"]) >= chegara:
        return False, (f"Oylik chegara tugadi ({chegara:.2f} USD). "
                       f"Chegarani oshirish uchun bog'laning.")
    return True, ""


def oylik_sarf(tashkilot_id: int) -> float:
    r = pg.bitta(
        """SELECT COALESCE(sum(hisob_usd), 0) FROM xarajatlar
           WHERE tashkilot_id=%s AND vaqt >= date_trunc('month', now())""",
        tashkilot_id)
    return float(r[0]) if r else 0.0


def balans_harakat(tashkilot_id: int, tur: str, summa_usd: float,
                   xarajat_id: int | None = None, izoh: str = "") -> float:
    """Balansni O'ZGARTIRADIGAN YAGONA funksiya. Yangi qoldiqni qaytaradi.

    Bitta tranzaksiyada: qatorni qulflaymiz, yangilaymiz, daftarga yozamiz.
    `FOR UPDATE` bo'lmasa parallel ikki so'rov bir xil qoldiqni o'qib,
    daftarda uzilish hosil qilardi (pul.tolandi dagi naqsh).
    """
    if summa_usd == 0:
        return float(tashkilot_ol(tashkilot_id)["balans_usd"])
    with pg.ulanish() as u, u.cursor() as k:
        k.execute("SELECT balans_usd FROM tashkilotlar WHERE id=%s FOR UPDATE",
                  (tashkilot_id,))
        qator = k.fetchone()
        if not qator:
            raise ValueError(f"tashkilot #{tashkilot_id} yo'q")
        yangi = float(qator[0]) + float(summa_usd)
        k.execute("UPDATE tashkilotlar SET balans_usd=%s WHERE id=%s",
                  (yangi, tashkilot_id))
        k.execute(
            """INSERT INTO balans_harakat(tashkilot_id, tur, summa_usd,
                                          qoldiq_usd, xarajat_id, izoh)
               VALUES(%s,%s,%s,%s,%s,%s)""",
            (tashkilot_id, tur, summa_usd, yangi, xarajat_id, izoh[:200]))
    return yangi


def sarf_yoz(tashkilot_id: int, xarajat_id: int, narx_usd: float,
             bosqich: str = "") -> float:
    """Tannarxni hamkor hisobiga o'giradi va balansdan yechadi. `hisob_usd` qaytadi.

    HAMMASI BITTA TRANZAKSIYADA: tashkilot qatori qulflanadi, ustama o'qiladi,
    `xarajatlar.hisob_usd` to'ldiriladi, balans yangilanadi va daftarga yozuv
    tushadi. Bo'lib bajarilsa parallel chaqiruvlar orasida qoldiq uzilib
    qolardi (`pul.tolandi` dagi FOR UPDATE naqshi).

    USTAMA SHU YERDA QOTIRILADI: shartnoma keyin o'zgarsa ham o'tgan davrning
    hisobi qayta hisoblanmaydi.
    """
    if narx_usd <= 0:
        return 0.0
    with pg.ulanish() as u, u.cursor() as k:
        k.execute("""SELECT balans_usd, ustama FROM tashkilotlar
                     WHERE id=%s FOR UPDATE""", (tashkilot_id,))
        qator = k.fetchone()
        if not qator:
            raise ValueError(f"tashkilot #{tashkilot_id} yo'q")
        balans, ustama = float(qator[0]), float(qator[1])
        hisob = round(narx_usd * ustama, 6)
        yangi_balans = round(balans - hisob, 6)

        k.execute("UPDATE xarajatlar SET hisob_usd=%s WHERE id=%s",
                  (hisob, xarajat_id))
        k.execute("UPDATE tashkilotlar SET balans_usd=%s WHERE id=%s",
                  (yangi_balans, tashkilot_id))
        k.execute(
            """INSERT INTO balans_harakat(tashkilot_id, tur, summa_usd,
                                          qoldiq_usd, xarajat_id, izoh)
               VALUES(%s,'sarf',%s,%s,%s,%s)""",
            (tashkilot_id, -hisob, yangi_balans, xarajat_id, (bosqich or "")[:200]))
    return hisob


def toldir(tashkilot_id: int, summa_usd: float, izoh: str = "") -> float:
    """Admin qo'lda to'ldiradi (bank o'tkazmasidan keyin)."""
    if summa_usd <= 0:
        raise ValueError("summa musbat bo'lishi kerak")
    yangi = balans_harakat(tashkilot_id, "toldirish", summa_usd, izoh=izoh)
    log(f"B2B balans to'ldirildi: tashkilot={tashkilot_id} "
        f"+{summa_usd:.2f} -> {yangi:.2f}")
    return yangi


def hisob(tashkilot_id: int) -> dict:
    """Hamkor ko'radigan hisob. TANNARX (`narx_usd`) BU YERGA CHIQMAYDI."""
    t = tashkilot_ol(tashkilot_id)
    if not t:
        return {}
    oy = pg.bitta_d(
        """SELECT COALESCE(sum(hisob_usd),0) AS sarf, count(*) AS chaqiruv
           FROM xarajatlar
           WHERE tashkilot_id=%s AND vaqt >= date_trunc('month', now())""",
        tashkilot_id)
    savol = pg.bitta(
        """SELECT count(*) FROM majlislar m JOIN userlar u ON u.id = m.user_id
           WHERE u.tashkilot_id=%s AND m.vaqt >= date_trunc('month', now())""",
        tashkilot_id)
    return {
        "balans_usd": round(float(t["balans_usd"]), 4),
        "kredit_chegara_usd": round(float(t["kredit_chegara_usd"]), 4),
        "oylik_chegara_usd": round(float(t["oylik_chegara_usd"] or 0), 4),
        "joriy_oy": {
            "sarf_usd": round(float(oy["sarf"]), 4),
            "savollar": int(savol[0]) if savol else 0,
        },
        "ogohlantirish_usd": round(float(t["ogohlantirish_usd"]), 4),
        "balans_past": (float(t["balans_usd"])
                        <= float(t["ogohlantirish_usd"])),
    }


def hisobot(tashkilot_id: int, oy: str = "") -> dict:
    """Oylik hisob-faktura ma'lumoti. TANNARX CHIQMAYDI.

    `oy` — "YYYY-MM"; bo'sh bo'lsa joriy oy. Alohida jadval ATAYLAB yo'q:
    `xarajatlar` va `balans_harakat` da hamma narsa bor, ikkinchi nusxa esa
    ular bilan chalkashib ketardi.
    """
    if oy and len(oy) == 7 and oy[4] == "-" and oy[:4].isdigit():
        bosh_sql = "%s-01"
        davr = oy
    else:
        davr = None
        bosh_sql = None

    if davr:
        shart = ("x.vaqt >= %s::date AND x.vaqt < (%s::date + interval '1 month')")
        args = (tashkilot_id, bosh_sql % davr, bosh_sql % davr)
    else:
        shart = "x.vaqt >= date_trunc('month', now())"
        args = (tashkilot_id,)

    umumiy = pg.bitta_d(
        f"""SELECT COALESCE(sum(x.hisob_usd),0) AS hisob,
                   count(*) AS chaqiruv,
                   count(DISTINCT x.majlis_id) FILTER (WHERE x.majlis_id IS NOT NULL)
                     AS savollar,
                   count(DISTINCT x.user_id) AS mijozlar
            FROM xarajatlar x WHERE x.tashkilot_id=%s AND {shart}""", *args)

    twinlar_b = pg.hammasi_d(
        f"""SELECT t.nom, COALESCE(sum(x.hisob_usd),0) AS hisob,
                   count(DISTINCT x.majlis_id) AS savollar
            FROM xarajatlar x JOIN twinlar t ON t.id = x.twin_id
            WHERE x.tashkilot_id=%s AND {shart}
            GROUP BY t.nom ORDER BY 2 DESC""", *args)

    t = tashkilot_ol(tashkilot_id)
    return {
        "tashkilot": t["nom"] if t else "",
        "davr": davr or "joriy_oy",
        "savollar": int(umumiy["savollar"] or 0),
        "mijozlar": int(umumiy["mijozlar"] or 0),
        "chaqiruvlar": int(umumiy["chaqiruv"] or 0),
        "jami_usd": round(float(umumiy["hisob"]), 4),
        "twinlar": [{"nom": q["nom"], "savollar": int(q["savollar"]),
                     "usd": round(float(q["hisob"]), 4)} for q in twinlar_b],
        "balans_usd": round(float(t["balans_usd"]), 4) if t else 0.0,
    }


def royalti(kun: int = 30) -> list[dict]:
    """Twin egalariga tegadigan ulush (FAQAT admin uchun).

    Asos — B2B hisobi (`hisob_usd`), tannarx emas: ustoz bizning
    xarajatimizdan emas, DAROMADIMIZDAN ulush oladi.
    B2C obunasi bu yerga kirmaydi — u so'rov emas, oylik to'lov; uning
    ulushi boshqa asosda hisoblanadi (hali kelishilmagan).
    """
    return pg.hammasi_d(
        """SELECT t.id, t.nom, t.royalti_foiz,
                  u.ism AS egasi, u.id AS egasi_id,
                  COALESCE(sum(x.hisob_usd),0) AS b2b_usd,
                  round(COALESCE(sum(x.hisob_usd),0) * t.royalti_foiz / 100, 4)
                    AS ulush_usd,
                  count(DISTINCT x.majlis_id) AS savollar
           FROM twinlar t
           LEFT JOIN userlar u ON u.id = t.egasi_id
           LEFT JOIN xarajatlar x ON x.twin_id = t.id
                AND x.tashkilot_id IS NOT NULL
                AND x.vaqt > now() - (%s || ' days')::interval
           GROUP BY t.id, t.nom, t.royalti_foiz, u.ism, u.id
           HAVING COALESCE(sum(x.hisob_usd),0) > 0 OR t.royalti_foiz > 0
           ORDER BY 6 DESC""", kun)


def harakatlar(tashkilot_id: int, chegara: int = 50) -> list[dict]:
    return pg.hammasi_d(
        """SELECT id, vaqt, tur, summa_usd, qoldiq_usd, izoh
           FROM balans_harakat WHERE tashkilot_id=%s
           ORDER BY id DESC LIMIT %s""", tashkilot_id, min(chegara, 500))


# ------------------------------------------------------------ idempotentlik

IDEMPOTENT_SAQLASH_S = 24 * 3600


def idempotent_ol(tashkilot_id: int, kalit: str) -> dict | None:
    if not kalit:
        return None
    return pg.bitta_d(
        """SELECT javob, holat FROM api_idempotent
           WHERE tashkilot_id=%s AND kalit=%s
             AND vaqt > now() - interval '24 hours'""",
        tashkilot_id, kalit.strip()[:120])


def idempotent_yoz(tashkilot_id: int, kalit: str, javob: dict, holat: int = 200):
    if not kalit:
        return
    import json
    pg.bajar(
        """INSERT INTO api_idempotent(tashkilot_id, kalit, javob, holat)
           VALUES(%s,%s,%s,%s)
           ON CONFLICT (tashkilot_id, kalit) DO UPDATE
             SET javob=EXCLUDED.javob, holat=EXCLUDED.holat, vaqt=now()""",
        tashkilot_id, kalit.strip()[:120],
        json.dumps(javob, ensure_ascii=False), holat)


def idempotent_tozala() -> int:
    """Eskirgan yozuvlarni o'chiradi (worker davriy ishi)."""
    r = pg.bitta(
        """WITH o AS (DELETE FROM api_idempotent
                      WHERE vaqt < now() - interval '48 hours' RETURNING 1)
           SELECT count(*) FROM o""")
    return int(r[0]) if r else 0
