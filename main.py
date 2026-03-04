import discord
from discord import app_commands
from discord.ext import commands, tasks
import google.generativeai as genai
import os
import aiohttp
import io
import time
import json
import asyncio
import warnings
import datetime
import random

warnings.filterwarnings("ignore")

# ====================================================
#                  CONFIGURATION
# ====================================================

DISCORD_TOKEN = "METS_TON_TOKEN_DISCORD_ICI"
GOOGLE_API_KEY = "METS_TA_CLE_GOOGLE_GEMINI_ICI"
HF_TOKEN = "METS_TA_CLE_HUGGINGFACE_ICI"

OWNER_ID = 997185522302726260

# --- ABONNEMENTS IA ---
SKU_PLUS_ID = 1473355629916717138 
SKU_PRO_ID  = 1473358614763667503

# --- GACHA SKUS & VISUELS ---
SKU_TICKET_ULTRA = 111111111111111111 
SKU_BOOST_CHANCE = 222222222222222222 

URL_BANNER_ULTRA = "https://i.imgur.com/Q3q8y9J.gif" 

# IDs des rôles
ROLE_COMMUN = 100000000000000001
ROLE_POUVOIR_TEMP = 100000000000000002
ROLE_TITRE_RARE = 100000000000000003

# Tables Gacha
GACHA_STANDARD = [
    {"nom": "Rien (Échec)", "role_id": None, "poids": 70, "temp_hours": 0, "score": 0},
    {"nom": "Titre Commun", "role_id": ROLE_COMMUN, "poids": 29.9, "temp_hours": 0, "score": 10},
    {"nom": "Pouvoir Éphémère (2h)", "role_id": ROLE_POUVOIR_TEMP, "poids": 0.099, "temp_hours": 2, "score": 50},
    {"nom": "Titre Rare", "role_id": ROLE_TITRE_RARE, "poids": 0.001, "temp_hours": 0, "score": 200}
]

GACHA_ULTRA_BASE = [
    {"nom": "Pouvoir Éphémère (24h)", "role_id": ROLE_POUVOIR_TEMP, "poids": 99.999, "temp_hours": 24, "score": 100},
    {"nom": "Titre Rare", "role_id": ROLE_TITRE_RARE, "poids": 0.001, "temp_hours": 0, "score": 500}
]

GACHA_ULTRA_BOOSTED = [
    {"nom": "Pouvoir Éphémère (24h)", "role_id": ROLE_POUVOIR_TEMP, "poids": 99.0, "temp_hours": 24, "score": 100},
    {"nom": "Titre Rare", "role_id": ROLE_TITRE_RARE, "poids": 1.0, "temp_hours": 0, "score": 500}
]

# ====================================================
#               CONFIGURATION IA
# ====================================================
genai.configure(api_key=GOOGLE_API_KEY)
try:
    model = genai.GenerativeModel('gemini-3-flash-preview')
except:
    model = genai.GenerativeModel('gemini-1.5-flash')

chat_sessions = {}

# ====================================================
#             STATISTIQUES & DONNÉES
# ====================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATS_FILE = os.path.join(BASE_DIR, "stats.json")
VIP_FILE = os.path.join(BASE_DIR, "vip_data.json")
NOTIFS_FILE = os.path.join(BASE_DIR, "notifs.json")
GACHA_FILE = os.path.join(BASE_DIR, "gacha.json")

def load_data(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r") as f: return json.load(f)
        except: return default
    return default

stats_data = load_data(STATS_FILE, {"total_input": 0, "total_output": 0, "total_images": 0})
vip_data = load_data(VIP_FILE, {"users": [], "keys": []})
notifs_data = load_data(NOTIFS_FILE, {"channels": [], "announced": []})
gacha_data = load_data(GACHA_FILE, {"last_daily": {}, "active_powers": [], "manual_tickets": {}, "scores": {}, "weekend_claims": {}})

def save_data(path, data):
    with open(path, "w") as f: json.dump(data, f, indent=2)

def update_cost(response):
    try:
        usage = response.usage_metadata
        if usage:
            stats_data["total_input"] += usage.prompt_token_count
            stats_data["total_output"] += usage.candidates_token_count
            save_data(STATS_FILE, stats_data)
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
    if interaction.user.id == OWNER_ID or interaction.user.id in vip_data["users"]:
        return "PRO"
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
intents.members = True 
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
        description=f"Vous avez utilisé vos **5 000 tokens** gratuits.\n\n**Pour débloquer l'illimité :**",
        color=0xFF0000
    )
    embed.add_field(name="🚀 Boutique Discord", value=f"[S'abonner]({store_link})", inline=True)
    embed.add_field(name="💳 PayPal (5€)", value=f"[Payer 5€]({paypal_link})", inline=True)
    if isinstance(channel_or_interaction, discord.Interaction):
        await channel_or_interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await channel_or_interaction.send(embed=embed)

