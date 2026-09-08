# -*- coding: utf-8 -*-
"""Platforma sozlamalari: muhit o'zgaruvchilari, loglash.

Lokalda .env.platforma dan o'qiladi; Railway'da env to'g'ridan-to'g'ri keladi.
"""
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ILDIZ = Path(__file__).resolve().parent          # platforma/
LOYIHA = ILDIZ.parent                             # VoIpTelefoniya/

_ENV_FAYL = LOYIHA / ".env.platforma"
if _ENV_FAYL.exists():
    for q in _ENV_FAYL.read_text(encoding="utf-8").splitlines():
        q = q.strip()
        if q and not q.startswith("#") and "=" in q:
            k, _, v = q.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

RAILWAYDAMI = bool(os.environ.get("RAILWAY_ENVIRONMENT"))

# Jonli muhit bayrog'i. Railway o'zi belgi qo'yadi; o'z serverimizda (docker)
# PROD=1 qo'lda beriladi. Bu bayroqqa xavfsizlik qarorlari bog'langan —
# masalan parolsiz "dev" kirish jonli muhitda hech qachon yoqilmaydi
# (qarang auth.dev_rejim). Shuning uchun u platformaga bog'liq emas.
PROD = RAILWAYDAMI or os.environ.get("PROD", "").strip() == "1"
MUHIT = "railway" if RAILWAYDAMI else ("server" if PROD else "lokal")

PG_URL = os.environ.get("PG_URL") or os.environ.get("DATABASE_URL", "")

# S3 (MinIO) manzili muhitga qarab uch xil bo'ladi:
#   Railway  — ichki tarmoq (minio.railway.internal)
#   o'z server — docker tarmog'idagi konteyner nomi (S3_ENDPOINT)
#   lokal    — tashqi TCP proksi (S3_ENDPOINT_TASHQI); lokal .env'da ikkala
#              nom ham bor, shuning uchun bu yerda ular ATAYLAB ajratilgan.
if RAILWAYDAMI:
    S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://minio.railway.internal:9000")
elif PROD:
    S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "")
else:
    S3_ENDPOINT = os.environ.get("S3_ENDPOINT_TASHQI", "")
S3_KIRISH = os.environ.get("S3_KIRISH", "")
S3_MAXFIY = os.environ.get("S3_MAXFIY", "")
S3_BAKET = os.environ.get("S3_BAKET", "kengash")


def log(xabar: str):
    print(f"[{time.strftime('%H:%M:%S')}] {xabar}", flush=True)
