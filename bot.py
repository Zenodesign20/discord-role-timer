import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import json
import os

# ================= CONFIG =================
TOKEN = os.getenv("DISCORD_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

DATA_FILE = "members.json"
TOTAL_DAYS = 30

GIF_THUMBNAIL = "https://cdn.discordapp.com/attachments/1468621028598087843/1471249375706746890/Black_White_Minimalist_Animation_Logo_Video_1.gif"

ROLE_PACKAGES = {
    "VIP": {"price": 200, "days": 30},
    "Gold": {"price": 100, "days": 30},
}

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ================= UTILS =================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def parse_date(date_str):
    return datetime.datetime.strptime(date_str, "%d/%m/%y").date()

def calc_expire_date(start_date):
    return start_date + datetime.timedelta(days=29)

def package_from_role(role: discord.Role):
    for key, pack in ROLE_PACKAGES.items():
        if role and role.name.startswith(key):
            return f"{key} | ราคา {pack['price']} บาท | จำนวน {pack['days']} วัน"
    return "-"

def format_remaining(seconds: int):
    if seconds < 0:
        seconds = 0
    d, seconds = divmod(seconds, 86400)
    h, seconds = divmod(seconds, 3600)
    m, s = divmod(seconds, 60)
    return f"{d} วัน / {h} ชม / {m} นาที / {s} วินาที"

def progress_bar(start_ts, expire_ts):
    now = datetime.datetime.utcnow().timestamp()
    total = expire_ts - start_ts
    passed = now - start_ts
    ratio = min(max(passed / total, 0), 1)
    filled = int(ratio * 10)
    return "🟩" * filled + "⬜" * (10 - filled)

# ================= EMBED =================
def build_embed(member: discord.Member, info: dict):
    now_ts = datetime.datetime.utcnow().timestamp()

    start_ts = info["start_ts"]
    expire_ts = info["expire_ts"]

    remaining_sec = int(expire_ts - now_ts)
    role = member.guild.get_role(info["role_id"])

    start_dt = datetime.datetime.utcfromtimestamp(start_ts)
    expire_dt = datetime.datetime.utcfromtimestamp(expire_ts)

    embed = discord.Embed(
        title="👑 สถานะสมาชิก",
        color=discord.Color.gold()
    )

    embed.set_thumbnail(url=GIF_THUMBNAIL)

    embed.add_field(name="👤 ผู้รับ Role", value=member.mention, inline=False)
    embed.add_field(name="🎭 Role", value=role.mention if role else "-", inline=False)
    embed.add_field(name="📅 วันที่สมัคร", value=start_dt.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="💎 แพ็กเกจ", value=package_from_role(role), inline=False)
    embed.add_field(name="🗓 วันหมดอายุ", value=expire_dt.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="⏳ เวลาที่เหลือ", value=format_remaining(remaining_sec), inline=False)
    embed.add_field(name="📊 Progress", value=progress_bar(start_ts, expire_ts), inline=False)

    embed.set_footer(text="MEMBER SYSTEM • 30 DAYS")
    return embed

# ================= VIEW =================
class AdminView(discord.ui.View):
    def __init__(self, member_id):
        super().__init__(timeout=None)
        self.member_id = member_id

    @discord.ui.button(label="🗑️ ลบสมาชิก", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ เฉพาะแอดมิน", ephemeral=True)
            return

        data = load_data()
        if self.member_id in data:
            del data[self.member_id]
            save_data(data)
            await interaction.response.send_message("🗑️ ลบข้อมูลเรียบร้อย", ephemeral=True)

# ================= COMMAND =================
@bot.tree.command(name="setrole", description="เพิ่มสมาชิก (30 วัน)")
@app_commands.describe(
    member="ผู้รับ Role",
    role="Role",
    start_date="วันที่สมัคร (DD/MM/YY)"
)
async def setrole(interaction: discord.Interaction, member: discord.Member, role: discord.Role, start_date: str):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("❌ สำหรับแอดมินเท่านั้น", ephemeral=True)
        return

    try:
        start_date = parse_date(start_date)
    except:
        await interaction.response.send_message("❌ รูปแบบวันที่ไม่ถูกต้อง", ephemeral=True)
        return

    expire_date = calc_expire_date(start_date)

    start_ts = datetime.datetime.combine(start_date, datetime.time.min).timestamp()
    expire_ts = datetime.datetime.combine(expire_date, datetime.time.max).timestamp()

    await member.add_roles(role)

    info = {
        "role_id": role.id,
        "start_ts": start_ts,
        "expire_ts": expire_ts,
        "warned": False
    }

    await interaction.response.send_message(
        embed=build_embed(member, info),
        view=AdminView(str(member.id))
    )

    msg = await interaction.original_response()

    info["channel_id"] = msg.channel.id
    info["message_id"] = msg.id

    data = load_data()
    data[str(member.id)] = info
    save_data(data)

    try:
        await member.send("👑 คุณได้รับ Role สมาชิกเรียบร้อย")
        admin = await bot.fetch_user(ADMIN_ID)
        await admin.send(f"✅ เพิ่ม Role ให้ {member}")
    except:
        pass

# ================= AUTO REFRESH =================
@tasks.loop(seconds=1)
async def auto_refresh():
    data = load_data()
    now_ts = datetime.datetime.utcnow().timestamp()
    changed = False

    for uid, info in list(data.items()):
        member = None
        for guild in bot.guilds:
            member = guild.get_member(int(uid))
            if member:
                break
        if not member:
            continue

        expire_ts = info["expire_ts"]

        if now_ts >= expire_ts:
            role = member.guild.get_role(info["role_id"])
            if role:
                await member.remove_roles(role)

            try:
                ch = bot.get_channel(info["channel_id"])
                msg = await ch.fetch_message(info["message_id"])
                await msg.delete()
            except:
                pass

            del data[uid]
            changed = True
            continue

        # warn 3 days
        if not info["warned"] and int((expire_ts - now_ts) // 86400) == 3:
            try:
                await member.send("⏰ สมาชิกของคุณจะหมดอายุในอีก 3 วัน")
            except:
                pass
            info["warned"] = True
            changed = True

        # refresh embed
        try:
            ch = bot.get_channel(info["channel_id"])
            msg = await ch.fetch_message(info["message_id"])
            await msg.edit(embed=build_embed(member, info))
        except:
            pass

    if changed:
        save_data(data)

# ================= READY =================
@bot.event
async def on_ready():
    await bot.tree.sync()
    auto_refresh.start()
    print("👑 BOT ONLINE")

bot.run(TOKEN)
