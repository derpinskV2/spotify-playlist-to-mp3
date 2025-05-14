import os
import re
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import subprocess
import concurrent.futures
import logging
import json
import environ
from pathlib import Path

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
file_handler = logging.FileHandler("spotify_downloader.log", mode="a")
file_handler.setLevel(logging.WARNING)
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - [%(threadName)s] - %(message)s")
console_handler.setFormatter(log_formatter)
file_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)
logger.addHandler(file_handler)

env = environ.Env()
BASE_DIR = Path(__file__).resolve().parent

environ.Env.read_env(os.path.join(BASE_DIR, ".env"))
SPOTIFY_CLIENT_ID = env("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = env("SPOTIFY_CLIENT_SECRET")
MAX_WORKERS = env.int("MAX_WORKERS")
PLAYLIST_URLS = env.list("PLAYLIST_URLS")


FAILED_DOWNLOADS_JSON_FILE: str = "failed_downloads.json"
BASE_DOWNLOAD_FOLDER = "Spotify_Playlists_Downloads"


if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
    logger.critical("SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables not set. Exiting.")
    exit(1)

os.makedirs(BASE_DOWNLOAD_FOLDER, exist_ok=True)


def sanitize_foldername(name):
    name = str(name)
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip(". ")
    name = re.sub(r"_+", "_", name)
    if not name:
        name = "Untitled_Playlist"
    return name


def get_playlist_details(playlist_url_or_id):
    try:
        auth_manager = SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET)
        sp = spotipy.Spotify(auth_manager=auth_manager)
        playlist_info = sp.playlist(playlist_url_or_id)
        if not playlist_info or "name" not in playlist_info:
            logger.error(f"Could not retrieve playlist info for: {playlist_url_or_id}")
            return None
        playlist_name = playlist_info["name"]

        items = []
        results = sp.playlist_items(playlist_url_or_id)
        if results:
            items.extend(results["items"])
            while results.get("next"):
                results = sp.next(results)
                if results:
                    items.extend(results["items"])
                else:
                    break
        else:
            logger.warning(f"No items found in playlist: {playlist_url_or_id}")

        track_list = []
        for item in items:
            track = item.get("track")
            if track and track.get("name") and track.get("artists"):
                track_name = track["name"]
                artist_name = track["artists"][0]["name"]
                album_name = track.get("album", {}).get("name", "Unknown Album")
                track_list.append(
                    {
                        "name": track_name,
                        "artist": artist_name,
                        "album": album_name,
                        "playlist_attempted": playlist_name,
                    }
                )
        return {"name": playlist_name, "tracks": track_list}
    except Exception:
        logger.error(
            f"Error fetching playlist details from Spotify for: {playlist_url_or_id}",
            exc_info=True,
        )
        return None


def download_track_as_mp3(track_info, download_path):
    search_query = f"{track_info['artist']} - {track_info['name']} audio"
    safe_filename_base = "".join(
        c if c.isalnum() or c in " ._-" else "_" for c in f"{track_info['artist']} - {track_info['name']}"
    )
    output_template = os.path.join(download_path, f"{safe_filename_base}.mp3")

    logger.info(f"Processing: {track_info['artist']} - {track_info['name']}")

    if os.path.exists(output_template):
        logger.info(f"Skipping '{safe_filename_base}', already downloaded.")
        return True

    try:
        command = [
            "yt-dlp",
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "0",
            "--output",
            output_template,
            "--default-search",
            "ytsearch1:",
            "--no-playlist",
            "--quiet",
            "--no-warnings",
            search_query,
        ]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()

        if process.returncode == 0:
            logger.info(f"Successfully downloaded: {safe_filename_base}.mp3")
            return True
        else:
            error_message = f"Failed to download '{search_query}'."
            stderr_output = stderr.decode(errors="ignore").strip()
            if stderr_output:
                error_message += f" yt-dlp stderr: {stderr_output}"
            logger.error(error_message)
            return False
    except FileNotFoundError:
        logger.error(
            "yt-dlp command not found. Make sure it's installed and in your PATH.",
        )
        return False
    except Exception:
        logger.error(
            f"An error occurred during download for '{search_query}'",
            exc_info=True,
        )
        return False


def append_failed_tracks_to_json(failed_tracks, filename):
    all_failures = []
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read()
                if content.strip():
                    all_failures = json.loads(content)
                if not isinstance(all_failures, list):
                    logger.warning(f"Existing content in {filename} is not a list. Overwriting with new failures.")
                    all_failures = []
        except json.JSONDecodeError:
            logger.warning(f"Could not decode JSON from {filename}. File might be corrupted. Starting fresh list.")
            all_failures = []
        except IOError as e:
            logger.error(f"IOError reading {filename}: {e}. Starting fresh list.")
            all_failures = []

    all_failures.extend(failed_tracks)

    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(all_failures, f, indent=4, ensure_ascii=False)
        logger.info(f"Appended {len(failed_tracks)} failed track(s) to {filename}")
    except IOError as e:
        logger.error(f"Could not write to {filename}: {e}")


