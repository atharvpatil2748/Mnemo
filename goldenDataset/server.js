/**
 * Arvsal Server
 * Deterministic-first command pipeline
 * LLM used ONLY where intended
 * Memory-safe
 * AI-mode persistent
 */

const path = require("path");
require("module-alias/register");
require("dotenv").config({
  path: path.resolve(__dirname, "../.env")
});

if (process.env.UCML_ENABLED === 'true') {
  console.log('[UCML] ENABLED');
  if (process.env.UCML_DEBUG === 'true') {
    console.log('[UCML] DEBUG ENABLED');
  }
  
  const RAMIndexer = require('@core/cognitive/ucml/RAMIndexer');
  console.log('[UCML] Initializing RAM Indexer...');
  RAMIndexer.initialize().then(() => {
    console.log('[UCML] RAM Indexer Ready');
    console.log(`[UCML] Entity Index: ${RAMIndexer.entityIndex.size}`);
    console.log(`[UCML] Date Index: ${RAMIndexer.dateIndex.size}`);
    console.log(`[UCML] Vector Index: ${RAMIndexer.vectorKeywordIndex.size}`);
    console.log(`[UCML] Decision Index: ${RAMIndexer.decisionIndex.size}`);
    console.log(`[UCML] CSG Index: ${RAMIndexer.csgKeywordIndex.size}`);
  }).catch(err => {
    console.error('[UCML] INDEX INITIALIZATION FAILED', err);
  });
}

/* ================= OLLAMA WARMUP ================= */

const { warmAll } = require('@providers/llm/ollamaWarmup');
warmAll(); // DO NOT await


/* ================= MEMORY ================= */

const chatHistory = require('@core/memory/chatHistory');
const episodicMemory = require('@core/memory/episodicMemory');
const memory = require('@core/memory/semanticMemory');
const { extractKey } = require('@core/memory/themeExtractor');

/* ================= CORE ================= */

const express = require("express");
const cors = require("cors");
const fs = require("fs");
const os = require("os");
const { spawn } = require("child_process");
const axios = require("axios");
const FormData = require("form-data");  // 🔥 THIS ONE
/* ================= CONFIRMATION ================= */

const {
  setConfirmation,
  getConfirmation,
  clearConfirmation
} = require('@core/reasoning/confirmManager');

/* ================= PENDING SUGGESTION STATE ================= */
// Manages "type 1/2/3 to confirm" flow for content suggestions

let _pendingSuggestion = null;

function setPendingSuggestion(data) { _pendingSuggestion = data; }
function getPendingSuggestion() { return _pendingSuggestion; }
function clearPendingSuggestion() { _pendingSuggestion = null; }


/* ================= BRAIN ================= */

const normalize = require('@utils/normalizer');
const classifyIntent = require('@core/intent/intentClassifier');
const { handleIntent } = require('@actions/actions');
const applyPersonality = require('@core/personality/personality');
const llmRouter = require('@providers/llm/llmRouter');
const { getWeather, getNews } = require('@actions/localSkills');
const { runLLM } = require('@providers/llm/llmRunner');
const { isActionIntent } = require('@core/intent/actionIntentDetector');
const { sendTelegramMessage, fetchUpdates, sendTelegramDocument, downloadTelegramFile, downloadTelegramFileToBuffer } = require('@integrations/telegram/telegramService');
const { enableRemote, disableRemote, isRemoteEnabled } = require('@utils/remoteControl');
const { verifyToken } = require('@utils/totpManager');
const { searchFileByName } = require('@utils/fileSearch');
const screenshot = require("screenshot-desktop");
const { startWhatsApp, sendMessage } = require('@integrations/whatsapp/whatsappBridge');
const { enableBusy, disableBusy, isBusy, getBusyState } = require('@utils/busyMode');
const { isVIP } = require('@utils/vipList');
const { addMissed, formatSummary, clearMissed } = require('@utils/missedTracker');
const { canAutoReply, resetCooldown } = require('@utils/autoReplyGuard');
const { getContact, getAllContacts } = require('@utils/contactBook');
const { takeAeyeSnap } = require('@modules/aeye/visualService');
const visionRouter = require('@modules/vision/visionRouter');
const { runOCR } = require('@modules/vision/ocrRunner');
const { isTextHeavy } = require('@modules/vision/visionAnalyzer');
const sharp = require("sharp");
const { createTempFile, safeDelete, cleanupAll } = require('@utils/safeTempManager');
const interaction = require('@agents/interactionModeManager');
const conversionEngine = require('@integrations/telegram/conversionEngine');
const { classifyScreen } = require('@modules/vision/screenClassifier');
const { runFinalWhisper } = require('@modules/stt/whisperManager');
const vadManager = require('@modules/stt/vadManager');
const ttsSwitch = require('@providers/tts/ttsSwitch');


/* ================= VISION-DRIVEN ACTION LAYER (NEW) ================= */

const { handleScreenAction } = require('@modules/vision/screenActionOrchestrator');
const { suggestContent } = require('@actions/contentSuggester');

/* ================= PHASE 0.5: UNIFIED AGENT LOOP ================= */
// Feature-flag import. Does NOT affect legacy routing.
const { runAgent } = require('@core/reasoning/unifiedAgentLoop');

console.log(`
=================================================

[ROUTING MODE]

DEFAULT:
Unified Cognitive Core

LEGACY PREFIX:
"/legacy "

=================================================
`);

/* ================= REFLECTION ================= */

const { maybeRunReflection } = require('@modules/reflection/reflectionRunner');

/* ================= COGNITIVE LAYER (PHASE 1) ================= */

const cognitiveSnapshot = require('@core/cognitive/cognitiveSnapshot');
const workingMemory     = require('@core/cognitive/workingMemory');
// nodeTypeRegistry loaded implicitly by cognitiveSnapshot/workingMemory

const SyncEngine = require('../integrations/communication/channels/email/sync/SyncEngine');

// Load snapshot and pre-populate Working Memory immediately at startup
let _cognitiveSnapshot = cognitiveSnapshot.load();
workingMemory.init({ snapshot: _cognitiveSnapshot });

// Periodic snapshot save every 5 minutes
setInterval(() => {
  try {
    cognitiveSnapshot.mergeWorkingMemory(_cognitiveSnapshot, workingMemory.getSnapshotData());
    cognitiveSnapshot.save(_cognitiveSnapshot);
  } catch { }
}, 5 * 60 * 1000);

// Start Email SyncEngine in the background (non-blocking)
process.nextTick(() => {
  SyncEngine.start().catch(err => console.error('[Server] SyncEngine failed to start:', err.message));
});

/* ================= SYSTEM ACTIONS ================= */

const {
  openApp,
  openFolder,
  openCalendar,
  shutdown,
  restart,
  sleep,
  lock,
  volumeUp,
  volumeDown,
  mute,
  searchGoogle,
  openYouTube
} = require('@actions/systemActions');

const NON_LLM_INTENTS = new Set([
  "LOCAL_SKILL",
  "OPEN_APP",
  "OPEN_FOLDER",
  "OPEN_CALENDAR",
  "SHUTDOWN",
  "RESTART",
  "LOCK",
  "SLEEP",
  "MUTE",
  "VOLUME_UP",
  "VOLUME_DOWN",
  "SEARCH",
  "YOUTUBE"
]);
/* ================= AI SWITCH ================= */

