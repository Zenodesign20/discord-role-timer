import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import datetime
import json
import os
import re

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("DISCORD_TOKEN")  # หรือใส่ Token ตรง ๆ
ADMIN_ID = 1392851942480412822
DATA_FILE = "roles.json"
LOGO_URL = "https://cdn.phototourl.com/uploads/2026-02-11-5a3eeb2d-d2bf-4821-9742-bdcf3c4d9540.gif"

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
# TIME PARSER (30m / 1h / 7d)
# =========================
def parse_duration(text):
    match = re.fullmatch(r"(\d+)([mhd])", text.lower())
    if not match:
        return None
    value, unit = match.groups()
    value = int(value)
    return {"m": value*60, "h": value*3600, "d": value*86400}[unit]

# =========================
# DIGITAL TIME
# =========================
def digital_time(seconds):
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}"

# =========================
# THAI DATE
# =========================
def thai_date(dt):
    months = [
        "มกราคม","กุมภาพันธ์","มีนาคม","เมษายน","พฤษภาคม","มิถุนายน",
        "กรกฎาคม","สิงหาคม","กันยายน","ตุลาคม","พฤศจิกายน","ธันวาคม"
    ]
    days = ["จันทร์","อังคาร","พุธ","พฤหัสบดี","ศุกร์","เสาร์","อาทิตย์"]
    return f"วัน{days[dt.weekday()]}ที่ {dt.day} {months[dt.month-1]} {dt.year+543} {dt.strftime('%H:%M')}"

# =========================
# COLOR SYSTEM
# =========================
def progress_color(percent):
    if percent <= 0.15:
        return 0xFF3B3B
    elif percent <= 0.5:
        return 0xFFD93D
    return 0x3EF2C5

# =========================
# GOD BAR
# =========================
def god_bar(percent, tick):
    total = 20
    filled = int(total * percent)
    bar = []
    for i in range(total):
        if i < filled:
            bar.append("🟥" if percent <= 0.15 else "🟨" if percent <= 0.5 else "🟩")
        else:
            bar.append("⬛")
    bar[tick % total] = "⚡"
    return "".join(bar)

# =========================
# EMBED BUILDER
# =========================
def build_embed(member, role, expire, remaining, total, note, tick):
    percent = remaining / total
    embed = discord.Embed(
        title="📅 Check member time!",
        description="Welcome to Zeno Community Mod\nTime Member",
        color=progress_color(percent)
    )
    embed.add_field(name="👤 สมาชิก", value=member.mention, inline=False)
    embed.add_field(name="🏷 Role", value=role.mention, inline=False)
    embed.add_field(name="📝 Status", value=note, inline=False)
    embed.add_field(name="⏳ วันหมดอายุ", value=thai_date(expire), inline=False)
    embed.add_field(
        name="🕹 DIGITAL COUNTDOWN",
        value=f"```{digital_time(remaining)}```",
        inline=False
    )
    embed.add_field(
        name="📊 GOD PROGRESS",
        value=f"{god_bar(percent, tick)}  {int(percent*100)}%",
        inline=False
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_image(url=LOGO_URL)
    embed.set_footer(text="👑 ADMINZENO • GOD MODE")
    return embed

# =========================
# TIMER TASK
# =========================
async def role_timer(data):
    tick = 0
    guild = bot.get_guild(data["guild_id"])
    if not guild:
        return

    member = guild.get_member(data["member_id"])
    role = guild.get_role(data["role_id"])
    channel = guild.get_channel(data["channel_id"])
    message = await channel.fetch_message(data["message_id"])

    expire = datetime.datetime.fromisoformat(data["expire"])
    total = data["total"]

    while True:
        remaining = (expire - datetime.datetime.now()).total_seconds()

        if remaining <= 0:
            try:
                await member.remove_roles(role)

                expired = discord.Embed(
                    title="📅 Check member time!",
                    description="❌ **Role หมดเวลาแล้ว**",
                    color=0xFF3B3B
                )
                expired.add_field(name="👤 สมาชิก", value=member.mention, inline=False)
                expired.add_field(name="🏷 Role", value=role.mention, inline=False)
                expired.set_image(url=LOGO_URL)
                expired.set_footer(text="🔔 ADMINZENO • Expired")
                await message.edit(embed=expired)

                try:
                    await member.send(f"⛔ Role **{role.name}** ของคุณหมดเวลาแล้ว")
                except:
                    pass

            except:
                pass

            db = load_data()
            db = [d for d in db if d["message_id"] != data["message_id"]]
            save_data(db)
            break

        embed = build_embed(member, role, expire, remaining, total, data["note"], tick)
        await message.edit(embed=embed)

        tick += 1
        await asyncio.sleep(3)

# =========================
# SLASH COMMAND
# =========================
@bot.tree.command(name="setrole", description="👑 ตั้ง Role แบบจับเวลา (GOD MODE)")
@app_commands.describe(
    member="สมาชิก",
    role="Role",
    duration="30m / 1h / 7d",
    note="หมายเหตุ"
)
async def setrole(interaction: discord.Interaction, member: discord.Member,
                  role: discord.Role, duration: str, note: str):

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin Only", ephemeral=True)
        return

    seconds = parse_duration(duration)
    if not seconds:
        await interaction.response.send_message("❌ รูปแบบเวลาไม่ถูกต้อง", ephemeral=True)
        return

    expire = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
    await member.add_roles(role)

    # แจ้งเตือน MEMBER
    try:
        dm_member = discord.Embed(title="🎉 คุณได้รับ Role ใหม่!", color=0x3EF2C5)
        dm_member.add_field(name="🏷 Role", value=role.name, inline=False)
        dm_member.add_field(name="⏳ หมดอายุ", value=thai_date(expire), inline=False)
        dm_member.add_field(name="📝 หมายเหตุ", value=note, inline=False)
        dm_member.set_footer(text="👑 ADMINZENO")
        await member.send(embed=dm_member)
    except:
        pass

    # แจ้งเตือน ADMIN
    try:
        dm_admin = discord.Embed(title="✅ ให้ Role สำเร็จ", color=0x3EF2C5)
        dm_admin.add_field(name="👤 สมาชิก", value=member.mention, inline=False)
        dm_admin.add_field(name="🏷 Role", value=role.name, inline=False)
        dm_admin.add_field(name="⏳ ระยะเวลา", value=duration, inline=False)
        dm_admin.add_field(name="📝 หมายเหตุ", value=note, inline=False)
        await interaction.user.send(embed=dm_admin)
    except:
        pass

    embed = build_embed(member, role, expire, seconds, seconds, note, 0)
    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()

    data = {
        "guild_id": interaction.guild.id,
        "member_id": member.id,
        "role_id": role.id,
        "channel_id": interaction.channel.id,
        "message_id": message.id,
        "expire": expire.isoformat(),
        "total": seconds,
        "note": note
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
    print(f"👑 GOD MODE ACTIVE: {bot.user}")
    for data in load_data():
        bot.loop.create_task(role_timer(data))

bot.run(TOKEN)
