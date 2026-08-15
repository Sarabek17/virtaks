# -*- coding: utf-8 -*-
"""Ma'lumotlar qatlami — userlar, sessiyalar, twinlar, direktorlar, suhbatlar.

Barcha egalik tekshiruvlari SHU YERDA (SQL shartida) — endpoint unutib qo'ysa ham
begona ma'lumot chiqmaydi.
"""
import json
import secrets
from datetime import datetime, timedelta, timezone

from . import pg

SESSIYA_KUN = 60


def _hozir():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- userlar

def user_tg(tg: dict) -> dict:
    """Telegram ma'lumotidan user yaratadi/yangilaydi."""
    r = pg.bitta_d(
        """INSERT INTO userlar(tg_id, ism, familiya, username, telefon, foto)
           VALUES(%s, %s, %s, %s, %s, %s)
           ON CONFLICT(tg_id) DO UPDATE SET
             ism = EXCLUDED.ism,
             familiya = EXCLUDED.familiya,
             username = EXCLUDED.username,
             foto = CASE WHEN EXCLUDED.foto <> '' THEN EXCLUDED.foto ELSE userlar.foto END,
             telefon = CASE WHEN EXCLUDED.telefon <> '' THEN EXCLUDED.telefon
                            ELSE userlar.telefon END,
             oxirgi_kirish = now()
           RETURNING *""",
        tg["id"], tg.get("first_name") or "Foydalanuvchi", tg.get("last_name", "") or "",
        tg.get("username", "") or "", tg.get("telefon", "") or "",
        tg.get("photo_url", "") or "")
    return r


def user_ol(uid: int) -> dict | None:
    return pg.bitta_d("SELECT * FROM userlar WHERE id=%s", uid)


# ---------------------------------------------------------------- email akkaunt

def user_email_ol(email: str) -> dict | None:
    return pg.bitta_d("SELECT * FROM userlar WHERE lower(email)=lower(%s)",
                      email.strip())


def user_email_yasa(email: str, parol_hash: str, ism: str,
                    tasdiq: bool = False) -> dict:
    """Web orqali ro'yxatdan o'tgan klient."""
    return pg.bitta_d(
        """INSERT INTO userlar(email, parol_hash, ism, rol, manba, email_tasdiq)
           VALUES(%s,%s,%s,'client','web',%s) RETURNING *""",
        email.strip().lower(), parol_hash, ism.strip()[:60] or "Foydalanuvchi",
        tasdiq)


def email_tasdiqla(uid: int):
    pg.bajar("UPDATE userlar SET email_tasdiq=true WHERE id=%s", uid)


def parol_yangila(uid: int, parol_hash: str):
    pg.bajar("UPDATE userlar SET parol_hash=%s WHERE id=%s", parol_hash, uid)


def tg_bogla(uid: int, tg: dict):
    """Mavjud (email) akkauntga Telegramni bog'laydi.

    tg_id boshqa akkauntda band bo'lsa bog'lanmaydi — ikki akkaunt bitta
    Telegramga ega bo'lib qolmasin.
    """
    band = pg.bitta("SELECT id FROM userlar WHERE tg_id=%s AND id<>%s",
                    tg["id"], uid)
    if band:
        return False
    pg.bajar(
        """UPDATE userlar SET tg_id=%s,
             username = CASE WHEN %s <> '' THEN %s ELSE username END,
             foto = CASE WHEN %s <> '' THEN %s ELSE foto END
           WHERE id=%s""",
        tg["id"], tg.get("username", "") or "", tg.get("username", "") or "",
        tg.get("photo_url", "") or "", tg.get("photo_url", "") or "", uid)
    return True


# ---------------------------------------------------------------- email tokenlar

def token_yasa(uid: int, tur: str, soat: int) -> str:
    """Bir martalik token. Ayni turdagi eskilari bekor qilinadi."""
    token = secrets.token_urlsafe(32)
    pg.bajar("DELETE FROM email_tokenlar WHERE user_id=%s AND tur=%s", uid, tur)
    pg.bajar(
        "INSERT INTO email_tokenlar(token, user_id, tur, muddat) "
        "VALUES(%s,%s,%s,%s)",
        token, uid, tur, _hozir() + timedelta(hours=soat))
    pg.bajar("DELETE FROM email_tokenlar WHERE muddat < now() - interval '7 days'")
    return token


