"""Azure TTS dvigateli: jumlama-jumla striming, barge-in, ikki xil chiqish.

Chiqish rejimlari:
  - Karnay (audio_sink=None)  — konsol/lokal test: ovoz to'g'ridan-to'g'ri
    standart karnayga chiqadi.
  - Baytlar (audio_sink=...)  — web/telefoniya: 24 kHz 16-bit mono PCM baytlar
    async callback'ka beriladi (WebSocket, kelajakda SIP kanal).

Har bir jumla TTS ga berilishidan OLDIN core.normalize orqali "aksent"
algoritmidan o'tadi (raqamlar so'zga, kirill lotinga, markdown tozalanadi).
"""

import asyncio
import time
from typing import Awaitable, Callable, Optional
from xml.sax.saxutils import escape

import azure.cognitiveservices.speech as speechsdk
import httpx

from core.config import Settings
from core.normalize import normalize_for_tts

EventCallback = Callable[[dict], Awaitable[None]]
AudioSink = Callable[[bytes], Awaitable[None]]


def _parse_pct(value: str) -> int:
    """"+8%" -> 8, "-10%" -> -10"""
    try:
        return int(value.strip().rstrip("%"))
    except ValueError:
        return 0


def prosody_for(sentence: str, base_rate: int, base_pitch: int) -> tuple[str, str]:
    """Prozodiya: NEYTRAL — bazaviy qiymatlar o'zgarishsiz qaytariladi.

    Tajriba ko'rsatdi: jumlama-jumla sun'iy tezlik/ohang o'zgartirish
    (urg'u, tebranish) aksincha ROBOTLIK beradi — noto'g'ri joyda urg'u,
    keraksiz to'xtalishlar. Azure neyro-ovozining O'Z tabiiy prozodiyasi
    (Alisa uslubidagi ravonlik) eng yaxshi natija: matnga aralashmaymiz,
    faqat bazaviy tezlik/tembr beriladi. Intonatsiya matndagi tinish
    belgilaridan (savol, undov, vergul) tabiiy ravishda keladi.
    """
    return f"{base_rate:+d}%", f"{base_pitch:+d}%"


def _drain_batch(
    queue: asyncio.Queue, generation: int, first_raw: str, first_idx: int,
    max_chars: int = 400,
) -> tuple[str, int]:
    """RAVONLIK: navbatda tayyor turgan jumlalarni birlashtiradi.

    TTS yaxlit matnga eng tabiiy, uzluksiz ohang beradi — jumlama-jumla
    sintez ohangni bo'lib, keraksiz to'xtalishlar beradi. Birinchi jumla
    odatda yolg'iz ketadi (past latency saqlanadi), keyingilari LLM tezroq
    yozgani uchun guruh bo'lib qo'shiladi.
    """
    parts = [first_raw]
    idx = first_idx
    while not queue.empty() and sum(len(p) for p in parts) < max_chars:
        try:
            g, i, s = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        if g != generation:
            continue
        parts.append(s)
        idx = i
    return " ".join(parts), idx


