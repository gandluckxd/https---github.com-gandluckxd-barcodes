"""
Клиентское приложение для системы учета готовности изделий
"""
import sys
import requests
import pyttsx3
import threading
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QTextEdit, QGroupBox, QMessageBox, QHeaderView
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QColor

import config


class TTSWorker(QObject):
    """Класс для работы с TTS в отдельном потоке"""
    
    def __init__(self):
        super().__init__()
        self.engine = None
        self.init_engine()
    
    def init_engine(self):
        """Инициализация TTS движка"""
        try:
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', config.TTS_RATE)
            self.engine.setProperty('volume', config.TTS_VOLUME)
            
            # Пытаемся установить русский голос
            voices = self.engine.getProperty('voices')
            for voice in voices:
                if 'ru' in voice.languages or 'russian' in voice.name.lower():
                    self.engine.setProperty('voice', voice.id)
                    break
        except Exception as e:
            print(f"Ошибка инициализации TTS: {e}")
            self.engine = None
    
    def speak(self, text):
        """Озвучить текст"""
        if self.engine:
            try:
                self.engine.say(text)
                self.engine.runAndWait()
            except Exception as e:
                print(f"Ошибка озвучивания: {e}")


class BarcodeApp(QMainWindow):
    """Главное окно приложения"""
    
    # Сигнал для обновления UI из другого потока
    update_ui_signal = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        
        # TTS Worker
        self.tts_worker = TTSWorker()
        
        # История сканирований
        self.scan_history = []
        
        # Статистика
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'already_approved': 0
        }
        
        self.init_ui()
        
        # Проверка подключения к API при старте
        QTimer.singleShot(500, self.check_api_connection)
    
    def init_ui(self):
        """Инициализация UI"""
        self.setWindowTitle(config.WINDOW_TITLE)
        self.setGeometry(100, 100, config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
        
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Основной layout
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # === Заголовок ===
        title_label = QLabel("📦 Система учета готовности изделий")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # === Статус подключения ===
        self.connection_status = QLabel("🔴 Проверка подключения...")
        self.connection_status.setAlignment(Qt.AlignCenter)
        status_font = QFont()
        status_font.setPointSize(10)
        self.connection_status.setFont(status_font)
        main_layout.addWidget(self.connection_status)
        
        # === Ввод штрихкода ===
        barcode_group = QGroupBox("Ввод штрихкода")
        barcode_layout = QHBoxLayout()
        barcode_group.setLayout(barcode_layout)
        
        barcode_label = QLabel("Штрихкод:")
        barcode_label.setMinimumWidth(100)
        barcode_layout.addWidget(barcode_label)
        
        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("Отсканируйте штрихкод или введите вручную...")
        self.barcode_input.returnPressed.connect(self.process_barcode)
        barcode_font = QFont()
        barcode_font.setPointSize(14)
        self.barcode_input.setFont(barcode_font)
        self.barcode_input.setMinimumHeight(40)
        barcode_layout.addWidget(self.barcode_input)
        
        process_btn = QPushButton("Обработать")
        process_btn.clicked.connect(self.process_barcode)
        process_btn.setMinimumHeight(40)
        process_btn.setMinimumWidth(120)
        btn_font = QFont()
        btn_font.setPointSize(12)
        btn_font.setBold(True)
        process_btn.setFont(btn_font)
        barcode_layout.addWidget(process_btn)
        
        main_layout.addWidget(barcode_group)
        
        # === Статистика ===
        stats_group = QGroupBox("Статистика")
        stats_layout = QHBoxLayout()
        stats_group.setLayout(stats_layout)
        
        self.stats_label = QLabel(self.get_stats_text())
        self.stats_label.setAlignment(Qt.AlignCenter)
        stats_font = QFont()
        stats_font.setPointSize(11)
        self.stats_label.setFont(stats_font)
        stats_layout.addWidget(self.stats_label)
        
        main_layout.addWidget(stats_group)
        
        # === История сканирований ===
        history_group = QGroupBox("История сканирований")
        history_layout = QVBoxLayout()
        history_group.setLayout(history_layout)
        
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(7)
        self.history_table.setHorizontalHeaderLabels([
            "Время", "Статус", "Заказ", "Конструкция", "Изделие №", "Размеры", "Сообщение"
        ])
        
        # Настройка таблицы
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        history_layout.addWidget(self.history_table)
        
        main_layout.addWidget(history_group)
        
        # Устанавливаем фокус на поле ввода
        self.barcode_input.setFocus()
    
    def get_stats_text(self):
        """Получить текст статистики"""
        return (f"Всего: {self.stats['total']} | "
                f"✅ Успешно: {self.stats['success']} | "
                f"⚠️ Уже приходовано: {self.stats['already_approved']} | "
                f"❌ Ошибок: {self.stats['failed']}")
    
    def check_api_connection(self):
        """Проверка подключения к API"""
        try:
            response = requests.get(
                f"{config.API_BASE_URL}{config.API_HEALTH_ENDPOINT}",
                timeout=3
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('database_connected'):
                    self.connection_status.setText("🟢 Подключено к API и БД")
                    self.connection_status.setStyleSheet("color: green;")
                else:
                    self.connection_status.setText("🟡 API доступен, но БД не подключена")
                    self.connection_status.setStyleSheet("color: orange;")
            else:
                self.connection_status.setText("🔴 API недоступен")
                self.connection_status.setStyleSheet("color: red;")
        except Exception as e:
            self.connection_status.setText(f"🔴 Ошибка подключения: {str(e)}")
            self.connection_status.setStyleSheet("color: red;")
    
    def process_barcode(self):
        """Обработка штрихкода"""
        barcode = self.barcode_input.text().strip()
        
        if not barcode:
            return
        
        # Очищаем поле ввода
        self.barcode_input.clear()
        
        # Обновляем статистику
        self.stats['total'] += 1
        
        try:
            # Отправляем запрос к API
            response = requests.post(
                f"{config.API_BASE_URL}{config.API_PROCESS_BARCODE_ENDPOINT}",
                json={"barcode": barcode},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.handle_response(data, barcode)
            else:
                self.handle_error(f"HTTP ошибка {response.status_code}", barcode)
                
        except requests.exceptions.Timeout:
            self.handle_error("Превышено время ожидания", barcode)
        except requests.exceptions.ConnectionError:
            self.handle_error("Ошибка подключения к серверу", barcode)
        except Exception as e:
            self.handle_error(f"Ошибка: {str(e)}", barcode)
        
        # Обновляем статистику
        self.stats_label.setText(self.get_stats_text())
        
        # Устанавливаем фокус обратно на поле ввода
        self.barcode_input.setFocus()
    
    def handle_response(self, data, barcode):
        """Обработка успешного ответа от API"""
        success = data.get('success', False)
        message = data.get('message', '')
        voice_message = data.get('voice_message', '')
        product_info = data.get('product_info')
        
        if success:
            self.stats['success'] += 1
            status = "✅ Успех"
            status_color = QColor(0, 200, 0)
        else:
            # Проверяем, это уже приходованное изделие или ошибка
            if "уже было отмечено готовым" in message.lower():
                self.stats['already_approved'] += 1
                status = "⚠️ Уже приходовано"
                status_color = QColor(255, 165, 0)
            else:
                self.stats['failed'] += 1
                status = "❌ Ошибка"
                status_color = QColor(255, 0, 0)
        
        # Добавляем в историю
        self.add_to_history(
            status=status,
            status_color=status_color,
            message=message,
            product_info=product_info
        )
        
        # Озвучиваем результат в отдельном потоке
        if voice_message:
            threading.Thread(
                target=self.tts_worker.speak,
                args=(voice_message,),
                daemon=True
            ).start()
    
    def handle_error(self, error_message, barcode):
        """Обработка ошибки"""
        self.stats['failed'] += 1
        
        self.add_to_history(
            status="❌ Ошибка",
            status_color=QColor(255, 0, 0),
            message=error_message,
            product_info=None
        )
        
        # Озвучиваем ошибку
        threading.Thread(
            target=self.tts_worker.speak,
            args=("Ошибка подключения к серверу",),
            daemon=True
        ).start()
    
    def add_to_history(self, status, status_color, message, product_info):
        """Добавить запись в историю"""
        current_time = datetime.now().strftime("%H:%M:%S")
        
        row_position = self.history_table.rowCount()
        self.history_table.insertRow(0)  # Добавляем в начало
        
        # Время
        time_item = QTableWidgetItem(current_time)
        self.history_table.setItem(0, 0, time_item)
        
        # Статус
        status_item = QTableWidgetItem(status)
        status_item.setForeground(status_color)
        font = QFont()
        font.setBold(True)
        status_item.setFont(font)
        self.history_table.setItem(0, 1, status_item)
        
        if product_info:
            # Заказ
            self.history_table.setItem(0, 2, QTableWidgetItem(product_info.get('order_number', '')))
            
            # Конструкция
            self.history_table.setItem(0, 3, QTableWidgetItem(product_info.get('construction_number', '')))
            
            # Изделие №
            item_num = f"{product_info.get('item_number', '')} / {product_info.get('qty', '')}"
            self.history_table.setItem(0, 4, QTableWidgetItem(item_num))
            
            # Размеры
            width = product_info.get('width', 0)
            height = product_info.get('height', 0)
            if width and height:
                size_str = f"{width} x {height}"
            else:
                size_str = "-"
            self.history_table.setItem(0, 5, QTableWidgetItem(size_str))
        else:
            self.history_table.setItem(0, 2, QTableWidgetItem("-"))
            self.history_table.setItem(0, 3, QTableWidgetItem("-"))
            self.history_table.setItem(0, 4, QTableWidgetItem("-"))
            self.history_table.setItem(0, 5, QTableWidgetItem("-"))
        
        # Сообщение
        self.history_table.setItem(0, 6, QTableWidgetItem(message))
        
        # Ограничиваем историю до 100 записей
        if self.history_table.rowCount() > 100:
            self.history_table.removeRow(100)


def main():
    """Точка входа в приложение"""
    app = QApplication(sys.argv)
    
    # Устанавливаем стиль приложения
    app.setStyle('Fusion')
    
    window = BarcodeApp()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()

