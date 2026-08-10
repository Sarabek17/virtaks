# -*- coding: utf-8 -*-
"""To'lov adapterlari: Paylov (asosiy), Click (SHOP API), Payme (Merchant JSON-RPC).

XAVFSIZLIK — "Lethal Trifecta":
Bu endpointlar internetdan, ISHONCHSIZ manbadan so'rov qabul qiladi.
Shuning uchun ular butunlay LLM'siz zona:

  * Bu fayl `llm`/`agentlar`/`majlis` ni import QILMAYDI (sinovda tekshiriladi).
  * Kelgan so'rovdagi HECH BIR qiymat promptga tushmaydi.
  * Summa mijozdan EMAS, o'z bazamizdagi `tolovlar.summa_som` dan olinadi va
    solishtiriladi — provayder yuborgan summa faqat tekshiruv uchun.
  * Imzo/auth tekshirilmasa, hech qanday holat o'zgarmaydi.
  * Idempotent: qayta kelgan callback ikkinchi obuna bermaydi (`pul.tolandi`).
  * Xom so'rov `tolovlar.xom` ga audit uchun yoziladi — u faqat ekranlangan
    matn sifatida ko'rsatiladi.

Sirlar env orqali: PAYLOV_MERCHANT_ID, PAYLOV_CALLBACK_LOGIN,
PAYLOV_CALLBACK_PAROL; CLICK_SERVICE_ID, CLICK_MERCHANT_ID, CLICK_SECRET;
PAYME_MERCHANT_ID, PAYME_KEY. Sozlanmagan bo'lsa endpoint 404 qaytaradi
(yarim sozlangan holatda to'lov qabul qilinmasin).

To'liq reja va protokol tavsifi: `PAYLOV_REJA.md`.
"""
import base64
import hashlib
import hmac
import os
import time
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import auth, cheklov, db, monitoring, pg, pul
from .sozlama import log

router = APIRouter()
COOKIE = "twin_sessiya"

# Payme: tranzaksiya yaratilgandan keyin bajarish uchun eng ko'p vaqt
PAYME_MUHLAT_MS = 12 * 3600 * 1000


def _env(nom: str) -> str:
    return os.environ.get(nom, "").strip()


def click_sozlangan() -> bool:
    return bool(_env("CLICK_SERVICE_ID") and _env("CLICK_MERCHANT_ID")
                and _env("CLICK_SECRET"))


def payme_sozlangan() -> bool:
    return bool(_env("PAYME_MERCHANT_ID") and _env("PAYME_KEY"))


def paylov_sozlangan() -> bool:
    return bool(_env("PAYLOV_MERCHANT_ID") and _env("PAYLOV_CALLBACK_LOGIN")
                and _env("PAYLOV_CALLBACK_PAROL"))


def sozlangan_usullar() -> list[str]:
    """Ayni damda ishlatsa bo'ladigan to'lov usullari (tartib = UI tartibi)."""
    return [n for n, bor in (("paylov", paylov_sozlangan()),
                             ("click", click_sozlangan()),
                             ("payme", payme_sozlangan())) if bor]


def _joriy(request: Request) -> dict | None:
    return db.sessiya_user(request.cookies.get(COOKIE, ""))


# ================================================================ mijoz tomoni

@router.get("/api/planlar")
def planlar(request: Request):
    """Faol planlar + userning joriy holati (bepul promptlar, obuna).

    Kirish talab qilinadi: narxlar hali tasdiqlanmagan (taxminiy), ochiq
    endpointda turishi kerak emas. Rejalar oynasi baribir faqat kirgan
    foydalanuvchiga ko'rinadi.
    """
    u = _joriy(request)
    if not u:
        return JSONResponse({"xato": "kirish kerak"}, status_code=401)
    royxat = [{"id": p["id"], "kod": p["kod"], "nom": p["nom"],
               "tavsif": p["tavsif"], "narx_som": int(p["oylik_narx_som"]),
               "kun_soni": p["kun_soni"], "funksiyalar": list(p["funksiyalar"] or [])}
              for p in pul.planlar(faqat_faol=True) if p["oylik_narx_som"] > 0]
    javob = {"planlar": royxat, "usullar": sozlangan_usullar()}
    if u:
        javob["holat"] = pul.holat(u["id"])
    return javob


