# -*- coding: utf-8 -*-
"""Worker — fon-ishlarni bajaruvchi jarayon.

  python -m platforma.worker                # doimiy sikl (Railway'da shu)
  python -m platforma.worker --bir-aylanish # navbat bo'shaguncha ishlab chiqadi (sinov)

Handler'lar registri: har job turi uchun funksiya (job, yoz) -> natija dict.
Og'ir bosqichlar (STT, majlis, ffmpeg...) keyingi bosqichlarda shu registrga qo'shiladi.
"""
import argparse
import time
import traceback

from . import jobs, pg
from .sozlama import log

HANDLERLAR = {}


def handler(tur: str):
    def dek(fn):
        HANDLERLAR[tur] = fn
        return fn
    return dek


# ---------------------------------------------------------------- handlerlar

@handler("sinov")
def _sinov(job: dict, yoz):
    yoz("sinov job boshlandi")
    time.sleep(1)
    yoz("ishlanmoqda...")
    time.sleep(1)
    yoz("sinov job tugadi")
    return {"salom": "dunyo", "kirish": job["kirish"]}


@handler("majlis")
def _majlis(job: dict, yoz):
    from . import majlis
    return majlis.bajar(job, yoz)


@handler("profil")
def _profil(job: dict, yoz):
    from . import profil
    profil.yangila(job["user_id"])
    return {"ok": True}


@handler("ingest_fayl")
def _ingest_fayl(job: dict, yoz):
    from . import ingest
    return ingest.bajar(job, yoz)


@handler("ingest_url")
def _ingest_url(job: dict, yoz):
    from . import ingest
    return ingest.bajar(job, yoz)


@handler("sahifa_render")
def _sahifa_render(job: dict, yoz):
    from . import ingest
    return ingest.sahifa_render(job, yoz)


@handler("fragment")
def _fragment(job: dict, yoz):
    from . import fragment
    return fragment.bajar(job, yoz)


@handler("tg_fragment")
def _tg_fragment(job: dict, yoz):
    from . import fragment
    return fragment.tg_yubor(job, yoz)


@handler("kurs_qur")
def _kurs_qur(job: dict, yoz):
    """Twin bilimidan o'quv dasturi qoralamasini quradi (egasi tasdiqlaydi)."""
    from . import oquv
    return oquv.kurs_qur(job, yoz)


@handler("vazifa_tekshir")
def _vazifa_tekshir(job: dict, yoz):
    from . import vazifa
    return vazifa.tekshir(job, yoz)


@handler("vazifa_eslatma")
def _vazifa_eslatma(job: dict, yoz):
    """Muddati yaqinlashgan uy vazifalari bo'yicha bildirishnoma (soatlik)."""
    from . import vazifa
    return vazifa.eslatma(job, yoz)


@handler("maqsad_reja")
def _maqsad_reja(job: dict, yoz):
    """Foydalanuvchi maqsadidan qadamli reja quradi (qoralama holatda)."""
    from . import maqsad
    return maqsad.reja_qur(job, yoz)


@handler("maqsad_yakun")
def _maqsad_yakun(job: dict, yoz):
    """Sikl natijasi tahlili + keyingi sikl uchun prognozli takliflar."""
    from . import maqsad
    return maqsad.yakunla(job, yoz)


@handler("maqsad_eslatma")
def _maqsad_eslatma(job: dict, yoz):
    """Kechikkan qadamlar va jim qolgan sikllar bo'yicha eslatma (kunlik)."""
    from . import maqsad
    return maqsad.eslatma(job, yoz)


@handler("tizim_xulosa")
def _tizim_xulosa(job: dict, yoz):
    """CJM/EJM diagnostikasi natijasidan xulosa (biznes halqasi, 1-qadam)."""
    from . import tizim
    return tizim.xulosa_qur(job, yoz)


@handler("tizim_reja")
def _tizim_reja(job: dict, yoz):
    """Bitta bo'lim uchun reja qoralamasi: SSP, mediaplan, moliya modeli..."""
    from . import tizim
    return tizim.reja_qur(job, yoz)


@handler("obuna_nazorat")
def _obuna_nazorat(job: dict, yoz):
    """Muddati tugagan obunalarni yopadi va eslatma yuboradi (soatlik)."""
    from . import pul
    return pul.nazorat(yoz)


@handler("tolov_tozala")
def _tolov_tozala(job: dict, yoz):
    """Muddati o'tgan kutilayotgan to'lovlarni bekor qiladi (soatlik)."""
    from . import pul
    return pul.tolov_tozala(yoz)


@handler("zaxira")
def _zaxira(job: dict, yoz):
    """pg_dump -> MinIO (haftalik)."""
    from . import zaxira
    return zaxira.bajar(job, yoz)


@handler("b2b_tozala")
def _b2b_tozala(job: dict, yoz):
    """Eskirgan B2B idempotentlik yozuvlarini o'chiradi (kunlik)."""
    from . import b2b
    n = b2b.idempotent_tozala()
    yoz(f"{n} ta eskirgan idempotentlik yozuvi o'chirildi")
    return {"ochirilgan": n}


# ---------------------------------------------------------------- asosiy sikl

