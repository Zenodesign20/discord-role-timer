import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import datetime
import re
import os
import json

TOKEN = os.getenv("DISCORD_TOKEN")

ADMIN_ID = 1392851942480412822
SLIP_CHANNEL_ID = 1471194733836501198  # ห้องส่งสลิป

VIP_PRICE = 200
GOLD_PRICE = 100

LOGO_URL = "https://cdn.phototourl.com/uploads/2026-02-11-5a3eeb2d-d2bf-4821-9742-bdcf3c4d9540.gif"
DATA_FILE = "roles.json"

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# DATABASE
# =========================
def load_data():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# =========================
# TIME PARSER
# =========================
def parse_time(time_str):
    match = re.match(r"(\d+)([mhd])", time_str.lower())
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2)
    if unit == "m": return value * 60
    if unit == "h": return value * 3600
    if unit == "d": return value * 86400

# =========================
# DIGITAL TIMER
# =========================
def format_digital(seconds):
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}"

# =========================
# THAI DATE
# =========================
def thai_date(dt):
    months = ["มกราคม","กุมภาพันธ์","มีนาคม","เมษายน","พฤษภาคม","มิถุนายน",
              "กรกฎาคม","สิงหาคม","กันยายน","ตุลาคม","พฤศจิกายน","ธันวาคม"]
    days = ["จันทร์","อังคาร","พุธ","พฤหัสบดี","ศุกร์","เสาร์","อาทิตย์"]
    year = dt.year + 543
    return f"วัน{days[dt.weekday()]}ที่ {dt.day} {months[dt.month-1]} {year} {dt.strftime('%H:%M')}"

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
# GOD PROGRESS BAR
# =========================
def god_bar(percent, tick):
    total = 20
    filled = int(total * percent)
    bar = []

    for i in range(total):
        if i < filled:
            if percent <= 0.15:
                bar.append("🟥")
            elif percent <= 0.5:
                bar.append("🟨")
            else:
                bar.append("🟩")
        else:
            bar.append("⬛")

    runner = tick % total
    bar[runner] = "⚡"

    if percent <= 0.15 and tick % 2 == 0:
        bar = ["💥" if b != "⬛" else b for b in bar]

    return "".join(bar)

# =========================
# EMBED
# =========================
def build_embed(member, role, expire_time, remaining, total, note, tick):
    percent = remaining / total
    embed = discord.Embed(
        title="📅 Check member time!",
        description="Welcome to Zeno Community Mod\nTime Member",
        color=get_color(percent)
    )

    embed.add_field(name="👤 ZenoMember", value=member.mention, inline=False)
    embed.add_field(name="🏷 Role", value=role.mention, inline=False)
    embed.add_field(name="📝 Status", value=note, inline=False)
    embed.add_field(name="⏳ วันหมดอายุ", value=thai_date(expire_time), inline=False)

    embed.add_field(
        name="🕹 DIGITAL COUNTDOWN",
        value=f"```{format_digital(remaining)}```",
        inline=False
    )

    embed.add_field(
        name="📊 GOD PROGRESS",
        value=f"{god_bar(percent, tick)}  {int(percent*100)}%",
        inline=False
    )

    embed.set_image(url=LOGO_URL)
    embed.set_footer(text="👑 ADMINZENO • GOD MODE")

    return embed

# =========================
# ROLE TIMER
# =========================
async def role_timer(data):
    tick = 0
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
    total = data["total"]

    while True:
        now = datetime.datetime.now()
        remaining = (expire_time - now).total_seconds()

        if remaining <= 0:
            try:
                await member.remove_roles(role)

                expired = discord.Embed(
                    title="⛔ ROLE EXPIRED",
                    description=f"{member.mention} ถูกลบ {role.mention} แล้ว",
                    color=0xFF0000
                )
                expired.set_footer(text="👑 ADMINZENO • GOD MODE")
                await message.edit(embed=expired)

                await member.send(f"⛔ Role {role.name} หมดเวลาแล้ว")
                await admin_user.send(f"⛔ {member.name} หมดเวลา {role.name}")

            except:
                pass

            db = load_data()
            db = [r for r in db if r["message_id"] != data["message_id"]]
            save_data(db)
            break

        embed = build_embed(member, role, expire_time, remaining, total, data["note"], tick)
        await message.edit(embed=embed)

        tick += 1
        await asyncio.sleep(3)

# =========================
# SLIP MONITOR
# =========================
@bot.event
async def on_message(message):

    if message.author.bot:
        return

    # ตรวจเฉพาะห้องสลิป
    if message.channel.id == SLIP_CHANNEL_ID:

        content = message.content.lower()
        package = None
        price = None

        if "vip" in content:
            package = "VIP"
            price = VIP_PRICE
        elif "gold" in content:
            package = "GOLD"
            price = GOLD_PRICE

        if message.attachments and package:

            embed = discord.Embed(
                title="💳 PAYMENT ALERT",
                description="มีผู้โอนเงินเข้ามาแล้ว",
                color=0x3EF2C5
            )

            embed.add_field(
                name="👤 ผู้โอน",
                value=f"{message.author.mention}\nID: {message.author.id}",
                inline=False
            )

            embed.add_field(name="📦 แพ็กเกจ", value=package, inline=True)
            embed.add_field(name="💰 ราคา", value=f"{price} บาท", inline=True)
            embed.add_field(name="⏰ เวลา", value=datetime.datetime.now().strftime("%d/%m/%Y %H:%M"), inline=False)

            embed.set_image(url=message.attachments[0].url)
            embed.set_footer(text="👑 ADMINZENO • SLIP DETECTED")

            await message.channel.send(
                content=f"<@{ADMIN_ID}> ตรวจสอบสลิปใหม่",
                embed=embed
            )

            try:
                admin_user = await bot.fetch_user(ADMIN_ID)
                await admin_user.send(embed=embed)
            except:
                pass

            await message.reply("✅ ส่งสลิปเรียบร้อย กรุณารอแอดมินตรวจสอบ")

        elif message.attachments and not package:
            await message.reply("❌ กรุณาพิมพ์ vip หรือ gold พร้อมแนบสลิป")

    await bot.process_commands(message)

# =========================
# COMMAND
# =========================
@bot.tree.command(name="setrole", description="👑 GOD MODE ROLE TIMER")
@app_commands.describe(member="สมาชิก", role="Role", duration="30m / 1h / 7d", note="หมายเหตุ")
async def setrole(interaction: discord.Interaction, member: discord.Member,
                  role: discord.Role, duration: str, note: str):

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin Only", ephemeral=True)
        return

    seconds = parse_time(duration)
    if not seconds:
        await interaction.response.send_message("❌ เวลาไม่ถูกต้อง", ephemeral=True)
        return

    expire_time = datetime.datetime.now() + datetime.timedelta(seconds=seconds)

    await member.add_roles(role)

    embed = build_embed(member, role, expire_time, seconds, seconds, note, 0)
    await interaction.response.send_message(embed=embed)

    message = await interaction.original_response()

    data = {
        "guild_id": interaction.guild.id,
        "member_id": member.id,
        "role_id": role.id,
        "channel_id": interaction.channel.id,
        "message_id": message.id,
        "expire": expire_time.isoformat(),
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