# ====================================================
#               FONCTIONS UTILITAIRES
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

async def get_direct_steam_link(gamerpower_url):
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(gamerpower_url, allow_redirects=True) as resp:
                return str(resp.url)
    except: return gamerpower_url

def perform_gacha_pulls(table, pulls):
    population = [item for item in table]
    weights = [item["poids"] for item in table]
    return random.choices(population, weights=weights, k=pulls)

async def apply_gacha_rewards(interaction, results):
    uid = interaction.user.id
    guild = interaction.guild
    if not guild: return
    member = guild.get_member(uid)
    if not member: return

    now = time.time()
    mentions_list = []
    
    for item in results:
        role_id = item["role_id"]
        if role_id:
            role = guild.get_role(role_id)
            if role:
                if role not in member.roles:
                    try:
                        await member.add_roles(role)
                        if item["temp_hours"] > 0:
                            expire_time = now + (item["temp_hours"] * 3600)
                            gacha_data["active_powers"].append({
                                "user_id": uid, "guild_id": guild.id,
                                "role_id": role_id, "expire": expire_time
                            })
                    except Exception as e: print(f"Erreur rôle: {e}")
                mentions_list.append(role.mention)
            else: mentions_list.append(item["nom"])
        else: mentions_list.append(item["nom"])
        
    save_data(GACHA_FILE, gacha_data)
    return mentions_list

def update_gacha_score(uid_str, points):
    if "scores" not in gacha_data: gacha_data["scores"] = {}
    if uid_str not in gacha_data["scores"]: gacha_data["scores"][uid_str] = 0
    gacha_data["scores"][uid_str] += points
    save_data(GACHA_FILE, gacha_data)

