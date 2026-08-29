"""Ohang (jonlilik) A/B sinovi: bir xil savollarga uch variantda javob.

    .venv\\Scripts\\python.exe aksent_test\\sinov_ohang.py           # Puck, 3 variant x 3 savol
    .venv\\Scripts\\python.exe aksent_test\\sinov_ohang.py Achernar  # boshqa ovoz

Variantlar:
  eski     — avvalgi "xotirjam, undovsiz" xarakter (Azure Madina uchun yozilgan)
  yangi    — jonli ohang bloki (core.config.XARAKTER_SHABLON)
  affektiv — yangi + enable_affective_dialog (model kayfiyatni sezib ohangni moslaydi)

Natija: aksent_test/ohang_<variant>_<n>.wav (+ .txt transkript) + ohang.html.
Bu skript real suhbat kabi ishlaydi: savol matn bilan yuboriladi, javob — ovoz.
Mavjud (.wav + .txt bor) kataklar o'tkaziladi; hammasini qayta yozdirish: --qayta.
"""

import asyncio
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gemini_kasting as gk  # noqa: E402  (client, saqla, .env yuklash shu yerdan)
from google.genai import types  # noqa: E402

from core import config  # noqa: E402

MODEL = gk.MODELLAR["g31"]
ISM = "Sardor"

# Avvalgi xarakter bloki — git tarixidan (a7c53d0) aynan ko'chirilgan
ESKI_XARAKTER = """
Sen telefon orqali gaplashadigan o'zbek tilidagi AI-yordamchisan. Isming
{ism}. Xaraktering Yandex Alisa'ga o'xshaydi: xotirjam, aqlli, samimiy va
ozgina hazilkash.

XARAKTERING:
- Tabiiy, ravon so'zlashuv tilida gapir — aqlli do'stona suhbatdoshdek,
  rasmiyatchiliksiz va sun'iy ko'tarinkiliksiz.
- Xotirjam va o'ziga ishongan ohang. Ortiqcha his-hayajon, shirinsuxanlik,
  "jonim/azizim" kabi murojaatlar — YO'Q.
- O'rni kelganda yengil, nozik hazil qilishing mumkin — kamtarona va aqlli.
- Undov belgisini juda kam ishlat — deyarli har doim oddiy nuqta bilan tugat.
  Ravon, tabiiy jumlalar tuz: intonatsiya o'zi kelib chiqadi.
- Suhbatdoshga "siz" deb murojaat qil.
- She'r aytganda ifodali, satrma-satr, his bilan ayt.
"""

# nom -> (prompt, affektiv, model). enable_affective_dialog 3.1-flash-live'da
# 1011 beradi (2026-08-26 da tekshirildi) — faqat 2.5-native-audio qo'llaydi.
VARIANTLAR = {
    "eski": (ESKI_XARAKTER.format(ism=ISM) + config.QOIDALAR + config.TALAFFUZ, False, MODEL),
    "yangi": (config.prompt_yasa(ISM), False, MODEL),
    "affektiv": (config.prompt_yasa(ISM), True, gk.MODELLAR["g25"]),
}

SAVOLLAR = [
    "Salom! Bugun kayfiyatim yo'q, ishda hammasi chalkashib ketdi.",
    "Menga Samarqand haqida qisqacha, qiziqarli qilib gapirib bering.",
    "Bitta hazil aytib bering, kulgim kelsin.",
]

HTML = """<!doctype html>
<html lang="uz">
<head>
<meta charset="utf-8">
<title>Ohang A/B — {ovoz}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 1000px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; background: #fafafa; }}
  h1 {{ font-size: 1.3rem; }}
  table {{ border-collapse: collapse; width: 100%; background: #fff; }}
  th, td {{ text-align: left; padding: .5rem .6rem; border-bottom: 1px solid #e5e5e5; vertical-align: top; }}
  th {{ background: #f0f3f7; }}
  td.savol {{ width: 28%; font-style: italic; }}
  audio {{ width: 210px; height: 32px; display: block; }}
  .t {{ color: #666; font-size: .8rem; margin-top: .3rem; max-width: 210px; }}
  .m {{ color: #666; font-size: .85rem; }}
</style>
</head>
<body>
<h1>Ohang A/B — {ovoz} ({model})</h1>
<p class="m"><b>eski</b> — avvalgi xotirjam/undovsiz xarakter; <b>yangi</b> — jonli ohang bloki;
<b>affektiv</b> — yangi + enable_affective_dialog ({model25} modelida; 3.1-flash-live bu bayroqni rad etadi — 1011).
Har katakda javob ovozi va uning transkripti.</p>
<table>
<thead><tr><th>Savol</th><th>eski</th><th>yangi</th><th>affektiv</th></tr></thead>
<tbody>
{qatorlar}
</tbody>
</table>
</body>
</html>
"""


