# Requirements

- python 13 - <https://www.python.org/downloads/>
- uv package manager - <https://docs.astral.sh/uv/getting-started/installation/>
- spotify account and developer app - <https://developer.spotify.com/dashboard>

## How to use

1. Clone the repository
2. Create .env file in root of project based on default.env.
  - Set **SPOTIFY_CLIENT_ID** and **SPOTIFY_CLIENT_SECRET**. Optionally **MAX_WORKERS** by default is 5, but you can change how many threads will be used to download songs.
3. Run in terminal `uv sync`
4. Run script `uv run downloader.py`
5. It will ask you for spotify playlist url

### How it works

- When you pass your spotify playlist url it searches for these songs on youtube and downloads+converts them to mp3

#### Why would I use it if already have spotify premium with offline downloads?

- idk
