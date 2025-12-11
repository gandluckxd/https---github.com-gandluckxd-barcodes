"""
Модуль для работы с базой данных Firebird
"""
import fdb
import os
import sys
from contextlib import contextmanager
from config import settings

# Явно указываем путь к fbclient.dll
if hasattr(sys, '_MEIPASS'):
    # Если запущено из PyInstaller
    fbclient_path = os.path.join(sys._MEIPASS, 'fbclient.dll')
else:
    # Если запущено из исходников
    fbclient_path = os.path.join(os.path.dirname(__file__), 'fbclient.dll')

# Проверяем существование файла и устанавливаем путь
if os.path.exists(fbclient_path):
    fdb.load_api(fbclient_path)
    print(f"[OK] fbclient.dll загружена из: {fbclient_path}")
else:
    print(f"[WARNING] fbclient.dll не найдена по пути: {fbclient_path}")
    print("  Попытка использовать системную библиотеку...")


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

