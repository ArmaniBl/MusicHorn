import os
import telebot
import requests
import schedule
import time
import logging
import random
import json
from database import *
from dotenv import load_dotenv
from yandex_music import Client
from telebot import types
from requests.exceptions import ProxyError, ConnectionError
from urllib3.exceptions import MaxRetryError
from http.client import RemoteDisconnected
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Загрузка токенов из .env
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")
SPOTIFY_REFRESH_TOKEN = os.getenv("SPOTIFY_REFRESH_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1019214619"))
yandex_client = Client(os.getenv("YANDEX_MUSIC_TOKEN")).init()

# Стоимость слотов
SLOT_PRICES = {
    1: 10,  # 10 рублей за 1 слот
    3: 25,  # 25 рублей за 3 слота
    5: 40   # 40 рублей за 5 слотов
}

PAYMENT_INFO = """
💳 Реквизиты для оплаты:
Сбербанк: 5469 9804 7424 060
Тинькофф: 4377 7278 1980 1759
СБП: +7 (951) 107-82-24
После оплаты отправьте скриншот или фото чека администратору: @ArmaniB
"""

# Инициализация бота
bot = telebot.TeleBot(TOKEN)

# Очищаем лог файл при запуске
with open("bot.log", "w") as f:
    f.write("")

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="bot.log",
    filemode='w'  # Добавляем режим 'w' для перезаписи файла
)
logger = logging.getLogger(__name__)

# Настройка сессии requests с повторными попытками
session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)
session.mount("http://", adapter)

# Настройка таймаутов для бота
bot.timeout = 30  # Увеличиваем таймаут до 30 секунд

# Пример использования логов
@bot.message_handler(commands=["start"])
def start(message):
    logger.info(f"Пользователь {message.from_user.id} запустил бота.")
    add_user(message.from_user.id)
    welcome_text = f"👋 Привет, {message.from_user.first_name}! Я MusicHorn. Я помогу отслеживать новые релизы твоих любимых исполнителей."
    show_main_menu(message.chat.id, welcome_text)


@bot.callback_query_handler(func=lambda call: call.data.startswith("artist_info:"))
def handle_artist_info(call):
    try:
        _, artist_id, platform = call.data.split(":")
        logger.info(f"Fetching artist info for artist_id={artist_id}, platform={platform}")

        # Получаем информацию об артисте
        artist_info = get_artist_info(artist_id, platform)

        # Проверяем, получена ли информация
        if artist_info is None:
            bot.answer_callback_query(call.id, "❌ Информация об артисте не найдена.")
            bot.send_message(call.message.chat.id, "❌ Информация об артисте не найдена.")
            return

        # Форматируем информацию
        formatted_info = (
            f"🎤 Артист: {artist_info['name']}\n"
            f"👥 Подписчики: {artist_info['followers']}\n"
            f"🔗 Ссылка: {artist_info['link']}"
        )

        # Создаем клавиатуру с кнопками
        markup = types.InlineKeyboardMarkup(row_width=2)
        unsubscribe_button = types.InlineKeyboardButton(
            "❌ Отписаться",
            callback_data=f"unsubscribe:{artist_id}:{platform}"
        )
        last_release_button = types.InlineKeyboardButton(
            "🎵 Последний релиз",
            callback_data=f"last_release:{artist_id}:{platform}"
        )
        top_tracks_button = types.InlineKeyboardButton(
            "🎼 Топ 10 песен",
            callback_data=f"top_tracks:{artist_id}:{platform}"
        )
        back_button = types.InlineKeyboardButton(
            "🔙 К списку артистов",
            callback_data="view_subscriptions"
        )
        
        markup.add(unsubscribe_button, last_release_button)
        markup.add(top_tracks_button)
        markup.add(back_button)

        bot.edit_message_text(
            formatted_info,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        bot.answer_callback_query(call.id, "✅ Информация загружена.")

    except Exception as e:
        logger.error(f"Error in handle_artist_info: {e}")
        bot.send_message(call.message.chat.id, "Произошла ошибка при получении информации об артисте.")


def get_artist_info(artist_id, platform):
    if platform == "Spotify":
        return get_spotify_artist_info(artist_id)
    elif platform == "Yandex Music":
        return get_yandex_artist_info(artist_id)
    else:
        logger.error(f"Unsupported platform: {platform}")
        return None

def format_artist_info(artist_info):
    if artist_info:
        return (
            f"🎶 Имя: {artist_info['name']}\n"
            f"👥 Подписчики: {artist_info['followers']}\n"
            f"🔗 Ссылка: {artist_info['link']}"
        )
    return "❌ Информация об артисте не найдена."



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
            logger.info(f"Spotify API response: {data}")  # Добавим лог для отладки
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

# Для Spotify
def test_spotify_artist(artist_id):
    token = get_spotify_token()
    if not token:
        print("Токен Spotify недействителен.")
        return
    url = f"https://api.spotify.com/v1/artists/{artist_id}"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        print("Артист найден на Spotify.")
    else:
        print(f"Артист с ID {artist_id} не найден на Spotify.")

# Для Yandex Music
def test_yandex_artist(artist_id):
    try:
        artist = yandex_client.artists(artist_id)
        if artist:
            print("Артист найден на Yandex Music.")
        else:
            print(f"Артист с ID {artist_id} не найден на Yandex Music.")
    except Exception as e:
        print(f"Ошибка при проверке артиста на Yandex Music: {e}")


def check_spotify_token():
    token = get_spotify_token()
    if not token:
        print("Токен Spotify отсутствует или недействителен.")
        return False

    url = "https://api.spotify.com/v1/me"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        print("Токен Spotify действителен.")
        return True
    else:
        print(f"Токен Spotify недействителен. Код ошибки: {response.status_code}")
        return False


@bot.callback_query_handler(func=lambda call: call.data.startswith("unsubscribe:"))
def handle_unsubscribe(call):
    try:
        # Разбираем callback_data
        _, artist_id, platform = call.data.split(":")

        # Удаляем подписку по artist_id
        remove_subscription(call.from_user.id, artist_id=artist_id)

        # Отправляем уведомление и удаляем сообщение
        bot.answer_callback_query(call.id, f"❌ Ты больше не следишь за этим артистом на {platform}.")
        bot.delete_message(call.message.chat.id, call.message.message_id)

        # Показываем главное меню
        show_main_menu(call.message.chat.id, "Выберите действие:")

    except Exception as e:
        logger.error(f"Error in handle_unsubscribe: {e}")
        bot.answer_callback_query(call.id, "Произошла ошибка при отписке.")

# Получение токена доступа Spotify
def get_spotify_token():
    try:
        # Используем refresh token для получения нового access token
        auth_response = requests.post(
            'https://accounts.spotify.com/api/token',
            data={
                'grant_type': 'refresh_token',
                'refresh_token': os.getenv('SPOTIFY_REFRESH_TOKEN'),
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


@bot.callback_query_handler(func=lambda call: call.data.startswith("last_release:"))
def handle_last_release(call):
    # Разбираем callback_data
    _, artist_id, platform = call.data.split(":")

    # Получаем последние релизы
    if platform == "Spotify":
        album, single = get_spotify_last_releases(artist_id)
    elif platform == "Yandex Music":
        album, single = get_yandex_last_releases(artist_id)
    else:
        bot.answer_callback_query(call.id, "❌ Платформа не поддерживается.")
        return

    # Формируем сообщение
    message_text = "🎵 Последние релизы:\n\n"

    if album:
        message_text += (
            "📀 Последний альбом:\n"
            f"Название: {album['name']}\n"
            f"Дата выхода: {album.get('release_date', 'N/A')}\n"
            f"Ссылка: {album.get('link', 'N/A')}\n\n"
        )

    if single:
        message_text += (
            "💿 Последний сингл:\n"
            f"Название: {single['name']}\n"
            f"Дата выхода: {single.get('release_date', 'N/A')}\n"
            f"Ссылка: {single.get('link', 'N/A')}"
        )

    if not album and not single:
        message_text = "❌ Релизы не найдены"

    # Создаем клавиатуру с кнопкой "Назад"
    markup = types.InlineKeyboardMarkup()
    back_button = types.InlineKeyboardButton(
        "🔙 Назад к артисту",
        callback_data=f"artist_info:{artist_id}:{platform}"
    )
    markup.add(back_button)

    # Отправляем сообщение с кнопкой
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, message_text, reply_markup=markup)
    bot.answer_callback_query(call.id)

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
                "name": latest_album.title,
                "release_date": latest_album.release_date if latest_album.release_date else "N/A",
                "link": f"https://music.yandex.ru/album/{latest_album.id}"
            }

        if singles:
            latest_single = singles[0]
            single = {
                "name": latest_single.title,
                "release_date": latest_single.release_date if latest_single.release_date else "N/A",
                "link": f"https://music.yandex.ru/album/{latest_single.id}"
            }

        return album, single
    except Exception as e:
        logger.error(f"Error in get_yandex_last_releases: {e}")
        return None, None

# Поиск артиста в Spotify
def search_artist(artist_name):
    token = get_spotify_token()
    url = "https://api.spotify.com/v1/search"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"q": artist_name, "type": "artist", "limit": 1}
    response = requests.get(url, headers=headers, params=params)
    return response.json()