const {
  connectChatGPT,
  connectGemini,
  connectGroq,
  disconnectAI,
  getActiveAI
} = require('@providers/llm/aiSwitch');

/* ================= APP ================= */

const app = express();
app.use(cors());

// 🔥 raw audio MUST come before json
app.use("/audio", express.raw({
  type: ["audio/webm", "audio/wav", "application/octet-stream"],
  limit: "50mb"
}));

app.use(express.json());
app.get("/health", (_req, res) => {
  res.json({ status: "ok" });
});

/* ================= HEAVY INFERENCE LOCK ================= */
// Prevents Whisper medium model + LLM from running concurrently.
// Concurrent large model allocations exhaust address space → VirtualAlloc fatal crash.

let _heavyBusy = false;

async function runHeavyInference(label, fn) {
  // Spin-wait until any other heavy inference completes (max 90s wait)
  const deadline = Date.now() + 90000;
  while (_heavyBusy) {
    if (Date.now() > deadline) {
      console.warn(`[HeavyLock] ${label} wait exceeded 90s — proceeding anyway`);
      break;
    }
    await new Promise(r => setTimeout(r, 100));
  }
  _heavyBusy = true;
  try {
    return await fn();
  } finally {
    _heavyBusy = false;
  }
}

// Memory monitor — log RSS/heap every 60s to catch leaks
setInterval(() => {
  const m = process.memoryUsage();
  console.log(
    `[MEM] rss=${Math.round(m.rss / 1e6)}MB heap=${Math.round(m.heapUsed / 1e6)}/${Math.round(m.heapTotal / 1e6)}MB ext=${Math.round(m.external / 1e6)}MB`
  );
}, 60000);

/* ================= HELPERS ================= */
function stripWakeWord(text = "") {
  return text
    .replace(/^hey\s+(arvsal|arsal|arsel|arsenal|harshal)\s*/i, "")
    .trim();
}

async function speakLocally(text) {
  try {
    const audioBuffer = await ttsSwitch.generateAudio(text);
    const wavPath = createTempFile("tts_local", ".wav");
    fs.writeFileSync(wavPath, audioBuffer);

    await new Promise((resolve) => {
      const player = spawn("powershell", [
        "-c",
        `(New-Object Media.SoundPlayer "${wavPath}").PlaySync();`
      ]);

      player.on("close", () => {
        safeDelete(wavPath);
        resolve();
      });
    });
  } catch (err) {
    console.log("Local TTS error:", err.message);
  }
}

let speaking = false;

async function sendStatus(message) {
  console.log("🧠 ARVSAL:", message);

  if (speaking) return;

  speaking = true;

  try {
    await speakLocally(message); // 🔥 USE LOCAL SPEAKER
  } catch (err) {
    console.log("TTS failed:", err.message);
  }

  speaking = false;
}

function startNarrationSequence(messages, interval = 10000) {
  let i = 0;
  let stopped = false;

  const loop = async () => {
    while (!stopped && i < messages.length) {
      await sendStatus(messages[i]); // ✅ MUST await
      i++;
      await new Promise(r => setTimeout(r, interval));
    }
  };

  loop();

  return () => {
    stopped = true;
  };
}

async function analyzeScreen(prompt) {

  const tempPath = createTempFile("screen", ".png");
  const processedPath = createTempFile("screen_processed", ".png");

  let ocrText = "";
  let result;

  try {

    // 📸 Capture
    await screenshot({ filename: tempPath });

    // === First Pass: Cropped (Editor Optimized) ===
    await sharp(tempPath)
      .grayscale()
      .normalize()
      .sharpen()
      .extract({ left: 300, top: 100, width: 1200, height: 800 })
      .toFile(processedPath);

    ocrText = await runOCR(processedPath);

    console.log("CROPPED OCR LENGTH:", ocrText.length);

    // === Adaptive Retry If Weak ===
    if (ocrText.length < 300) {

      console.log("⚠️ Low OCR detected. Retrying full screen...");

      await sharp(tempPath)
        .grayscale()
        .normalize()
        .sharpen()
        .toFile(processedPath);

      ocrText = await runOCR(processedPath);

      console.log("FULL OCR LENGTH:", ocrText.length);
    }
    const screenType = classifyScreen(ocrText);
    console.log("SCREEN TYPE:", screenType);

    // ===== TEXT MODE =====
    if (isTextHeavy(ocrText)) {

      const textPrompt = `
      Screen context: ${screenType}

      You are performing technical screen analysis using raw OCR text.

      STRICT RULES:
      - Use ONLY extracted text
      - Be precise
      - Adapt explanation to the screen context (${screenType})
      - Do NOT speculate
      - Quote exact phrases

      Extracted Text:
      -------------------------
      ${ocrText}
      -------------------------

      User request:
      ${prompt || "Analyze and explain clearly."}
      `;

      result = await llmRouter({
        intent: "GENERAL_QUESTION",
        text: textPrompt
      });

      return result;
    }

    // ===== VISION FALLBACK =====
    result = await visionRouter({
      imagePath: tempPath,
      prompt: prompt || "Analyze precisely."
    });

    return result;

  } catch (err) {

    console.error("analyzeScreen error:", err.message);
    throw err;

  } finally {

    // ⭐ CLEANUP MUST NEVER THROW
    try { safeDelete(tempPath); } catch { }
    try { safeDelete(processedPath); } catch { }
  }
}

/* ================= MEMORY CONFIDENCE DECAY ================= */

try { memory.decayConfidence(); } catch { }
setInterval(() => {
  try { memory.decayConfidence(); } catch { }
}, 6 * 60 * 60 * 1000);

/* ================= WHISPER OUTPUT VALIDATOR (v2) ================= */

const WHISPER_ARTIFACTS_PARTIAL = [
  "thanks for watching", "thank you for watching", "please subscribe",
  "captions by", "subtitles by", "amara org", "translated by"
];

const WHISPER_ARTIFACTS_EXACT = new Set([
  "music", "applause", "thank you"
]);

const SINGLE_WORD_FILLERS = new Set([
  "you", "thanks", "hmm", "um", "uh", "oh", "ah", "the", "a", "i", "well"
]);

function validateWhisperOutput(raw, stageId = "?") {
  // Gate 1: type check
  if (!raw || typeof raw !== "string") {
    console.log(`[${stageId}] ❌ REJECT: null/non-string output`);
    return "";
  }

  // Gate 2: strip noise tokens + normalize whitespace
  let text = raw
    .replace(/\[.*?\]/g, "")   // [BLANK_AUDIO], [MUSIC], etc.
    .replace(/\(.*?\)/g, "")   // (crickets chirping), etc.
    .replace(/\s+/g, " ")      // normalize whitespace
    .trim();

  // Gate 3: char length minimum — catches ".", "-", single-char artifacts
  if (text.length < 3) {
    console.log(`[${stageId}] ❌ REJECT: too short ("${text}")`);
    return "";
  }
  
  const normalized = text.toLowerCase().replace(/[^a-z0-9 ]/g, "").trim();
  const words = normalized.split(/\s+/).filter(Boolean);

  // Gate 4: Punctuation/garbage-output gate
  const alphaChars = (normalized.match(/[a-z]/g) || []).length;
  if (alphaChars < 2) {
    console.log(`[${stageId}] ❌ REJECT: punctuation garbage ("${text}")`);
    return "";
  }

  // Gate 5: Exact Match Artifacts
  if (WHISPER_ARTIFACTS_EXACT.has(normalized)) {
    console.log(`[${stageId}] ❌ REJECT: exact artifact ("${text}")`);
    return "";
  }

  // Gate 6: Partial Match YouTube Artifacts (Guarded to <= 5 words)
  if (words.length <= 5 && WHISPER_ARTIFACTS_PARTIAL.some(art => normalized.includes(art))) {
    console.log(`[${stageId}] ❌ REJECT: partial artifact ("${text}")`);
    return "";
  }

  // Gate 7: Autoregressive Loop Detector
  if (words.length >= 5) {
    const uniqueWords = new Set(words);
    if (uniqueWords.size === 1) {
      console.log(`[${stageId}] ❌ REJECT: autoregressive loop ("${text}")`);
      return "";
    }
  }

  // Gate 8: Single-word Filler Blocklist
  if (words.length === 1 && SINGLE_WORD_FILLERS.has(words[0])) {
    console.log(`[${stageId}] ❌ REJECT: single-word filler ("${text}")`);
    return "";
  }

  // Gate 9: strip wake word residue at STT boundary
  const cleaned = stripWakeWord(text);
  if (!cleaned) {
    console.log(`[${stageId}] ❌ REJECT: only wake word in output`);
    return "";
  }

  console.log(`[${stageId}] ✅ ACCEPT: "${cleaned}"`);
  return cleaned;
}



