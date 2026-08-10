# -*- coding: utf-8 -*-
"""Majlis navbati — ko'p foydalanuvchi rejimi.

Qdrant lokal va log oqimi bitta jarayonga mo'ljallangani uchun majlislar
BITTA ishchi oqimda, navbat bilan bajariladi (har majlis ~20-30s).
Har job faqat egasiga ko'rinadi.
"""
import secrets
import threading
import time
from collections import deque

from . import db, profil, shablon, sozlama, suhbat, tg
from .majlis import majlis

NAVBAT = deque()          # kutayotgan joblar
JOBLAR = {}               # id -> job
_qulf = threading.Lock()
_joriy = {"job": None}    # hozir ishlanayotgan job (bitta ishchi -> poyga yo'q)
_ishchi_bor = [False]

SAQLASH = 3600            # tugagan job xotirada qancha turadi (soniya)


def _tinglovchi(qator: str):
    j = _joriy["job"]
    if j is None:
        return
    # Fon oqimlarining loglari (TG bot, profil o'rganish) shu payt ketayotgan
    # majlis jurnaliga aralashmasin — ular jobga tegishli emas
    if "] TG " in qator or "profil yangila" in qator:
        return
    j["loglar"].append(qator)


sozlama.LOG_TINGLOVCHILAR.append(_tinglovchi)


def _tozala():
    eski = [i for i, j in JOBLAR.items()
            if j["holat"] in ("tayyor", "xato") and time.time() - j["tugadi"] > SAQLASH]
    for i in eski:
        JOBLAR.pop(i, None)


def _ishla(job: dict):
    job["holat"] = "ketmoqda"
    job["boshladi"] = time.time()
    _joriy["job"] = job
    try:
        p = db.profil_ol(job["user_id"])
        # suhbat davomiyligi: FAQAT shu chat-sessiya ichidagi savol-javoblar
        ktx = suhbat.kontekst(job["user_id"], job.get("suhbat"))
        savol_m = suhbat.mustaqil(job["savol"], ktx)
        yol = majlis(savol_m, hamma=job["hamma"], foydalanuvchi=p,
                     suhbat=suhbat.formatla(ktx),
                     ustoz=db.ustoz_ol(job["user_id"]))
        job["fayl"] = yol.name
        job["davomiylik"] = round(time.time() - job["boshladi"])
        db.majlis_yoz(job["user_id"], yol.name, job["savol"], job["davomiylik"],
                      job.get("direktorlar", []), suhbat_id=job.get("suhbat"))
        # shablon: savol hujjat tuzishni so'ragan bo'lsa — tayyor fayl yasaymiz
        try:
            sh = shablon.mos(job["savol"])
            if sh:
                sozlama.log(f"Shablon aniqlandi: {sh} — fayl tayyorlanmoqda...")
                matn = yol.read_text(encoding="utf-8")
                m = suhbat.XULOSA_RE.search(matn)
                f2 = shablon.toldir(sh, job["savol"],
                                    m.group(1) if m else matn[:7000])
                job["biriktirma"] = f2.name
                db.biriktirma_yoz(yol.name, f2.name)
                # Telegram bilan bog'langan userga faylni chatiga ham yuboramiz
                tg.hujjat_yubor(job["user_id"], f2,
                                f"📎 «{job['savol'][:80]}» savolingiz bo'yicha "
                                f"kengash tayyorlagan fayl")
        except Exception as e:
            sozlama.log(f"Shablon xizmati xatosi (majlisga ta'sir qilmaydi): {str(e)[:120]}")
        job["holat"] = "tayyor"
        # user o'rganish — fonda, majlisni kutdirmaydi
        threading.Thread(target=profil.yangila, args=(job["user_id"],),
                         daemon=True).start()
    except Exception as e:
        job["xato"] = str(e)[:300]
        job["holat"] = "xato"
        sozlama.log(f"MAJLIS XATO: {e}")
    finally:
        job["tugadi"] = time.time()
        _joriy["job"] = None


def _ishchi():
    while True:
        with _qulf:
            job = NAVBAT.popleft() if NAVBAT else None
        if job is None:
            time.sleep(0.5)
            continue
        # Ishchi oqim HECH QACHON o'lmasligi shart: u o'lsa _ishchi_bor True
        # bo'lib qoladi, yangisi yaratilmaydi va navbat abadiy qotadi.
        try:
            _ishla(job)
            # direktorlar ro'yxatini loglardan DB ga ham yozamiz (chiplar uchun)
            if job["holat"] == "tayyor":
                rollar = []
                for q in job["loglar"]:
                    for rol in ("CEO", "CTO", "CFO", "COO", "CLO", "CMO"):
                        if f"{rol} javob berdi" in q and rol not in rollar:
                            rollar.append(rol)
                if rollar:
                    db.majlis_yoz(job["user_id"], job["fayl"], job["savol"],
                                  job["davomiylik"], rollar,
                                  suhbat_id=job.get("suhbat"))
        except Exception as e:
            sozlama.log(f"ISHCHI XATO (oqim himoyalandi): {str(e)[:200]}")
            if job["holat"] != "tayyor":     # hisobot chiqqan bo'lsa "tayyor" qoladi
                job["xato"] = str(e)[:300]
                job["holat"] = "xato"
                job["tugadi"] = time.time()
        with _qulf:
            _tozala()


def _ishchini_uygot():
    with _qulf:
        if not _ishchi_bor[0]:
            _ishchi_bor[0] = True
            threading.Thread(target=_ishchi, daemon=True).start()


def faol(user_id: int) -> dict | None:
    """Userning hozir navbatda yoki ishlanayotgan jobi."""
    with _qulf:
        for j in JOBLAR.values():
            if j["user_id"] == user_id and j["holat"] in ("navbatda", "ketmoqda"):
                return j
    return None


def qoshish(user_id: int, savol: str, hamma: bool, suhbat_id: int | None = None) -> dict:
    """Yangi majlis navbatga qo'shiladi. Bir userda bitta faol job bo'ladi."""
    _ishchini_uygot()
    bor = faol(user_id)
    if bor:
        raise ValueError("Sizning majlisingiz allaqachon ketmoqda — tugashini kuting")
    job = {"id": secrets.token_hex(8), "user_id": user_id, "savol": savol,
           "hamma": hamma, "suhbat": suhbat_id, "holat": "navbatda",
           "loglar": [], "fayl": None,
           "biriktirma": None, "xato": None, "yaratilgan": time.time(),
           "boshladi": None, "tugadi": None, "davomiylik": None}
    with _qulf:
        JOBLAR[job["id"]] = job
        NAVBAT.append(job)
    return job


def holat(job_id: str, user_id: int) -> dict | None:
    """Job holati — faqat egasiga."""
    j = JOBLAR.get(job_id)
    if not j or j["user_id"] != user_id:
        return None
    with _qulf:
        orin = next((i + 1 for i, x in enumerate(NAVBAT) if x["id"] == job_id), 0)
    return {"id": j["id"], "savol": j["savol"], "holat": j["holat"],
            "suhbat": j.get("suhbat"), "navbat_orni": orin,
            "loglar": j["loglar"][-200:],
            "fayl": j["fayl"], "biriktirma": j.get("biriktirma"),
            "xato": j["xato"]}