async def javob_ol(voice: str, prompt: str, savol: str, affektiv: bool, model: str) -> tuple[bytes, str]:
    cfg = dict(
        response_modalities=["AUDIO"],
        output_audio_transcription=types.AudioTranscriptionConfig(),
        thinking_config=types.ThinkingConfig(thinking_budget=0),
        system_instruction=types.Content(parts=[types.Part(text=prompt)]),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            )
        ),
    )
    if affektiv:
        cfg["enable_affective_dialog"] = True
    audio = bytearray()
    text = ""
    async with gk.client.aio.live.connect(model=model, config=types.LiveConnectConfig(**cfg)) as s:
        await s.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text=savol)]),
            turn_complete=True,
        )

        async def rx():
            nonlocal text
            while True:
                async for msg in s.receive():
                    sc = msg.server_content
                    if sc is None:
                        continue
                    if sc.output_transcription and sc.output_transcription.text:
                        text += sc.output_transcription.text
                    if sc.model_turn:
                        for p in sc.model_turn.parts or []:
                            if p.inline_data and p.inline_data.data:
                                audio.extend(p.inline_data.data)
                    if sc.turn_complete:
                        return

        await asyncio.wait_for(rx(), 60)
    return bytes(audio), text.strip()


async def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ovoz = args[0] if args else "Puck"
    kataklar: dict[tuple[int, str], str] = {}
    qayta = "--qayta" in sys.argv  # mavjud yozuvlarni ham qaytadan yozdirish
    for i, savol in enumerate(SAVOLLAR, 1):
        for nom, (prompt, affektiv, model) in VARIANTLAR.items():
            fayl = f"ohang_{nom}_{i}.wav"
            wav_yol = os.path.join(gk.OUT_DIR, fayl)
            txt_yol = wav_yol[:-4] + ".txt"
            if not qayta and os.path.exists(wav_yol) and os.path.exists(txt_yol):
                with open(txt_yol, encoding="utf-8") as tf:
                    text = tf.read().strip()
                print(f"  {i}/{nom}: mavjud, o'tkazildi")
                kataklar[(i, nom)] = (
                    f'<audio controls preload="none" src="{fayl}"></audio>'
                    f'<div class="t">{text}</div>'
                )
                continue
            t0 = time.time()
            pcm, text = b"", ""
            try:
                for urinish in range(3):  # bo'sh audio — o'tkinchi holat, qayta urinamiz
                    pcm, text = await javob_ol(ovoz, prompt, savol, affektiv, model)
                    if pcm:
                        break
                    print(f"  {i}/{nom}: audio kelmadi ({urinish + 1}-urinish)")
            except Exception as e:
                xato = f"XATO {type(e).__name__}: {str(e)[:100]}"
                print(f"  {i}/{nom}: {xato}")
                kataklar[(i, nom)] = f'<span class="t">{xato}</span>'
                continue
            if not pcm:
                kataklar[(i, nom)] = '<span class="t">audio kelmadi</span>'
                continue
            gk.saqla(fayl, pcm)
            text = " ".join(text.split())
            with open(txt_yol, "w", encoding="utf-8") as tf:
                tf.write(text)
            print(f"  [{time.time() - t0:3.0f}s] {fayl} | {len(pcm) / 48000:.1f} s | {text[:90]}")
            kataklar[(i, nom)] = (
                f'<audio controls preload="none" src="{fayl}"></audio>'
                f'<div class="t">{text}</div>'
            )

    qatorlar = []
    for i, savol in enumerate(SAVOLLAR, 1):
        hujayralar = "".join(f"<td>{kataklar.get((i, nom), '')}</td>" for nom in VARIANTLAR)
        qatorlar.append(f'<tr><td class="savol">{i}. {savol}</td>{hujayralar}</tr>')
    yol = os.path.join(gk.OUT_DIR, "ohang.html")
    with open(yol, "w", encoding="utf-8") as f:
        f.write(HTML.format(ovoz=ovoz, model=MODEL, model25=gk.MODELLAR["g25"], qatorlar="\n".join(qatorlar)))
    print("sahifa:", yol)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