def token_ishlat(token: str, tur: str) -> dict | None:
    """Tokenni tekshirib BIR MARTA ishlatadi (atomar) -> user."""
    r = pg.bitta(
        """UPDATE email_tokenlar SET ishlatilgan = now()
           WHERE token=%s AND tur=%s AND ishlatilgan IS NULL AND muddat > now()
           RETURNING user_id""", token, tur)
    return user_ol(r[0]) if r else None


def user_login_ol(login: str) -> dict | None:
    return pg.bitta_d("SELECT * FROM userlar WHERE login=%s", login.strip().lower())


def user_yangila(uid: int, **maydonlar):
    """Ruxsat etilgan maydonlarni yangilaydi (admin/kabinet)."""
    ruxsat = {"ism", "familiya", "telefon", "rol", "parol_hash", "login",
              "profil", "bloklangan", "joriy_twin"}
    qismlar, qiymatlar = [], []
    for k, v in maydonlar.items():
        if k in ruxsat:
            qismlar.append(f"{k}=%s")
            qiymatlar.append(v)
    if not qismlar:
        return
    qiymatlar.append(uid)
    pg.bajar(f"UPDATE userlar SET {', '.join(qismlar)} WHERE id=%s", *qiymatlar)


def userlar(qidiruv: str = "", limit: int = 100) -> list[dict]:
    if qidiruv:
        q = f"%{qidiruv.lower()}%"
        return pg.hammasi_d(
            """SELECT * FROM userlar
               WHERE lower(ism) LIKE %s OR lower(username) LIKE %s OR telefon LIKE %s
               ORDER BY id DESC LIMIT %s""", q, q, q, limit)
    return pg.hammasi_d("SELECT * FROM userlar ORDER BY id DESC LIMIT %s", limit)


# ---------------------------------------------------------------- sessiyalar

def sessiya_yasa(uid: int, impersonator_id: int | None = None) -> str:
    token = secrets.token_urlsafe(32)
    pg.bajar(
        "INSERT INTO sessiyalar(token, user_id, impersonator_id, muddat) "
        "VALUES(%s, %s, %s, %s)",
        token, uid, impersonator_id, _hozir() + timedelta(days=SESSIYA_KUN))
    pg.bajar("DELETE FROM sessiyalar WHERE muddat < now()")
    return token


def sessiya_user(token: str) -> dict | None:
    """Sessiyadan user (+ impersonator_id maydoni bilan)."""
    if not token:
        return None
    return pg.bitta_d(
        """SELECT u.*, s.impersonator_id FROM sessiyalar s
           JOIN userlar u ON u.id = s.user_id
           WHERE s.token=%s AND s.muddat > now() AND u.bloklangan = false""", token)


def sessiya_ochir(token: str):
    pg.bajar("DELETE FROM sessiyalar WHERE token=%s", token)


# ---------------------------------------------------------------- kategoriyalar / twinlar

def kategoriyalar() -> list[dict]:
    return pg.hammasi_d("SELECT * FROM kategoriyalar ORDER BY tartib, nom")


def kategoriya_yasa(nom: str, izoh: str = "", tartib: int = 100) -> int:
    r = pg.bitta(
        "INSERT INTO kategoriyalar(nom, izoh, tartib) VALUES(%s,%s,%s) "
        "ON CONFLICT(nom) DO UPDATE SET izoh=EXCLUDED.izoh RETURNING id",
        nom, izoh, tartib)
    return r[0]


def twinlar(faqat_faol: bool = True, egasi_id: int | None = None) -> list[dict]:
    shart, args = [], []
    if faqat_faol:
        shart.append("t.faol = true")
    if egasi_id is not None:
        shart.append("t.egasi_id = %s")
        args.append(egasi_id)
    w = ("WHERE " + " AND ".join(shart)) if shart else ""
    return pg.hammasi_d(
        f"""SELECT t.*, k.nom AS kategoriya,
                   (SELECT count(*) FROM bolaklar b WHERE b.twin_id = t.id) AS bolak_soni,
                   u.ism AS egasi_ism
            FROM twinlar t
            LEFT JOIN kategoriyalar k ON k.id = t.kategoriya_id
            LEFT JOIN userlar u ON u.id = t.egasi_id
            {w} ORDER BY t.tartib, t.nom""", *args)


def twin_ol(twin_id: int) -> dict | None:
    return pg.bitta_d("SELECT * FROM twinlar WHERE id=%s", twin_id)


