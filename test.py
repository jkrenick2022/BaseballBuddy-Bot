import requests
import os
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone, date
import pytz
import difflib
from supabase import create_client, Client
import statsapi
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
import io

load_dotenv()

api_key = os.getenv("ODDS_API_KEY")
# Supabase credentials
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize the bot with commands and intents
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True  # Ensure the bot can read message content

prefixes = ['mlb ', 'MLB ']
bot = commands.Bot(command_prefix=['mlb ', 'MLB '],
                   intents=intents, help_command=None)

# Initializes the bot when it is logged on


@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')
    activity = discord.Game(name="MLB Help")
    await bot.change_presence(status=discord.Status.online, activity=activity)


def convert_to_12hr_format(timestamp: str) -> str:
    # Parse the datetime string into a naive datetime object
    dt = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S')

    # Format the datetime object to a string in 12-hour format with AM/PM
    return dt.strftime('%Y-%m-%d %I:%M:%S %p')


def get_player_data(player):
    # get row from supabase for player
    player_data = supabase.table('players').select(
        '*').eq('player_name', player.title()).execute()

    # Access the data attribute directly
    if player_data.data:
        # Access the data returned by Supabase
        player_url = (player_data.data[0]['player_link'])
        player_team = (player_data.data[0]['team']
                       [:-7].replace('-', ' ').title())
    else:
        print(f"No data found for player: {player}")
        return None, None

    game_log_url = player_url + 'game-log/'

    return player_team, game_log_url


def get_players_game_id(player_team):
    today = datetime.now().date()  # Ensure today's date is correct
    games_data = supabase.table('games').select('*').execute()

    if not games_data.data:
        print("No games data found.")
        return None

    todays_games = [game for game in games_data.data if datetime.strptime(
        game['commence_time'], '%Y-%m-%dT%H:%M:%S').date() == today]

    game_ids = [game['game_id'] for game in todays_games if player_team in [
        game['team1'], game['team2']]]

    if not game_ids:
        print(f"No game found for {player_team} today.")
        return None

    return game_ids


def get_player_prop_odds(player, prop, game_id, api_key):
    base_url = f"https://api.the-odds-api.com/v4/sports/baseball_mlb/events/{
        game_id}/odds/"

    # Dictionary to map user-friendly prop names to API market keys
    market_identifiers = {
        'homeruns': 'batter_home_runs',
        'hits': 'batter_hits',
        'rbis': 'batter_rbis',
        'runs': 'batter_runs_scored',
        'doubles': 'batter_doubles',
        'triples': 'batter_triples',
        'walks': 'batter_walks',
        'strikeouts': 'batter_strikeouts',
        'pitcher_strikeouts': 'pitcher_strikeouts',
        'pitcher_hits_allowed': 'pitcher_hits_allowed',
        'pitcher_walks': 'pitcher_walks',
        'pitcher_earned_runs': 'pitcher_earned_runs'
    }

    market = market_identifiers.get(prop.lower())
    if not market:
        print(f"Market identifier for '{prop}' not found.")
        return None

    params = {
        'dateFormat': 'iso',
        'oddsFormat': 'american',
        'apiKey': api_key,
        'regions': 'us,us2',
        'bookmakers': 'fanduel',
        'markets': market
    }

    response = requests.get(base_url, params=params)
    if response.status_code == 404:
        error_message = response.json().get("message", "")
        if error_message == "Event not found. The event may have expired or the event id is invalid.":
            print(f"Failed to get odds: Event not found for game ID {
                  game_id}. The event may have expired or the event ID is invalid.")
        else:
            print(f"Failed to get odds: {
                  response.status_code}, {response.text}")
        return None
    elif response.status_code != 200:
        print(f"Failed to get odds: {response.status_code}, {response.text}")
        return None

    odds_data = response.json()

    player_odds = []
    for bookmaker in odds_data.get('bookmakers', []):
        for market_data in bookmaker.get('markets', []):
            if market_data['key'] == market:
                for outcome in market_data.get('outcomes', []):
                    if player.lower() in outcome['description'].lower():
                        player_odds.append({
                            'bookmaker': bookmaker['title'],
                            'market': market_data['key'],
                            'description': outcome['description'],
                            'price': outcome['price'],
                            'point': outcome['point']
                        })

    if not player_odds:
        print(f"No odds found for player '{player}' in market '{prop}'.")

    return player_odds


