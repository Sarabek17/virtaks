# -*- coding: utf-8 -*-
"""Hybrid qidiruv: pgvector (semantik) + BM25 (kalit so'z) -> RRF birlashtirish.

Twin chegarasi QAT'IY: qidiruv faqat ruxsat etilgan twinlar bilimidan chiqadi
(twin_ruxsat matritsasi). Teg filtri kam natija bersa yumshaydi, twin filtri —
hech qachon.
"""
import re
import threading
import time

from . import db, llm, pg
from .sozlama import log

_kesh = {}
_qulf = threading.Lock()


def tokenla(matn: str) -> list[str]:
    matn = matn.lower().replace("’", "'").replace("‘", "'").replace("`", "'")
    return re.findall(r"[a-zа-яё']+|\d+", matn)


VERSIYA_KESH_S = 10        # imzoni qayta so'ramaslik oynasi


def _bm25_versiya() -> tuple:
    """Bo'laklar o'zgarganini arzon aniqlash uchun imzo.

    Imzo har qidiruvda so'ralsa bu qo'shimcha DB borish-kelishi bo'ladi —
    chatda u birinchi token kechikishiga to'g'ridan-to'g'ri qo'shiladi.
    Bilim bazasi ingest paytida o'zgaradi, ya'ni 10 soniya "eski" imzo
    xavfsiz: eng yomoni yangi bo'lak indeksga 10 soniya kech tushadi.
    """
    hozir = time.time()
    if hozir - _kesh.get("v_vaqt", 0) < VERSIYA_KESH_S and "v" in _kesh:
        return _kesh["v"]
    r = pg.bitta("SELECT count(*), COALESCE(max(id), 0) FROM bolaklar")
    _kesh["v"] = (r[0], r[1])
    _kesh["v_vaqt"] = hozir
    return _kesh["v"]


def _bm25():
    """BM25 indeksi (xotirada, bo'laklar o'zgarsa qayta quriladi)."""
    v = _bm25_versiya()
    with _qulf:
        if _kesh.get("bm25_v") != v:
            from rank_bm25 import BM25Okapi
            log(f"BM25 indeksi quriladi ({v[0]} bo'lak)...")
            qatorlar = pg.hammasi_d(
                """SELECT id, twin_id, matn, joy, teglar, manba_id,
                          audio_bosh, audio_oxir, sahifa_png
                   FROM bolaklar ORDER BY id""")
            _kesh["bm25"] = BM25Okapi([tokenla(q["matn"]) for q in qatorlar])
            _kesh["bolaklar"] = qatorlar
            _kesh["bm25_v"] = v
            log("BM25 tayyor")
        return _kesh["bm25"], _kesh["bolaklar"]


def _boyit(qatorlar: list[dict]) -> list[dict]:
    """Bo'laklarga manba ma'lumotini qo'shadi (nom, tur, papka)."""
    if not qatorlar:
        return []
    idlar = list({q["manba_id"] for q in qatorlar})
    manbalar = {m["id"]: m for m in pg.hammasi_d(
        "SELECT id, nom, tur, papka FROM manbalar WHERE id = ANY(%s)", idlar)}
    for q in qatorlar:
        m = manbalar.get(q["manba_id"], {})
        q["manba"] = m.get("nom", "")
        q["tur"] = m.get("tur", "")
        q["papka"] = m.get("papka", "")
    return qatorlar


def qidir(savol: str, twin_id: int, teglar: list[str] | None = None,
          top: int = 10) -> list[dict]:
    """Hybrid qidiruv. Natija: bo'lak dictlari (id, matn, joy, manba, tur...)."""
    ruxsat = db.ruxsat_royxat(twin_id)

    # --- vektor qidiruv (pgvector, halfvec HNSW) ---
    vek = llm.embed([savol], turi="RETRIEVAL_QUERY")[0]
    shart = ["b.twin_id = ANY(%s)"]
    args = [ruxsat]
    if teglar:
        shart.append("b.teglar && %s")
        args.append(teglar)
    args.append(str(vek))
    args.append(top * 2)
    vek_qatorlar = pg.hammasi_d(
        f"""SELECT b.id, b.twin_id, b.matn, b.joy, b.teglar, b.manba_id,
                   b.audio_bosh, b.audio_oxir, b.sahifa_png
            FROM bolaklar b
            WHERE {' AND '.join(shart)} AND b.embedding IS NOT NULL
            ORDER BY b.embedding::halfvec(3072) <=> %s::halfvec(3072)
            LIMIT %s""", *args)

    # --- BM25 ---
    bm, hammasi = _bm25()
    ballar = bm.get_scores(tokenla(savol))
    juft = sorted(enumerate(ballar), key=lambda x: -x[1])[:top * 5]
    bm_qatorlar = []
    for idx, ball in juft:
        if ball <= 0:
            continue
        b = hammasi[idx]
        if b["twin_id"] not in ruxsat:
            continue
        if teglar and not (set(b["teglar"]) & set(teglar)):
            continue
        bm_qatorlar.append(b)
        if len(bm_qatorlar) >= top * 2:
            break

    # --- RRF ---
    ball_jadval, hujjat = {}, {}
    for royxat in (vek_qatorlar, bm_qatorlar):
        for rank, b in enumerate(royxat):
            ball_jadval[b["id"]] = ball_jadval.get(b["id"], 0.0) + 1.0 / (60 + rank)
            hujjat[b["id"]] = b
    natija = [hujjat[i] for i, _ in
              sorted(ball_jadval.items(), key=lambda x: -x[1])][:top]

    # teg filtri juda tor bo'lsa — tegsiz qayta (twin chegarasi SAQLANADI)
    if teglar and len(natija) < 4:
        log(f"  ({','.join(teglar)} bo'yicha kam natija — teg filtrisiz)")
        return qidir(savol, twin_id, teglar=None, top=top)
    return _boyit(natija)
