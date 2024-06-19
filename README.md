# BaseballBuddy Discord Bot

## Overview

The Sports Betting Odds API Bot is a Discord bot that provides up-to-date MLB betting odds, player prop odds, and game results. It includes features such as a streak game where users can pick teams and track their streaks. This bot integrates with the OddsAPI and uses Supabase for data storage.

## Features

- **Fetch Betting Odds**: Provides betting odds for MLB games.
- **Player Prop Finder**: Fetches and displays player prop odds.
- **Player Stats**: Fetches and displays season or career stats for players. 
- **Game Results**: Displays results of completed MLB games.
- **Streak Game**: Allows users to pick teams and track their streaks.

## Commands

### Admin Commands 
*These should only be used if their task loop malfunctions!*
- `mlb odds`: Fetches and displays today's MLB betting odds.
- `mlb results`: Fetches and displays the outcomes from the previous days games.
- `mlb daily_games`: Fetches and shows a list of the games for the day.
- 'mlb prop finder <player_name> <prop>`: Fetches and displays player prop odds for the specified player and prop.
- 'mlb check_winners': Checks the winners for the previous day and updates the database for the streak game.

### Streak Game Commands
- `mlb streak help`: Provides a guide for the user to use all of the commands.
- `!streak register`: Registers a user for the streak game.
- `mlb streak pick <team_name>`: Allows a user to pick a team for today's game.
- `mlb streak reset`: Resets the user's current pick.
- 'mlb streak profile': Shows the users profile with insights on the users stats.
- 'mlb streak leaderboard': Shows the top 5 current highest active streaks.

### Stats / Prop Commands
- 'mlb seasonstats <player_name> <stat_category>': Fetches the players season stats for one of 3 categories.
- 'mlb careerstats <player_name> <stat_category>': Fetches the players career stats for one of 3 categories.
- 'mlb prop finder <player_name> <prop>': Fetches the current odds for the player prop as well as provides a data visualization of their last 5 games for the respected prop.
