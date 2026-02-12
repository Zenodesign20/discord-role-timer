import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
from datetime import datetime, timedelta

# ========= CONFIG =========
TOKEN = os.getenv("DISCORD_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
DATA_FILE = "members.json"
ROLES_FILE = "roles.json"
DURATION_DAYS = 30

GIF_LOGO = "https://cdn.discordapp.com/attachments/1468621028598087843/1471249375706746890/Black_White_Minimalist_Animation_Logo_Video_1.gif"

# ========= INTENTS =========
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

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

# ========= /setrole =========
@bot.tree.command(name="setrole", description="เพิ่มสมาชิก (กำหนดวันที่สมัครเอง / 30 วัน)")
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
        start = datetime.strptime(register_date, "%d/%m/%y")
        start = start.replace(hour=0, minute=0, second=0)

        # นับวันสมัครเป็นวันแรก → +29 = ครบ 30 วัน
        expire = start + timedelta(days=DURATION_DAYS - 1)
        expire = expire.replace(hour=23, minute=59, second=59)

    except ValueError:
        await interaction.response.send_message("❌ รูปแบบวันที่ต้องเป็น DD/MM/YY", ephemeral=True)
        return

    data = load_json(DATA_FILE, {})

    data[str(member.id)] = {
        "role_id": role.id,
        "register_date": start.isoformat(),
        "expire_date": expire.isoformat(),
        "warned_3days": False
    }

    save_json(DATA_FILE, data)
    await member.add_roles(role)

    try:
        await member.send(
            f"👑 สมัครสมาชิกเรียบร้อย\n"
            f"📅 วันที่สมัคร: {start.strftime('%d/%m/%Y')}\n"
            f"🗓 วันหมดอายุ: {expire.strftime('%d/%m/%Y')}"
        )
    except:
        pass

    await interaction.response.send_message(f"✅ เพิ่มสมาชิก {member.mention} เรียบร้อย", ephemeral=True)

# ========= /check =========
@bot.tree.command(name="check", description="ตรวจสอบเวลาสมาชิก")
async def check(interaction: discord.Interaction):
    data = load_json(DATA_FILE, {})
    roles_cfg = load_json(ROLES_FILE, {})
    uid = str(interaction.user.id)

    if uid not in data:
        await interaction.response.send_message("❌ คุณยังไม่มีสถานะสมาชิก", ephemeral=True)
        return

    info = data[uid]
    now = datetime.now()

    start = datetime.fromisoformat(info["register_date"])
    expire = datetime.fromisoformat(info["expire_date"])

    remaining = expire - now
    if remaining.total_seconds() < 0:
        remaining = timedelta(seconds=0)

    days = remaining.days
    hours, rem = divmod(remaining.seconds, 3600)
    minutes, seconds = divmod(rem, 60)

    used_days = (now - start).days
    used_days = max(0, min(used_days, DURATION_DAYS))
    progress = int((used_days / DURATION_DAYS) * 100)

    bar_len = 20
    filled = int(bar_len * progress / 100)
    bar = "🟩" * filled + "⬛" * (bar_len - filled)

    role = interaction.guild.get_role(info["role_id"])
    role_name = role.name if role else "Unknown"

    pack_name = role_name.split("|")[0].strip()
    pack = roles_cfg.get(pack_name, {})
    price = pack.get("price", "-")
    pack_days = pack.get("days", DURATION_DAYS)

    embed = discord.Embed(title="📆 Check Member Time", color=discord.Color.gold())
    embed.set_thumbnail(url=GIF_LOGO)

    embed.add_field(name="👤 สมาชิก", value=interaction.user.mention, inline=False)
    embed.add_field(name="🎭 Role", value=role.mention if role else role_name, inline=False)
    embed.add_field(name="📅 วันที่สมัคร", value=start.strftime("%d/%m/%Y"), inline=False)
    embed.add_field(
        name="💎 แพ็กเกจสมาชิก",
        value=f"**{pack_name}** | ราคา **{price} บาท** | จำนวน **{pack_days} วัน**",
        inline=False
    )
    embed.add_field(name="🗓 วันหมดอายุ", value=expire.strftime("%d/%m/%Y"), inline=False)
    embed.add_field(
        name="⏳ เวลาที่เหลือ",
        value=f"{days} วัน / {hours} ชม / {minutes} นาที / {seconds} วินาที",
        inline=False
    )
    embed.add_field(name="📊 Progress", value=f"{bar} **{progress}%**", inline=False)
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
        warned = info.get("warned_3days", False)

        user = bot.get_user(int(uid))
        if not user:
            continue

        # 🔔 เตือนก่อนหมด 3 วัน
        if not warned and (expire - now).days == 3:
            try:
                await user.send("⏰ สมาชิกของคุณจะหมดอายุในอีก 3 วัน")
            except:
                pass
            info["warned_3days"] = True
            changed = True

        # ❌ หมดอายุ
        if now >= expire:
            for g in bot.guilds:
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
