# -*- coding: utf-8 -*-
"""Foydalanuvchilar, sessiyalar va majlis egaligi — SQLite (baza/kengash.db).

Har user faqat o'z majlislarini ko'radi. Birinchi ro'yxatdan o'tgan user
tizim egasi hisoblanadi — eski (egasiz) majlislar unga meros qilinadi.
"""
import json
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime

from .sozlama import BAZA, CHIQISH, USTOZ_YANGI

YOL = BAZA / "kengash.db"
SESSIYA_KUN = 60          # sessiya amal qilish muddati

_qulf = threading.RLock()
_ul = None


def _u() -> sqlite3.Connection:
    global _ul
    with _qulf:
        if _ul is None:
            BAZA.mkdir(parents=True, exist_ok=True)
            _ul = sqlite3.connect(str(YOL), check_same_thread=False)
            _ul.row_factory = sqlite3.Row
            _ul.execute("PRAGMA journal_mode=WAL")
            _ul.executescript("""
            CREATE TABLE IF NOT EXISTS userlar(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              tg_id INTEGER UNIQUE,
              ism TEXT NOT NULL,
              familiya TEXT DEFAULT '',
              username TEXT DEFAULT '',
              telefon TEXT DEFAULT '',
              foto TEXT DEFAULT '',
              profil TEXT DEFAULT '',
              yaratilgan TEXT,
              oxirgi_kirish TEXT);
            CREATE TABLE IF NOT EXISTS sessiyalar(
              token TEXT PRIMARY KEY,
              user_id INTEGER NOT NULL,
              yaratilgan TEXT,
              muddat REAL);
            CREATE TABLE IF NOT EXISTS majlislar(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              fayl TEXT UNIQUE,
              savol TEXT,
              vaqt TEXT,
              davomiylik INTEGER,
              direktorlar TEXT DEFAULT '[]');
            CREATE INDEX IF NOT EXISTS idx_majlis_user ON majlislar(user_id);
            CREATE TABLE IF NOT EXISTS suhbatlar(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              sarlavha TEXT DEFAULT '',
              yaratilgan TEXT,
              yangilangan TEXT);
            CREATE INDEX IF NOT EXISTS idx_suhbat_user ON suhbatlar(user_id);
            """)
            # migratsiya: eski bazaga yangi ustunlar (CREATE IF NOT EXISTS qo'shmaydi)
            ustunlar = {r[1] for r in _ul.execute("PRAGMA table_info(userlar)")}
            if "ustoz" not in ustunlar:
                # '' = barcha ustozlar bilimi (standart tanlov)
                _ul.execute("ALTER TABLE userlar ADD COLUMN ustoz TEXT DEFAULT ''")
            m_ustunlar = {r[1] for r in _ul.execute("PRAGMA table_info(majlislar)")}
            if "biriktirma" not in m_ustunlar:
                # majlisga biriktirilgan tayyor fayl (to'ldirilgan shablon)
                _ul.execute("ALTER TABLE majlislar ADD COLUMN biriktirma TEXT DEFAULT ''")
            if "suhbat_id" not in m_ustunlar:
                # har majlis bitta suhbatga (chat-sessiyaga) tegishli
                _ul.execute("ALTER TABLE majlislar ADD COLUMN suhbat_id INTEGER")
            _suhbat_backfill(_ul)
            _ul.commit()
    return _ul


def _suhbat_backfill(ul: sqlite3.Connection):
    """Suhbatsiz (eski) majlislar — har biri alohida suhbatga aylanadi.

    Idempotent: suhbat_id NULL qator qolmaguncha ishlaydi, keyin hech narsa qilmaydi."""
    qatorlar = ul.execute(
        "SELECT id,user_id,savol,vaqt FROM majlislar WHERE suhbat_id IS NULL").fetchall()
    for r in qatorlar:
        ul.execute(
            "INSERT INTO suhbatlar(user_id,sarlavha,yaratilgan,yangilangan) VALUES(?,?,?,?)",
            (r["user_id"], (r["savol"] or "")[:80], r["vaqt"], r["vaqt"]))
        sid = ul.execute("SELECT last_insert_rowid()").fetchone()[0]
        ul.execute("UPDATE majlislar SET suhbat_id=? WHERE id=?", (sid, r["id"]))