def twin_yasa(nom: str, slug: str, **f) -> int:
    r = pg.bitta(
        """INSERT INTO twinlar(nom, slug, kategoriya_id, egasi_id, tavsif, xulq, tartib)
           VALUES(%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT(slug) DO UPDATE SET nom=EXCLUDED.nom RETURNING id""",
        nom, slug, f.get("kategoriya_id"), f.get("egasi_id"), f.get("tavsif", ""),
        f.get("xulq", ""), f.get("tartib", 100))
    return r[0]


def twin_yangila(twin_id: int, **maydonlar):
    ruxsat = {"nom", "kategoriya_id", "egasi_id", "tavsif", "xulq", "uslub",
              "avatar", "faol", "tartib"}
    qismlar, qiymatlar = [], []
    for k, v in maydonlar.items():
        if k in ruxsat:
            qismlar.append(f"{k}=%s")
            qiymatlar.append(json.dumps(v, ensure_ascii=False) if k == "uslub" else v)
    if not qismlar:
        return
    qiymatlar.append(twin_id)
    pg.bajar(f"UPDATE twinlar SET {', '.join(qismlar)} WHERE id=%s", *qiymatlar)


def twin_ochir(twin_id: int):
    pg.bajar("DELETE FROM twinlar WHERE id=%s", twin_id)


def ruxsat_royxat(twin_id: int) -> list[int]:
    """Twin qaysi twinlarning bilimidan o'qiy oladi (o'zi doim kiradi)."""
    qatorlar = pg.hammasi(
        "SELECT manba_twin_id FROM twin_ruxsat WHERE twin_id=%s", twin_id)
    royxat = [q[0] for q in qatorlar]
    if twin_id not in royxat:
        royxat.append(twin_id)
    return royxat


def ruxsat_yoz(twin_id: int, manbalar: list[int]):
    with pg.ulanish() as u, u.cursor() as k:
        k.execute("DELETE FROM twin_ruxsat WHERE twin_id=%s", (twin_id,))
        for m in manbalar:
            if m != twin_id:
                k.execute("INSERT INTO twin_ruxsat(twin_id, manba_twin_id) "
                          "VALUES(%s,%s) ON CONFLICT DO NOTHING", (twin_id, m))


# ---------------------------------------------------------------- direktorlar

def direktorlar(twin_id: int | None = None, faqat_faol: bool = True) -> list[dict]:
    """Twin uchun direktorlar: twin-maxsuslari + umumiylar (NULL twin_id)."""
    shart = ["(twin_id IS NULL OR twin_id = %s)"]
    args = [twin_id]
    if faqat_faol:
        shart.append("faol = true")
    return pg.hammasi_d(
        f"SELECT * FROM direktorlar WHERE {' AND '.join(shart)} ORDER BY rais, tartib, kod",
        *args)


def direktor_ol(did: int) -> dict | None:
    return pg.bitta_d("SELECT * FROM direktorlar WHERE id=%s", did)


def direktor_yasa(kod: str, nom: str, persona: str, teglar: list[str], **f) -> int:
    r = pg.bitta(
        """INSERT INTO direktorlar(kod, nom, persona, teglar, rang, twin_id, rais, tartib)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT(kod, COALESCE(twin_id, 0)) DO UPDATE SET
             nom=EXCLUDED.nom, persona=EXCLUDED.persona, teglar=EXCLUDED.teglar,
             rang=EXCLUDED.rang, rais=EXCLUDED.rais, tartib=EXCLUDED.tartib
           RETURNING id""",
        kod, nom, persona, teglar, f.get("rang", "#5b8cff"), f.get("twin_id"),
        f.get("rais", False), f.get("tartib", 100))
    return r[0]


def direktor_yangila(did: int, **maydonlar):
    ruxsat = {"kod", "nom", "persona", "teglar", "rang", "faol", "tartib", "rais"}
    qismlar, qiymatlar = [], []
    for k, v in maydonlar.items():
        if k in ruxsat:
            qismlar.append(f"{k}=%s")
            qiymatlar.append(v)
    if not qismlar:
        return
    qiymatlar.append(did)
    pg.bajar(f"UPDATE direktorlar SET {', '.join(qismlar)} WHERE id=%s", *qiymatlar)


def direktor_ochir(did: int):
    pg.bajar("DELETE FROM direktorlar WHERE id=%s", did)