@router.post("/api/tolov/boshla")
async def tolov_boshla(request: Request):
    """To'lov yozuvini yaratadi va provayder checkout havolasini qaytaradi.

    Summani mijoz YUBORMAYDI — plan id si bo'yicha bazadan olinadi.
    """
    u = _joriy(request)
    if not u:
        return JSONResponse({"xato": "kirish kerak"}, status_code=401)
    if not cheklov.ruxsat("tolov", str(u["id"])):
        return JSONResponse({"xato": "juda ko'p urinish — biroz kuting"},
                            status_code=429)
    try:
        tana = await request.json()
    except Exception:                                        # noqa: BLE001
        tana = {}
    try:
        plan_id = int(tana.get("plan_id") or 0)
    except (TypeError, ValueError):
        plan_id = 0
    mavjud = sozlangan_usullar()
    if not mavjud:
        return JSONResponse({"xato": "to'lov tizimi hali ulanmagan"}, status_code=503)
    usul = str(tana.get("usul") or "").lower().strip()
    if not usul and len(mavjud) == 1:
        usul = mavjud[0]          # yagona usul bo'lsa UI tanlatib o'tirmaydi
    if usul not in mavjud:
        return JSONResponse({"xato": "to'lov usuli mavjud emas"}, status_code=400)

    try:
        t = pul.tolov_yasa(u["id"], plan_id, usul)
    except ValueError as e:
        return JSONResponse({"xato": str(e)}, status_code=400)

    # Qaytish havolasi tashqi UUID bilan: sahifa to'lov holatini shu bo'yicha
    # so'raydi va ketma-ket id tashqariga chiqmaydi.
    qaytish = f"{auth.public_url()}/?tolov={t['tashqi_id']}"
    if usul == "paylov":
        havola = _paylov_havola(t, qaytish)
    elif usul == "click":
        havola = (f"https://my.click.uz/services/pay?service_id={_env('CLICK_SERVICE_ID')}"
                  f"&merchant_id={_env('CLICK_MERCHANT_ID')}"
                  f"&amount={int(t['summa_som'])}&transaction_param={t['id']}"
                  f"&return_url={qaytish}")
    else:
        maydon = _env("PAYME_ACCOUNT_MAYDON") or "tolov_id"
        xom = (f"m={_env('PAYME_MERCHANT_ID')};ac.{maydon}={t['id']};"
               f"a={int(t['summa_som']) * 100};c={qaytish}")
        havola = "https://checkout.paycom.uz/" + \
                 base64.b64encode(xom.encode()).decode()
    return {"ok": True, "tolov_id": t["id"], "tashqi_id": str(t["tashqi_id"]),
            "usul": usul, "summa_som": int(t["summa_som"]), "havola": havola}


@router.get("/api/tolov/{tashqi_id}")
def tolov_holati(tashqi_id: str, request: Request):
    """Qaytish sahifasi uchun: to'lovim o'tdimi. FAQAT o'z to'lovi."""
    u = _joriy(request)
    if not u:
        return JSONResponse({"xato": "kirish kerak"}, status_code=401)
    t = pul.tolov_tashqi_ol(tashqi_id)
    if not t or t["user_id"] != u["id"]:
        return JSONResponse({"xato": "topilmadi"}, status_code=404)
    return {"holat": t["holat"], "plan_nom": t["plan_nom"],
            "summa_som": int(t["summa_som"]),
            "tolangan": t["tolangan"].isoformat() if t["tolangan"] else None}


@router.get("/api/tolovlarim")
def tolovlarim(request: Request):
    u = _joriy(request)
    if not u:
        return JSONResponse({"xato": "kirish kerak"}, status_code=401)
    return pg.hammasi_d(
        """SELECT t.id, t.summa_som, t.provayder, t.holat, t.yaratilgan, t.tolangan,
                  p.nom AS plan_nom
           FROM tolovlar t JOIN planlar p ON p.id = t.plan_id
           WHERE t.user_id=%s ORDER BY t.id DESC LIMIT 20""", u["id"])


# ================================================================ Paylov

PAYLOV_CHECKOUT = "https://my.paylov.uz/checkout/create/"
PAYLOV_VALYUTA = 860                 # UZS (840 = USD)

# Status kodlari — developer.paylov.uz/ru/merchants/statuses.
# DIQQAT: Paylov protokolida `error` obyekti yo'q; xato ham `result.status`
# orqali bildiriladi. `+1` — merchant o'z matnini yuborishi uchun.
PL_OK = "0"
PL_TEXNIK = "3"                      # "keyinroq urin" signali
PL_SUMMA = "5"
PL_TOPILMADI = "303"
PL_OZ = "+1"


def _paylov_tiyinda() -> bool:
    """Checkout havolasida summa tiyinda yuborilsinmi.

    Hujjat ziddiyatli (PAYLOV_REJA.md 2.4): `transaction.check` misolida
    `amount` so'mda ko'rinadi, checkout misolida esa `amount_in_tiyin=True`
    bilan birga `amount=500` turibdi. Shuning uchun bu KOD EMAS, sozlama —
    jonli sinovda 1 000 so'mlik to'lov bilan tasdiqlanadi.
    """
    return (_env("PAYLOV_TIYINDA") or "1") == "1"


def _paylov_valyuta() -> int:
    try:
        return int(_env("PAYLOV_VALYUTA") or PAYLOV_VALYUTA)
    except ValueError:
        return PAYLOV_VALYUTA


