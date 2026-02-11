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

IMAGE_URL = "https://cdn.discordapp.com/attachments/1468621028598087843/1471249375706746890/Black_White_Minimalist_Animation_Logo_Video_1.gif?ex=698e3f41&is=698cedc1&hm=01225246d18d44f7fbca37490f50a106e24ba7f9759d5faac411212d20c097c6&"
FOOTER_ICON = "https://cdn.discordapp.com/attachments/1468621028598087843/1471260996394811605/Sponsor-Zenobot1.png?ex=698e4a14&is=698cf894&hm=2d5f1a575b32db7bf0adde2fa0334a988f52a335578efabda3e949616a7dd8af&"   # 🔁 เปลี่ยนโลโก้มุมขวาล่าง
DATA_FILE = "roles.json"

UPDATE_INTERVAL = 10
WARN_BEFORE_DAYS = 3

# =========================
# BOT
# =========================
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

animation_tick = 0

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
    match = re.match(r"(\d+)([smhd])", time_str.lower())
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2)
    if unit == "s": return value
    if unit == "m": return value * 60
    if unit == "h": return value * 3600
    if unit == "d": return value * 86400

# =========================
# TIME FORMAT
# =========================
def remaining_detail(seconds):
    seconds = int(max(seconds, 0))
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return days, hours, minutes, secs

def short_thai_date(dt):
    year = dt.year + 543
    return dt.strftime(f"%d/%m/{str(year)[-2:]}")

def format_register_date(dt):
    year = dt.year + 543
    return dt.strftime(f"%d/%m/{str(year)[-2:]}")

def discord_timestamp(dt, style="R"):
    return f"<t:{int(dt.timestamp())}:{style}>"

# =========================
# COLOR
# =========================
def get_color(percent):
    if percent <= 0.15:
        return 0xFF3B3B
    elif percent <= 0.5:
        return 0xFFD93D
    return 0x3EF2C5

# =========================
# ANIMATED BAR
# =========================
ANIM_FRAMES = ["🟩", "🟨", "🟦"]

def animated_progress_bar(total, remaining, tick, length=12):
    if remaining <= 0:
        return "⬜" * length, 0

    percent = remaining / total
    filled = int(length * percent)
    anim = ANIM_FRAMES[tick % len(ANIM_FRAMES)]
    bar = anim * filled + "⬜" * (length - filled)

    return bar, int(percent * 100)

# =========================
# EMBED
# =========================
def build_embed(member, role, data, remaining, tick):
    expire_time = datetime.datetime.fromisoformat(data["expire"])
    register_dt = datetime.datetime.fromisoformat(data["register_date"])
    total = data["total"]

    percent = remaining / total
    days, hours, minutes, secs = remaining_detail(remaining)
    bar, percent_int = animated_progress_bar(total, remaining, tick)

    embed = discord.Embed(
        title="📅 Check member time!",
        description="Zeno Community • Time Member System",
        color=get_color(percent)
    )

    embed.add_field(name="👤 สมาชิก", value=member.mention, inline=False)
    embed.add_field(name="🏷 Role", value=role.mention, inline=False)

    # ✅ แทน Status ด้วยวันที่ลงทะเบียน
    embed.add_field(
        name="📌 วันที่ลงทะเบียน",
        value=f"**{format_register_date(register_dt)}**",
        inline=False
    )

    embed.add_field(
        name="📆 วันหมดอายุ",
        value=(
            f"**{short_thai_date(expire_time)}**\n"
            f"จำนวนที่เหลือ **[ {days} ] วัน**\n"
            f"{discord_timestamp(expire_time)}"
        ),
        inline=False
    )

    embed.add_field(
        name="⏱ เวลาที่เหลือ",
        value=f"`{hours} ชั่วโมง / {minutes} นาที / {secs} วินาที`",
        inline=False
    )

    embed.add_field(
        name="📊 Progress",
        value=f"{bar} **{percent_int}%**",
        inline=False
    )

    embed.set_image(url=IMAGE_URL)
    embed.set_footer(
        text="🔔 ADMINZENO • Time Member",
        icon_url=FOOTER_ICON
    )

    return embed

# =========================
# TIMER
# =========================
async def role_timer(data):
    global animation_tick

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

    expire_time = datetime.datetime.fromisoformat(data["expire"])
    warned = data.get("warned", False)

    while True:
        now = datetime.datetime.now()
        remaining = (expire_time - now).total_seconds()

        # 🔔 แจ้งเตือนก่อนหมด
        if remaining <= WARN_BEFORE_DAYS * 86400 and remaining > 0 and not warned:
            await member.send(f"⚠️ Role **{role.name}** จะหมดอายุในอีก {WARN_BEFORE_DAYS} วัน")
            await admin_user.send(f"⚠️ {member.name} ใกล้หมด Role {role.name}")

            data["warned"] = True
            db = load_data()
            for r in db:
                if r["message_id"] == data["message_id"]:
                    r["warned"] = True
            save_data(db)

        # ❌ หมดอายุ
        if remaining <= 0:
            try:
                await member.remove_roles(role)
                expired = discord.Embed(
                    title="⛔ ROLE EXPIRED",
                    description=f"{member.mention} หมดเวลา {role.mention}",
                    color=0xFF0000
                )
                await message.edit(embed=expired)
                await member.send(f"⛔ Role {role.name} หมดเวลาแล้ว")
                await admin_user.send(f"⛔ {member.name} หมดเวลา {role.name}")
            except:
                pass

            db = load_data()
            db = [r for r in db if r["message_id"] != data["message_id"]]
            save_data(db)
            break

        embed = build_embed(member, role, data, remaining, animation_tick)
        await message.edit(embed=embed)

        animation_tick += 1
        await asyncio.sleep(UPDATE_INTERVAL)

# =========================
# COMMAND
# =========================
@bot.tree.command(name="setrole", description="ตั้งเวลา Role (Time Member)")
@app_commands.describe(
    member="สมาชิก",
    role="Role",
    duration="เช่น 10d / 5h / 30m",
    register_date="วันที่ลงทะเบียน (DD/MM/YY) เช่น 11/03/69"
)
async def setrole(
    interaction: discord.Interaction,
    member: discord.Member,
    role: discord.Role,
    duration: str,
    register_date: str = None
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin Only", ephemeral=True)
        return

    seconds = parse_time(duration)
    if not seconds:
        await interaction.response.send_message("❌ รูปแบบเวลาไม่ถูกต้อง", ephemeral=True)
        return

    # 📌 วันที่ลงทะเบียน
    if register_date:
        try:
            dt = datetime.datetime.strptime(register_date, "%d/%m/%y")
            register_dt = dt.replace(year=dt.year - 543)
        except:
            await interaction.response.send_message(
                "❌ วันที่ต้องเป็น DD/MM/YY เช่น 11/03/69",
                ephemeral=True
            )
            return
    else:
        register_dt = datetime.datetime.now()

    expire_time = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
    await member.add_roles(role)

    data = {
        "guild_id": interaction.guild.id,
        "member_id": member.id,
        "role_id": role.id,
        "channel_id": interaction.channel.id,
        "expire": expire_time.isoformat(),
        "total": seconds,
        "register_date": register_dt.isoformat(),
        "warned": False
    }

    embed = build_embed(member, role, data, seconds, 0)
    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()

    data["message_id"] = message.id
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
    print(f"👑 BOT ONLINE: {bot.user}")
    for data in load_data():
        bot.loop.create_task(role_timer(data))

bot.run(TOKEN)