# ---------------------------------------------------------------- manbalar (bilim)

def manba_yasa(twin_id: int, nom: str, tur: str, **f) -> int:
    r = pg.bitta(
        """INSERT INTO manbalar(twin_id, nom, tur, s3_yol, manba_url, papka,
                                yuklagan_id, asl_nom, hajm, mime)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        twin_id, nom, tur, f.get("s3_yol", ""), f.get("manba_url", ""),
        f.get("papka", ""), f.get("yuklagan_id"), f.get("asl_nom", ""),
        f.get("hajm", 0), f.get("mime", ""))
    return r[0]


def manba_ol(mid: int) -> dict | None:
    return pg.bitta_d("SELECT * FROM manbalar WHERE id=%s", mid)


def manbalar(twin_id: int | None = None, limit: int = 500) -> list[dict]:
    shart = "WHERE m.twin_id=%s" if twin_id else ""
    args = [twin_id] if twin_id else []
    return pg.hammasi_d(
        f"""SELECT m.*, t.nom AS twin_nom,
                   (SELECT j.id FROM jobs j
                     WHERE j.tur IN ('ingest_fayl','ingest_url')
                       AND (j.kirish->>'manba_id')::bigint = m.id
                     ORDER BY j.id DESC LIMIT 1) AS job_id
            FROM manbalar m LEFT JOIN twinlar t ON t.id = m.twin_id
            {shart} ORDER BY m.id DESC LIMIT %s""", *args, limit)


def manba_holat(mid: int, holat: str, xato: str = ""):
    pg.bajar("UPDATE manbalar SET holat=%s, xato=%s WHERE id=%s", holat, xato[:500], mid)


def manba_tayyor(mid: int, bolak_soni: int, davomiylik: int | None,
                 sahifa_soni: int = 0):
    pg.bajar(
        """UPDATE manbalar SET holat='tayyor', xato='', bolak_soni=%s,
           davomiylik=%s, sahifa_soni=%s WHERE id=%s""",
        bolak_soni, davomiylik, sahifa_soni, mid)


def manba_ochir(mid: int):
    """Manba + bo'laklari + fragmentlari (CASCADE) o'chadi. S3 tozalash — chaqiruvchida."""
    pg.bajar("DELETE FROM manbalar WHERE id=%s", mid)


# ---------------------------------------------------------------- bo'laklar / fragmentlar

def bolak_ol(bid: int) -> dict | None:
    """Bo'lak + manba ma'lumoti (fragment xizmati uchun)."""
    return pg.bitta_d(
        """SELECT b.*, m.nom AS manba, m.tur, m.s3_yol AS manba_s3,
                  m.manba_url, m.papka, t.nom AS twin_nom
           FROM bolaklar b
           JOIN manbalar m ON m.id = b.manba_id
           LEFT JOIN twinlar t ON t.id = b.twin_id
           WHERE b.id=%s""", bid)


def bolaklar_almashtir(manba_id: int, twin_id: int, bolaklar: list[dict]):
    """Manbaning eski bo'laklarini o'chirib, yangilarini yozadi (bitta tranzaksiyada)."""
    with pg.ulanish() as u, u.cursor() as k:
        k.execute("DELETE FROM bolaklar WHERE manba_id=%s", (manba_id,))
        for i, b in enumerate(bolaklar):
            k.execute(
                """INSERT INTO bolaklar(manba_id, twin_id, tartib, matn, joy, teglar,
                                        embedding, sahifa_png, audio_bosh, audio_oxir)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (manba_id, twin_id, i, b["matn"], b.get("joy", ""),
                 b.get("teglar") or ["umumiy"], b.get("embedding"),
                 b.get("sahifa_png", ""), b.get("audio_bosh"), b.get("audio_oxir")))


def bolaklar_idlar(idlar: list[int]) -> list[dict]:
    """Bir nechta bo'lak — manba ma'lumoti bilan (mentor darsi uchun).

    Bitta so'rov: mavzuga 12 tagacha bo'lak biriktiriladi, ularni bittalab
    o'qish masofadagi bazada darsning birinchi so'ziga o'nlab soniya
    qo'shib qo'yardi.
    """
    if not idlar:
        return []
    return pg.hammasi_d(
        """SELECT b.id, b.twin_id, b.matn, b.joy, b.teglar, b.manba_id,
                  b.audio_bosh, b.audio_oxir, b.sahifa_png,
                  m.nom AS manba, m.tur, m.papka
           FROM bolaklar b JOIN manbalar m ON m.id = b.manba_id
           WHERE b.id = ANY(%s)""", list(idlar))


