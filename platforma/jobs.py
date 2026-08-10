# -*- coding: utf-8 -*-
"""Fon-ishlar navbati — Postgres asosida (SKIP LOCKED).

WEB faqat qo'shadi va holat o'qiydi; WORKER oladi va bajaradi.
Xatoda eksponensial kutish bilan qayta uriniladi; qotgan job muhlati
o'tgach avtomatik navbatga qaytariladi.
"""
import json

from . import pg
from .sozlama import log as _log


def qoshish(tur: str, kirish: dict | None = None, user_id: int | None = None,
            twin_id: int | None = None, ustunlik: int = 5,
            muhlat_s: int = 900, max_urinish: int = 3) -> int:
    r = pg.bitta(
        """INSERT INTO jobs(tur, kirish, user_id, twin_id, ustunlik, muhlat_s, max_urinish)
           VALUES(%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        tur, json.dumps(kirish or {}, ensure_ascii=False), user_id, twin_id,
        ustunlik, muhlat_s, max_urinish)
    return r[0]


def yoz(job_id: int, qator: str):
    """Job jurnaliga qator qo'shadi (UI jonli o'qiydi)."""
    pg.bajar("INSERT INTO job_loglar(job_id, qator) VALUES(%s, %s)", job_id, qator)
    _log(f"[job {job_id}] {qator}")


# Navbatdan olish so'rovi — alohida nom bilan: sinovlar aynan shu bayonotni
# o'z tranzaksiyasida ishlata olsin (tartib qoidasi bir joyda tursin).
TALAB_SQL = """
    UPDATE jobs SET holat='ketmoqda', boshlangan=now(), urinish=urinish+1
    WHERE id = (SELECT id FROM jobs
                WHERE holat='navbatda' AND keyin <= now()
                ORDER BY ustunlik, id LIMIT 1
                FOR UPDATE SKIP LOCKED)
    RETURNING id, tur, kirish, user_id, twin_id, urinish, max_urinish, muhlat_s"""


def talab() -> dict | None:
    """Navbatdan bitta jobni oladi (atomar, parallel workerlarga xavfsiz)."""
    r = pg.bitta(TALAB_SQL)
    if not r:
        return None
    return {"id": r[0], "tur": r[1], "kirish": r[2], "user_id": r[3],
            "twin_id": r[4], "urinish": r[5], "max_urinish": r[6], "muhlat_s": r[7]}


def tayyor(job_id: int, natija: dict | None = None):
    pg.bajar("UPDATE jobs SET holat='tayyor', natija=%s, tugagan=now() WHERE id=%s",
             json.dumps(natija or {}, ensure_ascii=False), job_id)


def yiqildi(job_id: int, xato: str, urinish: int, max_urinish: int):
    """Xato: urinishlar qolgan bo'lsa kechiktirib navbatga qaytadi, aks holda yakuniy xato."""
    if urinish < max_urinish:
        kutish = min(600, 15 * (2 ** (urinish - 1)))   # 15s, 30s, 60s...
        pg.bajar(
            """UPDATE jobs SET holat='navbatda', xato=%s,
               keyin = now() + make_interval(secs => %s) WHERE id=%s""",
            xato[:500], kutish, job_id)
        yoz(job_id, f"xato ({urinish}/{max_urinish}): {xato[:160]} — {kutish}s dan keyin qayta")
    else:
        pg.bajar("UPDATE jobs SET holat='xato', xato=%s, tugagan=now() WHERE id=%s",
                 xato[:500], job_id)
        yoz(job_id, f"YAKUNIY XATO: {xato[:160]}")


def qotganlarni_qaytar():
    """Muhlatidan oshgan 'ketmoqda' joblar — worker o'lgan/qotgan: navbatga qaytadi."""
    qatorlar = pg.hammasi(
        """UPDATE jobs SET holat = CASE WHEN urinish >= max_urinish THEN 'xato'
                                        ELSE 'navbatda' END,
               xato = COALESCE(xato,'') || ' [muhlat oshdi]',
               keyin = now() + interval '10 seconds'
           WHERE holat='ketmoqda'
             AND boshlangan < now() - make_interval(secs => muhlat_s)
           RETURNING id""")
    for (jid,) in qatorlar:
        yoz(jid, "muhlat oshdi — navbatga qaytarildi")
    return len(qatorlar)


def holat(job_id: int, user_id: int | None = None) -> dict | None:
    """Job holati + oxirgi loglar (user_id berilsa egalik tekshiriladi)."""
    r = pg.bitta(
        """SELECT id, tur, holat, natija, xato, user_id, yaratilgan, boshlangan, tugagan
           FROM jobs WHERE id=%s""", job_id)
    if not r or (user_id is not None and r[5] != user_id):
        return None
    loglar = [q[0] for q in pg.hammasi(
        "SELECT qator FROM job_loglar WHERE job_id=%s ORDER BY id DESC LIMIT 200",
        job_id)][::-1]
    return {"id": r[0], "tur": r[1], "holat": r[2], "natija": r[3], "xato": r[4],
            "loglar": loglar}
