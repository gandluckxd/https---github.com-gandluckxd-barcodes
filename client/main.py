"""
Клиентское приложение для системы учета готовности изделий
"""
import sys
import os
import requests
import threading
from datetime import datetime
import pygame
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QGroupBox, QHeaderView
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QColor, QIcon, QPixmap, QImage
from PIL import Image, ImageDraw, ImageFont
import ctypes

import config


def set_windows_appid():
    """Устанавливает AppUserModelID для Windows для правильного отображения иконки в панели задач"""
    try:
        # Устанавливаем уникальный ID приложения для Windows 7+
        app_id = 'VKCompany.BarcodeApp.ProductTracking.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception as e:
        print(f"Не удалось установить AppUserModelID: {e}")


def create_emoji_icon():
    """Создает иконку с emoji для приложения"""
    try:
        # Создаем изображение с emoji
        size = 256
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # Пытаемся использовать системный шрифт с поддержкой emoji
        try:
            # Для Windows используем Segoe UI Emoji
            font = ImageFont.truetype("seguiemj.ttf", size - 40)
        except (OSError, IOError):
            try:
                # Альтернативный шрифт для Windows
                font = ImageFont.truetype("arial.ttf", size - 40)
            except (OSError, IOError):
                # Если не найден, используем стандартный
                font = ImageFont.load_default()
        
        # Рисуем emoji в центре
        emoji = "📦"
        
        # Получаем размер текста для центрирования
        bbox = draw.textbbox((0, 0), emoji, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        position = ((size - text_width) // 2 - bbox[0], 
                   (size - text_height) // 2 - bbox[1])
        
        draw.text(position, emoji, font=font, embedded_color=True)
        
        # Конвертируем в QPixmap
        image_bytes = image.tobytes("raw", "RGBA")
        qimage = QImage(image_bytes, size, size, QImage.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimage)
        
        return QIcon(pixmap)
    except Exception as e:
        print(f"Ошибка создания иконки: {e}")
        return None


class SoundPlayer(QObject):
    """Класс для воспроизведения звуковых уведомлений"""

    def __init__(self):
        super().__init__()
        self.audio_available = False
        self.sounds = {}
        self.init_engine()

    def init_engine(self):
        """Инициализация pygame mixer и загрузка звуков"""
        try:
            # Пытаемся инициализировать pygame mixer с разными настройками
            try:
                # Стандартная инициализация
                pygame.mixer.init()
                print("Pygame mixer инициализирован успешно (стандартный режим)")
                self.audio_available = True
            except Exception as e:
                print(f"Ошибка стандартной инициализации pygame mixer: {e}")
                try:
                    # Пробуем с явными параметрами (низкая частота)
                    pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
                    print("Pygame mixer инициализирован успешно (режим 22050Hz)")
                    self.audio_available = True
                except Exception as e2:
                    print(f"Ошибка инициализации с параметрами 22050Hz: {e2}")
                    try:
                        # Пробуем с минимальными параметрами (моно)
                        pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=4096)
                        print("Pygame mixer инициализирован успешно (режим 44100Hz mono)")
                        self.audio_available = True
                    except Exception as e3:
                        print(f"Не удалось инициализировать pygame mixer: {e3}")
                        print("Звуковые уведомления будут отключены")
                        self.audio_available = False

            # Загружаем звуковые файлы
            if self.audio_available:
                self.load_sounds()

        except Exception as e:
            print(f"Критическая ошибка инициализации звука: {e}")
            self.audio_available = False

    def load_sounds(self):
        """Загрузка звуковых файлов"""
        try:
            # Определяем путь к папке sounds
            if getattr(sys, 'frozen', False):
                # Если приложение скомпилировано
                base_path = sys._MEIPASS
            else:
                # Если запускается как скрипт
                base_path = os.path.dirname(os.path.abspath(__file__))

            sounds_dir = os.path.join(base_path, 'sounds')

            # Загружаем звуки
            sound_files = {
                'success': 'success.mp3',
                'already_approved': 'warning.mp3',
                'error': 'error.mp3'
            }

            for sound_name, filename in sound_files.items():
                sound_path = os.path.join(sounds_dir, filename)
                if os.path.exists(sound_path):
                    self.sounds[sound_name] = pygame.mixer.Sound(sound_path)
                    print(f"Загружен звук: {sound_name} ({filename})")
                else:
                    print(f"Звуковой файл не найден: {sound_path}")

            if not self.sounds:
                print("Не удалось загрузить ни одного звукового файла")
                self.audio_available = False

        except Exception as e:
            print(f"Ошибка загрузки звуков: {e}")
            self.audio_available = False

    def play_sound(self, sound_type):
        """Воспроизвести звук определенного типа

        Args:
            sound_type: 'success', 'already_approved', или 'error'
        """
        # Проверяем доступность аудио
        if not self.audio_available:
            print(f"Аудио недоступно, пропускаем воспроизведение: {sound_type}")
            return

        try:
            if sound_type in self.sounds:
                self.sounds[sound_type].play()
            else:
                print(f"Звук '{sound_type}' не найден")
        except Exception as e:
            print(f"Ошибка воспроизведения звука: {e}")
            # При ошибке отключаем аудио, чтобы не пытаться повторять
            self.audio_available = False


class BarcodeApp(QMainWindow):
    """Главное окно приложения"""
    
    # Сигнал для обновления UI из другого потока
    update_ui_signal = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()

        # Sound Player
        self.sound_player = SoundPlayer()

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
        title_font.setPointSize(42)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # === Статус подключения ===
        self.connection_status = QLabel("🔴 Проверка подключения...")
        self.connection_status.setAlignment(Qt.AlignCenter)
        status_font = QFont()
        status_font.setPointSize(24)
        status_font.setBold(True)
        self.connection_status.setFont(status_font)
        main_layout.addWidget(self.connection_status)
        
        # === Ввод штрихкода ===
        barcode_group = QGroupBox("Ввод штрихкода")
        group_font = QFont()
        group_font.setPointSize(24)
        group_font.setBold(True)
        barcode_group.setFont(group_font)
        barcode_layout = QHBoxLayout()
        barcode_group.setLayout(barcode_layout)

        barcode_label = QLabel("Штрихкод:")
        barcode_label.setMinimumWidth(270)
        label_font = QFont()
        label_font.setPointSize(27)
        label_font.setBold(True)
        barcode_label.setFont(label_font)
        barcode_layout.addWidget(barcode_label)

        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("Отсканируйте штрихкод или введите вручную...")
        self.barcode_input.returnPressed.connect(self.process_barcode)
        barcode_font = QFont()
        barcode_font.setPointSize(30)
        self.barcode_input.setFont(barcode_font)
        self.barcode_input.setMinimumHeight(90)
        barcode_layout.addWidget(self.barcode_input)

        process_btn = QPushButton("Обработать")
        process_btn.clicked.connect(self.process_barcode)
        process_btn.setMinimumHeight(90)
        process_btn.setMinimumWidth(300)
        btn_font = QFont()
        btn_font.setPointSize(27)
        btn_font.setBold(True)
        process_btn.setFont(btn_font)
        # Отключаем возможность установки фокуса на кнопку
        process_btn.setFocusPolicy(Qt.NoFocus)
        barcode_layout.addWidget(process_btn)
        
        main_layout.addWidget(barcode_group)
        
        # === Статистика ===
        stats_group = QGroupBox("Статистика")
        stats_group_font = QFont()
        stats_group_font.setPointSize(24)
        stats_group_font.setBold(True)
        stats_group.setFont(stats_group_font)
        stats_layout = QHBoxLayout()
        stats_group.setLayout(stats_layout)

        self.stats_label = QLabel(self.get_stats_text())
        self.stats_label.setAlignment(Qt.AlignCenter)
        stats_font = QFont()
        stats_font.setPointSize(24)
        stats_font.setBold(True)
        self.stats_label.setFont(stats_font)
        stats_layout.addWidget(self.stats_label)
        
        main_layout.addWidget(stats_group)
        
        # === История сканирований ===
        history_group = QGroupBox("История сканирований")
        history_group_font = QFont()
        history_group_font.setPointSize(24)
        history_group_font.setBold(True)
        history_group.setFont(history_group_font)
        history_layout = QVBoxLayout()
        history_group.setLayout(history_layout)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(9)
        self.history_table.setHorizontalHeaderLabels([
            "Статус", "Штрихкод", "Заказ", "Изделие", "Номер №", "Размеры", "Кол-во в заказе", "Кол-во готово", "Время"
        ])

        # Увеличиваем шрифт таблицы
        table_font = QFont()
        table_font.setPointSize(19)
        self.history_table.setFont(table_font)

        # Увеличиваем шрифт заголовков
        header = self.history_table.horizontalHeader()
        header_font = QFont()
        header_font.setPointSize(21)
        header_font.setBold(True)
        header.setFont(header_font)
        
        # Настройка таблицы - автоматическое определение ширины для всех колонок
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Статус
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Штрихкод
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Заказ
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Изделие
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Номер №
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Размеры
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Кол-во в заказе
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)  # Кол-во готово
        header.setSectionResizeMode(8, QHeaderView.ResizeToContents)  # Время
        
        # Увеличиваем высоту строк
        self.history_table.verticalHeader().setDefaultSectionSize(60)
        
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        # Отключаем возможность установки фокуса на таблицу
        self.history_table.setFocusPolicy(Qt.NoFocus)

        history_layout.addWidget(self.history_table)
        
        main_layout.addWidget(history_group)
        
        # Устанавливаем фокус на поле ввода
        self.barcode_input.setFocus()

    def mousePressEvent(self, event):
        """Обработка клика мыши - возвращаем фокус на поле ввода"""
        super().mousePressEvent(event)
        self.barcode_input.setFocus()
    
    def get_stats_text(self):
        """Получить текст статистики"""
        return (f"Всего: {self.stats['total']} | "
                f"✅ Успешно: {self.stats['success']} | "
                f"⚠️ Уже оприходовано: {self.stats['already_approved']} | "
                f"❌ Ошибок: {self.stats['failed']}")
    
    def check_api_connection(self):
        """Проверка подключения к API"""
        try:
            url = f"{config.API_BASE_URL}{config.API_HEALTH_ENDPOINT}"
            print(f"Проверка подключения к API: {url}")

            response = requests.get(url, timeout=15)
            print(f"Ответ от API: status_code={response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"Данные от API: {data}")

                if data.get('database_connected'):
                    self.connection_status.setText("🟢 Программа готова к работе")
                    self.connection_status.setStyleSheet("color: green;")
                    print("✓ API и база данных работают")
                else:
                    self.connection_status.setText("🔴 Ошибка подключения к БД")
                    self.connection_status.setStyleSheet("color: red;")
                    print("✗ API работает, но нет подключения к БД")
            else:
                self.connection_status.setText("🔴 Ошибка подключения")
                self.connection_status.setStyleSheet("color: red;")
                print(f"✗ API вернул ошибку: {response.status_code}")
        except requests.exceptions.ConnectionError as e:
            self.connection_status.setText("🔴 API сервер недоступен")
            self.connection_status.setStyleSheet("color: red;")
            print(f"✗ Не удалось подключиться к API: {e}")
        except Exception as e:
            self.connection_status.setText("🔴 Ошибка подключения")
            self.connection_status.setStyleSheet("color: red;")
            print(f"✗ Ошибка проверки подключения: {type(e).__name__}: {e}")
    
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
                status = "⚠️ Уже оприходовано"
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
            product_info=product_info,
            barcode=barcode
        )

        # Воспроизводим соответствующий звук в отдельном потоке
        if success:
            sound_type = 'success'
        elif "уже было отмечено готовым" in message.lower():
            sound_type = 'already_approved'
        else:
            sound_type = 'error'

        threading.Thread(
            target=self.sound_player.play_sound,
            args=(sound_type,),
            daemon=True
        ).start()
    
    def handle_error(self, error_message, barcode):
        """Обработка ошибки"""
        self.stats['failed'] += 1
        
        self.add_to_history(
            status="❌ Ошибка",
            status_color=QColor(255, 0, 0),
            message=error_message,
            product_info=None,
            barcode=barcode
        )

        # Воспроизводим звук ошибки
        threading.Thread(
            target=self.sound_player.play_sound,
            args=('error',),
            daemon=True
        ).start()
    
    def add_to_history(self, status, status_color, message, product_info, barcode=""):
        """Добавить запись в историю"""
        current_time = datetime.now().strftime("%H:%M:%S")

        self.history_table.insertRow(0)  # Добавляем в начало

        # Порядок столбцов: "Статус", "Штрихкод", "Заказ", "Изделие", "Номер №", "Размеры", "Кол-во в заказе", "Кол-во готово", "Время"

        # Статус (колонка 0)
        status_item = QTableWidgetItem(status)
        status_item.setForeground(status_color)
        font = QFont()
        font.setPointSize(19)
        font.setBold(True)
        status_item.setFont(font)
        self.history_table.setItem(0, 0, status_item)

        # Штрихкод (колонка 1)
        self.history_table.setItem(0, 1, QTableWidgetItem(barcode))

        if product_info:
            # Заказ (колонка 2)
            self.history_table.setItem(0, 2, QTableWidgetItem(product_info.get('order_number', '')))

            # Изделие (колонка 3)
            self.history_table.setItem(0, 3, QTableWidgetItem(product_info.get('construction_number', '')))

            # Номер № (колонка 4)
            item_num = f"{product_info.get('item_number', '')} / {product_info.get('qty', '')}"
            self.history_table.setItem(0, 4, QTableWidgetItem(item_num))

            # Размеры (колонка 5)
            width = product_info.get('width', 0)
            height = product_info.get('height', 0)
            if width and height:
                size_str = f"{width} x {height}"
            else:
                size_str = "-"
            self.history_table.setItem(0, 5, QTableWidgetItem(size_str))

            # Кол-во изделий в заказе (колонка 6)
            total_items = product_info.get('total_items_in_order')
            self.history_table.setItem(0, 6, QTableWidgetItem(str(total_items) if total_items is not None else "-"))

            # Проведено изделий в заказе (колонка 7)
            approved_items = product_info.get('approved_items_in_order')
            self.history_table.setItem(0, 7, QTableWidgetItem(str(approved_items) if approved_items is not None else "-"))
        else:
            self.history_table.setItem(0, 2, QTableWidgetItem("-"))
            self.history_table.setItem(0, 3, QTableWidgetItem("-"))
            self.history_table.setItem(0, 4, QTableWidgetItem("-"))
            self.history_table.setItem(0, 5, QTableWidgetItem("-"))
            self.history_table.setItem(0, 6, QTableWidgetItem("-"))
            self.history_table.setItem(0, 7, QTableWidgetItem("-"))

        # Время (колонка 8)
        time_item = QTableWidgetItem(current_time)
        self.history_table.setItem(0, 8, time_item)

        # Ограничиваем историю до 100 записей
        if self.history_table.rowCount() > 100:
            self.history_table.removeRow(100)


def main():
    """Точка входа в приложение"""
    print("="*60)
    print("Запуск клиентского приложения...")
    print(f"API URL: {config.API_BASE_URL}")
    print(f"Python version: {sys.version}")
    print("="*60)

    # Устанавливаем AppUserModelID для Windows (до создания QApplication)
    set_windows_appid()

    app = QApplication(sys.argv)
    
    # Устанавливаем стиль приложения
    app.setStyle('Fusion')
    
    # Создаем иконку с emoji
    icon = create_emoji_icon()
    if icon:
        app.setWindowIcon(icon)
    
    # Создаем и отображаем главное окно
    window = BarcodeApp()
    if icon:
        window.setWindowIcon(icon)
    window.showMaximized()  # Открываем в полноэкранном режиме
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print("="*60)
        print("КРИТИЧЕСКАЯ ОШИБКА!")
        print(f"Тип ошибки: {type(e).__name__}")
        print(f"Сообщение: {str(e)}")
        print("="*60)
        import traceback
        traceback.print_exc()
        input("Нажмите Enter для выхода...")
        sys.exit(1)

