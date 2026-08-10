# -*- coding: utf-8 -*-
"""Eski Kengash tizimidan yangi platformaga ko'chirish (bir martalik, idempotent).

  python -m platforma.migratsiya_eski              # hammasi
  python -m platforma.migratsiya_eski --bilim      # faqat bilim (twin/manba/bo'lak)
  python -m platforma.migratsiya_eski --db YO'L    # boshqa kengash.db (cutover uchun)

Nima ko'chadi:
  1. kategoriya + twinlar (Abdulloh, Axrolxo'ja)  — ustoz nomidan
  2. direktorlar — kengash/personas/*.md dan (persona matni + teglar)
  3. bilim — kanonik/*.jsonl + Qdrant'dagi 3072-dim vektorlar (QAYTA EMBEDDING YO'Q)
  4. userlar, suhbatlar, majlislar — kengash.db (SQLite) dan
"""
import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

from . import db, pg
from .sozlama import log

ESKI = Path(r"E:\NewOffice\Labaratoriya\VoIpTelefoniya\kengash")
KANONIK = ESKI / "kanonik"
PERSONAS = ESKI / "personas"
BAZA = ESKI / "baza"
CHIQISH = ESKI / "chiqish"

# eski AGENT_TEGLARI
TEGLAR = {
    "CEO": ["strategiya", "umumiy"], "CTO": ["texnologiya", "umumiy"],
    "CFO": ["moliya", "umumiy"], "COO": ["operatsiya", "hr", "umumiy"],
    "CLO": ["huquq", "umumiy"], "CMO": ["marketing", "sotuv", "umumiy"],
    "RAIS": ["umumiy"],
}
NOMLAR = {"CEO": "Bosh ijrochi direktor", "CTO": "Texnologiya direktori",
          "CFO": "Moliya direktori", "COO": "Operatsiya direktori",
          "CLO": "Huquq direktori", "CMO": "Marketing direktori",
          "RAIS": "Kengash raisi"}
RANGLAR = {"CEO": "#f0b90b", "CTO": "#22d3ee", "CFO": "#34d399",
           "COO": "#fb923c", "CLO": "#fb7185", "CMO": "#a78bfa",
           "RAIS": "#5b8cff"}
SLUG = {"Abdulloh": "abdulloh", "Axrolxo'ja": "axrolxoja"}

VAQT_RE = re.compile(r"\[(\d+):(\d{2}):(\d{2})(?:[–\-](\d+):(\d{2}):(\d{2}))?\]")


def _soniya(s, d, u) -> int:
    return int(s) * 3600 + int(d) * 60 + int(u)


def audio_oraliq(joy: str):
    """'[0:34:12–0:39:45]' -> (2052, 2385); topilmasa (None, None)."""
    m = VAQT_RE.search(joy or "")
    if not m:
        return None, None
    bosh = _soniya(m.group(1), m.group(2), m.group(3))
    oxir = _soniya(m.group(4), m.group(5), m.group(6)) if m.group(4) else None
    return bosh, oxir


# ---------------------------------------------------------------- 1-2. twinlar, direktorlar

def twinlar_yarat() -> dict:
    kid = db.kategoriya_yasa("Biznes va sotuv", "Sotuv, marketing, boshqaruv darslari", 10)
    xarita = {}
    for ustoz, slug in SLUG.items():
        tid = db.twin_yasa(ustoz, slug, kategoriya_id=kid,
                           tavsif=f"{ustoz} ustoz darslari asosidagi digital twin")
        db.ruxsat_yoz(tid, [])      # standart: faqat o'z bilimi
        xarita[ustoz] = tid
        log(f"twin: {ustoz} -> id {tid}")
    return xarita


def twin_xaritasi() -> dict:
    """Ustoz nomi -> twin id, HECH NARSA O'ZGARTIRMASDAN.

    `--tarix` (cutover kuni) uchun: `twinlar_yarat()` ruxsat matritsasini
    standart holatga qaytarib yuboradi, cutover kuni bu yo'qotish bo'lardi.
    """
    xarita = {}
    for ustoz, slug in SLUG.items():
        r = pg.bitta("SELECT id FROM twinlar WHERE slug=%s", slug)
        if r:
            xarita[ustoz] = r[0]
        else:
            log(f"DIQQAT: '{slug}' twini topilmadi")
    return xarita