def bitta_job() -> bool:
    """Bitta jobni oladi va bajaradi. Job bo'lmasa False."""
    job = jobs.talab()
    if job is None:
        return False
    jid = job["id"]

    def yoz(qator: str):
        jobs.yoz(jid, qator)

    fn = HANDLERLAR.get(job["tur"])
    if fn is None:
        # Eski versiyadagi worker yangi job turini bilmasligi mumkin (rolling deploy):
        # yakuniy xato deb yozmaymiz — navbatga qaytaramiz, yangi worker oladi.
        jobs.yiqildi(jid, f"bu worker '{job['tur']}' turini bilmaydi",
                     job["urinish"], max(job["max_urinish"], 5))
        return True
    try:
        natija = fn(job, yoz)
        jobs.tayyor(jid, natija)
    except Exception as e:
        traceback.print_exc()
        jobs.yiqildi(jid, str(e), job["urinish"], job["max_urinish"])
        _bepulni_qaytar(job)
        # Yakuniy yiqilish bo'lsa — adminga xabar
        r = pg.bitta("SELECT holat FROM jobs WHERE id=%s", jid)
        if r and r[0] == "xato":
            _yakuniy_xato(job, e)
            from . import monitoring
            monitoring.job_xatosi(job, str(e))
    return True


def _yakuniy_xato(job: dict, e: Exception):
    """Job butunlay yiqilganda foydalanuvchi ishi yo'qolib qolmasin."""
    if job["tur"] == "vazifa_tekshir":
        from . import vazifa
        vid = (job.get("kirish") or {}).get("vazifa_id")
        if vid:
            try:
                vazifa.qaytar(int(vid))
            except Exception as x:                            # noqa: BLE001
                log(f"vazifa qaytarilmadi: {str(x)[:100]}")
    elif job["tur"] in ("maqsad_reja", "maqsad_yakun"):
        from . import maqsad
        mid = (job.get("kirish") or {}).get("maqsad_id")
        if mid:
            try:
                maqsad.qaytar(int(mid))
            except Exception as x:                            # noqa: BLE001
                log(f"maqsad qaytarilmadi: {str(x)[:100]}")
    elif job["tur"] == "tizim_xulosa":
        from . import tizim
        did = (job.get("kirish") or {}).get("diagnostika_id")
        if did:
            try:
                tizim.diag_qaytar(int(did))
            except Exception as x:                            # noqa: BLE001
                log(f"diagnostika qaytarilmadi: {str(x)[:100]}")


def _bepulni_qaytar(job: dict):
    """Majlis butunlay yiqilsa, band qilingan bepul promptni qaytaramiz.

    Foydalanuvchi javob olmadi — hisobdan yechilmasin.
    """
    if job["tur"] != "majlis" or not job.get("user_id"):
        return
    if not (job.get("kirish") or {}).get("bepul"):
        return
    r = pg.bitta("SELECT holat FROM jobs WHERE id=%s", job["id"])
    if not r or r[0] != "xato":      # hali qayta urinish bor
        return
    from . import pul
    pul.bepul_qaytar(job["user_id"])
    jobs.yoz(job["id"], "bepul prompt qaytarildi (majlis yiqildi)")


def _navbatga(tur: str, oraliq: str, ustunlik: int, muhlat_s: int):
    """Davriy jobni navbatga qo'yadi — ikki nusxa va tez-tez takror bo'lmasin."""
    bor = pg.bitta(
        f"""SELECT 1 FROM jobs WHERE tur=%s
            AND (holat IN ('navbatda','ketmoqda')
                 OR (holat IN ('tayyor','xato')
                     AND tugagan > now() - interval '{oraliq}'))
            LIMIT 1""", tur)
    if not bor:
        jobs.qoshish(tur, {}, ustunlik=ustunlik, muhlat_s=muhlat_s)


def _davriy_ish(oxirgi: float) -> float:
    """Davriy ishlar: soatlik obuna nazorati, haftalik zaxira."""
    if time.time() - oxirgi < 3600:
        return oxirgi
    try:
        _navbatga("obuna_nazorat", "55 minutes", 7, 300)
        _navbatga("tolov_tozala", "55 minutes", 7, 120)
        _navbatga("vazifa_eslatma", "55 minutes", 7, 300)
        _navbatga("maqsad_eslatma", "20 hours", 8, 300)
        _navbatga("zaxira", "6 days", 8, zaxira_muhlat())
        _navbatga("b2b_tozala", "20 hours", 9, 120)
    except Exception as e:                                   # noqa: BLE001
        log(f"davriy ish navbatga qo'yilmadi: {str(e)[:100]}")
    return time.time()


def zaxira_muhlat() -> int:
    from . import zaxira
    return zaxira.MUHLAT_S


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bir-aylanish", action="store_true",
                   help="navbat bo'shagach chiqish (sinov rejimi)")
    args = p.parse_args()

    pg.migratsiya()
    from . import storage
    storage.baket_yumshoq()
    log(f"WORKER ishga tushdi ({len(HANDLERLAR)} handler: {', '.join(HANDLERLAR)})")

    oxirgi_reaper = 0.0
    oxirgi_davriy = 0.0
    while True:
        if time.time() - oxirgi_reaper > 30:
            jobs.qotganlarni_qaytar()
            oxirgi_davriy = _davriy_ish(oxirgi_davriy)
            oxirgi_reaper = time.time()
        bor = bitta_job()
        if not bor:
            if args.bir_aylanish:
                log("navbat bo'sh — chiqildi (sinov rejimi)")
                return
            time.sleep(1)


if __name__ == "__main__":
    main()