def _dict(r) -> dict | None:
    return dict(r) if r is not None else None


def _hozir() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- userlar

def _meros(uid: int, ul: sqlite3.Connection):
    """Eski (DB'dan oldingi) majlis fayllarini birinchi userga biriktiradi."""
    tarix = {}
    tj = CHIQISH / "tarix.jsonl"
    if tj.exists():
        for qator in tj.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(qator)
                tarix[r["fayl"]] = r
            except Exception:
                pass
    for f in sorted(CHIQISH.glob("majlis_*.md")):
        bor = ul.execute("SELECT 1 FROM majlislar WHERE fayl=?", (f.name,)).fetchone()
        if bor:
            continue
        r = tarix.get(f.name, {})
        savol = r.get("savol")
        if not savol:
            m = re.search(r"\*\*Savol:\*\* (.+)", f.read_text(encoding="utf-8"))
            savol = m.group(1).strip() if m else f.name
        vaqt = r.get("vaqt") or datetime.fromtimestamp(
            f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        ul.execute(
            "INSERT INTO majlislar(user_id,fayl,savol,vaqt,davomiylik,direktorlar) "
            "VALUES(?,?,?,?,?,?)",
            (uid, f.name, savol, vaqt, r.get("davomiylik"),
             json.dumps(r.get("direktorlar", []), ensure_ascii=False)))
    _suhbat_backfill(ul)   # meros majlislar ham suhbatlarga aylansin


def _yangi_user(ul, **f) -> int:
    # yangi user standart holatda USTOZ_YANGI bilimi bilan boshlaydi
    ul.execute(
        "INSERT INTO userlar(tg_id,ism,familiya,username,telefon,foto,ustoz,"
        "yaratilgan,oxirgi_kirish) VALUES(?,?,?,?,?,?,?,?,?)",
        (f.get("tg_id"), f.get("ism") or "Foydalanuvchi", f.get("familiya", ""),
         f.get("username", ""), f.get("telefon", ""), f.get("foto", ""),
         USTOZ_YANGI, _hozir(), _hozir()))
    uid = ul.execute("SELECT last_insert_rowid()").fetchone()[0]
    soni = ul.execute("SELECT COUNT(*) FROM userlar").fetchone()[0]
    if soni == 1:
        _meros(uid, ul)     # birinchi user — tizim egasi, eski majlislar uniki
    return uid


def user_tg(tg: dict) -> dict:
    """Telegram ma'lumotidan user yaratadi/yangilaydi. tg: id, first_name, ..."""
    with _qulf:
        ul = _u()
        r = ul.execute("SELECT * FROM userlar WHERE tg_id=?", (tg["id"],)).fetchone()
        if r:
            uid = r["id"]
            ul.execute(
                "UPDATE userlar SET ism=?, familiya=?, username=?, foto=?, "
                "telefon=CASE WHEN ?<>'' THEN ? ELSE telefon END, oxirgi_kirish=? WHERE id=?",
                (tg.get("first_name") or r["ism"], tg.get("last_name", "") or r["familiya"],
                 tg.get("username", "") or r["username"], tg.get("photo_url", "") or r["foto"],
                 tg.get("telefon", ""), tg.get("telefon", ""), _hozir(), uid))
        else:
            uid = _yangi_user(ul, tg_id=tg["id"], ism=tg.get("first_name", ""),
                              familiya=tg.get("last_name", ""),
                              username=tg.get("username", ""),
                              telefon=tg.get("telefon", ""),
                              foto=tg.get("photo_url", ""))
        ul.commit()
        return _dict(ul.execute("SELECT * FROM userlar WHERE id=?", (uid,)).fetchone())


def user_dev(ism: str) -> dict:
    """Dev-rejim (bot token yo'q payt): ism bo'yicha lokal akkaunt."""
    ism = ism.strip()[:60] or "Mehmon"
    with _qulf:
        ul = _u()
        r = ul.execute("SELECT * FROM userlar WHERE tg_id IS NULL AND ism=?",
                       (ism,)).fetchone()
        if r:
            uid = r["id"]
            ul.execute("UPDATE userlar SET oxirgi_kirish=? WHERE id=?", (_hozir(), uid))
        else:
            uid = _yangi_user(ul, ism=ism, username="dev")
        ul.commit()
        return _dict(ul.execute("SELECT * FROM userlar WHERE id=?", (uid,)).fetchone())


def user_ol(uid: int) -> dict | None:
    with _qulf:
        return _dict(_u().execute("SELECT * FROM userlar WHERE id=?", (uid,)).fetchone())


# ---------------------------------------------------------------- sessiyalar

def sessiya_yasa(uid: int) -> str:
    token = secrets.token_urlsafe(32)
    with _qulf:
        ul = _u()
        ul.execute("INSERT INTO sessiyalar(token,user_id,yaratilgan,muddat) VALUES(?,?,?,?)",
                   (token, uid, _hozir(), time.time() + SESSIYA_KUN * 86400))
        ul.execute("DELETE FROM sessiyalar WHERE muddat < ?", (time.time(),))
        ul.commit()
    return token


def sessiya_user(token: str) -> dict | None:
    if not token:
        return None
    with _qulf:
        ul = _u()
        r = ul.execute(
            "SELECT u.* FROM sessiyalar s JOIN userlar u ON u.id=s.user_id "
            "WHERE s.token=? AND s.muddat > ?", (token, time.time())).fetchone()
        return _dict(r)


def sessiya_ochir(token: str):
    with _qulf:
        ul = _u()
        ul.execute("DELETE FROM sessiyalar WHERE token=?", (token,))
        ul.commit()


# ---------------------------------------------------------------- suhbatlar (chat-sessiyalar)

def suhbat_yasa(uid: int, sarlavha: str) -> int:
    with _qulf:
        ul = _u()
        ul.execute(
            "INSERT INTO suhbatlar(user_id,sarlavha,yaratilgan,yangilangan) VALUES(?,?,?,?)",
            (uid, sarlavha.strip()[:80], _hozir(), _hozir()))
        sid = ul.execute("SELECT last_insert_rowid()").fetchone()[0]
        ul.commit()
        return sid


def suhbatlar(uid: int) -> list[dict]:
    """Userning suhbatlari (eskidan yangiga) + har birida nechta majlis borligi."""
    with _qulf:
        qatorlar = _u().execute(
            "SELECT s.id, s.sarlavha, s.yaratilgan, s.yangilangan, "
            "       COUNT(m.id) AS soni "
            "FROM suhbatlar s LEFT JOIN majlislar m ON m.suhbat_id=s.id "
            "WHERE s.user_id=? GROUP BY s.id ORDER BY s.yangilangan, s.id",
            (uid,)).fetchall()
        return [dict(r) for r in qatorlar]


def suhbat_egasi(sid: int) -> int | None:
    with _qulf:
        r = _u().execute("SELECT user_id FROM suhbatlar WHERE id=?", (sid,)).fetchone()
        return r["user_id"] if r else None


def suhbat_majlislari(uid: int, sid: int) -> list[dict]:
    """Bitta suhbatning majlislari — xronologik (faqat egasiga)."""
    with _qulf:
        qatorlar = _u().execute(
            "SELECT fayl,savol,vaqt,davomiylik,direktorlar,biriktirma FROM majlislar "
            "WHERE user_id=? AND suhbat_id=? ORDER BY id", (uid, sid)).fetchall()
    nat = []
    for r in qatorlar:
        d = dict(r)
        try:
            d["direktorlar"] = json.loads(d["direktorlar"] or "[]")
        except Exception:
            d["direktorlar"] = []
        nat.append(d)
    return nat


# ---------------------------------------------------------------- majlislar

def majlis_yoz(uid: int, fayl: str, savol: str, davomiylik: int, direktorlar: list,
               suhbat_id: int | None = None):
    with _qulf:
        ul = _u()
        # UPSERT (INSERT OR REPLACE EMAS): REPLACE qatorni o'chirib qayta yozadi —
        # keyin qo'yilgan biriktirma (shablon fayli) yo'qolib qolardi
        ul.execute(
            "INSERT INTO majlislar(user_id,fayl,savol,vaqt,davomiylik,direktorlar,suhbat_id) "
            "VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(fayl) DO UPDATE SET user_id=excluded.user_id, "
            "savol=excluded.savol, davomiylik=excluded.davomiylik, "
            "direktorlar=excluded.direktorlar, "
            "suhbat_id=COALESCE(excluded.suhbat_id, majlislar.suhbat_id)",
            (uid, fayl, savol, _hozir(), davomiylik,
             json.dumps(direktorlar, ensure_ascii=False), suhbat_id))
        if suhbat_id:
            ul.execute("UPDATE suhbatlar SET yangilangan=? WHERE id=?",
                       (_hozir(), suhbat_id))
        ul.commit()


def majlislar(uid: int) -> list[dict]:
    """Userning majlislari — xronologik (eskidan yangiga)."""
    with _qulf:
        qatorlar = _u().execute(
            "SELECT fayl,savol,vaqt,davomiylik,direktorlar,biriktirma FROM majlislar "
            "WHERE user_id=? ORDER BY id", (uid,)).fetchall()
    nat = []
    for r in qatorlar:
        d = dict(r)
        try:
            d["direktorlar"] = json.loads(d["direktorlar"] or "[]")
        except Exception:
            d["direktorlar"] = []
        nat.append(d)
    return nat


def majlis_egasi(fayl: str) -> int | None:
    with _qulf:
        r = _u().execute("SELECT user_id FROM majlislar WHERE fayl=?", (fayl,)).fetchone()
        return r["user_id"] if r else None


def biriktirma_yoz(fayl: str, biriktirma: str):
    """Majlisga tayyor fayl (to'ldirilgan shablon) biriktiriladi."""
    with _qulf:
        ul = _u()
        ul.execute("UPDATE majlislar SET biriktirma=? WHERE fayl=?", (biriktirma, fayl))
        ul.commit()


def biriktirma_egasi(biriktirma: str) -> int | None:
    with _qulf:
        r = _u().execute("SELECT user_id FROM majlislar WHERE biriktirma=?",
                         (biriktirma,)).fetchone()
        return r["user_id"] if r else None


def majlis_soni(uid: int) -> int:
    with _qulf:
        return _u().execute("SELECT COUNT(*) FROM majlislar WHERE user_id=?",
                            (uid,)).fetchone()[0]


# ---------------------------------------------------------------- ustoz (bilim manbasi)

def ustoz_ol(uid: int) -> str:
    """User tanlagan bilim manbasi ('' = barcha ustozlar)."""
    with _qulf:
        r = _u().execute("SELECT ustoz FROM userlar WHERE id=?", (uid,)).fetchone()
        return (r["ustoz"] or "") if r else ""


def ustoz_yoz(uid: int, ustoz: str):
    with _qulf:
        ul = _u()
        ul.execute("UPDATE userlar SET ustoz=? WHERE id=?", (ustoz.strip()[:60], uid))
        ul.commit()


# ---------------------------------------------------------------- profil (user o'rganish)

def profil_ol(uid: int) -> str:
    with _qulf:
        r = _u().execute("SELECT profil FROM userlar WHERE id=?", (uid,)).fetchone()
        return (r["profil"] or "") if r else ""


def profil_yoz(uid: int, matn: str):
    with _qulf:
        ul = _u()
        ul.execute("UPDATE userlar SET profil=? WHERE id=?", (matn[:2000], uid))
        ul.commit()


def savollar(uid: int, n: int = 15) -> list[str]:
    """Userning oxirgi savollari — profilni o'rganish uchun."""
    with _qulf:
        qatorlar = _u().execute(
            "SELECT savol FROM majlislar WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (uid, n)).fetchall()
    return [r["savol"] for r in qatorlar][::-1]
