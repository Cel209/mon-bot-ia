import discord
from discord import app_commands
from discord.ext import commands
import google.generativeai as genai
import os
import aiohttp
import io
import time
import json
import asyncio
import warnings

warnings.filterwarnings("ignore")

# ====================================================
#                  CONFIGURATION
# ====================================================

# 👇 REMETS TES 3 CLÉS ICI (ET GARDE-LES SECRÈTES) 👇
DISCORD_TOKEN = "VOTRE_TOKEN_DISCORD_ICI"
GOOGLE_API_KEY = "VOTRE_TOKEN_GOOGLE_ICI"
HF_TOKEN = "VOTRE_TOKEN_HF_ICI"

OWNER_ID = VOTRE_ID_DISCORD

# 👇 CONFIGURATION DES ABONNEMENTS (SKUS DISCORD) 👇
SKU_PLUS_ID = 1473355629916717138 
SKU_PRO_ID  = 1473358614763667503

# ====================================================
#               CONFIGURATION IA
# ====================================================
genai.configure(api_key=GOOGLE_API_KEY)
try:
    model = genai.GenerativeModel('gemini-3-flash-preview')
    print("✅ Modèle Texte : gemini-3-flash-preview")
except:
    model = genai.GenerativeModel('gemini-1.5-flash')
    print("/!\\ Fallback sur gemini-1.5-flash")

chat_sessions = {}

# ====================================================
#             STATISTIQUES & DONNÉES
# ====================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATS_FILE = os.path.join(BASE_DIR, "stats.json")
VIP_FILE = os.path.join(BASE_DIR, "vip_data.json")

def load_data(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r") as f: return json.load(f)
        except: return default
    return default

stats_data = load_data(STATS_FILE, {"total_input": 0, "total_output": 0, "total_images": 0})
vip_data = load_data(VIP_FILE, {"users": [], "keys": []})

def save_stats():
    with open(STATS_FILE, "w") as f: json.dump(stats_data, f, indent=2)

def save_vip_data():
    with open(VIP_FILE, "w") as f: json.dump(vip_data, f, indent=2)

def update_cost(response):
    try:
        usage = response.usage_metadata
        if usage:
            stats_data["total_input"] += usage.prompt_token_count
            stats_data["total_output"] += usage.candidates_token_count
            save_stats()
    except: pass

# ====================================================
#               LIMITES & NIVEAUX
# ====================================================
LIMIT_FREE = 5000   
LIMIT_VIP = 500000  

COOLDOWN_IMG_FREE = 60  
COOLDOWN_IMG_VIP = 5    

user_token_usage = {}
user_cooldowns_img = {}

def get_user_tier(interaction: discord.Interaction):
    # 1. Le Owner et les VIPs manuels sont PRO d'office
    if interaction.user.id == OWNER_ID or interaction.user.id in vip_data["users"]:
        return "PRO"
    # 2. Vérification des abonnements Discord (SKU)
    for ent in interaction.entitlements:
        if ent.sku_id == SKU_PRO_ID: return "PRO"
        if ent.sku_id == SKU_PLUS_ID: return "PLUS"
    return "FREE"

def check_token_limit(user_id, text_input, is_vip=False):
    current_time = time.time()
    estimated_tokens = len(text_input) // 4 + 5
    
    limit = LIMIT_VIP if is_vip or user_id in vip_data["users"] else LIMIT_FREE

    if user_id not in user_token_usage:
        user_token_usage[user_id] = [current_time, 0]
    
    timestamp, usage = user_token_usage[user_id]
    
    # Reset toutes les 5 minutes (300s)
    if current_time - timestamp > 300: 
        user_token_usage[user_id] = [current_time, estimated_tokens]
        return True
    
    if usage + estimated_tokens > limit: return False
    user_token_usage[user_id][1] += estimated_tokens
    return True

# ====================================================
#                  BOT SETUP
# ====================================================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def get_chat_session(channel_id):
    if channel_id not in chat_sessions:
        chat_sessions[channel_id] = model.start_chat(history=[])
    return chat_sessions[channel_id]

async def send_limit_message(channel_or_interaction, user_id):
    store_link = f"https://discord.com/application-directory/{bot.user.id}/store"
    paypal_link = "https://paypal.me/Cel209YT/5" 
    
    embed = discord.Embed(
        title="🔒 Limite Gratuite Atteinte",
        description=f"Vous avez utilisé vos **5 000 tokens** gratuits.\nPour continuer, passez VIP :",
        color=0xFF0000
    )
    embed.add_field(name="🚀 Boutique Discord", value=f"[S'abonner]({store_link})", inline=True)
    embed.add_field(name="💳 PayPal (5€)", value=f"[Payer 5€]({paypal_link})", inline=True)
    embed.set_footer(text="Si PayPal : Demandez votre code à l'admin.")

    if isinstance(channel_or_interaction, discord.Interaction):
        await channel_or_interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await channel_or_interaction.send(embed=embed)

# ====================================================
#               FONCTION IMAGE
# ====================================================
async def generate_image_hf(prompt):
    API_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {"inputs": prompt, "parameters": {"num_inference_steps": 4}}
    
    async with aiohttp.ClientSession() as session:
        for i in range(3):
            try:
                async with session.post(API_URL, headers=headers, json=payload) as response:
                    if response.status == 200: return await response.read()
                    elif response.status == 503: await asyncio.sleep(5); continue
                    else: break
            except: break
    return None

# ====================================================
#                  EVENTS
# ====================================================
@bot.event
async def on_ready():
    print(f'✅ Connecté : {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f'✅ {len(synced)} commandes synchronisées.')
    except Exception as e: print(f'❌ Erreur Sync : {e}')
    
    # 👇 LE STATUT PAYPAL EST ICI 👇
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="paypal.me/Cel209YT"))

