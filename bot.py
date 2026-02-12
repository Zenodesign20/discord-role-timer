import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import datetime
import os
import json
import re

TOKEN = os.getenv("DISCORD_TOKEN")
ADMIN_ID = 1392851942480412822
DATA_FILE = "roles.json"
LOGO_URL = "https://cdn.phototourl.com/uploads/2026-02-11-5a3eeb2d-d2bf-4821-9742-bdcf3c4d9540.gif"

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# DATABASE
# =========================
def load_data():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# =========================
# TIME PARSER
# =========================
def parse_time(t):
    m = re.match(r"(\d+)([smhd])", t.lower())
    if not m:
        return None
    v, u = int(m.group(1)), m.group(2)
    return v * {"s":1,"m":60,"h":3600,"d":86400}[u]

def format_digital(sec):
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02}:{m:02}:{s:02}"

# =========================
# PROGRESS BAR
# =========================
def progress_bar(percent, tick):
    total = 20
    fill = int(total * percent)
    bar = ["🟩" if i < fill else "⬛" for i in range(total)]
    bar[tick % total] = "⚡"
    return "".join(bar)

# =========================
# EMBED
# =========================
def build_embed(member, role, expire, remain, total, note, tick):
    percent = max(remain / total, 0)
    embed = discord.Embed(
        title="📅 Check member time!",
        description="Zeno Community • Time Member",
        color=discord.Color.green()
    )

    embed.add_field(name="👤 Member", value=member.mention, inline=False)
    embed.add_field(name="🏷 Role", value=role.mention, inline=False)
    embed.add_field(name="📝 Note", value=note, inline=False)
    embed.add_field(
        name="🕒 Expire",
        value=f"<t:{int(expire.timestamp())}:F>",
        inline=False
    )
    embed.add_field(
        name="⏱ Countdown",
        value=f"```{format_digital(int(remain))}```",
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

# =========================
# CANCEL VIEW (PERSISTENT)
# =========================
class CancelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="❌ ยกเลิก",
        style=discord.ButtonStyle.danger,
        custom_id="cancel_role_timer"
    )
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_data()
        data = next((r for r in db if r["message_id"] == interaction.message.id), None)

        if not data:
            await interaction.response.send_message("❌ ไม่พบข้อมูล", ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Admin เท่านั้น", ephemeral=True)
            return

        guild = interaction.guild
        member = guild.get_member(data["member_id"])
        role = guild.get_role(data["role_id"])

        if member and role:
            await member.remove_roles(role)

        db = [r for r in db if r["message_id"] != interaction.message.id]
        save_data(db)

        embed = discord.Embed(
            title="❌ ยกเลิกเรียบร้อย",
            description="Role และ Timer ถูกลบแล้ว",
            color=discord.Color.red()
        )
        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.defer()

# =========================
# TIMER TASK
# =========================
async def role_timer(data):
    tick = 0
    guild = bot.get_guild(data["guild_id"])
    if not guild:
        return

    member = guild.get_member(data["member_id"])
    role = guild.get_role(data["role_id"])
    channel = guild.get_channel(data["channel_id"])
    admin = await bot.fetch_user(ADMIN_ID)

    if not member or not role or not channel:
        return

    message = await channel.fetch_message(data["message_id"])
    expire = datetime.datetime.fromisoformat(data["expire"])
    total = data["total"]

    while True:
        now = datetime.datetime.now()
        remain = (expire - now).total_seconds()

        # 🔔 แจ้งก่อนหมด 3 วัน
        if remain <= 259200 and not data.get("warned_3days"):
            try:
                await member.send(f"⏰ Role {role.name} จะหมดอายุในอีก 3 วัน")
                await admin.send(f"⏰ {member.name} ({role.name}) จะหมดใน 3 วัน")
            except:
                pass
            data["warned_3days"] = True
            db = load_data()
            for r in db:
                if r["message_id"] == data["message_id"]:
                    r["warned_3days"] = True
            save_data(db)

        if remain <= 0:
            try:
                await member.remove_roles(role)
                await member.send(f"⛔ Role {role.name} หมดเวลาแล้ว")
                await admin.send(f"⛔ {member.name} หมดเวลา {role.name}")
            except:
                pass

            embed = discord.Embed(
                title="⛔ ROLE EXPIRED",
                description=f"{member.mention} หมด {role.mention}",
                color=discord.Color.red()
            )
            await message.edit(embed=embed, view=None)

            db = [r for r in load_data() if r["message_id"] != data["message_id"]]
            save_data(db)
            break

        embed = build_embed(member, role, expire, remain, total, data["note"], tick)
        await message.edit(embed=embed, view=CancelView())

        tick += 1
        await asyncio.sleep(10)

# =========================
# COMMAND
# =========================
@bot.tree.command(name="setrole", description="👑 Set Role Timer")
async def setrole(
    interaction: discord.Interaction,
    member: discord.Member,
    role: discord.Role,
    duration: str,
    note: str
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only", ephemeral=True)
        return

    seconds = parse_time(duration)
    if not seconds:
        await interaction.response.send_message("❌ รูปแบบเวลาไม่ถูกต้อง", ephemeral=True)
        return

    expire = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
    await member.add_roles(role)

    embed = build_embed(member, role, expire, seconds, seconds, note, 0)
    await interaction.response.send_message(embed=embed, view=CancelView())
    msg = await interaction.original_response()

    data = {
        "guild_id": interaction.guild.id,
        "member_id": member.id,
        "role_id": role.id,
        "channel_id": interaction.channel.id,
        "message_id": msg.id,
        "expire": expire.isoformat(),
        "total": seconds,
        "note": note,
        "warned_3days": False
    }

    db = load_data()
    db.append(data)
    save_data(db)

    bot.loop.create_task(role_timer(data))

# =========================
# READY
# =========================
@bot.event
async def on_ready():
    await bot.tree.sync()
    bot.add_view(CancelView())
    print(f"👑 BOT ONLINE: {bot.user}")

    for d in load_data():
        bot.loop.create_task(role_timer(d))

bot.run(TOKEN)
