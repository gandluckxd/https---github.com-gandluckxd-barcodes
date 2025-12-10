"""
Конфигурация клиентского приложения
"""

# API Configuration
API_BASE_URL = "http://localhost:8015"
API_PROCESS_BARCODE_ENDPOINT = "/api/process-barcode"
API_HEALTH_ENDPOINT = "/"
API_DAILY_STATS_ENDPOINT = "/api/statistics/daily"
API_ORDER_STATS_ENDPOINT = "/api/statistics/orders"

# UI Configuration
WINDOW_TITLE = "Система учета готовности изделий"
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800

# TTS Configuration (Google TTS)
# Google TTS автоматически определяет оптимальную скорость и качество голоса

