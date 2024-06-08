import requests
import os
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import json
from supabase import create_client, Client

# Load environment variables from .env file
load_dotenv()

# Supabase credentials
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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
    daily_games_task.start()  # Start the daily games task
    daily_check_winners_task.start()  # Start the daily winner check task

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


@bot.command(name='daily_games')
async def daily_games(ctx):
    api_key = os.getenv('ODDS_API_KEY')
    if not api_key:
        print("API key not found. Please set ODDS_API_KEY in the .env file.")
        return

    odds_data = get_baseball_odds(api_key)
    if not odds_data:
        print("No games data found.")
        return

    today = datetime.now(timezone.utc).date()
    games_today = [game for game in odds_data if convert_to_est(
        game['commence_time']).date() == today]

    if not games_today:
        print("No games today.")
        return

    embed = discord.Embed(
        title="Today's MLB Games",
        color=discord.Color.blue()
    )

    for game in games_today:
        game_id = game['id']
        team1 = game['away_team']
        team2 = game['home_team']
        commence_time_est = convert_to_est(game['commence_time'])
        formatted_commence_time = commence_time_est.strftime(
            '%Y-%m-%d %I:%M %p')  # Format to 12-hour time with AM/PM

        existing_game = supabase.table('games').select(
            '*').eq('game_id', game_id).execute()
        if not existing_game.data:
            supabase.table('games').insert({
                'game_id': game_id,
                'team1': team1,
                'team2': team2,
                # Store as EST in ISO format
                'commence_time': commence_time_est.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'result': None  # Result will be updated later
            }).execute()

        embed.add_field(
            name=f"{team1} vs {team2}",
            value=f"Commence Time: {formatted_commence_time}",
            inline=False
        )

    channel = bot.get_channel(int(os.getenv('STREAK_CHANNEL_ID')))
    if channel:
        await channel.send(embed=embed)
    else:
        print("Channel not found")


@tasks.loop(hours=24)
async def daily_games_task():
    print("daily_games_task started")
    await bot.wait_until_ready()
    now = datetime.now(timezone.utc)
    est_now = now.astimezone(timezone(timedelta(hours=-4)))
    print(f"Current EST time: {est_now.strftime('%Y-%m-%d %I:%M %p EST')}")
    if est_now.hour == 6 and est_now.minute == 0:
        print("It's 06:00 AM EST, fetching today's games...")
        await daily_games()  # Call the daily_games function


@daily_games_task.before_loop
async def before_daily_games_task():
    await bot.wait_until_ready()
    now = datetime.now(timezone.utc)
    est_now = now.astimezone(timezone(timedelta(hours=-4)))
    target_time = est_now.replace(hour=6, minute=0, second=0, microsecond=0)
    if est_now >= target_time:
        target_time += timedelta(days=1)
    await discord.utils.sleep_until(target_time)


def is_streak_channel():
    async def predicate(ctx):
        return ctx.channel.id == int(os.getenv('STREAK_CHANNEL_ID'))
    return commands.check(predicate)


# Group command for streak-related commands
@bot.group()
async def streak(ctx):
    if ctx.invoked_subcommand is None:
        await ctx.send('Invalid streak command. Use `mlb streak help` for more information.')


@streak.command(name='help')
@is_streak_channel()
async def streak_help(ctx):
    help_text = [
        "**Streak Game Commands:**",
        "1. **mlb streak register** - Register for the streak game.",
        "2. **mlb streak pick <team_name>** - Make a pick for today's game. Example: `mlb streak pick Yankees`",
        "3. **mlb streak reset** - Reset your current pick (only before the game starts).",
        "4. **mlb streak profile [user]** - View your profile or mention a user to view their profile.",
        "5. **mlb streak current** - View your current streak and pick status.",
        "6. **mlb streak leaderboard** - View the top streaks on the leaderboard.",
        "7. **mlb streak help** - Display this help message."
    ]
    embed = discord.Embed(
        title="Streak Game Help",
        description="\n".join(help_text),
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)


@streak.command(name='register')
@is_streak_channel()
async def register(ctx):
    user_id = ctx.author.id
    username = str(ctx.author)

    # Check if the user is already registered
    existing_user = supabase.table('users').select(
        '*').eq('user_id', user_id).execute()
    if existing_user.data:
        await ctx.send(f"{username.title()}, you are already registered.")
        return

    # Register the user
    supabase.table('users').insert({
        'user_id': user_id,
        'username': username,
        'streak': 0,
        'current_pick': None,
        'current_game_id': None
    }).execute()

    await ctx.send(f"{username.title()}, you have been registered for the streak game!")


