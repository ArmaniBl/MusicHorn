import sqlite3
import logging

# Очищаем лог файл при запуске
with open("database.log", "w") as f:
    f.write("")

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="database.log",
    filemode='w'  # Добавляем режим 'w' для перезаписи файла
)
logger = logging.getLogger(__name__)
# Подключение к базе данных (файл database.db)
conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

# Создание таблиц
def migrate_db():
    try:
        # Проверяем существование старой таблицы и столбца telegram_id
        cursor.execute("PRAGMA table_info(users)")
        columns = cursor.fetchall()
        has_telegram_id = any(column[1] == 'telegram_id' for column in columns)
        
        if has_telegram_id:
            # Создаем временную таблицу с новой структурой
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER UNIQUE,
                    muted BOOLEAN DEFAULT FALSE,
                    vip_level INTEGER DEFAULT 0
                )
            """)
            
            # Копируем данные из старой таблицы в новую
            cursor.execute("""
                INSERT INTO users_new (id, chat_id, muted, vip_level)
                SELECT id, telegram_id, muted, vip_level FROM users
            """)
            
            # Удаляем старую таблицу
            cursor.execute("DROP TABLE users")
            
            # Переименовываем новую таблицу
            cursor.execute("ALTER TABLE users_new RENAME TO users")
            
            # Создаем индекс для chat_id
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_id ON users(chat_id)")
            
            conn.commit()
            logger.info("База данных успешно обновлена")
        else:
            # Если старой структуры нет, просто создаем новую таблицу
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER UNIQUE,
                    muted BOOLEAN DEFAULT FALSE,
                    vip_level INTEGER DEFAULT 0
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_id ON users(chat_id)")
            conn.commit()
            logger.info("Создана новая структура базы данных")
            
    except Exception as e:
        logger.error(f"Ошибка при миграции базы данных: {e}")
        conn.rollback()
        raise

def init_db():
    try:
        # Проверяем существование таблицы users
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cursor.fetchone():
            # Создаем таблицы с новой структурой
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER UNIQUE,
                    muted BOOLEAN DEFAULT FALSE,
                    vip_level INTEGER DEFAULT 0
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_id ON users(chat_id)")
        else:
            # Проверяем необходимость миграции
            cursor.execute("PRAGMA table_info(users)")
            columns = cursor.fetchall()
            if any(column[1] == 'telegram_id' for column in columns):
                logger.info("Обнаружена старая структура базы данных, выполняем миграцию...")
                migrate_db()
        
        # Создаем остальные таблицы
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
                subscription_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS releases_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artist_id TEXT,
                platform TEXT,
                release_id TEXT,
                release_type TEXT,
                release_date TEXT,
                UNIQUE(artist_id, platform, release_id)
            )
        """)
        
        # Проверяем, существует ли столбец subscription_date
        cursor.execute("PRAGMA table_info(subscriptions)")
        columns = cursor.fetchall()
        if not any(column[1] == 'subscription_date' for column in columns):
            # Создаем временную таблицу с новой структурой
            cursor.execute("""
                CREATE TABLE subscriptions_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    artist_id TEXT,
                    artist_name TEXT,
                    platform TEXT,
                    subscription_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            
            # Копируем данные из старой таблицы в новую
            cursor.execute("""
                INSERT INTO subscriptions_new (id, user_id, artist_id, artist_name, platform)
                SELECT id, user_id, artist_id, artist_name, platform FROM subscriptions
            """)
            
            # Обновляем subscription_date для существующих записей
            cursor.execute("""
                UPDATE subscriptions_new 
                SET subscription_date = CURRENT_TIMESTAMP
                WHERE subscription_date IS NULL
            """)
            
            # Удаляем старую таблицу
            cursor.execute("DROP TABLE subscriptions")
            
            # Переименовываем новую таблицу
            cursor.execute("ALTER TABLE subscriptions_new RENAME TO subscriptions")
            
            logger.info("Added subscription_date column to subscriptions table")
        
        conn.commit()
        logger.info("База данных инициализирована")
        
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
        conn.rollback()
        raise

# Добавление пользователя
def add_user(chat_id):
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO users (chat_id, muted, vip_level) VALUES (?, FALSE, 0)",
            (chat_id,)
        )
        conn.commit()
        logger.info(f"Added or updated user with chat_id: {chat_id}")
    except Exception as e:
        logger.error(f"Error in add_user: {e}")

def get_user_id(chat_id):
    try:
        cursor.execute("SELECT id FROM users WHERE chat_id = ?", (chat_id,))
        result = cursor.fetchone()
        if not result:
            # Если пользователь не найден, добавляем его
            add_user(chat_id)
            cursor.execute("SELECT id FROM users WHERE chat_id = ?", (chat_id,))
            result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Error in get_user_id: {e}")
        return None

# Добавление подписки
def add_subscription(chat_id, artist_id, artist_name, platform):
    logger.info(f"Попытка добавить подписку: chat_id={chat_id}, artist_name={artist_name}, platform={platform}")
    cursor.execute("SELECT id FROM users WHERE chat_id = ?", (chat_id,))
    user = cursor.fetchone()
    if not user:
        logger.info(f"Пользователь {chat_id} не найден, добавляем...")
        add_user(chat_id)
        cursor.execute("SELECT id FROM users WHERE chat_id = ?", (chat_id,))
        user = cursor.fetchone()

    user_id = user[0]
    cursor.execute("""
        INSERT INTO subscriptions 
        (user_id, artist_id, artist_name, platform, subscription_date) 
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (user_id, artist_id, artist_name, platform))
    conn.commit()
    logger.info(f"Подписка добавлена: user_id={user_id}, artist_name={artist_name}, platform={platform}")

