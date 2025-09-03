import discord
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import datetime
import random
from collections import defaultdict
import asyncio

# ⚠️ Ne JAMAIS mettre vos vrais tokens en clair dans le code
# Stockez-les dans un fichier .env (via python-dotenv) ou des variables d'environnement
TOKEN = "YOUR_DISCORD_BOT_TOKEN"
APPLICATION_ID = "YOUR_APPLICATION_ID"
PUBLIC_KEY = "YOUR_PUBLIC_KEY"
PRIVATE_KEY = "YOUR_PRIVATE_KEY"
CHANNEL_ID = 123456789012345678  # Remplacez par l’ID de votre channel
SEND_HOUR = 9  # Envoi du message quotidien à 9h

# Liste de mots interdits
BANNED_WORDS = [
    "nerver mind", "badword2", "badword3", "idiot", "stupid", "dumb", "fool",
    "moron", "shut up", "loser", "hate", "kill", "die", "suck", "bastard",
    "asshole", "bitch", "crap", "damn", "fuck", "shit", "piss", "dick",
    "cock", "pussy", "slut", "whore", "retard"
]

# Intents Discord requis
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True

# Initialisation du bot
bot = commands.Bot(command_prefix="!", intents=intents)

# Gestion des infractions pour bannissement temporaire
user_infractions = defaultdict(int)
KICK_DURATION_SECONDS = 7 * 24 * 60 * 60  # 1 semaine


# ----------------------------
# Événements Discord
# ----------------------------
@bot.event
async def on_ready():
    print(f"✅ Bot connecté en tant que {bot.user}")
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_daily_message, 'cron', hour=SEND_HOUR)
    scheduler.start()


async def send_daily_message():
    """Envoie un message quotidien dans le channel défini."""
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.send("☀️ Good morning! Voici votre message quotidien.")


@bot.event
async def on_member_join(member):
    """Message de bienvenue."""
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.send(f"Bienvenue {member.mention} sur le serveur ! 🎉")


@bot.event
async def on_member_remove(member):
    """Message de départ."""
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.send(f"{member.mention} a quitté le serveur. 👋")


# ----------------------------
# Commandes Discord
# ----------------------------
@bot.command(name="sondage")
async def sondage(ctx, question: str, *options):
    """Crée un sondage à choix multiple."""
    if len(options) < 2:
        await ctx.send("⚠️ Veuillez fournir au moins deux options.")
        return
    if len(options) > 10:
        await ctx.send("⚠️ Maximum 10 options autorisées.")
        return

    emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    description = "\n".join(f"{emojis[i]} {opt}" for i, opt in enumerate(options))

    embed = discord.Embed(
        title="📊 Sondage (choix multiple)",
        description=f"**{question}**\n\n{description}",
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Sondage créé par {ctx.author.display_name}")

    poll_message = await ctx.send(embed=embed)
    for i in range(len(options)):
        await poll_message.add_reaction(emojis[i])


@bot.command(name="motdepasse")
async def generate_password(ctx):
    """Génère un mot de passe aléatoire de 12 caractères."""
    characters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()"
    password = ''.join(random.choice(characters) for _ in range(12))
    await ctx.send(f"🔐 Votre mot de passe généré : `{password}`")


@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    """Bannir un utilisateur."""
    await member.ban(reason=reason)
    await ctx.send(f"⛔ {member.mention} a été banni. Raison : {reason or 'Aucune'}")


@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    """Expulser un utilisateur."""
    await member.kick(reason=reason)
    await ctx.send(f"🚪 {member.mention} a été expulsé. Raison : {reason or 'Aucune'}")


@bot.command(name="warn")
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason=None):
    """Avertir un utilisateur."""
    await ctx.send(f"⚠️ {member.mention}, vous êtes averti. Raison : {reason or 'Aucune'}")


@bot.command(name="stats")
async def stats(ctx):
    """Affiche les stats du serveur."""
    guild = ctx.guild
    embed = discord.Embed(title=f"📊 Stats de {guild.name}", color=discord.Color.blue())
    embed.add_field(name="👥 Membres", value=guild.member_count, inline=True)
    embed.add_field(name="💬 Salons", value=len(guild.channels), inline=True)
    embed.add_field(name="🎭 Rôles", value=len(guild.roles), inline=True)
    embed.set_thumbnail(url=guild.icon.url if guild.icon else "")
    await ctx.send(embed=embed)


# ----------------------------
# Lancement du bot
# ----------------------------
bot.run(TOKEN)

