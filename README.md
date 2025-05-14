# Requirements

- UV package manager - <https://docs.astral.sh/uv/getting-started/installation/>
- Spotify account and developer app - <https://developer.spotify.com/dashboard>

## How to use

1. Clone the repository

2. Create .env file in root of project based on default.env.
    - Set **SPOTIFY_CLIENT_ID** and **SPOTIFY_CLIENT_SECRET**.
    - Set **SPOTIFY_PLAYLIST** like in default.env
    - Optionally **MAX_WORKERS** by default is 5, but you can change how many threads will be used to download songs.

3. Run in terminal `uv sync`

4. Run script `uv run python downloader.py`

5. It will ask you for spotify playlist url

### How it works

- When you pass list of your playlists in .env it will download all songs and puts them in separate folders based on playlist name.
- Only works on your own playlists

#### Why would I use it if already have spotify premium with offline downloads?

1. no access to phone
2. idk
