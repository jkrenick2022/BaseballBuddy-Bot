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

load_dotenv()

api_key = os.getenv("ODDS_API_KEY")
# Supabase credentials
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def convert_to_est(timestamp: str) -> datetime:

    # Remove the 'Z' character and parse the datetime string into a naive datetime object
    dt = datetime.strptime(timestamp.rstrip('Z'), '%Y-%m-%dT%H:%M:%S')

    # Convert the naive datetime object from UTC to Eastern Time
    utc = pytz.timezone('UTC')
    dt_utc = utc.localize(dt)
    eastern = pytz.timezone('US/Eastern')
    dt_eastern = dt_utc.astimezone(eastern)

    return dt_eastern


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


odds_data = get_baseball_odds(api_key)


today = datetime.now().date()
games_today = [game for game in odds_data if convert_to_est(
    game['commence_time']).date() == today]

for game in games_today:
    game_id = game['id']
    team1 = game['away_team']
    team2 = game['home_team']
    commence_time_est = convert_to_est(game['commence_time'])
    formatted_commence_time = commence_time_est.strftime(
        '%m-%d-%y %I:%M %p')  # Format to 12-hour time with AM/PM

    print(f"{team1} at {team2} at {formatted_commence_time}")


def get_player_props(player, prop):
    # get row from supabase for player
    player_data = supabase.table('players').select(
        '*').eq('player_name', player).execute()

    # Access the data attribute directly
    if player_data.data:
        # Access the data returned by Supabase
        player_url = (player_data.data[0]['player_link'])
    else:
        print(f"No data found for player: {player}")
        return None

    game_log_url = player_url + 'game-log/'

    # Send a GET request to the URL
    response = requests.get(game_log_url)

    # Check if the request was successful
    if response.status_code != 200:
        print(f"Failed to retrieve page: {response.status_code}")
        return None

    # Parse the HTML content using BeautifulSoup
    soup = BeautifulSoup(response.content, 'html.parser')

    # Find the table headers
    thead = soup.find('div', class_='Page-colMain').find('div', class_='TableBase').find(
        'table', class_='TableBase-table').find('thead').find_all('th')

    # Debug: Print all headers for inspection
    print("Table headers:")
    headers = [th.get_text(strip=True) for th in thead]
    for index, header in enumerate(headers):
        print(f"{index}: '{header}'")

    # Dictionary to map props to table headers
    prop_identifiers = {
        'hits': 'hhits',
        'runs': 'rruns',
        'rbi': 'rbirunsbattedin',
        'homeruns': 'hrhomeruns',
        'strikeouts': 'sostrikeouts',
        'walks': 'bbbaseonballs(walk)',
        'doubles': '2bdoubles',
        'triples': '3btriples'
    }

    # Normalize prop to match the table headers
    header_name = prop_identifiers.get(prop.lower())
    if not header_name:
        print(f"Property '{prop}' not found in the prop identifiers.")
        return None

    # Normalize headers for comparison
    normalized_headers = [header.lower().replace(' ', '')
                          for header in headers]

    # Determine the index of the column that matches the header name
    prop_index = None
    for index, header in enumerate(normalized_headers):
        normalized_header_name = header_name.lower().replace(' ', '')
        if header == normalized_header_name:
            prop_index = index
            break

    if prop_index is None:
        print(f"Header '{header_name}' not found in the table headers.")
        return None

    # Extract data from the first 5 rows
    data_rows = soup.find('div', class_='Page-colMain').find('div', class_='TableBase').find(
        'table', class_='TableBase-table').find('tbody').find_all('tr')[:5]

    prop_data = []
    for row in data_rows:
        cells = row.find_all('td')
        if len(cells) > prop_index:
            prop_data.append(cells[prop_index].get_text(strip=True))

    return prop_data


print(get_player_props('Bryce Harper', 'Homeruns'))
