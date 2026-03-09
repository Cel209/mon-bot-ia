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

# Initialisation structure Gacha avec tables dynamiques
default_gacha = {
    "last_daily": {}, "active_powers": [], "manual_tickets": {}, 
    "scores": {}, "weekend_claims": {}, "loans": {}, "loan_counts": {},
    "tables": {
        "standard": [
            {"nom": "Rien (Échec)", "role_id": None, "poids": 70.0, "temp_hours": 0, "score": 0},
            {"nom": "Titre Commun", "role_id": ROLE_COMMUN, "poids": 29.9, "temp_hours": 0, "score": 10},
            {"nom": "Pouvoir Éphémère (2h)", "role_id": ROLE_POUVOIR_TEMP, "poids": 0.099, "temp_hours": 2, "score": 50},
            {"nom": "Titre Rare", "role_id": ROLE_TITRE_RARE, "poids": 0.001, "temp_hours": 0, "score": 200}
        ],
        "ultra_base": [
            {"nom": "Pouvoir Éphémère (24h)", "role_id": ROLE_POUVOIR_TEMP, "poids": 99.999, "temp_hours": 24, "score": 100},
            {"nom": "Titre Rare", "role_id": ROLE_TITRE_RARE, "poids": 0.001, "temp_hours": 0, "score": 50000}
        ],
        "ultra_boosted": [
            {"nom": "Pouvoir Éphémère (24h)", "role_id": ROLE_POUVOIR_TEMP, "poids": 99.0, "temp_hours": 24, "score": 100},
            {"nom": "Titre Rare", "role_id": ROLE_TITRE_RARE, "poids": 1.0, "temp_hours": 0, "score": 50000}
        ]
    }
}

gacha_data = load_data(GACHA_FILE, default_gacha)
if "tables" not in gacha_data: gacha_data["tables"] = default_gacha["tables"]

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
user_cooldowns_btc = {}

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
        try: await channel_or_interaction.followup.send(embed=embed, ephemeral=True)
        except: pass
    else:
        try: await channel_or_interaction.send(embed=embed)
        except: pass

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
    if not guild: return []
    member = guild.get_member(uid)
    if not member: return []

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
                    except: pass
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

def apply_urssaf_tax(uid_str, gain_brut):
    dette = gacha_data.get("loans", {}).get(uid_str, 0)
    if dette > 0 and gain_brut > 0:
        taxe = int(gain_brut * 0.5)
        update_gacha_score(str(OWNER_ID), taxe)
        return gain_brut - taxe, taxe
    return gain_brut, 0

# ====================================================
#               LOGIQUE TICKETS
# ====================================================
class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Suppression du ticket dans 5 secondes...", ephemeral=False)
        await asyncio.sleep(5)
        await interaction.channel.delete()

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📩 Créer un Ticket", style=discord.ButtonStyle.primary, custom_id="persistent_ticket_button")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="Tickets")
        if not category:
            try: category = await guild.create_category("Tickets")
            except: pass
        
        channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=category,
            overwrites={
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
        )
        await interaction.response.send_message(f"✅ Ton ticket a été créé : {channel.mention}", ephemeral=True)
        
        embed = discord.Embed(title="Nouveau Ticket", description=f"Bienvenue {interaction.user.mention}.\nUn administrateur va te répondre prochainement.", color=0x3498db)
        await channel.send(embed=embed, view=CloseTicketView())

