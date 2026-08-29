"""Gemini Live sessiya menejeri va suhbat konveyeri.

ARXITEKTURA (o'zgartirilmaydi!):
    Audio manba (16 kHz PCM mono: mikrofon / brauzer / kelajakda AudioSocket)
      -> Gemini Live API (audio KIRISH, matn CHIQISH)
      -> Azure TTS (uz-UZ neyro-ovoz)
      -> Chiqish (karnay yoki baytlar oqimi)

UZILISHLARGA CHIDAMLILIK:
  - session_resumption: Gemini har bir muhim nuqtada "resume handle" beradi.
    Ulanish uzilsa (keepalive timeout, GoAway, tarmoq) — yangi ulanishda shu
    handle bilan SUHBAT KONTEKSTI TO'LIQ SAQLANGAN HOLDA davom etamiz.
  - context_window_compression (sliding window): sessiya muddati cheklovini
    olib tashlaydi — uzun suhbatlarda kontekst avtomatik siqiladi.
  - Eksponensial backoff bilan avtomatik qayta ulanish.

MUHIM (2026-iyul): native-audio Live modellar response_modalities=["TEXT"] ni
qo'llab-quvvatlamaydi (1011 xato). Shuning uchun AUDIO modallik +
output_audio_transcription ishlatamiz: Gemini'ning o'z ovozi TASHLAB
YUBORILADI, faqat matn Azure TTS ga boradi. Mantiqiy arxitektura o'zgarmaydi.

TTS_PROVIDER=gemini (2026-08-25): modelning o'z ovozi tashlanmaydi —
inline_data bo'laklari to'g'ridan-to'g'ri chiqishga (karnay/WebSocket)
uzatiladi, Azure/Yandex zaxirada. Talaffuz qatlami bu rejimda ovozga ta'sir
qilmaydi.
"""

import asyncio
import re
import time
import traceback
from typing import AsyncIterator, Awaitable, Callable, Optional

from google import genai
from google.genai import types
from websockets.exceptions import ConnectionClosed

from core import audio as audio_utils
from core.config import Settings
from core.tts import AudioSink, EventCallback, create_tts

AudioSourceFactory = Callable[[], AsyncIterator[bytes]]

_SENTENCE_END = re.compile(r"[.!?]+(?:\s|$)")

# Ketma-ket muvaffaqiyatsiz ulanish urinishlari chegarasi
_MAX_CONSECUTIVE_FAILURES = 10


def take_sentences(buf: str) -> tuple[list[str], str]:
    """Buferdan tugallangan jumlalarni (. ! ?) ajratadi, qolganini qaytaradi."""
    sentences = []
    while True:
        m = _SENTENCE_END.search(buf)
        if not m:
            break
        sent = buf[: m.end()].strip()
        buf = buf[m.end():]
        if sent:
            sentences.append(sent)
    return sentences, buf


class PipelineError(RuntimeError):
    """Tiklanib bo'lmaydigan xato (autentifikatsiya, konfiguratsiya...)."""