/* ================= PCM → WAV HELPER ================= */

/**
 * Converts a raw Int16 PCM buffer (16kHz, mono) into a valid WAV buffer.
 * Built entirely in memory — NO FFmpeg, NO disk I/O for the header.
 * @param {Buffer} pcmBuffer  Raw 16-bit little-endian PCM samples
 * @param {number} sampleRate Defaults to 16000 (whisper.cpp requirement)
 * @returns {Buffer} Complete WAV file buffer (header + data)
 */
function pcmToWav(pcmBuffer, sampleRate = 16000) {
  const numChannels = 1;
  const bitsPerSample = 16;
  const byteRate = sampleRate * numChannels * (bitsPerSample / 8);
  const blockAlign = numChannels * (bitsPerSample / 8);
  const dataSize = pcmBuffer.length;
  const header = Buffer.alloc(44);

  header.write("RIFF", 0);                          // ChunkID
  header.writeUInt32LE(36 + dataSize, 4);            // ChunkSize
  header.write("WAVE", 8);                          // Format
  header.write("fmt ", 12);                         // Subchunk1ID
  header.writeUInt32LE(16, 16);                      // Subchunk1Size (PCM)
  header.writeUInt16LE(1, 20);                       // AudioFormat (PCM = 1)
  header.writeUInt16LE(numChannels, 22);             // NumChannels
  header.writeUInt32LE(sampleRate, 24);              // SampleRate
  header.writeUInt32LE(byteRate, 28);                // ByteRate
  header.writeUInt16LE(blockAlign, 32);              // BlockAlign
  header.writeUInt16LE(bitsPerSample, 34);           // BitsPerSample
  header.write("data", 36);                         // Subchunk2ID
  header.writeUInt32LE(dataSize, 40);                // Subchunk2Size

  return Buffer.concat([header, pcmBuffer]);
}




/* ================= AUDIO/FINAL — Whisper Medium ================= */

const MEDIUM_MODEL_PATH = require('@utils/pathConfig').MEDIUM_MODEL_PATH;

// Accepts the same raw WebM body as /audio.
// Runs ggml-medium for single blocking transcription.
app.post("/audio/final", async (req, res) => {
  const stageId = `final_${Date.now()}`;
  try {
    if (!req.body || !req.body.length) {
      console.log(`[${stageId}] ❌ REJECT: empty buffer`);
      return res.json({ text: "" });
    }

    console.log(`[${stageId}] ✅ audio_received bytes=${req.body.length}`);

    let whisperInputPath;
    const contentType = req.headers["content-type"];

    if (contentType === "application/octet-stream") {
      // 🚀 NEW OPTIMIZED PIPELINE: Raw PCM + Silero VAD (No FFmpeg)
      whisperInputPath = createTempFile("final", ".wav");
      const wavBuffer = pcmToWav(req.body, 16000);
      fs.writeFileSync(whisperInputPath, wavBuffer);
      console.log(`[${stageId}] [Native VAD] Bypassed FFmpeg. WAV size: ${wavBuffer.length}`);

      // Apply the trustworthy Silero VAD as a final gate before heavy Whisper inference
      console.log(`[${stageId}] [INSTRUMENT] Fast VAD check on ${whisperInputPath}`);
      const vadResult = await vadManager.checkSpeech(whisperInputPath, { mode: 'spawn' });
      if (!vadResult.pass) {
        console.log(`[${stageId}] ❌ VAD REJECT: no qualified speech detected in PCM buffer`);
        safeDelete(whisperInputPath);
        return res.json({ text: "" });
      }
    } else {
      // 🐌 LEGACY PIPELINE: WebM + FFmpeg + VAD
      const webmPath = createTempFile("final", ".webm");
      const wavPath = createTempFile("final", ".wav");
      fs.writeFileSync(webmPath, req.body);

      const ffmpegExe = process.env.ARVSAL_FFMPEG_PATH || path.resolve(__dirname, "../runtime/ffmpeg/bin/ffmpeg.exe");

      await new Promise((resolve, reject) => {
        const args = [
          "-y", "-i", webmPath,
          "-ar", "16000",
          "-ac", "1",
          "-c:a", "pcm_s16le",
          wavPath
        ];
        const ff = spawn(ffmpegExe, args);
        ff.on("close", code => code === 0 ? resolve() : reject(new Error("ffmpeg failed")));
      });

      safeDelete(webmPath);

      const wavStats = fs.statSync(wavPath);
      if (wavStats.size < 40000) {
        safeDelete(wavPath);
        return res.json({ text: "" });
      }

      const vadResult = await vadManager.checkSpeech(wavPath, { mode: 'spawn' });
      if (!vadResult.pass) {
        safeDelete(wavPath);
        return res.json({ text: "" });
      }

      whisperInputPath = wavPath;
      if (vadResult.speechStartMs != null && vadResult.speechEndMs != null) {
        const trimmedPath = createTempFile("vad_trimmed", ".wav");
        const ffmpegExeTrim = process.env.ARVSAL_FFMPEG_PATH || path.resolve(__dirname, "../runtime/ffmpeg/bin/ffmpeg.exe");
        const trimStart = Math.max(0, (vadResult.speechStartMs - 150) / 1000);
        const trimEnd   = (vadResult.speechEndMs + 200) / 1000;
        const trimOk = await new Promise((resolve) => {
          const ff = spawn(ffmpegExeTrim, [
            "-y", "-i", wavPath,
            "-ss", String(trimStart),
            "-to", String(trimEnd),
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
            trimmedPath
          ]);
          ff.on("close", code => resolve(code === 0));
        });
        if (trimOk) {
          safeDelete(wavPath);
          whisperInputPath = trimmedPath;
        } else {
          safeDelete(trimmedPath);
        }
      }
    }

    console.log(`[${stageId}] [INSTRUMENT] Whisper start (model: ${MEDIUM_MODEL_PATH}, input: ${whisperInputPath})`);
    
    const raw = await runHeavyInference('audio/final', () => runFinalWhisper(
      whisperInputPath,
      MEDIUM_MODEL_PATH,
      []
    ));
      
    console.log(`[${stageId}] [INSTRUMENT] Whisper raw output: "${raw}"`);
    safeDelete(whisperInputPath);

    console.log(`[${stageId}] [INSTRUMENT] validateWhisperOutput input: "${raw}"`);
    const finalText = validateWhisperOutput(raw || "", stageId);
    console.log(`[${stageId}] [INSTRUMENT] validateWhisperOutput output: "${finalText}"`);
    console.log(`[${stageId}] whisper_output text="${finalText}"`);

    if (!finalText) {
      return res.json({ text: "" });
    }

    return res.json({ text: finalText });

  } catch (err) {
    console.error(`[${stageId}] [audio/final] error:`, err.message);
    res.json({ text: "" });
  }
});



