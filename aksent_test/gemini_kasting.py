"""Gemini Live ovoz kastingi: har ovoz bir xil o'zbekcha matnni o'qiydi.

    .venv\\Scripts\\python.exe aksent_test\\gemini_kasting.py                # 10 ovoz x 2 model
    .venv\\Scripts\\python.exe aksent_test\\gemini_kasting.py Kore Aoede     # faqat shu ovozlar
    .venv\\Scripts\\python.exe aksent_test\\gemini_kasting.py --model gemini-3.1-flash-live-preview

Natija: aksent_test/gemini_<model>_<ovoz>.wav (24 kHz PCM16 mono) va
aksent_test/gemini_kasting_natija.txt. Tizim prompti — core.config.SYSTEM_PROMPT
(talaffuz bo'limi bilan); "asos" fayli promptsiz, standart ovoz — hozirgi
holat bilan solishtirish uchun.
"""

import asyncio
import os
import sys
import time
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"), override=True)

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

from core.config import SYSTEM_PROMPT  # noqa: E402

MODELLAR = {
    "g31": "gemini-3.1-flash-live-preview",
    "g25": "gemini-2.5-flash-native-audio-preview-12-2025",
}
# Ayol ovozlari (Madina personasi) + solishtirish uchun ikki erkak ovoz
OVOZLAR = ["Kore", "Aoede", "Leda", "Zephyr", "Despina", "Sulafat", "Laomedeia",
           "Achernar", "Puck", "Charon"]

# Qiyin tovushlar: q, g', o', x, h, ng, tutuq; orfoepiya holatlari: kitob, to'rtta, do'stlar
MATN = ("Assalomu alaykum! Men Madinaman, sizning yordamchingizman. Bugun Toshkentda "
        "havo ochiq. Qishloqqa borib, do'stlar bilan to'rtta kitob o'qidik, keyin "
        "G'ijduvon somsasini yedik. Sog'liq — eng katta boylik, shunday emasmi?")
TOPSHIRIQ = ("Quyidagi matnni AYNAN, so'zma-so'z, hech narsa qo'shmasdan va "
             "o'zgartirmasdan o'qib ber:\n«" + MATN + "»")

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


async def oqit(model: str, voice: str | None, prompt: str | None) -> tuple[bytes, str]:
    cfg = dict(
        response_modalities=["AUDIO"],
        output_audio_transcription=types.AudioTranscriptionConfig(),
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    if prompt:
        cfg["system_instruction"] = types.Content(parts=[types.Part(text=prompt)])
    if voice:
        cfg["speech_config"] = types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            )
        )
    audio = bytearray()
    text = ""
    async with client.aio.live.connect(model=model, config=types.LiveConnectConfig(**cfg)) as s:
        await s.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text=TOPSHIRIQ)]),
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


def saqla(nom: str, pcm: bytes) -> str:
    yol = os.path.join(OUT_DIR, nom)
    with wave.open(yol, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)
    return yol


async def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ovozlar = args or OVOZLAR
    modellar = dict(MODELLAR)
    if "--model" in sys.argv:
        m = sys.argv[sys.argv.index("--model") + 1]
        modellar = {k: v for k, v in MODELLAR.items() if v == m} or {"x": m}

    ishlar = [("asos", MODELLAR["g31"], None, None)]   # hozirgi holat: promptsiz, standart ovoz
    for qisqa, model in modellar.items():
        for v in ovozlar:
            ishlar.append((f"{qisqa}_{v}", model, v, SYSTEM_PROMPT))

    natija_yol = os.path.join(OUT_DIR, "gemini_kasting_natija.txt")
    qatorlar = [f"# Gemini ovoz kastingi — matn: {MATN}\n# fayl | model | ovoz | davomiyligi | transkript\n"]
    print(f"{len(ishlar)} ta yozuv, ketma-ket (har biri ~15-30 s)...")
    for nom, model, voice, prompt in ishlar:
        t0 = time.time()
        try:
            pcm, text = await oqit(model, voice, prompt)
        except Exception as e:
            qator = f"gemini_{nom}.wav | {model} | {voice or 'standart'} | XATO {type(e).__name__}: {str(e)[:100]}"
            print("  " + qator)
            qatorlar.append(qator + "\n")
            continue
        if not pcm:
            qator = f"gemini_{nom}.wav | {model} | {voice or 'standart'} | audio kelmadi | {text[:80]}"
        else:
            saqla(f"gemini_{nom}.wav", pcm)
            qator = (f"gemini_{nom}.wav | {model} | {voice or 'standart'} | "
                     f"{len(pcm) / 48000:.1f} s | {text[:120]}")
        print(f"  [{time.time() - t0:4.0f}s] {qator}")
        qatorlar.append(qator + "\n")
    with open(natija_yol, "w", encoding="utf-8") as f:
        f.writelines(qatorlar)
    print("natija:", natija_yol)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
