"""Ovoz sozlash (DSP): Gemini ovozining balandligi (pitch) va tezligini (rate)
Azure'dagi TTS_PITCH / TTS_RATE kabi foizda o'zgartirish.

Gemini Live API'da bunday sozlama YO'Q (SpeechConfig faqat ovoz nomini biladi,
google-genai 2.12 da tekshirildi). Shuning uchun 24 kHz PCM16 oqimini o'zimiz
qayta ishlaymiz:

  1) WSOLA (Waveform Similarity Overlap-Add) — vaqtni cho'zish/qisqartirish,
     balandlik o'zgarmaydi;
  2) chiziqli qayta diskretlash (resample) — balandlik va uzunlik birga
     o'zgaradi.

Pitch koeffitsienti p, tezlik r uchun: WSOLA cho'zish = p / r, so'ng resample
1/p.  Uzunlik: (p/r)·(1/p) = 1/r (faqat tezlik ta'sir qiladi), balandlik: p.

Oqimli ishlaydi: bo'laklar kelishi bilan qayta ishlanadi, ichki kechikish
~30 ms (bitta kadr + qidiruv oynasi). Navbat oxirida `tugat()` qolgan dumini
chiqaradi. Faqat numpy — qo'shimcha kutubxona yo'q.

Sifat chegarasi: ±10–15 % gacha tabiiy; ±20 % dan oshsa sun'iylik seziladi
(formantlar ham siljiydi — "kichrayadi/kattalashadi" effekti).
"""

from __future__ import annotations

import numpy as np

SAMPLE_RATE = 24000


