import os
from dotenv import load_dotenv
import requests
from urllib.parse import urlencode
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

load_dotenv()

CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
REDIRECT_URI = 'http://localhost:8888/callback'  # Используем локальный сервер для получения кода

# Области доступа, которые нам нужны
SCOPE = 'playlist-modify-public playlist-modify-private user-read-private'

class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if '/callback' in self.path:
            # Получаем код из URL
            code = self.path.split('code=')[1].split('&')[0]
            
            # Отправляем успешный ответ пользователю
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"Authorization successful! You can close this window.")
            
            # Сохраняем код для использования в основном потоке
            self.server.auth_code = code

    def log_message(self, format, *args):
        # Отключаем логирование запросов
        return

def get_refresh_token():
    # Создаем URL для авторизации
    auth_url = 'https://accounts.spotify.com/authorize?' + urlencode({
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPE
    })

    # Открываем браузер для авторизации
    print("Opening browser for authorization...")
    webbrowser.open(auth_url)

    # Запускаем локальный сервер для получения кода
    server = HTTPServer(('localhost', 8888), CallbackHandler)
    server.auth_code = None
    print("Waiting for authorization...")
    
    # Ждем пока не получим код
    while server.auth_code is None:
        server.handle_request()
    
    auth_code = server.auth_code
    print("Authorization code received!")

    # Обмениваем код на токены
    response = requests.post('https://accounts.spotify.com/api/token', data={
        'grant_type': 'authorization_code',
        'code': auth_code,
        'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    })

    if response.status_code == 200:
        tokens = response.json()
        print("\nHere are your tokens:")
        print(f"Access Token: {tokens['access_token']}")
        print(f"\nRefresh Token: {tokens['refresh_token']}")
        print("\nAdd the refresh token to your .env file as SPOTIFY_REFRESH_TOKEN")
    else:
        print(f"Error getting tokens: {response.text}")

if __name__ == "__main__":
    get_refresh_token() 