def fragment_ol(bolak_id: int, tur: str = "audio") -> dict | None:
    return pg.bitta_d("SELECT * FROM fragmentlar WHERE bolak_id=%s AND tur=%s",
                      bolak_id, tur)


def fragment_yoz(bolak_id: int, tur: str, holat: str, s3_yol: str = "",
                 xato: str = "", davomiylik: int | None = None):
    pg.bajar(
        """INSERT INTO fragmentlar(bolak_id, tur, holat, s3_yol, xato, davomiylik)
           VALUES(%s,%s,%s,%s,%s,%s)
           ON CONFLICT(bolak_id, tur) DO UPDATE SET
             holat=EXCLUDED.holat, s3_yol=EXCLUDED.s3_yol, xato=EXCLUDED.xato,
             davomiylik=EXCLUDED.davomiylik""",
        bolak_id, tur, holat, s3_yol, xato[:500], davomiylik)


# ---------------------------------------------------------------- suhbatlar / majlislar

def suhbat_yasa(uid: int, twin_id: int | None, sarlavha: str) -> int:
    r = pg.bitta(
        "INSERT INTO suhbatlar(user_id, twin_id, sarlavha) VALUES(%s,%s,%s) RETURNING id",
        uid, twin_id, sarlavha.strip()[:80])
    return r[0]


def suhbatlar(uid: int, arxiv: bool = False) -> list[dict]:
    return pg.hammasi_d(
        """SELECT s.id, s.sarlavha, s.twin_id, s.mavzu_id, s.maqsad_id,
                  s.tizim_maqsad_id,
                  s.yaratilgan, s.yangilangan, t.nom AS twin_nom,
                  (SELECT count(*) FROM majlislar m WHERE m.suhbat_id = s.id) AS soni
           FROM suhbatlar s LEFT JOIN twinlar t ON t.id = s.twin_id
           WHERE s.user_id=%s AND s.arxiv = %s
           ORDER BY s.yangilangan DESC, s.id DESC""", uid, arxiv)


def suhbat_sarlavha(sid: int, sarlavha: str):
    pg.bajar("UPDATE suhbatlar SET sarlavha=%s WHERE id=%s",
             sarlavha.strip()[:80], sid)


def suhbat_soni(sid: int) -> int:
    """Suhbatdagi savol-javoblar soni."""
    r = pg.bitta("SELECT count(*) FROM majlislar WHERE suhbat_id=%s", sid)
    return int(r[0]) if r else 0


def suhbat_arxiv(sid: int, uid: int, arxiv: bool = True) -> bool:
    """Suhbatni yashiradi/qaytaradi (egasi tekshiruvi SQL da)."""
    r = pg.bitta("UPDATE suhbatlar SET arxiv=%s WHERE id=%s AND user_id=%s "
                 "RETURNING id", arxiv, sid, uid)
    return bool(r)


def suhbat_ochir(sid: int, uid: int) -> bool:
    """Butunlay o'chiradi (majlislar CASCADE bilan ketadi)."""
    r = pg.bitta("DELETE FROM suhbatlar WHERE id=%s AND user_id=%s RETURNING id",
                 sid, uid)
    return bool(r)


def suhbat_egasi(sid: int) -> int | None:
    r = pg.bitta("SELECT user_id FROM suhbatlar WHERE id=%s", sid)
    return r[0] if r else None


def suhbat_ol(sid: int) -> dict | None:
    return pg.bitta_d("SELECT * FROM suhbatlar WHERE id=%s", sid)


def suhbat_mavzu(uid: int, mavzu_id: int) -> int | None:
    """Shu mavzu uchun ochilgan dars suhbati (bo'lsa)."""
    r = pg.bitta(
        """SELECT id FROM suhbatlar WHERE user_id=%s AND mavzu_id=%s
           ORDER BY id DESC LIMIT 1""", uid, mavzu_id)
    return r[0] if r else None


def suhbat_mavzu_yoz(sid: int, mavzu_id: int):
    pg.bajar("UPDATE suhbatlar SET mavzu_id=%s WHERE id=%s", mavzu_id, sid)


