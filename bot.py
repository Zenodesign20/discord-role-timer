import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, date, timedelta, timezone
import json
import os
import hashlib
import asyncio

# ================= CONFIG =================
TOKEN = os.getenv("DISCORD_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1392851942480412822"))
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

data_lock = asyncio.Lock()
last_hash = None

# ================= DATA =================
async def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    async with data_lock:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

async def save_data(data):
    async with data_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

def hash_data(data):
    return hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()

# ================= TIME =================
def parse_date(date_str: str) -> date:
    return datetime.strptime(date_str, "%d/%m/%y").date()

def calc_expire(start_date: date) -> date:
    return start_date + timedelta(days=29)

# ================= PACKAGE =================
def package_from_role(role: discord.Role) -> str:
    if not role:
        return "-"
    for key, pack in ROLE_PACKAGES.items():
        if role.name.startswith(key):
            return f"{key} | ราคา {pack['price']} บาท | จำนวน {pack['days']} วัน"
    return role.name

# ================= EMBED =================
def build_embed(member: discord.Member, info: dict) -> discord.Embed:
    role = member.guild.get_role(info["role_id"])
    start_date = date.fromisoformat(info["start_date"])
    expire_date = date.fromisoformat(info["expire_date"])

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

    embed.set_footer(text="MEMBER SYSTEM • 30 DAYS")
    return embed

# ================= VIEW =================
class AdminView(discord.ui.View):
    def __init__(self, member_id: str):
        super().__init__(timeout=None)
        self.member_id = member_id

    @discord.ui.button(label="🗑️ ลบสมาชิก", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ เฉพาะแอดมิน", ephemeral=True)
            return

        data = await load_data()
        if self.member_id in data:
            del data[self.member_id]
            await save_data(data)
            await interaction.message.delete()
            await interaction.response.send_message("🗑️ ลบข้อมูลสมาชิกเรียบร้อย", ephemeral=True)

# ================= COMMAND =================
@bot.tree.command(name="setrole", description="เพิ่มสมาชิก (30 วัน)")
async def setrole(interaction: discord.Interaction, member: discord.Member, role: discord.Role, start_date: str):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("❌ สำหรับแอดมินเท่านั้น", ephemeral=True)
        return

    try:
        start = parse_date(start_date)
    except:
        await interaction.response.send_message("❌ วันที่ต้องเป็น DD/MM/YY", ephemeral=True)
        return

    expire = calc_expire(start)
    await member.add_roles(role)

    info = {
        "guild_id": interaction.guild.id,
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

    data = await load_data()
    data[str(member.id)] = info
    await save_data(data)

    try:
        await member.send("👑 คุณได้รับ Role สมาชิกเรียบร้อยแล้ว")
        admin = await bot.fetch_user(ADMIN_ID)
        await admin.send(f"✅ เพิ่ม Role ให้ {member}")
    except:
        pass

# ================= SMART REFRESH =================
@tasks.loop(seconds=15)
async def monitor_changes():
    global last_hash

    data = await load_data()
    current_hash = hash_data(data)

    if last_hash is None:
        last_hash = current_hash
        return

    if current_hash == last_hash:
        return

    last_hash = current_hash

    for uid, info in data.items():
        guild = bot.get_guild(info["guild_id"])
        if not guild:
            continue

        member = guild.get_member(int(uid))
        if not member:
            continue

        try:
            channel = bot.get_channel(info["channel_id"])
            msg = await channel.fetch_message(info["message_id"])
            await msg.edit(embed=build_embed(member, info))
        except:
            pass

# ================= EXPIRE =================
@tasks.loop(minutes=1)
async def check_expired():
    data = await load_data()
    now = datetime.now(timezone.utc)
    changed = False

    for uid, info in list(data.items()):
        guild = bot.get_guild(info["guild_id"])
        if not guild:
            continue

        member = guild.get_member(int(uid))
        role = guild.get_role(info["role_id"])

        expire_date = date.fromisoformat(info["expire_date"])
        expire_dt = datetime.combine(expire_date, datetime.max.time(), tzinfo=timezone.utc)

        if now >= expire_dt:
            try:
                if member and role:
                    await member.remove_roles(role)
                    await member.send("⛔ Role สมาชิกของคุณหมดอายุแล้ว")
                    admin = await bot.fetch_user(ADMIN_ID)
                    await admin.send(f"⛔ Role ของ {member} หมดอายุแล้ว")
            except:
                pass

            try:
                channel = bot.get_channel(info["channel_id"])
                msg = await channel.fetch_message(info["message_id"])
                await msg.delete()
            except:
                pass

            del data[uid]
            changed = True
            continue

        if not info["warned"] and (expire_dt - now).days == 3:
            try:
                await member.send("⏰ สมาชิกของคุณจะหมดอายุในอีก 3 วัน")
                admin = await bot.fetch_user(ADMIN_ID)
                await admin.send(f"⚠ {member} จะหมดอายุในอีก 3 วัน")
            except:
                pass
            info["warned"] = True
            changed = True

    if changed:
        await save_data(data)

# ================= READY =================
@bot.event
async def on_ready():
    await bot.tree.sync()
    monitor_changes.start()
    check_expired.start()
    print("👑 BOT ONLINE - ULTIMATE VERSION")

bot.run(TOKEN)