/* ================= TTS (PIPER) ================= */


app.post("/speak", async (req, res) => {
  try {
    const text = req.body?.text;
    if (!text || typeof text !== "string") {
      return res.status(400).json({ error: "No text provided" });
    }

    const options = {
      voice: req.body?.voice
    };

    const audio = await ttsSwitch.generateAudio(text, options);
    res.set("Content-Type", "audio/wav");
    res.send(audio);

  } catch (err) {
    console.error("TTS ERROR:", err);
    res.status(500).json({ error: "TTS failed" });
  }
});

app.get("/api/tts/status", (req, res) => {
  res.json({
    engine: ttsSwitch.getActiveEngine(),
    voice: ttsSwitch.getDefaultVoice()
  });
});

app.post("/api/tts/switch", (req, res) => {
  const { engine, voice } = req.body;
  let updated = false;
  if (engine) {
    updated = ttsSwitch.setActiveEngine(engine);
  }
  if (voice) {
    updated = ttsSwitch.setDefaultVoice(voice) || updated;
  }
  res.json({
    success: updated,
    engine: ttsSwitch.getActiveEngine(),
    voice: ttsSwitch.getDefaultVoice()
  });
});

/* ================= COMMAND ENDPOINT ================= */

app.get("/stream", (req, res) => {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  
  const progressEmitter = require('@core/state/progressEventEmitter');
  
  const onToken = (token) => {
    res.write(`data: ${JSON.stringify({ token })}\n\n`);
  };
  
  progressEmitter.on('stream-token', onToken);
  
  req.on('close', () => {
    progressEmitter.off('stream-token', onToken);
  });
});