class AzureTTS:
    def __init__(
        self,
        settings: Settings,
        event_cb: EventCallback,
        audio_sink: Optional[AudioSink] = None,
    ):
        self.settings = settings
        self.event_cb = event_cb
        self.audio_sink = audio_sink

        cfg = speechsdk.SpeechConfig(
            subscription=settings.azure_speech_key, region=settings.azure_region
        )
        cfg.speech_synthesis_voice_name = settings.azure_voice
        if audio_sink is not None:
            # Baytlar rejimi: SDK o'zi ijro etmaydi, PCM natijani biz olamiz
            cfg.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Raw24Khz16BitMonoPcm
            )
            self.synth = speechsdk.SpeechSynthesizer(speech_config=cfg, audio_config=None)
        else:
            # Karnay rejimi (konsol testi)
            self.synth = speechsdk.SpeechSynthesizer(speech_config=cfg)

        self.queue: asyncio.Queue = asyncio.Queue()
        self.generation = 0          # barge-in hisoblagichi
        self._first_byte_ts: Optional[float] = None
        self._in_flight = False      # hozir sintez ketyaptimi
        self._base_rate = _parse_pct(settings.tts_rate)
        self._base_pitch = _parse_pct(settings.tts_pitch)
        self.synth.synthesizing.connect(self._on_first_chunk)

    # -- ichki ----------------------------------------------------------------

    def _on_first_chunk(self, evt):
        # Birinchi audio bayt kelgan payt (TTFB o'lchovi) — Azure thread'idan chaqiriladi
        if self._first_byte_ts is None:
            self._first_byte_ts = time.perf_counter()

    def _ssml(self, text: str, rate: str, pitch: str) -> str:
        # mstts:silence — har jumla boshidagi/oxiridagi "o'lik havo"ni qisqartiradi:
        # biz jumlama-jumla sintez qilamiz, ortiqcha sukut bo'laklar orasida
        # robotga xos pauza beradi. Qisqartirsak nutq odamnikidek oqadi.
        # <lang> — multilingual ovozlar (masalan AvaMultilingual) uchun matn
        # o'zbekcha ekanini aniq bildiradi; uz-UZ ovozlarga ta'sir qilmaydi.
        return (
            '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="uz-UZ">'
            f'<voice name="{self.settings.azure_voice}">'
            '<mstts:silence type="Leading-exact" value="40ms"/>'
            '<mstts:silence type="Tailing-exact" value="60ms"/>'
            '<lang xml:lang="uz-UZ">'
            f'<prosody rate="{rate}" pitch="{pitch}">'
            f"{escape(text)}</prosody>"
            "</lang></voice></speak>"
        )

    # -- ochiq interfeys --------------------------------------------------------

    def say(self, sentence: str, idx: int) -> None:
        """Jumlani navbatga qo'yish."""
        self.queue.put_nowait((self.generation, idx, sentence))

    async def stop(self) -> None:
        """BARGE-IN: joriy sintezni to'xtatish va navbatni tozalash.

        MUHIM: bu metod hech qachon blok qilmasligi kerak — u Gemini
        qabul-siklidan chaqiriladi. Navbatni tozalash va generation'ni
        oshirish o'zi yetarli (eski natijalar worker'da tashlab yuboriladi).
        stop_speaking_async natijasi ATAYLAB kutilmaydi: .get() ni kutish
        SDK osilganda oqimni band qilib, executor'ni asta to'ldirardi.
        """
        self.generation += 1
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        if self.synth is not None and (self.audio_sink is None or self._in_flight):
            try:
                self.synth.stop_speaking_async()   # fire-and-forget
            except Exception:
                pass  # SDK xatosi — baribir generation himoya qiladi

    async def close(self) -> None:
        """Ulanish yopilganda resurslarni bo'shatish.

        Azure SDK'da ochiq close() yo'q — hodisa ulanishlarini uzib, havolani
        tashlaymiz (native resurs GC bilan qaytadi). Har WebSocket ulanish o'z
        sintezatorini yaratadi — busiz uzoq ishlaydigan serverda yig'ilib boradi.
        """
        synth, self.synth = self.synth, None
        if synth is None:
            return
        try:
            synth.synthesizing.disconnect_all()
        except Exception:
            pass

    async def worker(self) -> None:
        """Navbatdagi jumlalarni ketma-ket sintez qiladi va vaqtini o'lchaydi."""
        while True:
            gen, idx, raw_sentence = await self.queue.get()
            if gen != self.generation:
                continue  # barge-in'dan oldingi eskirgan jumla

            raw_sentence, idx = _drain_batch(
                self.queue, self.generation, raw_sentence, idx
            )

            # "Aksent" algoritmi: matnni toza lotin-o'zbekka keltiramiz
            sentence = normalize_for_tts(raw_sentence)
            if not sentence:
                continue

            # Dinamik prozodiya: jumla turiga qarab ohang tanlanadi
            rate, pitch = prosody_for(sentence, self._base_rate, self._base_pitch)

            self._first_byte_ts = None
            t0 = time.perf_counter()
            self._in_flight = True
            try:
                future = self.synth.speak_ssml_async(self._ssml(sentence, rate, pitch))
                # Muhlat SHART: Azure SDK osilib qolsa future.get() abadiy
                # bloklaydi — worker qotadi va assistent butunlay jim bo'lib
                # qoladi (ulanish tirik bo'lgani uchun reconnect ham bo'lmaydi)
                result = await asyncio.wait_for(asyncio.to_thread(future.get),
                                                timeout=30.0)
            except asyncio.TimeoutError:
                try:
                    self.synth.stop_speaking_async()  # kutmaymiz — bo'shatishga urinish
                except Exception:
                    pass
                if gen == self.generation:
                    await self.event_cb({
                        "type": "error", "source": "tts",
                        "message": f"TTS 30 soniyada javob bermadi — jumla "
                                   f"tashlab yuborildi: \"{sentence[:60]}\"",
                    })
                continue
            finally:
                self._in_flight = False
            total_ms = (time.perf_counter() - t0) * 1000
            ttfb_ms = (
                (self._first_byte_ts - t0) * 1000 if self._first_byte_ts else None
            )

            if result.reason == speechsdk.ResultReason.Canceled:
                details = result.cancellation_details
                if gen == self.generation:
                    await self.event_cb(
                        {
                            "type": "error",
                            "source": "tts",
                            "message": f"{details.reason}: {details.error_details}",
                        }
                    )
                continue

            # Barge-in sintez PAYTIDA bo'lgan bo'lsa — natijani tashlaymiz
            if gen != self.generation:
                continue

            if self.audio_sink is not None and result.audio_data:
                await self.audio_sink(result.audio_data)

            await self.event_cb(
                {
                    "type": "tts",
                    "idx": idx,
                    "sentence": sentence,
                    "raw_sentence": raw_sentence if raw_sentence.strip() != sentence else None,
                    "ttfb_ms": round(ttfb_ms) if ttfb_ms is not None else None,
                    "total_ms": round(total_ms),
                    # Karnay rejimida total_ms ijroni ham o'z ichiga oladi
                    "playback_included": self.audio_sink is None,
                }
            )


