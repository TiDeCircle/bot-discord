import os
import random

import discord
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")


class MyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # Sync to one guild for instant updates while developing; global sync can take a while.
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()


bot = MyBot()


@bot.event
async def on_ready():
    print(f"ล็อกอินเป็น {bot.user} (ID: {bot.user.id})")


@bot.tree.command(name="ping", description="เช็กว่าบอทยังอยู่ไหม")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! {round(bot.latency * 1000)} ms")


@bot.tree.command(name="hello", description="ทักทาย")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message(f"สวัสดี {interaction.user.mention} 👋")


@bot.tree.command(name="roll", description="ทอยลูกเต๋า")
@app_commands.describe(sides="จำนวนหน้าของลูกเต๋า (ค่าเริ่มต้น 6)")
async def roll(interaction: discord.Interaction, sides: app_commands.Range[int, 2, 1000] = 6):
    await interaction.response.send_message(f"🎲 ได้ **{random.randint(1, sides)}** (1-{sides})")


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("ไม่พบ DISCORD_TOKEN — คัดลอก .env.example เป็น .env แล้วใส่โทเคน")
    bot.run(TOKEN)