# ====================================================
#               LOGIQUE JEUX (VUES)
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

    def is_full(self): return all(self.board[0][c] != 0 for c in range(7))

    def get_drop_row(self, col):
        for r in range(5, -1, -1):
            if self.board[r][col] == 0: return r
        return -1

    def drop_piece(self, col, player):
        r = self.get_drop_row(col)
        if r != -1:
            self.board[r][col] = player
            return True
        return False

    def render_board(self):
        symbols = {0: "⚪", 1: "🔴", 2: "🟡"}
        res = ""
        for row in self.board: res += "".join(symbols[cell] for cell in row) + "\n"
        res += "1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣"
        return res

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Ce n'est pas ta partie.", ephemeral=True)
            return
        
        await interaction.response.defer()
        col = int(self.select.values[0])
        if self.board[0][col] != 0:
            await interaction.followup.send("Colonne pleine !", ephemeral=True)
            return

        self.drop_piece(col, 1)
        if self.check_win(1):
            self.game_over = True
            self.clear_items()
            table = gacha_data["tables"]["standard"]
            results = perform_gacha_pulls(table, 1)
            mentions = await apply_gacha_rewards(interaction, results)
            
            pts_brut = results[0]["score"]
            pts_net, taxe = apply_urssaf_tax(str(self.user.id), pts_brut)
            update_gacha_score(str(self.user.id), pts_net)
            
            mention_txt = mentions[0] if mentions else "Aucune récompense"
            desc = f"{self.render_board()}\n\n🎁 **Victoire !** Tu as gagné un Tirage :\n🔸 {mention_txt} (+{pts_net} pts)"
            if taxe > 0: desc += f"\n🚨 **URSSAF :** {taxe} pts versés à l'État (Dette)."
                
            embed = discord.Embed(title="🔴 Victoire !", description=desc, color=0x00FF00)
            await interaction.edit_original_response(embed=embed, view=self)
            return

        if self.is_full():
            self.game_over = True
            self.clear_items()
            await interaction.edit_original_response(embed=discord.Embed(title="🤝 Match Nul", description=self.render_board(), color=0x808080), view=self)
            return

        valid_cols = [c for c in range(7) if self.board[0][c] == 0]
        bot_col = None
        for c in valid_cols:
            r = self.get_drop_row(c)
            self.board[r][c] = 2
            if self.check_win(2): bot_col = c
            self.board[r][c] = 0
            if bot_col is not None: break
            
        if bot_col is None:
            for c in valid_cols:
                r = self.get_drop_row(c)
                self.board[r][c] = 1
                if self.check_win(1): bot_col = c
                self.board[r][c] = 0
                if bot_col is not None: break
                
        if bot_col is None: bot_col = random.choice(valid_cols)
        self.drop_piece(bot_col, 2)

        if self.check_win(2):
            self.game_over = True
            self.clear_items()
            await interaction.edit_original_response(embed=discord.Embed(title="🟡 Défaite", description=f"{self.render_board()}\n\nLe bot a gagné.", color=0xFF0000), view=self)
            return
            
        await interaction.edit_original_response(embed=discord.Embed(title="🔴 Puissance 4 🟡", description=self.render_board(), color=0x3498db), view=self)

def get_card():
    suits = ['♠', '♥', '♦', '♣']
    ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    return f"{random.choice(ranks)}{random.choice(suits)}"

def calc_hand(hand):
    val = 0
    aces = 0
    for card in hand:
        rank = card[:-1]
        if rank in ['J', 'Q', 'K']: val += 10
        elif rank == 'A':
            aces += 1
            val += 11
        else: val += int(rank)
    while val > 21 and aces > 0:
        val -= 10
        aces -= 1
    return val

