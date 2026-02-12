import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
from datetime import datetime, timedelta

# ========= CONFIG =========
TOKEN = os.getenv("DISCORD_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1392851942480412822"))
DATA_FILE = "members.json"
ROLES_FILE = "roles.json"
DURATION_DAYS = 30  # FIX 30 DAYS
GIF_LOGO = "https://cdn.discordapp.com/attachments/1468621028598087843/1471249375706746890/Black_White_Minimalist_Animation_Logo_Video_1.gif"

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ========= UTILS =========
def load_json(path, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ========= EVENTS =========
@bot.event
async def on_ready():
    await bot.tree.sync()
    role_timer.start()
    print("👑 BOT ONLINE")

# ========= COMMANDS =========
@bot.tree.command(name="setrole", description="เพิ่มสมาชิกแบบกำหนดวันที่สมัครเอง (30 วัน)")
@app_commands.describe(
    member="สมาชิก",
    role="Role",
    register_date="วันที่สมัคร (DD/MM/YY)"
)
async def setrole(interaction: discord.Interaction, member: discord.Member, role: discord.Role, register_date: str):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("❌ คำสั่งนี้สำหรับแอดมินเท่านั้น", ephemeral=True)
        return

    try:
        # 📅 แปลงวันที่สมัคร (บังคับเป็น 00:00)
        start_date = datetime.strptime(register_date, "%d/%m/%y")
        start_date = start_date.replace(hour=0, minute=0, second=0)

        # ⏳ หมดอายุ 30 วัน (สิ้นวัน)
        expire_date = start_date + timedelta(days=DURATION_DAYS)
        expire_date = expire_date.replace(hour=23, minute=59, second=59)

    except ValueError:
        await interaction.response.send_message("❌ รูปแบบวันที่ต้องเป็น DD/MM/YY", ephemeral=True)
        return

    data = load_json(DATA_FILE, {})

    data[str(member.id)] = {
        "role_id": role.id,
        "register_date": start_date.isoformat(),
        "expire_date": expire_date.isoformat(),
        "warned_3days": False
    }

    save_json(DATA_FILE, data)
    await member.add_roles(role)

    # 📩 DM แจ้งสมาชิก
    try:
        await member.send(
            f"👑 สมัครสมาชิกเรียบร้อย\n"
            f"📅 วันที่สมัคร: {start_date.strftime('%d/%m/%Y')}\n"
            f"⏳ หมดอายุ: {expire_date.strftime('%d/%m/%Y')}"
        )
    except:
        pass

    await interaction.response.send_message(f"✅ เพิ่มสมาชิก {member.mention} เรียบร้อย", ephemeral=True)

# ========= CHECK COMMAND =========
@bot.tree.command(name="check", description="ตรวจสอบเวลาสมาชิก")
async def check(interaction: discord.Interaction):
    data = load_json(DATA_FILE, {})
    uid = str(interaction.user.id)

    if uid not in data:
        await interaction.response.send_message("❌ คุณยังไม่มีสถานะสมาชิก", ephemeral=True)
        return

    info = data[uid]
    now = datetime.now()
    expire = datetime.fromisoformat(info["expire_date"])
    start = datetime.fromisoformat(info["register_date"])

    remain = expire - now
    days_left = max(0, remain.days)

    progress = int(((DURATION_DAYS - days_left) / DURATION_DAYS) * 100)
    bar = "🟩" * (progress // 10) + "⬛" * (10 - progress // 10)

    embed = discord.Embed(
        title="📆 Check Member Time",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=GIF_LOGO)
    embed.add_field(name="👤 สมาชิก", value=interaction.user.mention, inline=False)
    embed.add_field(name="📅 วันที่สมัคร", value=start.strftime("%d %B %Y"), inline=False)
    embed.add_field(name="⏳ วันหมดอายุ", value=expire.strftime("%d %B %Y"), inline=False)
    embed.add_field(name="⏱ เหลือเวลา", value=f"{days_left} วัน", inline=False)
    embed.add_field(name="📊 Progress", value=f"{bar} {progress}%", inline=False)
    embed.set_footer(text="👑 ADMINZENO • TIME MEMBER SYSTEM")

    await interaction.response.send_message(embed=embed)

# ========= TIMER =========
@tasks.loop(minutes=1)
async def role_timer():
    data = load_json(DATA_FILE, {})
    now = datetime.now()
    changed = False

    for uid, info in list(data.items()):
        if not isinstance(info, dict):
            continue

        expire = datetime.fromisoformat(info["expire_date"])
        start = datetime.fromisoformat(info["register_date"])
        warned = info.get("warned_3days", False)

        member = bot.get_user(int(uid))
        if not member:
            continue

        # 🔔 แจ้งเตือนก่อนหมด 3 วัน
        if not warned and (expire - now).days <= 3:
            try:
                await member.send("⏰ สมาชิกของคุณจะหมดอายุในอีก 3 วัน")
            except:
                pass
            info["warned_3days"] = True
            changed = True

        # ❌ หมดอายุ
        if now >= expire:
            guilds = bot.guilds
            for g in guilds:
                m = g.get_member(int(uid))
                if m:
                    role = g.get_role(info["role_id"])
                    if role:
                        await m.remove_roles(role)
            del data[uid]
            changed = True

    if changed:
        save_json(DATA_FILE, data)

# ========= START =========
bot.run(TOKEN)