app.post("/command", async (req, res) => {
  const controller = new AbortController();
  const { signal } = controller;

  res.on('close', () => {
    if (!res.writableEnded) {
      console.warn("[SERVER] Client connection closed prematurely. Triggering abort signal...");
      controller.abort();
    }
  });

  const rawInput =
    req.body.command ??
    req.body.text ??
    req.body.message ??
    "";

  if (!rawInput || typeof rawInput !== "string") {
    return res.json({ reply: "" });
  }

  const source = req.headers["x-source"] || "local";

  // ================= GLOBAL BUSY MODE =================

  const lower = rawInput.toLowerCase();

  // Enable busy
  if (lower.startsWith("busy ")) {

    // Format:
    // busy study 90
    // busy lecture 120

    const parts = lower.split(" ");
    const type = parts[1] || "busy";
    const minutes = parseInt(parts[2]) || 60;

    const freeAt = new Date(Date.now() + minutes * 60000);

    enableBusy(type, freeAt, async () => {

      const summary = formatSummary();

      await sendTelegramMessage(
        `⏰ Busy mode expired (${type}).\n\n${summary}`
      );

      await sendMessage("919699621635@c.us",
        `⏰ Busy mode expired (${type}).\n\n${summary}`
      );
      resetCooldown();

      clearMissed();
    });

    return res.json({
      reply: `Busy mode enabled: ${type}\nFree at ${freeAt.toLocaleTimeString()}`
    });
  }
  if (lower === "missed") {

    const summary = formatSummary();

    clearMissed();

    return res.json({ reply: summary });
  }

  // Disable busy
  if (lower === "free") {
    disableBusy();
    resetCooldown();
    return res.json({ reply: "Busy mode disabled." });
  }

  // Status
  if (lower === "status") {

    if (!isBusy()) {
      return res.json({ reply: "You are currently free." });
    }

    const state = getBusyState();

    return res.json({
      reply: `Current mode: ${state.type}\nFree at ${new Date(state.freeAt).toLocaleTimeString()}`
    });
  }

  // ================= DIRECT MESSAGE =================
  // Format:
  // message Rahul Hello bro

  if (lower.startsWith("message ")) {

    const parts = rawInput.split(" ");
    const name = parts[1];
    const content = parts.slice(2).join(" ");

    const number = getContact(name);

    if (!number) {
      return res.json({
        reply: `Unknown contact.\nAvailable: ${getAllContacts().join(", ")}`
      });
    }

    await sendMessage(number, content);

    return res.json({ reply: `Message sent to ${name}.` });
  }

  /* ---------- NORMALIZATION ---------- */

  const normalized = normalize(rawInput);

  // 🔒 FORCE spoken + typed to behave identically
  let cleanRawText = stripWakeWord(normalized.rawText);
  const cleanNormalizedText = stripWakeWord(
    normalized.normalizedText
      .toLowerCase()
      .replace(/[^\w\s]/g, "")   // 🔥 remove punctuation
      .trim()
  );

  /* ---------- TELEGRAM ---------- */

  if (source === "telegram") {

    const parts = cleanRawText.split(" ");
    const lastWord = parts[parts.length - 1];

    const lower = cleanRawText.toLowerCase();

    const sensitiveCommands = [
      "enable remote",
      "disable remote",
      "shutdown",
      "restart",
      "send file",
      "screenshot"
    ];

    const isSensitive = sensitiveCommands.some(cmd =>
      lower.startsWith(cmd)
    );
    if (isSensitive) {

      if (!verifyToken(lastWord)) {
        // 🚨 INTRUDER ALERT: Trigger the A-Eye silently before replying
        // We use a non-awaited call or a separate try/catch so the reply isn't delayed
        takeAeyeSnap().catch(err => console.error("Intruder snap failed:", err));

        return res.json({ reply: "❌ Invalid or missing TOTP code. A-Eye scan initiated." });
      }

      // remove TOTP from command
      cleanRawText = parts.slice(0, -1).join(" ");
    }


    const updatedLower = cleanRawText.toLowerCase();

    if (updatedLower === "enable remote") {
      enableRemote();
      return res.json({ reply: "🔓 Remote control enabled." });
    }

    if (updatedLower === "disable remote") {
      disableRemote();
      return res.json({ reply: "🔒 Remote control disabled." });
    }

    if (!isRemoteEnabled()) {
      return res.json({ reply: "🚫 Remote control is disabled." });
    }
  }

  // 🔥 Telegram-specific file send trigger
  if (source === "telegram" && cleanRawText.toLowerCase().startsWith("send file")) {

    const keyword = cleanRawText.replace(/send file/i, "").trim();

    const filePath = searchFileByName(keyword);

    if (!filePath) {
      return res.json({ reply: "File not found." });
    }

    await sendTelegramDocument(filePath);

    return res.json({ reply: "File sent successfully." });
  }

  if (source === "telegram" && cleanRawText.toLowerCase().startsWith("screenshot")) {

    const tempPath = createTempFile("telegram_screen", ".png");

    await screenshot({ filename: tempPath });
    await new Promise(r => setTimeout(r, 200));

    await sendTelegramDocument(tempPath);

    safeDelete(tempPath);

    return res.json({ reply: "Screenshot sent and deleted locally." });
  }

  /* ---------- SCREEN ANALYSIS ---------- */

  if (lower.startsWith("analyze screen")) {

    let prompt = rawInput
      .replace(/analyze screen/i, "")
      .replace(/[^\w\s]/g, "")   // remove punctuation
      .trim();

    if (!prompt || prompt.length < 3) {
      prompt = "Analyze and explain clearly.";
    }

    try {

      const result = await analyzeScreen(prompt);

      return res.json({ reply: result });

    } catch (err) {
      return res.json({ reply: "Vision analysis failed: " + err.message });
    }
  }

  /* ---------- INTENT CLASSIFICATION (MOVED UP FOR PHASE 0.5E) ---------- */

  let intentObj = null; 

  /* ---------- CHAT HISTORY (USER) ---------- */

  chatHistory.addMessage("user", cleanRawText);

  const emotional =
    /\b(wasted|tired|sad|happy|free|love|hate|stress|enjoy)\b/i.test(cleanRawText);

  // ALWAYS classify intent BEFORE routing
  intentObj = classifyIntent({
    rawText: cleanRawText,
    normalizedText: cleanNormalizedText
  });

  /* ─────────────────────────────────────────────────────────────
   * PHASE 0.5E: DETERMINISTIC / UNIFIED HYBRID ROUTING
   *
   * Intent classification happens first.
   * If it's a reasoning-heavy intent (General, Memory, Coding, Math),
   * we route it to the Unified Cognitive Core.
   *
   * If it's a fast-path OS command (Mute, Open App) or /legacy prefix,
   * we fall through to the native deterministic switch blocks below.
   * ───────────────────────────────────────────────────────────── */

  const UNIFIED_CORE_INTENTS = [
    "GENERAL_QUESTION", "SMALLTALK", "CODING_QUERY", "MATH_QUERY",
    "MEMORY_SUMMARY", "EPISODIC_RECALL", "META_MEMORY", "RECALL"
  ];

  let reply = "";
  let skipEpisodic = false;
  let skipPersonality = false;
  let handledByUnifiedCore = false;

  if (cleanRawText.startsWith('/legacy ')) {
    cleanRawText = cleanRawText.replace('/legacy ', '').trim();
    cleanNormalizedText = cleanRawText.toLowerCase();
    // Re-classify without the prefix
    intentObj = classifyIntent({
      rawText: cleanRawText,
      normalizedText: cleanNormalizedText
    });
    console.log('[Phase 0.5E] Routing to legacy bifurcated path:', cleanRawText);
    // FALL THROUGH to switch block
  } else if (UNIFIED_CORE_INTENTS.includes(intentObj.intent)) {
    console.log(`[Phase 0.5E] Unified Agent Loop routing: [${intentObj.intent}]`, cleanRawText);
    try {
      // Pass full context to unifiedAgentLoop with a unique session ID
      const requestSessionId = req.headers["x-session-id"] || ('temp_session_' + Date.now() + '_' + Math.random().toString(36).substring(2, 7));
      reply = await runAgent(cleanRawText, intentObj.intent, intentObj, requestSessionId, { signal });
      handledByUnifiedCore = true;
    } catch (err) {
      if (signal?.aborted) {
        console.warn('[Phase 0.5E] Unified Agent Loop aborted:', err.message);
        if (!res.writableEnded) {
          return res.json({
            success: false,
            reply: "Query execution aborted due to timeout or client disconnection.",
            error: "Query execution aborted due to timeout or client disconnection."
          });
        }
        return;
      }
      console.error('[Phase 0.5E] Unified Agent Loop error:', err.message);
      reply = 'Unified cognitive core encountered an error, sir. Falling back.';
      handledByUnifiedCore = true;
    }
  } else {
    console.log(`[Phase 0.5E] Deterministic execution path: [${intentObj.intent}]`);
    // FALL THROUGH to native handler switch block
  }

  /* ---------- CONFIRMATION (ABSOLUTE PRIORITY) ---------- */

  const pendingStore = require('@core/state/pendingActionStore');
  const phase2Pending = pendingStore.getPending();
  if (phase2Pending) {
    if (intentObj.intent === "CONFIRM_YES") {
      pendingStore.clear();
      try {
        const { executeTool } = require('@tools/toolRegistry');
        const toolResult = await executeTool({ 
          tool: phase2Pending.tool, 
          action: phase2Pending.action, 
          params: phase2Pending.params 
        });
        const reply = `Action ${phase2Pending.tool}.${phase2Pending.action} executed. Result: ${toolResult.success ? 'Success' : 'Failed - ' + toolResult.error}`;
        chatHistory.addMessage("arvsal", reply);
        return res.json({ reply });
      } catch (err) {
        const reply = `Execution failed: ${err.message}`;
        chatHistory.addMessage("arvsal", reply);
        return res.json({ reply });
      }
    }

    if (intentObj.intent === "CONFIRM_NO") {
      pendingStore.clear();
      const reply = "Okay, cancelled Phase 2 action.";
      chatHistory.addMessage("arvsal", reply);
      return res.json({ reply });
    }

    const reply = "I need your permission to execute the pending action. Please say yes or no.";
    chatHistory.addMessage("arvsal", reply);
    return res.json({ reply });
  }

  const pending = getConfirmation();
  if (pending) {
    if (intentObj.intent === "CONFIRM_YES") {
      clearConfirmation();
      pending.execute?.();
      const reply = "Okay, confirmed.";
      chatHistory.addMessage("arvsal", reply);
      return res.json({ reply });
    }

    if (intentObj.intent === "CONFIRM_NO") {
      clearConfirmation();
      const reply = "Okay, cancelled.";
      chatHistory.addMessage("arvsal", reply);
      return res.json({ reply });
    }

    const reply = "Please say yes or no.";
    chatHistory.addMessage("arvsal", reply);
    return res.json({ reply });
  }

  /* ---------- PENDING SUGGESTION (1/2/3/none) ---------- */

  const _pendingSug = getPendingSuggestion();
  if (_pendingSug) {
    const rawNum = cleanRawText.trim();

    if (/^[1-3]$/.test(rawNum)) {
      const idx = parseInt(rawNum, 10) - 1;
      const chosen = _pendingSug.suggestions[idx];
      clearPendingSuggestion();

      if (chosen) {
        const { executeTool } = require('@tools/toolRegistry');
        await executeTool({
          tool: "desktop",
          action: "type",
          params: { text: chosen }
        });
        const reply = `Typed: "${chosen}"`;
        chatHistory.addMessage("arvsal", reply);
        return res.json({ reply });
      } else {
        const reply = "That option wasn't found. Try 1, 2, or 3.";
        chatHistory.addMessage("arvsal", reply);
        return res.json({ reply });
      }
    }

    if (/^none$/i.test(rawNum)) {
      clearPendingSuggestion();
      const reply = "Suggestion cancelled.";
      chatHistory.addMessage("arvsal", reply);
      return res.json({ reply });
    }
  }


  if (!handledByUnifiedCore && [
    "INTRODUCE_SELF",
    "REMEMBER",
    "RECALL",
    "FORGET",
    "MEMORY_SUMMARY",
    "DAY_RECALL",
    "EPISODIC_RECALL",
    "EPISODIC_BY_DATE",
    "SESSION_RECALL",
    "META_MEMORY"
  ].includes(intentObj.intent)) {
    const reply = await handleIntent(intentObj);
    chatHistory.addMessage("arvsal", reply);
    return res.json({ reply });
  }

  /* ---------- COGNITIVE MEMORY LAYER DEPRECATED IN GENERAL PATH ---------- */
  // The general chat hot-path memory is now exclusively handled by llmRouter.js via the CSM in <10ms.

  /* ---------- MAIN EXECUTION ---------- */

  try {
    if (!handledByUnifiedCore) {
      switch (intentObj.intent) {

      /* ===== AI MODE ===== */

      case "CONNECT_CHATGPT":
        connectChatGPT();
        reply = "Switched to ChatGPT.";
        skipEpisodic = true;
        skipPersonality = true;
        break;

      case "CONNECT_GEMINI":
        connectGemini();
        reply = "Switched to Gemini.";
        skipEpisodic = true;
        skipPersonality = true;
        break;

      case "CONNECT_GROQ":
        connectGroq();
        reply = "Switched to Groq";
        skipEpisodic = true;
        skipPersonality = true;
        break;

      case "DISCONNECT_AI":
        disconnectAI();
        reply = "Disconnected from external AI.";
        skipEpisodic = true;
        skipPersonality = true;
        break;

      /* ===== LOCAL SKILLS ===== */

      case "LOCAL_SKILL":
        skipPersonality = true;

        if (intentObj.skill === "WEATHER") {
          reply = await getWeather(intentObj.city);
        } else if (intentObj.skill === "NEWS") {
          reply = await getNews();
        } else {
          reply = await handleIntent(intentObj);
        }

        // ⚠️ IMPORTANT:
        // Allow episodic memory for meaningful local info
        skipEpisodic = false;
        break;

      /* ===== SYSTEM / APPS ===== */

      case "OPEN_APP":
        openApp(intentObj.app);
        reply = `Opening ${intentObj.app}.`;
        skipEpisodic = true;
        skipPersonality = true;
        break;

      case "OPEN_FOLDER":
        openFolder(intentObj.path);
        reply = "Opening folder.";
        skipEpisodic = true;
        skipPersonality = true;
        break;

      case "OPEN_CALENDAR":
        openCalendar();
        reply = "Opening calendar.";
        skipEpisodic = true;
        skipPersonality = true;
        break;

      case "SHUTDOWN":
        setConfirmation({ execute: shutdown });
        reply = "Are you sure you want to shut down?";
        skipEpisodic = true;
        break;

      case "RESTART":
        setConfirmation({ execute: restart });
        reply = "Are you sure you want to restart?";
        skipEpisodic = true;
        break;

      case "SLEEP":
        setConfirmation({ execute: sleep });
        reply = "Do you want to put the system to sleep?";
        skipEpisodic = true;
        break;

      case "LOCK":
        lock();
        reply = "System locked.";
        skipEpisodic = true;
        skipPersonality = true;
        break;

      case "WEBCAM_SNAP":
        if (source === "telegram") {
          try {
            // Call the new service
            await takeAeyeSnap();
            reply = "A-Eye scan complete. Image sent to your secure channel.";
          } catch (err) {
            reply = "A-Eye failed: " + err;
          }
        } else {
          reply = "Visual scanning is restricted to external secure channels.";
        }
        skipEpisodic = true;
        skipPersonality = true;
        break;


      case "VOLUME_UP":
        volumeUp();
        reply = "Volume increased.";
        skipEpisodic = true;
        skipPersonality = true;
        break;

      case "VOLUME_DOWN":
        volumeDown();
        reply = "Volume decreased.";
        skipEpisodic = true;
        skipPersonality = true;
        break;

      case "MUTE":
        mute();
        reply = "Volume muted.";
        skipEpisodic = true;
        skipPersonality = true;
        break;

      case "SEARCH":
        searchGoogle(intentObj.query);
        reply = `Searching for ${intentObj.query}.`;
        skipEpisodic = true;
        skipPersonality = true;
        break;

      case "YOUTUBE":
        openYouTube(intentObj.query || "");
        reply = "Opening YouTube.";
        skipEpisodic = true;
        skipPersonality = true;
        break;

      case "EMAIL_FETCH": {
        const { fetchAndProcess } = require('@integrations/email/emailHandler');

        skipEpisodic = true;

        // 🔥 START NARRATION LOOP
        const stopNarration = startNarrationSequence([
          "Fetching your emails sir...",
          "Scanning inbox...",
          "Collecting relevant information...",
          "Categorising events and deadlines...",
          "Updating your calendar...",
          "Preparing your schedule briefing..."
        ], 10000);

        try {
          const result = await fetchAndProcess();

          // 🔥 STOP narration immediately after pipeline
          stopNarration();

          if (result.type === "error") {
            reply = "I couldn't fetch your emails right now.";
            break;
          }

          const data = result.data;

          // 🔥 OPTIONAL dynamic update
          sendStatus(`You have ${data.events.length + data.deadlines.length} updates.`);

          const prompt = `
          You are Arvsal, a highly intelligent personal assistant like Jarvis.

          You are given structured data of events and deadlines extracted from emails.
          These items have already been automatically added to the user's calendar.

          Your task:
          - Speak naturally and concisely
          - Summarize intelligently (don't list everything blindly)
          - Highlight important or urgent things
          - Mention time and location where useful
          - Prioritize high priority deadlines
          - Briefly acknowledge that the events/deadlines are already scheduled in the calendar (do this naturally, not repetitively)
          - Sound human, not robotic

          DATA:
          Events:
          ${JSON.stringify(data.events, null, 2)}

          Deadlines:
          ${JSON.stringify(data.deadlines, null, 2)}

          User query:
          "${cleanRawText}"

          Now respond naturally like a smart assistant.
          `;

          reply = await runLLM({
            model: "llama3",
            prompt,
            timeout: 20000
          });

          if (!reply) {
            reply = "I couldn't process your schedule properly.";
          }

        } catch (err) {
          stopNarration(); // 🔥 VERY IMPORTANT (avoid infinite speaking)
          console.error("EMAIL_FETCH ERROR:", err);
          reply = "Something went wrong while checking your emails.";
        }

        break;
      }
      /* ===== GENERATIVE (LAST) ===== */

      /* ===== SCREEN ACTION (Vision Automation Layer) ===== */

      case "SCREEN_ACTION": {
        interaction.setMode("action");
        skipEpisodic = true;
        skipPersonality = true;

        const actionResult = await runAgent(cleanRawText, intentObj.intent, intentObj, requestSessionId, { signal });

        reply = typeof actionResult === "string" ? actionResult : (actionResult?.response || "Screen action completed.");
        interaction.resetMode();
        break;
      }

      case "SCREEN_ACTION_MIXED": {
        interaction.setMode("mixed");
        // Mixed: chat response + screen action in parallel
        skipEpisodic = false;
        skipPersonality = false;

        const [chatReply, actionResult] = await Promise.all([
          llmRouter({ intent: "GENERAL_QUESTION", text: intentObj.rawText }),
          handleScreenAction(intentObj.rawText)
        ]);

        if (actionResult.needsClarification) {
          // If action needs info, prioritize asking over chat
          reply = actionResult.question;
          skipEpisodic = true;
        } else {
          const actionSummary = actionResult.success
            ? `\n\n✅ ${actionResult.response}`
            : `\n\n⚠️ ${actionResult.response}`;
          reply = (chatReply || "") + actionSummary;
        }
        interaction.resetMode();
        break;
      }

      case "SUGGEST_CONTENT": {
        interaction.setMode("suggestion");
        skipEpisodic = true;
        skipPersonality = true;

        // Capture screen for context
        const { captureScreen } = require('@modules/vision/screenCapture');
        const { runOCR } = require('@modules/vision/ocrRunner');
        const { classifyScreen } = require('@modules/vision/screenClassifier');

        let screenOCR = "";
        let screenType = "unknown";

        try {
          const cap = await captureScreen();
          if (cap) {
            screenOCR = await runOCR(cap.imagePath);
            screenType = classifyScreen(screenOCR);
          }
        } catch { /* ignore capture failures */ }

        const suggestResult = await suggestContent({
          screenText: screenOCR,
          screenType,
          userInstruction: intentObj.rawText
        });

        if (suggestResult.suggestions.length > 0) {
          // Store suggestions for follow-up confirmation
          setPendingSuggestion({
            suggestions: suggestResult.suggestions,
            screenType
          });
        }

        reply = suggestResult.response;
        interaction.resetMode();
        break;
      }

      case "CONFIRM_YES":
      case "CONFIRM_NO": {
        // ---- Check pending suggestion first ----
        const pendingSug = getPendingSuggestion();
        const rawNum = cleanRawText.trim();

        if (pendingSug && /^[1-3]$/.test(rawNum)) {
          const idx = parseInt(rawNum, 10) - 1;
          const chosen = pendingSug.suggestions[idx];
          clearPendingSuggestion();

          if (chosen) {
            // Type the chosen suggestion using desktop tool
            const { executeTool } = require('@tools/toolRegistry');
            await executeTool({
              tool: "desktop",
              action: "type",
              params: { text: chosen }
            });
            reply = `Typed: "${chosen}"`;
          } else {
            reply = "That option wasn't found. Try 1, 2, 3, or 'none' to cancel.";
          }
          skipEpisodic = true;
          skipPersonality = true;
          break;
        }

        if (pendingSug && /^none$/i.test(rawNum)) {
          clearPendingSuggestion();
          reply = "Suggestion cancelled.";
          skipEpisodic = true;
          skipPersonality = true;
          break;
        }

        // ---- Normal confirmation flow ----
        const pending = getConfirmation();

        if (!pending) {
          reply = intentObj.intent === "CONFIRM_NO"
            ? "Alright."
            : "Okay.";
          break;
        }

        if (intentObj.intent === "CONFIRM_NO") {
          clearConfirmation();
          reply = "Okay, cancelled.";
          break;
        }

        if (intentObj.intent === "CONFIRM_YES") {
          clearConfirmation();
          reply = await handleIntent(pending);
          break;
        }
      }

      case "SMALLTALK":
      case "GENERAL_QUESTION":
      case "CODING_QUERY":
      case "MATH_QUERY":

        // 1️⃣ Try planner first
        let plan = null;

        if (isActionIntent(cleanRawText)) {
          try {
            plan = await generatePlan({
              userInput: cleanRawText
            });
          } catch (err) {
            console.log("Planner error:", err);
          }
        }

        // 2️⃣ If planner returned steps → execute
        if (
          plan &&
          Array.isArray(plan.steps) &&
          plan.steps.length > 0 &&
          plan.goal !== "unclear"
        ) {

          const { executeTool } = require('@tools/toolRegistry');
          const { evaluate } = require('@safety/riskEngine');

          const risk = evaluate(plan);

          if (!risk.allowed) {
            reply = "This action is blocked for safety.";
            break;
          }

          if (risk.requiresConfirmation) {
            reply = "This action requires confirmation.";
            break;
          }

          let executionResults = [];
          let allSuccess = true;
          const EXECUTABLE_TOOLS = ["system", "desktop", "n8n"];

          for (const step of plan.steps) {

            if (!EXECUTABLE_TOOLS.includes(step.tool)) {
              continue; // ignore non-executable tools
            }

            const result = await executeTool(step);
            executionResults.push(result);

            if (!result?.success) {
              allSuccess = false;
            }
          }

          /* ===== If any action failed ===== */
          if (!allSuccess) {

            const errors = executionResults
              .filter(r => !r.success)
              .map(r => r.error)
              .join(", ");

            reply = `I tried to execute that, but it failed: ${errors}`;
            break;
          }

          /* ===== If execution successful → generate natural confirmation ===== */

          if (plan.goal && plan.goal !== "unclear") {
            reply = `Action completed: ${plan.goal}`;
          } else {
            reply = "Action completed successfully.";
          }
          break;
        }

        // 3️⃣ Otherwise fallback to LLM chat
        reply = await llmRouter({
          intent: intentObj.intent,
          text: cleanRawText
        });

        if (!reply) {
          reply = "I'm not certain about that.";
        }

        break;

        reply = "I'm not certain about that.";
    }
    }

  } catch (err) {
    console.error("COMMAND ERROR:", err);
    reply = "Something went wrong.";
  }

  /* ---------- EPISODIC STORE (CONVERSATION ONLY) ---------- */

  const conversational =
    intentObj.intent === "GENERAL_QUESTION" ||
    intentObj.intent === "SMALLTALK" ||
    intentObj.intent === "CODING_QUERY" ||
    intentObj.intent === "MATH_QUERY";

  if (conversational && !skipEpisodic) {
    const themedKey = extractKey(cleanRawText);
    await episodicMemory.store({
      type: "conversation",
      subject: "user",
      // 🚫 "general" is noise — never let it become a dominant theme key
      key: themedKey !== "general" ? themedKey : null,
      value: cleanRawText,
      source: "user",
      importance: emotional ? 0.75 : 0.6
    });
  }

  /* ---------- PERSONALITY ---------- */

  if (!skipPersonality && !handledByUnifiedCore) {
    reply = await applyPersonality(reply);
  }

  /* ---------- CHAT HISTORY ---------- */
  
  let historyText = reply;
  if (reply && typeof reply === 'object') {
    if (reply.type === 'QUICK_ANSWER') {
      historyText = reply.answer;
    } else if (reply.type === 'DEEP_RESEARCH_REPORT' || reply.type === 'RESEARCH_REPORT' || reply.type === 'REPORT_GENERATION_AND_SAVE') {
      historyText = `[Deep Research Report Generated: ${reply.title || 'Untitled'}]\n${reply.summary || ''}`;
    } else {
      historyText = "[Complex Object Response]";
    }
  }

  chatHistory.addMessage("arvsal", historyText);
  if (["CONFIRM_YES", "CONFIRM_NO"].includes(intentObj.intent)) {
    skipEpisodic = true;
  }

  /* ---------- EPISODIC STORE (ASSISTANT) ---------- */

  if (conversational && !skipEpisodic) {
    await episodicMemory.store({
      type: "response",
      subject: "arvsal",
      value: historyText,
      source: "system",
      importance: 0.5
    });
  }

  /* ---------- REFLECTION (FIRE-AND-FORGET) ---------- */

  // 🔥 NEVER await — Mistral runs in background, response is immediate
  setImmediate(() => maybeRunReflection("user").catch(() => { }));

  /* ---------- COGNITIVE STATE UPDATE (PHASE 1) ---------- */

  try {
    // Extract simple topics from intent for snapshot tracking
    const _turnTopics = [];
    if (intentObj.key   && intentObj.key   !== 'general') _turnTopics.push(intentObj.key);
    if (intentObj.subject && !['user','arvsal','assistant'].includes(intentObj.subject)) _turnTopics.push(intentObj.subject);

    cognitiveSnapshot.updateFromTurn({
      snapshot: _cognitiveSnapshot,
      intent:   intentObj.intent,
      topics:   _turnTopics
    });
  } catch { }

  res.json({ reply });
});


