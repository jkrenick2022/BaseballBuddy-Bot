import requests
import os
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import json

# Load environment variables from .env file
load_dotenv()

# Load team data from JSON file
with open('team_data.json', 'r') as f:
    team_data = json.load(f)

# Initialize the bot with commands and intents
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True  # Ensure the bot can read message content

bot = commands.Bot(command_prefix='mlb ', intents=intents)

# Initializes the bot when it is logged on


@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')
    activity = discord.Game(name="Baseball Helper")
    await bot.change_presence(status=discord.Status.online, activity=activity)
    daily_odds.start()  # Start the daily odds task
    daily_scores.start()  # Start the daily scores task

# Converts UTC time to EST time


def convert_to_est(utc_time):
    utc_dt = datetime.strptime(
        utc_time, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    est_dt = utc_dt.astimezone(timezone(timedelta(hours=-4)))
    return est_dt

# Gets the baseball odds from the API


def get_baseball_odds(api_key):
    base_url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/"

    params = {
        'dateFormat': 'iso',
        'oddsFormat': 'american',
        'regions': 'us,us2',
        'markets': 'h2h,spreads,totals',
        'apiKey': api_key,
        'bookmakers': 'fanduel,draftkings'
    }
    response = requests.get(base_url, params=params)
    if response.status_code != 200:
        print(f"Failed to get odds: {response.status_code}, {response.text}")
        return []
    return response.json()


# Task loop to fetch and display MLB odds daily


@tasks.loop(hours=24)
async def daily_odds():
    print("daily_odds task started")
    await bot.wait_until_ready()
    now = datetime.now(timezone.utc)
    est_now = now.astimezone(timezone(timedelta(hours=-4)))
    print(f"Current EST time: {est_now.strftime('%Y-%m-%d %I:%M %p EST')}")
    if est_now.hour == 9 and est_now.minute == 0:
        print("It's 09:00 AM EST, fetching odds...")
        channel = bot.get_channel(int(os.getenv('ODDS_CHANNEL_ID')))
        if channel:
            await send_odds(channel)
        else:
            print("Channel not found")


# Command to fetch and display MLB odds manually
@bot.command(name='odds')
async def fetch_odds(ctx):
    channel = bot.get_channel(int(os.getenv('ODDS_CHANNEL_ID')))
    if channel:
        await send_odds(channel)
    else:
        await ctx.send("Channel not found")


# Function to fetch and send odds


async def send_odds(ctx):
    api_key = os.getenv('ODDS_API_KEY')
    if not api_key:
        await ctx.send("API key not found. Please set ODDS_API_KEY in the .env file.")
        return

    odds_data = get_baseball_odds(api_key)

    if not odds_data:
        await ctx.send("No odds data found.")
        return

    today = datetime.now(timezone.utc).date()
    games_today = [game for game in odds_data if convert_to_est(
        game['commence_time']).date() == today]

    if not games_today:
        await ctx.send("No games today.")
        return

    for game in games_today:
        embed = discord.Embed(
            title=f"{game['away_team']} vs {game['home_team']}",
            description=f"Commence Time: {convert_to_est(
                game['commence_time']).strftime('%Y-%m-%d %I:%M %p EST')}",
            color=discord.Color.blue()
        )

        for bookmaker in game['bookmakers']:
            if bookmaker['key'] in ['fanduel', 'draftkings']:
                for market in bookmaker['markets']:
                    market_key = market['key']
                    market_name = 'Head to Head' if market_key == 'h2h' else 'Totals' if market_key == 'totals' else 'Spreads'

                    if market_key == 'spreads':
                        outcomes = "\n".join([
                            f"{outcome['name']}: {'+' if outcome['price'] > 0 else ''}{
                                outcome['price']} (Spread: {'+' if outcome['point'] > 0 else ''}{outcome['point']})"
                            for outcome in market['outcomes']
                        ])
                    elif market_key == 'totals':
                        outcomes = "\n".join([
                            f"{outcome['name']}: {
                                '+' if outcome['price'] > 0 else ''}{outcome['price']} ({outcome['point']})"
                            for outcome in market['outcomes']
                        ])
                    else:
                        outcomes = "\n".join([
                            f"{outcome['name']}: {
                                '+' if outcome['price'] > 0 else ''}{outcome['price']}"
                            for outcome in market['outcomes']
                        ])

                    embed.add_field(
                        name=f"{bookmaker['title']} - {market_name}", value=outcomes, inline=False)

        await ctx.send(embed=embed)

# Set the initial start time for the daily odds task


@daily_odds.before_loop
async def before_daily_odds():
    await bot.wait_until_ready()
    now = datetime.now(timezone.utc)
    est_now = now.astimezone(timezone(timedelta(hours=-4)))
    target_time = est_now.replace(hour=9, minute=0, second=0, microsecond=0)
    if est_now >= target_time:
        target_time += timedelta(days=1)
    await discord.utils.sleep_until(target_time)


