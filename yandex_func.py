import os
import logging
import random
from yandex_music import Client
from dotenv import load_dotenv
import json
import time

# Загрузка переменных окружения
load_dotenv()
yandex_client = Client(os.getenv("YANDEX_MUSIC_TOKEN")).init()

# Настройка логирования
logger = logging.getLogger(__name__)

def get_yandex_artist_info(artist_id):
    try:
        artist = yandex_client.artists(artist_id)[0]  # Получаем первого артиста из списка
        logger.info(f"Yandex artist data: {artist}")  # Добавим лог для отладки
        return {
            "name": artist.name,
            "followers": "N/A",
            "link": f"https://music.yandex.ru/artist/{artist_id}"
        }
    except Exception as e:
        logger.error(f"Error in get_yandex_artist_info: {e}")
    return None

def search_yandex_artist(artist_name):
    try:
        search_result = yandex_client.search(artist_name, type_="artist")
        if search_result and search_result.artists:
            return search_result.artists.results[:5]  # Возвращаем первые 5 артистов
        return None
    except Exception as e:
        logger.error(f"Ошибка при поиске артиста в Yandex Music: {e}")
        return None

def get_yandex_last_releases(artist_id):
    try:
        artist = yandex_client.artists(artist_id)[0]
        albums = []
        singles = []

        for release in artist.get_albums():
            if release.type == 'single':
                singles.append(release)
            else:
                albums.append(release)

        album = None
        single = None

        if albums:
            latest_album = albums[0]
            album = {
                "id": str(latest_album.id),  # Добавляем ID как строку
                "name": latest_album.title,
                "release_date": latest_album.release_date if latest_album.release_date else "N/A",
                "link": f"https://music.yandex.ru/album/{latest_album.id}"
            }

        if singles:
            latest_single = singles[0]
            single = {
                "id": str(latest_single.id),  # Добавляем ID как строку
                "name": latest_single.title,
                "release_date": latest_single.release_date if latest_single.release_date else "N/A",
                "link": f"https://music.yandex.ru/album/{latest_single.id}"
            }

        return album, single
    except Exception as e:
        logger.error(f"Error in get_yandex_last_releases: {e}")
        return None, None

def get_yandex_top_tracks(artist_id):
    try:
        artist = yandex_client.artists(artist_id)[0]
        
        # Получаем популярные треки артиста
        if not artist.popular_tracks:
            # Если нет списка популярных треков, получаем все треки
            tracks = artist.get_tracks()
            if not tracks:
                return None
        else:
            tracks = artist.popular_tracks
        
        all_tracks = []
        # Берем только первые 10 треков
        for track in tracks[:10]:
            # Проверяем длительность трека
            if track.duration_ms >= 60000:  # 60000 мс = 1 минута
                track_info = {
                    "name": track.title,
                    "link": f"https://music.yandex.ru/track/{track.id}"
                }
                all_tracks.append(track_info)
        
        return all_tracks
        
    except Exception as e:
        logger.error(f"Error in get_yandex_top_tracks: {e}")
        return None

def get_yandex_new_releases(artist_id):
    try:
        artist = yandex_client.artists(artist_id)
        if artist and artist.releases:
            return artist.releases  # Возвращаем список релизов
        return []
    except Exception as e:
        logger.error(f"Ошибка при получении релизов из Yandex Music: {e}")
        return []

def create_yandex_playlist(tracks, title="Случайный микс"):
    try:
        # Проверяем токен
        if not yandex_client.token:
            logger.error("No Yandex Music token available")
            return None
            
        # Проверяем пользователя
        try:
            user_id = yandex_client.me.account.uid
            logger.info(f"Got user_id: {user_id}")
        except Exception as e:
            logger.error(f"Failed to get user info: {e}")
            return None
        
        # Создаем новый плейлист
        try:
            playlist = yandex_client.users_playlists_create(
                title=title,
                visibility="public",
                user_id=user_id
            )
            logger.info(f"Created playlist with kind={playlist.kind}")
        except Exception as e:
            logger.error(f"Failed to create playlist: {e}")
            return None
        
        # Получаем информацию о треках
        tracks_info = []
        for track in tracks:
            if 'link' in track:
                try:
                    track_id = int(track['link'].split('/')[-1])
                    track_info = yandex_client.tracks([track_id])[0]
                    
                    if not track_info or not track_info.albums:
                        continue
                        
                    tracks_info.append({
                        'id': str(track_id),
                        'albumId': str(track_info.albums[0].id)
                    })
                    logger.info(f"Added track {track_id} to queue")
                except Exception as e:
                    logger.error(f"Error processing track {track.get('link', 'unknown')}: {e}")
                    continue
        
        if not tracks_info:
            logger.error("No valid tracks found")
            return None
        
        try:
            # Получаем актуальную версию плейлиста
            current_playlist = yandex_client.users_playlists(kind=playlist.kind)
            
            # Создаем изменения для плейлиста
            diff = [{
                'op': 'insert',
                'at': 0,
                'tracks': []
            }]
            
            # Добавляем треки в diff
            for track in tracks_info:
                track_obj = {
                    'id': int(track['id']),
                    'albumId': int(track['albumId'])
                }
                diff[0]['tracks'].append(track_obj)
            
            # Формируем данные для запроса
            data = {
                'kind': playlist.kind,
                'revision': current_playlist.revision,
                'diff': json.dumps(diff)
            }
            
            # Отправляем запрос через API клиент
            base_url = "https://api.music.yandex.net"
            url = f"{base_url}/users/{yandex_client.me.account.uid}/playlists/{playlist.kind}/change-relative"
            
            response = yandex_client._request.post(
                url,
                data,
                timeout=30
            )
            
            if isinstance(response, dict):
                logger.info(f"Successfully added {len(tracks_info)} tracks")
                time.sleep(2)  # Даем время на обновление плейлиста
            else:
                logger.error(f"Failed to modify playlist: {response}")
            
            # В любом случае возвращаем ссылку на плейлист
            logger.info("Returning playlist link")
            return f"https://music.yandex.ru/users/{yandex_client.me.account.uid}/playlists/{playlist.kind}"
            
        except Exception as e:
            logger.error(f"Error in playlist modification: {e}")
            return f"https://music.yandex.ru/users/{yandex_client.me.account.uid}/playlists/{playlist.kind}"
            
    except Exception as e:
        logger.error(f"Error in create_yandex_playlist: {e}")
        return None

def delete_old_mix(user_id, username):
    try:
        # Получаем все плейлисты пользователя
        playlists = yandex_client.users_playlists_list()
        
        # Ищем плейлист с названием "Микс для {username}"
        for playlist in playlists:
            if playlist.title == f"Микс для {username}":
                try:
                    yandex_client.users_playlists_delete(kind=playlist.kind)
                    logger.info(f"Deleted old mix playlist for user {username}")
                except Exception as e:
                    logger.error(f"Error deleting old playlist: {e}")
                break
    except Exception as e:
        logger.error(f"Error finding old playlist: {e}") 