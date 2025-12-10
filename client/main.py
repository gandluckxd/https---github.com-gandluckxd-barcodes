"""
Клиентское приложение для системы учета готовности изделий
"""
import sys
import os
import requests
import threading
from datetime import datetime, timedelta
import pygame
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QGroupBox, QHeaderView, QTabWidget, QMessageBox
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
    # Сигнал для обновления таблиц статистики
    update_stats_tables_signal = pyqtSignal(list, list)

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

        # Данные статистики
        self.daily_stats_data = []
        self.order_stats_data = []
        self.last_stats_update = None
        self.stats_loading = False

        self.init_ui()

        # Подключаем сигнал для обновления таблиц
        self.update_stats_tables_signal.connect(self.update_stats_tables)

        # Проверка подключения к API при старте
        QTimer.singleShot(500, self.check_api_connection)

        # Запускаем загрузку статистики в фоне сразу после старта
        QTimer.singleShot(1000, self.start_background_stats_loading)

        # Настраиваем таймер для автоматического обновления статистики каждые 5 минут
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.start_background_stats_loading)
        self.stats_timer.start(5 * 60 * 1000)  # 5 минут в миллисекундах
    
    def init_ui(self):
        """Инициализация UI с вкладками"""
        self.setWindowTitle(config.WINDOW_TITLE)
        self.setGeometry(100, 100, config.WINDOW_WIDTH, config.WINDOW_HEIGHT)

        # Создаем QTabWidget
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Настройка шрифта для вкладок
        tab_font = QFont()
        tab_font.setPointSize(18)
        tab_font.setBold(True)
        self.tabs.setFont(tab_font)

        # Создаем вкладки
        main_tab = self.create_main_tab()
        stats_tab = self.create_stats_tab()

        # Добавляем вкладки
        self.tabs.addTab(main_tab, "Главное меню")
        self.tabs.addTab(stats_tab, "Статистика")

        # Подключаем обработчик переключения вкладок
        self.tabs.currentChanged.connect(self.on_tab_changed)

        # Устанавливаем фокус на поле ввода
        self.barcode_input.setFocus()

    def create_main_tab(self):
        """Создание главной вкладки с основным функционалом"""
        tab = QWidget()
        main_layout = QVBoxLayout()
        tab.setLayout(main_layout)

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

        return tab

    def create_stats_tab(self):
        """Создание вкладки со статистикой производства"""
        tab = QWidget()
        main_layout = QVBoxLayout()
        tab.setLayout(main_layout)

        # === Заголовок ===
        title_label = QLabel("📊 Статистика производства")
        title_font = QFont()
        title_font.setPointSize(36)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # === Информация о периоде ===
        period_label = QLabel("Отображается период: 2 дня назад - 5 дней вперёд")
        period_font = QFont()
        period_font.setPointSize(18)
        period_label.setFont(period_font)
        period_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(period_label)

        # === Метка последнего обновления ===
        self.last_update_label = QLabel("Загрузка данных...")
        update_font = QFont()
        update_font.setPointSize(16)
        update_font.setItalic(True)
        self.last_update_label.setFont(update_font)
        self.last_update_label.setAlignment(Qt.AlignCenter)
        self.last_update_label.setStyleSheet("color: gray;")
        main_layout.addWidget(self.last_update_label)

        # === Кнопка обновления ===
        refresh_btn = QPushButton("🔄 Обновить статистику")
        refresh_btn.clicked.connect(self.start_background_stats_loading)
        refresh_btn.setMinimumHeight(60)
        btn_font = QFont()
        btn_font.setPointSize(20)
        btn_font.setBold(True)
        refresh_btn.setFont(btn_font)
        refresh_btn.setFocusPolicy(Qt.NoFocus)
        main_layout.addWidget(refresh_btn)

        # === Общая статистика по дням ===
        daily_group = QGroupBox("Общая статистика по дням")
        daily_group_font = QFont()
        daily_group_font.setPointSize(22)
        daily_group_font.setBold(True)
        daily_group.setFont(daily_group_font)
        daily_layout = QVBoxLayout()
        daily_group.setLayout(daily_layout)

        self.daily_stats_table = QTableWidget()
        self.daily_stats_table.setColumnCount(7)
        self.daily_stats_table.setHorizontalHeaderLabels([
            "Дата", "План ПВХ", "Сделано ПВХ", "План Раздвижки", "Сделано Раздвижки", "План Итого", "Сделано Итого"
        ])

        # Настройка шрифтов таблицы
        table_font = QFont()
        table_font.setPointSize(17)
        self.daily_stats_table.setFont(table_font)

        header = self.daily_stats_table.horizontalHeader()
        header_font = QFont()
        header_font.setPointSize(19)
        header_font.setBold(True)
        header.setFont(header_font)

        # Автоматический размер колонок
        for i in range(7):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        self.daily_stats_table.verticalHeader().setDefaultSectionSize(55)
        self.daily_stats_table.setAlternatingRowColors(True)
        self.daily_stats_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.daily_stats_table.setFocusPolicy(Qt.NoFocus)

        daily_layout.addWidget(self.daily_stats_table)
        main_layout.addWidget(daily_group)

        # === Детальная статистика по заказам ===
        order_group = QGroupBox("Детальная статистика по заказам")
        order_group_font = QFont()
        order_group_font.setPointSize(22)
        order_group_font.setBold(True)
        order_group.setFont(order_group_font)
        order_layout = QVBoxLayout()
        order_group.setLayout(order_layout)

        self.order_stats_table = QTableWidget()
        self.order_stats_table.setColumnCount(7)
        self.order_stats_table.setHorizontalHeaderLabels([
            "Номер заказа", "Дата производства", "План ПВХ", "Сделано ПВХ",
            "План Раздвижки", "Сделано Раздвижки", "Комментарий"
        ])

        # Настройка шрифтов таблицы
        self.order_stats_table.setFont(table_font)

        header2 = self.order_stats_table.horizontalHeader()
        header2.setFont(header_font)

        # Автоматический размер колонок
        for i in range(7):
            header2.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        self.order_stats_table.verticalHeader().setDefaultSectionSize(55)
        self.order_stats_table.setAlternatingRowColors(True)
        self.order_stats_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.order_stats_table.setFocusPolicy(Qt.NoFocus)

        order_layout.addWidget(self.order_stats_table)
        main_layout.addWidget(order_group)

        return tab

    def on_tab_changed(self, index):
        """Обработчик переключения вкладок"""
        if index == 1:  # Вкладка "Статистика"
            # Принудительно обновляем таблицы из кеша
            self.update_stats_tables(self.daily_stats_data, self.order_stats_data)
        elif index == 0:  # Вкладка "Главное меню"
            self.barcode_input.setFocus()

    def start_background_stats_loading(self):
        """Запуск фоновой загрузки статистики"""
        if self.stats_loading:
            print("Загрузка статистики уже выполняется, пропускаем...")
            return

        self.stats_loading = True

        # Обновляем метку сразу же
        self.last_update_label.setText("Идет загрузка данных...")
        self.last_update_label.setStyleSheet("color: orange;")

        # Запускаем загрузку в отдельном потоке
        thread = threading.Thread(target=self.load_statistics_background, daemon=True)
        thread.start()

    def load_statistics_background(self):
        """Загрузка статистики в фоновом режиме"""
        try:
            # Рассчитываем даты: 2 дня назад - 5 дней вперёд
            today = datetime.now()
            start_date = (today - timedelta(days=2)).strftime('%Y-%m-%d')
            end_date = (today + timedelta(days=5)).strftime('%Y-%m-%d')

            # Загрузка общей статистики по дням
            daily_url = f"{config.API_BASE_URL}{config.API_DAILY_STATS_ENDPOINT}"
            daily_params = {'start_date': start_date, 'end_date': end_date}

            daily_response = requests.get(daily_url, params=daily_params, timeout=10)
            daily_data = []
            if daily_response.status_code == 200:
                daily_json = daily_response.json()
                if daily_json.get('success'):
                    daily_data = daily_json.get('data', [])

            # Загрузка детальной статистики по заказам
            order_url = f"{config.API_BASE_URL}{config.API_ORDER_STATS_ENDPOINT}"
            order_params = {'start_date': start_date, 'end_date': end_date}

            order_response = requests.get(order_url, params=order_params, timeout=10)
            order_data = []
            if order_response.status_code == 200:
                order_json = order_response.json()
                if order_json.get('success'):
                    order_data = order_json.get('data', [])

            # Сохраняем данные и время обновления
            self.daily_stats_data = daily_data
            self.order_stats_data = order_data
            self.last_stats_update = datetime.now()

            # Отправляем сигнал для обновления UI
            self.update_stats_tables_signal.emit(daily_data, order_data)

        except Exception as e:
            print(f"Ошибка фоновой загрузки статистики: {e}")
        finally:
            self.stats_loading = False

    def update_stats_tables(self, daily_data, order_data):
        """Обновление таблиц статистики в главном потоке"""
        # Обновляем метку последнего обновления
        if self.last_stats_update:
            time_str = self.last_stats_update.strftime('%d.%m.%Y %H:%M:%S')
            self.last_update_label.setText(f"Последнее обновление: {time_str}")
            self.last_update_label.setStyleSheet("color: green;")
        elif self.stats_loading:
            self.last_update_label.setText("Загрузка данных...")
            self.last_update_label.setStyleSheet("color: orange;")
        else:
            self.last_update_label.setText("Данные не загружены")
            self.last_update_label.setStyleSheet("color: gray;")

        # Заполняем таблицы
        self.populate_daily_stats_table(daily_data)
        self.populate_order_stats_table(order_data)

    def populate_daily_stats_table(self, data):
        """Заполнение таблицы общей статистики"""
        self.daily_stats_table.setRowCount(0)

        for row_data in data:
            row_position = self.daily_stats_table.rowCount()
            self.daily_stats_table.insertRow(row_position)

            # Дата (форматируем в день.месяц.год)
            proddate = row_data['proddate']
            try:
                # Пробуем распарсить дату
                if isinstance(proddate, str):
                    date_obj = datetime.strptime(proddate, '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%d.%m.%Y')
                else:
                    formatted_date = proddate
            except:
                formatted_date = proddate

            self.daily_stats_table.setItem(row_position, 0, QTableWidgetItem(formatted_date))

            # План ПВХ (колонка 1)
            planned_pvh = row_data['planned_pvh']
            self.daily_stats_table.setItem(row_position, 1, QTableWidgetItem(str(planned_pvh)))

            # Сделано ПВХ (колонка 2) с цветовой индикацией
            completed_pvh = row_data['completed_pvh']
            completed_pvh_item = QTableWidgetItem(str(completed_pvh))
            if planned_pvh > 0:
                if completed_pvh >= planned_pvh:
                    completed_pvh_item.setForeground(QColor(0, 200, 0))  # Зеленый
                elif completed_pvh > 0:
                    completed_pvh_item.setForeground(QColor(255, 165, 0))  # Оранжевый
            self.daily_stats_table.setItem(row_position, 2, completed_pvh_item)

            # План Раздвижки (колонка 3)
            planned_razdv = row_data['planned_razdv']
            self.daily_stats_table.setItem(row_position, 3, QTableWidgetItem(str(planned_razdv)))

            # Сделано Раздвижки (колонка 4) с цветовой индикацией
            completed_razdv = row_data['completed_razdv']
            completed_razdv_item = QTableWidgetItem(str(completed_razdv))
            if planned_razdv > 0:
                if completed_razdv >= planned_razdv:
                    completed_razdv_item.setForeground(QColor(0, 200, 0))  # Зеленый
                elif completed_razdv > 0:
                    completed_razdv_item.setForeground(QColor(255, 165, 0))  # Оранжевый
            self.daily_stats_table.setItem(row_position, 4, completed_razdv_item)

            # Итого План (колонка 5) - сумма ПВХ и Раздвижки
            total_planned = planned_pvh + planned_razdv
            self.daily_stats_table.setItem(row_position, 5, QTableWidgetItem(str(total_planned)))

            # Итого Сделано (колонка 6) - сумма ПВХ и Раздвижки с цветовой индикацией
            total_completed = completed_pvh + completed_razdv
            total_completed_item = QTableWidgetItem(str(total_completed))
            if total_planned > 0:
                if total_completed >= total_planned:
                    total_completed_item.setForeground(QColor(0, 200, 0))  # Зеленый
                elif total_completed > 0:
                    total_completed_item.setForeground(QColor(255, 165, 0))  # Оранжевый
            self.daily_stats_table.setItem(row_position, 6, total_completed_item)

    def populate_order_stats_table(self, data):
        """Заполнение таблицы детальной статистики"""
        self.order_stats_table.setRowCount(0)

        for row_data in data:
            row_position = self.order_stats_table.rowCount()
            self.order_stats_table.insertRow(row_position)

            # Номер заказа (колонка 0)
            self.order_stats_table.setItem(row_position, 0, QTableWidgetItem(row_data['order_number']))

            # Дата производства (колонка 1) - форматируем в день.месяц.год
            proddate = row_data['proddate']
            try:
                if isinstance(proddate, str):
                    date_obj = datetime.strptime(proddate, '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%d.%m.%Y')
                else:
                    formatted_date = proddate
            except:
                formatted_date = proddate
            self.order_stats_table.setItem(row_position, 1, QTableWidgetItem(formatted_date))

            # План ПВХ (колонка 2)
            self.order_stats_table.setItem(row_position, 2, QTableWidgetItem(str(row_data['planned_pvh'])))

            # Сделано ПВХ (колонка 3) с цветовой индикацией
            completed_pvh_item = QTableWidgetItem(str(row_data['completed_pvh']))
            if row_data['planned_pvh'] > 0:
                if row_data['completed_pvh'] >= row_data['planned_pvh']:
                    completed_pvh_item.setForeground(QColor(0, 200, 0))  # Зеленый
                elif row_data['completed_pvh'] > 0:
                    completed_pvh_item.setForeground(QColor(255, 165, 0))  # Оранжевый
            self.order_stats_table.setItem(row_position, 3, completed_pvh_item)

            # План Раздвижки (колонка 4)
            self.order_stats_table.setItem(row_position, 4, QTableWidgetItem(str(row_data['planned_razdv'])))

            # Сделано Раздвижки (колонка 5) с цветовой индикацией
            completed_razdv_item = QTableWidgetItem(str(row_data['completed_razdv']))
            if row_data['planned_razdv'] > 0:
                if row_data['completed_razdv'] >= row_data['planned_razdv']:
                    completed_razdv_item.setForeground(QColor(0, 200, 0))  # Зеленый
                elif row_data['completed_razdv'] > 0:
                    completed_razdv_item.setForeground(QColor(255, 165, 0))  # Оранжевый
            self.order_stats_table.setItem(row_position, 5, completed_razdv_item)

            # Комментарий (колонка 6)
            comment = row_data.get('comment', '') or ''
            self.order_stats_table.setItem(row_position, 6, QTableWidgetItem(comment.strip()))

    def show_error(self, title, message):
        """Показать диалог с ошибкой"""
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)

        # Устанавливаем шрифт
        font = QFont()
        font.setFamily("Arial")
        font.setPointSize(14)
        msg_box.setFont(font)

        msg_box.exec_()

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

                api_version = data.get('api_version', 'unknown')
                print(f"Версия API: {api_version}")

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

        # Диагностика: выводим полученные данные
        print(f"DEBUG: Получен ответ от API:")
        print(f"  success: {success}")
        print(f"  product_info: {product_info}")
        if product_info:
            print(f"  total_items_in_order: {product_info.get('total_items_in_order')}")
            print(f"  approved_items_in_order: {product_info.get('approved_items_in_order')}")
        
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

