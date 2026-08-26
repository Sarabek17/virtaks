/**
 * O'zbek ovozli AI-assistent — web-mijoz.
 *
 * Oqim: mikrofon -> AudioWorklet (16 kHz PCM16) -> WebSocket -> server
 *       server -> WebSocket -> (JSON hodisalar + 24 kHz TTS PCM) -> karnay
 */

const TTS_RATE = 24000;

const els = {
  startBtn: document.getElementById('startBtn'),
  stopSpeechBtn: document.getElementById('stopSpeechBtn'),
  phoneMode: document.getElementById('phoneMode'),
  status: document.getElementById('status'),
  statusText: document.getElementById('statusText'),
  micDot: document.getElementById('micDot'),
  chat: document.getElementById('chat'),
  statLatency: document.getElementById('statLatency'),
  statLatencyAvg: document.getElementById('statLatencyAvg'),
  statTtfb: document.getElementById('statTtfb'),
  statTurns: document.getElementById('statTurns'),
  modelInfo: document.getElementById('modelInfo'),
};

let ws = null;
let audioCtx = null;
let mediaStream = null;
let workletNode = null;
let running = false;

// TTS ijro navbati
let playQueue = [];      // faol AudioBufferSourceNode'lar
let nextPlayTime = 0;

// Statistika (massiv emas — soatlab ochiq sessiyada cheksiz o'smasin)
let latCount = 0;
let latSum = 0;
let currentAiBubble = null;

// Chat DOM chegarasi: eng eski elementlar o'chiriladi (uzoq sessiyada
// brauzer sekinlashib qolmasligi uchun)
const MAX_CHAT_ELEMENTS = 300;

function trimChat() {
  while (els.chat.children.length > MAX_CHAT_ELEMENTS) {
    els.chat.removeChild(els.chat.firstChild);
  }
}

function setStatus(cls, text) {
  els.status.className = 'dot ' + cls;
  els.statusText.textContent = text;
}

function addBubble(who, text) {
  const div = document.createElement('div');
  div.className = 'bubble ' + who;
  div.textContent = text;
  els.chat.appendChild(div);
  trimChat();
  els.chat.scrollTop = els.chat.scrollHeight;
  return div;
}

function addMeta(text) {
  const div = document.createElement('div');
  div.className = 'meta';
  div.textContent = text;
  els.chat.appendChild(div);
  trimChat();
  els.chat.scrollTop = els.chat.scrollHeight;
}

// ---------------------------------------------------------------------------
// TTS ijro (24 kHz PCM16 -> AudioBuffer navbati)
// ---------------------------------------------------------------------------

function playTtsChunk(arrayBuffer) {
  if (!audioCtx) return;
  const int16 = new Int16Array(arrayBuffer);
  if (!int16.length) return;
  const buf = audioCtx.createBuffer(1, int16.length, TTS_RATE);
  const ch = buf.getChannelData(0);
  for (let i = 0; i < int16.length; i++) ch[i] = int16[i] / 0x8000;

  const src = audioCtx.createBufferSource();
  src.buffer = buf;
  src.connect(audioCtx.destination);
  const startAt = Math.max(audioCtx.currentTime + 0.02, nextPlayTime);
  src.start(startAt);
  nextPlayTime = startAt + buf.duration;
  playQueue.push(src);
  src.onended = () => {
    playQueue = playQueue.filter((s) => s !== src);
  };
}

function flushPlayback() {
  // BARGE-IN: hamma rejalashtirilgan ovozni darhol to'xtatamiz
  for (const src of playQueue) {
    try { src.stop(); } catch (e) { /* allaqachon tugagan */ }
  }
  playQueue = [];
  nextPlayTime = 0;
}

// ---------------------------------------------------------------------------
// Server hodisalari
// ---------------------------------------------------------------------------