# Получение подписок пользователя
def get_new_connection():
    return sqlite3.connect("database.db", check_same_thread=False)

def get_subscriptions(chat_id):
    try:
        # Создаем новое соединение для этого запроса
        local_conn = get_new_connection()
        local_cursor = local_conn.cursor()
        
        local_cursor.execute("""
            SELECT 
                subscriptions.artist_id, 
                subscriptions.artist_name, 
                subscriptions.platform,
                subscriptions.subscription_date
            FROM subscriptions
            JOIN users ON subscriptions.user_id = users.id
            WHERE users.chat_id = ?
        """, (chat_id,))
        
        result = local_cursor.fetchall()
        
        # Закрываем локальное соединение
        local_cursor.close()
        local_conn.close()
        
        return result
    except Exception as e:
        logger.error(f"Error in get_subscriptions: {e}")
        return []

def get_db():
    return conn, cursor

def remove_subscription(chat_id, artist_id=None, artist_name=None):
    try:
        logger.info(f"Starting subscription removal for chat_id={chat_id}, artist_id={artist_id}, artist_name={artist_name}")
        
        # Проверяем существование пользователя
        cursor.execute("SELECT id FROM users WHERE chat_id = ?", (chat_id,))
        user_result = cursor.fetchone()
        
        if not user_result:
            logger.warning(f"User not found for chat_id: {chat_id}")
            # Попробуем создать пользователя
            add_user(chat_id)
            cursor.execute("SELECT id FROM users WHERE chat_id = ?", (chat_id,))
            user_result = cursor.fetchone()
            if not user_result:
                logger.error("Failed to create user")
                return
        
        user_id = user_result[0]
        logger.info(f"Found user_id={user_id} for chat_id={chat_id}")
        
        # Проверяем существование подписки перед удалением
        if artist_id:
            cursor.execute("""
                SELECT COUNT(*) FROM subscriptions 
                WHERE user_id = ? AND artist_id = ?
            """, (user_id, artist_id))
            count = cursor.fetchone()[0]
            logger.info(f"Found {count} subscriptions for user_id={user_id} and artist_id={artist_id}")
            
            cursor.execute("""
                DELETE FROM subscriptions
                WHERE user_id = ? AND artist_id = ?
            """, (user_id, artist_id))
        elif artist_name:
            cursor.execute("""
                SELECT COUNT(*) FROM subscriptions 
                WHERE user_id = ? AND artist_name LIKE ?
            """, (user_id, artist_name))
            count = cursor.fetchone()[0]
            logger.info(f"Found {count} subscriptions for user_id={user_id} and artist_name={artist_name}")
            
            cursor.execute("""
                DELETE FROM subscriptions
                WHERE user_id = ? AND artist_name LIKE ?
            """, (user_id, artist_name))
        
        rows_affected = cursor.rowcount
        conn.commit()
        logger.info(f"Removed {rows_affected} subscriptions for user_id={user_id}, chat_id={chat_id}")
        
    except Exception as e:
        logger.error(f"Error removing subscription: {e}", exc_info=True)
        conn.rollback()
        raise