def suhbat_majlislari(uid: int, sid: int) -> list[dict]:
    return pg.hammasi_d(
        """SELECT id, savol, xulosa, hisobot, biriktirma, davomiylik, twin_id,
                  vaqt, rejim, toxtatildi
           FROM majlislar WHERE user_id=%s AND suhbat_id=%s AND tugallandi
           ORDER BY id""", uid, sid)


# ---------------------------------------------------------------- chat (yordamchi)
# Chat javobi OQIM bilan keladi: qator avval yaratiladi (xarajat unga
# bog'lansin va to'xtatilgan javob ham saqlansin), oxirida to'ldiriladi.

def chat_boshla(uid: int, suhbat_id: int, twin_id: int | None, savol: str,
                rejim: str = "yordamchi") -> int:
    r = pg.bitta(
        """INSERT INTO majlislar(suhbat_id, user_id, twin_id, savol, rejim,
                                 tugallandi)
           VALUES(%s,%s,%s,%s,%s,false) RETURNING id""",
        suhbat_id, uid, twin_id, savol,
        rejim if rejim in ("yordamchi", "mentor", "maqsad") else "yordamchi")
    return r[0]


def chat_yakunla(mid: int, javob: str, hisobot: dict, davomiylik: int,
                 narx: float, savol_mustaqil: str = "",
                 toxtatildi: bool = False):
    pg.bajar(
        """UPDATE majlislar SET xulosa=%s, hisobot=%s, davomiylik=%s,
               narx_usd=%s, savol_mustaqil=%s, toxtatildi=%s, tugallandi=true
           WHERE id=%s""",
        javob, json.dumps(hisobot, ensure_ascii=False), davomiylik, narx,
        savol_mustaqil, toxtatildi, mid)
    pg.bajar(
        "UPDATE suhbatlar SET yangilangan = now() WHERE id = "
        "(SELECT suhbat_id FROM majlislar WHERE id=%s)", mid)


def chat_ochir(mid: int):
    """Yiqilgan javob qatorini olib tashlaydi (tarixda yarim qator qolmasin)."""
    pg.bajar("DELETE FROM majlislar WHERE id=%s", mid)


def chat_oxirgi(uid: int, sid: int) -> dict | None:
    """Suhbatdagi oxirgi savol-javob (qayta yaratish uchun)."""
    return pg.bitta_d(
        """SELECT id, savol, twin_id FROM majlislar
           WHERE user_id=%s AND suhbat_id=%s ORDER BY id DESC LIMIT 1""", uid, sid)


def majlis_yoz(uid: int, suhbat_id: int, twin_id: int | None, savol: str,
               savol_mustaqil: str, xulosa: str, hisobot: dict,
               davomiylik: int, job_id: int | None = None) -> int:
    r = pg.bitta(
        """INSERT INTO majlislar(suhbat_id, user_id, twin_id, job_id, savol,
                                 savol_mustaqil, xulosa, hisobot, davomiylik)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        suhbat_id, uid, twin_id, job_id, savol, savol_mustaqil, xulosa,
        json.dumps(hisobot, ensure_ascii=False), davomiylik)
    pg.bajar("UPDATE suhbatlar SET yangilangan = now() WHERE id=%s", suhbat_id)
    return r[0]


def majlis_ol(mid: int, uid: int | None = None) -> dict | None:
    if uid is None:
        return pg.bitta_d("SELECT * FROM majlislar WHERE id=%s", mid)
    return pg.bitta_d("SELECT * FROM majlislar WHERE id=%s AND user_id=%s", mid, uid)


def majlis_biriktirma(mid: int, s3_yol: str):
    pg.bajar("UPDATE majlislar SET biriktirma=%s WHERE id=%s", s3_yol, mid)


def majlis_hisobot(mid: int, hisobot: dict):
    """Hisobotni qayta yozadi (skill natijalari qo'shilganda)."""
    pg.bajar("UPDATE majlislar SET hisobot=%s WHERE id=%s",
             json.dumps(hisobot, ensure_ascii=False), mid)


def majlis_soni(uid: int) -> int:
    return pg.bitta("SELECT count(*) FROM majlislar WHERE user_id=%s", uid)[0]


def oxirgi_savollar(uid: int, n: int = 15) -> list[str]:
    qatorlar = pg.hammasi(
        "SELECT savol FROM majlislar WHERE user_id=%s ORDER BY id DESC LIMIT %s", uid, n)
    return [q[0] for q in qatorlar][::-1]
