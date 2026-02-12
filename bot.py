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
LOGO_URL = "https://cdn.discordapp.com/attachments/1468621028598087843/1471249375706746890/Black_White_Minimalist_Animation_Logo_Video_1.gif?ex=698ee801&is=698d9681&hm=193acbc25aaa2da001605dd84fc0bfc2472fd8a0ebb0da321ac7c93a0edad888&"

WARN_3_DAYS = 3 * 86400  # 3 วัน (วินาที)

# =========================
# MEMBER PACKAGES
# =========================
MEMBER_PACKAGES = {
    "VIP | Zenomember": {
        "name": "VIP",
        "price": 200,
        "days": 30
    },
    "Gold | Zenomember": {
        "name": "Gold",
        "price": 100,
        "days": 30
    }
}

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
# TIME UTILS
# =========================
def parse_time(time_str):
    match = re.match(r"(\d+)([mhd])", time_str.lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    return value * {"m": 60, "h": 3600, "d": 86400}[unit]

def format_digital(seconds):
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h} ชม. / {m} นาที / {s} วิ"

def thai_short_date(dt):
    year = dt.year + 543
    return dt.strftime(f"%d/%m/{str(year)[-2:]}")

# =========================
# PROGRESS BAR
# =========================
def progress_bar(percent, tick):
    total = 20
    filled = int(total * percent)
    bar = ["🟦" if i < filled else "⬜" for i in range(total)]
    bar[tick % total] = "⚡"
    return "".join(bar)

# =========================
# EMBED BUILDER
# =========================
def build_embed(member, role, data, remaining, tick):
    total = data["total"]
    percent = remaining / total if total > 0 else 0

    package = MEMBER_PACKAGES.get(role.name, {
        "name": role.name,
        "price": "-",
        "days": total // 86400
    })

    embed = discord.Embed(
        title="📅 Check member time!",
        description="Zeno Community • Time Member System",
        color=discord.Color.blue()
    )

    embed.add_field(name="👤 สมาชิก", value=member.mention, inline=False)
    embed.add_field(name="🏷 Role", value=role.mention, inline=False)

    embed.add_field(
        name="📌 วันที่ลงทะเบียน",
        value=(
            f"{thai_short_date(data['register'])}\n"
            f"💎 {package['name']} | ราคา {package['price']} บาท | จำนวน {package['days']} วัน"
        ),
        inline=False
    )

    embed.add_field(
        name="📅 วันหมดอายุ",
        value=(
            f"<t:{int(data['expire'].timestamp())}:D>\n"
            f"จำนวนที่เหลือ [ {max(0, int(remaining // 86400))} ] วัน"
        ),
        inline=False
    )

    embed.add_field(
        name="⏱ เวลาที่เหลือ",
        value=f"```{format_digital(remaining)}```",
        inline=False
    )

    embed.add_field(
        name="📊 Progress",
        value=f"{progress_bar(percent, tick)} {int(percent*100)}%",
        inline=False
    )

    embed.set_image(url=LOGO_URL)
    embed.set_footer(text="🔔 ADMINZENO • Time Member")

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
    admin = await bot.fetch_user(ADMIN_ID)

    if not member or not role or not channel:
        return

    message = await channel.fetch_message(data["message_id"])

    while True:
        remaining = (data["expire"] - datetime.datetime.now()).total_seconds()

        # 🔔 แจ้งเตือนก่อนหมด 3 วัน (ครั้งเดียว)
        if remaining <= WARN_3_DAYS and not data.get("warned_3days"):
            try:
                await member.send(
                    f"⏰ แจ้งเตือนสมาชิก\n"
                    f"Role {role.name} ของคุณจะหมดอายุในอีก 3 วัน\n"
                    f"📅 หมดอายุวันที่ <t:{int(data['expire'].timestamp())}:D>"
                )

                await admin.send(
                    f"⏰ แจ้งเตือน Admin\n"
                    f"{member.name} ({role.name}) จะหมดอายุในอีก 3 วัน"
                )
            except:
                pass

            data["warned_3days"] = True
            db = load_data()
            for r in db:
                if r["message_id"] == data["message_id"]:
                    r["warned_3days"] = True
            save_data(db)

        # ⛔ หมดอายุ
        if remaining <= 0:
            try:
                await member.remove_roles(role)
                await member.send(f"⛔ Role {role.name} หมดเวลาแล้ว")
                await admin.send(f"⛔ {member.name} หมดเวลา {role.name}")
            except:
                pass

            db = [r for r in load_data() if r["message_id"] != data["message_id"]]
            save_data(db)
            break

        embed = build_embed(member, role, data, remaining, tick)
        await message.edit(embed=embed)

        tick += 1
        await asyncio.sleep(10)

# =========================
# COMMAND
# =========================
@bot.tree.command(name="setrole", description="ตั้ง Role แบบจับเวลา")
@app_commands.describe(
    member="สมาชิก",
    role="Role",
    duration="30m / 1h / 7d",
    register_date="วันที่สมัคร (DD/MM/YYYY)"
)
async def setrole(
    interaction: discord.Interaction,
    member: discord.Member,
    role: discord.Role,
    duration: str,
    register_date: str = None
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only", ephemeral=True)
        return

    seconds = parse_time(duration)
    if not seconds:
        await interaction.response.send_message("❌ รูปแบบเวลาไม่ถูกต้อง", ephemeral=True)
        return

    if register_date:
        try:
            register = datetime.datetime.strptime(register_date, "%d/%m/%Y")
        except ValueError:
            await interaction.response.send_message(
                "❌ รูปแบบวันที่ไม่ถูกต้อง (DD/MM/YYYY)",
                ephemeral=True
            )
            return
    else:
        register = datetime.datetime.now()

    expire = register + datetime.timedelta(seconds=seconds)

    await member.add_roles(role)

    data = {
        "guild_id": interaction.guild.id,
        "member_id": member.id,
        "role_id": role.id,
        "channel_id": interaction.channel.id,
        "message_id": None,
        "register": register,
        "expire": expire,
        "total": seconds,
        "warned_3days": False
    }

    embed = build_embed(member, role, data, seconds, 0)
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()

    data["message_id"] = msg.id

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