# ====================================================
#               LOGIQUE PUISSANCE 4
# ====================================================
class Puissance4View(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=300)
        self.user = user
        self.board = [[0] * 7 for _ in range(6)]
        self.game_over = False
        
        options = [discord.SelectOption(label=f"Colonne {i+1}", value=str(i)) for i in range(7)]
        self.select = discord.ui.Select(placeholder="Choisis une colonne...", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    def check_win(self, player):
        for c in range(4):
            for r in range(6):
                if self.board[r][c] == player and self.board[r][c+1] == player and self.board[r][c+2] == player and self.board[r][c+3] == player: return True
        for c in range(7):
            for r in range(3):
                if self.board[r][c] == player and self.board[r+1][c] == player and self.board[r+2][c] == player and self.board[r+3][c] == player: return True
        for c in range(4):
            for r in range(3):
                if self.board[r][c] == player and self.board[r+1][c+1] == player and self.board[r+2][c+2] == player and self.board[r+3][c+3] == player: return True
        for c in range(4):
            for r in range(3, 6):
                if self.board[r][c] == player and self.board[r-1][c+1] == player and self.board[r-2][c+2] == player and self.board[r-3][c+3] == player: return True
        return False

    def is_full(self):
        return all(self.board[0][c] != 0 for c in range(7))

    def drop_piece(self, col, player):
        for r in range(5, -1, -1):
            if self.board[r][col] == 0:
                self.board[r][col] = player
                return True
        return False

    def render_board(self):
        symbols = {0: "⚪", 1: "🔴", 2: "🟡"}
        res = ""
        for row in self.board:
            res += "".join(symbols[cell] for cell in row) + "\n"
        res += "1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣"
        return res

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Ce n'est pas ta partie.", ephemeral=True)
            return
        
        col = int(self.select.values[0])
        if self.board[0][col] != 0:
            await interaction.response.send_message("Colonne pleine !", ephemeral=True)
            return

        self.drop_piece(col, 1)
        
        if self.check_win(1):
            self.game_over = True
            uid_str = str(self.user.id)
            gacha_data["manual_tickets"][uid_str] = gacha_data.get("manual_tickets", {}).get(uid_str, 0) + 1
            save_data(GACHA_FILE, gacha_data)
            embed = discord.Embed(title="🔴 Victoire !", description=f"{self.render_board()}\n\n🎁 Tu as gagné **1 Ticket Ultra** !", color=0x00FF00)
            self.clear_items()
            await interaction.response.edit_message(embed=embed, view=self)
            return

        if self.is_full():
            self.game_over = True
            embed = discord.Embed(title="🤝 Match Nul", description=self.render_board(), color=0x808080)
            self.clear_items()
            await interaction.response.edit_message(embed=embed, view=self)
            return

        valid_cols = [c for c in range(7) if self.board[0][c] == 0]
        bot_col = random.choice(valid_cols)
        self.drop_piece(bot_col, 2)

        if self.check_win(2):
            self.game_over = True
            embed = discord.Embed(title="🟡 Défaite", description=f"{self.render_board()}\n\nLe bot a gagné.", color=0xFF0000)
            self.clear_items()
            await interaction.response.edit_message(embed=embed, view=self)
            return
            
        embed = discord.Embed(title="🔴 Puissance 4 🟡", description=self.render_board(), color=0x3498db)
        await interaction.response.edit_message(embed=embed, view=self)

# ====================================================
#                  TASKS (BOUCLES)
# ====================================================
@tasks.loop(hours=4)
async def check_free_games():
    if not notifs_data["channels"]: return
    url = "https://www.gamerpower.com/api/giveaways?platform=steam&type=game"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    games = await resp.json()
                    for game in games:
                        game_id = game.get("id")
                        if game_id not in notifs_data["announced"]:
                            notifs_data["announced"].append(game_id)
                            save_data(NOTIFS_FILE, notifs_data)
                            
                            worth = game.get('worth', 'N/A')
                            direct_url = await get_direct_steam_link(game.get('open_giveaway_url', ''))
                            
                            end_date_str = game.get('end_date', 'N/A')
                            date_info = ""
                            if end_date_str != "N/A":
                                try:
                                    end_dt = datetime.datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S")
                                    days = (end_dt - datetime.datetime.now()).days
                                    date_info = f" jusqu'au {end_dt.strftime('%d/%m/%Y')} ( dans {days} jours )"
                                except: pass

                            price_str = f"~~{worth}~~ **Gratuit**{date_info}" if worth not in ["N/A", "$0.00"] else f"**Gratuit**{date_info}"
                            app_link = f"\n🎮 **[Ouvrir dans le logiciel Steam](steam://store/{direct_url.split('app/')[1].split('/')[0].split('?')[0]})**" if "store.steampowered.com/app/" in direct_url else ""

                            embed = discord.Embed(
                                title=f"{game.get('title')} gratuit sur Steam !", url=direct_url,
                                description=f"> {game.get('description')}\n\n{price_str}\n🔗 **[Voir sur le site Steam]({direct_url})**{app_link}",
                                color=0x2b2d31, timestamp=datetime.datetime.now(datetime.timezone.utc)
                            )
                            embed.set_image(url=game.get('image'))
                            embed.set_thumbnail(url="https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Steam_icon_logo.svg/512px-Steam_icon_logo.svg.png")
                            embed.set_footer(text=f"{bot.user.name} [Officiel]")
                            
                            for cid in notifs_data["channels"]:
                                channel = bot.get_channel(cid)
                                if channel: await channel.send(embed=embed)
        except: pass

@tasks.loop(minutes=5)
async def check_expired_powers():
    now = time.time()
    active = gacha_data["active_powers"]
    remaining = []
    for power in active:
        if now >= power["expire"]:
            guild = bot.get_guild(power["guild_id"])
            if guild:
                member = guild.get_member(power["user_id"])
                role = guild.get_role(power["role_id"])
                if member and role: 
                    try: await member.remove_roles(role)
                    except: pass
        else: remaining.append(power)
    if len(active) != len(remaining):
        gacha_data["active_powers"] = remaining
        save_data(GACHA_FILE, gacha_data)

@check_free_games.before_loop
@check_expired_powers.before_loop
async def before_tasks(): await bot.wait_until_ready()

# ====================================================
#                  EVENTS
# ====================================================
@bot.event
async def on_ready():
    print(f'✅ Connecté : {bot.user}')
    await bot.tree.sync()
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="paypal.me/Cel209YT"))
    if not check_free_games.is_running(): check_free_games.start()
    if not check_expired_powers.is_running(): check_expired_powers.start()

