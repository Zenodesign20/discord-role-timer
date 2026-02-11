import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import datetime
import json
import os
import re

# =====================
# CONFIG
# =====================
TOKEN = os.getenv("DISCORD_TOKEN")
ADMIN_ID = 1392851942480412822
DATA_FILE = "roles.json"
LOGO_URL = "https://cdn.phototourl.com/uploads/2026-02-11-5a3eeb2d-d2bf-4821-9742-bdcf3c4d9540.gif"

UPDATE_INTERVAL = 10  # วินาที
WARNING_BEFORE = 3 * 24 * 3600  # เตือนก่อนหมด 3 วัน

# =====================
# BOT SETUP
# =====================
intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
animation_tick = 0

# =====================
# DATABASE
# =====================
def load_data():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# =====================
# TIME PARSER
# =====================
def parse_time(text):
    match = re.match(r"(\d+)([smhd])", text.lower())
    if not match:
        return None
    value, unit = match.groups()
    value = int(value)
    return {
        "s": value,
        "m": value * 60,
        "h": value * 3600,
        "d": value * 86400
    }.get(unit)

# =====================
# FORMAT
# =====================
def format_remaining(seconds):
    seconds = int(seconds)
    d, seconds = divmod(seconds, 86400)
    h, seconds = divmod(seconds, 3600)
    m, s = divmod(seconds, 60)
    return f"{d}d {h}h {m}m {s}s"

def discord_timestamp(dt, style="F"):
    return f"<t:{int(dt.timestamp())}:{style}>"

# =====================
# ANIMATED BAR
# =====================
ANIM_FRAMES = ["🟩", "🟨", "🟦"]

def animated_bar(total, remaining, tick, length=10):
    percent = max(0, remaining / total)
    filled = int(length * percent)
    anim = ANIM_FRAMES[tick % len(ANIM_FRAMES)]
    bar = anim * filled + "⬜" * (length - filled)
    return bar, int(percent * 100)

# =====================
# EMBED
# =====================
def build_embed(member, role, start_at, expire_at, remaining, tick, note):
    total = (expire_at - start_at).total_seconds()
    bar, percent = animated_bar(total, remaining, tick)

    embed = discord.Embed(
        title="📅 Check member time!",
        description="Time Member System",
        color=0x3EF2C5 if percent > 30 else 0xFFD93D if percent > 10 else 0xFF3B3B
    )

    embed.add_field(name="👤 สมาชิก", value=member.mention, inline=False)
    embed.add_field(name="🏷 Role", value=role.mention, inline=False)
    embed.add_field(name="📝 สถานะ", value=note, inline=False)

    embed.add_field(
        name="📊 เวลาใช้งาน",
        value=f"{bar} **{percent}%**\n`{format_remaining(remaining)}`",
        inline=False
    )

    embed.add_field(
        name="🕒 วันหมดอายุ",
        value=f"{discord_timestamp(expire_at,'F')}\n({discord_timestamp(expire_at,'R')})",
        inline=False
    )

    embed.set_image(url=LOGO_URL)
    embed.set_footer(text="🔔 ADMINZENO • Expired")

    return embed

# =====================
# TIMER LOOP
# =====================
async def role_timer(data):
    global animation_tick

    guild = bot.get_guild(data["guild_id"])
    if not guild:
        return

    member = guild.get_member(data["member_id"])
    role = guild.get_role(data["role_id"])
    channel = guild.get_channel(data["channel_id"])

    if not all([member, role, channel]):
        return

    message = await channel.fetch_message(data["message_id"])
    admin = await bot.fetch_user(ADMIN_ID)

    start_at = datetime.datetime.fromisoformat(data["start_at"])
    expire_at = datetime.datetime.fromisoformat(data["expire_at"])
    warned = data.get("warned", False)

    while True:
        now = datetime.datetime.now()
        remaining = (expire_at - now).total_seconds()

        if remaining <= 0:
            await member.remove_roles(role)

            embed = discord.Embed(
                title="❌ Role หมดเวลาแล้ว",
                description=f"{member.mention} ถูกลบ {role.mention}",
                color=0xFF0000
            )
            await message.edit(embed=embed)

            await member.send(f"⛔ Role **{role.name}** หมดเวลาแล้ว")
            await admin.send(f"⛔ {member} หมดเวลา Role {role.name}")

            db = load_data()
            db = [d for d in db if d["message_id"] != data["message_id"]]
            save_data(db)
            break

        if remaining <= WARNING_BEFORE and not warned:
            await member.send(f"⚠️ Role **{role.name}** จะหมดใน 3 วัน")
            await admin.send(f"⚠️ {member} ใกล้หมด Role {role.name}")
            data["warned"] = True
            db = load_data()
            save_data(db)

        animation_tick += 1
        embed = build_embed(member, role, start_at, expire_at, remaining, animation_tick, data["note"])
        await message.edit(embed=embed)

        await asyncio.sleep(UPDATE_INTERVAL)

# =====================
# SLASH COMMAND
# =====================
@bot.tree.command(name="setrole", description="ตั้งเวลา Role")
async def setrole(
    interaction: discord.Interaction,
    member: discord.Member,
    role: discord.Role,
    duration: str,
    note: str
):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin only", ephemeral=True)

    seconds = parse_time(duration)
    if not seconds:
        return await interaction.response.send_message("❌ รูปแบบเวลาไม่ถูกต้อง", ephemeral=True)

    await member.add_roles(role)

    start_at = datetime.datetime.now()
    expire_at = start_at + datetime.timedelta(seconds=seconds)

    embed = build_embed(member, role, start_at, expire_at, seconds, 0, note)
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()

    data = {
        "guild_id": interaction.guild.id,
        "member_id": member.id,
        "role_id": role.id,
        "channel_id": interaction.channel.id,
        "message_id": msg.id,
        "start_at": start_at.isoformat(),
        "expire_at": expire_at.isoformat(),
        "note": note,
        "warned": False
    }

    db = load_data()
    db.append(data)
    save_data(db)

    bot.loop.create_task(role_timer(data))

# =====================
# READY
# =====================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"👑 GOD MODE ACTIVE: {bot.user}")

    for data in load_data():
        bot.loop.create_task(role_timer(data))

bot.run(TOKEN)
