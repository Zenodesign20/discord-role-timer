import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import json
import os

# ================= CONFIG =================
TOKEN = os.getenv("DISCORD_TOKEN")
ADMIN_ID = 1392851942480412822

DATA_FILE = "members.json"
TOTAL_DAYS = 30

GIF_THUMBNAIL = "https://cdn.discordapp.com/attachments/1468621028598087843/1471249375706746890/Black_White_Minimalist_Animation_Logo_Video_1.gif"

# ผูกแพ็กกับ Role (ใช้แสดงผลอย่างเดียว ❌ไม่เอาไปคำนวณ)
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

def parse_date(date_str: str):
    return datetime.datetime.strptime(date_str, "%d/%m/%y").date()

def format_remaining(td: datetime.timedelta):
    if td.total_seconds() < 0:
        td = datetime.timedelta(seconds=0)
    sec = int(td.total_seconds())
    d, sec = divmod(sec, 86400)
    h, sec = divmod(sec, 3600)
    m, s = divmod(sec, 60)
    return f"{d} วัน / {h} ชม / {m} นาที / {s} วินาที"

def progress_bar(start_dt, end_dt):
    total = (end_dt - start_dt).total_seconds()
    passed = (datetime.datetime.now() - start_dt).total_seconds()
    ratio = min(max(passed / total, 0), 1)
    blocks = 20
    filled = int(ratio * blocks)
    return "🟩" * filled + "⬜" * (blocks - filled)

def package_from_role(role: discord.Role):
    if not role:
        return "-"
    for key, pack in ROLE_PACKAGES.items():
        if role.name.startswith(key):
            return f"{key} | ราคา {pack['price']} บาท | จำนวน {pack['days']} วัน"
    return role.name

# ================= EMBED =================
def build_embed(member: discord.Member, info: dict):
    guild = member.guild
    role = guild.get_role(info["role_id"])

    start_dt = datetime.datetime.fromtimestamp(info["start_ts"])
    expire_dt = datetime.datetime.fromtimestamp(info["expire_ts"])
    now = datetime.datetime.now()

    embed = discord.Embed(
        title="👑 สถานะสมาชิก",
        color=discord.Color.gold()
    )

    embed.set_thumbnail(url=GIF_THUMBNAIL)

    embed.add_field(name="👤 ผู้รับ Role", value=member.mention, inline=False)
    embed.add_field(name="🎭 Role", value=role.mention if role else "-", inline=False)

    embed.add_field(
        name="📅 วันที่สมัคร",
        value=start_dt.strftime("%d/%m/%Y"),
        inline=True
    )

    embed.add_field(
        name="💎 แพ็กเกจ",
        value=package_from_role(role),
        inline=False
    )

    embed.add_field(
        name="🗓 วันหมดอายุ",
        value=expire_dt.strftime("%d/%m/%Y"),
        inline=True
    )

    embed.add_field(
        name="⏳ เวลาที่เหลือ",
        value=format_remaining(expire_dt - now),
        inline=False
    )

    embed.add_field(
        name="📊 Progress",
        value=progress_bar(start_dt, expire_dt),
        inline=False
    )

    embed.set_footer(text="MEMBER SYSTEM • REAL-TIME")
    return embed

# ================= ADMIN VIEW =================
class AdminView(discord.ui.View):
    def __init__(self, member_id: str):
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
            await interaction.response.send_message("🗑️ ลบข้อมูลสมาชิกเรียบร้อย", ephemeral=True)
        else:
            await interaction.response.send_message("❌ ไม่พบข้อมูล", ephemeral=True)

# ================= COMMAND =================
@bot.tree.command(name="setrole", description="เพิ่มสมาชิก (แพ็ก 30 วัน)")
@app_commands.describe(
    member="ผู้รับ Role",
    role="Role",
    start_date="วันที่สมัคร (DD/MM/YY)"
)
async def setrole(interaction: discord.Interaction, member: discord.Member, role: discord.Role, start_date: str):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("❌ คำสั่งนี้สำหรับแอดมินเท่านั้น", ephemeral=True)
        return

    try:
        base_date = parse_date(start_date)
    except:
        await interaction.response.send_message("❌ รูปแบบวันที่ต้องเป็น DD/MM/YY", ephemeral=True)
        return

    # ใช้เวลา real-time (สำคัญมาก)
    start_dt = datetime.datetime.combine(base_date, datetime.datetime.now().time())
    expire_dt = start_dt + datetime.timedelta(days=29, hours=23, minutes=59, seconds=59)

    await member.add_roles(role)

    info = {
        "role_id": role.id,
        "start_ts": start_dt.timestamp(),
        "expire_ts": expire_dt.timestamp(),
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

    # DM แจ้ง
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
    now = datetime.datetime.now()
    changed = False

    for uid, info in list(data.items()):
        member = bot.get_user(int(uid))
        if not member:
            continue

        expire_dt = datetime.datetime.fromtimestamp(info["expire_ts"])

        # ⏰ เตือนก่อนหมด 3 วัน
        if not info["warned"] and (expire_dt - now).days == 3:
            try:
                await member.send("⏰ สมาชิกของคุณจะหมดอายุในอีก 3 วัน")
            except:
                pass
            info["warned"] = True
            changed = True

        # ❌ หมดอายุ
        if now >= expire_dt:
            for g in bot.guilds:
                m = g.get_member(int(uid))
                if m:
                    role = g.get_role(info["role_id"])
                    if role:
                        await m.remove_roles(role)

            try:
                ch = bot.get_channel(info["channel_id"])
                msg = await ch.fetch_message(info["message_id"])
                await msg.delete()
            except:
                pass

            del data[uid]
            changed = True
            continue

        # 🔄 refresh เฉพาะที่ยังไม่หมดอายุ
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
