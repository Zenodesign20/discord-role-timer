import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import datetime
import json
import os

# ================= CONFIG =================
TOKEN = os.getenv("DISCORD_TOKEN")
ADMIN_ID = 1392851942480412822
DATA_FILE = "roles.json"
LOGO_URL = "https://cdn.discordapp.com/attachments/1468621028598087843/1471249375706746890/Black_White_Minimalist_Animation_Logo_Video_1.gif?ex=698ee801&is=698d9681&hm=193acbc25aaa2da001605dd84fc0bfc2472fd8a0ebb0da321ac7c93a0edad888&"

ROLE_CONFIG = {
    "VIP":  {"price": 200, "days": 30},
    "GOLD": {"price": 100, "days": 30},
}

# ================= BOT =================
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ================= DATABASE =================
def load_data():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# ================= UTILS =================
def parse_date(d):
    return datetime.datetime.strptime(d, "%d/%m/%y")

def format_countdown(sec):
    sec = int(sec)
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h} ชม / {m} นาที / {s} วินาที"

def progress_bar(percent, tick):
    total = 20
    fill = int(total * percent)
    bar = ["🟩"] * fill + ["⬛"] * (total - fill)
    bar[tick % total] = "⚡"
    return "".join(bar)

def get_color(p):
    if p <= 0.15:
        return 0xFF3B3B
    elif p <= 0.5:
        return 0xFFD93D
    return 0x3EF2C5

# ================= EMBED =================
def build_embed(data, remaining, tick):
    percent = remaining / data["total_seconds"]
    embed = discord.Embed(
        title="📅 Check Member Time",
        color=get_color(percent)
    )

    embed.add_field(
        name="📌 วันที่ลงทะเบียน",
        value=data["register_date"],
        inline=False
    )

    embed.add_field(
        name="👤 Member",
        value=f"{data['member_name']} | ราคา {data['price']} บาท | {data['days']} วัน",
        inline=False
    )

    embed.add_field(
        name="⏳ วันหมดอายุ",
        value=f"<t:{int(data['expire_ts'])}:F>",
        inline=False
    )

    embed.add_field(
        name="🗓 วันที่เหลือ",
        value=f"[ {int(remaining//86400)} ] วัน",
        inline=False
    )

    embed.add_field(
        name="⏱ Countdown",
        value=f"```{format_countdown(remaining)}```",
        inline=False
    )

    embed.add_field(
        name="📊 Progress",
        value=f"{progress_bar(percent, tick)} {int(percent*100)}%",
        inline=False
    )

    embed.set_image(url=LOGO_URL)
    embed.set_footer(text="👑 ADMINZENO • GOD MODE")
    return embed

# ================= VIEW (BUTTONS) =================
class ControlView(discord.ui.View):
    def __init__(self, data):
        super().__init__(timeout=None)
        self.data = data

    @discord.ui.button(label="❌ ยกเลิก Member", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ Admin เท่านั้น", ephemeral=True)
            return

        guild = interaction.guild
        member = guild.get_member(self.data["member_id"])
        role = guild.get_role(self.data["role_id"])

        try:
            await member.remove_roles(role)
        except:
            pass

        db = load_data()
        save_data([d for d in db if d["id"] != self.data["id"]])

        embed = discord.Embed(
            title="❌ MEMBER CANCELED",
            description="รายการนี้ถูกยกเลิกแล้ว",
            color=0xFF0000
        )
        await interaction.response.edit_message(embed=embed, view=None)

# ================= TIMER =================
async def role_timer(data):
    tick = 0

    while True:
        now = datetime.datetime.now().timestamp()
        remaining = data["expire_ts"] - now

        guild = bot.get_guild(data["guild_id"])
        channel = guild.get_channel(data["channel_id"])
        member = guild.get_member(data["member_id"])
        role = guild.get_role(data["role_id"])

        if remaining <= 0:
            try:
                await member.remove_roles(role)
                await member.send(f"⛔ Role {role.name} หมดอายุแล้ว")
                await bot.fetch_user(ADMIN_ID).send(
                    f"⛔ {member.name} หมดอายุ {role.name}"
                )
            except:
                pass

            db = load_data()
            save_data([d for d in db if d["id"] != data["id"]])
            break

        if remaining <= 259200 and not data.get("warned"):
            try:
                await member.send("⚠️ Role ของคุณใกล้หมดอายุ (3 วัน)")
                await bot.fetch_user(ADMIN_ID).send(
                    f"⚠️ {member.name} ใกล้หมดอายุ {role.name}"
                )
            except:
                pass

            data["warned"] = True
            db = load_data()
            for d in db:
                if d["id"] == data["id"]:
                    d["warned"] = True
            save_data(db)

        msg = await channel.fetch_message(data["message_id"])
        embed = build_embed(data, remaining, tick)
        await msg.edit(embed=embed, view=ControlView(data))

        tick += 1
        await asyncio.sleep(10)

# ================= COMMAND =================
@bot.tree.command(name="setrole", description="Set Member Role with Timer")
@app_commands.describe(
    member="สมาชิก",
    role="Role",
    register_date="วันที่สมัคร DD/MM/YY"
)
async def setrole(
    interaction: discord.Interaction,
    member: discord.Member,
    role: discord.Role,
    register_date: str
):
    role_key = role.name.split("|")[0].strip().upper()
    if role_key not in ROLE_CONFIG:
        await interaction.response.send_message("❌ Role นี้ไม่มีในระบบ", ephemeral=True)
        return

    cfg = ROLE_CONFIG[role_key]
    reg = parse_date(register_date)
    expire = reg + datetime.timedelta(days=cfg["days"])

    await member.add_roles(role)

    data = {
        "id": int(datetime.datetime.now().timestamp()),
        "guild_id": interaction.guild.id,
        "channel_id": interaction.channel.id,
        "member_id": member.id,
        "role_id": role.id,
        "member_name": role_key,
        "price": cfg["price"],
        "days": cfg["days"],
        "register_date": register_date,
        "expire_ts": expire.timestamp(),
        "total_seconds": cfg["days"] * 86400,
        "warned": False
    }

    embed = build_embed(data, data["total_seconds"], 0)
    await interaction.response.send_message(embed=embed, view=ControlView(data))
    msg = await interaction.original_response()
    data["message_id"] = msg.id

    db = load_data()
    db.append(data)
    save_data(db)

    # DM แจ้งทันที
    try:
        await member.send(
            f"🎉 คุณได้รับ {role.name}\n"
            f"📅 สมัคร: {register_date}\n"
            f"⏳ หมดอายุ: {expire.strftime('%d/%m/%y')}"
        )
        await bot.fetch_user(ADMIN_ID).send(
            f"✅ เพิ่ม {role.name} ให้ {member.name} แล้ว"
        )
    except:
        pass

    bot.loop.create_task(role_timer(data))

# ================= READY =================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print("👑 BOT ONLINE")
    for d in load_data():
        bot.loop.create_task(role_timer(d))

bot.run(TOKEN)
