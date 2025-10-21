"""
Конфигурация приложения
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки приложения"""
    
    # Database
    DB_HOST: str = "10.8.0.3"
    DB_PORT: int = 3050
    DB_DATABASE: str = "D:/altAwinDB/ppk.gdb"
    DB_USER: str = "sysdba"
    DB_PASSWORD: str = "masterkey"
    DB_CHARSET: str = "WIN1251"
    
    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8015
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