def _b64_yol(xom: str) -> str:
    """base64 — URL YO'L SEGMENTI uchun.

    Standart base64 chiqishida '/' bo'lsa havola buziladi. Payloadga zararsiz
    `&_=N` qo'shib, birinchi "toza" variantni tanlaymiz: deterministik va
    Paylov bu parametrni (`account.` prefiksi yo'q) e'tiborsiz qoldiradi.
    """
    for n in range(50):
        qator = xom if n == 0 else f"{xom}&_={n}"
        kod = base64.b64encode(qator.encode()).decode()
        if "/" not in kod and "+" not in kod:
            return kod
    log("Paylov: toza base64 topilmadi — urlsafe variantga o'tildi")
    return base64.urlsafe_b64encode(xom.encode()).decode()


def _paylov_havola(t: dict, qaytish: str) -> str:
    """Checkout havolasi: my.paylov.uz/checkout/create/<base64(parametrlar)>."""
    tiyinda = _paylov_tiyinda()
    summa = int(t["summa_som"]) * (100 if tiyinda else 1)
    xom = urlencode({
        "merchant_id": _env("PAYLOV_MERCHANT_ID"),
        "amount": summa,
        "currency_id": _paylov_valyuta(),
        "return_url": qaytish,
        # Hujjatdagi misolda aynan katta harfli True/False ishlatilgan.
        "amount_in_tiyin": "True" if tiyinda else "False",
        "account.order_id": str(t["tashqi_id"]),
    }, quote_via=quote, safe="")
    asos = (_env("PAYLOV_CHECKOUT") or PAYLOV_CHECKOUT).rstrip("/")
    return f"{asos}/{_b64_yol(xom)}"


def _paylov_javob(status: str, matn: str, sorov_id=None) -> dict:
    return {"jsonrpc": "2.0", "id": sorov_id,
            "result": {"status": status, "statusText": matn}}


def _paylov_auth_ok(request: Request) -> bool:
    """Basic Auth — login ham, parol ham doimiy vaqtda solishtiriladi."""
    bosh = request.headers.get("authorization", "")
    if not bosh.lower().startswith("basic "):
        return False
    try:
        xom = base64.b64decode(bosh.split(" ", 1)[1]).decode()
    except Exception:                                        # noqa: BLE001
        return False
    login, ajratgich, parol = xom.partition(":")
    if not ajratgich:
        return False
    ok_login = hmac.compare_digest(login.encode(),
                                   _env("PAYLOV_CALLBACK_LOGIN").encode())
    ok_parol = hmac.compare_digest(parol.encode(),
                                   _env("PAYLOV_CALLBACK_PAROL").encode())
    return ok_login and ok_parol


def _paylov_ip_ok(request: Request) -> bool:
    """PAYLOV_IP bo'sh bo'lsa filtr o'chiq. Aks holda faqat ro'yxatdagilar.

    X-Forwarded-For'ga faqat o'z nginx'imiz orqasida ishonamiz — env bo'sh
    bo'lganda bu tekshiruv umuman ishlamaydi.
    """
    royxat = [x.strip() for x in (_env("PAYLOV_IP") or "").split(",") if x.strip()]
    if not royxat:
        return True
    oldinga = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    ip = oldinga or (request.client.host if request.client else "")
    return ip in royxat


def _butun(q) -> int | None:
    """Ishonchsiz qiymatni butun songa keltiradi (bo'lmasa None)."""
    try:
        return int(str(q).strip())
    except (TypeError, ValueError):
        return None


def _paylov_xom(params: dict) -> dict:
    """Audit uchun xom callback — faqat kutilgan maydonlar, qisqartirilgan.

    DIQQAT: bu ISHONCHSIZ matn. Promptga hech qachon kirmaydi, UI'da faqat
    ekranlangan holda ko'rsatiladi.
    """
    yozuv = {}
    for kalit in ("transaction_id", "amount", "amount_tiyin", "currency"):
        if kalit in params:
            yozuv[kalit] = str(params.get(kalit))[:120]
    hisob = params.get("account")
    if isinstance(hisob, dict):
        yozuv["order_id"] = str(hisob.get("order_id"))[:120]
    return yozuv


