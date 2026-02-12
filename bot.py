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

# ================= UTIL =================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def parse_date(d):
    return datetime.datetime.strptime(d, "%d/%m/%y").date()

def expire_date(start):
    return start + datetime.timedelta(days=29)

def format_remaining(td):
    if td.total_seconds() < 0:
        td = datetime.timedelta(seconds=0)
    d, r = divmod(int(td.total_seconds()), 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    return f"{d} วัน / {h} ชม / {m} นาที / {s} วินาที"

def progress(start_dt, end_dt):
    total = (end_dt - start_dt).total_seconds()
    passed = (datetime.datetime.now() - start_dt).total_seconds()
    ratio = min(max(passed / total, 0), 1)
    bar = int(ratio * 10)
    return "🟩" * bar + "⬜" * (10 - bar)

def package_from_role(role):
    for k in ROLE_PACKAGES:
        if role.name.startswith(k):
            p = ROLE_PACKAGES[k]
            return f"{k} | ราคา {p['price']} บาท | จำนวน {p['days']} วัน"
    return role.name

# ================= EMBED =================
def build_embed(member, data):
    role = member.guild.get_role(data["role_id"])
    start = datetime.date.fromisoformat(data["start_date"])
    expire = datetime.date.fromisoformat(data["expire_date"])

    start_dt = datetime.datetime.combine(start, datetime.time.min)
    expire_dt = datetime.datetime.combine(expire, datetime.time.max)

    embed = discord.Embed(title="👑 สถานะสมาชิก", color=discord.Color.gold())
    embed.set_thumbnail(url=GIF_THUMBNAIL)

    embed.add_field(name="👤 ผู้รับ Role", value=member.mention, inline=False)
    embed.add_field(name="🎭 Role", value=role.mention, inline=False)
    embed.add_field(name="📅 วันที่สมัคร", value=start.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="💎 แพ็กเกจ", value=package_from_role(role), inline=False)
    embed.add_field(name="🗓 วันหมดอายุ", value=expire.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(
        name="⏳ เวลาที่เหลือ",
        value=format_remaining(expire_dt - datetime.datetime.now()),
        inline=False
    )
    embed.add_field(
        name="📊 Progress",
        value=progress(start_dt, expire_dt),
        inline=False
    )
    embed.set_footer(text="MEMBER SYSTEM • 30 DAYS")
    return embed

# ================= COMMAND =================
@bot.tree.command(name="setrole")
async def setrole(interaction: discord.Interaction, member: discord.Member, role: discord.Role, start_date: str):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("❌ Admin only", ephemeral=True)
        return

    start = parse_date(start_date)
    expire = expire_date(start)

    await member.add_roles(role)

    data = load_data()
    payload = {
        "role_id": role.id,
        "start_date": start.isoformat(),
        "expire_date": expire.isoformat(),
        "warned": False
    }

    msg = await interaction.response.send_message(
        embed=build_embed(member, payload),
        fetch_response=True
    )

    payload["channel_id"] = msg.channel.id
    payload["message_id"] = msg.id

    data[str(member.id)] = payload
    save_data(data)

    try:
        await member.send("👑 คุณได้รับ Role เรียบร้อย")
        admin = await bot.fetch_user(ADMIN_ID)
        await admin.send(f"✅ แอด Role ให้ {member}")
    except:
        pass

# ================= AUTO TASK =================
@tasks.loop(minutes=1)
async def auto_refresh():
    data = load_data()
    now = datetime.datetime.now()
    changed = False

    for uid, info in list(data.items()):
        user = bot.get_user(int(uid))
        if not user:
            continue

        expire = datetime.date.fromisoformat(info["expire_date"])
        expire_dt = datetime.datetime.combine(expire, datetime.time.max)

        # refresh embed
        try:
            ch = bot.get_channel(info["channel_id"])
            msg = await ch.fetch_message(info["message_id"])
            await msg.edit(embed=build_embed(user, info))
        except:
            pass

        # warn 3 days
        if not info["warned"] and (expire_dt - now).days == 3:
            try:
                await user.send("⏰ สมาชิกของคุณจะหมดอายุในอีก 3 วัน")
            except:
                pass
            info["warned"] = True
            changed = True

        # expire → delete embed
        if now > expire_dt:
            try:
                ch = bot.get_channel(info["channel_id"])
                msg = await ch.fetch_message(info["message_id"])
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
