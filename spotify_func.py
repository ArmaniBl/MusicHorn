import os
import requests
import logging
import random
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REFRESH_TOKEN = os.getenv("SPOTIFY_REFRESH_TOKEN")

# Настройка логирования
logger = logging.getLogger(__name__)

def get_spotify_token():
    try:
        # Используем refresh token для получения нового access token
        auth_response = requests.post(
            'https://accounts.spotify.com/api/token',
            data={
                'grant_type': 'refresh_token',
                'refresh_token': SPOTIFY_REFRESH_TOKEN,
                'client_id': SPOTIFY_CLIENT_ID,
                'client_secret': SPOTIFY_CLIENT_SECRET
            }
        )
        
        if auth_response.status_code != 200:
            logger.error(f"Failed to refresh Spotify token: {auth_response.text}")
            return None
            
        return auth_response.json()['access_token']
    except Exception as e:
        logger.error(f"Error getting Spotify token: {e}")
        return None

def search_artist(artist_name):
    token = get_spotify_token()
    url = "https://api.spotify.com/v1/search"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"q": artist_name, "type": "artist", "limit": 5}
    response = requests.get(url, headers=headers, params=params)
    return response.json()

def get_spotify_artist_info(artist_id):
    try:
        token = get_spotify_token()
        if not token:
            logger.error("Spotify token is missing or invalid.")
            return None

        url = f"https://api.spotify.com/v1/artists/{artist_id}"
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            return {
                "name": data["name"],
                "followers": data["followers"]["total"],
                "link": data["external_urls"]["spotify"]
            }
        else:
            logger.error(f"Spotify API error: {response.status_code}, {response.text}")
    except Exception as e:
        logger.error(f"Error in get_spotify_artist_info: {e}")
    return None

def get_spotify_last_releases(artist_id):
    token = get_spotify_token()
    headers = {"Authorization": f"Bearer {token}"}

    # Получаем последний альбом
    album_params = {"limit": 1, "include_groups": "album"}
    album_response = requests.get(
        f"https://api.spotify.com/v1/artists/{artist_id}/albums",
        headers=headers,
        params=album_params
    )

    # Получаем последний сингл
    single_params = {"limit": 1, "include_groups": "single"}
    single_response = requests.get(
        f"https://api.spotify.com/v1/artists/{artist_id}/albums",
        headers=headers,
        params=single_params
    )

    album = None
    single = None

    if album_response.status_code == 200:
        albums = album_response.json().get("items", [])
        if albums:
            album = {
                "name": albums[0]["name"],
                "release_date": albums[0].get("release_date", "N/A"),
                "link": albums[0]["external_urls"]["spotify"]
            }

    if single_response.status_code == 200:
        singles = single_response.json().get("items", [])
        if singles:
            single = {
                "name": singles[0]["name"],
                "release_date": singles[0].get("release_date", "N/A"),
                "link": singles[0]["external_urls"]["spotify"]
            }

    return album, single

def get_spotify_top_tracks(artist_id):
    try:
        token = get_spotify_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        # Получаем топ треки артиста
        response = requests.get(
            f"https://api.spotify.com/v1/artists/{artist_id}/top-tracks?market=RU",
            headers=headers
        )
        
        if response.status_code != 200:
            return None
            
        tracks_data = response.json()["tracks"]
        tracks = []
        
        for track in tracks_data:
            # Проверяем длительность трека (duration_ms в миллисекундах)
            if track["duration_ms"] >= 60000:  # 60000 мс = 1 минута
                tracks.append({
                    "name": track["name"],
                    "link": track["external_urls"]["spotify"]
                })
        
        return tracks
    except Exception as e:
        logger.error(f"Error in get_spotify_top_tracks: {e}")
        return None

def create_spotify_playlist(tracks, user_name):
    try:
        token = get_spotify_token()
        if not token:
            logger.error("Failed to get Spotify token")
            return None
            
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Получаем ID пользователя Spotify
        user_response = requests.get(
            "https://api.spotify.com/v1/me",
            headers=headers
        )
        
        if user_response.status_code == 401:
            logger.error("Spotify token is not valid for user operations")
            return None
            
        if user_response.status_code != 200:
            logger.error(f"Failed to get Spotify user info: {user_response.text}")
            return None
            
        user_id = user_response.json()['id']
        
        # Создаем новый плейлист
        playlist_data = {
            "name": f"Микс для {user_name}",
            "description": "Создано ботом MusicHorn",
            "public": True
        }
        
        playlist_response = requests.post(
            f"https://api.spotify.com/v1/users/{user_id}/playlists",
            headers=headers,
            json=playlist_data
        )
        
        if playlist_response.status_code != 201:
            logger.error(f"Failed to create Spotify playlist: {playlist_response.text}")
            return None
            
        playlist_id = playlist_response.json()['id']
        logger.info(f"Created Spotify playlist with ID: {playlist_id}")
        
        # Добавляем треки в плейлист
        track_uris = []
        for track in tracks:
            if 'link' in track:
                track_id = track['link'].split('/')[-1]
                track_uris.append(f"spotify:track:{track_id}")
                logger.info(f"Added track {track_id} to queue")
        
        # Добавляем треки порциями по 100
        for i in range(0, len(track_uris), 100):
            chunk = track_uris[i:i + 100]
            add_tracks_response = requests.post(
                f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
                headers=headers,
                json={"uris": chunk}
            )
            
            if add_tracks_response.status_code != 201:
                logger.error(f"Failed to add tracks to Spotify playlist: {add_tracks_response.text}")
                return None
            
            logger.info(f"Added chunk of {len(chunk)} tracks to playlist")
        
        logger.info("Successfully created Spotify playlist")
        return f"https://open.spotify.com/playlist/{playlist_id}"
        
    except Exception as e:
        logger.error(f"Error creating Spotify playlist: {e}")
        return None

def delete_old_spotify_mix(token, user_name):
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Получаем ID пользователя
        user_response = requests.get(
            "https://api.spotify.com/v1/me",
            headers=headers
        )
        if user_response.status_code != 200:
            logger.error(f"Failed to get Spotify user info: {user_response.text}")
            return
            
        user_id = user_response.json()['id']
        
        # Получаем плейлисты пользователя
        playlists_response = requests.get(
            f"https://api.spotify.com/v1/users/{user_id}/playlists",
            headers=headers
        )
        
        if playlists_response.status_code != 200:
            logger.error(f"Failed to get Spotify playlists: {playlists_response.text}")
            return
            
        # Ищем плейлист с нужным названием
        for playlist in playlists_response.json()['items']:
            if playlist['name'] == f"Микс для {user_name}":
                # Удаляем найденный плейлист
                delete_response = requests.delete(
                    f"https://api.spotify.com/v1/playlists/{playlist['id']}/followers",
                    headers=headers
                )
                if delete_response.status_code == 200:
                    logger.info(f"Deleted old Spotify mix playlist for user {user_name}")
                else:
                    logger.error(f"Failed to delete Spotify playlist: {delete_response.text}")
                break
                
    except Exception as e:
        logger.error(f"Error deleting old Spotify playlist: {e}") 