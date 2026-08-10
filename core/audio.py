"""Audio yordamchilari: telefon simulyatsiyasi va energiya o'lchovi."""

import numpy as np

SEND_SAMPLE_RATE = 16000          # Gemini Live kirish formati: 16 kHz PCM mono
CHUNK_MS = 100                    # 100 ms li bo'laklar
CHUNK_FRAMES = SEND_SAMPLE_RATE * CHUNK_MS // 1000   # 1600 sempl
TTS_OUTPUT_RATE = 24000           # Azure TTS chiqishi (web rejim uchun)

# Oddiy energiya-VAD chegarasi (faqat latency o'lchovi uchun; haqiqiy VAD
# Gemini serverida avtomatik ishlaydi)
VAD_RMS_THRESHOLD = 400


def rms(pcm: bytes) -> float:
    """int16 PCM bo'lakning o'rtacha energiyasi."""
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    if not len(samples):
        return 0.0
    return float(np.sqrt(np.mean(samples * samples)))


def degrade_to_phone(pcm: bytes) -> bytes:
    """Audioni telefon (tor polosali) sifatiga tushiradi.

    1) 8 kHz ga tushirish — 4 kHz dan yuqori chastotalar yo'qoladi
       (o'zbekcha "s"/"sh", "f" kabi tovushlar aynan shu diapazonda!)
    2) G.711 mu-law uslubida 8 bitli kvantlash shovqini
    3) 16 kHz ga qaytarish (chiziqli interpolyatsiya — yo'qolgan chastotalar QAYTMAYDI)
    """
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    if len(x) % 2:
        x = x[:-1]
    if not len(x):
        return pcm

    # 1) Juft semplarni o'rtachalab 8 kHz ga tushiramiz (sodda anti-aliasing)
    x8 = x.reshape(-1, 2).mean(axis=1)

    # 2) mu-law (G.711) kompanding: 16 bit -> 8 bit -> 16 bit
    mu = 255.0
    n = np.clip(x8 / 32768.0, -1.0, 1.0)
    y = np.sign(n) * np.log1p(mu * np.abs(n)) / np.log1p(mu)
    y = np.round(y * 127.0) / 127.0                      # 8 bitli kvantlash shovqini
    n2 = np.sign(y) * np.expm1(np.abs(y) * np.log1p(mu)) / mu
    x8 = n2 * 32768.0

    # 3) 16 kHz ga qaytaramiz — Gemini har doim 16 kHz kutadi
    idx = np.arange(len(x8) * 2) / 2.0
    x16 = np.interp(idx, np.arange(len(x8)), x8)
    return x16.clip(-32768, 32767).astype(np.int16).tobytes()