@bot.event
async def on_message(message):
    if message.author == bot.user: return
    
    # Mode Legacy "!"
    if message.content.startswith('!'):
        prompt = message.content.replace('!', '', 1).strip()
        if prompt:
            is_vip = message.author.id in vip_data["users"] or message.author.id == OWNER_ID
            
            if not check_token_limit(message.author.id, prompt, is_vip):
                await send_limit_message(message.channel, message.author.id)
                return
            
            async with message.channel.typing():
                try:
                    chat = get_chat_session(message.channel.id)
                    response = await asyncio.to_thread(chat.send_message, prompt)
                    update_cost(response)
                    if len(response.text) > 2000:
                         await message.channel.send(response.text[:2000])
                    else:
                        await message.channel.send(response.text)
                except: await message.channel.send("❌ Erreur IA.")
    
    await bot.process_commands(message)

# ====================================================
#                 COMMANDES PRINCIPALES
# ====================================================

@bot.tree.command(name="discussion", description="💬 Discuter avec l'IA")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def discussion(interaction: discord.Interaction, message: str):
    await interaction.response.defer()
    
    tier = get_user_tier(interaction)
    is_vip = tier in ["PLUS", "PRO"]
    
    if not check_token_limit(interaction.user.id, message, is_vip=is_vip):
        await send_limit_message(interaction, interaction.user.id)
        return
        
    try:
        chat = get_chat_session(interaction.channel_id)
        response = await asyncio.to_thread(chat.send_message, message)
        update_cost(response)
        
        txt = response.text
        if len(txt) > 1900:
            await interaction.followup.send(txt[:1900])
            await interaction.followup.send(txt[1900:])
        else:
            await interaction.followup.send(txt)
    except: await interaction.followup.send("❌ Erreur IA.")

@bot.tree.command(name="imagine", description="🎨 Créer une image")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def imagine(interaction: discord.Interaction, prompt: str):
    uid = interaction.user.id
    now = time.time()
    tier = get_user_tier(interaction)
    is_vip = tier in ["PLUS", "PRO"]
    cooldown = COOLDOWN_IMG_VIP if is_vip else COOLDOWN_IMG_FREE
    
    if uid in user_cooldowns_img and (now - user_cooldowns_img[uid] < cooldown):
        r = int(cooldown - (now - user_cooldowns_img[uid]))
        await interaction.response.send_message(f"⏳ Attends {r}s ou passe VIP (/premium) !", ephemeral=True)
        return
        
    user_cooldowns_img[uid] = now
    await interaction.response.defer()
    img = await generate_image_hf(prompt)
    
    if img:
        stats_data["total_images"] += 1
        save_stats()
        f = discord.File(io.BytesIO(img), filename="img.png")
        await interaction.followup.send(file=f, content=f"🎨 **{prompt}** pour {interaction.user.mention}")
    else: await interaction.followup.send("❌ Erreur HuggingFace.")