def main():
    if not PLAYLIST_URLS:
        logger.warning("No playlist URLs provided in PLAYLIST_URLS list. Exiting.")
        return

    all_failed_tracks_across_playlists = []

    for playlist_url in PLAYLIST_URLS:
        logger.info(f"Processing playlist URL: {playlist_url}")
        playlist_data = get_playlist_details(playlist_url)

        if not playlist_data or not playlist_data.get("tracks"):
            logger.error(f"No tracks found or error fetching playlist details for {playlist_url}. Skipping.")
            continue

        playlist_name = playlist_data["name"]
        tracks_to_download = playlist_data["tracks"]
        total_tracks = len(tracks_to_download)

        sanitized_playlist_name = sanitize_foldername(playlist_name)
        playlist_specific_download_folder = os.path.join(BASE_DOWNLOAD_FOLDER, sanitized_playlist_name)
        os.makedirs(playlist_specific_download_folder, exist_ok=True)

        logger.info(f"Playlist: '{playlist_name}' (Saving to folder: '{sanitized_playlist_name}')")
        logger.info(
            f"Found {total_tracks} tracks. Starting downloads to "
            f"'{playlist_specific_download_folder}' using up to {MAX_WORKERS} workers."
        )

        downloaded_count = 0
        failed_count = 0
        failed_tracks_details_for_playlist = []

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=MAX_WORKERS, thread_name_prefix=f"Downloader-{sanitized_playlist_name}"
        ) as executor:
            future_to_track = {
                executor.submit(
                    download_track_as_mp3,
                    track,
                    playlist_specific_download_folder,
                ): track
                for track in tracks_to_download
            }

            for i, future in enumerate(concurrent.futures.as_completed(future_to_track)):
                track_info = future_to_track[future]
                try:
                    success = future.result()
                    if success:
                        downloaded_count += 1
                    else:
                        failed_count += 1
                        failed_tracks_details_for_playlist.append(track_info)
                        logger.warning(
                            f"Download FAILED for track: {track_info['artist']} - {track_info['name']} "
                            f"(Playlist: {playlist_name}). See above error for details."
                        )
                except Exception:
                    failed_count += 1
                    failed_tracks_details_for_playlist.append(track_info)
                    logger.error(
                        f"Exception during download for track: {track_info['artist']} - {track_info['name']} "
                        f"(Playlist: {playlist_name})",
                        exc_info=True,
                    )

                logger.info(
                    f"\rPlaylist '{playlist_name}' Progress: {i+1}/{total_tracks} tasks processed. "
                    f"(Succeeded: {downloaded_count}, Failed: {failed_count})",
                )

        logger.info(f"--- Download Summary for Playlist: {playlist_name} ---")
        logger.info(f"Successfully downloaded: {downloaded_count} tracks.")
        logger.info(f"Failed to download: {failed_count} tracks.")

        if failed_tracks_details_for_playlist:
            all_failed_tracks_across_playlists.extend(failed_tracks_details_for_playlist)
            logger.warning(
                f"{failed_count} track(s) failed in playlist '{playlist_name}'. Details will be included in the overall failed downloads file."
            )
        else:
            logger.info(f"All tracks processed successfully in playlist '{playlist_name}' or were already downloaded.")

        logger.info(
            f"MP3s for playlist '{playlist_name}' saved in: {os.path.abspath(playlist_specific_download_folder)}"
        )
        logger.info("-" * 20)  # Separator between playlists

    if all_failed_tracks_across_playlists:
        logger.warning(
            f"Overall: {len(all_failed_tracks_across_playlists)} track(s) failed across all processed playlists."
        )
        logger.info("--- Overall Failed Track Details ---")
        for failed_track in all_failed_tracks_across_playlists:
            logger.info(
                f"  - Name: {failed_track['name']}, Artist: {failed_track['artist']}, Album: {failed_track['album']} (Attempted in: {failed_track.get('playlist_attempted', 'N/A')})"
            )
        append_failed_tracks_to_json(all_failed_tracks_across_playlists, FAILED_DOWNLOADS_JSON_FILE)
    else:
        logger.info(
            "Overall: All tracks processed successfully across all processed playlists or were already downloaded."
        )


if __name__ == "__main__":
    main()
