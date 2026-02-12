import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import datetime
import os
import json
import re

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("DISCORD_TOKEN")
ADMIN_ID = 1392851942480412822

LOGO_GIF = "https://cdn.discordapp.com/attachments/1468621028598087843/1471249375706746890/Black_White_Minimalist_Animation_Logo_Video_1.gif"
DATA_FILE = "roles.json"
MEMBER_DAYS = 30          # สมัคร 30 วัน
UPDATE_INTERVAL = 10      # อัปเดต embed ทุก 10 วินาที
WARN_BEFORE_DAYS = 3      # แจ้งเตือนก่อนหมด 3 วัน

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# DATABASE
# =========================
def load_data():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except:
        pass
    return []

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# =========================
# UTILS
# =========================
def parse_register_date(date_str):
    # DD/MM/YY (พ.ศ.)
    d, m, y = map(int, date_str.split("/"))
    y = y + 2500 if y < 2500 else y
    return datetime.datetime(y - 543, m, d, 0, 0, 0)

def thai_date(dt):
    months = ["มกราคม","กุมภาพันธ์","มีนาคม","เมษายน","พฤษภาคม","มิถุนายน",
              "กรกฎาคม","สิงหาคม","กันยายน","ตุลาคม","พฤศจิกายน","ธันวาคม"]
    year = dt.year + 543
    return f"{dt.day} {months[dt.month-1]} {year}"

def format_digital(seconds):
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}"

def progress_bar(percent, tick):
    total = 20
    filled = int(total * percent)
    bar = ["🟩" if i < filled else "⬛" for i in range(total)]
    bar[tick % total] = "⚡"
    return "".join(bar)

# =========================
# EMBED
# =========================
def build_embed(member, role, register_date, expire_date, remaining_seconds, tick):
    total_seconds = MEMBER_DAYS * 86400
    percent = remaining_seconds / total_seconds

    embed = discord.Embed(
        title="📅 Check Member Time",
        color=0x3EF2C5 if percent > 0.5 else 0xFFD93D if percent > 0.15 else 0xFF3B3B
    )

    embed.add_field(
        name="👤 สมาชิก",
        value=f"{member.mention}",
        inline=False
    )

    embed.add_field(
        name="🏷 Member",
        value=f"{role.mention} | {MEMBER_DAYS} วัน",
        inline=False
    )

    embed.add_field(
        name="📌 วันที่ลงทะเบียน",
        value=thai_date(register_date),
        inline=False
    )

    embed.add_field(
        name="⏳ วันหมดอายุ",
        value=f"{thai_date(expire_date)}\n<t:{int(expire_date.timestamp())}:R>",
        inline=False
    )

    embed.add_field(
        name="🕒 นับเวลาถอยหลัง",
        value=f"```{format_digital(remaining_seconds)}```",
        inline=False
    )

    embed.add_field(
        name="📊 Progress",
        value=f"{progress_bar(percent, tick)}  {int(percent*100)}%",
        inline=False
    )

    embed.set_thumbnail(url=LOGO_GIF)
    embed.set_footer(text="👑 ADMINZENO • TIME MEMBER SYSTEM")

    return embed

# =========================
# TIMER SYSTEM
# =========================
async def role_timer(data: dict):
    if not isinstance(data, dict):
        return

    tick = 0
    warned_3days = data.get("warned_3days", False)

    guild = bot.get_guild(data["guild_id"])
    if not guild:
        return

    member = guild.get_member(data["member_id"])
    role = guild.get_role(data["role_id"])
    channel = guild.get_channel(data["channel_id"])

    if not member or not role or not channel:
        return

    try:
        message = await channel.fetch_message(data["message_id"])
    except:
        return

    admin = await bot.fetch_user(ADMIN_ID)

    register_date = datetime.datetime.fromisoformat(data["register_date"])
    expire_date = register_date + datetime.timedelta(days=MEMBER_DAYS)

    while True:
        now = datetime.datetime.now()
        remaining = (expire_date - now).total_seconds()

        # แจ้งเตือนก่อนหมด 3 วัน
        if not warned_3days and remaining <= WARN_BEFORE_DAYS * 86400 and remaining > 0:
            try:
                await member.send(f"🔔 แจ้งเตือน: สมาชิก {role.name} จะหมดอายุในอีก {WARN_BEFORE_DAYS} วัน")
                await admin.send(f"🔔 {member.name} ({role.name}) ใกล้หมดอายุ")
            except:
                pass

            data["warned_3days"] = True
            db = load_data()
            for r in db:
                if isinstance(r, dict) and r.get("message_id") == data["message_id"]:
                    r["warned_3days"] = True
            save_data(db)
            warned_3days = True

        # หมดอายุ
        if remaining <= 0:
            try:
                await member.remove_roles(role)
                expired = discord.Embed(
                    title="⛔ ROLE EXPIRED",
                    description=f"{member.mention} หมดอายุ {role.mention}",
                    color=0xFF0000
                )
                await message.edit(embed=expired)
                await member.send(f"⛔ Role {role.name} หมดอายุแล้ว")
                await admin.send(f"⛔ {member.name} หมดอายุ {role.name}")
            except:
                pass

            db = [r for r in load_data() if isinstance(r, dict) and r.get("message_id") != data["message_id"]]
            save_data(db)
            break

        embed = build_embed(member, role, register_date, expire_date, remaining, tick)
        await message.edit(embed=embed)

        tick += 1
        await asyncio.sleep(UPDATE_INTERVAL)

# =========================
# COMMAND
# =========================
@bot.tree.command(name="setmember", description="👑 สมัคร Member 30 วัน (กำหนดวันที่สมัครเอง)")
@app_commands.describe(
    member="สมาชิก",
    role="Role Member",
    register_date="วันที่สมัคร (DD/MM/YY)"
)
async def setmember(
    interaction: discord.Interaction,
    member: discord.Member,
    role: discord.Role,
    register_date: str
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin Only", ephemeral=True)
        return

    try:
        reg_date = parse_register_date(register_date)
    except:
        await interaction.response.send_message("❌ รูปแบบวันที่ผิด (DD/MM/YY)", ephemeral=True)
        return

    await member.add_roles(role)

    expire_date = reg_date + datetime.timedelta(days=MEMBER_DAYS)
    embed = build_embed(member, role, reg_date, expire_date, MEMBER_DAYS * 86400, 0)
    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()

    data = {
        "guild_id": interaction.guild.id,
        "member_id": member.id,
        "role_id": role.id,
        "channel_id": interaction.channel.id,
        "message_id": message.id,
        "register_date": reg_date.isoformat(),
        "warned_3days": False
    }

    db = load_data()
    db.append(data)
    save_data(db)

    bot.loop.create_task(role_timer(data))

# =========================
# READY
# =========================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print("👑 BOT ONLINE")

    for data in load_data():
        if isinstance(data, dict):
            bot.loop.create_task(role_timer(data))
        else:
            print("⚠️ Skip invalid data:", data)

bot.run(TOKEN)
