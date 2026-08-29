"""«Madina» ovozi — Gemini Live'ning eng kichik MUSTAQIL namunasi.

Boshqa loyihaga ko'chirish uchun yozilgan (qarang: OVOZ_KOCHIRISH.md). Faqat
ikki narsa kerak: shu fayl yonida `core/config.py` (prompt bloklari + Settings)
va `.env` (GEMINI_API_KEY, TTS_PROVIDER=gemini, GEMINI_LIVE_MODEL,
GEMINI_VOICE=Zephyr, ASSISTANT_NAME=Madina).

    pip install google-genai python-dotenv
    python ovoz_namuna.py "Salom! O'zingni qisqacha tanishtir."
    -> namuna.wav (24 kHz, 16-bit, mono) + transkript ekranda

Bu yerda ovozning "retsepti" to'liq: model + ovoz nomi + prompt + to'rtta
sozlama. Real vaqt suhbat (mikrofon, barge-in, uzilishga chidamlilik) uchun
core/pipeline.py ishlatiladi — u ham aynan shu konfiguratsiyani quradi.
"""

import asyncio
import sys
import wave

from google import genai
from google.genai import types

from core.config import Settings

SAMPLE_RATE = 24000  # Gemini Live chiqishi: 24 kHz PCM16 mono


def live_config(s: Settings) -> types.LiveConnectConfig:
    """Ovoz retsepti. Boshqa loyihada AYNAN shu konfiguratsiya qurilsin."""
    return types.LiveConnectConfig(
        # 1) Native-audio modellar TEXT modallikni rad etadi (1011) —
        #    AUDIO + transkript ishlatiladi.
        response_modalities=["AUDIO"],
        output_audio_transcription=types.AudioTranscriptionConfig(),
        # 2) Fikrlash o'chiq: yoqilsa kechikish 3 barobar va "fikr" matni oqadi.
        thinking_config=types.ThinkingConfig(thinking_budget=0),
        # 3) Prompt — core/config.py dagi XARAKTER + QOIDALAR + TALAFFUZ bloklari
        #    (ism ASSISTANT_NAME dan). Bloklar o'zgartirilmaydi.
        system_instruction=types.Content(parts=[types.Part(text=s.system_prompt)]),
        # 4) Ovoz — GEMINI_VOICE (tanlov: Zephyr).
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=s.gemini_voice)
            )
        ),
        # enable_affective_dialog YO'Q — gemini-3.1-flash-live-preview uni rad etadi.
    )


async def gapir(savol: str, chiqish: str = "namuna.wav") -> None:
    s = Settings.load()
    if s.tts_provider != "gemini" or not s.gemini_voice:
        sys.exit("XATO: .env da TTS_PROVIDER=gemini va GEMINI_VOICE=Zephyr bo'lishi kerak")
    client = genai.Client(api_key=s.gemini_api_key)
    audio, matn = bytearray(), ""

    async with client.aio.live.connect(model=s.gemini_model, config=live_config(s)) as sess:
        # Savol matn bilan (real suhbatda: send_realtime_input(audio=...) 16 kHz PCM)
        await sess.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text=savol)]),
            turn_complete=True,
        )
        # MUHIM: sess.receive() BITTA navbat uchun iterator — uzoq sessiyada
        # uni `while True:` ichida qayta-qayta ochish shart (aks holda sessiya
        # birinchi javobdan keyin "kar" bo'lib qoladi). Bu yerda bitta javob yetarli.
        async for msg in sess.receive():
            sc = msg.server_content
            if sc is None:
                continue
            if sc.output_transcription and sc.output_transcription.text:
                matn += sc.output_transcription.text
            if sc.model_turn:
                for part in sc.model_turn.parts or []:
                    if part.inline_data and part.inline_data.data:
                        audio.extend(part.inline_data.data)   # 24 kHz PCM16 — to'g'ridan-to'g'ri karnayga
            if sc.turn_complete:
                break

    pcm = bytes(audio)
    # Ixtiyoriy: GEMINI_PITCH / GEMINI_RATE 0 bo'lmasa — DSP (core/ovoz_sozlash.py)
    from core.ovoz_sozlash import OvozSozlagich

    sozlagich = OvozSozlagich(s.gemini_pitch, s.gemini_rate, SAMPLE_RATE)
    if sozlagich.faol:
        pcm = sozlagich.qayta_ishla(pcm) + sozlagich.tugat()

    with wave.open(chiqish, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    print(f"{s.voice_label} | {chiqish}: {len(pcm) / (2 * SAMPLE_RATE):.1f} s")
    print("Transkript:", " ".join(matn.split()))


if __name__ == "__main__":
    savol = " ".join(sys.argv[1:]) or "Salom! O'zingni qisqacha tanishtir."
    asyncio.run(gapir(savol))
