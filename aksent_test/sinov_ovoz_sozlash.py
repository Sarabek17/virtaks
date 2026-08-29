"""Ovoz sozlash (pitch/rate) tinglash sahifasi — API'siz, diskdagi kasting
yozuvlaridan (gemini_g31_<ovoz>.wav, bir xil matn) quriladi.

    .venv\\Scripts\\python.exe aksent_test\\sinov_ovoz_sozlash.py
    .venv\\Scripts\\python.exe aksent_test\\sinov_ovoz_sozlash.py --ovozlar Leda,Zephyr
    .venv\\Scripts\\python.exe aksent_test\\sinov_ovoz_sozlash.py --pitch +12% --rate +3%   # bitta kombinatsiya

Natija: aksent_test/sozlash_<ovoz>_p<pitch>_r<rate>.wav + ovoz_sozlash.html.
Yoqqan katakdagi qiymatlar .env ga yoziladi: GEMINI_VOICE, GEMINI_PITCH, GEMINI_RATE.
Qayta ishlash core.ovoz_sozlash orqali, serverdagi kabi oqimli (4000 baytli bo'laklar).
"""

import os
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.ovoz_sozlash import OvozSozlagich, foiz_oqi  # noqa: E402

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Ayol ovozlari (Google tavsifi bilan) — "yosh, yengil qiz" nomzodlari birinchi
OVOZLAR = [
    ("Leda", "yoshlik (youthful)"),
    ("Zephyr", "yorqin (bright)"),
    ("Laomedeia", "quvnoq (upbeat)"),
    ("Aoede", "yengil (breezy)"),
    ("Achernar", "yumshoq (soft)"),
    ("Despina", "silliq (smooth)"),
    ("Kore", "qat'iy (firm)"),
    ("Sulafat", "iliq (warm)"),
]

# (pitch, rate) ustunlari — Azure "18-20 yosh qiz" preseti +12%/+3% edi
KOMBINATSIYALAR = [
    ("+0%", "+0%"),
    ("+6%", "+3%"),
    ("+10%", "+3%"),
    ("+14%", "+3%"),
    ("+18%", "+3%"),
    ("+10%", "+8%"),
]

HTML = """<!doctype html>
<html lang="uz">
<head>
<meta charset="utf-8">
<title>Ovoz sozlash — pitch / rate</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 1400px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; background: #fafafa; }}
  h1 {{ font-size: 1.3rem; }}
  table {{ border-collapse: collapse; width: 100%; background: #fff; }}
  th, td {{ text-align: left; padding: .45rem .5rem; border-bottom: 1px solid #e5e5e5; vertical-align: top; white-space: nowrap; }}
  th {{ background: #f0f3f7; font-size: .85rem; }}
  td.ovoz b {{ display: block; }}
  td.ovoz span {{ color: #666; font-size: .8rem; }}
  audio {{ width: 190px; height: 30px; display: block; }}
  .m {{ color: #666; font-size: .85rem; }}
  code {{ background: #eef; padding: 0 .3em; }}
</style>
</head>
<body>
<h1>Ovoz sozlash — Gemini ayol ovozlari × pitch / rate</h1>
<p class="m">Manba: kasting yozuvlari (gemini-3.1-flash-live-preview, bir xil matn). Ustun sarlavhasi —
<code>GEMINI_PITCH</code> / <code>GEMINI_RATE</code> qiymati. Yoqqan katakni toping va <code>.env</code> ga yozing:
<code>GEMINI_VOICE=&lt;ovoz&gt;</code>, <code>GEMINI_PITCH=…</code>, <code>GEMINI_RATE=…</code>. Qayta ishlash serverdagi
bilan bir xil (core/ovoz_sozlash.py, oqimli).</p>
<table>
<thead><tr><th>Ovoz</th>{ustunlar}</tr></thead>
<tbody>
{qatorlar}
</tbody>
</table>
</body>
</html>
"""


def wav_oqi(yol: str) -> tuple[bytes, int]:
    with wave.open(yol, "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2, yol
        return w.readframes(w.getnframes()), w.getframerate()


def wav_yoz(yol: str, pcm: bytes, sr: int) -> None:
    with wave.open(yol, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)


def qayta_ishla(pcm: bytes, pitch: str, rate: str, sr: int) -> bytes:
    s = OvozSozlagich(pitch, rate, sr)
    if not s.faol:
        return pcm
    bolak = 4000
    out = b"".join(s.qayta_ishla(pcm[i:i + bolak]) for i in range(0, len(pcm), bolak))
    return out + s.tugat()


def _arg(nom: str, standart: str | None = None) -> str | None:
    return sys.argv[sys.argv.index(nom) + 1] if nom in sys.argv else standart


def main() -> int:
    ovozlar = OVOZLAR
    if _arg("--ovozlar"):
        tanlov = [o.strip() for o in _arg("--ovozlar").split(",")]
        tavsif = dict(OVOZLAR)
        ovozlar = [(o, tavsif.get(o, "")) for o in tanlov]
    kombolar = KOMBINATSIYALAR
    if _arg("--pitch") or _arg("--rate"):
        kombolar = [(_arg("--pitch", "+0%"), _arg("--rate", "+0%"))]

    qatorlar = []
    for ovoz, tavsif in ovozlar:
        manba = os.path.join(OUT_DIR, f"gemini_g31_{ovoz}.wav")
        if not os.path.exists(manba):
            print(f"  {ovoz}: manba yo'q ({os.path.basename(manba)}), o'tkazildi")
            continue
        pcm, sr = wav_oqi(manba)
        kataklar = []
        for pitch, rate in kombolar:
            fayl = f"sozlash_{ovoz}_p{int(foiz_oqi(pitch)):+d}_r{int(foiz_oqi(rate)):+d}.wav"
            chiqish = qayta_ishla(pcm, pitch, rate, sr)
            wav_yoz(os.path.join(OUT_DIR, fayl), chiqish, sr)
            kataklar.append(f'<td><audio controls preload="none" src="{fayl}"></audio></td>')
        print(f"  {ovoz}: {len(kombolar)} ta variant ({len(pcm) / (2 * sr):.1f} s manba)")
        qatorlar.append(
            f'<tr><td class="ovoz"><b>{ovoz}</b><span>{tavsif}</span></td>{"".join(kataklar)}</tr>'
        )

    ustunlar = "".join(f"<th>pitch {p}<br>rate {r}</th>" for p, r in kombolar)
    yol = os.path.join(OUT_DIR, "ovoz_sozlash.html")
    with open(yol, "w", encoding="utf-8") as f:
        f.write(HTML.format(ustunlar=ustunlar, qatorlar="\n".join(qatorlar)))
    print("sahifa:", yol)
    return 0


if __name__ == "__main__":
    sys.exit(main())