function handleEvent(ev) {
  switch (ev.type) {
    case 'hello':
      els.modelInfo.textContent = ev.model + ' + ' + ev.voice;
      break;
    case 'ready':
      setStatus('ok', ev.reconnected
        ? 'Qayta ulandi' + (ev.context_restored ? ' (kontekst saqlandi)' : '')
        : 'Tayyor — gapiring!');
      break;
    case 'mic_active':
      els.micDot.classList.add('active');
      setTimeout(() => els.micDot.classList.remove('active'), 800);
      break;
    case 'user_transcript':
      if (!ev.final) {
        // YANGI savol tanildi — eski javobning hali ijro etilmagan ovozini
        // darhol to'xtatamiz (aks holda yangi javob eski ovoz orqasida
        // navbatda turib, "eshitmayapti" degan taassurot beradi)
        flushPlayback();
        addBubble('user', ev.text);
      }
      break;
    case 'latency': {
      latCount += 1;
      latSum += ev.ms;
      const avg = Math.round(latSum / latCount);
      els.statLatency.textContent = ev.ms + ' ms';
      els.statLatency.className = 'val ' + (ev.ms < 1500 ? 'good' : 'bad');
      els.statLatencyAvg.textContent = avg + ' ms';
      els.statTurns.textContent = latCount;
      currentAiBubble = null; // yangi javob boshlanadi
      break;
    }
    case 'ai_delta':
      if (!currentAiBubble) currentAiBubble = addBubble('ai', '');
      currentAiBubble.textContent += ev.text;
      els.chat.scrollTop = els.chat.scrollHeight;
      break;
    case 'ai_text':
      if (currentAiBubble) currentAiBubble.textContent = ev.text;
      else addBubble('ai', ev.text);
      currentAiBubble = null;
      break;
    case 'tts':
      if (ev.ttfb_ms !== null) els.statTtfb.textContent = ev.ttfb_ms + ' ms';
      // Talaffuz qatlami matnni o'zgartirgan bo'lsa — nima eshitilayotganini
      // ko'rsatamiz (orfoepiya/lug'at sinovi uchun): raw -> TTS'ga ketgan shakl
      if (ev.raw_sentence) addMeta('🔤 ' + ev.raw_sentence + '  →  ' + ev.sentence);
      break;
    case 'barge_in':
      flushPlayback();
      addMeta('⚡ Gap bo‘lindi (barge-in) — ovoz to‘xtatildi');
      currentAiBubble = null;
      break;
    case 'reconnecting':
      setStatus('warn', ev.reason === 'go_away'
        ? 'Server sessiyani yangilamoqda...'
        : 'Aloqa uzildi — qayta ulanmoqda' +
          (ev.context_preserved ? ' (kontekst saqlanadi)...' : '...'));
      break;
    case 'config_ack':
      addMeta(ev.phone
        ? '📞 Telefon simulyatsiyasi YOQILDI (8 kHz + G.711)'
        : '🎙 To‘liq sifat rejimi (16 kHz)');
      break;
    case 'error':
      setStatus('bad', 'Xato: ' + ev.message);
      break;
  }
}

// ---------------------------------------------------------------------------
// Boshlash / to'xtatish
// ---------------------------------------------------------------------------

async function start() {
  els.startBtn.disabled = true;
  setStatus('warn', 'Ulanmoqda...');

  try {
    // 1. Mikrofon (echoCancellation MUHIM: karnaydagi TTS ovozi mikrofonga
    //    qaytib, assistent o'zini bo'lib yubormasligi uchun)
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    });

    // 2. Audio graf
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    await audioCtx.audioWorklet.addModule('/static/worklet.js');
    const source = audioCtx.createMediaStreamSource(mediaStream);
    workletNode = new AudioWorkletNode(audioCtx, 'mic-capture');
    source.connect(workletNode);
    workletNode.connect(audioCtx.destination); // graf ishlashi uchun (chiqishi jim)

    // 3. WebSocket
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(proto + '://' + location.host + '/ws');
    ws.binaryType = 'arraybuffer';

    ws.onmessage = (e) => {
      if (typeof e.data === 'string') handleEvent(JSON.parse(e.data));
      else playTtsChunk(e.data);
    };
    ws.onclose = () => {
      if (running) setStatus('bad', 'Server bilan aloqa yopildi');
      stop(false);
    };
    ws.onerror = () => setStatus('bad', 'WebSocket xatosi');

    await new Promise((res, rej) => {
      ws.onopen = res;
      setTimeout(() => rej(new Error('ulanish vaqti tugadi')), 8000);
    });

    // 4. Mikrofon bo'laklarini serverga uzatish
    workletNode.port.onmessage = (e) => {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(e.data);
    };

    // Telefon rejimi holatini yuboramiz
    sendConfig();

    running = true;
    els.startBtn.textContent = '⏹ To‘xtatish';
    els.startBtn.disabled = false;
    els.stopSpeechBtn.disabled = false;
  } catch (err) {
    setStatus('bad', 'Boshlashda xato: ' + err.message);
    els.startBtn.disabled = false;
    stop(false);
  }
}

function stop(resetUi = true) {
  running = false;
  flushPlayback();
  if (workletNode) { try { workletNode.disconnect(); } catch (e) {} workletNode = null; }
  if (mediaStream) { mediaStream.getTracks().forEach((t) => t.stop()); mediaStream = null; }
  if (audioCtx) { try { audioCtx.close(); } catch (e) {} audioCtx = null; }
  if (ws) { try { ws.close(); } catch (e) {} ws = null; }
  els.startBtn.textContent = '🎙 Boshlash';
  els.startBtn.disabled = false;
  els.stopSpeechBtn.disabled = true;
  if (resetUi) setStatus('', 'To‘xtatilgan');
}

function sendConfig() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'config', phone: els.phoneMode.checked }));
  }
}

els.startBtn.addEventListener('click', () => (running ? stop() : start()));
els.phoneMode.addEventListener('change', sendConfig);
els.stopSpeechBtn.addEventListener('click', () => {
  flushPlayback();
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'barge_in' }));
  }
});