@bot.event
async def on_message(message):
    if message.author == bot.user: return
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
                    await message.channel.send(response.text[:2000])
                except: await message.channel.send("❌ Erreur IA.")
    await bot.process_commands(message)

# ====================================================
#                 COMMANDES JEUX & GACHA
# ====================================================
@bot.tree.command(name="puissance4", description="🔴 Jouer au Puissance 4 contre le bot")
@app_commands.allowed_installs(guilds=True)
@app_commands.allowed_contexts(guilds=True)
async def puissance4(interaction: discord.Interaction):
    view = Puissance4View(interaction.user)
    embed = discord.Embed(title="🔴 Puissance 4 🟡", description=view.render_board(), color=0x3498db)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="coinflip", description="🪙 Parier des points Gacha (Pile ou Face)")
@app_commands.allowed_installs(guilds=True)
@app_commands.allowed_contexts(guilds=True)
@app_commands.choices(choix=[
    app_commands.Choice(name="Pile", value="pile"),
    app_commands.Choice(name="Face", value="face")
])
async def coinflip(interaction: discord.Interaction, choix: app_commands.Choice[str], mise: int):
    uid_str = str(interaction.user.id)
    score_actuel = gacha_data.get("scores", {}).get(uid_str, 0)
    
    if mise <= 0 or mise > score_actuel:
        await interaction.response.send_message(f"❌ Mise invalide. Tu possèdes **{score_actuel}** pts.", ephemeral=True)
        return
        
    resultat = random.choice(["pile", "face"])
    if choix.value == resultat:
        update_gacha_score(uid_str, mise)
        await interaction.response.send_message(f"🪙 La pièce tombe sur **{resultat.capitalize()}** ! 🎉 Tu gagnes **{mise}** pts. (Total: {score_actuel + mise} pts)")
    else:
        update_gacha_score(uid_str, -mise)
        await interaction.response.send_message(f"🪙 La pièce tombe sur **{resultat.capitalize()}**... 💀 Tu perds **{mise}** pts. (Total: {score_actuel - mise} pts)")

@bot.tree.command(name="gacha_daily", description="🎰 Tirage quotidien gratuit (10 pulls)")
@app_commands.allowed_installs(guilds=True)
@app_commands.allowed_contexts(guilds=True)
async def gacha_daily(interaction: discord.Interaction):
    uid_str = str(interaction.user.id)
    now = time.time()
    if now - gacha_data["last_daily"].get(uid_str, 0) < 86400:
        await interaction.response.send_message("⏳ Reviens demain !", ephemeral=True)
        return
    gacha_data["last_daily"][uid_str] = now
    results = perform_gacha_pulls(GACHA_STANDARD, 10)
    mentions = await apply_gacha_rewards(interaction, results)
    pts = sum(r["score"] for r in results)
    update_gacha_score(uid_str, pts)
    embed = discord.Embed(title="🎰 Tirage Quotidien (x10)", description="\n".join([f"🔸 {m}" for m in mentions]) + f"\n\n📈 **+{pts} pts**", color=0x3498db)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="gacha_ultra", description="💎 Bannière Ultra Rare (Ticket Requis ou Week-end)")