def mute_user(chat_id):
    cursor.execute("UPDATE users SET muted = TRUE WHERE chat_id = ?", (chat_id,))
    conn.commit()

def unmute_user(chat_id):
    cursor.execute("UPDATE users SET muted = FALSE WHERE chat_id = ?", (chat_id,))
    conn.commit()

def is_muted(chat_id):
    cursor.execute("SELECT muted FROM users WHERE chat_id = ?", (chat_id,))
    result = cursor.fetchone()
    return result[0] if result else False

def get_vip_level(chat_id):
    cursor.execute(
        "SELECT vip_level FROM users WHERE chat_id = ?",
        (chat_id,)
    )
    result = cursor.fetchone()
    return result[0] if result else 0

def get_max_subscriptions(chat_id):
    vip_level = get_vip_level(chat_id)
    return 5 + vip_level

def can_add_subscription(chat_id):
    current_subs = len(get_subscriptions(chat_id))
    max_subs = get_max_subscriptions(chat_id)
    return current_subs < max_subs

def set_vip_level(chat_id, level):
    cursor.execute(
        "UPDATE users SET vip_level = ? WHERE chat_id = ?",
        (level, chat_id)
    )
    conn.commit()

def get_transaction_history(chat_id):
    user_id = get_user_id(chat_id)
    cursor.execute("""
        SELECT amount, status, timestamp 
        FROM transactions 
        WHERE user_id = ? 
        ORDER BY timestamp DESC 
        LIMIT 10
    """, (user_id,))
    return cursor.fetchall()

def create_payment_request(chat_id, slots, amount):
    user_id = get_user_id(chat_id)
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
            users.chat_id,
            payment_requests.slots, 
            payment_requests.amount,
            payment_requests.timestamp,
            payment_requests.payment_info
        FROM payment_requests 
        JOIN users ON payment_requests.user_id = users.id
        WHERE payment_requests.status = 'pending'
    """)
    return cursor.fetchall()

def get_payment_history(chat_id):
    user_id = get_user_id(chat_id)
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
        SELECT payment_requests.*, users.chat_id
        FROM payment_requests 
        JOIN users ON payment_requests.user_id = users.id
        WHERE payment_requests.id = ?
    """, (payment_id,))
    return cursor.fetchone()

def has_subscription(chat_id, artist_id):
    try:
        logger.info(f"Checking subscription for chat_id={chat_id}, artist_id={artist_id}")
        cursor.execute("""
            SELECT COUNT(*) FROM subscriptions
            JOIN users ON subscriptions.user_id = users.id
            WHERE users.chat_id = ? AND subscriptions.artist_id = ?
        """, (chat_id, artist_id))
        count = cursor.fetchone()[0]
        logger.info(f"Found {count} subscriptions")
        return count > 0
    except Exception as e:
        logger.error(f"Error checking subscription: {e}", exc_info=True)
        return False

def add_release_to_history(artist_id, platform, release_id, release_type, release_date):
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO releases_history 
            (artist_id, platform, release_id, release_type, release_date)
            VALUES (?, ?, ?, ?, ?)
        """, (artist_id, platform, release_id, release_type, release_date))
        conn.commit()
        return cursor.rowcount > 0  # True если релиз новый
    except Exception as e:
        logger.error(f"Error adding release to history: {e}")
        return False

def update_subscription_date(chat_id, artist_id, release_date):
    try:
        # Получаем user_id
        cursor.execute("SELECT id FROM users WHERE chat_id = ?", (chat_id,))
        user = cursor.fetchone()
        if not user:
            logger.error(f"User not found for chat_id: {chat_id}")
            return False
            
        user_id = user[0]
        
        # Обновляем дату подписки
        cursor.execute("""
            UPDATE subscriptions 
            SET subscription_date = ? 
            WHERE user_id = ? AND artist_id = ?
        """, (release_date, user_id, artist_id))
        
        conn.commit()
        logger.info(f"Updated subscription date for artist {artist_id} to {release_date}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating subscription date: {e}")
        return False

# Инициализация базы данных при импорте
init_db()