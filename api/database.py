"""
Модуль для работы с базой данных Firebird
"""
import fdb
import os
import sys
from contextlib import contextmanager
from config import settings


def _candidate_fbclient_paths() -> list[str]:
    # Highest priority: explicit env/config path
    candidates: list[str] = []
    if settings.FBCLIENT_PATH:
        candidates.append(settings.FBCLIENT_PATH)

    base_dir = os.path.dirname(__file__)
    meipass = getattr(sys, "_MEIPASS", None)

    if sys.platform.startswith("win"):
        if meipass:
            candidates.append(os.path.join(meipass, "fbclient.dll"))
        candidates.append(os.path.join(base_dir, "fbclient.dll"))
    elif sys.platform == "darwin":
        # Common macOS locations for Firebird client
        candidates.extend(
            [
                os.path.join(base_dir, "libfbclient.dylib"),
                "/Library/Frameworks/Firebird.framework/Versions/A/Libraries/libfbclient.dylib",
                "/usr/local/lib/libfbclient.dylib",
            ]
        )
    else:
        # Linux and other *nix
        candidates.extend(
            [
                os.path.join(base_dir, "libfbclient.so"),
                "/usr/lib/libfbclient.so",
                "/usr/lib64/libfbclient.so",
                "/usr/local/lib/libfbclient.so",
            ]
        )

    # Keep only existing files, preserve order
    return [path for path in candidates if path and os.path.exists(path)]


def _load_fbclient() -> None:
    for path in _candidate_fbclient_paths():
        try:
            fdb.load_api(path)
            print(f"[OK] Firebird client library loaded from: {path}")
            return
        except Exception as exc:
            print(f"[WARNING] Failed to load Firebird client from: {path}")
            print(f"  {exc}")

    print("[WARNING] Firebird client library not found. Trying system default...")


_load_fbclient()


class Database:
    """Класс для работы с Firebird базой данных"""
    
    def __init__(self):
        self.host = settings.DB_HOST
        self.port = settings.DB_PORT
        self.database = settings.DB_DATABASE
        self.user = settings.DB_USER
        self.password = settings.DB_PASSWORD
        self.charset = settings.DB_CHARSET
    
    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для получения соединения с БД"""
        connection = None
        try:
            # Для Firebird используем формат: host/port:database
            dsn = f"{self.host}/{self.port}:{self.database}"

            print(f"Подключение к БД с DSN: {dsn}")
            print(f"Пользователь: {self.user}")
            print(f"Пароль: {'*' * len(self.password)}")

            connection = fdb.connect(
                dsn=dsn,
                user=self.user.upper(),  # Firebird чувствителен к регистру
                password=self.password,
                charset=self.charset
            )
            print("[OK] Соединение установлено")
            yield connection
        except Exception as e:
            if connection:
                connection.rollback()
            raise e
        finally:
            if connection:
                connection.close()
    
    def execute_query(self, query: str, params: tuple = None):
        """Выполнить SELECT запрос и вернуть результаты"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            # Получаем названия столбцов
            columns = [desc[0] for desc in cursor.description]
            
            # Получаем данные
            rows = cursor.fetchall()
            
            # Преобразуем в список словарей
            result = []
            for row in rows:
                result.append(dict(zip(columns, row)))
            
            return result
    
    def execute_update(self, query: str, params: tuple = None):
        """Выполнить UPDATE/INSERT запрос"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            conn.commit()
            return cursor.rowcount


# Глобальный экземпляр
db = Database()