@streak.command(name='pick')
@is_streak_channel()
async def pick(ctx, *, team_name: str):
    user_id = ctx.author.id
    username = str(ctx.author)

    # Check if the user is registered
    existing_user = supabase.table('users').select(
        '*').eq('user_id', user_id).execute()
    if not existing_user.data:
        await ctx.send(f"{username.title()}, you are not registered. Please register first using `mlb streak register`.")
        return

    # Fetch today's games
    api_key = os.getenv('ODDS_API_KEY')
    if not api_key:
        await ctx.send("API key not found. Please set ODDS_API_KEY in the .env file.")
        return

    odds_data = get_baseball_odds(api_key)
    today = datetime.now(timezone.utc).date()
    games_today = [game for game in odds_data if convert_to_est(
        game['commence_time']).date() == today]

    if not games_today:
        await ctx.send("No games today.")
        return

    # Normalize the team name input for comparison
    normalized_team_name = team_name.strip().lower()

    # Find the game with the specified team
    selected_game = None
    for game in games_today:
        away_team = game['away_team'].strip().lower()
        home_team = game['home_team'].strip().lower()

        if normalized_team_name in away_team or normalized_team_name in home_team:
            # Check if the game has already started
            game_time = convert_to_est(game['commence_time'])
            if datetime.now(timezone(timedelta(hours=-4))) < game_time:
                selected_game = game
                break

    if not selected_game:
        await ctx.send(f"{username.title()}, no game found for the team '{team_name}' today or the game has already started. Please check the team name and try again.")
        return

    # Determine the full team name for the user's pick
    user_pick = selected_game['away_team'] if normalized_team_name in selected_game['away_team'].strip(
    ).lower() else selected_game['home_team']

    # Update the user's current pick and current game ID
    game_id = selected_game['id']
    supabase.table('users').update({
        'current_pick': user_pick,
        'current_game_id': game_id
    }).eq('user_id', user_id).execute()

    await ctx.send(f"{username.title()}, you have selected the {user_pick} for today, good luck!")


@streak.command(name='reset')
@is_streak_channel()
async def reset_pick(ctx):
    user_id = ctx.author.id
    username = str(ctx.author)

    # Check if the user is registered
    existing_user = supabase.table('users').select(
        '*').eq('user_id', user_id).execute()
    if not existing_user.data:
        await ctx.send(f"{username.title()}, you are not registered. Please register first using `mlb streak register`.")
        return

    # Fetch the user's current pick and game ID
    user_data = existing_user.data[0]
    current_game_id = user_data.get('current_game_id')
    current_pick = user_data.get('current_pick')

    if not current_game_id or not current_pick:
        await ctx.send(f"{username.title()}, you do not have an active pick to reset.")
        return

    # Fetch today's games to check if the game has started
    api_key = os.getenv('ODDS_API_KEY')
    if not api_key:
        await ctx.send("API key not found. Please set ODDS_API_KEY in the .env file.")
        return

    odds_data = get_baseball_odds(api_key)
    today = datetime.now(timezone.utc).date()
    games_today = {game['id']: game for game in odds_data if convert_to_est(
        game['commence_time']).date() == today}

    selected_game = games_today.get(current_game_id)
    if not selected_game:
        await ctx.send(f"{username.title()}, no game found for your current pick today.")
        return

    # Check if the game has already started
    game_time = convert_to_est(selected_game['commence_time'])
    if datetime.now(timezone(timedelta(hours=-4))) >= game_time:
        await ctx.send(f"{username.title()}, the game you picked has already started. You cannot reset your pick now.")
        return

    # Reset the user's current pick and game ID
    supabase.table('users').update({
        'current_pick': None,
        'current_game_id': None
    }).eq('user_id', user_id).execute()

    await ctx.send(f"{username.title()}, your pick has been reset. You can now make a new pick for today's games.")