# Получение новых релизов артиста
def get_new_releases(artist_id):
    token = get_spotify_token()
    url = f"https://api.spotify.com/v1/artists/{artist_id}/albums"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"limit": 5, "include_groups": "album,single"}  # Последние 5 альбомов/синглов
    response = requests.get(url, headers=headers, params=params)
    return response.json().get("items", [])


# Обработчик команды /track
@bot.message_handler(commands=["track"])
def track_artist(message):
    args = message.text.split()[1:]  # Получаем аргументы после команды
    if not args:
        bot.reply_to(message, "❌ Укажи имя артиста: /track Billie Eilish")
        return

    artist_name = " ".join(args)
    # Создаем inline-кнопки для выбора платформы
    markup = types.InlineKeyboardMarkup(row_width=2)
    spotify_btn = types.InlineKeyboardButton("Spotify", callback_data=f"choose_platform:Spotify:{artist_name}")
    yandex_btn = types.InlineKeyboardButton("Yandex Music", callback_data=f"choose_platform:Yandex Music:{artist_name}")
    back_btn = types.InlineKeyboardButton("🔙 Назад", callback_data="menu_subscriptions")
    markup.add(spotify_btn, yandex_btn, back_btn)
    
    bot.reply_to(
        message, 
        "🎵 Выберите платформу:", 
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("choose_platform:"))
def handle_platform_choice(call):
    try:
        _, platform, artist_name = call.data.split(":", 2)
        
        if not can_add_subscription(call.from_user.id):
            vip_level = get_vip_level(call.from_user.id)
            max_subs = get_max_subscriptions(call.from_user.id)
            bot.answer_callback_query(call.id)
            bot.edit_message_text(
                f"❌ Достигнут лимит подписок!\n"
                f"Текущий уровень: {vip_level}\n"
                f"Максимум подписок: {max_subs}\n"
                f"Повысьте уровень для увеличения лимита.",
                call.message.chat.id,
                call.message.message_id
            )
            show_main_menu(call.message.chat.id)
            return

        if platform == "Spotify":
            result = search_artist(artist_name)
            if result.get("artists", {}).get("items"):
                artist = result["artists"]["items"][0]
                artist_id = artist["id"]
                
                if has_subscription(call.from_user.id, artist_id):
                    bot.answer_callback_query(call.id)
                    bot.edit_message_text(
                        f"❌ Ты уже подписан на {artist['name']} в Spotify!",
                        call.message.chat.id,
                        call.message.message_id
                    )
                    show_main_menu(call.message.chat.id)
                    return
                    
                artist_name = artist["name"]
                add_subscription(call.from_user.id, artist_id, artist_name, platform="Spotify")
                bot.answer_callback_query(call.id)
                bot.edit_message_text(
                    f"🎤 Теперь ты следишь за {artist_name} на Spotify!\n"
                    f"Ссылка: {artist['external_urls']['spotify']}\n\n"
                    f"Подписок: {len(get_subscriptions(call.from_user.id))}/{get_max_subscriptions(call.from_user.id)}",
                    call.message.chat.id,
                    call.message.message_id
                )
            else:
                bot.answer_callback_query(call.id)
                bot.edit_message_text(
                    f"❌ Артист {artist_name} не найден на Spotify.",
                    call.message.chat.id,
                    call.message.message_id
                )
        elif platform == "Yandex Music":
            artist = search_yandex_artist(artist_name)
            if artist:
                artist_id = artist.id
                
                if has_subscription(call.from_user.id, str(artist_id)):
                    bot.answer_callback_query(call.id)
                    bot.edit_message_text(
                        f"❌ Ты уже подписан на {artist.name} в Yandex Music!",
                        call.message.chat.id,
                        call.message.message_id
                    )
                    show_main_menu(call.message.chat.id)
                    return
                    
                artist_name = artist.name
                add_subscription(call.from_user.id, artist_id, artist_name, platform="Yandex Music")
                bot.answer_callback_query(call.id)
                bot.edit_message_text(
                    f"🎤 Теперь ты следишь за {artist_name} на Yandex Music!\n"
                    f"Ссылка: https://music.yandex.ru/artist/{artist_id}\n\n"
                    f"Подписок: {len(get_subscriptions(call.from_user.id))}/{get_max_subscriptions(call.from_user.id)}",
                    call.message.chat.id,
                    call.message.message_id
                )
            else:
                bot.answer_callback_query(call.id)
                bot.edit_message_text(
                    f"❌ Артист {artist_name} не найден на Yandex Music.",
                    call.message.chat.id,
                    call.message.message_id
                )
        
        show_main_menu(call.message.chat.id)
        
    except Exception as e:
        logger.error(f"Error in handle_platform_choice: {e}")
        bot.answer_callback_query(call.id, "Произошла ошибка")