def direktorlar_yarat():
    if not PERSONAS.is_dir():
        log("personas papkasi topilmadi — direktorlar o'tkazib yuborildi")
        return
    n = 0
    for f in sorted(PERSONAS.glob("*.md")):
        kod = f.stem.upper()
        db.direktor_yasa(kod, NOMLAR.get(kod, kod), f.read_text(encoding="utf-8"),
                         TEGLAR.get(kod, ["umumiy"]), rang=RANGLAR.get(kod, "#5b8cff"),
                         rais=(kod == "RAIS"),
                         tartib=list(NOMLAR).index(kod) if kod in NOMLAR else 100)
        n += 1
    log(f"direktorlar: {n} ta yozildi")


# ---------------------------------------------------------------- 3. bilim

def _qdrant_vektorlar() -> dict:
    """Eski Qdrant'dan {bo'lak_id: vektor} — qayta embedding qilmaslik uchun."""
    from qdrant_client import QdrantClient
    qc = QdrantClient(path=str(BAZA / "qdrant"))
    xarita, keyingi = {}, None
    while True:
        nuqtalar, keyingi = qc.scroll("kengash", limit=500, offset=keyingi,
                                      with_payload=True, with_vectors=True)
        for p in nuqtalar:
            bid = (p.payload or {}).get("id")
            if bid and p.vector is not None:
                xarita[bid] = list(p.vector)
        if keyingi is None:
            break
    qc.close()
    log(f"Qdrant'dan {len(xarita)} vektor o'qildi")
    return xarita