def foiz_oqi(value) -> float:
    """"+8%", "-5", "8", 8.0 -> 8.0. Bo'sh/None -> 0."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace("%", "").replace(" ", "")
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


class _Wsola:
    """Oqimli WSOLA. stretch > 1 — uzunroq (sekinroq), < 1 — qisqaroq (tezroq)."""

    def __init__(self, stretch: float, sr: int = SAMPLE_RATE):
        self.N = 512 if sr >= 16000 else 256           # kadr ~21 ms (24 kHz)
        self.H = self.N // 2                            # chiqish qadami (50 % ustma-ust)
        self.delta = max(8, sr // 200)                  # qidiruv ±5 ms
        self.hs = self.H / stretch                      # kirish qadami (kasr)
        n = np.arange(self.N)
        # davriy Hann: 50 % ustma-ust yig'indisi = 1
        self.win = (0.5 - 0.5 * np.cos(2 * np.pi * n / self.N)).astype(np.float32)
        self.qayta_boshla()

    def qayta_boshla(self) -> None:
        self.buf = np.zeros(0, dtype=np.float32)
        self.buf_start = 0            # buf[0] ning oqimdagi mutlaq indeksi
        self.k = 0                    # chiqish kadr hisoblagichi
        self.ovl = np.zeros(self.H, dtype=np.float32)
        self.prev_pos = None

    def _process(self) -> np.ndarray:
        N, H, d = self.N, self.H, self.delta
        out = []
        while True:
            nominal = int(round(self.k * self.hs))
            lo = max(0, nominal - d)
            hi = nominal + d
            end = self.buf_start + len(self.buf)
            if hi + N > end:
                break
            if self.prev_pos is None:
                chosen = nominal
            else:
                # Oldingi kadrning tabiiy davomi (ustma-ust qismi) bilan eng
                # o'xshash boshlanishni qidiramiz — shunda ulanish "chok"siz.
                r0 = self.prev_pos + H - self.buf_start
                ref = self.buf[r0:r0 + H]
                seg = self.buf[lo - self.buf_start: hi - self.buf_start + H]
                cand = np.lib.stride_tricks.sliding_window_view(seg, H)
                norm = np.sqrt(np.einsum("ij,ij->i", cand, cand)) + 1e-6
                scores = (cand @ ref) / norm
                chosen = lo + int(np.argmax(scores))
            c0 = chosen - self.buf_start
            frame = self.buf[c0:c0 + N] * self.win
            out.append(self.ovl + frame[:H])
            self.ovl = frame[H:].copy()
            self.prev_pos = chosen
            self.k += 1
        # Keraksiz boshni tashlaymiz (keyingi kadr uchun kerak joy saqlanadi)
        keep_from = int(round(self.k * self.hs)) - d
        if self.prev_pos is not None:
            keep_from = min(keep_from, self.prev_pos)
        keep_from = max(self.buf_start, keep_from)
        cut = keep_from - self.buf_start
        if cut > 0:
            self.buf = self.buf[cut:]
            self.buf_start = keep_from
        if not out:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(out)

    def process(self, x: np.ndarray) -> np.ndarray:
        self.buf = np.concatenate([self.buf, x.astype(np.float32, copy=False)])
        return self._process()

    def flush(self) -> np.ndarray:
        pad = np.zeros(self.N + self.delta + self.H, dtype=np.float32)
        y = self.process(pad)
        tail = self.ovl
        self.qayta_boshla()
        return np.concatenate([y, tail])


class _Resampler:
    """Oqimli chiziqli resample. step = kirish namunasi / chiqish namunasi (= p)."""

    def __init__(self, step: float):
        self.step = step
        self.qayta_boshla()

    def qayta_boshla(self) -> None:
        self.buf = np.zeros(0, dtype=np.float32)
        self.pos = 0.0

    def process(self, x: np.ndarray) -> np.ndarray:
        buf = np.concatenate([self.buf, x.astype(np.float32, copy=False)])
        n_out = int(np.floor((len(buf) - 1 - self.pos) / self.step)) if len(buf) > 1 else 0
        if n_out <= 0:
            self.buf = buf
            return np.zeros(0, dtype=np.float32)
        t = self.pos + self.step * np.arange(n_out)
        i0 = np.floor(t).astype(np.int64)
        frac = (t - i0).astype(np.float32)
        y = buf[i0] * (1 - frac) + buf[i0 + 1] * frac
        new_pos = self.pos + n_out * self.step
        keep = int(np.floor(new_pos))
        self.buf = buf[keep:]
        self.pos = new_pos - keep
        return y

    def flush(self) -> np.ndarray:
        y = self.process(np.zeros(2, dtype=np.float32))
        self.qayta_boshla()
        return y


class OvozSozlagich:
    """PCM16 mono oqimini pitch/rate foizlari bilan qayta ishlaydi.

        s = OvozSozlagich("+8%", "+3%")
        chiqish = s.qayta_ishla(bolak)   # har kelgan bo'lak uchun
        chiqish += s.tugat()             # navbat oxirida (dum + holatni tiklash)
    """

    def __init__(self, pitch=0, rate=0, sample_rate: int = SAMPLE_RATE):
        self.pitch_pct = foiz_oqi(pitch)
        self.rate_pct = foiz_oqi(rate)
        p = 1.0 + self.pitch_pct / 100.0
        r = 1.0 + self.rate_pct / 100.0
        if p <= 0.3 or r <= 0.3:
            raise ValueError("pitch/rate foizi juda kichik")
        stretch = p / r
        self.wsola = _Wsola(stretch, sample_rate) if abs(stretch - 1.0) > 1e-3 else None
        self.resamp = _Resampler(p) if abs(p - 1.0) > 1e-3 else None

    @property
    def faol(self) -> bool:
        return self.wsola is not None or self.resamp is not None

    def tavsif(self) -> str:
        return f"pitch {self.pitch_pct:+.0f}%, rate {self.rate_pct:+.0f}%"

    def qayta_boshla(self) -> None:
        if self.wsola:
            self.wsola.qayta_boshla()
        if self.resamp:
            self.resamp.qayta_boshla()

    @staticmethod
    def _to_bytes(y: np.ndarray) -> bytes:
        if len(y) == 0:
            return b""
        return np.clip(y, -32768, 32767).astype(np.int16).tobytes()

    def qayta_ishla(self, pcm: bytes) -> bytes:
        if not self.faol or not pcm:
            return pcm
        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        if self.wsola:
            x = self.wsola.process(x)
        if self.resamp:
            x = self.resamp.process(x)
        return self._to_bytes(x)

    def tugat(self) -> bytes:
        if not self.faol:
            return b""
        y = np.zeros(0, dtype=np.float32)
        if self.wsola:
            y = self.wsola.flush()
        if self.resamp:
            y = np.concatenate([self.resamp.process(y), self.resamp.flush()])
        return self._to_bytes(y)


def _sinov() -> int:
    """O'z-o'zini tekshirish: sinus to'lqinda chastota va uzunlik o'lchanadi."""
    sr = SAMPLE_RATE
    t = np.arange(int(sr * 2.0)) / sr
    x = (0.5 * 32767 * np.sin(2 * np.pi * 200 * t)).astype(np.int16).tobytes()

    def chastota(pcm: bytes) -> float:
        y = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
        spec = np.abs(np.fft.rfft(y * np.hanning(len(y))))
        return float(np.argmax(spec) * sr / len(y))

    def ishlat(pitch, rate) -> bytes:
        s = OvozSozlagich(pitch, rate)
        out = b"".join(s.qayta_ishla(x[i:i + 4000]) for i in range(0, len(x), 4000))
        return out + s.tugat()

    xato = 0
    for pitch, rate, kut_f, kut_len in [
        ("+10%", "+0%", 220.0, 1.0),
        ("-10%", "+0%", 180.0, 1.0),
        ("+0%", "+10%", 200.0, 1 / 1.1),
        ("+0%", "-10%", 200.0, 1 / 0.9),
        ("+8%", "+3%", 216.0, 1 / 1.03),
    ]:
        y = ishlat(pitch, rate)
        f = chastota(y)
        uz = len(y) / len(x)
        ok = abs(f - kut_f) < 2.0 and abs(uz - kut_len) < 0.02
        xato += not ok
        print(f"  pitch {pitch:>5} rate {rate:>5}: f={f:6.1f} Hz (kutilgan {kut_f}), "
              f"uzunlik x{uz:.3f} (kutilgan {kut_len:.3f}) {'OK' if ok else 'XATO'}")
    return xato


if __name__ == "__main__":
    import sys
    sys.exit(_sinov())