# Обработчик команды /my_artists
@bot.message_handler(commands=["my_artists"])
def list_artists(message):
    subscriptions = get_subscriptions(message.from_user.id)

    if subscriptions:
        markup = types.InlineKeyboardMarkup()

        for sub in subscriptions:
            # Ensure sub has at least 3 elements
            if len(sub) >= 3:
                artist_id = sub[0]  # ID артиста
                artist_name = sub[1]  # Имя артиста
                platform = sub[2]  # Платформа

                # Create a button for each artist
                markup.add(types.InlineKeyboardButton(
                    text=f"{artist_name} ({platform})",
                    callback_data=f"artist_info:{artist_id}:{platform}"
                ))

        # Меняем callback_data для кнопки "Назад"
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="menu_subscriptions"))
        bot.send_message(message.chat.id, "🎤 Твои подписки:", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "❌ У тебя пока нет подписок.")
        show_main_menu(message.chat.id)


@bot.message_handler(commands=["untrack"])
def untrack_artist(message):
    args = message.text.split()[1:]  # Получаем аргументы после команды
    if not args:
        bot.reply_to(message, "❌ Укажи имя артиста: /untrack Billie Eilish")
        return

    artist_name = " ".join(args)
    # Удаляем подписку по имени артиста
    remove_subscription(message.from_user.id, artist_name=artist_name)
    bot.reply_to(message, f"❌ Ты больше не следишь за {artist_name}.")

    # Показываем главное меню
    show_main_menu(message.chat.id)

@bot.message_handler(commands=["mute"])
def mute_notifications(message):
    mute_user(message.from_user.id)
    bot.reply_to(message, "🔕 Уведомления отключены. Используй /unmute, чтобы включить их снова.")

@bot.message_handler(commands=["unmute"])
def unmute_notifications(message):
    unmute_user(message.from_user.id)
    bot.reply_to(message, "🔔 Уведомления включены. Используй /mute, чтобы отключить их.")

# Функция для проверки новых релизов
def check_new_releases():
    conn, cursor = get_db()
    #Получаем всех пользователей и их подписки
    cursor.execute("SELECT telegram_id FROM users WHERE muted = FALSE")
    users = cursor.fetchall()
    for user in users:
        telegram_id = user[0]
        subscriptions = get_subscriptions(telegram_id)
        for sub in subscriptions:
            artist_id = sub[1]  # artist_id
            platform = sub[3]  # platform
            if platform == "Spotify":
                new_releases = get_new_releases(artist_id)
            elif platform == "Yandex Music":
                new_releases = get_yandex_new_releases(artist_id)
            else:
                continue

            if new_releases:
                for release in new_releases:
                    if platform == "Spotify":
                        release_date = release.get("release_date", "дата неизвестна")
                        total_tracks = release.get("total_tracks", "?")
                        message = (
                            f"🎵 Новый релиз от {sub[2]} на Spotify!\n"
                            f"Название: {release['name']}\n"
                            f"Дата выхода: {release_date}\n"
                            f"Треков: {total_tracks}\n"
                            f"Ссылка: {release['external_urls']['spotify']}"
                        )
                        if release.get("images"):
                            image_url = release["images"][0]["url"]
                            bot.send_photo(telegram_id, image_url, caption=message)
                        else:
                            bot.send_message(telegram_id, message)
                    elif platform == "Yandex Music":
                        release_date = release.date if release.date else "дата неизвестна"
                        message = (
                            f"🎵 Новый релиз от {sub[2]} на Yandex Music!\n"
                            f"Название: {release.title}\n"
                            f"Дата выхода: {release_date}\n"
                            f"Ссылка: https://music.yandex.ru/album/{release.id}"
                        )
                        bot.send_message(telegram_id, message)

# Поиск артиста в Yandex Music
def search_yandex_artist(artist_name):
    try:
        search_result = yandex_client.search(artist_name, type_="artist")
        if search_result and search_result.artists:
            return search_result.artists.results[0]  # Возвращаем первого найденного артиста
        return None
    except Exception as e:
        logger.error(f"Ошибка при поиске артиста в Yandex Music: {e}")
        return None