@bot.tree.command(name="video", description="🎥 Simulation Vidéo (Réservé PRO)")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def video(interaction: discord.Interaction, prompt: str):
    if get_user_tier(interaction) != "PRO":
        embed = discord.Embed(title="💎 Offre Pro Requise", description="Génération vidéo réservée aux membres Pro.\n`/premium` pour débloquer.", color=0xFF0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    await interaction.response.defer()
    img = await generate_image_hf("Cinematic shot, 8k, " + prompt)
    if img:
        f = discord.File(io.BytesIO(img), filename="video_render.png")
        await interaction.followup.send(file=f, content=f"🎥 **{prompt}** (Mode Pro)")
    else: await interaction.followup.send("❌ Erreur.")

@bot.tree.command(name="premium", description="💎 Boutique")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def premium(interaction: discord.Interaction):
    link = f"https://discord.com/application-directory/{bot.user.id}/store"
    embed = discord.Embed(title="💎 Devenir VIP", description="Débloquez la puissance ultime :", color=0x4285F4)
    embed.add_field(name="🥉 Plus (Images illimitées)", value="7.99€ / mois", inline=True)
    embed.add_field(name="🥇 Pro (Vidéo + Priorité)", value="21.99€ / mois", inline=True)
    embed.add_field(name="💳 PayPal (Alternative)", value="[Payer 5€ (Unique)](https://paypal.me/Cel209YT/5)", inline=False)
    
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="🛒 Ouvrir la Boutique Discord", url=link, style=discord.ButtonStyle.link))
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ====================================================
#               COMMANDES UTILITAIRES
# ====================================================

@bot.tree.command(name="traduire", description="🌍 Traduire")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def traduire(interaction: discord.Interaction, langue: str, texte: str):
    await interaction.response.defer()
    try:
        res = await asyncio.to_thread(model.generate_content, f"Traduis en {langue}: {texte}")
        update_cost(res)
        await interaction.followup.send(f"**Traduction ({langue}):**\n{res.text}")
    except Exception as e: await interaction.followup.send(f"Erreur: {e}")

@bot.tree.command(name="systeme", description="💻 État CPU")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def systeme(interaction: discord.Interaction):
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f: t = int(f.read()) / 1000
    except: t = 0
    await interaction.response.send_message(f"🌡 CPU: {t}°C", ephemeral=True)

@bot.tree.command(name="ping", description="🏓 Ping")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency*1000)}ms", ephemeral=True)

@bot.tree.command(name="reset", description="🧠 Reset Mémoire")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def reset(interaction: discord.Interaction):
    if interaction.channel_id in chat_sessions:
        del chat_sessions[interaction.channel_id]
        await interaction.response.send_message("🧠 Mémoire effacée.", ephemeral=True)
    else: await interaction.response.send_message("Rien à effacer.", ephemeral=True)

# ====================================================
#               COMMANDES ADMIN (OWNER)
# ====================================================

@bot.tree.command(name="vip", description="💎 Activer VIP (Manuel)")
async def vip(interaction: discord.Interaction, code: str):
    if code in vip_data["keys"]:
        vip_data["keys"].remove(code)
        vip_data["users"].append(interaction.user.id)
        save_vip_data()
        await interaction.response.send_message("🎉 VIP activé !", ephemeral=False)
    else: await interaction.response.send_message("❌ Code invalide.", ephemeral=True)

@bot.tree.command(name="gen_key", description="🔑 Créer clé (Owner)")
async def gen_key(interaction: discord.Interaction, code: str):
    if interaction.user.id == OWNER_ID:
        vip_data["keys"].append(code)
        save_vip_data()
        await interaction.response.send_message(f"✅ Clé : `{code}`", ephemeral=True)
    else: await interaction.response.send_message("⛔", ephemeral=True)

@bot.tree.command(name="remove_vip", description="🚫 Retirer VIP (Owner)")
async def remove_vip(interaction: discord.Interaction, user_id: str):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("⛔", ephemeral=True)
        return
    try:
        uid = int(user_id)
        if uid in vip_data["users"]:
            vip_data["users"].remove(uid)
            save_vip_data()
            await interaction.response.send_message(f"🚫 VIP retiré pour {uid}.", ephemeral=True)
        else: await interaction.response.send_message("Cet ID n'est pas VIP.", ephemeral=True)
    except: await interaction.response.send_message("ID invalide.", ephemeral=True)

@bot.tree.command(name="cout", description="📊 Stats (Owner)")
async def cout(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("⛔", ephemeral=True)
        return
    await interaction.response.send_message(f"📊 **Stats**\nInput Tokens: {stats_data['total_input']}\nOutput Tokens: {stats_data['total_output']}\nImages générées: {stats_data['total_images']}", ephemeral=True)

@bot.tree.command(name="effacer", description="🧹 Clean Chat")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def effacer(interaction: discord.Interaction, nombre: int):
    try:
        await interaction.channel.purge(limit=min(nombre, 100))
        await interaction.response.send_message(f"🧹 Terminé.", ephemeral=True)
    except:
        await interaction.response.send_message("❌ Impossible ici.", ephemeral=True)

@bot.tree.command(name="farm_badge", description="🔰 Badge Dev")
@app_commands.checks.has_permissions(administrator=True)
async def farm_badge(interaction: discord.Interaction):
    await interaction.response.send_message("🔰 Commande exécutée.", ephemeral=True)

bot.run(DISCORD_TOKEN)
