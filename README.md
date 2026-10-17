# bot-discord

บอท Discord เขียนด้วย Python ([discord.py](https://discordpy.readthedocs.io/)) ใช้คำสั่งแบบ slash

## คำสั่ง

| คำสั่ง | ทำอะไร |
| --- | --- |
| `/ping` | เช็กว่าบอทออนไลน์ และแสดงค่า latency |
| `/hello` | ทักทายผู้ใช้ |
| `/roll [sides]` | ทอยลูกเต๋า (ค่าเริ่มต้น 6 หน้า) |

## วิธีรัน

1. สร้างบอทที่ https://discord.com/developers/applications แล้วคัดลอกโทเคนจากแท็บ **Bot**
2. เชิญบอทเข้าเซิร์ฟเวอร์ผ่าน **OAuth2 → URL Generator** (ติ๊ก `bot` และ `applications.commands`)
3. ติดตั้งและรัน:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # แล้วใส่ DISCORD_TOKEN
python bot.py
```

ใส่ `GUILD_ID` ใน `.env` ระหว่างพัฒนา เพื่อให้คำสั่ง slash ขึ้นในเซิร์ฟเวอร์นั้นทันที