# Получение новых релизов артиста в Yandex Music
def get_yandex_new_releases(artist_id):
    try:
        artist = yandex_client.artists(artist_id)
        if artist and artist.releases:
            return artist.releases  # Возвращаем список релизов
        return []
    except Exception as e:
        logger.error(f"Ошибка при получении релизов из Yandex Music: {e}")
        return []

@bot.message_handler(commands=["help"])
def show_help(message):
    help_text = """
    🎵 Доступные команды:
    /start - Начать работу с ботом.
    /track [имя артиста] - Подписаться на артиста.
    /untrack [имя артиста] - Отписаться от артиста.
    /my_artists - Показать список подписок.
    /mute - Отключить уведомления.
    /unmute - Включить уведомления.
    /help - Показать это сообщение.
    """
    bot.reply_to(message, help_text)

# Запуск периодической проверки
schedule.every(1).hours.do(check_new_releases)  # Проверка каждые 1 час

def show_main_menu(chat_id, message_text="Выберите действие:", reply_to_message_id=None):
    try:
        vip_level = get_vip_level(chat_id)
        current_subs = len(get_subscriptions(chat_id))
        max_subs = get_max_subscriptions(chat_id)
        
        status_text = (
            f"📝 Подписки: {current_subs}/{max_subs}\n\n"
            f"{message_text}"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        subscriptions_btn = types.InlineKeyboardButton("📋 Подписки", callback_data="menu_subscriptions")
        mix_btn = types.InlineKeyboardButton("🎵 Создать микс", callback_data="create_mix")
        balance_btn = types.InlineKeyboardButton("💰 Купить слоты", callback_data="menu_balance")
        settings_btn = types.InlineKeyboardButton("⚙️ Настройки", callback_data="menu_settings")
        support_btn = types.InlineKeyboardButton("💝 Поддержать разработчика", callback_data="menu_support")
        
        markup.add(subscriptions_btn, mix_btn, balance_btn, settings_btn, support_btn)
        
        return bot.send_message(
            chat_id,
            status_text,
            reply_markup=markup,
            timeout=30  # Добавляем таймаут
        )
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        # Повторная попытка с увеличенным таймаутом
        time.sleep(2)
        return bot.send_message(
            chat_id,
            status_text,
            reply_markup=markup,
            timeout=60
        )
    except Exception as e:
        logger.error(f"Error in show_main_menu: {e}")
        return None

@bot.callback_query_handler(func=lambda call: call.data.startswith("menu_"))
def handle_menu(call):
    try:
        # Удаляем предыдущее сообщение
        bot.delete_message(call.message.chat.id, call.message.message_id)

        if call.data == "menu_subscriptions":
            markup = types.InlineKeyboardMarkup(row_width=1)
            view_btn = types.InlineKeyboardButton("👀 Посмотреть подписки", callback_data="view_subscriptions")
            add_btn = types.InlineKeyboardButton("➕ Подписаться на артиста", callback_data="add_subscription")
            remove_btn = types.InlineKeyboardButton("➖ Отписаться от артиста", callback_data="remove_subscription")
            back_btn = types.InlineKeyboardButton("🔙 Назад в меню", callback_data="show_main_menu")
            markup.add(view_btn, add_btn, remove_btn, back_btn)
            bot.send_message(call.message.chat.id, "📋 Управление подписками:", reply_markup=markup)

        elif call.data == "menu_balance":
            markup = types.InlineKeyboardMarkup(row_width=1)
            
            # Кнопки покупки слотов
            for slots, price in SLOT_PRICES.items():
                btn_text = f"🎟 Купить {slots} {'слот' if slots == 1 else 'слота' if 1 < slots < 5 else 'слотов'} за {price}₽"
                markup.add(types.InlineKeyboardButton(
                    btn_text,
                    callback_data=f"buy_slots:{slots}"
                ))
            
            history_btn = types.InlineKeyboardButton(
                "📋 История платежей",
                callback_data="payment_history"
            )
            back_btn = types.InlineKeyboardButton(
                "🔙 Назад в меню",
                callback_data="show_main_menu"
            )
            
            markup.add(history_btn, back_btn)
            
            message_text = (
                f"💫 Уровень: {get_vip_level(call.from_user.id)}\n"
                f"📝 Доступно слотов: {get_max_subscriptions(call.from_user.id)}\n\n"
                "Выберите количество слотов для покупки:"
            )
            
            bot.send_message(call.message.chat.id, message_text, reply_markup=markup)

        elif call.data == "menu_settings":
            markup = types.InlineKeyboardMarkup(row_width=1)

            # Проверяем статус уведомлений пользователя
            is_user_muted = is_muted(call.message.chat.id)

            # Показываем только релевантную кнопку
            if is_user_muted:
                notifications_btn = types.InlineKeyboardButton(
                    "🔔 Включить уведомления",
                    callback_data="unmute_notifications"
                )
            else:
                notifications_btn = types.InlineKeyboardButton(
                    "🔕 Отключить уведомления",
                    callback_data="mute_notifications"
                )

            back_btn = types.InlineKeyboardButton("🔙 Назад в меню", callback_data="show_main_menu")
            markup.add(notifications_btn, back_btn)

            # Показываем текущий статус
            status_text = "⚙️ Настройки\n\nСтатус уведомлений: " + ("🔕 Отключены" if is_user_muted else "🔔 Включены")
            bot.send_message(call.message.chat.id, status_text, reply_markup=markup)

        elif call.data == "menu_support":
            markup = types.InlineKeyboardMarkup(row_width=1)
            back_btn = types.InlineKeyboardButton("🔙 Назад в меню", callback_data="show_main_menu")
            markup.add(back_btn)
            bot.send_message(
                call.message.chat.id,
                "💝 Поддержать разработчика:\n\n"
                "Тинькофф: 4377 7278 1980 1759\n"
                "СБП: +7 (951) 107-82-24",
                reply_markup=markup
            )

    except Exception as e:
        logger.error(f"Error in handle_menu: {e}")
        bot.answer_callback_query(call.id, "Произошла ошибка")

@bot.callback_query_handler(func=lambda call: call.data == "show_main_menu")
def handle_show_main_menu(call):
    try:
        show_main_menu(call.message.chat.id)
        # Удаляем предыдущее сообщение
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception as e:
        logger.error(f"Error in handle_show_main_menu: {e}")
        bot.answer_callback_query(call.id, "Произошла ошибка")



@bot.callback_query_handler(func=lambda call: call.data in ["view_subscriptions", "add_subscription", "remove_subscription", "mute_notifications", "unmute_notifications"])
def handle_menu_actions(call):
    try:
        # Удаляем предыдущее сообщение
        bot.delete_message(call.message.chat.id, call.message.message_id)

        if call.data == "view_subscriptions":
            subscriptions = get_subscriptions(call.message.chat.id)

            if subscriptions:
                markup = types.InlineKeyboardMarkup()

                for sub in subscriptions:
                    if len(sub) >= 3:
                        artist_id = sub[0]
                        artist_name = sub[1]
                        platform = sub[2]

                        markup.add(types.InlineKeyboardButton(
                            text=f"{artist_name} ({platform})",
                            callback_data=f"artist_info:{artist_id}:{platform}"
                        ))

                # Меняем callback_data для кнопки "Назад"
                markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="menu_subscriptions"))
                bot.send_message(call.message.chat.id, "🎤 Твои подписки:", reply_markup=markup)
            else:
                bot.send_message(call.message.chat.id, "❌ У тебя пока нет подписок.")
                show_main_menu(call.message.chat.id)

        elif call.data == "add_subscription":
            msg = bot.send_message(call.message.chat.id, "Введите имя артиста:")
            bot.register_next_step_handler(msg, handle_artist_name_input)

        elif call.data == "remove_subscription":
            # Получаем список подписок
            subscriptions = get_subscriptions(call.message.chat.id)

            if subscriptions:
                markup = types.InlineKeyboardMarkup()

                for sub in subscriptions:
                    if len(sub) >= 3:
                        artist_id = sub[0]
                        artist_name = sub[1]
                        platform = sub[2]

                        # Создаем кнопку для каждого артиста
                        markup.add(types.InlineKeyboardButton(
                            text=f"❌ {artist_name} ({platform})",
                            callback_data=f"unsubscribe:{artist_id}:{platform}"
                        ))

                # Добавляем кнопку "Назад"
                markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="menu_subscriptions"))
                bot.send_message(call.message.chat.id, "Выберите артиста для отписки:", reply_markup=markup)
            else:
                bot.send_message(call.message.chat.id, "❌ У тебя пока нет подписок.")
                show_main_menu(call.message.chat.id)

        elif call.data == "mute_notifications":
            # Используем ID пользователя из call
            mute_user(call.from_user.id)
            # Вместо главного меню показываем меню настроек
            markup = types.InlineKeyboardMarkup(row_width=1)
            notifications_btn = types.InlineKeyboardButton(
                "🔔 Включить уведомления",
                callback_data="unmute_notifications"
            )
            back_btn = types.InlineKeyboardButton("🔙 Назад в меню", callback_query_data="show_main_menu")
            markup.add(notifications_btn, back_btn)
            status_text = "⚙️ Настройки\n\nСтатус уведомлений: 🔕 Отключены"
            bot.send_message(call.message.chat.id, status_text, reply_markup=markup)

        elif call.data == "unmute_notifications":
            # Используем ID пользователя из call
            unmute_user(call.from_user.id)
            markup = types.InlineKeyboardMarkup(row_width=1)
            notifications_btn = types.InlineKeyboardButton(
                "🔕 Отключить уведомления",
                callback_data="mute_notifications"
            )
            back_btn = types.InlineKeyboardButton("🔙 Назад в меню", callback_data="show_main_menu")
            markup.add(notifications_btn, back_btn)
            status_text = "⚙️ Настройки\n\nСтатус уведомлений: 🔔 Включены"
            bot.send_message(call.message.chat.id, status_text, reply_markup=markup)

    except Exception as e:
        logger.error(f"Error in handle_menu_actions: {e}")
        bot.answer_callback_query(call.id, "Произошла ошибка")

