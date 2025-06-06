import discord
from discord.ext import commands
import json, random, time, os, asyncio
from keep_alive import keep_alive
from discord.ext import tasks

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="$", intents=intents)

DATA_FILE = "xp_data.json"
COOLDOWN_SECONDS = 15
xp_data = {}
user_cooldowns = {}

if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        xp_data = json.load(f)


def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(xp_data, f)


@tasks.loop(minutes=30)
async def backup_xp_data():
    channel = bot.get_channel(1374366552983343254)  # Replace with your backup channel ID
    if not channel:
        print("Backup channel not found!")
        return
    try:
        with open(DATA_FILE, "r") as f:
            data = f.read()
        await channel.send(file=discord.File(DATA_FILE, filename="xp_backup.json"))
    except Exception as e:
        print(f"Backup failed: {e}")

@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    await load_backup_from_discord()
    backup_xp_data.start()


async def load_backup_from_discord():
    global xp_data
    backup_channel_id = 1374366552983343254
    channel = bot.get_channel(backup_channel_id)

    if not channel:
        print("Backup channel not found!")
        return

    try:
        async for message in channel.history(limit=50):
            for attachment in message.attachments:
                if attachment.filename == "xp_backup.json":
                    await attachment.save("xp_data.json")
                    with open("xp_data.json", "r") as f:
                        xp_data = json.load(f)
                    print("Successfully loaded XP data from latest Discord backup.")
                    return
        print("No backup file found. Falling back to local file...")
    except Exception as e:
        print(f"Error loading backup from Discord: {e}")

    # Fallback: try loading local file
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            xp_data = json.load(f)
        print("Successfully loaded XP data from local JSON file.")
    else:
        print("No local data file found. Starting fresh.")


@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    await process_xp(message)
    await bot.process_commands(message)


async def process_xp(message):
    user_id = str(message.author.id)
    guild_id = str(message.guild.id)
    now = time.time()

    if guild_id not in xp_data:
        xp_data[guild_id] = {}

    if user_id in user_cooldowns:
        if now - user_cooldowns[user_id] < COOLDOWN_SECONDS:
            return

    user_cooldowns[user_id] = now

    if user_id not in xp_data[guild_id]:
        xp_data[guild_id][user_id] = {"xp": 0, "level": 1}

    xp_gain = random.randint(5, 15)
    xp_data[guild_id][user_id]["xp"] += xp_gain

    level = xp_data[guild_id][user_id]["level"]
    level_up_xp = level * 100

    if xp_data[guild_id][user_id]["xp"] >= level_up_xp:
        xp_data[guild_id][user_id]["xp"] -= level_up_xp
        xp_data[guild_id][user_id]["level"] += 1
        await message.channel.send(
            f"{message.author.mention} leveled up to level {xp_data[guild_id][user_id]['level']}!"
        )

    save_data()


@bot.command()
async def leaderboard(ctx):
    guild_id = str(ctx.guild.id)
    if guild_id not in xp_data or not xp_data[guild_id]:
        await ctx.send("No leaderboard data available for this server.")
        return

    sorted_users = sorted(xp_data[guild_id].items(),
                          key=lambda item: (item[1]["level"], item[1]["xp"]),
                          reverse=True)

    per_page = 10
    pages = [
        sorted_users[i:i + per_page]
        for i in range(0, len(sorted_users), per_page)
    ]
    total_pages = len(pages)
    current_page = 0

    async def send_leaderboard_page(page_idx):
        embed = discord.Embed(
            title=f"Leaderboard - Page {page_idx + 1}/{total_pages}",
            color=discord.Color.gold())
        for i, (user_id, stats) in enumerate(pages[page_idx],
                                             start=page_idx * per_page + 1):
            user = ctx.guild.get_member(int(user_id))
            name = user.name if user else f"User ID {user_id}"
            embed.add_field(
                name=f"{i}. {name}",
                value=f"Level: {stats['level']} | XP: {stats['xp']}",
                inline=False)
        return embed

    message = await ctx.send(embed=await send_leaderboard_page(current_page))
    await message.add_reaction("⬅️")
    await message.add_reaction("➡️")

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in [
            "⬅️", "➡️"
        ] and reaction.message.id == message.id

    while True:
        try:
            reaction, user = await bot.wait_for("reaction_add",
                                                timeout=60.0,
                                                check=check)

            if str(reaction.emoji) == "⬅️" and current_page > 0:
                current_page -= 1
                await message.edit(
                    embed=await send_leaderboard_page(current_page))
            elif str(
                    reaction.emoji) == "➡️" and current_page < total_pages - 1:
                current_page += 1
                await message.edit(
                    embed=await send_leaderboard_page(current_page))

            await message.remove_reaction(reaction.emoji, user)
        except asyncio.TimeoutError:
            break


@bot.command()
@commands.guild_only()
async def rank(ctx, target: discord.Member = None):
    target = target or ctx.author
    guild_id = str(ctx.guild.id)
    user_id = str(target.id)

    if guild_id not in xp_data or user_id not in xp_data[guild_id]:
        await ctx.send(f"{target.name} hasn't earned any XP yet!")
        return

    stats = xp_data[guild_id][user_id]
    level = stats["level"]
    xp = stats["xp"]
    level_up_xp = level * 100
    progress = int((xp / level_up_xp) * 20)
    bar = "█" * progress + "—" * (20 - progress)

    sorted_users = sorted(xp_data[guild_id].items(),
                          key=lambda item: (item[1]["level"], item[1]["xp"]),
                          reverse=True)
    global_rank = next(
        (i + 1 for i, (uid, _) in enumerate(sorted_users) if uid == user_id),
        None)

    embed = discord.Embed(title=f"{target.name}'s Rank",
                          color=discord.Color.blue())
    embed.add_field(name="Level", value=level)
    embed.add_field(name="XP", value=f"{xp}/{level_up_xp}")
    embed.add_field(name="Progress", value=f"`{bar}`")
    embed.add_field(name="Global Rank",
                    value=f"{global_rank}/{len(sorted_users)}")
    await ctx.send(embed=embed)
    await asyncio.sleep(2)


@bot.command()
@commands.has_permissions(administrator=True)
async def resetxp(ctx, target: discord.Member = None):
    guild_id = str(ctx.guild.id)
    if target:
        user_id = str(target.id)
        if guild_id in xp_data and user_id in xp_data[guild_id]:
            xp_data[guild_id][user_id] = {"xp": 0, "level": 1}
            save_data()
            await ctx.send(f"XP and level reset for {target.name}.")
        else:
            await ctx.send(f"{target.name} has no XP data.")
    else:
        xp_data[guild_id] = {}
        save_data()
        await ctx.send(
            "All users' XP and levels have been reset in this server.")


@resetxp.error
async def resetxp_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to use this command.")
    else:
        await ctx.send(f"Error: {error}")


# Start web server and run bot
keep_alive()
bot.run(os.getenv("TOKEN"))