def get_player_game_log(url, prop):
    # Send a GET request to the URL
    response = requests.get(url)

    # Check if the request was successful
    if response.status_code != 200:
        print(f"Failed to retrieve page: {response.status_code}")
        return None, None

    # Parse the HTML content using BeautifulSoup
    soup = BeautifulSoup(response.content, 'html.parser')

    # Find the table headers
    try:
        thead = soup.find('div', class_='Page-colMain').find('div', class_='TableBase').find(
            'table', class_='TableBase-table').find('thead').find_all('th')
    except AttributeError as e:
        print(f"Failed to parse table headers: {e}")
        return None, None

    headers = [th.get_text(strip=True) for th in thead]
    print(f"Table Headers: {headers}")

    # Dictionary to map props to table headers for both batters and pitchers
    prop_identifiers = {
        'hits': 'hhits',
        'runs': 'rruns',
        'rbi': 'rbirunsbattedin',
        'homeruns': 'hrhomeruns',
        'strikeouts': 'sostrikeouts',
        'walks': 'bbbaseonballs(walk)',
        'doubles': '2bdoubles',
        'triples': '3btriples',
        'pitcher_hits_allowed': 'hhits',
        'pitcher_earned_runs': 'erearnedruns',
        'pitcher_walks': 'bbbaseonballs(walk)',
        'pitcher_strikeouts': 'sostrikeouts'
    }

    # Normalize prop to match the table headers
    header_name = prop_identifiers.get(prop.lower())
    if not header_name:
        print(f"Property '{prop}' not found in the prop identifiers.")
        return None, None

    print(f"Header Name for '{prop}': {header_name}")

    # Normalize headers for comparison
    normalized_headers = [header.lower().replace(' ', '')
                          for header in headers]

    print(f"Normalized Headers: {normalized_headers}")

    # Determine the index of the column that matches the header name
    prop_index = None
    for index, header in enumerate(normalized_headers):
        normalized_header_name = header_name.lower().replace(' ', '')
        if header == normalized_header_name:
            prop_index = index
            break

    if prop_index is None:
        print(f"Header '{header_name}' not found in the table headers.")
        return None, None

    # Extract data from the first 5 rows
    try:
        data_rows = soup.find('div', class_='Page-colMain').find('div', class_='TableBase').find(
            'table', class_='TableBase-table').find('tbody').find_all('tr')[:5]
    except AttributeError as e:
        print(f"Failed to parse table rows: {e}")
        return None, None

    dates = []
    prop_data = []
    for row in data_rows:
        cells = row.find_all('td')
        if len(cells) > prop_index:
            # Assuming the date is in the first column
            dates.append(cells[0].get_text(strip=True))
            prop_data.append(cells[prop_index].get_text(strip=True))

    return dates, prop_data

# Function to plot game log data


def plot_game_log_data(player_name, prop, dates, game_log_data):
    values = [float(data) for data in game_log_data]

    plt.figure(figsize=(12, 6))  # Increase the size of the plot
    plt.bar(dates, values, color='b')

    plt.title(f'{player_name} - {prop.title()
                                 } Over Last {len(game_log_data)} Games', fontsize=16)
    plt.xlabel('Date', fontsize=14)
    plt.ylabel(prop.title(), fontsize=14)
    plt.xticks(rotation=45, fontsize=12)
    plt.yticks(fontsize=12)
    plt.grid(False)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf


# # Example usage
# player_name = 'Nolan Schanuel'
# prop = 'hits'


# player_team, game_log_url = get_player_data(player_name)
# if player_team:
#     game_ids = get_todays_game_id(player_team)
#     if game_ids:
#         for id in game_ids:
#             prop_odds = get_player_prop_odds(
#                 player_name, prop, id, api_key)

#             if prop_odds:
#                 print(f"Odds for player '{player_name}' in game {id}:")
#                 for odds in prop_odds:
#                     print(f"{odds['bookmaker']}: {
#                           odds['price']} ({odds['point']})")

#         # Fetch game log data for the specified prop
#         dates, game_log_data = get_player_game_log(game_log_url, prop)
#         if game_log_data:
#             print(f"Game log data for '{player_name}': {game_log_data}")
#             # Plot the game log data
#             plot_game_log_data(player_name, prop, dates, game_log_data)
#         else:
#             print(f"No game log data found for '{player_name}'.")
#     else:
#         print(f"No game found for {player_team} today.")

# Group command for streak-related commands


@bot.group()
async def prop(ctx):
    if ctx.invoked_subcommand is None:
        await ctx.send('Invalid prop command. Use `mlb prop help` for more information.')


@prop.command(name='finder')
async def prop_finder(ctx, *, player_name_prop):
    api_key = os.getenv('ODDS_API_KEY')
    try:
        input_ = player_name_prop.split()
        player_name = ' '.join(input_[:-1])
        prop = input_[-1]
    except ValueError:
        await ctx.send("Please provide the player's name followed by the prop.")
        return

    print(f"Player Name: {player_name}, Prop: {prop}")

    player_team, game_log_url = get_player_data(player_name)

    print(f"Player Team: {player_team}, Game Log URL: {game_log_url}")

    if not player_team:
        await ctx.send(f"No data found for player: {player_name}")
        return

    game_ids = get_players_game_id(player_team)

    print(f"Game IDs: {game_ids}")

    if not game_ids:
        await ctx.send(f"No game found for {player_team} today.")
        return

    odds_message = f"Odds for {player_name.title()} {prop.title()}:\n"
    odds_found = False  # Flag to check if any odds are found

    for game_id in game_ids:
        prop_odds = get_player_prop_odds(player_name, prop, game_id, api_key)

        if prop_odds:
            odds_found = True
            for odds in prop_odds:
                sign = '+' if odds['price'] > 0 else ''
                odds_message += f"Over {odds['point']
                                        } - [{sign}{odds['price']}]\n"

    if not odds_found:
        odds_message += f"No odds found for player '{
            player_name}' in market '{prop}'."

    await ctx.send(odds_message)

    # Fetch game log data for the specified prop
    dates, game_log_data = get_player_game_log(game_log_url, prop)
    if game_log_data:
        plot_buf = plot_game_log_data(player_name, prop, dates, game_log_data)

        file = discord.File(fp=plot_buf, filename="plot.png")
        embed = discord.Embed(
            title=f"{player_name} - {prop.title()} Over Last {len(game_log_data)} Games")
        embed.set_image(url="attachment://plot.png")

        await ctx.send(file=file, embed=embed)
    else:
        await ctx.send(f"No game log data found for '{player_name}'.")

# Run the bot with the token from the developer portal
bot.run(os.getenv('BOT_TOKEN'))
