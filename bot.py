import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
from datetime import datetime, timedelta

# ================= CONFIG =================
TOKEN = os.getenv("DISCORD_TOKEN")
ADMIN_ID = 1392851942480412822
DATA_FILE = "members.json"

DURATION_DAYS = 30

GIF_LOGO = "https://cdn.discordapp.com/attachments/1468621028598087843/1471249375706746890/Black_White_Minimalist_Animation_Logo_Video_1.gif"

# ตัวอย่างราคา (โชว์อย่างเดียว ไม่เอาไปคำนวณ)
ROLE_PACKAGES = {
    "VIP": {"price": "200 บาท", "days": 30},
    "Gold": {"price": "100 บาท", "days": 30}
}

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= UTILS =================
def load_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2)
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def format_remaining(td: timedelta):
    total_seconds = int(td.total_seconds())
    if total_seconds < 0:
        return "หมดอายุแล้ว"

    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    return f"{days} วัน / {hours} ชม / {minutes} นาที / {seconds} วิ"

# ================= EVENTS =================
@bot.event
async def on_ready():
    await bot.tree.sync()
    role_timer.start()
    print("👑 BOT ONLINE")

# ================= COMMAND =================
@bot.tree.command(name="setrole", description="เพิ่มสมาชิก (สมัคร + 30 วัน)")
@app_commands.describe(
    member="สมาชิก",
    role="Role",
    register_date="วันที่สมัคร (DD/MM/YY)"
)
async def setrole(
    interaction: discord.Interaction,
    member: discord.Member,
    role: discord.Role,
    register_date: str
):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("❌ สำหรับแอดมินเท่านั้น", ephemeral=True)
        return

    try:
        start_date = datetime.strptime(register_date, "%d/%m/%y")
        start_date = start_date.replace(hour=0, minute=0, second=0)

        # นับวันสมัครเป็นวันที่ 1 → +29 = 30 วัน
        expire_date = start_date + timedelta(days=DURATION_DAYS - 1)
        expire_date = expire_date.replace(hour=23, minute=59, second=59)

    except ValueError:
        await interaction.response.send_message("❌ รูปแบบวันที่ต้องเป็น DD/MM/YY", ephemeral=True)
        return

    data = load_data()

    role_name_clean = role.name.split("|")[0].strip()
    package = ROLE_PACKAGES.get(role_name_clean, {"price": "-", "days": 30})

    data[str(member.id)] = {
        "member_name": member.display_name,
        "role_id": role.id,
        "role_name": role.name,
        "register_date": start_date.isoformat(),
        "expire_date": expire_date.isoformat(),
        "package_name": role_name_clean,
        "price": package["price"],
        "days": package["days"],
        "warned_3days": False
    }

    save_data(data)
    await member.add_roles(role)

    try:
        await member.send(
            f"👑 สมัครสมาชิกสำเร็จ\n"
            f"📅 สมัครวันที่: {start_date.strftime('%d/%m/%Y')}\n"
            f"⏳ หมดอายุวันที่: {expire_date.strftime('%d/%m/%Y')}"
        )
    except:
        pass

    await interaction.response.send_message(
        f"✅ เพิ่มสมาชิก {member.mention} เรียบร้อย",
        ephemeral=True
    )

# ================= CHECK =================
@bot.tree.command(name="check", description="ตรวจสอบสถานะสมาชิก")
async def check(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)

    if uid not in data:
        await interaction.response.send_message("❌ คุณยังไม่มีสถานะสมาชิก", ephemeral=True)
        return

    info = data[uid]
    now = datetime.now()

    start = datetime.fromisoformat(info["register_date"])
    expire = datetime.fromisoformat(info["expire_date"])

    used_days = max(0, (now.date() - start.date()).days + 1)
    remaining = expire - now

    progress_percent = min(100, int((used_days / DURATION_DAYS) * 100))
    bar = "🟩" * (progress_percent // 10) + "⬛" * (10 - progress_percent // 10)

    embed = discord.Embed(
        title="👑 MEMBER STATUS",
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=GIF_LOGO)

    embed.add_field(name="👤 สมาชิก", value=interaction.user.mention, inline=False)
    embed.add_field(name="🎭 Role", value=info["role_name"], inline=False)
    embed.add_field(name="📅 วันที่สมัคร", value=start.strftime("%d/%m/%Y"), inline=False)

    embed.add_field(
        name="💳 แพ็กเกจ",
        value=f"**{info['package_name']}** | ราคา {info['price']} | {info['days']} วัน",
        inline=False
    )

    embed.add_field(name="📆 วันหมดอายุ", value=expire.strftime("%d/%m/%Y"), inline=False)
    embed.add_field(name="📈 ใช้ไปแล้ว", value=f"{used_days} วัน", inline=False)
    embed.add_field(name="⏳ เวลาที่เหลือ", value=format_remaining(remaining), inline=False)
    embed.add_field(name="📊 Progress", value=f"{bar} {progress_percent}%", inline=False)

    embed.set_footer(text="👑 TIME MEMBER SYSTEM")

    await interaction.response.send_message(embed=embed)

# ================= TIMER =================
@tasks.loop(minutes=1)
async def role_timer():
    data = load_data()
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

        # 🔔 แจ้งเตือนก่อนหมด 3 วัน
        if not warned and 0 < (expire - now).days <= 3:
            try:
                await user.send("⏰ สมาชิกของคุณจะหมดอายุในอีก **3 วัน**")
            except:
                pass
            info["warned_3days"] = True
            changed = True

        # ❌ หมดอายุ
        if now >= expire:
            for guild in bot.guilds:
                member = guild.get_member(int(uid))
                if member:
                    role = guild.get_role(info["role_id"])
                    if role:
                        await member.remove_roles(role)
            del data[uid]
            changed = True

    if changed:
        save_data(data)

# ================= START =================
bot.run(TOKEN)
