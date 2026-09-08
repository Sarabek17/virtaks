# -*- coding: utf-8 -*-
"""Fayl ombori — S3 (MinIO/R2/AWS mos). Web ham, worker ham shu orqali ishlaydi.

Asl manbalar, slayd PNG'lari, audio kesmalari, to'ldirilgan Excel'lar shu yerda.
"""
import io

import boto3
from botocore.config import Config

from .sozlama import S3_BAKET, S3_ENDPOINT, S3_KIRISH, S3_MAXFIY, log

_kesh = {}


def klient():
    if "s3" not in _kesh:
        if not S3_ENDPOINT:
            raise RuntimeError("S3_ENDPOINT sozlanmagan")
        _kesh["s3"] = boto3.client(
            "s3", endpoint_url=S3_ENDPOINT,
            aws_access_key_id=S3_KIRISH, aws_secret_access_key=S3_MAXFIY,
            config=Config(signature_version="s3v4",
                          retries={"max_attempts": 3},
                          connect_timeout=10, read_timeout=120),
            region_name="us-east-1")
    return _kesh["s3"]


def baket_tayyorla():
    """Baket bo'lmasa yaratadi (idempotent)."""
    s3 = klient()
    try:
        s3.head_bucket(Bucket=S3_BAKET)
    except Exception:
        s3.create_bucket(Bucket=S3_BAKET)
        log(f"S3 baket yaratildi: {S3_BAKET}")


def baket_yumshoq():
    """Baketni tayyorlaydi, lekin xato bo'lsa jarayonni TO'XTATMAYDI.

    Web va worker ishga tushganda chaqiriladi. Yangi muhitda (bo'sh MinIO
    volumi) baketni hech kim yaratmasdi va birinchi fayl yuklash
    "NoSuchBucket" bilan yiqilardi — sababi faqat loglardan topilardi.
    S3 vaqtincha yetib bo'lmasa ham chat/dars ishlayveradi, shuning uchun
    bu yerda xato yutiladi.
    """
    try:
        baket_tayyorla()
    except Exception as e:                                   # noqa: BLE001
        log(f"S3 baketi tayyorlanmadi: {type(e).__name__}: {str(e)[:120]}")


def yukla(yol: str, tarkib: bytes, tur: str = "application/octet-stream"):
    """Baytlarni omborga yozadi. yol: masalan 'manbalar/12/dars1.mp3'."""
    klient().put_object(Bucket=S3_BAKET, Key=yol, Body=tarkib, ContentType=tur)


def yukla_fayl(yol: str, lokal_yol: str, tur: str = "application/octet-stream"):
    klient().upload_file(lokal_yol, S3_BAKET, yol,
                         ExtraArgs={"ContentType": tur})


def yukla_oqim(yol: str, oqim, tur: str = "application/octet-stream"):
    """Fayl obyektini bo'lak-bo'lak yuklaydi — katta fayl xotiraga sig'masligi mumkin."""
    klient().upload_fileobj(oqim, S3_BAKET, yol, ExtraArgs={"ContentType": tur})


def ol_faylga(yol: str, lokal_yol: str):
    """Omborni to'g'ridan-to'g'ri diskka tushiradi (katta audio uchun)."""
    klient().download_file(S3_BAKET, yol, lokal_yol)


def ol(yol: str) -> bytes:
    r = klient().get_object(Bucket=S3_BAKET, Key=yol)
    return r["Body"].read()


def ol_oqim(yol: str):
    """Katta fayllar uchun oqim (web proxy-javoblarda ishlatiladi)."""
    r = klient().get_object(Bucket=S3_BAKET, Key=yol)
    return r["Body"], r.get("ContentType", "application/octet-stream"), r["ContentLength"]


def bormi(yol: str) -> bool:
    try:
        klient().head_object(Bucket=S3_BAKET, Key=yol)
        return True
    except Exception:
        return False


def ochir(yol: str):
    klient().delete_object(Bucket=S3_BAKET, Key=yol)


def royxat(prefiks: str, chegara: int = 1000) -> list[str]:
    """Prefiks bo'yicha obyekt kalitlari (zaxira nusxalari, sahifalar...)."""
    s3 = klient()
    kalitlar: list[str] = []
    davom = None
    while len(kalitlar) < chegara:
        kw = {"Bucket": S3_BAKET, "Prefix": prefiks}
        if davom:
            kw["ContinuationToken"] = davom
        r = s3.list_objects_v2(**kw)
        kalitlar += [o["Key"] for o in r.get("Contents", [])]
        if not r.get("IsTruncated"):
            break
        davom = r.get("NextContinuationToken")
    return kalitlar[:chegara]


def prefiks_ochir(prefiks: str) -> int:
    """Prefiks bo'yicha hamma obyektni o'chiradi (manba fayllari, kesh)."""
    s3 = klient()
    ochirildi = 0
    davom = None
    while True:
        kw = {"Bucket": S3_BAKET, "Prefix": prefiks}
        if davom:
            kw["ContinuationToken"] = davom
        r = s3.list_objects_v2(**kw)
        kalitlar = [{"Key": o["Key"]} for o in r.get("Contents", [])]
        if kalitlar:
            s3.delete_objects(Bucket=S3_BAKET, Delete={"Objects": kalitlar})
            ochirildi += len(kalitlar)
        if not r.get("IsTruncated"):
            break
        davom = r.get("NextContinuationToken")
    return ochirildi


def havola(yol: str, muddat_s: int = 3600) -> str:
    """Vaqtinchalik to'g'ridan-to'g'ri havola — ffmpeg HTTP range bilan o'qiydi
    (katta audioni to'liq yuklab olmaslik uchun)."""
    return klient().generate_presigned_url(
        "get_object", Params={"Bucket": S3_BAKET, "Key": yol}, ExpiresIn=muddat_s)