def handle_artist_name_input(message):
    artist_name = message.text
    # Создаем inline-кнопки для выбора платформы
    markup = types.InlineKeyboardMarkup(row_width=2)
    spotify_btn = types.InlineKeyboardButton("Spotify", callback_data=f"choose_platform:Spotify:{artist_name}")
    yandex_btn = types.InlineKeyboardButton("Yandex Music", callback_data=f"choose_platform:Yandex Music:{artist_name}")
    back_btn = types.InlineKeyboardButton("🔙 Назад", callback_data="menu_subscriptions")
    markup.add(spotify_btn, yandex_btn, back_btn)
    
    bot.reply_to(
        message, 
        "🎵 Выберите платформу:", 
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("top_tracks:"))
def handle_top_tracks(call):
    try:
        _, artist_id, platform = call.data.split(":")
        
        # Получаем топ треков
        if platform == "Spotify":
            tracks = get_spotify_top_tracks(artist_id)
        elif platform == "Yandex Music":
            tracks = get_yandex_top_tracks(artist_id)
        else:
            bot.answer_callback_query(call.id, "❌ Платформа не поддерживается.")
            return

        if not tracks:
            bot.answer_callback_query(call.id, "❌ Не удалось получить топ треков.")
            return

        # Формируем сообщение
        message_text = "🎵 Топ 10 песен:\n\n"
        for i, track in enumerate(tracks, 1):
            message_text += f"{i}. {track['name']}\n"
            if track.get('link'):
                message_text += f"🔗 {track['link']}\n"
            message_text += "\n"

        # Создаем клавиатуру с кнопкой "Назад"
        markup = types.InlineKeyboardMarkup()
        back_button = types.InlineKeyboardButton(
            "🔙 Назад к артисту",
            callback_data=f"artist_info:{artist_id}:{platform}"
        )
        markup.add(back_button)

        # Отправляем сообщение
        bot.edit_message_text(
            message_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        bot.answer_callback_query(call.id)

    except Exception as e:
        logger.error(f"Error in handle_top_tracks: {e}")
        bot.answer_callback_query(call.id, "Произошла ошибка при получении топ треков.")

def get_spotify_top_tracks(artist_id):
    try:
        token = get_spotify_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        # Получаем топ треки артиста напрямую
        top_tracks_response = requests.get(
            f"https://api.spotify.com/v1/artists/{artist_id}/top-tracks",
            headers=headers,
            params={"market": "US"}  # или другой рынок
        )
        
        if top_tracks_response.status_code != 200:
            return None
            
        all_tracks = []
        tracks = top_tracks_response.json()['tracks']
        
        # Добавляем топ треки
        for track in tracks:
            all_tracks.append({
                'name': track['name'],
                'link': track['external_urls']['spotify']
            })
        
        # Получаем последние релизы (опционально)
        albums_response = requests.get(
            f"https://api.spotify.com/v1/artists/{artist_id}/albums",
            headers=headers,
            params={
                "limit": 3,  # Берем только 3 последних альбома
                "include_groups": "album,single"
            }
        )
        
        if albums_response.status_code == 200:
            albums = albums_response.json()['items']
            
            # Для каждого альбома получаем несколько треков
            for album in albums:
                tracks_response = requests.get(
                    f"https://api.spotify.com/v1/albums/{album['id']}/tracks",
                    headers=headers,
                    params={"limit": 5}  # Берем только 5 треков из каждого альбома
                )
                if tracks_response.status_code == 200:
                    tracks = tracks_response.json()['items']
                    for track in tracks:
                        all_tracks.append({
                            'name': track['name'],
                            'link': track['external_urls']['spotify']
                        })
        
        return all_tracks
    except Exception as e:
        logger.error(f"Error in get_spotify_top_tracks: {e}")
        return None

def get_yandex_top_tracks(artist_id):
    try:
        artist = yandex_client.artists(artist_id)[0]
        all_tracks = []
        
        # Получаем все альбомы артиста
        albums = artist.get_albums()
        for album in albums:
            # Получаем треки из каждого альбома
            album_tracks = album.with_tracks().volumes
            for volume in album_tracks:
                for track in volume:
                    all_tracks.append({
                        'name': track.title,
                        'link': f"https://music.yandex.ru/track/{track.id}"
                    })
        
        return all_tracks
    except Exception as e:
        logger.error(f"Error in get_yandex_top_tracks: {e}")
        return None

# Добавим команду для администратора бота
@bot.message_handler(commands=["set_vip"])
def set_vip(message):
    # Проверяем, является ли отправитель администратором
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ У вас нет прав для выполнения этой команды.")
        return

    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "❌ Использование: /set_vip <user_id>")
        return

    try:
        user_id = int(args[1])
        set_vip_level(user_id, True)
        bot.reply_to(message, f"✅ Пользователь {user_id} получил VIP статус!")
    except ValueError:
        bot.reply_to(message, "❌ Некорректный ID пользователя.")
    except Exception as e:
        logger.error(f"Error in set_vip: {e}")
        bot.reply_to(message, "❌ Произошла ошибка при установке VIP статуса.")