@streak.command(name='profile')
@is_streak_channel()
async def view(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author

    user_id = member.id
    username = str(member)

    # Check if the user is registered
    existing_user = supabase.table('users').select(
        '*').eq('user_id', user_id).execute()
    if not existing_user.data:
        await ctx.send(f"{username.title()}, this user is not registered.")
        return

    user_data = existing_user.data[0]
    current_pick = user_data.get('current_pick')
    current_game_id = user_data.get('current_game_id')
    streak = user_data.get('streak', 0)

    if not current_pick or not current_game_id:
        await ctx.send(f"{username.title()}, does not have an active pick. Their current streak is {streak}.")
        return

    # Fetch today's games to display the game details
    api_key = os.getenv('ODDS_API_KEY')
    if not api_key:
        await ctx.send("API key not found. Please set ODDS_API_KEY in the .env file.")
        return

    odds_data = get_baseball_odds(api_key)
    today = datetime.now(timezone.utc).date()
    games_today = {game['id']: game for game in odds_data if convert_to_est(
        game['commence_time']).date() == today}

    selected_game = games_today.get(current_game_id)
    if not selected_game:
        await ctx.send(f"{username.title()}, no game found for their current pick today. Their current streak is {streak}.")
        return

    team1 = selected_game['away_team']
    team2 = selected_game['home_team']
    commence_time = convert_to_est(
        selected_game['commence_time']).strftime('%Y-%m-%d %I:%M %p EST')

    embed = discord.Embed(
        title=f"{username.title()}'s Current Pick",
        description=f"Current Streak: {streak}",
        color=discord.Color.blue()
    )

    embed.add_field(name="Game", value=f"{team1} vs {team2}", inline=False)
    embed.add_field(name="Commence Time", value=commence_time, inline=False)
    embed.add_field(name="Their Pick", value=current_pick, inline=False)

    await ctx.send(embed=embed)


@streak.command(name='leaderboard')
@is_streak_channel()
async def leaderboard(ctx):
    # Fetch all users and sort by streak
    users_data = supabase.table('users').select('*').execute()
    if not users_data.data:
        await ctx.send("No users found.")
        return

    sorted_users = sorted(
        users_data.data, key=lambda x: x.get('streak', 0), reverse=True)

    # Create an embed message for the leaderboard
    embed = discord.Embed(
        title="MLB Streak Leaderboard",
        color=discord.Color.gold()
    )

    # Show top 10 users
    for idx, user in enumerate(sorted_users[:10], start=1):
        user_name = user.get('username', 'Unknown User')
        streak = user.get('streak', 0)
        embed.add_field(name=f"{idx}. {user_name.title()}",
                        value=f"Streak: {streak}", inline=False)

    await ctx.send(embed=embed)


@streak.command(name='check_winners')
async def check_winners(ctx):
    await check_and_update_winners(ctx.channel)


async def check_and_update_winners(channel):
    api_key = os.getenv('ODDS_API_KEY')
    if not api_key:
        print("API key not found. Please set ODDS_API_KEY in the .env file.")
        return

    scores_data = get_baseball_scores(api_key)
    if not scores_data:
        print("No scores data found.")
        return

    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    completed_games = {game['id']: game for game in scores_data if game['completed']
                       and convert_to_est(game['commence_time']).date() == yesterday}

    users_data = supabase.table('users').select('*').execute()
    for user in users_data.data:
        current_pick = user['current_pick']
        if current_pick:
            pick_game = supabase.table('games').select(
                '*').eq('game_id', current_pick).execute()
            if pick_game.data:
                pick_game = pick_game.data[0]
                game_id = pick_game['game_id']
                if game_id in completed_games:
                    scores = completed_games[game_id]['scores']
                    team1_name, team2_name = scores[0]['name'], scores[1]['name']
                    team1_score, team2_score = scores[0]['score'], scores[1]['score']
                    winner = team1_name if team1_score > team2_score else team2_name
                    if user['current_pick'] == winner:
                        new_streak = user['current_streak'] + 1
                    else:
                        new_streak = 0

                    supabase.table('users').update({
                        'current_streak': new_streak,
                        'current_pick': None  # Reset the pick after processing
                    }).eq('user_id', user['user_id']).execute()

                    # Send a message to the channel with the update
                    print(f"User {user['user_id']} picked {user['current_pick']} for game {
                          game_id}. Result: {winner} won. New streak: {new_streak}.")


@tasks.loop(hours=24)
async def daily_check_winners_task():
    await bot.wait_until_ready()
    now = datetime.now(timezone.utc)
    est_now = now.astimezone(timezone(timedelta(hours=-4)))
    print(f"Current EST time: {est_now.strftime('%Y-%m-%d %I:%M %p EST')}")
    if est_now.hour == 6 and est_now.minute == 0:
        print("It's 06:00 AM EST, checking and updating winners...")
        channel = bot.get_channel(int(os.getenv('STREAK_CHANNEL_ID')))
        if channel:
            await check_and_update_winners(channel)
        else:
            print("Channel not found")


@daily_check_winners_task.before_loop
async def before_daily_check_winners_task():
    await bot.wait_until_ready()
    now = datetime.now(timezone.utc)
    est_now = now.astimezone(timezone(timedelta(hours=-4)))
    target_time = est_now.replace(hour=6, minute=0, second=0, microsecond=0)
    if est_now >= target_time:
        target_time += timedelta(days=1)
    await discord.utils.sleep_until(target_time)


# Run the bot with the token from the developer portal
bot.run(os.getenv('BOT_TOKEN'))
