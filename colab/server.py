"""OpenAI-compatible voice AI server for the Discord bot.

Serves the three endpoints the bot calls, so the bot only needs
OPENAI_BASE_URL and OPENAI_API_KEY pointed here:

  POST /v1/audio/transcriptions  speech -> text   (faster-whisper)
  POST /v1/chat/completions      reply            (proxied to Ollama)
  POST /v1/audio/speech          text -> mp3      (edge-tts)

Every /v1 request must carry "Authorization: Bearer <API_KEY>".
"""

import asyncio
import json
import os
import secrets
import tempfile
from contextlib import asynccontextmanager

import edge_tts
import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from faster_whisper import WhisperModel

API_KEY = os.environ["API_KEY"]
LLM_MODEL = os.environ["LLM_MODEL"]
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large-v3")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE = os.getenv("WHISPER_COMPUTE", "float16")
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "th")
TTS_VOICE = os.getenv("TTS_VOICE", "th-TH-PremwadeeNeural")

whisper: WhisperModel | None = None
whisper_lock = asyncio.Lock()  # one transcription at a time on the GPU


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global whisper
    # Load at startup so a bad model name or missing CUDA fails before the tunnel opens.
    whisper = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE)
    yield


app = FastAPI(lifespan=lifespan)


def require_key(request: Request) -> None:
    given = request.headers.get("authorization", "")
    if not secrets.compare_digest(given.encode(), f"Bearer {API_KEY}".encode()):
        raise HTTPException(status_code=401, detail="invalid API key")


@app.get("/health")
async def health():
    return {"ok": True, "llm": LLM_MODEL, "whisper": WHISPER_MODEL, "voice": TTS_VOICE}


# ---- Speech to text ----
@app.post("/v1/audio/transcriptions", dependencies=[Depends(require_key)])
async def transcriptions(
    file: UploadFile = File(...),
    model: str = Form("whisper-1"),  # accepted for compatibility; WHISPER_MODEL is used
    language: str | None = Form(None),
):
    suffix = os.path.splitext(file.filename or "")[1] or ".mp3"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        path = tmp.name
    try:
        async with whisper_lock:
            text = await asyncio.to_thread(_transcribe, path, language or STT_LANGUAGE)
    finally:
        os.unlink(path)
    return {"text": text}


def _transcribe(path: str, language: str) -> str:
    # The VAD filter drops silence, which is where Whisper invents phrases like "thanks for watching".
    segments, _info = whisper.transcribe(path, language=language, beam_size=5, vad_filter=True)
    return "".join(s.text for s in segments).strip()


# ---- Text to speech ----
@app.post("/v1/audio/speech", dependencies=[Depends(require_key)])
async def speech(request: Request):
    body = await request.json()
    text = (body.get("input") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="input is empty")
    # The bot sends OpenAI voice names like "alloy"; only Edge voice names ("...Neural") are used as-is.
    voice = body.get("voice") or ""
    if "Neural" not in voice:
        voice = TTS_VOICE
    audio = bytearray()
    async for chunk in edge_tts.Communicate(text, voice).stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
    return Response(content=bytes(audio), media_type="audio/mpeg")


# ---- Chat ----
class ThinkStripper:
    """Removes <think>...</think> blocks from streamed text, even when a tag is split across chunks."""

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self):
        self.buf = ""
        self.inside = False

    def feed(self, text: str) -> str:
        self.buf += text
        out = []
        while True:
            tag = self.CLOSE if self.inside else self.OPEN
            i = self.buf.find(tag)
            if i >= 0:
                if not self.inside:
                    out.append(self.buf[:i])
                self.buf = self.buf[i + len(tag):]
                self.inside = not self.inside
                continue
            # Hold back a trailing fragment that could be the start of the tag.
            keep = next((k for k in range(min(len(tag) - 1, len(self.buf)), 0, -1) if tag.startswith(self.buf[-k:])), 0)
            if not self.inside:
                out.append(self.buf[: len(self.buf) - keep])
            self.buf = self.buf[len(self.buf) - keep:]
            return "".join(out)

    def flush(self) -> str:
        rest = "" if self.inside else self.buf
        self.buf = ""
        return rest


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/v1/chat/completions", dependencies=[Depends(require_key)])
async def chat(request: Request):
    body = await request.json()
    body["model"] = LLM_MODEL  # whatever OPENAI_MODEL the bot sends, use the model Ollama has loaded
    url = f"{OLLAMA_URL}/v1/chat/completions"

    if not body.get("stream"):
        async with httpx.AsyncClient(timeout=300) as client:
            res = await client.post(url, json=body)
        if res.status_code != 200:
            return JSONResponse(status_code=502, content={"error": res.text})
        data = res.json()
        for choice in data.get("choices", []):
            msg = choice.get("message") or {}
            if isinstance(msg.get("content"), str):
                stripper = ThinkStripper()
                msg["content"] = (stripper.feed(msg["content"]) + stripper.flush()).strip()
        return data

    async def relay():
        stripper = ThinkStripper()
        last = None
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream("POST", url, json=body) as res:
                if res.status_code != 200:
                    error = (await res.aread()).decode(errors="replace")
                    yield _sse({"error": {"message": f"Ollama returned {res.status_code}: {error}"}})
                    return
                async for line in res.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    last = chunk
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta") or {}
                        delta.pop("reasoning", None)
                        if isinstance(delta.get("content"), str):
                            delta["content"] = stripper.feed(delta["content"])
                    yield _sse(chunk)
        rest = stripper.flush()
        if rest and last:
            yield _sse({**last, "choices": [{"index": 0, "delta": {"content": rest}, "finish_reason": None}]})
        yield "data: [DONE]\n\n"

    return StreamingResponse(relay(), media_type="text/event-stream")