@bot.message_handler(commands=["remove_vip"])
def remove_vip(message):
    # Проверяем, является ли отправитель администратором
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ У вас нет прав для выполнения этой команды.")
        return

    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "❌ Использование: /remove_vip <user_id>")
        return

    try:
        user_id = int(args[1])
        set_vip_level(user_id, False)
        bot.reply_to(message, f"✅ VIP статус пользователя {user_id} удален!")
    except ValueError:
        bot.reply_to(message, "❌ Некорректный ID пользователя.")
    except Exception as e:
        logger.error(f"Error in remove_vip: {e}")
        bot.reply_to(message, "❌ Произошла ошибка при удалении VIP статуса.")

@bot.callback_query_handler(func=lambda call: call.data == "menu_balance")
def handle_balance_menu(call):
    try:
        logger.info(f"Открываю меню баланса для пользователя {call.from_user.id}")
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        # Кнопки покупки слотов
        for slots, price in SLOT_PRICES.items():
            btn_text = f"🎟 Купить {slots} {'слот' if slots == 1 else 'слота' if 1 < slots < 5 else 'слотов'} за {price}₽"
            markup.add(types.InlineKeyboardButton(
                btn_text,
                callback_data=f"buy_slots:{slots}"
            ))
            
            history_btn = types.InlineKeyboardButton(
                "📋 История платежей",
                callback_data="payment_history"
            )
            back_btn = types.InlineKeyboardButton(
                "🔙 Назад в меню",
                callback_data="show_main_menu"
            )
            
            markup.add(history_btn, back_btn)
            
            message_text = (
                f"💫 Уровень: {get_vip_level(call.from_user.id)}\n"
                f"📝 Доступно слотов: {get_max_subscriptions(call.from_user.id)}\n\n"
                "Выберите количество слотов для покупки:"
            )
            
            # Пробуем отредактировать сообщение и логируем результат
            try:
                bot.edit_message_text(
                    message_text,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=markup
                )
                logger.info("Меню баланса успешно отображено")
                bot.answer_callback_query(call.id)
            except Exception as edit_error:
                logger.error(f"Ошибка при редактировании сообщения: {edit_error}")
                # Если не получилось отредактировать, пробуем отправить новое
                bot.send_message(
                    call.message.chat.id,
                    message_text,
                    reply_markup=markup
                )
            
    except Exception as e:
        logger.error(f"Error in handle_balance_menu: {e}")
        bot.answer_callback_query(call.id, "Произошла ошибка при открытии меню")
        # Отправляем сообщение об ошибке пользователю
        bot.send_message(call.message.chat.id, "Произошла ошибка при открытии меню. Попробуйте еще раз.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_slots:"))