/* ================= START ================= */

const ramIndexer = require('@core/cognitive/ucml/RAMIndexer');

app.listen(3000, async () => {
  console.log("Arvsal backend running on http://localhost:3000");
  
  // Phase-0: Initialize UCML RAM Indexer asynchronously so we don't block server boot
  await ramIndexer.initialize().catch(err => {
    console.error("[UCML] Boot-time indexer failed:", err.message);
  });
});

/* ================= COGNITIVE SHUTDOWN SAVE ================= */

function _saveCognitiveState() {
  try {
    cognitiveSnapshot.mergeWorkingMemory(_cognitiveSnapshot, workingMemory.getSnapshotData());
    cognitiveSnapshot.save(_cognitiveSnapshot);
    console.log('[CognitiveSnapshot] Saved on shutdown.');
  } catch { }
}

process.on("exit",            () => { _saveCognitiveState(); });
process.on("SIGINT",          () => { _saveCognitiveState(); process.exit(0); });
process.on("SIGTERM",         () => { _saveCognitiveState(); process.exit(0); });
process.on("uncaughtException", (err) => { console.error('[UncaughtException]', err); _saveCognitiveState(); process.exit(1); });


/* ================= WHATSAPP AUTOMATION ================= */

startWhatsApp(async (msg) => {

  const number = msg.from;
  const text = msg.body;

  // 🔒 SELF CONTROL CHANNEL
  if (number === "919699621635@c.us" && text.startsWith("@arvsal")) {
    console.log("CONTROL CHANNEL TRIGGERED:MESSAGE FROM WHATSAPP");
    const command = text.replace("@arvsal", "").trim();

    const response = await axios.post(
      "http://localhost:3000/command",
      { message: command },
      {
        headers: {
          "x-source": "whatsapp"
        }
      }
    );

    await sendMessage(number, response.data.reply);
    return;
  }

  // 🤖 BUSY MODE AUTO-REPLY
  if (isBusy() && isVIP(number)) {

    addMissed(number, text);

    if (!canAutoReply(number)) {
      return; // 🔒 skip auto reply if in cooldown
    }

    const state = getBusyState();

    const freeTime = new Date(state.freeAt);

    const relativeMinutes = Math.max(
      0,
      Math.round((freeTime.getTime() - Date.now()) / 60000)
    );

    const prompt = `
Atharv is currently in ${state.type}.
He will be free at ${freeTime.toLocaleTimeString()} 
(which is about ${relativeMinutes} minutes from now).

Write a short polite and humanly WhatsApp reply in third person,DO NOT use any other names despite of Atharv and Arvsal.
Add at bottom:

- Arvsal, AI assistant of Atharv
`;

    const aiReply = await runLLM({
      model: "llama3",
      prompt,
      timeout: 15000
    });

    // Human-like delay
    await new Promise(r => setTimeout(r, 4000 + Math.random() * 4000));

    await sendMessage(number, aiReply);

    return;
  }

});

