"""
Модуль для работы с базой данных Firebird
"""
import fdb
from contextlib import contextmanager
from config import settings


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
            connection = fdb.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                charset=self.charset
            )
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

