import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import datetime
import json
import os

TOKEN = os.getenv("DISCORD_TOKEN")
ADMIN_ID = 123456789012345678  # 👈 ใส่ Discord ID Admin
DATA_FILE = "roles.json"

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# Utils
# =========================

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

async def safe_dm(user, content=None, embed=None):
    try:
        await user.send(content=content, embed=embed)
    except Exception:
        pass  # ผู้ใช้ปิด DM / บอทโดนบล็อก

# =========================
# Slash Command: Add Role
# =========================

@bot.tree.command(name="addrole", description="เพิ่ม Role แบบมีวันหมดอายุ")
@app_commands.describe(
    member="ผู้ใช้",
    role="Role ที่จะให้",
    days="จำนวนวัน"
)
async def addrole(
    interaction: discord.Interaction,
    member: discord.Member,
    role: discord.Role,
    days: int
):
    await interaction.response.defer(ephemeral=True)

    now_ts = int(datetime.datetime.utcnow().timestamp())
    expire_ts = now_ts + days * 86400

    await member.add_roles(role)

    data = load_data()
    guild_id = str(interaction.guild.id)

    data.setdefault(guild_id, {})
    data[guild_id][f"{member.id}:{role.id}"] = {
        "user_id": member.id,
        "role_id": role.id,
        "expire_ts": expire_ts,
        "warned": False
    }

    save_data(data)

    # ===== DM User =====
    await safe_dm(
        member,
        f"🎉 คุณได้รับ Role **{role.name}** แล้ว\n"
        f"⏰ หมดอายุ: <t:{expire_ts}:F>"
    )

    # ===== DM Admin =====
    admin = interaction.guild.get_member(ADMIN_ID)
    if admin:
        await safe_dm(
            admin,
            f"✅ เพิ่ม Role สำเร็จ\n"
            f"👤 ผู้ใช้: {member} ({member.id})\n"
            f"🎭 Role: {role.name}\n"
            f"⏰ หมดอายุ: <t:{expire_ts}:F>"
        )

    await interaction.followup.send(
        f"✅ เพิ่ม Role **{role.name}** ให้ {member.mention} แล้ว",
        ephemeral=True
    )

# =========================
# Background Task: Check Expire
# =========================

@tasks.loop(minutes=1)
async def check_expired_roles():
    data = load_data()
    now_ts = int(datetime.datetime.utcnow().timestamp())

    for guild_id, records in list(data.items()):
        guild = bot.get_guild(int(guild_id))
        if not guild:
            continue

        admin = guild.get_member(ADMIN_ID)

        for key, info in list(records.items()):
            member = guild.get_member(info["user_id"])
            role = guild.get_role(info["role_id"])
            expire_ts = info["expire_ts"]

            if not member or not role:
                del data[guild_id][key]
                continue

            # ⏳ แจ้งเตือนก่อนหมด 3 วัน
            if not info["warned"] and 0 < (expire_ts - now_ts) <= 3 * 86400:
                await safe_dm(
                    member,
                    f"⏳ Role **{role.name}** ของคุณจะหมดอายุในอีก **3 วัน**\n"
                    f"📅 หมดอายุ: <t:{expire_ts}:F>"
                )

                if admin:
                    await safe_dm(
                        admin,
                        f"⚠️ แจ้งเตือนใกล้หมดอายุ\n"
                        f"👤 ผู้ใช้: {member}\n"
                        f"🎭 Role: {role.name}\n"
                        f"⏳ เหลือ 3 วัน"
                    )

                info["warned"] = True

            # ⛔ หมดอายุ
            if now_ts >= expire_ts:
                await member.remove_roles(role)

                await safe_dm(
                    member,
                    f"⛔ Role **{role.name}** ของคุณหมดอายุแล้ว\n"
                    f"📅 หมดอายุเมื่อ: <t:{expire_ts}:F>"
                )

                if admin:
                    await safe_dm(
                        admin,
                        f"🗑️ ลบ Role อัตโนมัติ (หมดอายุ)\n"
                        f"👤 ผู้ใช้: {member}\n"
                        f"🎭 Role: {role.name}"
                    )

                del data[guild_id][key]

    save_data(data)

# =========================
# Bot Events
# =========================

@bot.event
async def on_ready():
    await bot.tree.sync()
    check_expired_roles.start()
    print(f"✅ Logged in as {bot.user}")

bot.run(TOKEN)