def bilim_kochir(twin_xarita: dict):
    bor = pg.bitta("SELECT count(*) FROM bolaklar")[0]
    if bor:
        log(f"bolaklar jadvalida allaqachon {bor} yozuv bor — bilim o'tkazib yuborildi")
        return
    vektorlar = _qdrant_vektorlar()

    jami_b = 0
    for f in sorted(KANONIK.glob("*.jsonl")):
        qatorlar = [json.loads(q) for q in f.read_text(encoding="utf-8").splitlines() if q.strip()]
        if not qatorlar:
            continue
        b0 = qatorlar[0]
        ustoz = b0.get("ustoz", "Abdulloh")
        twin_id = twin_xarita.get(ustoz)
        if not twin_id:
            log(f"  DIQQAT: {f.name} — noma'lum ustoz {ustoz!r}, o'tkazildi")
            continue
        with pg.ulanish() as u, u.cursor() as k:
            k.execute(
                """INSERT INTO manbalar(twin_id, nom, tur, papka, holat, bolak_soni)
                   VALUES(%s,%s,%s,%s,'tayyor',%s) RETURNING id""",
                (twin_id, b0.get("manba", f.stem), b0.get("tur", "hujjat"),
                 b0.get("dars", ""), len(qatorlar)))
            manba_id = k.fetchone()[0]
            for i, b in enumerate(qatorlar):
                bosh, oxir = audio_oraliq(b.get("joy", ""))
                k.execute(
                    """INSERT INTO bolaklar(manba_id, twin_id, tartib, matn, joy, teglar,
                                            embedding, audio_bosh, audio_oxir, eski_id)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (manba_id, twin_id, i, b["matn"], b.get("joy", ""),
                     b.get("teglar", ["umumiy"]), vektorlar.get(b["id"]),
                     bosh, oxir, b["id"]))
            jami_b += len(qatorlar)
        log(f"  {f.name}: {len(qatorlar)} bo'lak ({ustoz})")
    yoq = pg.bitta("SELECT count(*) FROM bolaklar WHERE embedding IS NULL")[0]
    log(f"bilim ko'chdi: {jami_b} bo'lak, vektorsiz: {yoq}")


# ---------------------------------------------------------------- 4. userlar/suhbatlar

def _xulosa_ajrat(matn: str) -> str:
    m = re.search(r"# YAKUNIY XULOSA \(RAIS\)\n(.*?)"
                  r"(?=\n## MANBALAR \(yagona|\n---\n\n# DIREKTORLAR|\Z)", matn, re.S)
    return m.group(1).strip() if m else matn


def _hisobot_ajrat(matn: str) -> dict:
    manbalar = [{"g": int(g), "manba": ma, "joy": j, "tur": t, "dars": d}
                for g, ma, j, t, d in re.findall(
                    r"^- \*\*\[(\d+)\]\*\* (.+?) — (.+?) \((.+?), papka: (.*?)\)$",
                    matn, re.M)]
    direktorlar = []
    dq = matn.split("# DIREKTORLAR JAVOBLARI")[-1]
    bolak = re.split(r"\n## (CEO|CTO|CFO|COO|CLO|CMO)\n", dq)
    for i in range(1, len(bolak) - 1, 2):
        rol, tana = bolak[i], bolak[i + 1].strip()
        gl = []
        gm = re.search(r"\n?\*\*O'qigan manbalari:\*\* (.+)\s*$", tana)
        if gm:
            gl = [int(x) for x in re.findall(r"\[(\d+)\]", gm.group(1))]
            tana = tana[:gm.start()].rstrip()
        direktorlar.append({"rol": rol, "javob": tana, "global": gl})
    return {"manbalar": manbalar, "direktorlar": direktorlar}


def _eski_tarixni_tozala() -> tuple[int, int]:
    """Eski tizimdan kelgan suhbat/majlisni o'chiradi (qayta ko'chirish uchun).

    Faqat `eski_id IS NOT NULL` qatorlar — yangi platformada tug'ilgan
    suhbatlar tegilmaydi. Majlislar suhbatga CASCADE, lekin suhbatsiz
    (eski_id li) majlis ham bo'lishi mumkin — ikkalasi ham tozalanadi.
    """
    m = pg.hammasi("DELETE FROM majlislar WHERE eski_id IS NOT NULL RETURNING id")
    s = pg.hammasi("DELETE FROM suhbatlar WHERE eski_id IS NOT NULL RETURNING id")
    return len(s), len(m)


def userlar_kochir(db_yol: Path, twin_xarita: dict, chiqish: Path | None = None):
    """Eski SQLite dan userlar/suhbatlar/majlislarni ko'chiradi.

    QAYTA ISHGA TUSHIRISH XAVFSIZ: avval eski_id li tarix o'chiriladi, keyin
    yangisi yoziladi. Cutover kuni eski servisdan yangi `kengash.db` + `chiqish/`
    olinadi va shu funksiya qayta chaqiriladi.
    """
    if not db_yol.exists():
        log(f"SQLite topilmadi: {db_yol} — userlar o'tkazib yuborildi")
        return
    chiqish = chiqish or CHIQISH
    s = sqlite3.connect(str(db_yol))
    s.row_factory = sqlite3.Row

    # userlar (tg_id yoki dev-login bo'yicha idempotent)
    uid_xarita = {}
    for r in s.execute("SELECT * FROM userlar"):
        if r["tg_id"]:
            yangi = db.user_tg({"id": r["tg_id"], "first_name": r["ism"],
                                "last_name": r["familiya"], "username": r["username"],
                                "telefon": r["telefon"], "photo_url": r["foto"]})
        else:   # dev-user (tg_id yo'q) — login sifatida saqlaymiz
            mavjud = pg.bitta_d("SELECT * FROM userlar WHERE login=%s",
                                f"dev_{r['ism'].lower()}")
            if mavjud:
                yangi = mavjud
            else:
                yangi = pg.bitta_d(
                    "INSERT INTO userlar(ism, login, rol) VALUES(%s,%s,'client') RETURNING *",
                    r["ism"], f"dev_{r['ism'].lower()}")
        if r["profil"]:
            db.user_yangila(yangi["id"], profil=r["profil"])
        # ustoz tanlovi -> joriy twin
        tw = twin_xarita.get((r["ustoz"] or "").strip()) if "ustoz" in r.keys() else None
        if tw:
            db.user_yangila(yangi["id"], joriy_twin=tw)
        uid_xarita[r["id"]] = yangi["id"]
    log(f"userlar: {len(uid_xarita)} ta")

    o_s, o_m = _eski_tarixni_tozala()
    if o_s or o_m:
        log(f"oldingi ko'chirish tozalandi: {o_s} suhbat, {o_m} majlis")

    # suhbatlar + majlislar — vaqtlari BILAN (tarix tartibi saqlanadi)
    ustunlar = {c[1] for c in s.execute("PRAGMA table_info(majlislar)")}
    suhbat_bor = bool(s.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='suhbatlar'"
    ).fetchone())
    sid_xarita = {}
    if suhbat_bor:
        for r in s.execute("SELECT * FROM suhbatlar"):
            uid = uid_xarita.get(r["user_id"])
            if not uid:
                continue
            q = pg.bitta(
                """INSERT INTO suhbatlar(user_id, twin_id, sarlavha, eski_id,
                                         yaratilgan, yangilangan)
                   VALUES(%s, NULL, %s, %s, COALESCE(%s::timestamptz, now()),
                          COALESCE(%s::timestamptz, now())) RETURNING id""",
                uid, (r["sarlavha"] or "")[:80], r["id"],
                r["yaratilgan"], r["yangilangan"])
            sid_xarita[r["id"]] = q[0]
    n_m, matnsiz = 0, 0
    for r in s.execute("SELECT * FROM majlislar ORDER BY id"):
        uid = uid_xarita.get(r["user_id"])
        if not uid:
            continue
        sid = sid_xarita.get(r["suhbat_id"]) if "suhbat_id" in ustunlar else None
        if not sid:
            q = pg.bitta(
                """INSERT INTO suhbatlar(user_id, twin_id, sarlavha, eski_id,
                                         yaratilgan, yangilangan)
                   VALUES(%s, NULL, %s, NULL, COALESCE(%s::timestamptz, now()),
                          COALESCE(%s::timestamptz, now())) RETURNING id""",
                uid, (r["savol"] or "")[:80], r["vaqt"], r["vaqt"])
            sid = q[0]
        yol = chiqish / r["fayl"]
        matn = yol.read_text(encoding="utf-8") if yol.exists() else ""
        if not matn:
            matnsiz += 1
        twin_id = None
        bm = re.search(r"\*\*Bilim manbasi:\*\* (\S+)", matn)
        if bm:
            twin_id = twin_xarita.get(bm.group(1))
        pg.bajar(
            """INSERT INTO majlislar(suhbat_id, user_id, twin_id, savol, savol_mustaqil,
                                     xulosa, hisobot, biriktirma, davomiylik,
                                     eski_id, vaqt)
               VALUES(%s,%s,%s,%s,'',%s,%s,%s,%s,%s,
                      COALESCE(%s::timestamptz, now()))""",
            sid, uid, twin_id, r["savol"] or "", _xulosa_ajrat(matn),
            json.dumps(_hisobot_ajrat(matn), ensure_ascii=False),
            (r["biriktirma"] or "") if "biriktirma" in ustunlar else "",
            r["davomiylik"] or 0, r["id"], r["vaqt"])
        n_m += 1
    log(f"suhbatlar: {len(sid_xarita)} ta, majlislar: {n_m} ta"
        + (f" (hisobot matni topilmadi: {matnsiz} ta)" if matnsiz else ""))
    s.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bilim", action="store_true", help="faqat twin/bilim")
    p.add_argument("--tarix", action="store_true",
                   help="faqat user/suhbat/majlis (cutover kuni: yangi kengash.db bilan)")
    p.add_argument("--db", default=str(BAZA / "kengash.db"), help="kengash.db yo'li")
    p.add_argument("--chiqish", default="",
                   help="majlis .md fayllari papkasi (standart: kengash/chiqish)")
    args = p.parse_args()

    pg.migratsiya()
    # --tarix: mavjud twinlarni O'ZGARTIRMASDAN o'qiymiz (ruxsat matritsasi,
    # tavsif, xulq — bularning hammasi adminda sozlangan bo'lishi mumkin)
    xarita = twin_xaritasi() if args.tarix else twinlar_yarat()
    if not args.tarix:
        direktorlar_yarat()
        bilim_kochir(xarita)
    if not args.bilim:
        userlar_kochir(Path(args.db), xarita,
                       Path(args.chiqish) if args.chiqish else None)
    log("MIGRATSIYA TUGADI")


if __name__ == "__main__":
    sys.exit(main())