def _paylov_tolov(params: dict):
    """(tolov, (status, matn)) — to'lovni topadi va summani tekshiradi.

    Summa qoidasi (PAYLOV_REJA.md 2.4 noaniqligiga chidamli, lekin xavfsiz):
      * `amount_tiyin` kelsa — u ANIQ tiyinda, `summa_som * 100` ga teng bo'lishi shart;
      * `amount` kelsa — u so'mda ham, tiyinda ham bo'lishi mumkin, shuning
        uchun ikki qiymatdan biriga teng bo'lsa o'tadi. Bu BIR XIL PULNING
        ikki o'lchovi — boshqa summani qabul qilishga yo'l ochmaydi;
      * ikkalasi ham kelmasa — rad etamiz (summasiz to'lov qabul qilinmaydi).
    """
    hisob = params.get("account")
    if not isinstance(hisob, dict):
        return None, (PL_TOPILMADI, "order_not_found")
    t = pul.tolov_tashqi_ol(hisob.get("order_id"))
    if not t or t["provayder"] != "paylov":
        return None, (PL_TOPILMADI, "order_not_found")

    som = int(t["summa_som"])
    valyuta = _butun(params.get("currency")) if "currency" in params else None
    if "currency" in params and valyuta != _paylov_valyuta():
        return t, (PL_SUMMA, "invalid_currency")

    tiyin = _butun(params.get("amount_tiyin")) if "amount_tiyin" in params else None
    summa = _butun(params.get("amount")) if "amount" in params else None
    if tiyin is None and summa is None:
        return t, (PL_SUMMA, "invalid_amount")
    if tiyin is not None and tiyin != som * 100:
        return t, (PL_SUMMA, "invalid_amount")
    if summa is not None and summa not in (som, som * 100):
        return t, (PL_SUMMA, "invalid_amount")
    return t, None


def _paylov_yopiq(t: dict, sorov_id):
    """To'lov ustida ish qilib bo'lmaydigan holatlar. Yo'q bo'lsa None."""
    if t["holat"] == "bekor":
        return _paylov_javob(PL_OZ, "order_cancelled", sorov_id)
    if t["holat"] != "tolangan" and t["muddati_otdi"]:
        pul.bekor(t["id"], "muddati o'tdi")
        return _paylov_javob(PL_OZ, "order_expired", sorov_id)
    return None