class BlackjackView(discord.ui.View):
    def __init__(self, user, mise):
        super().__init__(timeout=120)
        self.user = user
        self.mise = mise
        self.player_hand = [get_card(), get_card()]
        self.dealer_hand = [get_card(), get_card()]
        self.taxe_urssaf = 0
        self.gain_net = 0

    def render_embed(self, game_over=False):
        p_val = calc_hand(self.player_hand)
        d_val = calc_hand(self.dealer_hand) if game_over else calc_hand([self.dealer_hand[0]])
        d_cards = " ".join(self.dealer_hand) if game_over else f"{self.dealer_hand[0]} 🂠"
        
        color = 0x3498db
        title = "🃏 Blackjack"
        if game_over:
            if p_val > 21:
                title = f"💥 Buste ! Tu perds {self.mise} pts."
                color = 0xFF0000
            elif d_val > 21 or p_val > d_val:
                title = f"🎉 Victoire ! Tu gagnes {self.gain_net} pts."
                color = 0x00FF00
            elif p_val == d_val:
                title = "🤝 Égalité. Mise récupérée."
                color = 0x808080
            else:
                title = f"💀 Le croupier gagne. Tu perds {self.mise} pts."
                color = 0xFF0000

        embed = discord.Embed(title=title, color=color)
        embed.add_field(name=f"Tes cartes ({p_val})", value=" ".join(self.player_hand), inline=False)
        embed.add_field(name=f"Croupier ({d_val})", value=d_cards, inline=False)
        if self.taxe_urssaf > 0:
            embed.set_footer(text=f"🚨 URSSAF : {self.taxe_urssaf} pts versés à l'État.")
        return embed

    @discord.ui.button(label="Tirer", style=discord.ButtonStyle.primary, custom_id="hit")
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id: return
        await interaction.response.defer()
        
        self.player_hand.append(get_card())
        p_val = calc_hand(self.player_hand)
        
        if p_val > 21:
            self.clear_items()
            update_gacha_score(str(self.user.id), -self.mise)
            await interaction.edit_original_response(embed=self.render_embed(True), view=self)
        else:
            await interaction.edit_original_response(embed=self.render_embed(), view=self)

    @discord.ui.button(label="Rester", style=discord.ButtonStyle.secondary, custom_id="stand")
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id: return
        await interaction.response.defer()
        self.clear_items()
        
        p_val = calc_hand(self.player_hand)
        d_val = calc_hand(self.dealer_hand)
        
        while d_val < 17:
            self.dealer_hand.append(get_card())
            d_val = calc_hand(self.dealer_hand)
            
        uid_str = str(self.user.id)
        if d_val > 21 or p_val > d_val:
            gain_brut = int(self.mise * 1.5) if p_val == 21 and len(self.player_hand) == 2 else self.mise
            self.gain_net, self.taxe_urssaf = apply_urssaf_tax(uid_str, gain_brut)
            update_gacha_score(uid_str, self.gain_net)
        elif p_val < d_val:
            update_gacha_score(uid_str, -self.mise)
            
        await interaction.edit_original_response(embed=self.render_embed(True), view=self)

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
    bot.add_view(TicketView())
    bot.add_view(CloseTicketView())
    try:
        synced = await bot.tree.sync()
        print(f'✅ {len(synced)} commandes synchronisées avec succès.')
    except Exception as e:
        print(f'❌ Erreur de synchronisation des commandes : {e}')
    
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="paypal.me/Cel209YT"))
    if not check_free_games.is_running(): check_free_games.start()
    if not check_expired_powers.is_running(): check_expired_powers.start()

@bot.event
async def on_message(message):
    if message.author.bot: return
    
    # Ignore les messages ne contenant aucun texte
    prompt = message.content.strip()
    if not prompt: return

    is_vip = message.author.id in vip_data["users"] or message.author.id == OWNER_ID
    if not check_token_limit(message.author.id, prompt, is_vip):
        await send_limit_message(message.channel, message.author.id)
        return
        
    async with message.channel.typing():
        try:
            chat = get_chat_session(message.channel.id)
            response = await asyncio.to_thread(chat.send_message, prompt)
            update_cost(response)
            if response.text:
                await message.channel.send(response.text[:2000])
        except: 
            pass # Fail silencieux en cas d'erreur de l'API pour éviter le spam

# ====================================================
#                 COMMANDES TICKETS
# ====================================================
@bot.tree.command(name="setup_ticket", description="📩 Installer le panel de tickets")
@app_commands.checks.has_permissions(administrator=True)
async def setup_ticket(interaction: discord.Interaction):
    embed = discord.Embed(title="📩 Support", description="Cliquez sur le bouton ci-dessous pour ouvrir un ticket.", color=0x3498db)
    await interaction.channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message("✅ Panel installé.", ephemeral=True)

