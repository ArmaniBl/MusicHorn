import sqlite3
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="database.log"
)
logger = logging.getLogger(__name__)
# Подключение к базе данных (файл database.db)
conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

# Создание таблиц
def init_db():
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE,
            muted BOOLEAN DEFAULT FALSE,
            vip_level INTEGER DEFAULT 0
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payment_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            slots INTEGER,
            status TEXT DEFAULT 'pending',
            payment_info TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            artist_id TEXT,
            artist_name TEXT,
            platform TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    conn.commit()
    logger.info("База данных инициализирована")

# Добавление пользователя
def add_user(telegram_id):
    cursor.execute(
        "INSERT OR IGNORE INTO users (telegram_id, muted, vip_level) VALUES (?, FALSE, 0)",
        (telegram_id,)
    )
    conn.commit()

def get_user_id(telegram_id):
    cursor.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
    result = cursor.fetchone()
    return result[0] if result else None

# Добавление подписки
def add_subscription(telegram_id, artist_id, artist_name, platform):
    logger.info(f"Попытка добавить подписку: telegram_id={telegram_id}, artist_name={artist_name}, platform={platform}")
    cursor.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    if not user:
        logger.info(f"Пользователь {telegram_id} не найден, добавляем...")
        add_user(telegram_id)
        cursor.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
        user = cursor.fetchone()

    user_id = user[0]
    cursor.execute("INSERT INTO subscriptions (user_id, artist_id, artist_name, platform) VALUES (?, ?, ?, ?)",
                   (user_id, artist_id, artist_name, platform))
    conn.commit()
    logger.info(f"Подписка добавлена: user_id={user_id}, artist_name={artist_name}, platform={platform}")

# Получение подписок пользователя
def get_subscriptions(telegram_id):
    cursor.execute("""
        SELECT subscriptions.artist_id, subscriptions.artist_name, subscriptions.platform
        FROM subscriptions
        JOIN users ON subscriptions.user_id = users.id
        WHERE users.telegram_id = ?
    """, (telegram_id,))
    return cursor.fetchall()

def get_db():
    return conn, cursor

def remove_subscription(telegram_id, artist_id=None, artist_name=None):
    try:
        if artist_id:
            cursor.execute("""
                DELETE FROM subscriptions
                WHERE user_id = (SELECT id FROM users WHERE telegram_id = ?)
                AND artist_id = ?
            """, (telegram_id, artist_id))
        elif artist_name:
            cursor.execute("""
                DELETE FROM subscriptions
                WHERE user_id = (SELECT id FROM users WHERE telegram_id = ?)
                AND artist_name LIKE ?
            """, (telegram_id, artist_name))
        conn.commit()
        logger.info(f"Subscription removed for user {telegram_id}, artist_id: {artist_id}, artist_name: {artist_name}")
    except Exception as e:
        logger.error(f"Error removing subscription: {e}")

def mute_user(telegram_id):
    cursor.execute("UPDATE users SET muted = TRUE WHERE telegram_id = ?", (telegram_id,))
    conn.commit()

def unmute_user(telegram_id):
    cursor.execute("UPDATE users SET muted = FALSE WHERE telegram_id = ?", (telegram_id,))
    conn.commit()

def is_muted(telegram_id):
    cursor.execute("SELECT muted FROM users WHERE telegram_id = ?", (telegram_id,))
    result = cursor.fetchone()
    return result[0] if result else False

def get_vip_level(telegram_id):
    cursor.execute(
        "SELECT vip_level FROM users WHERE telegram_id = ?",
        (telegram_id,)
    )
    result = cursor.fetchone()
    return result[0] if result else 0

def get_max_subscriptions(telegram_id):
    vip_level = get_vip_level(telegram_id)
    return 5 + vip_level

def can_add_subscription(telegram_id):
    current_subs = len(get_subscriptions(telegram_id))
    max_subs = get_max_subscriptions(telegram_id)
    return current_subs < max_subs

def set_vip_level(telegram_id, level):
    cursor.execute(
        "UPDATE users SET vip_level = ? WHERE telegram_id = ?",
        (level, telegram_id)
    )
    conn.commit()

def get_transaction_history(telegram_id):
    user_id = get_user_id(telegram_id)
    cursor.execute("""
        SELECT amount, status, timestamp 
        FROM transactions 
        WHERE user_id = ? 
        ORDER BY timestamp DESC 
        LIMIT 10
    """, (user_id,))
    return cursor.fetchall()

def create_payment_request(telegram_id, slots, amount):
    user_id = get_user_id(telegram_id)
    cursor.execute(
        "INSERT INTO payment_requests (user_id, slots, amount, status) VALUES (?, ?, ?, 'pending')",
        (user_id, slots, amount)
    )
    conn.commit()
    return cursor.lastrowid

def update_payment_request(request_id, status):
    cursor.execute(
        "UPDATE payment_requests SET status = ? WHERE id = ?",
        (status, request_id)
    )
    conn.commit()

def get_pending_payments():
    cursor.execute("""
        SELECT 
            payment_requests.id,
            users.telegram_id,
            payment_requests.slots, 
            payment_requests.amount,
            payment_requests.timestamp,
            payment_requests.payment_info
        FROM payment_requests 
        JOIN users ON payment_requests.user_id = users.id
        WHERE payment_requests.status = 'pending'
    """)
    return cursor.fetchall()

def get_payment_history(telegram_id):
    user_id = get_user_id(telegram_id)
    cursor.execute("""
        SELECT amount, slots, status, timestamp 
        FROM payment_requests 
        WHERE user_id = ? 
        ORDER BY timestamp DESC 
        LIMIT 10
    """, (user_id,))
    return cursor.fetchall()

def get_payment_by_id(payment_id):
    cursor.execute("""
        SELECT payment_requests.*, users.telegram_id
        FROM payment_requests 
        JOIN users ON payment_requests.user_id = users.id
        WHERE payment_requests.id = ?
    """, (payment_id,))
    return cursor.fetchone()

def has_subscription(telegram_id, artist_id):
    cursor.execute("""
        SELECT COUNT(*) FROM subscriptions
        JOIN users ON subscriptions.user_id = users.id
        WHERE users.telegram_id = ? AND subscriptions.artist_id = ?
    """, (telegram_id, artist_id))
    count = cursor.fetchone()[0]
    return count > 0

# Инициализация базы данных при импорте
init_db()