class YandexTTS:
    """Yandex SpeechKit TTS — Alisa yaratilgan texnologiya, o'zbekcha "nigora" ovozi.

    AzureTTS bilan bir xil interfeys (say/stop/worker), shuning uchun pipeline
    uchun farqi yo'q. REST v1 sintez API ishlatiladi, chiqish: 24 kHz LPCM.
    Eslatma: Yandex v1 da pitch sozlamasi yo'q, faqat tezlik (speed).
    """

    URL = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
    SAMPLE_RATE = 24000

    def __init__(
        self,
        settings: Settings,
        event_cb: EventCallback,
        audio_sink: Optional[AudioSink] = None,
    ):
        self.settings = settings
        self.event_cb = event_cb
        self.audio_sink = audio_sink
        self.queue: asyncio.Queue = asyncio.Queue()
        self.generation = 0
        # TTS_RATE (+4%) -> Yandex speed (1.04)
        self._speed = max(0.5, min(3.0, 1.0 + _parse_pct(settings.tts_rate) / 100))
        self._client = httpx.AsyncClient(timeout=30.0)
        self._pa = None       # karnay rejimi uchun lazy pyaudio
        self._out_stream = None

    def say(self, sentence: str, idx: int) -> None:
        self.queue.put_nowait((self.generation, idx, sentence))

    async def stop(self) -> None:
        """BARGE-IN: navbat tozalanadi; ketayotgan sintez natijasi generation
        tekshiruvi bilan tashlab yuboriladi, ijro esa 100 ms ichida to'xtaydi."""
        self.generation += 1
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def close(self) -> None:
        """Ulanish yopilganda resurslarni bo'shatish: HTTP klient va karnay.

        Busiz har WebSocket ulanish o'zining httpx klientini (socketlarini)
        ochiq qoldirardi — uzoq ishlaydigan serverda asta yig'ilib boradi.
        """
        try:
            await self._client.aclose()
        except Exception:
            pass
        if self._out_stream is not None:
            try:
                self._out_stream.stop_stream()
                self._out_stream.close()
            except Exception:
                pass
            self._out_stream = None
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None

    def _play_speaker(self, pcm: bytes, gen: int) -> None:
        """Konsol rejimi: 24 kHz PCM ni karnayga chiqarish (barge-in'ni his qiladi)."""
        import pyaudio  # lazy: web-serverga pyaudio umuman kerak emas

        if self._pa is None:
            self._pa = pyaudio.PyAudio()
            self._out_stream = self._pa.open(
                format=pyaudio.paInt16, channels=1, rate=self.SAMPLE_RATE, output=True
            )
        chunk = self.SAMPLE_RATE // 10 * 2  # 100 ms
        for i in range(0, len(pcm), chunk):
            if gen != self.generation:
                break  # barge-in — darhol jim bo'lamiz
            self._out_stream.write(pcm[i:i + chunk])

    async def worker(self) -> None:
        while True:
            gen, idx, raw_sentence = await self.queue.get()
            if gen != self.generation:
                continue

            raw_sentence, idx = _drain_batch(
                self.queue, self.generation, raw_sentence, idx
            )
            sentence = normalize_for_tts(raw_sentence)
            if not sentence:
                continue

            t0 = time.perf_counter()
            ttfb_ms = None
            buf = bytearray()
            try:
                async with self._client.stream(
                    "POST",
                    self.URL,
                    headers={"Authorization": f"Api-Key {self.settings.yandex_api_key}"},
                    data={
                        "text": sentence,
                        "lang": "uz-UZ",
                        "voice": self.settings.yandex_voice,
                        "speed": f"{self._speed:.2f}",
                        "format": "lpcm",
                        "sampleRateHertz": str(self.SAMPLE_RATE),
                    },
                ) as resp:
                    if resp.status_code != 200:
                        body = (await resp.aread())[:300]
                        await self.event_cb(
                            {
                                "type": "error",
                                "source": "tts",
                                "message": f"Yandex TTS {resp.status_code}: {body.decode(errors='replace')}",
                            }
                        )
                        continue
                    async for chunk in resp.aiter_bytes():
                        if ttfb_ms is None:
                            ttfb_ms = (time.perf_counter() - t0) * 1000
                        buf += chunk
            except httpx.HTTPError as e:
                await self.event_cb(
                    {"type": "error", "source": "tts", "message": f"Yandex TTS: {e}"}
                )
                continue

            total_ms = (time.perf_counter() - t0) * 1000
            if gen != self.generation or not buf:
                continue  # barge-in sintez paytida bo'ldi — natija tashlanadi

            pcm = bytes(buf)
            if self.audio_sink is not None:
                await self.audio_sink(pcm)
            else:
                await asyncio.to_thread(self._play_speaker, pcm, gen)

            await self.event_cb(
                {
                    "type": "tts",
                    "idx": idx,
                    "sentence": sentence,
                    "raw_sentence": raw_sentence if raw_sentence.strip() != sentence else None,
                    "ttfb_ms": round(ttfb_ms) if ttfb_ms is not None else None,
                    "total_ms": round(total_ms),
                    "playback_included": self.audio_sink is None,
                }
            )


