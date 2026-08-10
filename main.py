#!/usr/bin/env python3
"""O'zbek tilidagi ovozli AI-assistent — KONSOL (mikrofon) rejimi.

Arxitektura va barcha mantiq core/ paketida; bu fayl faqat:
  - mikrofonni ochadi (pyaudio, o'z-o'zini tiklaydigan oqim)
  - hodisalarni konsolga chiroyli chiqaradi (test-log)

Web rejim uchun: server.py (FastAPI + WebSocket, brauzerdan mikrofon).

!!! TELEFONIYAGA O'TISH NUQTASI !!!
mic_source() o'rniga Asterisk AudioSocket'dan 16 kHz PCM bo'laklar yield
qiladigan generator qo'yilsa — qolgan tizim o'zgarishsiz ishlaydi.
"""

import argparse
import asyncio
import sys

import pyaudio

from core import AssistantPipeline, Settings
from core.audio import CHUNK_FRAMES, SEND_SAMPLE_RATE
from core.pipeline import PipelineError

# Windows konsolida UTF-8 (o'zbekcha harflar uchun)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ---------------------------------------------------------------------------
# Mikrofon manbasi (o'z-o'zini tiklaydigan)
# ---------------------------------------------------------------------------

def _open_mic_stream(pa: pyaudio.PyAudio):
    return pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SEND_SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_FRAMES,
    )


async def mic_source():
    """Mikrofondan 100 ms li 16 kHz PCM bo'laklar oqimi.

    Windows'da audio qurilma ba'zan "reset" bo'ladi (Bluetooth profil
    almashishi, standart qurilma o'zgarishi) — oqim avtomatik qayta ochiladi.
    """
    pa = pyaudio.PyAudio()
    stream = _open_mic_stream(pa)
    errors_in_row = 0
    try:
        while True:
            try:
                data = await asyncio.to_thread(
                    stream.read, CHUNK_FRAMES, exception_on_overflow=False
                )
                errors_in_row = 0
                yield data
            except OSError as e:
                errors_in_row += 1
                if errors_in_row > 5:
                    raise RuntimeError(
                        f"Mikrofon oqimi tiklanmadi ({e}). Sozlamalar -> Tizim -> "
                        f"Ovoz bo'limida mikrofonni tekshiring."
                    ) from e
                print(f"  [MIC OGOHLANTIRISH] oqim uzildi ({e}) — qayta ochilmoqda...")
                try:
                    stream.close()
                except Exception:
                    pass
                await asyncio.sleep(0.5)
                try:
                    stream = _open_mic_stream(pa)
                except OSError:
                    continue
    finally:
        try:
            stream.stop_stream()
            stream.close()
        except Exception:
            pass
        pa.terminate()


# ---------------------------------------------------------------------------
# Konsol hodisa-printeri (test-log formati)
# ---------------------------------------------------------------------------

async def console_events(event: dict) -> None:
    t = event["type"]
    if t == "ready":
        if event["reconnected"]:
            ctx = "kontekst SAQLANDI" if event["context_restored"] else "kontekst yangidan"
            print(f"  [ULANISH] qayta ulandi ({ctx})")
    elif t == "mic_active":
        print(f"  [MIC] ovoz aniqlandi (daraja: {event['level']})")
    elif t == "user_transcript":
        if event["final"]:
            print(f"  [SIZ, to'liq]  {event['text']}")
        else:
            print("\n" + "-" * 60)
            print(f"  [SIZ]  {event['text']}")
    elif t == "latency":
        ms = event["ms"]
        target = "OK" if ms < 1500 else "SEKIN (maqsad < 1500 ms)"
        print(f"  [LATENCY] nutq tugashi -> birinchi token: {ms} ms ({target})")
    elif t == "ai_text":
        print(f"  [AI]   {event['text']}")
    elif t == "tts":
        ttfb = f"{event['ttfb_ms']} ms" if event["ttfb_ms"] is not None else "-"
        label = "sintez+ijro" if event["playback_included"] else "sintez"
        print(
            f"  [TTS #{event['idx']}] \"{event['sentence']}\" | "
            f"birinchi bayt: {ttfb} | {label}: {event['total_ms']} ms"
        )
    elif t == "barge_in":
        print("  [BARGE-IN] foydalanuvchi gapni bo'ldi — TTS to'xtatildi, bufer tozalandi")
    elif t == "reconnecting":
        if event["reason"] == "go_away":
            print("  [ULANISH] server sessiyani yopmoqchi (GoAway) — qayta ulanishga tayyorlanamiz")
        else:
            ctx = "kontekst saqlanadi" if event.get("context_preserved") else "kontekst yangidan boshlanadi"
            print(
                f"\n  [ULANISH] aloqa uzildi — {event['delay_s']} soniyadan keyin "
                f"qayta ulanamiz ({ctx})..."
            )
    elif t == "error":
        print(f"\nXATO [{event.get('source', '?')}]: {event['message']}")
        if event.get("trace"):
            print(event["trace"])
    # ai_delta konsolda chiqarilmaydi (juda sershovqin) — web UI uchun


# ---------------------------------------------------------------------------

async def run(args) -> None:
    settings = Settings.load()
    pipeline = AssistantPipeline(
        settings,
        event_cb=console_events,
        phone_mode=args.phone,
        text_mode=args.text_mode,
    )

    print("=" * 60)
    print("  O'ZBEK OVOZLI ASSISTENT — KONSOL TEST REJIMI")
    print(f"  Gemini model : {settings.gemini_model}")
    print(f"  Azure ovoz   : {settings.azure_voice}")
    print(f"  Matn manbai  : {'TEXT modallik' if args.text_mode else 'AUDIO + output transkripsiya'}")
    if args.phone:
        print("  Audio sifati : TELEFON SIMULYATSIYASI (8 kHz + G.711 shovqin)")
    else:
        print("  Audio sifati : to'liq (16 kHz)")
    print("  Gapiring! To'xtatish: Ctrl+C")
    print("=" * 60)

    try:
        await pipeline.run(mic_source)
    finally:
        try:
            await pipeline.tts.close()
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="O'zbek ovozli AI-assistent (Gemini Live + Azure TTS) — konsol test stendi"
    )
    parser.add_argument(
        "--phone",
        action="store_true",
        help="Telefon simulyatsiyasi: audioni 8 kHz + G.711 sifatiga tushirish",
    )
    parser.add_argument(
        "--text-mode",
        action="store_true",
        help="response_modalities=[TEXT] so'rash (hozirgi modellarda ishlamaydi)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nTo'xtatildi. Xayr!")
    except PipelineError as e:
        sys.exit(f"\nJIDDIY XATO: {e}")


if __name__ == "__main__":
    main()