@app_commands.allowed_installs(guilds=True)
@app_commands.allowed_contexts(guilds=True)
async def gacha_ultra(interaction: discord.Interaction):
    uid_str = str(interaction.user.id)
    now_dt = datetime.datetime.now()
    day = now_dt.weekday() 
    iso_year, iso_week, _ = now_dt.isocalendar()
    week_key = f"{uid_str}_{iso_year}_{iso_week}"
    
    if "weekend_claims" not in gacha_data: gacha_data["weekend_claims"] = {}
    if week_key not in gacha_data["weekend_claims"]:
        gacha_data["weekend_claims"][week_key] = {"sat": False, "sun": False}

    is_free_weekend = False
    if day == 5 and not gacha_data["weekend_claims"][week_key]["sat"]:
        gacha_data["weekend_claims"][week_key]["sat"] = True
        is_free_weekend = True
    elif day == 6 and not gacha_data["weekend_claims"][week_key]["sun"]:
        gacha_data["weekend_claims"][week_key]["sun"] = True
        is_free_weekend = True

    used_ticket_type = ""
    if is_free_weekend:
        used_ticket_type = "🎁 Tirage gratuit du Week-end !"
        save_data(GACHA_FILE, gacha_data)
    else:
        ticket = next((e for e in interaction.entitlements if e.sku_id == SKU_TICKET_ULTRA and not e.is_consumed()), None)
        manual = gacha_data["manual_tickets"].get(uid_str, 0)
        
        if ticket: 
            await ticket.consume()
            used_ticket_type = "💳 Achat Boutique Discord"
        elif manual > 0:
            gacha_data["manual_tickets"][uid_str] -= 1
            save_data(GACHA_FILE, gacha_data)
            used_ticket_type = "🎟️ Ticket Manuel Admin"
        else:
            await interaction.response.send_message("🎟️ Ticket requis ou attendez le week-end ! (/premium)", ephemeral=True)
            return

    table = GACHA_ULTRA_BOOSTED if any(e.sku_id == SKU_BOOST_CHANCE for e in interaction.entitlements) else GACHA_ULTRA_BASE
    results = perform_gacha_pulls(table, 1)
    mentions = await apply_gacha_rewards(interaction, results)
    pts = results[0]["score"]
    update_gacha_score(uid_str, pts)
    
    embed = discord.Embed(title="✨ INVOCATION LÉGENDAIRE ✨", description=f"🌟 Résultat : **{mentions[0]}**\n📈 **+{pts} pts**\n\n_{used_ticket_type}_", color=0xFFD700)
    embed.set_image(url=URL_BANNER_ULTRA)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="classement", description="🏆 Top 10 des joueurs")
@app_commands.allowed_installs(guilds=True)
@app_commands.allowed_contexts(guilds=True)
async def classement(interaction: discord.Interaction):
    s = sorted(gacha_data.get("scores", {}).items(), key=lambda x: x[1], reverse=True)[:10]
    desc = "\n".join([f"**{i+1}.** <@{u}> — **{pts}** pts" for i, (u, pts) in enumerate(s)]) or "Aucun score."
    await interaction.response.send_message(embed=discord.Embed(title="🏆 Classement Gacha", description=desc, color=0x3498db))

# ====================================================
#                 COMMANDES IA & MEDIA
# ====================================================
@bot.tree.command(name="discussion", description="💬 Discuter avec l'IA")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def discussion(interaction: discord.Interaction, message: str):
    await interaction.response.defer()
    if not check_token_limit(interaction.user.id, message, get_user_tier(interaction) in ["PLUS", "PRO"]):
        await send_limit_message(interaction, interaction.user.id)
        return
    try:
        chat = get_chat_session(interaction.channel_id)
        response = await asyncio.to_thread(chat.send_message, message)
        update_cost(response)
        await interaction.followup.send(response.text[:2000])
    except: await interaction.followup.send("❌ Erreur IA.")

@bot.tree.command(name="imagine", description="🎨 Créer une image")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def imagine(interaction: discord.Interaction, prompt: str):
    uid = interaction.user.id
    tier = get_user_tier(interaction)
    cd = COOLDOWN_IMG_VIP if tier in ["PLUS", "PRO"] else COOLDOWN_IMG_FREE
    if uid in user_cooldowns_img and (time.time() - user_cooldowns_img[uid] < cd):
        await interaction.response.send_message(f"⏳ Attends encore un peu !", ephemeral=True)
        return
    user_cooldowns_img[uid] = time.time()
    await interaction.response.defer()
    img = await generate_image_hf(prompt)
    if img:
        stats_data["total_images"] += 1
        save_data(STATS_FILE, stats_data)
        await interaction.followup.send(file=discord.File(io.BytesIO(img), "img.png"), content=f"🎨 **{prompt}**")
    else: await interaction.followup.send("❌ Erreur.")

