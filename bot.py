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
        json.dump(data, f, ensure_ascii=False, indent=2)

def parse_date(date_str):
    return datetime.datetime.strptime(date_str, "%d/%m/%y").date()

def calc_expire(start_date):
    return start_date + datetime.timedelta(days=29)

def format_remaining(td):
    if td.total_seconds() <= 0:
        return "0 วัน / 0 ชม / 0 นาที / 0 วินาที"
    sec = int(td.total_seconds())
    d, sec = divmod(sec, 86400)
    h, sec = divmod(sec, 3600)
    m, s = divmod(sec, 60)
    return f"{d} วัน / {h} ชม / {m} นาที / {s} วินาที"

def progress_bar(start_dt, end_dt):
    total = (end_dt - start_dt).total_seconds()
    elapsed = (datetime.datetime.now() - start_dt).total_seconds()
    ratio = min(max(elapsed / total, 0), 1)
    filled = int(ratio * 10)
    return "🟩" * filled + "⬜" * (10 - filled)

def package_from_role(role):
    for key, pack in ROLE_PACKAGES.items():
        if role.name.startswith(key):
            return f"{key} | ราคา {pack['price']} บาท | จำนวน {pack['days']} วัน"
    return role.name

# ================= EMBED =================
def build_embed(member, info):
    guild = member.guild
    role = guild.get_role(info["role_id"])

    start_date = datetime.date.fromisoformat(info["start_date"])
    expire_date = datetime.date.fromisoformat(info["expire_date"])

    start_dt = datetime.datetime.combine(start_date, datetime.time.min)
    expire_dt = datetime.datetime.combine(expire_date, datetime.time.max)

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
    embed.add_field(
        name="⏳ เวลาที่เหลือ",
        value=format_remaining(expire_dt - datetime.datetime.now()),
        inline=False
    )
    embed.add_field(
        name="📊 Progress",
        value=progress_bar(start_dt, expire_dt),
        inline=False
    )

    embed.set_footer(text="MEMBER SYSTEM • 30 DAYS")
    return embed

# ================= VIEW =================
class AdminView(discord.ui.View):
    def __init__(self, uid):
        super().__init__(timeout=None)
        self.uid = uid

    @discord.ui.button(label="🗑️ ลบสมาชิก", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ เฉพาะแอดมิน", ephemeral=True)
            return

        data = load_data()
        if self.uid in data:
            del data[self.uid]
            save_data(data)
            await interaction.response.send_message("🗑️ ลบข้อมูลเรียบร้อย", ephemeral=True)

# ================= COMMAND =================
@bot.tree.command(name="setrole", description="เพิ่มสมาชิก (30 วัน)")
async def setrole(interaction: discord.Interaction, member: discord.Member, role: discord.Role, start_date: str):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("❌ เฉพาะแอดมิน", ephemeral=True)
        return

    start = parse_date(start_date)
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

        expire_date = datetime.date.fromisoformat(info["expire_date"])
        expire_dt = datetime.datetime.combine(expire_date, datetime.time.max)

        # ❌ หมดอายุ → ลบ Role + ลบ Embed + ลบข้อมูล
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

        # 🔔 เตือนก่อนหมด 3 วัน
        if not info["warned"] and (expire_dt - now).days == 3:
            try:
                await member.send("⏰ สมาชิกของคุณจะหมดอายุในอีก 3 วัน")
            except:
                pass
            info["warned"] = True
            changed = True

        # 🔄 Refresh เฉพาะที่ยังไม่หมด
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
