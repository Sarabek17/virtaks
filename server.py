#!/usr/bin/env python3
"""O'zbek ovozli AI-assistent — WEB rejimi (FastAPI + WebSocket).

Brauzer mikrofonni yozib, 16 kHz PCM bo'laklarni WebSocket orqali yuboradi;
server ularni core.AssistantPipeline ga beradi (arxitektura konsol rejimi
bilan BIR XIL — faqat audio manba boshqa) va javoblarni qaytaradi:

  Brauzer -> server : binary  = mikrofon PCM (16 kHz, 16-bit, mono)
                      text    = JSON buyruqlar: {"type":"config","phone":bool}
  Server -> brauzer : binary  = Azure TTS PCM (24 kHz, 16-bit, mono)
                      text    = JSON hodisalar (transkript, latency, barge-in...)

Ishga tushirish:
    python server.py            # http://localhost:8000

MUHIM: brauzer mikrofonga faqat localhost yoki HTTPS sahifada ruxsat beradi.
Tashqi serverga joylashtirishda reverse-proxy (nginx/caddy) orqali TLS shart.
"""

import asyncio
import json
import logging
import os
import sys

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from core import AssistantPipeline, Settings
from core.pipeline import PipelineError

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("assistant.web")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

settings = Settings.load()  # kalitlar yo'q bo'lsa o'zbekcha xato bilan chiqadi

app = FastAPI(title="O'zbek ovozli AI-assistent")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "model": settings.gemini_model, "voice": settings.voice_label}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    client = f"{ws.client.host}:{ws.client.port}" if ws.client else "?"
    log.info("Yangi ulanish: %s", client)

    # Brauzerdan kelayotgan mikrofon bo'laklari uchun navbat.
    # To'lib ketsa eng eskisini tashlaymiz — real vaqt muhimroq.
    # maxsize=15 (~1.5 s): katta bufer yig'ilib qolsa, Gemini foydalanuvchini
    # shuncha KECHIKIB eshitadi — shuning uchun qisqa ushlaymiz.
    audio_q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=15)

    def audio_source_factory():
        async def gen():
            while True:
                yield await audio_q.get()
        return gen()

    async def send_event(event: dict) -> None:
        # Diagnostika uchun hodisalarni server logiga ham yozamiz
        # (ai_delta juda sershovqin — o'tkazib yuboriladi)
        if event.get("type") != "ai_delta":
            log.info("[%s] hodisa: %s", client, event)
        try:
            await ws.send_text(json.dumps(event, ensure_ascii=False))
        except Exception:
            pass  # mijoz uzilgan — pipeline baribir bekor qilinadi

    async def send_tts_audio(pcm: bytes) -> None:
        try:
            await ws.send_bytes(pcm)
        except Exception:
            pass

    pipeline = AssistantPipeline(
        settings,
        event_cb=send_event,
        tts_audio_sink=send_tts_audio,
        phone_mode=False,
    )

    await send_event(
        {
            "type": "hello",
            "model": settings.gemini_model,
            "voice": settings.voice_label,
        }
    )

    pipeline_task = asyncio.create_task(pipeline.run(audio_source_factory))

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                chunk = msg["bytes"]
                if audio_q.full():
                    try:
                        audio_q.get_nowait()  # eng eskisini tashlaymiz
                    except asyncio.QueueEmpty:
                        pass
                audio_q.put_nowait(chunk)
            elif msg.get("text"):
                try:
                    cmd = json.loads(msg["text"])
                except json.JSONDecodeError:
                    continue
                if cmd.get("type") == "config":
                    pipeline.phone_mode = bool(cmd.get("phone", False))
                    await send_event(
                        {"type": "config_ack", "phone": pipeline.phone_mode}
                    )
                elif cmd.get("type") == "barge_in":
                    # Mijoz qo'lda to'xtatdi (Stop tugmasi)
                    await pipeline.tts.stop()
                    await send_event({"type": "barge_in"})
    except WebSocketDisconnect:
        pass
    finally:
        pipeline_task.cancel()
        try:
            await pipeline_task
        except (asyncio.CancelledError, PipelineError):
            pass
        except Exception:
            log.exception("Pipeline yakunlanishida xato")
        try:
            await pipeline.tts.close()   # sintezator/HTTP klient yig'ilib qolmasin
        except Exception:
            pass
        log.info("Ulanish yopildi: %s", client)


def main() -> None:
    host = os.getenv("WEB_HOST", "127.0.0.1")
    port = int(os.getenv("WEB_PORT", "8000"))
    print("=" * 60)
    print("  O'ZBEK OVOZLI ASSISTENT — WEB REJIMI")
    print(f"  Gemini model : {settings.gemini_model}")
    print(f"  Ovoz         : {settings.voice_label} (TTS_PROVIDER={settings.tts_provider})")
    print(f"  Brauzerda oching: http://localhost:{port}")
    print("=" * 60)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
