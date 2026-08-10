# -*- coding: utf-8 -*-
"""PostgreSQL: ulanish puli + migratsiyalar.

Foydalanish:
  from platforma import pg
  with pg.ulanish() as u, u.cursor() as k: k.execute(...)

Migratsiyalar: platforma/migratsiyalar/NNN_nom.sql — tartib bilan, bir marta.
  python -m platforma.pg   # migratsiyalarni qo'llaydi
"""
from contextlib import contextmanager
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .sozlama import ILDIZ, PG_URL, log

MIGRATSIYALAR = ILDIZ / "migratsiyalar"

_pul: ConnectionPool | None = None


def _sozla(u):
    """Har yangi ulanishga vector turini ro'yxatdan o'tkazamiz (pgvector)."""
    try:
        from pgvector.psycopg import register_vector
        register_vector(u)
    except Exception:
        pass      # vector kengaytmasi hali yo'q bo'lsa (birinchi migratsiya) — muhim emas


def pul() -> ConnectionPool:
    global _pul
    if _pul is None:
        if not PG_URL:
            raise SystemExit("PG_URL topilmadi (.env.platforma yoki DATABASE_URL)")
        # check: puldan olingan ulanish "tirik"ligini tekshiradi. Railway PG
        # proksisi bo'sh turgan ulanishni uzib qo'yadi — tekshiruvsiz o'lik
        # ulanish so'rovga berilib, "SSL error: unexpected eof" chiqardi.
        # max_idle: uzoq bo'sh ulanishlarni o'zimiz yopamiz (proksi yopishidan oldin).
        _pul = ConnectionPool(PG_URL, min_size=1, max_size=10, open=True,
                              configure=_sozla, check=ConnectionPool.check_connection,
                              max_idle=120, kwargs={"autocommit": False})
    return _pul


@contextmanager
def ulanish():
    """Tranzaksiyali ulanish: blok muvaffaqiyatli tugasa commit, aks holda rollback."""
    with pul().connection() as u:
        yield u


def bitta(sql: str, *args):
    """Bitta qator qaytaradigan qulay yordamchi."""
    with ulanish() as u, u.cursor() as k:
        k.execute(sql, args or None)
        return k.fetchone()


def hammasi(sql: str, *args):
    with ulanish() as u, u.cursor() as k:
        k.execute(sql, args or None)
        return k.fetchall()


def bajar(sql: str, *args):
    with ulanish() as u, u.cursor() as k:
        k.execute(sql, args or None)


def bitta_d(sql: str, *args) -> dict | None:
    """Bitta qator — lug'at ko'rinishida."""
    with ulanish() as u, u.cursor(row_factory=dict_row) as k:
        k.execute(sql, args or None)
        return k.fetchone()


def hammasi_d(sql: str, *args) -> list[dict]:
    with ulanish() as u, u.cursor(row_factory=dict_row) as k:
        k.execute(sql, args or None)
        return k.fetchall()


def migratsiya():
    """Qo'llanmagan .sql fayllarni tartib bilan qo'llaydi (har biri tranzaksiyada)."""
    with ulanish() as u, u.cursor() as k:
        k.execute("""CREATE TABLE IF NOT EXISTS migratsiyalar(
                       nom TEXT PRIMARY KEY, vaqt timestamptz DEFAULT now())""")
    qollangan = {r[0] for r in hammasi("SELECT nom FROM migratsiyalar")}
    fayllar = sorted(MIGRATSIYALAR.glob("*.sql"))
    yangi = 0
    for f in fayllar:
        if f.name in qollangan:
            continue
        log(f"migratsiya: {f.name}")
        with ulanish() as u, u.cursor() as k:
            k.execute(f.read_text(encoding="utf-8"))
            k.execute("INSERT INTO migratsiyalar(nom) VALUES(%s)", (f.name,))
        yangi += 1
    log(f"migratsiya tayyor: {yangi} yangi, jami {len(fayllar)}")


if __name__ == "__main__":
    migratsiya()