@bot.tree.command(name="ticket", description="📩 Créer un ticket de support directement")
async def ticket_cmd(interaction: discord.Interaction):
    guild = interaction.guild
    category = discord.utils.get(guild.categories, name="Tickets")
    if not category:
        try: category = await guild.create_category("Tickets")
        except: pass
    
    channel = await guild.create_text_channel(
        name=f"ticket-{interaction.user.name}",
        category=category,
        overwrites={
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
    )
    await interaction.response.send_message(f"✅ Ton ticket a été créé : {channel.mention}", ephemeral=True)
    
    embed = discord.Embed(title="Nouveau Ticket", description=f"Bienvenue {interaction.user.mention}.\nUn administrateur va te répondre prochainement.", color=0x3498db)
    await channel.send(embed=embed, view=CloseTicketView())

# ====================================================
#                 COMMANDES ÉCONOMIE & FUN
# ====================================================
@bot.tree.command(name="miner_btc", description="⛏️ Miner du Bitcoin (+50 pts) - Cooldown 1h")
@app_commands.allowed_installs(guilds=True)
@app_commands.allowed_contexts(guilds=True)
async def miner_btc(interaction: discord.Interaction):
    uid = interaction.user.id
    now = time.time()
    if uid in user_cooldowns_btc and now - user_cooldowns_btc[uid] < 3600:
        restant = int(3600 - (now - user_cooldowns_btc[uid]))
        await interaction.response.send_message(f"⏳ Ta carte graphique surchauffe. Reviens dans {restant//60} min.", ephemeral=True)
        return
        
    user_cooldowns_btc[uid] = now
    update_gacha_score(str(uid), 50)
    await interaction.response.send_message("⛏️ Tu as miné **+50 pts** avec succès !", ephemeral=False)

@bot.tree.command(name="depression", description="🎲 Quitte ou double émotionnel (Bonus ou Malus aléatoire)")
@app_commands.allowed_installs(guilds=True)
@app_commands.allowed_contexts(guilds=True)
async def depression(interaction: discord.Interaction):
    uid_str = str(interaction.user.id)
    if random.choice([True, False]):
        gain = random.randint(100, 1000)
        update_gacha_score(uid_str, gain)
        await interaction.response.send_message(f"✨ Lueur d'espoir ! Tu sors de la dépression et gagnes **{gain} pts**.", ephemeral=False)
    else:
        perte = random.randint(100, 1000)
        update_gacha_score(uid_str, -perte)
        await interaction.response.send_message(f"🌧️ La dépression te frappe... Tu perds **{perte} pts**.", ephemeral=False)

@bot.tree.command(name="pret", description="🏦 Emprunter (Max: 10k, 10 prêts max, Intérêts: 150%+)")
@app_commands.allowed_installs(guilds=True)
@app_commands.allowed_contexts(guilds=True)
async def pret(interaction: discord.Interaction, montant: int):
    if montant <= 0 or montant > 10000:
        await interaction.response.send_message("❌ Montant invalide. Le prêt est limité entre 1 et 10 000 pts.", ephemeral=True)
        return
    uid_str = str(interaction.user.id)
    dette_actuelle = gacha_data.get("loans", {}).get(uid_str, 0)
    loan_count = gacha_data.get("loan_counts", {}).get(uid_str, 0)
    
    if loan_count >= 10:
        await interaction.response.send_message("❌ Refusé. Tu as atteint la limite stricte de 10 prêts actifs simultanés.", ephemeral=True)
        return

    if "loans" not in gacha_data: gacha_data["loans"] = {}
    if "loan_counts" not in gacha_data: gacha_data["loan_counts"] = {}

    multiplicateur = 2.5 + (0.5 * loan_count)
    dette_ajoutee = montant * multiplicateur
    
    gacha_data["loans"][uid_str] = dette_actuelle + dette_ajoutee
    gacha_data["loan_counts"][uid_str] = loan_count + 1
    update_gacha_score(uid_str, montant)
    
    await interaction.response.send_message(f"🏦 Prêt n°{loan_count+1} accordé : **+{montant} pts**.\n📉 Taux d'intérêt punitif appliqué : **x{multiplicateur}**.\n📊 Nouvelle dette totale : **{int(gacha_data['loans'][uid_str])} pts**.")

@bot.tree.command(name="rembourser", description="💸 Rembourser ta dette avec ton score actuel")
@app_commands.allowed_installs(guilds=True)
@app_commands.allowed_contexts(guilds=True)
async def rembourser(interaction: discord.Interaction, montant: int):
    if montant <= 0:
        await interaction.response.send_message("❌ Montant invalide.", ephemeral=True)
        return
    uid_str = str(interaction.user.id)
    dette_actuelle = gacha_data.get("loans", {}).get(uid_str, 0)
    score_actuel = gacha_data.get("scores", {}).get(uid_str, 0)

    if dette_actuelle <= 0:
        await interaction.response.send_message("✅ Tu n'as aucune dette en cours.", ephemeral=True)
        return
    if montant > score_actuel:
        await interaction.response.send_message(f"❌ Fonds insuffisants (Score: {score_actuel} pts).", ephemeral=True)
        return

    montant_rembourse = min(montant, dette_actuelle)
    gacha_data["loans"][uid_str] -= montant_rembourse
    update_gacha_score(uid_str, -int(montant_rembourse))
    
    if gacha_data["loans"][uid_str] <= 0:
        gacha_data["loans"][uid_str] = 0
        gacha_data["loan_counts"][uid_str] = 0 
        
    await interaction.response.send_message(f"💸 Tu as remboursé **{int(montant_rembourse)} pts**.\n📉 Dette restante : **{int(gacha_data['loans'][uid_str])} pts**.")

@bot.tree.command(name="acheter_ticket", description="🛒 Acheter 1 Ticket Ultra avec tes points (10 000 pts)")
@app_commands.allowed_installs(guilds=True)
@app_commands.allowed_contexts(guilds=True)
async def acheter_ticket(interaction: discord.Interaction, quantite: int = 1):
    if quantite <= 0: return
    cout_total = quantite * 10000
    uid_str = str(interaction.user.id)
    score = gacha_data.get("scores", {}).get(uid_str, 0)
    
    if score < cout_total:
        await interaction.response.send_message(f"❌ Fonds insuffisants. Il te faut {cout_total} pts.", ephemeral=True)
        return
        
    update_gacha_score(uid_str, -cout_total)
    gacha_data["manual_tickets"][uid_str] = gacha_data.get("manual_tickets", {}).get(uid_str, 0) + quantite
    save_data(GACHA_FILE, gacha_data)
    await interaction.response.send_message(f"🛒 Transaction validée ! Tu as échangé **{cout_total} pts** contre **{quantite}x Ticket(s) Ultra**.")

# ====================================================
#                 COMMANDES JEUX & CASINO
# ====================================================
@bot.tree.command(name="machine_a_sous", description="🎰 Jouer à la Machine à sous (x2, x10, x50)")
@app_commands.allowed_installs(guilds=True)
@app_commands.allowed_contexts(guilds=True)
async def machine_a_sous(interaction: discord.Interaction, mise: int):
    uid_str = str(interaction.user.id)
    score_actuel = gacha_data.get("scores", {}).get(uid_str, 0)
    if mise <= 0 or mise > score_actuel:
        await interaction.response.send_message(f"❌ Mise invalide (Score: {score_actuel} pts).", ephemeral=True)
        return
        
    symboles = ["🍒", "🍋", "🍉", "🔔", "💎", "7️⃣"]
    res = [random.choice(symboles) for _ in range(3)]
    
    gagne = False
    mult = 0
    if res[0] == res[1] == res[2]:
        gagne = True
        mult = 50 if res[0] == "7️⃣" else 10
    elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
        gagne = True
        mult = 2

    affichage = f"🎰 **[ {res[0]} | {res[1]} | {res[2]} ]** 🎰"
    
    if gagne:
        gain_brut = (mise * mult) - mise
        gain_net, taxe = apply_urssaf_tax(uid_str, gain_brut)
        update_gacha_score(uid_str, gain_net)
        msg = f"{affichage}\n🎉 **Gagné !** Multiplicateur **x{mult}**. Tu remportes **{gain_net} pts**."
        if taxe > 0: msg += f"\n🚨 **URSSAF :** {taxe} pts versés à l'État (Dette)."
        await interaction.response.send_message(msg)
    else:
        update_gacha_score(uid_str, -mise)
        await interaction.response.send_message(f"{affichage}\n💀 **Perdu.** Tu perds **{mise} pts**.")

@bot.tree.command(name="blackjack", description="🃏 Jouer au Blackjack")
@app_commands.allowed_installs(guilds=True)
@app_commands.allowed_contexts(guilds=True)
async def blackjack(interaction: discord.Interaction, mise: int):
    uid_str = str(interaction.user.id)
    score_actuel = gacha_data.get("scores", {}).get(uid_str, 0)
    if mise <= 0 or mise > score_actuel:
        await interaction.response.send_message(f"❌ Mise invalide (Score: {score_actuel} pts).", ephemeral=True)
        return
    view = BlackjackView(interaction.user, mise)
    await interaction.response.send_message(embed=view.render_embed(), view=view)

@bot.tree.command(name="roulette", description="🎡 Miser à la roulette")
@app_commands.allowed_installs(guilds=True)
@app_commands.allowed_contexts(guilds=True)
@app_commands.choices(choix=[
    app_commands.Choice(name="🔴 Rouge (x2)", value="rouge"),
    app_commands.Choice(name="⚫ Noir (x2)", value="noir"),
    app_commands.Choice(name="🟢 Vert (Zéro) (x14)", value="vert"),
    app_commands.Choice(name="🔢 Pair (x2)", value="pair"),
    app_commands.Choice(name="🔢 Impair (x2)", value="impair")
])
async def roulette(interaction: discord.Interaction, choix: app_commands.Choice[str], mise: int):
    uid_str = str(interaction.user.id)
    score_actuel = gacha_data.get("scores", {}).get(uid_str, 0)
    if mise <= 0 or mise > score_actuel:
        await interaction.response.send_message(f"❌ Mise invalide (Score: {score_actuel} pts).", ephemeral=True)
        return
        
    num = random.randint(0, 36)
    couleur = "vert" if num == 0 else ("rouge" if num in [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36] else "noir")
    parite = "pair" if num != 0 and num % 2 == 0 else ("impair" if num != 0 else "aucun")
    
    gagne = False
    multiplicateur = 0
    if choix.value in ["rouge", "noir", "vert"] and choix.value == couleur:
        gagne = True
        multiplicateur = 14 if choix.value == "vert" else 2
    elif choix.value in ["pair", "impair"] and choix.value == parite:
        gagne = True
        multiplicateur = 2
        
    emoji = "🔴" if couleur == "rouge" else "⚫" if couleur == "noir" else "🟢"
    if gagne:
        gain_brut = (mise * multiplicateur) - mise
        gain_net, taxe = apply_urssaf_tax(uid_str, gain_brut)
        update_gacha_score(uid_str, gain_net)
        msg = f"🎡 Le **{num} {emoji}** sort !\n🎉 Gagné ! Tu remportes **{gain_net} pts**."
        if taxe > 0: msg += f"\n🚨 **URSSAF :** {taxe} pts versés à l'État (Dette)."
        await interaction.response.send_message(msg)
    else:
        update_gacha_score(uid_str, -mise)
        await interaction.response.send_message(f"🎡 Le **{num} {emoji}** sort !\n💀 Perdu. Tu perds **{mise} pts**.")

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
        gain_net, taxe = apply_urssaf_tax(uid_str, mise)
        update_gacha_score(uid_str, gain_net)
        msg = f"🪙 La pièce tombe sur **{resultat.capitalize()}** ! 🎉 Tu gagnes **{gain_net}** pts."
        if taxe > 0: msg += f"\n🚨 **URSSAF :** {taxe} pts versés à l'État (Dette)."
        await interaction.response.send_message(msg)
    else:
        update_gacha_score(uid_str, -mise)
        await interaction.response.send_message(f"🪙 La pièce tombe sur **{resultat.capitalize()}**... 💀 Tu perds **{mise}** pts.")

# ====================================================
#                 COMMANDES GACHA & CLASSEMENT
# ====================================================
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
    table = gacha_data["tables"]["standard"]
    results = perform_gacha_pulls(table, 10)
    mentions = await apply_gacha_rewards(interaction, results)
    
    pts_brut = sum(r["score"] for r in results)
    pts_net, taxe = apply_urssaf_tax(uid_str, pts_brut)
    update_gacha_score(uid_str, pts_net)
    
    desc = "\n".join([f"🔸 {m}" for m in mentions]) + f"\n\n📈 **+{pts_net} pts**"
    if taxe > 0: desc += f"\n🚨 **URSSAF :** {taxe} pts versés à l'État."
    
    embed = discord.Embed(title="🎰 Tirage Quotidien (x10)", description=desc, color=0x3498db)
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
            used_ticket_type = "💳 Achat Boutique"
        elif manual > 0:
            gacha_data["manual_tickets"][uid_str] -= 1
            save_data(GACHA_FILE, gacha_data)
            used_ticket_type = "🎟️ Ticket Inventaire"
        else:
            await interaction.response.send_message("🎟️ Aucun Ticket Ultra possédé. Utilise `/acheter_ticket` ou visite la boutique ! (/premium)", ephemeral=True)
            return

    table = gacha_data["tables"]["ultra_boosted"] if any(e.sku_id == SKU_BOOST_CHANCE for e in interaction.entitlements) else gacha_data["tables"]["ultra_base"]
    results = perform_gacha_pulls(table, 1)
    mentions = await apply_gacha_rewards(interaction, results)
    
    pts_brut = results[0]["score"]
    pts_net, taxe = apply_urssaf_tax(uid_str, pts_brut)
    update_gacha_score(uid_str, pts_net)
    
    desc = f"🌟 Résultat : **{mentions[0]}**\n📈 **+{pts_net} pts**\n\n_{used_ticket_type}_"
    if taxe > 0: desc += f"\n🚨 **URSSAF :** {taxe} pts versés à l'État."
    
    embed = discord.Embed(title="✨ INVOCATION LÉGENDAIRE ✨", description=desc, color=0xFFD700)
    embed.set_image(url=URL_BANNER_ULTRA)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="classement", description="🏆 Top 10 des joueurs (Points Nets)")
