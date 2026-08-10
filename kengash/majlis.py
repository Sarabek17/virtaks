# -*- coding: utf-8 -*-
"""Majlis — kengash yig'ilishi: savol -> yo'naltirish -> parallel direktorlar -> sintez.

Foydalanish:
  python -m kengash.majlis "Savolingiz..."
  python -m kengash.majlis "Savol" --hamma        # 6 direktor ham majburiy qatnashadi
"""
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout
from pathlib import Path

from .agentlar import agent_javobi, rais_sintez, rais_yonaltirish
from .sozlama import AGENT_TEGLARI, CHIQISH, log
from .tekshiruv import global_raqamlash

AGENT_MUHLAT = 900   # barcha direktorlar javobi uchun umumiy chegara (soniya)


def majlis(savol: str, hamma: bool = False, foydalanuvchi: str = "",
           suhbat: str = "", ustoz: str = "") -> Path:
    bosh = time.time()
    log(f"=== KENGASH MAJLISI ===")
    log(f"Savol: {savol}")
    log(f"Bilim manbasi: {ustoz + ' ustoz' if ustoz else 'barcha ustozlar'}")

    agentlar = list(AGENT_TEGLARI) if hamma else rais_yonaltirish(savol)

    # user profili + suhbat tarixi — faqat tushunish/uslub uchun, fakt manbasi emas
    qismlar = []
    if foydalanuvchi:
        qismlar.append(f"Savol beruvchi haqida (javob uslubini moslash uchun, "
                       f"FAKT MANBASI EMAS): {foydalanuvchi}")
    if suhbat:
        qismlar.append(f"SUHBAT TARIXI (savol shunga ishora qilishi mumkin; "
                       f"fakt manbasi EMAS):\n{suhbat}")
    kontekst = "\n\n".join(qismlar)

    javoblar = []
    # with-blok ATAYLAB ishlatilmaydi: shutdown(wait=True) osilib qolgan
    # oqimni kutib majlisni ushlab turmasin
    ex = ThreadPoolExecutor(max_workers=len(agentlar))
    fut = {ex.submit(agent_javobi, rol, savol, kontekst, ustoz): rol for rol in agentlar}
    try:
        for f in as_completed(fut, timeout=AGENT_MUHLAT):
            try:
                javoblar.append(f.result())
            except Exception as e:
                log(f"  {fut[f]} XATO: {str(e)[:120]}")
    except FuturesTimeout:
        qoldi = [rol for f, rol in fut.items() if not f.done()]
        log(f"  MUHLAT TUGADI ({AGENT_MUHLAT}s): {', '.join(qoldi)} javobsiz qoldirildi")
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    javoblar.sort(key=lambda j: list(AGENT_TEGLARI).index(j["rol"]))

    # lokal [n] -> yagona global raqamlash (hisobotda bitta [n] = bitta aniq manba)
    reestr = global_raqamlash(javoblar)
    manba_royxati = "\n".join(f"[{m['g']}] {m['manba']} — {m['joy']}" for m in reestr)
    log(f"Manbalar birlashtirildi: {len(reestr)} noyob bo'lak")

    log("RAIS sintez qilmoqda...")
    xulosa = rais_sintez(savol, javoblar, manba_royxati, len(reestr), suhbat=suhbat)

    # hisobot
    CHIQISH.mkdir(parents=True, exist_ok=True)
    raqam = len(list(CHIQISH.glob("majlis_*.md"))) + 1
    yol = CHIQISH / f"majlis_{raqam:03d}.md"
    qismlar = [f"# Kengash majlisi #{raqam}", f"**Savol:** {savol}",
               f"**Bilim manbasi:** {ustoz + ' ustoz' if ustoz else 'Barcha ustozlar'}", "",
               "# YAKUNIY XULOSA (RAIS)", xulosa, "",
               "## MANBALAR (yagona raqamlash — barcha [n] shu ro'yxatga ishora qiladi)"]
    qismlar += [f"- **[{m['g']}]** {m['manba']} — {m['joy']} ({m['tur']}, papka: {m['dars']})"
                for m in reestr]
    qismlar += ["", "---", "", "# DIREKTORLAR JAVOBLARI (to'liq)"]
    for j in javoblar:
        qismlar += [f"\n## {j['rol']}", j["javob"],
                    "\n**O'qigan manbalari:** " +
                    ", ".join(f"[{g}]" for g in j["global"])]
    yol.write_text("\n".join(qismlar), encoding="utf-8")

    # suhbat tarixi — web UI xronologiya shu fayldan o'qiydi
    with open(CHIQISH / "tarix.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "fayl": yol.name, "savol": savol,
            "vaqt": time.strftime("%Y-%m-%d %H:%M:%S"),
            "davomiylik": round(time.time() - bosh),
            "direktorlar": [j["rol"] for j in javoblar],
        }, ensure_ascii=False) + "\n")

    log(f"TAYYOR ({time.time() - bosh:.0f}s): {yol}")
    print("\n" + "=" * 60 + "\n" + xulosa)
    from . import qidiruv
    qidiruv.yopish()
    return yol


def main():
    p = argparse.ArgumentParser(description="AI direktorlar kengashi majlisi")
    p.add_argument("savol")
    p.add_argument("--hamma", action="store_true", help="6 direktor ham qatnashsin")
    p.add_argument("--ustoz", default="", help="faqat shu ustoz bilimidan (standart: barchasi)")
    args = p.parse_args()
    majlis(args.savol, hamma=args.hamma, ustoz=args.ustoz.strip())


if __name__ == "__main__":
    main()
