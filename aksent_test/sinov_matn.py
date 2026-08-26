"""Tanlangan ovozlar (Achernar, Puck) uchun uzun, qiyin matn sinovi.

    .venv\\Scripts\\python.exe aksent_test\\sinov_matn.py            # Achernar + Puck
    .venv\\Scripts\\python.exe aksent_test\\sinov_matn.py Achernar   # faqat bittasi

Natija: aksent_test/sinov_<ovoz>.wav + sinov_matn.html (tinglash sahifasi).
Matn qasddan qiyin: q, g', o', x/h, ng, tutuq (ʼ), uzun so'zlar va
orfoepiya holatlari (uchta, ishdan, avtobus, mashhur, to'rtta...).
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gemini_kasting as gk  # noqa: E402  (client, oqit, saqla shu yerdan)

MODEL = gk.MODELLAR["g31"]
OVOZLAR = ["Achernar", "Puck"]

MATN = (
    "Assalomu alaykum, aziz tinglovchi! Men Madinaman, bugun sizga qiyinroq "
    "matn o'qib beraman. Qorong'i tushganda qishloqqa qaytdik: bog'bon tog' "
    "etagida g'isht terar, o'g'illari esa qo'shni ariqdan suv olib kelishardi. "
    "Ma'lumki, ta'lim va san'at — xalqning haqiqiy boyligi; mas'uliyatni his "
    "qilgan o'qituvchi ming mashaqqatga ham chidaydi. Ishdan keyin do'stlar "
    "bilan avtobusda G'ijduvonga bordik, mashhur somsapazdan uchta emas, "
    "nechtadir somsa oldik — hammasi sakkizta bo'ldi. Singlim kulib: "
    "«Sog'inch — mo''jizadek tuyg'u», dedi. Mustaqilligimizni qadrlab, "
    "yangi maqsadlar sari birgalikda intilaylik!"
)

HTML = """<!doctype html>
<html lang="uz">
<head>
<meta charset="utf-8">
<title>Achernar/Puck — qiyin matn sinovi</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 860px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; background: #fafafa; }}
  h1 {{ font-size: 1.3rem; }}
  p.matn {{ background: #fff; border-left: 4px solid #3b6ea5; padding: .7rem 1rem; line-height: 1.6; }}
  table {{ border-collapse: collapse; width: 100%; background: #fff; }}
  th, td {{ text-align: left; padding: .5rem .7rem; border-bottom: 1px solid #e5e5e5; }}
  th {{ background: #f0f3f7; }}
  audio {{ width: 320px; height: 34px; }}
  .m {{ color: #666; font-size: .85rem; }}
</style>
</head>
<body>
<h1>Tanlangan ovozlar — uzun, qiyin matn (model: {model})</h1>
<p class="matn">{matn}</p>
<p class="m">Qiyin joylar: <b>q</b> (qishloqqa, mashaqqat, haqiqiy), <b>g'</b> (qorong'i, bog'bon,
G'ijduvon, sog'inch, tuyg'u), <b>o'</b> (o'g'illari, o'qituvchi), <b>x/h</b> (xalq, his, ham),
<b>ng</b> (ming, singlim, yangi), <b>tutuq</b> (ma'lumki, ta'lim, san'at, mas'uliyat, mo''jiza),
uzun so'z (mustaqilligimizni, birgalikda), orfoepiya (ishdan, do'stlar, avtobusda, mashhur, uchta,
nechtadir, sakkizta).</p>
<table>
<thead><tr><th>Ovoz</th><th>Tinglash</th><th>Davomiyligi</th></tr></thead>
<tbody>
{qatorlar}
</tbody>
</table>
</body>
</html>
"""


async def main() -> int:
    ovozlar = [a for a in sys.argv[1:] if not a.startswith("--")] or OVOZLAR
    gk.TOPSHIRIQ = (
        "Quyidagi matnni AYNAN, so'zma-so'z, hech narsa qo'shmasdan va "
        "o'zgartirmasdan o'qib ber:\n«" + MATN + "»"
    )
    for ovoz in ovozlar:
        t0 = time.time()
        try:
            pcm, text = await gk.oqit(MODEL, ovoz, gk.SYSTEM_PROMPT)
        except Exception as e:
            print(f"  {ovoz}: XATO {type(e).__name__}: {str(e)[:120]}")
            continue
        if not pcm:
            print(f"  {ovoz}: audio kelmadi | {text[:80]}")
            continue
        gk.saqla(f"sinov_{ovoz}.wav", pcm)
        print(f"  [{time.time() - t0:4.0f}s] sinov_{ovoz}.wav | {len(pcm) / 48000:.1f} s | {text[:100]}")

    # Sahifaga hozir yozilganlar EMAS, diskda bor hamma sinov_*.wav kiradi —
    # bitta ovoz qayta yozilganda qolganlari tushib qolmaydi.
    qatorlar = []
    for ovoz in OVOZLAR + [o for o in ovozlar if o not in OVOZLAR]:
        yol = os.path.join(gk.OUT_DIR, f"sinov_{ovoz}.wav")
        if not os.path.exists(yol):
            continue
        davomiylik = (os.path.getsize(yol) - 44) / 48000
        qatorlar.append(
            f'<tr><td><b>{ovoz}</b></td>'
            f'<td><audio controls preload="none" src="sinov_{ovoz}.wav"></audio></td>'
            f"<td>{davomiylik:.1f} s</td></tr>"
        )
    yol = os.path.join(gk.OUT_DIR, "sinov_matn.html")
    with open(yol, "w", encoding="utf-8") as f:
        f.write(HTML.format(model=MODEL, matn=MATN, qatorlar="\n".join(qatorlar)))
    print("sahifa:", yol)
    return 0 if qatorlar else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