@app_commands.allowed_installs(guilds=True)
@app_commands.allowed_contexts(guilds=True)
async def classement(interaction: discord.Interaction):
    scores = gacha_data.get("scores", {})
    loans = gacha_data.get("loans", {})
    net_scores = {u: scores.get(u, 0) - loans.get(u, 0) for u in scores}
    s = sorted(net_scores.items(), key=lambda x: x[1], reverse=True)[:10]
    
    desc = "\n".join([f"**{i+1}.** <@{u}> — **{int(pts)} pts nets** (Score: {scores.get(u,0)} | Dette: {int(loans.get(u,0))})" for i, (u, pts) in enumerate(s)]) or "Aucun score."
    await interaction.response.send_message(embed=discord.Embed(title="🏆 Classement Gacha", description=desc, color=0x3498db))

# ====================================================
#                 COMMANDES IA & MEDIA
# ====================================================
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
#               UTILITAIRES & ADMIN
# ====================================================
@bot.tree.command(name="admin_proba_standard", description="🔧 Modifier probabilités Gacha Standard (Owner)")
async def admin_proba_standard(interaction: discord.Interaction, rien: float, commun: float, pouvoir: float, rare: float):
    if interaction.user.id != OWNER_ID: return
    gacha_data["tables"]["standard"][0]["poids"] = rien
    gacha_data["tables"]["standard"][1]["poids"] = commun
    gacha_data["tables"]["standard"][2]["poids"] = pouvoir
    gacha_data["tables"]["standard"][3]["poids"] = rare
    save_data(GACHA_FILE, gacha_data)
    await interaction.response.send_message(f"✅ Probas Standard MAJ: Rien({rien}), Commun({commun}), Pouvoir({pouvoir}), Rare({rare})", ephemeral=False)