class AssistantPipeline:
    """Bitta suhbat sessiyasi: audio manba -> Gemini -> Azure TTS -> chiqish.

    audio_source_factory: har chaqirilganda YANGI 16 kHz PCM generator qaytaradi
    (qayta ulanishda eski generator bekor qilinib, yangisi ochiladi — shuning
    uchun factory, tayyor generator emas).
    """

    def __init__(
        self,
        settings: Settings,
        event_cb: EventCallback,
        tts_audio_sink: Optional[AudioSink] = None,
        phone_mode: bool = False,
        text_mode: bool = False,
    ):
        self.settings = settings
        self.event_cb = event_cb
        self.phone_mode = phone_mode      # web'dan jonli almashtirilishi mumkin
        self.text_mode = text_mode
        self.tts = create_tts(settings, event_cb, audio_sink=tts_audio_sink)
        # Modelning o'z ovozi ishlatiladigan rejim (GeminiVoice) — audio
        # bo'laklari shu funksiyaga boradi, aks holda None (tashlanadi)
        self._model_audio = getattr(self.tts, "play_audio", None)

        # Suhbat navbati (turn) holati
        self.last_voice_ts: Optional[float] = None
        self.first_token_ts: Optional[float] = None
        self.input_buf = ""
        self.input_reported = ""
        self.resp_buf = ""
        self.resp_full = ""
        self.sent_idx = 0
        self._audio_started = False   # navbatda modeldan birinchi audio keldimi
        self._voice_active = False
        self._silence_count = 0

        # Uzilishlarga chidamlilik holati
        self._resume_handle: Optional[str] = None
        self._ever_connected = False

    # -- yordamchilar -----------------------------------------------------------

    async def _emit(self, **event) -> None:
        await self.event_cb(event)

    def _reset_turn(self) -> None:
        self.input_buf = ""
        self.input_reported = ""
        self.resp_buf = ""
        self.resp_full = ""
        self.first_token_ts = None
        self.sent_idx = 0
        self._audio_started = False

    def _build_config(self) -> types.LiveConnectConfig:
        common: dict = dict(
            system_instruction=types.Content(parts=[types.Part(text=self.settings.system_prompt)]),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            # Thinking O'CHIRILADI: latency 2-3 barobar oshadi va "fikr"
            # matnlari javobga aralashadi
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            # Uzilishda kontekstni saqlash uchun resume handle so'raymiz
            session_resumption=types.SessionResumptionConfig(handle=self._resume_handle),
            # Sessiya muddati cheklovini olib tashlash (kontekst siqiladi)
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow()
            ),
        )
        if self.settings.tts_provider == "gemini" and self.settings.gemini_voice:
            common["speech_config"] = types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.settings.gemini_voice
                    )
                )
            )
        if self.settings.tts_provider == "gemini" and self.settings.gemini_affective:
            # Model suhbatdosh ohangini sezib, javob ohangini moslaydi (faqat
            # native-audio modellar; qo'llamasa ulanish 1011 bilan yiqiladi)
            common["enable_affective_dialog"] = True
        if self.text_mode:
            # Sof TEXT modallik — hozirgi native-audio modellar rad etadi,
            # kelajakdagi modellar uchun qoldirilgan
            return types.LiveConnectConfig(response_modalities=["TEXT"], **common)
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            **common,
        )

    # -- audio yuborish -----------------------------------------------------------

    async def _send_audio(self, session, source: AsyncIterator[bytes]) -> None:
        """Audio manbadan bo'laklarni olib Gemini Live ga yuboradi.

        Manba faqat 16 kHz PCM mono bo'laklar yield qilishi shart — mikrofonmi,
        brauzermi, Asterisk AudioSocket'mi — farqi yo'q.
        """
        async for chunk in source:
            if self.phone_mode:
                chunk = audio_utils.degrade_to_phone(chunk)

            level = audio_utils.rms(chunk)
            if level > audio_utils.VAD_RMS_THRESHOLD:
                self.last_voice_ts = time.perf_counter()
                self._silence_count = 0
                if not self._voice_active:
                    self._voice_active = True
                    await self._emit(type="mic_active", level=round(level))
            else:
                self._silence_count += 1
                if self._voice_active and self._silence_count >= 10:  # ~1 s jimlik
                    self._voice_active = False

            await session.send_realtime_input(
                audio=types.Blob(
                    data=chunk,
                    mime_type=f"audio/pcm;rate={audio_utils.SEND_SAMPLE_RATE}",
                )
            )

    # -- javoblarni qabul qilish ----------------------------------------------------

    async def _on_text_piece(self, piece: str) -> None:
        if self.first_token_ts is None:
            self.first_token_ts = time.perf_counter()
            if self.input_buf.strip():
                await self._emit(
                    type="user_transcript", text=self.input_buf.strip(), final=False
                )
                self.input_reported = self.input_buf
            if self.last_voice_ts is not None:
                latency_ms = (self.first_token_ts - self.last_voice_ts) * 1000
                await self._emit(type="latency", ms=round(latency_ms))

        self.resp_buf += piece
        self.resp_full += piece
        await self._emit(type="ai_delta", text=piece)
        sentences, self.resp_buf = take_sentences(self.resp_buf)
        for sent in sentences:
            self.sent_idx += 1
            self.tts.say(sent, self.sent_idx)

    async def _on_model_audio(self, pcm: bytes) -> None:
        """Modelning o'z ovozi (TTS_PROVIDER=gemini): bo'lakni ijroga uzatish."""
        if not self._audio_started:
            self._audio_started = True
            ttfb_ms = (
                (time.perf_counter() - self.last_voice_ts) * 1000
                if self.last_voice_ts is not None else None
            )
            # Konsol/web statistikasi Azure bilan bir xil hodisa orqali
            await self._emit(
                type="tts", idx=1, sentence="(Gemini ovozi)", raw_sentence=None,
                ttfb_ms=round(ttfb_ms) if ttfb_ms is not None else None,
                total_ms=0, playback_included=False,
            )
        self._model_audio(pcm)

    async def _on_interrupted(self) -> None:
        await self._emit(type="barge_in")
        self.resp_buf = ""
        self.resp_full = ""
        self.first_token_ts = None
        self.sent_idx = 0
        self._audio_started = False
        await self.tts.stop()
        # input_buf tozalanmaydi: unda foydalanuvchining YANGI gapi yig'ilmoqda

    async def _on_turn_complete(self) -> None:
        # Gemini ovozi + pitch/rate sozlash: navbat oxirida DSP dumini chiqarish
        flush_audio = getattr(self.tts, "flush_audio", None)
        if flush_audio is not None:
            flush_audio()
        remainder = self.resp_buf.strip()
        if remainder:
            self.sent_idx += 1
            self.tts.say(remainder, self.sent_idx)
        if self.input_buf.strip() and self.input_buf != self.input_reported:
            await self._emit(
                type="user_transcript", text=self.input_buf.strip(), final=True
            )
        if self.resp_full.strip():
            await self._emit(type="ai_text", text=self.resp_full.strip())
        self._reset_turn()

    async def _receive(self, session) -> None:
        # MUHIM: google-genai da session.receive() BITTA NAVBAT uchun iterator
        # qaytaradi — turn_complete kelganda iterator TUGAYDI (live.py:449 break).
        # Tashqi while shart: har navbatdan keyin yangi iterator ochamiz.
        # Busiz birinchi javobdan keyin sessiya "kar" bo'lib qoladi: websocketni
        # hech kim o'qimaydi -> pong'lar ishlanmaydi -> keepalive timeout (1011).
        while True:
            await self._receive_one_turn(session)

    async def _receive_one_turn(self, session) -> None:
        async for msg in session.receive():
            # Uzilishda kontekstni tiklash uchun handle'ni yangilab boramiz
            if msg.session_resumption_update:
                upd = msg.session_resumption_update
                if upd.resumable and upd.new_handle:
                    self._resume_handle = upd.new_handle

            # Server yaqinda ulanishni yopishini oldindan bildiradi
            if msg.go_away:
                await self._emit(
                    type="reconnecting",
                    reason="go_away",
                    detail=str(msg.go_away.time_left or ""),
                )

            sc = msg.server_content
            if sc is None:
                continue

            if sc.input_transcription and sc.input_transcription.text:
                self.input_buf += sc.input_transcription.text

            if sc.interrupted:
                await self._on_interrupted()
                continue

            # Matn ikki yo'ldan keladi:
            #  1) output_transcription — standart rejim (AUDIO + transkripsiya)
            #  2) model_turn.parts[].text — text_mode (agar model TEXT ni qo'llasa)
            if sc.output_transcription and sc.output_transcription.text:
                await self._on_text_piece(sc.output_transcription.text)

            if sc.model_turn:
                for part in sc.model_turn.parts or []:
                    if getattr(part, "thought", False):
                        continue  # modelning ICHKI FIKRI — javob emas
                    if part.text:
                        await self._on_text_piece(part.text)
                    # part.inline_data = Gemini'ning O'Z OVOZI. Azure/Yandex
                    # rejimida ataylab TASHLAB YUBORILADI (talaffuzni TTS
                    # kafolatlaydi); TTS_PROVIDER=gemini da ijroga boradi
                    if (
                        self._model_audio is not None
                        and part.inline_data is not None
                        and part.inline_data.data
                    ):
                        await self._on_model_audio(part.inline_data.data)

            if sc.turn_complete:
                await self._on_turn_complete()

    # -- asosiy sikl -----------------------------------------------------------

    async def run(self, audio_source_factory: AudioSourceFactory) -> None:
        """Sessiyani yuritadi; uzilishlarda kontekstni saqlab qayta ulanadi.

        Tashqaridan bekor qilinmaguncha (asyncio cancellation) ishlayveradi.
        PipelineError — tiklanib bo'lmaydigan xato (kalit, konfiguratsiya).
        """
        client = genai.Client(api_key=self.settings.gemini_api_key)
        consecutive_failures = 0

        while True:
            fatal_errors: list[BaseException] = []
            try:
                async with client.aio.live.connect(
                    model=self.settings.gemini_model, config=self._build_config()
                ) as session:
                    await self._emit(
                        type="ready",
                        model=self.settings.gemini_model,
                        reconnected=self._ever_connected,
                        context_restored=bool(self._resume_handle),
                    )
                    self._ever_connected = True
                    consecutive_failures = 0
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(
                            self._send_audio(session, audio_source_factory())
                        )
                        tg.create_task(self._receive(session))
                        tg.create_task(self.tts.worker())
            except* ConnectionClosed:
                # Gemini Live sessiyalari vaqti-vaqti bilan uziladi (keepalive
                # timeout, GoAway, server limitlari) — bu kutilgan holat
                pass
            except* Exception as eg:
                fatal_errors = list(eg.exceptions)

            if fatal_errors:
                if not self._ever_connected:
                    # Birinchi ulanishdayoq xato — kalit/model/konfiguratsiya muammosi
                    for e in fatal_errors:
                        await self._emit(
                            type="error",
                            source="connect",
                            message=str(e),
                            trace="".join(traceback.format_exception(e)),
                        )
                    raise PipelineError(str(fatal_errors[0])) from fatal_errors[0]
                # Ulanish ishlagan edi — vaqtinchalik muammo deb hisoblab qayta uramiz
                for e in fatal_errors:
                    await self._emit(type="error", source="session", message=str(e))

            consecutive_failures += 1
            if consecutive_failures > _MAX_CONSECUTIVE_FAILURES:
                raise PipelineError(
                    "Ulanish ketma-ket ko'p marta uzildi — internet yoki API bilan "
                    "jiddiy muammo bor."
                )

            # Navbat holatini tozalab, backoff bilan qayta ulanamiz.
            # Kontekst yo'qolmaydi: _resume_handle keyingi ulanishda ishlatiladi.
            backoff = min(2 ** (consecutive_failures - 1), 15)
            await self._emit(
                type="reconnecting",
                reason="connection_lost",
                delay_s=backoff,
                context_preserved=bool(self._resume_handle),
            )
            await self.tts.stop()
            self._reset_turn()
            await asyncio.sleep(backoff)