@bot.tree.command(name="video", description="🎥 Simulation Vidéo (Réservé PRO)")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def video(interaction: discord.Interaction, prompt: str):
    if get_user_tier(interaction) != "PRO":
        await interaction.response.send_message("💎 Réservé PRO !", ephemeral=True)
        return
    await interaction.response.defer()
    img = await generate_image_hf("Cinematic shot, 8k, " + prompt)
    if img: await interaction.followup.send(file=discord.File(io.BytesIO(img), "vid.png"), content=f"🎥 **{prompt}**")
    else: await interaction.followup.send("❌ Erreur.")

@bot.tree.command(name="premium", description="💎 Boutique")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def premium(interaction: discord.Interaction):
    link = f"https://discord.com/application-directory/{bot.user.id}/store"
    embed = discord.Embed(title="💎 Boutique", description="Booste ton IA et tente ta chance !", color=0x4285F4)
    embed.add_field(name="🥉 IA Plus / 🥇 IA Pro", value="Plus de mémoire et Vidéo", inline=True)
    embed.add_field(name="🎟️ Ticket Ultra / ✨ Boost Chance", value="Pour le Gacha", inline=True)
    embed.add_field(name="💳 PayPal", value="[5€ (Manuel)](https://paypal.me/Cel209YT/5)", inline=False)
    v = discord.ui.View(); v.add_item(discord.ui.Button(label="🛒 Boutique", url=link, style=discord.ButtonStyle.link))
    await interaction.response.send_message(embed=embed, view=v, ephemeral=True)

# ====================================================
#               COMMANDES ADMIN & UTILITAIRES
# ====================================================
@bot.tree.command(name="admin_cheat", description="⚠️ Abuse (Owner) : Donne 100 tickets et 50k points")
async def admin_cheat(interaction: discord.Interaction, user: discord.Member):
    if interaction.user.id != OWNER_ID: return
    u = str(user.id)
    gacha_data["manual_tickets"][u] = gacha_data["manual_tickets"].get(u, 0) + 100
    update_gacha_score(u, 50000)
    await interaction.response.send_message(f"⚠️ Cheat appliqué pour {user.mention} : +100 Tickets, +50000 Pts.", ephemeral=False)

@bot.tree.command(name="set_points", description="🔧 Définir le score Gacha d'un joueur (Owner)")
async def set_points(interaction: discord.Interaction, user: discord.Member, points: int):
    if interaction.user.id != OWNER_ID: return
    uid_str = str(user.id)
    if "scores" not in gacha_data: gacha_data["scores"] = {}
    gacha_data["scores"][uid_str] = max(0, points)
    save_data(GACHA_FILE, gacha_data)
    await interaction.response.send_message(f"✅ Le score de {user.mention} a été défini sur {max(0, points)} pts.", ephemeral=False)