def handle_buy_slots(call):
    try:
        slots = int(call.data.split(":")[1])
        price = SLOT_PRICES.get(slots)
        
        if not price:
            bot.answer_callback_query(call.id, "Неверное количество слотов")
            return
        
        # Создаем запрос на оплату
        request_id = create_payment_request(call.from_user.id, slots, price)
        
        message_text = (
            f"💳 Покупка {slots} {'слота' if slots == 1 else 'слотов'}\n"
            f"Сумма к оплате: {price}₽\n\n"
            f"Номер заказа: #{request_id}\n\n"
            f"{PAYMENT_INFO}\n\n"
            "⚠️ В комментарии к переводу укажите номер заказа!"
        )
        
        markup = types.InlineKeyboardMarkup()
        cancel_btn = types.InlineKeyboardButton(
            "🔙 Назад",
            callback_data="menu_balance"
        )
        markup.add(cancel_btn)
        
        bot.edit_message_text(
            message_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Error in handle_buy_slots: {e}")
        bot.answer_callback_query(call.id, "Произошла ошибка при создании заказа")

@bot.callback_query_handler(func=lambda call: call.data == "payment_history")
def handle_payment_history(call):
    try:
        payments = get_payment_history(call.from_user.id)
        
        if not payments:
            message_text = "История платежей пуста"
        else:
            message_text = "📋 История платежей:\n\n"
            for amount, slots, status, timestamp in payments:
                status_emoji = "✅" if status == "approved" else "❌" if status == "rejected" else "⏳"
                message_text += (
                    f"{status_emoji} {slots} {'слот' if slots == 1 else 'слота' if 1 < slots < 5 else 'слотов'} "
                    f"за {amount}₽ - {status}\n"
                    f"Дата: {timestamp}\n\n"
                )
        
        markup = types.InlineKeyboardMarkup()
        back_btn = types.InlineKeyboardButton(
            "🔙 Назад к балансу",
            callback_data="menu_balance"
        )
        markup.add(back_btn)
        
        bot.edit_message_text(
            message_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Error in handle_payment_history: {e}")
        bot.answer_callback_query(call.id, "Произошла ошибка")

# Команды для администратора
@bot.message_handler(commands=["payments"])
def show_pending_payments(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ У вас нет прав для выполнения этой команды.")
        return
        
    payments = get_pending_payments()
    if not payments:
        bot.reply_to(message, "Нет ожидающих подтверждения платежей")
        return
        
    for payment_id, user_id, slots, amount, timestamp, _ in payments:
        try:
            # Получаем информацию о пользователе
            user_info = bot.get_chat(user_id)
            user_name = user_info.first_name
            username = f"@{user_info.username}" if user_info.username else "нет username"
            
            markup = types.InlineKeyboardMarkup(row_width=2)
            approve_btn = types.InlineKeyboardButton(
                "✅ Подтвердить",
                callback_data=f"approve_payment:{payment_id}"
            )
            reject_btn = types.InlineKeyboardButton(
                "❌ Отклонить",
                callback_data=f"reject_payment:{payment_id}"
            )
            markup.add(approve_btn, reject_btn)
            
            message_text = (
                f"🆕 Новый платеж\n"
                f"Заказ: #{payment_id}\n"
                f"От: {user_name} ({username})\n"
                f"ID: {user_id}\n"
                f"Слотов: {slots}\n"
                f"Сумма: {amount}₽\n"
                f"Дата: {timestamp}"
            )
            
            bot.send_message(message.chat.id, message_text, reply_markup=markup)
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            # Если не удалось получить информацию о пользователе, показываем только ID
            message_text = (
                f"🆕 Новый платеж\n"
                f"Заказ: #{payment_id}\n"
                f"От: ID {user_id}\n"
                f"Слотов: {slots}\n"
                f"Сумма: {amount}₽\n"
                f"Дата: {timestamp}"
            )
            bot.send_message(message.chat.id, message_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith(("approve_payment:", "reject_payment:")))
def handle_payment_action(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ У вас нет прав для выполнения этого действия.")
        return
        
    action, payment_id = call.data.split(":")
    payment_id = int(payment_id)
    
    try:
        if action == "approve_payment":
            # Получаем информацию о платеже
            payment = get_payment_by_id(payment_id)
            if payment:
                # Обновляем статус платежа
                update_payment_request(payment_id, "approved")
                # Увеличиваем уровень VIP
                current_level = get_vip_level(payment[7])  # telegram_id
                set_vip_level(payment[7], current_level + payment[3])  # slots
                # Уведомляем пользователя
                bot.send_message(
                    payment[7],  # telegram_id
                    f"✅ Ваш платеж #{payment_id} подтвержден!\n"
                    f"Добавлено {payment[3]} {'слот' if payment[3] == 1 else 'слота' if 1 < payment[3] < 5 else 'слотов'}"
                )
        else:
            update_payment_request(payment_id, "rejected")
            # Уведомляем пользователя
            payment = get_payment_by_id(payment_id)
            if payment:
                bot.send_message(
                    payment[7],  # telegram_id
                    f"❌ Ваш платеж #{payment_id} отклонен.\n"
                    "Свяжитесь с администратором для выяснения причины."
                )
        
        # Удаляем кнопки из сообщения администратора
        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=None
        )
        
        bot.answer_callback_query(call.id, "✅ Готово")
        
    except Exception as e:
        logger.error(f"Error in handle_payment_action: {e}")
        bot.answer_callback_query(call.id, "Произошла ошибка при обработке платежа")

@bot.callback_query_handler(func=lambda call: call.data == "create_mix")
def handle_create_mix(call):
    try:
        # Получаем подписки пользователя
        subscriptions = get_subscriptions(call.from_user.id)
        
        if not subscriptions:
            bot.answer_callback_query(call.id)
            bot.edit_message_text(
                "❌ У вас нет подписок на исполнителей.\n"
                "Добавьте исполнителей для создания микса!",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=get_back_to_menu_markup()
            )
            return

        # Создаем клавиатуру для выбора платформы
        markup = types.InlineKeyboardMarkup(row_width=1)
        spotify_btn = types.InlineKeyboardButton("Spotify микс 🎵", callback_data="mix_platform:Spotify")
        yandex_btn = types.InlineKeyboardButton("Яндекс.Музыка микс 🎵", callback_data="mix_platform:Yandex Music")
        back_btn = types.InlineKeyboardButton("🔙 Назад", callback_data="show_main_menu")
        markup.add(spotify_btn, yandex_btn, back_btn)

        bot.edit_message_text(
            "Выберите платформу для создания микса:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

    except Exception as e:
        logger.error(f"Error in handle_create_mix: {e}")
        bot.answer_callback_query(call.id, "Произошла ошибка при создании микса")
        bot.edit_message_text(
            "❌ Произошла ошибка при создании микса.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=get_back_to_menu_markup()
        )

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

@bot.callback_query_handler(func=lambda call: call.data.startswith("mix_platform:"))
def handle_mix_platform(call):
    try:
        platform = call.data.split(":")[1]
        subscriptions = get_subscriptions(call.from_user.id)
        
        # Получаем имя пользователя
        user_name = call.from_user.first_name
        
        # Удаляем старый микс перед созданием нового
        if platform == "Yandex Music":
            delete_old_mix(call.from_user.id, user_name)
        elif platform == "Spotify":
            token = get_spotify_token()
            if token:
                delete_old_spotify_mix(token, user_name)
        
        # Фильтруем подписки по выбранной платформе
        platform_subscriptions = [sub for sub in subscriptions if sub[2] == platform]
        
        if not platform_subscriptions:
            bot.answer_callback_query(call.id)
            bot.edit_message_text(
                f"❌ У вас нет подписок на исполнителей в {platform}.\n"
                "Добавьте исполнителей для создания микса!",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=get_back_to_menu_markup()
            )
            return
            
        # Создаем сообщение о подготовке микса
        bot.edit_message_text(
            f"🎵 Создаю микс из случайных треков ваших любимых исполнителей в {platform}...\n"
            "Это может занять некоторое время, так как я просматриваю все альбомы...",
            call.message.chat.id,
            call.message.message_id
        )
        
        # Собираем треки от всех исполнителей выбранной платформы
        all_tracks = []
        for artist_id, artist_name, _ in platform_subscriptions:
            tracks = None
            if platform == "Spotify":
                tracks = get_spotify_top_tracks(artist_id)
            elif platform == "Yandex Music":
                tracks = get_yandex_top_tracks(artist_id)
            
            if tracks:
                # Добавляем имя исполнителя к каждому треку
                for track in tracks:
                    track['artist'] = artist_name
                    all_tracks.append(track)
        
        if not all_tracks:
            bot.edit_message_text(
                "❌ Не удалось получить треки для микса.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=get_back_to_menu_markup()
            )
            return
        
        # Перемешиваем все треки и выбираем случайные 30 вместо 15
        random.shuffle(all_tracks)
        selected_tracks = all_tracks[:30]  # Изменено с 15 на 30
        
        # Создаем плейлист
        playlist_link = None
        if platform == "Yandex Music":
            try:
                playlist_link = create_yandex_playlist(
                    selected_tracks,
                    f"Микс для {user_name}"
                )
                if not playlist_link:
                    logger.error("Failed to create Yandex Music playlist")
            except Exception as e:
                logger.error(f"Error in Yandex Music playlist creation: {e}")
        elif platform == "Spotify":
            try:
                playlist_link = create_spotify_playlist(selected_tracks, user_name)
                if not playlist_link:
                    logger.error("Failed to create Spotify playlist")
            except Exception as e:
                logger.error(f"Error in Spotify playlist creation: {e}")
        
        # Формируем сообщение с миксом
        message_text = f"Ваш случайный микс в {platform}:\n\n"
        for i, track in enumerate(selected_tracks, 1):
            message_text += f"{i}. {track['artist']} - {track['name']}\n"
            if track.get('link'):
                message_text += f"🔗 {track['link']}\n"
            message_text += "\n"
            
        if playlist_link:
            message_text += f"\n🎵 Плейлист в {'Яндекс.Музыке' if platform == 'Yandex Music' else 'Spotify'}:\n{playlist_link}"
        
        # Добавляем кнопку для создания нового случайного микса
        markup = types.InlineKeyboardMarkup(row_width=1)
        new_mix_btn = types.InlineKeyboardButton(
            "🔄 Создать новый случайный микс",
            callback_data=f"mix_platform:{platform}"
        )
        back_btn = types.InlineKeyboardButton(
            "🔙 В главное меню",
            callback_data="show_main_menu"
        )
        markup.add(new_mix_btn, back_btn)
        
        # Отправляем результат
        bot.edit_message_text(
            message_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Error in handle_mix_platform: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Произошла ошибка при создании микса")
        bot.edit_message_text(
            "❌ Произошла ошибка при создании микса.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=get_back_to_menu_markup()
        )

def get_back_to_menu_markup():
    """Вспомогательная функция для создания кнопки возврата в меню"""
    markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton("🔙 В главное меню", callback_data="show_main_menu")
    markup.add(back_btn)
    return markup

# Добавим новую функцию для получения и удаления старого плейлиста
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
                # Извлекаем ID трека из ссылки
                track_id = track['link'].split('/')[-1]
                track_uris.append(f"spotify:track:{track_id}")
                logger.info(f"Added track {track_id} to queue")
        
        # Добавляем треки порциями по 100 (ограничение API)
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

# Изменим структуру запуска бота в конце файла
if __name__ == "__main__":
    print("Бот запущен!")
    
    import threading
    
    def run_bot():
        while True:
            try:
                logger.info("Запуск бота...")
                bot.polling(none_stop=True, timeout=60, long_polling_timeout=30)
            except requests.exceptions.Timeout as e:
                logger.error(f"Timeout error: {e}")
                time.sleep(15)
            except requests.exceptions.ConnectionError as e:
                logger.error(f"Connection error: {e}")
                time.sleep(15)
            except telebot.apihelper.ApiTelegramException as e:
                if "Too Many Requests" in str(e):
                    logger.error("Rate limit exceeded, waiting...")
                    time.sleep(60)
                else:
                    logger.error(f"Telegram API error: {e}")
                    time.sleep(10)
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                time.sleep(10)
    
    def run_scheduler():
        while True:
            try:
                schedule.run_pending()
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            time.sleep(60)
    
    schedule.every(1).hours.do(check_new_releases)
    
    bot_thread = threading.Thread(target=run_bot)
    scheduler_thread = threading.Thread(target=run_scheduler)
    
    bot_thread.start()
    scheduler_thread.start()