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

WARN_3_DAYS = 3 * 86400

# =========================
# MEMBER PACKAGES
# =========================
MEMBER_PACKAGES = {
    "VIP | Zenomember": {"name": "VIP", "price": 200, "days": 30},
    "Gold | Zenomember": {"name": "Gold", "price": 100, "days": 30}
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
    return int(match.group(1)) * {"m":60,"h":3600,"d":86400}[match.group(2)]

def format_digital(sec):
    sec = max(0, int(sec))
    return f"{sec//3600} ชม. / {(sec%3600)//60} นาที / {sec%60} วิ"

def thai_short_date(dt):
    return dt.strftime("%d/%m/") + str(dt.year + 543)[-2:]

# =========================
# PROGRESS BAR
# =========================
def progress_bar(percent, tick):
    total = 20
    bar = ["🟦" if i < int(total*percent) else "⬜" for i in range(total)]
    bar[tick % total] = "⚡"
    return "".join(bar)

# =========================
# EMBED
# =========================
def build_embed(member, role, data, remaining, tick):
    pkg = MEMBER_PACKAGES.get(role.name, {"name": role.name, "price": "-", "days": data["total"]//86400})
    percent = remaining / data["total"]

    e = discord.Embed(
        title="📅 Check member time!",
        description="Zeno Community • Time Member System",
        color=discord.Color.blue()
    )

    e.add_field(name="👤 สมาชิก", value=member.mention, inline=False)
    e.add_field(name="🏷 Role", value=role.mention, inline=False)
    e.add_field(
        name="📌 วันที่ลงทะเบียน",
        value=f"{thai_short_date(data['register'])}\n💎 {pkg['name']} | ราคา {pkg['price']} บาท | {pkg['days']} วัน",
        inline=False
    )
    e.add_field(
        name="📅 วันหมดอายุ",
        value=f"<t:{int(data['expire'].timestamp())}:D>\nเหลือ {int(remaining//86400)} วัน",
        inline=False
    )
    e.add_field(name="⏱ เวลาที่เหลือ", value=f"```{format_digital(remaining)}```", inline=False)
    e.add_field(name="📊 Progress", value=f"{progress_bar(percent, tick)} {int(percent*100)}%", inline=False)
    e.set_image(url=LOGO_URL)
    e.set_footer(text="🔔 ADMINZENO • Time Member")
    return e

# =========================
# CANCEL BUTTON VIEW
# =========================
class CancelView(discord.ui.View):
    def __init__(self, data, author_id):
        super().__init__(timeout=None)
        self.data = data
        self.author_id = author_id

    @discord.ui.button(label="❌ ยกเลิก", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ คุณไม่มีสิทธิ์", ephemeral=True)
            return

        guild = interaction.guild
        member = guild.get_member(self.data["member_id"])
        role = guild.get_role(self.data["role_id"])

        if member and role:
            await member.remove_roles(role)

        db = [r for r in load_data() if r["message_id"] != self.data["message_id"]]
        save_data(db)

        embed = discord.Embed(
            title="❌ ยกเลิกเรียบร้อย",
            description="การตั้งค่า Role นี้ถูกยกเลิกแล้ว",
            color=discord.Color.red()
        )

        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.defer()

# =========================
# TIMER
# =========================
async def role_timer(data):
    tick = 0
    guild = bot.get_guild(data["guild_id"])
    member = guild.get_member(data["member_id"])
    role = guild.get_role(data["role_id"])
    channel = guild.get_channel(data["channel_id"])
    admin = await bot.fetch_user(ADMIN_ID)
    msg = await channel.fetch_message(data["message_id"])

    while True:
        remaining = (data["expire"] - datetime.datetime.now()).total_seconds()

        if remaining <= WARN_3_DAYS and not data.get("warned_3days"):
            try:
                await member.send(f"⏰ Role {role.name} จะหมดใน 3 วัน")
                await admin.send(f"⏰ {member.name} ({role.name}) เหลือ 3 วัน")
            except: pass
            data["warned_3days"] = True
            db = load_data()
            for r in db:
                if r["message_id"] == data["message_id"]:
                    r["warned_3days"] = True
            save_data(db)

        if remaining <= 0:
            await member.remove_roles(role)
            break

        await msg.edit(embed=build_embed(member, role, data, remaining, tick))
        tick += 1
        await asyncio.sleep(10)

# =========================
# COMMAND
# =========================
@bot.tree.command(name="setrole", description="ตั้ง Role แบบจับเวลา")
@app_commands.describe(member="สมาชิก", role="Role", duration="30d / 1h", register_date="DD/MM/YYYY")
async def setrole(interaction, member: discord.Member, role: discord.Role, duration: str, register_date: str = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only", ephemeral=True)
        return

    sec = parse_time(duration)
    if not sec:
        await interaction.response.send_message("❌ เวลาไม่ถูกต้อง", ephemeral=True)
        return

    try:
        register = datetime.datetime.strptime(register_date, "%d/%m/%Y") if register_date else datetime.datetime.now()
    except:
        await interaction.response.send_message("❌ วันที่ผิด", ephemeral=True)
        return

    expire = register + datetime.timedelta(seconds=sec)
    await member.add_roles(role)

    data = {
        "guild_id": interaction.guild.id,
        "member_id": member.id,
        "role_id": role.id,
        "channel_id": interaction.channel.id,
        "message_id": None,
        "register": register,
        "expire": expire,
        "total": sec,
        "warned_3days": False
    }

    embed = build_embed(member, role, data, sec, 0)
    view = CancelView(data, interaction.user.id)
    await interaction.response.send_message(embed=embed, view=view)
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
