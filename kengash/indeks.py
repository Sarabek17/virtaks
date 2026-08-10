# -*- coding: utf-8 -*-
"""Indeks — kanonik bo'laklarni embedding qilib Qdrant (lokal) + BM25 ga yozadi.

Foydalanish:
  python -m kengash.indeks            # kanonik/*.jsonl hammasini qayta indekslaydi
"""
import json
import pickle
import re

from google.genai import types

from .sozlama import (BAZA, EMBED_MODEL, EMBED_OLCHAM, KANONIK, USTOZ_STANDART,
                      klient, log, qayta_urinib)

KOLLEKSIYA = "kengash"
GURUH = 20   # bitta embed so'rovida nechta bo'lak


def tokenla(matn: str) -> list[str]:
    """BM25 uchun sodda tokenizatsiya: kichik harf + lotin/kirill so'zlar.
    O'zbek apostroflarini (o', g') birlashtiradi."""
    matn = matn.lower().replace("’", "'").replace("‘", "'").replace("`", "'")
    return re.findall(r"[a-zа-яё']+|\d+", matn)


def bolaklarni_oqi() -> list[dict]:
    bolaklar = []
    for f in sorted(KANONIK.glob("*.jsonl")):
        with open(f, encoding="utf-8") as fp:
            for qator in fp:
                b = json.loads(qator)
                b.setdefault("ustoz", USTOZ_STANDART)   # eski bo'laklar
                bolaklar.append(b)
    return bolaklar


def embed(cl, matnlar: list[str], turi: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    def sorov():
        r = cl.models.embed_content(
            model=EMBED_MODEL, contents=matnlar,
            config=types.EmbedContentConfig(task_type=turi, output_dimensionality=EMBED_OLCHAM))
        return [e.values for e in r.embeddings]
    return qayta_urinib(sorov, f"embedding x{len(matnlar)}")


def main():
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    bolaklar = bolaklarni_oqi()
    if not bolaklar:
        raise SystemExit("kanonik/ bo'sh — avval ingest qiling")
    log(f"{len(bolaklar)} bo'lak indekslanadi ({EMBED_MODEL}, {EMBED_OLCHAM}-o'lcham)")

    cl = klient()
    vektorlar: list[list[float]] = []
    for i in range(0, len(bolaklar), GURUH):
        guruh = [b["matn"][:6000] for b in bolaklar[i:i + GURUH]]
        vektorlar.extend(embed(cl, guruh))
        log(f"  embedding: {min(i + GURUH, len(bolaklar))}/{len(bolaklar)}")

    BAZA.mkdir(parents=True, exist_ok=True)

    # --- Qdrant (lokal, serversiz) ---
    qc = QdrantClient(path=str(BAZA / "qdrant"))
    if qc.collection_exists(KOLLEKSIYA):
        qc.delete_collection(KOLLEKSIYA)
    qc.create_collection(KOLLEKSIYA,
                         vectors_config=VectorParams(size=EMBED_OLCHAM, distance=Distance.COSINE))
    nuqtalar = [PointStruct(id=i, vector=v, payload=b)
                for i, (b, v) in enumerate(zip(bolaklar, vektorlar))]
    for i in range(0, len(nuqtalar), 100):
        qc.upsert(KOLLEKSIYA, nuqtalar[i:i + 100])
    qc.close()
    log(f"Qdrant: {len(nuqtalar)} nuqta yozildi")

    # --- BM25 ---
    from rank_bm25 import BM25Okapi
    tokenlar = [tokenla(b["matn"]) for b in bolaklar]
    bm25 = BM25Okapi(tokenlar)
    with open(BAZA / "bm25.pkl", "wb") as f:
        pickle.dump({"bm25": bm25, "bolaklar": bolaklar}, f)
    log("BM25 indeksi yozildi")
    log(f"TAYYOR: indeks {len(bolaklar)} bo'lak bilan yangilandi")


if __name__ == "__main__":
    main()