/* ================= TELEGRAM LISTENER ================= */

async function startTelegramListener() {
  console.log("📡 Telegram listener started...");

  let offset = 0;
  // 🔥 Declared outside the loop so it remembers your progress
  let userState = {};

  while (true) {
    try {
      const updates = await fetchUpdates(offset);

      for (const update of updates) {
        offset = update.update_id + 1;

        const messageObj = update?.message;
        if (!messageObj) continue;

        const chatId = messageObj.chat?.id;

        // 🔒 THE GATEKEEPER: Strictly only for your Telegram ID
        if (String(chatId) !== process.env.TELEGRAM_CHAT_ID) {
          console.log(`⚠️ Blocked unauthorized access from: ${chatId}`);
          continue;
        }

        /* ================= 1. TEXT MESSAGE HANDLING ================= */

        if (messageObj.text) {
          const raw = messageObj.text.trim();

          // A. PDF Start Trigger
          if (raw.toLowerCase() === "@arvsal start pdf") {
            userState[chatId] = { mode: "PDF", step: "COLLECTING" };
            conversionEngine.startSession(chatId);
            await sendTelegramMessage("📥 A-Eye Batch Mode: ON. Send your mixed files. Type '@arvsal finish' when done.");
            continue;
          }

          // B. Naming Step (The Final Hook)
          if (userState[chatId]?.step === "NAMING") {
            const pdfName = raw.replace("@arvsal", "").trim();
            await sendTelegramMessage(`⚙️ Finalizing ${pdfName}.pdf...`);

            try {
              const finalPath = await conversionEngine.finalize(chatId, pdfName);
              await sendTelegramDocument(finalPath);
              setTimeout(() => safeDelete(finalPath), 1500);
              delete userState[chatId];
              await sendTelegramMessage("✅ Project complete. Workspace purged.");
            } catch (err) {
              await sendTelegramMessage("❌ Engine Error: " + err.message);
            }
            continue; // 🔥 USE CONTINUE INSTEAD OF RETURN
          }



          // C. PDF Finish Trigger
          if (raw.toLowerCase() === "@arvsal finish") {
            if (userState[chatId]) {
              userState[chatId].step = "NAMING";
              await sendTelegramMessage("📝 What shall we name this PDF, sir?");
            } else {
              await sendTelegramMessage("🚫 No active batch session found.");
            }
            continue;
          }

          /* --- STANDARD COMMANDS (ONLY IF NO BATCH TRIGGERED) --- */
          if (!raw.toLowerCase().startsWith("@arvsal")) continue;

          const message = raw.replace(/^@arvsal/i, "").trim();
          console.log("📩 Telegram (validated):", message);

          const response = await axios.post(
            "http://localhost:3000/command",
            { message },
            { headers: { "x-source": "telegram" } }
          );

          await sendTelegramMessage(response.data.reply);
        }

        /* ================= 2. FILE/PHOTO HANDLING ================= */

        else if (messageObj.document || messageObj.photo) {
          let fileId = null;
          let fileName = null;

          if (messageObj.document) {
            fileId = messageObj.document.file_id;
            fileName = messageObj.document.file_name;
          } else if (messageObj.photo) {
            // Get highest resolution
            fileId = messageObj.photo[messageObj.photo.length - 1].file_id;
            fileName = `arvsal_img_${Date.now()}.jpg`;
          }

          if (fileId) {
            if (userState[chatId]?.step === "COLLECTING") {
              const fileBuffer = await downloadTelegramFileToBuffer(fileId);
              if (fileBuffer) {
                // 🔥 CHANGE: Pass messageObj.message_id as the 4th argument
                await conversionEngine.addFile(chatId, fileName, fileBuffer, messageObj.message_id);
                console.log(`📎 Added to batch (ID: ${messageObj.message_id}): ${fileName}`);
              } else {
                await sendTelegramMessage(`⚠️ Failed to download ${fileName}. Skipping.`);
              }
            }
          }

        }
      }

    } catch (err) {
      console.log("Telegram listener error:", err.message);
      await new Promise(r => setTimeout(r, 3000));
    }
  }
}


startTelegramListener();