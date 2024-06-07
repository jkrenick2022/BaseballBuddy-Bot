import requests
import os
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone

# Load environment variables from .env file
load_dotenv()

# Initialize the bot with commands and intents
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True  # Ensure the bot can read message content

bot = commands.Bot(command_prefix='!', intents=intents)

# Gets the baseball odds from the API
def get_baseball_odds(api_key):
    base_url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/"
    
    params = {
        'dateFormat': 'iso',
        'oddsFormat': 'american',
        'regions': 'us,us2',
        'markets': 'h2h,spreads,totals',
        'apiKey': api_key,
        'bookmakers': 'fanduel'
    }
    response = requests.get(base_url, params=params)
    if response.status_code != 200:
        print(f"Failed to get odds: {response.status_code}, {response.text}")
        return []
    return response.json()

# Converts UTC time to EST time
def convert_to_est(utc_time):
    utc_dt = datetime.strptime(utc_time, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    est_dt = utc_dt.astimezone(timezone(timedelta(hours=-4)))
    return est_dt

# Initializes the bot when it is logged on
@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')
    fetch_and_send_odds.start()  # Start the daily task loop

# Command to fetch and display MLB odds
@bot.command(name='odds')
async def fetch_odds(ctx):
    api_key = os.getenv('ODDS_API_KEY')
    if not api_key:
        await ctx.send("API key not found. Please set ODDS_API_KEY in the .env file.")
        return

    await ctx.send("Fetching odds...")
    odds_data = get_baseball_odds(api_key)

    if not odds_data:
        await ctx.send("No odds data found.")
        return

    today = datetime.now(timezone.utc).date()
    games_today = [game for game in odds_data if convert_to_est(game['commence_time']).date() == today]

    if not games_today:
        await ctx.send("No games today.")
        return

    for game in games_today:
        embed = discord.Embed(
            title=f"{game['away_team']} vs {game['home_team']}",
            description=f"Commence Time: {convert_to_est(game['commence_time']).strftime('%Y-%m-%d %I:%M %p EST')}",
            color=discord.Color.blue()
        )

        for bookmaker in game['bookmakers']:
            if bookmaker['key'] == 'fanduel':
                for market in bookmaker['markets']:
                    market_key = market['key']
                    market_name = 'Head to Head' if market_key == 'h2h' else 'Totals' if market_key == 'totals' else 'Spreads'
                    
                    if market_key == 'spreads':
                        outcomes = "\n".join([
                            f"{outcome['name']}: {'+' if outcome['price'] > 0 else ''}{outcome['price']} (Spread: {'+' if outcome['point'] > 0 else ''}{outcome['point']})"
                            for outcome in market['outcomes']
                        ])
                    elif market_key == 'totals':
                        outcomes = "\n".join([
                            f"{outcome['name']}: {'+' if outcome['price'] > 0 else ''}{outcome['price']} ({outcome['point']})"
                            for outcome in market['outcomes']
                        ])
                    else:
                        outcomes = "\n".join([
                            f"{outcome['name']}: {'+' if outcome['price'] > 0 else ''}{outcome['price']}"
                            for outcome in market['outcomes']
                        ])
                    
                    embed.add_field(name=f"{bookmaker['title']} - {market_name}", value=outcomes, inline=False)

        await ctx.send(embed=embed)

# Task loop to fetch and send MLB odds daily
@tasks.loop(hours=24)
async def fetch_and_send_odds():
    channel_id = int(os.getenv('DISCORD_CHANNEL_ID'))  # Ensure you have set this in your .env file
    channel = bot.get_channel(channel_id)
    if not channel:
        print(f"Channel with ID {channel_id} not found.")
        return

    api_key = os.getenv('ODDS_API_KEY')
    if not api_key:
        await channel.send("API key not found. Please set ODDS_API_KEY in the .env file.")
        return

    odds_data = get_baseball_odds(api_key)

    if not odds_data:
        await channel.send("No odds data found.")
        return

    today = datetime.now(timezone.utc).date()
    games_today = [game for game in odds_data if convert_to_est(game['commence_time']).date() == today]

    if not games_today:
        await channel.send("No games today.")
        return

    for game in games_today:
        embed = discord.Embed(
            title=f"{game['away_team']} vs {game['home_team']}",
            description=f"Commence Time: {convert_to_est(game['commence_time']).strftime('%Y-%m-%d %I:%M %p EST')}",
            color=discord.Color.blue()
        )

        for bookmaker in game['bookmakers']:
            if bookmaker['key'] == 'fanduel':
                for market in bookmaker['markets']:
                    market_key = market['key']
                    market_name = 'Head to Head' if market_key == 'h2h' else 'Totals' if market_key == 'totals' else 'Spreads'
                    
                    if market_key == 'spreads':
                        outcomes = "\n".join([
                            f"{outcome['name']}: {'+' if outcome['price'] > 0 else ''}{outcome['price']} (Spread: {'+' if outcome['point'] > 0 else ''}{outcome['point']})"
                            for outcome in market['outcomes']
                        ])
                    elif market_key == 'totals':
                        outcomes = "\n".join([
                            f"{outcome['name']}: {'+' if outcome['price'] > 0 else ''}{outcome['price']} ({outcome['point']})"
                            for outcome in market['outcomes']
                        ])
                    else:
                        outcomes = "\n".join([
                            f"{outcome['name']}: {'+' if outcome['price'] > 0 else ''}{outcome['price']}"
                            for outcome in market['outcomes']
                        ])
                    
                    embed.add_field(name=f"{bookmaker['title']} - {market_name}", value=outcomes, inline=False)

        await channel.send(embed=embed)

# Start the task loop
@fetch_and_send_odds.before_loop
async def before_fetch_and_send_odds():
    await bot.wait_until_ready()
    now = datetime.now()
    target_time = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now > target_time:
        target_time += timedelta(days=1)
    await discord.utils.sleep_until(target_time)

# Run the bot with the token from the developer portal
bot.run(os.getenv('BOT_TOKEN'))
