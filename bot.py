import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import json
import os

TOKEN = os.getenv("DISCORD_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

DATA_FILE = "members.json"
TOTAL_DAYS = 30

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ----------------- Utils -----------------
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def calc_expire(start_date: datetime.date):
    # นับวันสมัครเป็นวันแรก → 30 วัน
    return start_date + datetime.timedelta(days=29)

def progress_bar(used):
    percent = min(used / TOTAL_DAYS, 1)
    filled = int(percent * 10)
    return "🟩" * filled + "⬜" * (10 - filled)

def format_timedelta(td: datetime.timedelta):
    seconds = int(td.total_seconds())
    if seconds < 0:
        seconds = 0
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{days} วัน / {hours} ชม / {minutes} นาที / {seconds} วินาที"

# ----------------- Views -----------------
class MemberControlView(discord.ui.View):
    def __init__(self, member_id):
        super().__init__(timeout=None)
        self.member_id = str(member_id)

    @discord.ui.button(label="✏️ แก้ไขวันสมัคร", style=discord.ButtonStyle.primary)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ เฉพาะแอดมินเท่านั้น", ephemeral=True)
            return
        await interaction.response.send_message(
            "📝 ใช้คำสั่ง `/setrole` ใหม่ เพื่อแก้ไขข้อมูลสมาชิกนี้",
            ephemeral=True
        )

    @discord.ui.button(label="🗑️ ลบสมาชิก", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ เฉพาะแอดมินเท่านั้น", ephemeral=True)
            return

        data = load_data()
        if self.member_id in data:
            del data[self.member_id]
            save_data(data)
            await interaction.response.send_message("🗑️ ลบสถานะสมาชิกเรียบร้อย", ephemeral=True)
        else:
            await interaction.response.send_message("❌ ไม่พบข้อมูลสมาชิก", ephemeral=True)

# ----------------- Commands -----------------
@bot.tree.command(name="setrole", description="เพิ่ม/แก้ไขสมาชิกแบบกำหนดวันสมัคร")
@app_commands.describe(
    member="ผู้รับ Role",
    role="Role ที่ให้",
    start_date="วันสมัคร (DD/MM/YY)",
    member_name="ชื่อ Member",
    price="ราคา",
    days="จำนวนวัน (โชว์เฉย ๆ)"
)
async def setrole(
    interaction: discord.Interaction,
    member: discord.Member,
    role: discord.Role,
    start_date: str,
    member_name: str,
    price: int,
    days: int
):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("❌ เฉพาะแอดมินเท่านั้น", ephemeral=True)
        return

    try:
        start = datetime.datetime.strptime(start_date, "%d/%m/%y").date()
    except:
        await interaction.response.send_message("❌ รูปแบบวันที่ไม่ถูกต้อง (DD/MM/YY)", ephemeral=True)
        return

    expire = calc_expire(start)
    await member.add_roles(role)

    data = load_data()
    data[str(member.id)] = {
        "role_id": role.id,
        "start": start.isoformat(),
        "expire": expire.isoformat(),
        "member_name": member_name,
        "price": price,
        "days": days,
        "warned": False
    }
    save_data(data)

    await interaction.response.send_message(
        f"✅ เพิ่มสมาชิก {member.mention} เรียบร้อย",
        ephemeral=True
    )

@bot.tree.command(name="check", description="ตรวจสอบสถานะสมาชิก")
async def check(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)

    if uid not in data:
        await interaction.response.send_message("❌ คุณยังไม่มีสถานะสมาชิก", ephemeral=True)
        return

    info = data[uid]
    start = datetime.date.fromisoformat(info["start"])
    expire = datetime.date.fromisoformat(info["expire"])
    now = datetime.datetime.now()

    used = (now.date() - start).days + 1
    remaining = datetime.datetime.combine(
        expire + datetime.timedelta(days=1),
        datetime.time.min
    ) - now

    # -------- EMBED (FIXED DISPLAY) --------
    embed = discord.Embed(
        title="📅 Check Member Time",
        color=discord.Color.green()
    )

    embed.add_field(
        name="👤 สมาชิก",
        value=interaction.user.mention,
        inline=False
    )

    embed.add_field(
        name="🏷️ Member",
        value=f"**{info['member_name']}** | {info['days']} วัน | {info['price']} บาท",
        inline=False
    )

    embed.add_field(
        name="📌 วันที่ลงทะเบียน",
        value=start.strftime("%d/%m/%Y"),
        inline=False
    )

    embed.add_field(
        name="⏳ วันหมดอายุ",
        value=expire.strftime("%d/%m/%Y"),
        inline=False
    )

    embed.add_field(
        name="🕒 เวลาที่เหลือ",
        value=f"```{format_timedelta(remaining)}```",
        inline=False
    )

    embed.add_field(
        name="📊 Progress (30 วัน)",
        value=f"{progress_bar(used)}  {int((used/TOTAL_DAYS)*100)}%",
        inline=False
    )

    embed.set_footer(text="👑 ADMINZENO • TIME MEMBER SYSTEM")

    await interaction.response.send_message(
        embed=embed,
        view=MemberControlView(uid),
        ephemeral=True
    )

# ----------------- Background Task -----------------
@tasks.loop(minutes=1)
async def expire_checker():
    data = load_data()
    now = datetime.datetime.now()

    for uid, info in list(data.items()):
        expire = datetime.date.fromisoformat(info["expire"])
        remaining_days = (expire - now.date()).days

        user = bot.get_user(int(uid))
        if not user:
            continue

        if remaining_days == 3 and not info.get("warned"):
            try:
                await user.send("⏰ สมาชิกของคุณจะหมดอายุในอีก 3 วัน")
                info["warned"] = True
            except:
                pass

        if remaining_days < 0:
            del data[uid]

    save_data(data)

# ----------------- Events -----------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    expire_checker.start()
    print("👑 BOT ONLINE")

bot.run(TOKEN)