@router.post("/tolov/paylov")
async def paylov(request: Request):
    """Paylov callback — bitta URL, JSON-RPC 2.0, Basic Auth.

    Tartib: auth -> JSON -> metod -> to'lov -> summa -> holat. Har bosqich
    yiqilsa keyingisiga o'tilmaydi va BAZAGA TEGILMAYDI.
    """
    if not paylov_sozlangan():
        return JSONResponse({"xato": "topilmadi"}, status_code=404)
    if not _paylov_ip_ok(request) or not _paylov_auth_ok(request):
        log("Paylov: AUTH NOTO'G'RI")
        monitoring.xato("Paylov callback: auth rad etildi", kalit="paylov_auth",
                        jimgina=True)
        return JSONResponse({"xato": "ruxsat yo'q"}, status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="paylov"'})
    try:
        tana = await request.json()
    except Exception:                                        # noqa: BLE001
        tana = None
    if not isinstance(tana, dict):
        return JSONResponse(_paylov_javob(PL_TEXNIK, "bad_request"))

    sorov_id = tana.get("id")
    params = tana.get("params")
    if not isinstance(params, dict):
        params = {}
    fn = {"transaction.check": _pl_check,
          "transaction.perform": _pl_perform}.get(tana.get("method") or "")
    if not fn:
        return JSONResponse(_paylov_javob(PL_TEXNIK, "method_not_found", sorov_id))
    try:
        return JSONResponse(fn(params, sorov_id))
    except Exception as e:                                   # noqa: BLE001
        # Ichki xatoda "3" — Paylov uchun bu "keyinroq urin" degani, ya'ni
        # to'lov yo'qolmaydi. Sabab faqat bizning logda qoladi.
        log(f"Paylov callback xatosi: {str(e)[:150]}")
        monitoring.xato("Paylov callback ichki xatosi", str(e)[:300],
                        kalit="paylov_ichki")
        return JSONResponse(_paylov_javob(PL_TEXNIK, "internal_error", sorov_id))


def _pl_check(params, sorov_id):
    """transaction.check — to'lovdan oldingi tekshiruv. Pul yechilmaydi."""
    t, xato = _paylov_tolov(params)
    if t is not None:
        pul.xom_qosh(t["id"], {"bosqich": "paylov_check", "p": _paylov_xom(params)})
    if xato:
        return _paylov_javob(xato[0], xato[1], sorov_id)
    if t["holat"] == "tolangan":
        return _paylov_javob(PL_OZ, "already_paid", sorov_id)
    yopiq = _paylov_yopiq(t, sorov_id)
    if yopiq:
        return yopiq
    pg.bajar("""UPDATE tolovlar SET holat='tayyorlangan'
                WHERE id=%s AND holat='kutilmoqda'""", t["id"])
    return _paylov_javob(PL_OK, "OK", sorov_id)


def _pl_perform(params, sorov_id):
    """transaction.perform — pul yechildi, obunani ochamiz. IDEMPOTENT."""
    t, xato = _paylov_tolov(params)
    if t is not None:
        pul.xom_qosh(t["id"], {"bosqich": "paylov_perform", "p": _paylov_xom(params)})
    if xato:
        return _paylov_javob(xato[0], xato[1], sorov_id)

    tr_id = str(params.get("transaction_id") or "").strip()[:120]
    if not tr_id:
        return _paylov_javob(PL_TEXNIK, "transaction_id_required", sorov_id)

    if t["holat"] == "tolangan":
        # Takroriy callback: AYNAN shu tranzaksiya bo'lsa — muvaffaqiyat
        # deb javob beramiz (Paylov qayta urinishni to'xtatsin).
        if str(t["provayder_id"] or "") == tr_id:
            return _paylov_javob(PL_OK, "OK", sorov_id)
        monitoring.xato("Paylov: to'langan buyurtmaga BOSHQA tranzaksiya",
                        f"tolov={t['id']}", kalit="paylov_ikki_tranzaksiya")
        return _paylov_javob(PL_OZ, "already_paid", sorov_id)
    yopiq = _paylov_yopiq(t, sorov_id)
    if yopiq:
        return yopiq

    # Pul haqiqati AVVAL yoziladi: `pul.tolandi` — idempotent va qulflangan
    # (SELECT ... FOR UPDATE), obunani u ochadi.
    obuna_id = pul.tolandi(t["id"], tr_id)

    # Tranzaksiya qaydi — audit va XABAR DEDUPLIKATSIYASI. PK ustidagi
    # ON CONFLICT takroriy callbackda bo'sh qaytadi, demak foydalanuvchiga
    # xabar faqat bir marta ketadi. Tartib ataylab shunday: `tolandi` yiqilib
    # Paylov qayta urinsa, keyingi urinishda ham xabar yo'qolmaydi.
    yangi = pg.bitta(
        """INSERT INTO paylov_tranzaksiyalar(id, tolov_id, summa_som, summa_tiyin,
                                             valyuta)
           VALUES(%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING RETURNING id""",
        tr_id, t["id"], int(t["summa_som"]), int(t["summa_som"]) * 100,
        _paylov_valyuta())
    if yangi and obuna_id:
        _obuna_xabar(t, obuna_id)
    return _paylov_javob(PL_OK, "OK", sorov_id)


# ================================================================ Click

CLICK_XATO = {
    "ok": 0, "imzo": -1, "summa": -2, "amal": -3, "tolangan": -4,
    "user": -5, "topilmadi": -6, "yangilash": -7, "sorov": -8, "bekor": -9,
}


def _click_javob(kod: str, izoh: str, **qo):
    return {"error": CLICK_XATO[kod], "error_note": izoh, **qo}


def _click_imzo_ok(d: dict, tayyorlash_id: str = "") -> bool:
    """MD5 imzo: prepare va complete uchun tarkib har xil."""
    sir = _env("CLICK_SECRET")
    qismlar = [d.get("click_trans_id", ""), d.get("service_id", ""), sir,
               d.get("merchant_trans_id", "")]
    if tayyorlash_id:
        qismlar.append(tayyorlash_id)
    qismlar += [d.get("amount", ""), d.get("action", ""), d.get("sign_time", "")]
    kutilgan = hashlib.md5("".join(qismlar).encode()).hexdigest()
    return hmac.compare_digest(kutilgan, (d.get("sign_string") or "").lower())


async def _click_dict(request: Request) -> dict:
    """Click form-encoded yuboradi; JSON ham qabul qilamiz (sinov qulayligi)."""
    try:
        forma = await request.form()
        if forma:
            return {k: str(v) for k, v in forma.items()}
    except Exception:                                        # noqa: BLE001
        pass
    try:
        return {k: str(v) for k, v in (await request.json()).items()}
    except Exception:                                        # noqa: BLE001
        return {}


def _click_tolov(d: dict):
    """(tolov, xato_javobi). merchant_trans_id = bizning tolovlar.id."""
    try:
        tid = int(d.get("merchant_trans_id") or 0)
    except (TypeError, ValueError):
        return None, _click_javob("topilmadi", "Order not found")
    t = pul.tolov_ol(tid)
    if not t:
        return None, _click_javob("topilmadi", "Order not found")
    if t["provayder"] != "click":
        return None, _click_javob("topilmadi", "Order not found")
    try:
        summa = float(d.get("amount") or 0)
    except (TypeError, ValueError):
        return None, _click_javob("summa", "Incorrect parameter amount")
    if abs(summa - float(t["summa_som"])) > 0.5:
        return None, _click_javob("summa", "Incorrect parameter amount")
    return t, None


@router.post("/tolov/click/prepare")
async def click_prepare(request: Request):
    if not click_sozlangan():
        return JSONResponse({"xato": "topilmadi"}, status_code=404)
    d = await _click_dict(request)
    if not _click_imzo_ok(d):
        log("Click prepare: IMZO NOTO'G'RI")
        return _click_javob("imzo", "SIGN CHECK FAILED")
    t, xato = _click_tolov(d)
    if xato:
        return xato
    pul.xom_qosh(t["id"], {"bosqich": "click_prepare", "d": d})
    if t["holat"] == "tolangan":
        return _click_javob("tolangan", "Already paid",
                            click_trans_id=d.get("click_trans_id"),
                            merchant_trans_id=str(t["id"]))
    if t["holat"] == "bekor":
        return _click_javob("bekor", "Transaction cancelled",
                            click_trans_id=d.get("click_trans_id"),
                            merchant_trans_id=str(t["id"]))
    pg.bajar("UPDATE tolovlar SET holat='tayyorlangan', provayder_id=%s WHERE id=%s",
             str(d.get("click_trans_id") or ""), t["id"])
    return _click_javob("ok", "Success", click_trans_id=d.get("click_trans_id"),
                        merchant_trans_id=str(t["id"]),
                        merchant_prepare_id=t["id"])


@router.post("/tolov/click/complete")
async def click_complete(request: Request):
    if not click_sozlangan():
        return JSONResponse({"xato": "topilmadi"}, status_code=404)
    d = await _click_dict(request)
    if not _click_imzo_ok(d, str(d.get("merchant_prepare_id") or "")):
        log("Click complete: IMZO NOTO'G'RI")
        return _click_javob("imzo", "SIGN CHECK FAILED")
    t, xato = _click_tolov(d)
    if xato:
        return xato
    pul.xom_qosh(t["id"], {"bosqich": "click_complete", "d": d})

    if str(d.get("error") or "0") not in ("0", ""):
        pul.bekor(t["id"], f"click error {d.get('error')}")
        return _click_javob("bekor", "Transaction cancelled",
                            click_trans_id=d.get("click_trans_id"),
                            merchant_trans_id=str(t["id"]))
    if t["holat"] == "bekor":
        return _click_javob("bekor", "Transaction cancelled")
    if t["holat"] == "tolangan":
        return _click_javob("tolangan", "Already paid",
                            click_trans_id=d.get("click_trans_id"),
                            merchant_trans_id=str(t["id"]),
                            merchant_confirm_id=t["id"])

    obuna_id = pul.tolandi(t["id"], str(d.get("click_trans_id") or ""))
    _obuna_xabar(t, obuna_id)
    return _click_javob("ok", "Success", click_trans_id=d.get("click_trans_id"),
                        merchant_trans_id=str(t["id"]), merchant_confirm_id=t["id"])


# ================================================================ Payme

def _payme_xato(kod: int, xabar: str, sorov_id=None, data: str | None = None):
    x = {"code": kod, "message": {"uz": xabar, "ru": xabar, "en": xabar}}
    if data:
        x["data"] = data
    return {"error": x, "id": sorov_id, "jsonrpc": "2.0"}


def _payme_auth_ok(request: Request) -> bool:
    bosh = request.headers.get("authorization", "")
    if not bosh.lower().startswith("basic "):
        return False
    try:
        xom = base64.b64decode(bosh.split(" ", 1)[1]).decode()
    except Exception:                                        # noqa: BLE001
        return False
    login, _, kalit = xom.partition(":")
    return login == "Paycom" and hmac.compare_digest(kalit, _env("PAYME_KEY"))


def _payme_tolov(params: dict):
    """Account ichidagi tolov_id bo'yicha to'lovni topadi va summani solishtiradi."""
    maydon = _env("PAYME_ACCOUNT_MAYDON") or "tolov_id"
    hisob = params.get("account") or {}
    try:
        tid = int(hisob.get(maydon) or 0)
    except (TypeError, ValueError):
        return None, (-31050, "To'lov topilmadi")
    t = pul.tolov_ol(tid)
    if not t or t["provayder"] != "payme":
        return None, (-31050, "To'lov topilmadi")
    if "amount" in params:
        try:
            summa = int(params.get("amount") or 0)
        except (TypeError, ValueError):
            return None, (-31001, "Noto'g'ri summa")
        if summa != int(t["summa_som"]) * 100:
            return None, (-31001, "Noto'g'ri summa")
    return t, None


def _payme_tr(tr_id: str) -> dict | None:
    return pg.bitta_d("SELECT * FROM payme_tranzaksiyalar WHERE id=%s", tr_id)


@router.post("/tolov/payme")
async def payme(request: Request):
    """Payme Merchant JSON-RPC — to'liq protokol."""
    if not payme_sozlangan():
        return JSONResponse({"xato": "topilmadi"}, status_code=404)
    try:
        tana = await request.json()
    except Exception:                                        # noqa: BLE001
        return JSONResponse(_payme_xato(-32700, "JSON o'qilmadi"))
    sorov_id = tana.get("id")
    if not _payme_auth_ok(request):
        log("Payme: AUTH NOTO'G'RI")
        return JSONResponse(_payme_xato(-32504, "Ruxsat yo'q", sorov_id))

    metod = tana.get("method") or ""
    params = tana.get("params") or {}
    fn = {"CheckPerformTransaction": _p_check_perform,
          "CreateTransaction": _p_create,
          "PerformTransaction": _p_perform,
          "CancelTransaction": _p_cancel,
          "CheckTransaction": _p_check,
          "GetStatement": _p_statement}.get(metod)
    if not fn:
        return JSONResponse(_payme_xato(-32601, "Metod topilmadi", sorov_id))
    try:
        natija = fn(params, sorov_id)
    except Exception as e:                                   # noqa: BLE001
        log(f"Payme {metod} xatosi: {str(e)[:150]}")
        return JSONResponse(_payme_xato(-32400, "Ichki xato", sorov_id))
    return JSONResponse(natija)


def _p_check_perform(params, sorov_id):
    t, xato = _payme_tolov(params)
    if xato:
        return _payme_xato(xato[0], xato[1], sorov_id)
    if t["holat"] == "tolangan":
        return _payme_xato(-31051, "To'lov allaqachon amalga oshirilgan", sorov_id)
    if t["holat"] == "bekor":
        return _payme_xato(-31052, "To'lov bekor qilingan", sorov_id)
    return {"result": {"allow": True}, "id": sorov_id, "jsonrpc": "2.0"}


def _p_create(params, sorov_id):
    tr_id = str(params.get("id") or "")
    mavjud = _payme_tr(tr_id)
    if mavjud:
        if mavjud["holat"] != 1:
            return _payme_xato(-31008, "Tranzaksiya holati mos emas", sorov_id)
        if int(time.time() * 1000) - mavjud["yaratilgan_ms"] > PAYME_MUHLAT_MS:
            _p_bekorla(mavjud, 4)
            return _payme_xato(-31008, "Tranzaksiya muddati o'tdi", sorov_id)
        return {"result": {"create_time": mavjud["yaratilgan_ms"],
                           "transaction": str(mavjud["tolov_id"]),
                           "state": mavjud["holat"]},
                "id": sorov_id, "jsonrpc": "2.0"}

    t, xato = _payme_tolov(params)
    if xato:
        return _payme_xato(xato[0], xato[1], sorov_id)
    if t["holat"] in ("tolangan", "bekor"):
        return _payme_xato(-31008, "To'lov holati mos emas", sorov_id)
    bor = pg.bitta(
        "SELECT id FROM payme_tranzaksiyalar WHERE tolov_id=%s AND holat IN (1,2)",
        t["id"])
    if bor:
        return _payme_xato(-31008, "Bu to'lov uchun tranzaksiya ochilgan", sorov_id)

    vaqt = int(params.get("time") or time.time() * 1000)
    pg.bajar(
        """INSERT INTO payme_tranzaksiyalar(id, tolov_id, summa_tiyin, holat,
                                            yaratilgan_ms)
           VALUES(%s,%s,%s,1,%s)""",
        tr_id, t["id"], int(params.get("amount") or 0), vaqt)
    pul.xom_qosh(t["id"], {"bosqich": "payme_create", "tr": tr_id})
    pg.bajar("UPDATE tolovlar SET holat='tayyorlangan', provayder_id=%s WHERE id=%s",
             tr_id, t["id"])
    return {"result": {"create_time": vaqt, "transaction": str(t["id"]), "state": 1},
            "id": sorov_id, "jsonrpc": "2.0"}


def _p_perform(params, sorov_id):
    tr = _payme_tr(str(params.get("id") or ""))
    if not tr:
        return _payme_xato(-31003, "Tranzaksiya topilmadi", sorov_id)
    if tr["holat"] == 2:
        return {"result": {"transaction": str(tr["tolov_id"]),
                           "perform_time": tr["bajarilgan_ms"], "state": 2},
                "id": sorov_id, "jsonrpc": "2.0"}
    if tr["holat"] != 1:
        return _payme_xato(-31008, "Tranzaksiya bekor qilingan", sorov_id)
    if int(time.time() * 1000) - tr["yaratilgan_ms"] > PAYME_MUHLAT_MS:
        _p_bekorla(tr, 4)
        return _payme_xato(-31008, "Tranzaksiya muddati o'tdi", sorov_id)

    hozir = int(time.time() * 1000)
    pg.bajar("""UPDATE payme_tranzaksiyalar SET holat=2, bajarilgan_ms=%s
                WHERE id=%s""", hozir, tr["id"])
    t = pul.tolov_ol(tr["tolov_id"])
    obuna_id = pul.tolandi(tr["tolov_id"], tr["id"])
    pul.xom_qosh(tr["tolov_id"], {"bosqich": "payme_perform", "tr": tr["id"]})
    _obuna_xabar(t, obuna_id)
    return {"result": {"transaction": str(tr["tolov_id"]), "perform_time": hozir,
                       "state": 2}, "id": sorov_id, "jsonrpc": "2.0"}


def _p_bekorla(tr: dict, sabab: int):
    """Tranzaksiyani bekor qiladi: yaratilgan bo'lsa -1, bajarilgan bo'lsa -2."""
    yangi = -2 if tr["holat"] == 2 else -1
    hozir = int(time.time() * 1000)
    pg.bajar("""UPDATE payme_tranzaksiyalar SET holat=%s, sabab=%s, bekor_ms=%s
                WHERE id=%s""", yangi, sabab, hozir, tr["id"])
    pul.bekor(tr["tolov_id"], f"payme bekor ({sabab})")
    return yangi, hozir


def _p_cancel(params, sorov_id):
    tr = _payme_tr(str(params.get("id") or ""))
    if not tr:
        return _payme_xato(-31003, "Tranzaksiya topilmadi", sorov_id)
    if tr["holat"] < 0:
        return {"result": {"transaction": str(tr["tolov_id"]),
                           "cancel_time": tr["bekor_ms"], "state": tr["holat"]},
                "id": sorov_id, "jsonrpc": "2.0"}
    try:
        sabab = int(params.get("reason") or 0)
    except (TypeError, ValueError):
        sabab = 0
    yangi, hozir = _p_bekorla(tr, sabab)
    return {"result": {"transaction": str(tr["tolov_id"]), "cancel_time": hozir,
                       "state": yangi}, "id": sorov_id, "jsonrpc": "2.0"}


def _p_check(params, sorov_id):
    tr = _payme_tr(str(params.get("id") or ""))
    if not tr:
        return _payme_xato(-31003, "Tranzaksiya topilmadi", sorov_id)
    return {"result": {"create_time": tr["yaratilgan_ms"],
                       "perform_time": tr["bajarilgan_ms"],
                       "cancel_time": tr["bekor_ms"],
                       "transaction": str(tr["tolov_id"]),
                       "state": tr["holat"], "reason": tr["sabab"]},
            "id": sorov_id, "jsonrpc": "2.0"}


def _p_statement(params, sorov_id):
    try:
        bosh = int(params.get("from") or 0)
        oxir = int(params.get("to") or 0)
    except (TypeError, ValueError):
        return _payme_xato(-32600, "Noto'g'ri parametr", sorov_id)
    qatorlar = pg.hammasi_d(
        """SELECT * FROM payme_tranzaksiyalar
           WHERE yaratilgan_ms BETWEEN %s AND %s ORDER BY yaratilgan_ms""",
        bosh, oxir)
    return {"result": {"transactions": [
        {"id": q["id"], "time": q["yaratilgan_ms"], "amount": q["summa_tiyin"],
         "account": {(_env("PAYME_ACCOUNT_MAYDON") or "tolov_id"): q["tolov_id"]},
         "create_time": q["yaratilgan_ms"], "perform_time": q["bajarilgan_ms"],
         "cancel_time": q["bekor_ms"], "transaction": str(q["tolov_id"]),
         "state": q["holat"], "reason": q["sabab"]} for q in qatorlar]},
        "id": sorov_id, "jsonrpc": "2.0"}


# ================================================================ umumiy

def _obuna_xabar(tolov: dict | None, obuna_id: int | None):
    """To'lov o'tgach foydalanuvchiga TG xabari (matn faqat shu koddan)."""
    if not tolov or not obuna_id:
        return
    from . import tg
    nom = (tolov.get("plan_nom") or "").replace("<", "&lt;").replace(">", "&gt;")
    try:
        tg.matn_yubor(tolov["user_id"],
                      f"✅ To'lov qabul qilindi — <b>{nom}</b> obunasi faollashdi.\n"
                      f"Ilovaga qaytib savolingizni davom ettiring.")
    except Exception as e:                                   # noqa: BLE001
        log(f"to'lov xabari yuborilmadi: {str(e)[:80]}")


def sozlama_holati() -> dict:
    """Admin panel uchun: qaysi provayder sozlangan (SIRLAR OCHILMAYDI)."""
    return {"paylov": paylov_sozlangan(), "click": click_sozlangan(),
            "payme": payme_sozlangan(), "usullar": sozlangan_usullar(),
            "paylov_merchant_id": bool(_env("PAYLOV_MERCHANT_ID")),
            "paylov_tiyinda": _paylov_tiyinda(),
            "paylov_ip_filtri": bool(_env("PAYLOV_IP")),
            "click_service_id": bool(_env("CLICK_SERVICE_ID")),
            "payme_merchant_id": bool(_env("PAYME_MERCHANT_ID"))}
