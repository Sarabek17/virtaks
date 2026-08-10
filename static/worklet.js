/**
 * Mikrofon capture AudioWorklet: brauzer native chastotasidan (odatda 48 kHz)
 * 16 kHz mono PCM16 ga o'giradi va 100 ms li bo'laklarni main thread'ga beradi.
 * Server tomonidagi pipeline aynan shu formatni kutadi (Gemini Live talabi).
 */
const TARGET_RATE = 16000;
const CHUNK_SAMPLES = TARGET_RATE / 10; // 100 ms = 1600 sempl

class MicCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / TARGET_RATE; // sampleRate — worklet global (masalan 48000)
    this.inBuf = new Float32Array(0);
    this.readPos = 0;
    this.outBuf = new Int16Array(CHUNK_SAMPLES);
    this.outLen = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    const mono = input[0]; // birinchi kanal (mono)

    // Kirish buferiga qo'shamiz
    const merged = new Float32Array(this.inBuf.length + mono.length);
    merged.set(this.inBuf);
    merged.set(mono, this.inBuf.length);
    this.inBuf = merged;

    // Chiziqli interpolyatsiya bilan 16 kHz ga tushiramiz
    while (this.readPos + 1 < this.inBuf.length) {
      const i = Math.floor(this.readPos);
      const frac = this.readPos - i;
      const sample = this.inBuf[i] * (1 - frac) + this.inBuf[i + 1] * frac;
      const s = Math.max(-1, Math.min(1, sample));
      this.outBuf[this.outLen++] = s < 0 ? s * 0x8000 : s * 0x7fff;
      this.readPos += this.ratio;

      if (this.outLen === CHUNK_SAMPLES) {
        // 100 ms tayyor — main thread'ga yuboramiz (u WebSocket'ga uzatadi)
        const copy = this.outBuf.slice().buffer;
        this.port.postMessage(copy, [copy]);
        this.outLen = 0;
      }
    }

    // Ishlatilgan qismini tashlaymiz
    const consumed = Math.floor(this.readPos);
    this.inBuf = this.inBuf.slice(consumed);
    this.readPos -= consumed;
    return true;
  }
}

registerProcessor('mic-capture', MicCaptureProcessor);