class GeminiVoice:
    """Gemini Live'ning O'Z ovozi — sintez yo'q, model chiqarayotgan audio
    to'g'ridan-to'g'ri uzatiladi.

    AzureTTS bilan bir xil interfeys (say/stop/worker/close) + play_audio():
    pipeline model_turn.parts[].inline_data bo'laklarini (24 kHz PCM16 mono —
    Azure chiqishi bilan bir xil format) shu yerga beradi. say() hech narsa
    qilmaydi — matn faqat ekran uchun.

    MUHIM: talaffuz qatlami (core.normalize) BU REJIMDA OVOZGA TA'SIR
    QILMAYDI — model o'zi gapiradi, biz uning matnini tuzata olmaymiz.
    Azure/Yandex TTS_PROVIDER orqali zaxirada qoladi.
    """

    SAMPLE_RATE = 24000

    def __init__(
        self,
        settings: Settings,
        event_cb: EventCallback,
        audio_sink: Optional[AudioSink] = None,
    ):
        self.settings = settings
        self.event_cb = event_cb
        self.audio_sink = audio_sink
        self.queue: asyncio.Queue = asyncio.Queue()
        self.generation = 0
        self._pa = None
        self._out_stream = None
        # Balandlik/tezlik sozlash (GEMINI_PITCH / GEMINI_RATE) — Azure'dagi
        # TTS_PITCH/TTS_RATE ning DSP analogi; 0% bo'lsa umuman ishlatilmaydi.
        from core.ovoz_sozlash import OvozSozlagich

        sozlagich = OvozSozlagich(settings.gemini_pitch, settings.gemini_rate, self.SAMPLE_RATE)
        self.sozlagich = sozlagich if sozlagich.faol else None

    def say(self, sentence: str, idx: int) -> None:
        pass  # matn sintez qilinmaydi — ovoz modeldan keladi

    def play_audio(self, pcm: bytes) -> None:
        """Modeldan kelgan audio bo'lagini ijro navbatiga qo'yish."""
        self.queue.put_nowait((self.generation, pcm))

    def flush_audio(self) -> None:
        """Navbat tugadi: sozlagichda qolgan dumni (~30 ms) chiqarish."""
        if self.sozlagich is not None:
            self.queue.put_nowait((self.generation, None))

    async def stop(self) -> None:
        """BARGE-IN: navbatdagi eski bo'laklar tashlanadi, karnay 100 ms ichida jim bo'ladi."""
        self.generation += 1
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        if self.sozlagich is not None:
            self.sozlagich.qayta_boshla()

    async def close(self) -> None:
        if self._out_stream is not None:
            try:
                self._out_stream.stop_stream()
                self._out_stream.close()
            except Exception:
                pass
            self._out_stream = None
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None

    def _play_speaker(self, pcm: bytes, gen: int) -> None:
        import pyaudio  # lazy: web-serverga pyaudio umuman kerak emas

        if self._pa is None:
            self._pa = pyaudio.PyAudio()
            self._out_stream = self._pa.open(
                format=pyaudio.paInt16, channels=1, rate=self.SAMPLE_RATE, output=True
            )
        chunk = self.SAMPLE_RATE // 10 * 2  # 100 ms
        for i in range(0, len(pcm), chunk):
            if gen != self.generation:
                break
            self._out_stream.write(pcm[i:i + chunk])

    async def worker(self) -> None:
        while True:
            gen, pcm = await self.queue.get()
            if gen != self.generation:
                continue
            if self.sozlagich is not None:
                # None — navbat oxiri belgisi (flush_audio): dumni chiqaramiz
                pcm = self.sozlagich.tugat() if pcm is None else self.sozlagich.qayta_ishla(pcm)
            if not pcm:
                continue
            if self.audio_sink is not None:
                await self.audio_sink(pcm)
            else:
                await asyncio.to_thread(self._play_speaker, pcm, gen)


def create_tts(
    settings: Settings,
    event_cb: EventCallback,
    audio_sink: Optional[AudioSink] = None,
):
    """TTS ta'minotchisini tanlash: .env dagi TTS_PROVIDER (azure | yandex | gemini)."""
    if settings.tts_provider == "gemini":
        return GeminiVoice(settings, event_cb, audio_sink=audio_sink)
    if settings.tts_provider == "yandex":
        return YandexTTS(settings, event_cb, audio_sink=audio_sink)
    return AzureTTS(settings, event_cb, audio_sink=audio_sink)