@bot.tree.command(name="admin_proba_ultra", description="🔧 Modifier probabilités Gacha Ultra (Owner)")
@app_commands.choices(table=[app_commands.Choice(name="Base", value="ultra_base"), app_commands.Choice(name="Boosté", value="ultra_boosted")])
async def admin_proba_ultra(interaction: discord.Interaction, table: app_commands.Choice[str], pouvoir: float, rare: float):
    if interaction.user.id != OWNER_ID: return
    gacha_data["tables"][table.value][0]["poids"] = pouvoir
    gacha_data["tables"][table.value][1]["poids"] = rare
    save_data(GACHA_FILE, gacha_data)
    await interaction.response.send_message(f"✅ Probas Ultra {table.name} MAJ: Pouvoir({pouvoir}), Rare({rare})", ephemeral=False)

@bot.tree.command(name="set_dette", description="🔧 Définir la dette exacte d'un joueur (Owner)")
async def set_dette(interaction: discord.Interaction, user: discord.Member, montant: int):
    if interaction.user.id != OWNER_ID: return
    uid_str = str(user.id)
    if "loans" not in gacha_data: gacha_data["loans"] = {}
    gacha_data["loans"][uid_str] = max(0, montant)
    save_data(GACHA_FILE, gacha_data)
    await interaction.response.send_message(f"✅ La dette de {user.mention} a été définie sur {max(0, montant)} pts.", ephemeral=False)

@bot.tree.command(name="set_nb_prets", description="🔧 Définir le nombre de prêts actifs d'un joueur (Owner)")
async def set_nb_prets(interaction: discord.Interaction, user: discord.Member, nombre: int):
    if interaction.user.id != OWNER_ID: return
    uid_str = str(user.id)
    if "loan_counts" not in gacha_data: gacha_data["loan_counts"] = {}
    gacha_data["loan_counts"][uid_str] = max(0, nombre)
    save_data(GACHA_FILE, gacha_data)
    await interaction.response.send_message(f"✅ Le nombre de prêts de {user.mention} a été défini sur {max(0, nombre)}.", ephemeral=False)

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
    gacha_data["loans"] = {}
    gacha_data["loan_counts"] = {}
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
