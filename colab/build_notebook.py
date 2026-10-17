"""Builds voice_ai_server.ipynb from server.py.

Edit server.py, then run:  python colab/build_notebook.py
"""

import json
from pathlib import Path

HERE = Path(__file__).parent


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)}


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text.strip("\n").splitlines(keepends=True),
    }


cells = [
    md("""
# เซิร์ฟเวอร์ AI สำหรับบอทคุยในห้องเสียง

โน้ตบุ๊กนี้เปิด AI ทั้งสามส่วนที่บอทต้องใช้ไว้บน Colab แล้วสร้างลิงก์ให้บอทเรียกใช้ได้

| ส่วน | ใช้อะไร |
| --- | --- |
| ฟังเสียง → ข้อความ | faster-whisper (รันบน GPU ของ Colab) |
| คิดคำตอบ | Typhoon 2.5 ผ่าน Ollama (รันบน GPU ของ Colab) |
| ข้อความ → เสียงพูด | edge-tts เสียงภาษาไทยของ Microsoft (ส่งข้อความไปเซิร์ฟเวอร์ Microsoft) |

**วิธีใช้**
1. เมนู **Runtime → Change runtime type** เลือก GPU (T4 ก็พอ)
2. เมนู **Runtime → Run all** แล้วรอจนเซลล์สุดท้ายพิมพ์สองบรรทัด `OPENAI_BASE_URL=...` และ `OPENAI_API_KEY=...`
3. คัดลอกสองบรรทัดนั้นไปแทนที่ในไฟล์ `.env` ของบอท แล้วรันบอทใหม่
4. เล่นเสร็จแล้วเลือก **Runtime → Disconnect and delete runtime** เพื่อหยุดใช้หน่วยประมวลผล

ลิงก์จะเปลี่ยนทุกครั้งที่เปิดโน้ตบุ๊กใหม่ ถ้าตั้ง `API_KEY` ไว้คงที่ จะต้องแก้แค่ `OPENAI_BASE_URL`

> ข้อควรระวัง: ข้อตกลงของ Colab ห้ามใช้ runtime เปิดเป็นบริการเว็บ การใช้แบบนี้มีความเสี่ยงที่ runtime จะถูกตัดหรือบัญชีถูกจำกัด
"""),
    md("## 1. ตั้งค่า"),
    code("""
# โมเดลคิดคำตอบ (ชื่อที่ Ollama ดึงได้) ตัวเริ่มต้นเล็กพอสำหรับ T4
# ถ้าใช้ GPU L4 หรือ A100 ลองตัวใหญ่ที่ฉลาดกว่า: "hf.co/typhoon-ai/typhoon2.5-qwen3-30b-a3b-gguf:Q4_K_M"
LLM_MODEL = "hf.co/typhoon-ai/typhoon2.5-qwen3-4b-gguf"

# โมเดลฟังเสียง: "large-v3" แม่นสุด, "large-v3-turbo" เร็วกว่าแต่ภาษาไทยพลาดบ่อยกว่า
WHISPER_MODEL = "large-v3"
STT_LANGUAGE = "th"

# เสียงพูด: "th-TH-PremwadeeNeural" (ผู้หญิง) หรือ "th-TH-NiwatNeural" (ผู้ชาย)
TTS_VOICE = "th-TH-PremwadeeNeural"

# รหัสผ่านที่บอทใช้เรียกเซิร์ฟเวอร์นี้ เว้นว่างไว้เพื่อสุ่มใหม่ทุกครั้ง
API_KEY = ""

import secrets
API_KEY = API_KEY or secrets.token_urlsafe(24)
"""),
    md("## 2. ติดตั้งโปรแกรม"),
    code("""
!curl -fsSL https://ollama.com/install.sh | sh > /dev/null
!pip install -q faster-whisper edge-tts fastapi uvicorn httpx python-multipart
!wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared && chmod +x cloudflared
"""),
    md("## 3. เปิด Ollama และดาวน์โหลดโมเดลคิดคำตอบ"),
    code("""
import subprocess, time, urllib.request

ollama_proc = subprocess.Popen(["ollama", "serve"], stdout=open("ollama.log", "w"), stderr=subprocess.STDOUT)
for _ in range(60):
    try:
        urllib.request.urlopen("http://127.0.0.1:11434")
        break
    except Exception:
        time.sleep(1)
else:
    raise RuntimeError("Ollama ไม่ยอมเปิด ดู ollama.log")

!ollama pull {LLM_MODEL}
"""),
    md("## 4. โค้ดเซิร์ฟเวอร์"),
    code("%%writefile server.py\n" + (HERE / "server.py").read_text(encoding="utf-8")),
    md("## 5. เปิดเซิร์ฟเวอร์\n\nครั้งแรกต้องดาวน์โหลดโมเดลฟังเสียงด้วย อาจใช้เวลาสักครู่"),
    code("""
import os, glob

# faster-whisper ต้องหาไลบรารี cuDNN/cuBLAS ที่มากับ PyTorch ให้เจอ
lib_dirs = glob.glob("/usr/local/lib/python3*/dist-packages/nvidia/*/lib")
env = {
    **os.environ,
    "LD_LIBRARY_PATH": ":".join(lib_dirs + [os.environ.get("LD_LIBRARY_PATH", "")]),
    "API_KEY": API_KEY,
    "LLM_MODEL": LLM_MODEL,
    "WHISPER_MODEL": WHISPER_MODEL,
    "STT_LANGUAGE": STT_LANGUAGE,
    "TTS_VOICE": TTS_VOICE,
}
server_proc = subprocess.Popen(
    ["python", "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8000"],
    env=env, stdout=open("server.log", "w"), stderr=subprocess.STDOUT,
)
for _ in range(600):
    if server_proc.poll() is not None:
        print(open("server.log").read())
        raise RuntimeError("เซิร์ฟเวอร์ปิดตัวเอง ดูข้อความด้านบน")
    try:
        print(urllib.request.urlopen("http://127.0.0.1:8000/health").read().decode())
        break
    except Exception:
        time.sleep(1)
else:
    raise RuntimeError("รอเซิร์ฟเวอร์นานเกินไป ดู server.log")
"""),
    md("## 6. ทดสอบในเครื่อง\n\nสร้างเสียงพูดภาษาไทย แล้วให้ระบบฟังกลับเป็นข้อความ และถามโมเดลหนึ่งคำถาม"),
    code("""
import json, urllib.request, uuid

def call(path, data, content_type):
    req = urllib.request.Request(f"http://127.0.0.1:8000/v1{path}", data=data, headers={
        "Authorization": f"Bearer {API_KEY}", "Content-Type": content_type})
    return urllib.request.urlopen(req, timeout=300).read()

mp3 = call("/audio/speech", json.dumps({"input": "สวัสดีครับ วันนี้อากาศดีมาก"}).encode(), "application/json")
print("TTS ได้ไฟล์เสียง", len(mp3), "ไบต์")

boundary = uuid.uuid4().hex
form = (f"--{boundary}\\r\\nContent-Disposition: form-data; name=\\"file\\"; filename=\\"t.mp3\\"\\r\\n"
        f"Content-Type: audio/mpeg\\r\\n\\r\\n").encode() + mp3 + f"\\r\\n--{boundary}--\\r\\n".encode()
print("STT:", json.loads(call("/audio/transcriptions", form, f"multipart/form-data; boundary={boundary}"))["text"])

reply = json.loads(call("/chat/completions", json.dumps(
    {"messages": [{"role": "user", "content": "แนะนำตัวสั้นๆ หน่อย"}]}).encode(), "application/json"))
print("LLM:", reply["choices"][0]["message"]["content"])
"""),
    md("## 7. เปิดลิงก์ให้บอทเข้ามาได้\n\nคัดลอกสองบรรทัดที่พิมพ์ออกมาไปใส่ใน `.env` ของบอท"),
    code("""
import re

tunnel_proc = subprocess.Popen(["./cloudflared", "tunnel", "--url", "http://127.0.0.1:8000"],
                               stdout=open("tunnel.log", "w"), stderr=subprocess.STDOUT)
url = None
for _ in range(60):
    match = re.search(r"https://[-a-z0-9]+\\.trycloudflare\\.com", open("tunnel.log").read())
    if match:
        url = match.group(0)
        break
    time.sleep(1)
if not url:
    raise RuntimeError("สร้างลิงก์ไม่สำเร็จ ดู tunnel.log")

# ลิงก์ใหม่ใช้เวลาสักพักกว่าจะเข้าได้
for _ in range(30):
    try:
        urllib.request.urlopen(f"{url}/health", timeout=10)
        break
    except Exception:
        time.sleep(2)

print("ใส่สองบรรทัดนี้ในไฟล์ .env ของบอท:\\n")
print(f"OPENAI_BASE_URL={url}/v1")
print(f"OPENAI_API_KEY={API_KEY}")
"""),
    md("## ดูบันทึกการทำงาน\n\nรันเซลล์นี้เมื่อบอทมีปัญหา เพื่อดูว่าเซิร์ฟเวอร์ได้รับคำขออะไรบ้าง"),
    code("!tail -n 30 server.log"),
]

notebook = {
    "cells": cells,
    "metadata": {
        "accelerator": "GPU",
        "colab": {"gpuType": "T4", "provenance": []},
        "kernelspec": {"display_name": "Python 3", "name": "python3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 0,
}

(HERE / "voice_ai_server.ipynb").write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("wrote", HERE / "voice_ai_server.ipynb")
