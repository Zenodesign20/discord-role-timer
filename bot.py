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

UTC = datetime.timezone.utc

# ================= DATA =================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# ================= TIME =================
def parse_date(date_str):
    return datetime.datetime.strptime(date_str, "%d/%m/%y").date()

def calc_expire(start_date):
    return start_date + datetime.timedelta(days=29)

def format_remaining(td):
    if td.total_seconds() < 0:
        td = datetime.timedelta(seconds=0)

    sec = int(td.total_seconds())
    d, sec = divmod(sec, 86400)
    h, sec = divmod(sec, 3600)
    m, s = divmod(sec, 60)

    return f"{d} วัน / {h} ชม / {m} นาที / {s} วินาที"

# ================= PROGRESS =================
def fancy_progress_bar(start_dt, end_dt):
    now = datetime.datetime.now(UTC)

    total = (end_dt - start_dt).total_seconds()
    passed = (now - start_dt).total_seconds()

    ratio = max(0.0, min(passed / total, 1.0))
    percent = int(ratio * 100)

    BAR_LEN = 20
    blocks = ["▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]

    filled = ratio * BAR_LEN
    full = int(filled)
    rem = filled - full

    bar = "█" * full
    if full < BAR_LEN:
        bar += blocks[int(rem * (len(blocks) - 1))]
        bar += "─" * (BAR_LEN - full - 1)

    if percent < 70:
        color = "🟩"
    elif percent < 90:
        color = "🟨"
    else:
        color = "🟥"

    pulse = ""
    if percent >= 90 and int(now.timestamp()) % 2 == 0:
        pulse = " ✨"

    return f"{color} `{bar}` **{percent}%**{pulse}"

# ================= PACKAGE =================
def package_from_role(role):
    for key, pack in ROLE_PACKAGES.items():
        if role.name.startswith(key):
            return f"{key} | ราคา {pack['price']} บาท | จำนวน {pack['days']} วัน"
    return role.name

# ================= EMBED =================
def build_embed(member, info):
    role = member.guild.get_role(info["role_id"])

    start_date = datetime.date.fromisoformat(info["start_date"])
    expire_date = datetime.date.fromisoformat(info["expire_date"])

    start_dt = datetime.datetime.combine(start_date, datetime.time.min, tzinfo=UTC)
    expire_dt = datetime.datetime.combine(expire_date, datetime.time.max, tzinfo=UTC)
    now = datetime.datetime.now(UTC)

    embed = discord.Embed(
        title="👑 สถานะสมาชิก",
        color=discord.Color.gold()
    )

    embed.set_thumbnail(url=GIF_THUMBNAIL)

    embed.add_field(name="👤 ผู้รับ Role", value=member.mention, inline=False)
    embed.add_field(name="🎭 Role", value=role.mention if role else "-", inline=False)
    embed.add_field(name="📅 วันที่สมัคร", value=start_date.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="💎 แพ็กเกจ", value=package_from_role(role), inline=False)
    embed.add_field(name="🗓 วันหมดอายุ", value=expire_date.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="⏳ เวลาที่เหลือ", value=format_remaining(expire_dt - now), inline=False)
    embed.add_field(name="📊 Progress", value=fancy_progress_bar(start_dt, expire_dt), inline=False)

    embed.set_footer(text="MEMBER SYSTEM • 30 DAYS")
    return embed

# ================= ADMIN VIEW =================
class AdminView(discord.ui.View):
    def __init__(self, member_id):
        super().__init__(timeout=None)
        self.member_id = member_id

    @discord.ui.button(label="🗑️ ลบสมาชิก", style=discord.ButtonStyle.danger)
    async def delete(self, interaction, button):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ เฉพาะแอดมิน", ephemeral=True)
            return

        data = load_data()
        if self.member_id in data:
            del data[self.member_id]
            save_data(data)
            await interaction.response.send_message("🗑️ ลบข้อมูลแล้ว", ephemeral=True)

# ================= COMMAND =================
@bot.tree.command(name="setrole", description="เพิ่มสมาชิก (30 วัน)")
@app_commands.describe(
    member="ผู้รับ Role",
    role="Role",
    start_date="วันที่สมัคร (DD/MM/YY)"
)
async def setrole(interaction, member, role, start_date):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("❌ สำหรับแอดมินเท่านั้น", ephemeral=True)
        return

    try:
        start = parse_date(start_date)
    except:
        await interaction.response.send_message("❌ รูปแบบวันที่ผิด", ephemeral=True)
        return

    expire = calc_expire(start)
    await member.add_roles(role)

    info = {
        "role_id": role.id,
        "start_date": start.isoformat(),
        "expire_date": expire.isoformat(),
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

# ================= AUTO TASK =================
@tasks.loop(seconds=5)
async def auto_refresh():
    data = load_data()
    now = datetime.datetime.now(UTC)
    changed = False

    for uid, info in list(data.items()):
        channel = bot.get_channel(info["channel_id"])
        if not channel:
            continue

        guild = channel.guild
        member = guild.get_member(int(uid))
        role = guild.get_role(info["role_id"])

        expire = datetime.date.fromisoformat(info["expire_date"])
        expire_dt = datetime.datetime.combine(expire, datetime.time.max, tzinfo=UTC)

        if now <= expire_dt:
            try:
                msg = await channel.fetch_message(info["message_id"])
                if member:
                    await msg.edit(embed=build_embed(member, info))
            except:
                pass

        if not info["warned"] and (expire_dt - now).days == 3:
            try:
                if member:
                    await member.send("⏰ สมาชิกของคุณจะหมดอายุในอีก 3 วัน")
            except:
                pass
            info["warned"] = True
            changed = True

        if now > expire_dt:
            try:
                if member and role:
                    await member.remove_roles(role)

                msg = await channel.fetch_message(info["message_id"])
                await msg.delete()
            except:
                pass

            del data[uid]
            changed = True

    if changed:
        save_data(data)

# ================= READY =================
@bot.event
async def on_ready():
    await bot.tree.sync()
    auto_refresh.start()
    print("👑 BOT ONLINE")

bot.run(TOKEN)