# Gets the baseball scores from the API
def get_baseball_scores(api_key):
    base_url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/scores/"

    params = {
        'dateFormat': 'iso',
        'daysFrom': '1',
        'apiKey': api_key
    }
    response = requests.get(base_url, params=params)
    if response.status_code != 200:
        print(f"Failed to get scores: {response.status_code}, {response.text}")
        return []
    return response.json()

# Task loop to fetch and display MLB scores daily


@tasks.loop(hours=24)
async def daily_scores():
    print("daily_scores task started")
    await bot.wait_until_ready()
    now = datetime.now(timezone.utc)
    est_now = now.astimezone(timezone(timedelta(hours=-5)))  # Adjusted for EST
    print(f"Current EST time: {est_now.strftime('%Y-%m-%d %I:%M %p EST')}")
    if est_now.hour == 6 and est_now.minute == 0:
        print("It's 06:00 AM EST, fetching scores...")
        channel = bot.get_channel(int(os.getenv('SCORES_CHANNEL_ID')))
        if channel:
            await send_results(channel)
        else:
            print("Channel not found")

# Command to fetch and display MLB results manually


@bot.command(name='results')
async def fetch_results(ctx):
    channel = bot.get_channel(int(os.getenv('SCORES_CHANNEL_ID')))
    if channel:
        await send_results(channel)
    else:
        await ctx.send("Channel not found.")


# Function to fetch and send scores


async def send_results(channel):
    api_key = os.getenv('ODDS_API_KEY')
    if not api_key:
        await channel.send("API key not found. Please set ODDS_API_KEY in the .env file.")
        return

    scores_data = get_baseball_scores(api_key)

    if not scores_data:
        await channel.send("No scores data found.")
        return

    completed_games = {
        game['id']: {
            'commence_time': game['commence_time'],
            'completed': game['completed'],
            'scores': game['scores']
        }
        for game in scores_data if game['completed'] == True
    }

    results = {}

    for key, value in completed_games.items():
        scores = value['scores']
        team1_name, team2_name = scores[0]['name'], scores[1]['name']
        team1_score, team2_score = scores[0]['score'], scores[1]['score']

        winner = {
            'team_name': team1_name if int(team1_score) > int(team2_score) else team2_name,
            'score': team1_score if int(team1_score) > int(team2_score) else team2_score
        }
        loser = {
            'team_name': team1_name if int(team1_score) < int(team2_score) else team2_name,
            'score': team1_score if int(team1_score) < int(team2_score) else team2_score
        }

        results[key] = {
            'commence_time': value['commence_time'],
            'team1_name': team1_name,
            'team1_score': team1_score,
            'team2_name': team2_name,
            'team2_score': team2_score,
            'winner': winner,
            'loser': loser
        }

    # Send embedded messages with the scores
    for key, value in results.items():
        team1_name = value['team1_name']
        team2_name = value['team2_name']
        winner_name = value['winner']['team_name']
        loser_name = value['loser']['team_name']
        winning_team_info = team_data.get(winner_name, {})
        losing_team_info = team_data.get(loser_name, {})

        embed = discord.Embed(
            title=f"{team1_name} vs {team2_name}",
            description=f"Commence Time: {convert_to_est(
                value['commence_time']).strftime('%Y-%m-%d %I:%M %p EST')}",
            color=discord.Color.blue()
        )

        embed.add_field(name=team1_name, value=f"Score: {
                        value['team1_score']}", inline=True)
        embed.add_field(name=team2_name, value=f"Score: {
                        value['team2_score']}", inline=True)
        embed.add_field(name="Winner", value=f"{value['winner']['team_name']} ({
                        value['winner']['score']})", inline=False)
        embed.add_field(name="Loser", value=f"{value['loser']['team_name']} ({
                        value['loser']['score']})", inline=False)

        if 'logo' in winning_team_info:
            embed.set_thumbnail(url=winning_team_info['logo'])
        if 'color' in winning_team_info:
            embed.color = discord.Color(
                int(winning_team_info['color'][1:], 16))

        await channel.send(embed=embed)

# Set the initial start time for the daily scores task


@daily_scores.before_loop
async def before_daily_scores():
    await bot.wait_until_ready()
    now = datetime.now(timezone.utc)
    est_now = now.astimezone(timezone(timedelta(hours=-5)))  # Adjusted for EST
    target_time = est_now.replace(hour=6, minute=0, second=0, microsecond=0)
    if est_now >= target_time:
        target_time += timedelta(days=1)
    await discord.utils.sleep_until(target_time)


# Run the bot with the token from the developer portal
bot.run(os.getenv('BOT_TOKEN'))