@bot.tree.command(name="reset_leaderboard", description="⚠️ Remettre tous les scores Gacha à zéro (Owner)")
async def reset_leaderboard(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID: return
    gacha_data["scores"] = {}
    save_data(GACHA_FILE, gacha_data)
    await interaction.response.send_message("⚠️ Le classement a été entièrement réinitialisé.", ephemeral=False)

@bot.tree.command(name="give_ticket", description="🎁 Donner des tickets Ultra manuels (Owner)")
async def give_ticket(interaction: discord.Interaction, user: discord.Member, nombre: int):
    if interaction.user.id != OWNER_ID: return
    u = str(user.id); gacha_data["manual_tickets"][u] = gacha_data["manual_tickets"].get(u, 0) + nombre
    save_data(GACHA_FILE, gacha_data)
    await interaction.response.send_message(f"🎁 {nombre} tickets ajoutés pour {user.name} !")

@bot.tree.command(name="remove_ticket", description="🚫 Retirer des tickets Ultra manuels (Owner)")
async def remove_ticket(interaction: discord.Interaction, user: discord.Member, nombre: int):
    if interaction.user.id != OWNER_ID: return
    u = str(user.id)
    actuel = gacha_data["manual_tickets"].get(u, 0)
    gacha_data["manual_tickets"][u] = max(0, actuel - nombre)
    save_data(GACHA_FILE, gacha_data)
    await interaction.response.send_message(f"🚫 Tickets ajustés pour {user.name}.")

@bot.tree.command(name="setup_jeux", description="🎮 Notifications Steam")
@app_commands.checks.has_permissions(manage_channels=True)
async def setup_jeux(interaction: discord.Interaction):
    cid = interaction.channel_id
    if cid in notifs_data["channels"]: notifs_data["channels"].remove(cid)
    else: notifs_data["channels"].append(cid)
    save_data(NOTIFS_FILE, notifs_data)
    await interaction.response.send_message("✅ Configuration mise à jour.", ephemeral=True)

@bot.tree.command(name="test_jeux", description="🔧 Forcer la vérification Steam (Owner)")
async def test_jeux(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID: return
    await interaction.response.send_message("🔄 Exécution manuelle...", ephemeral=True)
    await check_free_games.coro()

@bot.tree.command(name="vip", description="💎 Activer VIP manuel (Owner)")
async def vip(interaction: discord.Interaction, code: str):
    if code in vip_data["keys"]:
        vip_data["keys"].remove(code)
        vip_data["users"].append(interaction.user.id)
        save_data(VIP_FILE, vip_data)
        await interaction.response.send_message("🎉 VIP activé !", ephemeral=False)
    else: await interaction.response.send_message("❌ Code invalide.", ephemeral=True)

@bot.tree.command(name="gen_key", description="🔑 Créer clé VIP (Owner)")
async def gen_key(interaction: discord.Interaction, code: str):
    if interaction.user.id == OWNER_ID:
        vip_data["keys"].append(code)
        save_data(VIP_FILE, vip_data)
        await interaction.response.send_message(f"✅ Clé : `{code}`", ephemeral=True)
    else: await interaction.response.send_message("⛔", ephemeral=True)

@bot.tree.command(name="remove_vip", description="🚫 Retirer VIP manuel (Owner)")
async def remove_vip(interaction: discord.Interaction, user_id: str):
    if interaction.user.id != OWNER_ID: return
    try:
        uid = int(user_id)
        if uid in vip_data["users"]:
            vip_data["users"].remove(uid)
            save_data(VIP_FILE, vip_data)
            await interaction.response.send_message(f"🚫 VIP retiré.", ephemeral=True)
        else: await interaction.response.send_message("ID non VIP.", ephemeral=True)
    except: await interaction.response.send_message("ID invalide.", ephemeral=True)

@bot.tree.command(name="cout", description="📊 Stats IA (Owner)")
async def cout(interaction: discord.Interaction):
    if interaction.user.id == OWNER_ID:
        await interaction.response.send_message(f"📊 Tokens: {stats_data['total_input']} | Images: {stats_data['total_images']}", ephemeral=True)

@bot.tree.command(name="traduire", description="🌍 Traduire")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def traduire(interaction: discord.Interaction, langue: str, texte: str):
    await interaction.response.defer()
    try:
        res = await asyncio.to_thread(model.generate_content, f"Traduis en {langue}: {texte}")
        await interaction.followup.send(f"**Traduction :**\n{res.text}")
    except: await interaction.followup.send("Erreur")

@bot.tree.command(name="systeme", description="💻 État CPU")
async def systeme(interaction: discord.Interaction):
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f: t = int(f.read()) / 1000
    except: t = 0
    await interaction.response.send_message(f"🌡 CPU: {t}°C", ephemeral=True)

@bot.tree.command(name="ping", description="🏓 Ping")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency*1000)}ms", ephemeral=True)

@bot.tree.command(name="reset", description="🧠 Reset Mémoire IA")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def reset(interaction: discord.Interaction):
    if interaction.channel_id in chat_sessions:
        del chat_sessions[interaction.channel_id]
        await interaction.response.send_message("🧠 Mémoire effacée.", ephemeral=True)
    else: await interaction.response.send_message("Rien à effacer.", ephemeral=True)

@bot.tree.command(name="effacer", description="🧹 Clean Chat")
@app_commands.checks.has_permissions(manage_messages=True)
async def effacer(interaction: discord.Interaction, nombre: int):
    await interaction.channel.purge(limit=min(nombre, 100))
    await interaction.response.send_message("🧹 Terminé.", ephemeral=True)

bot.run(DISCORD_TOKEN)
