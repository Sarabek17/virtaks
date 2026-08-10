# -*- coding: utf-8 -*-
"""Hybrid qidiruv: vektor (Qdrant) + BM25 -> RRF birlashtirish + rol filtri."""
import pickle
import threading

from .indeks import KOLLEKSIYA, embed, tokenla
from .sozlama import BAZA, USTOZ_STANDART, klient, log

_kesh = {}
_qulf = threading.Lock()   # parallel agentlar bir vaqtda ochganda poyga bo'lmasin


def _bm25():
    with _qulf:
        if "bm25" not in _kesh:
            with open(BAZA / "bm25.pkl", "rb") as f:
                _kesh["bm25"] = pickle.load(f)
    return _kesh["bm25"]


def _qdrant():
    with _qulf:
        if "qc" not in _kesh:
            from qdrant_client import QdrantClient
            try:
                _kesh["qc"] = QdrantClient(path=str(BAZA / "qdrant"))
            except Exception as e:
                if "already accessed" in str(e):
                    raise RuntimeError(
                        "Qdrant indeksi band: boshqa kengash jarayoni (server yoki "
                        "CLI majlis) ishlab turibdi — avval uni to'xtating") from e
                raise
    return _kesh["qc"]


def _klient():
    with _qulf:
        if "cl" not in _kesh:
            _kesh["cl"] = klient()
    return _kesh["cl"]


def yopish():
    """Qdrant klientini toza yopish (jarayon oxirida chaqiriladi)."""
    qc = _kesh.pop("qc", None)
    if qc is not None:
        qc.close()


def qidir(savol: str, teglar: list[str] | None = None, top: int = 10,
          ustoz: str = "") -> list[dict]:
    """Hybrid qidiruv. teglar — soha filtri (kam natija bo'lsa olib tashlanadi).
    ustoz — QAT'IY filtr: tanlangan ustoz bilimidan tashqariga hech qachon chiqilmaydi.

    Natija: bo'lak dictlari (id, manba, tur, joy, matn, teglar, ustoz) ball tartibida.
    """
    # --- vektor qidiruv ---
    vek = embed(_klient(), [savol], turi="RETRIEVAL_QUERY")[0]
    flt = None
    if teglar or ustoz:
        from qdrant_client.models import (FieldCondition, Filter, MatchAny,
                                          MatchValue)
        shartlar = []
        if teglar:
            shartlar.append(FieldCondition(key="teglar", match=MatchAny(any=teglar)))
        if ustoz:
            shartlar.append(FieldCondition(key="ustoz", match=MatchValue(value=ustoz)))
        flt = Filter(must=shartlar)
    vk = _qdrant().query_points(KOLLEKSIYA, query=vek, limit=top * 2, query_filter=flt).points
    vek_royxat = [(p.payload["id"], p.payload) for p in vk]

    # --- BM25 qidiruv ---
    d = _bm25()
    ballar = d["bm25"].get_scores(tokenla(savol))
    juft = sorted(enumerate(ballar), key=lambda x: -x[1])[:top * 3]
    bm_royxat = []
    for idx, ball in juft:
        if ball <= 0:
            continue
        b = d["bolaklar"][idx]
        if ustoz and b.get("ustoz", USTOZ_STANDART) != ustoz:
            continue
        if teglar and not (set(b["teglar"]) & set(teglar)):
            continue
        bm_royxat.append((b["id"], b))

    # --- RRF birlashtirish ---
    ball_jadval: dict[str, float] = {}
    hujjat: dict[str, dict] = {}
    for royxat in (vek_royxat, bm_royxat):
        for rank, (bid, b) in enumerate(royxat):
            ball_jadval[bid] = ball_jadval.get(bid, 0.0) + 1.0 / (60 + rank)
            hujjat[bid] = b
    natija = [hujjat[bid] for bid, _ in
              sorted(ball_jadval.items(), key=lambda x: -x[1])][:top]

    # teg filtri juda tor bo'lsa — tegsiz qayta; ustoz filtri esa SAQLANADI
    # (user tanlagan ustoz chegarasi hech qanday holatda buzilmaydi)
    if teglar and len(natija) < 4:
        log(f"  ({','.join(teglar)} bo'yicha kam natija — teg filtrisiz qidiramiz)")
        return qidir(savol, teglar=None, top=top, ustoz=ustoz)
    return natija
