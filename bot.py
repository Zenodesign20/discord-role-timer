import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import datetime
import re
import os
import json

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("DISCORD_TOKEN")
ADMIN_ID = 1392851942480412822
DATA_FILE = "roles.json"

LOGO_URL = (
    "https://cdn.discordapp.com/attachments/1468621028598087843/"
    "1471249375706746890/Black_White_Minimalist_Animation_Logo_Video_1.gif"
)

# =========================
# BOT SETUP
# =========================
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# DATABASE
# =========================
def load_data():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# =========================
# TIME PARSER
# =========================
def parse_time(time_str):
    match = re.match(r"(\d+)([mhd])", time_str.lower())
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2)
    if unit == "m":
        return value * 60
    if unit == "h":
        return value * 3600
    if unit == "d":
        return value * 86400

# =========================
# TIME FORMAT
# =========================
def format_digital(seconds):
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}"

def thai_date(dt):
    months = [
        "มกราคม","กุมภาพันธ์","มีนาคม","เมษายน","พฤษภาคม","มิถุนายน",
        "กรกฎาคม","สิงหาคม","กันยายน","ตุลาคม","พฤศจิกายน","ธันวาคม"
    ]
    year = dt.year + 543
    return f"{dt.day} {months[dt.month-1]} {year} {dt.strftime('%H:%M')}"

# =========================
# COLOR SYSTEM
# =========================
def get_color(percent):
    if percent <= 0.15:
        return 0xFF3B3B
    elif percent <= 0.5:
        return 0xFFD93D
    else:
        return 0x3EF2C5

# =========================
# PROGRESS BAR
# =========================
def progress_bar(percent, tick):
    total = 20
    filled = int(total * percent)
    bar = []
    for i in range(total):
        bar.append("🟩" if i < filled else "⬛")
    bar[tick % total] = "⚡"
    return "".join(bar)

# =========================
# EMBED BUILDER
# =========================
def build_embed(member, role, register_date, expire_time, remaining, total, tick):
    percent = remaining / total if total > 0 else 0
    days_left = max(0, int(remaining // 86400))

    embed = discord.Embed(
        title="📅 Check member time!",
        description="Zeno Community • Time Member System",
        color=get_color(percent)
    )

    embed.set_thumbnail(url=LOGO_URL)

    embed.add_field(name="👤 สมาชิก", value=member.mention, inline=False)
    embed.add_field(name="🏷 Member Package", value=role.mention, inline=False)

    embed.add_field(
        name="🗓 วันที่ลงทะเบียน",
        value=register_date.strftime("%d/%m/%y"),
        inline=True
    )

    embed.add_field(
        name="⏳ วันหมดอายุ",
        value=f"{thai_date(expire_time)}\nเหลืออีก **{days_left} วัน**",
        inline=True
    )

    embed.add_field(
        name="🕒 Countdown",
        value=f"```{format_digital(remaining)}```",
        inline=False
    )

    embed.add_field(
        name="📊 Progress",
        value=f"{progress_bar(percent, tick)}  {int(percent*100)}%",
        inline=False
    )

    embed.set_footer(
        text="👑 ADMINZENO • GOD MODE",
        icon_url=LOGO_URL
    )

    return embed

# =========================
# TIMER SYSTEM
# =========================
async def role_timer(data):
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

    message = await channel.fetch_message(data["message_id"])
    admin_user = await bot.fetch_user(ADMIN_ID)

    register_date = datetime.datetime.fromisoformat(data["register"])
    expire_time = datetime.datetime.fromisoformat(data["expire"])
    total = data["total"]

    while True:
        now = datetime.datetime.now()
        remaining = (expire_time - now).total_seconds()

        # 🔔 แจ้งเตือนก่อนหมด 3 วัน
        if remaining <= 3 * 86400 and remaining > 0 and not warned_3days:
            try:
                await member.send(f"🔔 Role **{role.name}** จะหมดอายุในอีก 3 วัน")
                await admin_user.send(f"⚠️ {member.name} ใกล้หมดอายุ Role {role.name}")
            except:
                pass

            data["warned_3days"] = True
            db = load_data()
            for r in db:
                if r["message_id"] == data["message_id"]:
                    r["warned_3days"] = True
            save_data(db)
            warned_3days = True

        # ⛔ หมดอายุ
        if remaining <= 0:
            try:
                await member.remove_roles(role)

                expired = discord.Embed(
                    title="⛔ ROLE EXPIRED",
                    description=f"{member.mention} หมดอายุ {role.mention}",
                    color=0xFF0000
                )
                expired.set_thumbnail(url=LOGO_URL)
                expired.set_footer(
                    text="👑 ADMINZENO • GOD MODE",
                    icon_url=LOGO_URL
                )

                await message.edit(embed=expired)
                await member.send(f"⛔ Role {role.name} หมดอายุแล้ว")
                await admin_user.send(f"⛔ {member.name} หมดเวลา {role.name}")
            except:
                pass

            db = load_data()
            db = [r for r in db if r["message_id"] != data["message_id"]]
            save_data(db)
            break

        embed = build_embed(
            member, role, register_date, expire_time, remaining, total, tick
        )
        await message.edit(embed=embed)

        tick += 1
        await asyncio.sleep(10)

# =========================
# SLASH COMMAND
# =========================
@bot.tree.command(name="setrole", description="👑 ตั้ง Role พร้อมจับเวลา")
@app_commands.describe(
    member="สมาชิก",
    role="Role",
    duration="30m / 1h / 7d",
    register_date="วันที่สมัคร (DD/MM/YY)"
)
async def setrole(interaction: discord.Interaction, member: discord.Member,
                  role: discord.Role, duration: str, register_date: str):

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin Only", ephemeral=True)
        return

    seconds = parse_time(duration)
    if not seconds:
        await interaction.response.send_message("❌ รูปแบบเวลาไม่ถูกต้อง", ephemeral=True)
        return

    try:
        reg_date = datetime.datetime.strptime(register_date, "%d/%m/%y")
    except:
        await interaction.response.send_message("❌ วันที่ต้องเป็น DD/MM/YY", ephemeral=True)
        return

    expire_time = reg_date + datetime.timedelta(seconds=seconds)

    await member.add_roles(role)

    embed = build_embed(
        member, role, reg_date, expire_time, seconds, seconds, 0
    )
    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()

    data = {
        "guild_id": interaction.guild.id,
        "member_id": member.id,
        "role_id": role.id,
        "channel_id": interaction.channel.id,
        "message_id": message.id,
        "register": reg_date.isoformat(),
        "expire": expire_time.isoformat(),
        "total": seconds,
        "warned_3days": False
    }

    db = load_data()
    db.append(data)
    save_data(db)

    admin_user = await bot.fetch_user(ADMIN_ID)
    try:
        await member.send(f"✅ คุณได้รับ Role {role.name}")
        await admin_user.send(f"👑 เพิ่ม Role {role.name} ให้ {member.name}")
    except:
        pass

    bot.loop.create_task(role_timer(data))

# =========================
# READY
# =========================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print("👑 BOT ONLINE")
    for data in load_data():
        bot.loop.create_task(role_timer(data))

bot.run(TOKEN)
