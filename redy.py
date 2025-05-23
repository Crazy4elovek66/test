import sys
import os
import re
import requests
import subprocess
import cv2
import numpy as np
import logging
import mediapipe as mp
import math
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QLineEdit, 
    QHeaderView, QMessageBox, QFileDialog, QCheckBox, QFrame, 
    QProgressBar, QToolBar, QStatusBar, QStyle, QStackedLayout,QGraphicsView, QGraphicsScene, QGraphicsItem
)
from PyQt6.QtGui import (
    QColor, QPainter, QPen, QImage, QPixmap, QIcon, 
    QAction, QDesktopServices
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget, QGraphicsVideoItem
from PyQt6.QtCore import Qt, QRect, QPoint, QUrl, QThread, pyqtSignal, QSize, QTimer, QSizeF, QRectF
from PyQt6.QtGui import QBrush, QColor
from dotenv import load_dotenv
import vlc
import mediapipe as mp


# Настройка логгирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TwitchVideoSuite")

# Загрузка переменных окружения
load_dotenv()
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
DEFAULT_CHANNELS = os.getenv('CHANNELS', '')

mp_pose = mp.solutions.pose
pose = mp_pose.Pose(static_image_mode=True)

def sanitize_filename(name):
    return re.sub(r'[\\/:"*?<>|]+', '_', name)   

class VideoPlayer(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Dual Video Player")
        self.resize(1280, 720)

        # Виджеты для вывода видео
        self.video_widget_main = QVideoWidget()     # 16:9
        self.video_widget_vertical = QVideoWidget() # 9:16

        # Основной плеер (16:9)
        self.player_main = QMediaPlayer()
        self.audio_output_main = QAudioOutput()
        self.player_main.setAudioOutput(self.audio_output_main)
        self.player_main.setVideoOutput(self.video_widget_main)

        # Вертикальный плеер (9:16)
        self.player_vertical = QMediaPlayer()
        self.player_vertical.setVideoOutput(self.video_widget_vertical)

        # Кнопки управления
        self.open_button = QPushButton("Открыть видео")
        self.play_button = QPushButton("▶")
        self.pause_button = QPushButton("⏸")

        self.open_button.clicked.connect(self.open_file)
        self.play_button.clicked.connect(self.play_video)
        self.pause_button.clicked.connect(self.pause_video)

        # Макеты
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.open_button)
        button_layout.addWidget(self.play_button)
        button_layout.addWidget(self.pause_button)

        video_layout = QHBoxLayout()
        video_layout.addWidget(self.video_widget_main)          # основной холст 16:9
        video_layout.addWidget(self.video_widget_vertical)  # вертикальный предпросмотр 9:16

        layout = QVBoxLayout()
        layout.addLayout(video_layout)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def open_file(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Выберите видео", "", "Видео файлы (*.mp4 *.avi *.mov)")
        if path:
            self.load_video(path)

    def load_video(self, path):
        url = QUrl.fromLocalFile(path)
        self.player_main.setSource(url)
        self.player_vertical.setSource(url)

    def play_video(self):
        self.player_main.play()
        self.player_vertical.play()

    def pause_video(self):
        self.player_main.pause()
        self.player_vertical.pause()
        
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Twitch Video Suite")
        self.setGeometry(100, 100, 1200, 800)
        
        # Иконка приложения
        self.setWindowIcon(QIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)))
        
        # Создаем вкладки
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.setMovable(False)
        
        # Создаем стиль для вкладок
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #444;
                border-radius: 4px;
                background: #2a2a2a;
            }
            QTabBar::tab {
                background: #333;
                color: #ddd;
                padding: 8px 15px;
                border: 1px solid #444;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: #444;
                color: #fff;
                border-color: #555;
            }
            QTabBar::tab:hover {
                background: #3a3a3a;
            }
        """)
        
        # Добавляем вкладки
        self.clip_finder_tab = TwitchClipFinderTab()
        self.video_editor_tab = VideoEditorTab()
        
        self.tabs.addTab(self.clip_finder_tab, "Twitch Clip Finder")
        self.tabs.addTab(self.video_editor_tab, "Video Editor")
        
        self.setCentralWidget(self.tabs)
        
        # Создаем статус бар
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Создаем тулбар
        self.create_toolbar()
        
        # Применяем стили
        self.apply_styles()
    
    def create_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))
        
        # Действия для тулбара
        exit_action = QAction(QIcon.fromTheme("application-exit"), "Exit", self)
        exit_action.triggered.connect(self.close)
        
        about_action = QAction(QIcon.fromTheme("help-about"), "About", self)
        about_action.triggered.connect(self.show_about)
        
        toolbar.addAction(exit_action)
        toolbar.addSeparator()
        toolbar.addAction(about_action)
        
        self.addToolBar(toolbar)
    
    def show_about(self):
        QMessageBox.about(self, "About Twitch Video Suite", 
                         "Twitch Video Suite v1.0\n\n"
                         "A powerful tool for Twitch clip discovery and video editing.")
    
    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2a2a2a;
            }
            QWidget {
                color: #eee;
                font-size: 14px;
            }
            QLineEdit, QPushButton {
                padding: 8px;
                border-radius: 4px;
                border: 1px solid #444;
                background: #333;
                min-width: 80px;
            }
            QPushButton:hover {
                background: #3a3a3a;
            }
            QPushButton:pressed {
                background: #2a2a2a;
            }
            QTableWidget {
                background: #333;
                border: 1px solid #444;
                gridline-color: #444;
            }
            QHeaderView::section {
                background: #3a3a3a;
                padding: 5px;
                border: none;
            }
            QProgressBar {
                border: 1px solid #444;
                border-radius: 3px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: #4a90e2;
                width: 10px;
            }
        """)
        
    def detect_face_area(self, frame):

        mp_face_detection = mp.solutions.face_detection
        with mp_face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.5) as face_detection:
            results = face_detection.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if results.detections:
                detection = results.detections[0]
                bboxC = detection.location_data.relative_bounding_box
                h, w, _ = frame.shape
                x = int(bboxC.xmin * w)
                y = int(bboxC.ymin * h)
                width = int(bboxC.width * w)
                height = int(bboxC.height * h)
                return x, y, width, height
        return None        


class TwitchClipFinderTab(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.setup_vlc()
    
    def setup_vlc(self):
        VLC_PATH = "C:\\Program Files\\VideoLAN\\VLC"
        os.add_dll_directory(VLC_PATH)
        os.environ["PATH"] += os.pathsep + VLC_PATH
        self.instance = vlc.Instance()
        self.mediaplayer = self.instance.media_player_new()
        self.token = self.get_access_token()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        # Верхняя панель с поиском
        search_layout = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Enter channels separated by commas (e.g. shroud,xqc,pokimane)")
        self.input.setText(DEFAULT_CHANNELS)
        search_layout.addWidget(self.input)
        
        self.search_btn = QPushButton("Find Clips")
        self.search_btn.setIcon(QIcon.fromTheme("edit-find"))
        self.search_btn.clicked.connect(self.fetch_clips)
        search_layout.addWidget(self.search_btn)
        
        layout.addLayout(search_layout)
        
        # Статус лейбл
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Кнопка скачивания
        self.download_btn = QPushButton("Download Selected Clips")
        self.download_btn.setIcon(QIcon.fromTheme("document-save"))
        self.download_btn.clicked.connect(self.download_selected_clips)
        layout.addWidget(self.download_btn)
        
        # Таблица с клипами
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Select", "Channel", "Title", "Views", 
            "URL", "Download", "Preview"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.cellClicked.connect(self.open_url)
        layout.addWidget(self.table)
        
        # Видео фрейм
        self.video_frame = QFrame()
        self.video_frame.setStyleSheet("background-color: black;")
        self.video_frame.setMinimumHeight(300)
        layout.addWidget(self.video_frame)
        
        self.setLayout(layout)
    
    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform.startswith('win'):
            self.mediaplayer.set_hwnd(int(self.video_frame.winId()))
            print("HWND:", int(self.video_frame.winId()))

    def get_access_token(self):
        url = 'https://id.twitch.tv/oauth2/token'
        params = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'client_credentials'
        }
        response = requests.post(url, params=params).json()
        return response['access_token']

    def get_user_id(self, username, headers):
        url = f'https://api.twitch.tv/helix/users'
        params = {'login': username}
        response = requests.get(url, headers=headers, params=params).json()
        return response['data'][0]['id'] if response['data'] else None

    def get_clips(self, user_id, headers):
        url = f'https://api.twitch.tv/helix/clips'
        params = {
            'broadcaster_id': user_id,
            'first': 20,
            'started_at': '2024-01-01T00:00:00Z',
        }
        response = requests.get(url, headers=headers, params=params).json()
        return response['data']

    def fetch_clips(self):
        self.table.setRowCount(0)
        self.status_label.setText("Загрузка...")
        QApplication.processEvents()

        headers = {
            'Client-ID': CLIENT_ID,
            'Authorization': f'Bearer {self.token}'
        }

        channels = [c.strip() for c in self.input.text().split(',') if c.strip()]
        if not channels:
            QMessageBox.warning(self, "Ошибка", "Введите хотя бы один канал.")
            return

        all_clips = []

        for channel in channels:
            user_id = self.get_user_id(channel, headers)
            if not user_id:
                continue
            clips = self.get_clips(user_id, headers)
            for clip in clips:
                clip['channel'] = channel
                all_clips.append(clip)

        sorted_clips = sorted(all_clips, key=lambda x: x['view_count'], reverse=True)

        for clip in sorted_clips:
            row_pos = self.table.rowCount()
            self.table.insertRow(row_pos)

            # NEW: Добавляем чекбокс в первый столбец
            checkbox = QCheckBox()
            checkbox_widget = QWidget()
            layout_cb = QHBoxLayout(checkbox_widget)
            layout_cb.addWidget(checkbox)
            layout_cb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout_cb.setContentsMargins(0, 0, 0, 0)
            checkbox_widget.setLayout(layout_cb)
            self.table.setCellWidget(row_pos, 0, checkbox_widget)

            self.table.setItem(row_pos, 1, QTableWidgetItem(clip['channel']))
            self.table.setItem(row_pos, 2, QTableWidgetItem(clip['title']))
            self.table.setItem(row_pos, 3, QTableWidgetItem(str(clip['view_count'])))
            url_item = QTableWidgetItem(clip['url'])
            url_item.setForeground(QColor('cyan'))
            self.table.setItem(row_pos, 4, url_item)

            preview_button = QPushButton("▶️")
            preview_button.clicked.connect(lambda _, url=clip['url']: self.preview_clip(url))
            self.table.setCellWidget(row_pos, 6, preview_button)

            button = QPushButton("Скачать")
            button.setStyleSheet("padding: 4px 10px; font-weight: bold;")
            button.clicked.connect(lambda _, url=clip['url'], ch=clip['channel'], title=clip['title']: 
                       self.download_clip(url, {"channel": ch, "title": title}))

            self.table.setCellWidget(row_pos, 5, button)

        self.status_label.setText(f"Найдено клипов: {len(sorted_clips)}")      
    
    def download_selected_clips(self):
        selected_clips = []
        for row in range(self.table.rowCount()):
            checkbox_widget = self.table.cellWidget(row, 0)
            if checkbox_widget:
                checkbox = checkbox_widget.findChild(QCheckBox)
                if checkbox and checkbox.isChecked():
                    url_item = self.table.item(row, 4)
                    channel_item = self.table.item(row, 1)
                    title_item = self.table.item(row, 2)
                    if url_item and channel_item and title_item:
                        selected_clips.append({
                            'url': url_item.text(),
                            'channel': channel_item.text(),
                            'title': title_item.text()
                        })

        if not selected_clips:
            QMessageBox.information(self, "Информация", "Не выбраны клипы для скачивания.")
            return

        save_dir = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения")
        if not save_dir:
            return

        self.status_label.setText("Скачивание выбранных клипов...")
        QApplication.processEvents()

        errors = []
        for clip in selected_clips:
            try:
                filename = f"{clip['channel']} - {clip['title']}.mp4"
                filename = sanitize_filename(filename)
                save_path = os.path.join(save_dir, filename)
                subprocess.run(["yt-dlp", "-o", save_path, clip['url']], check=True)
            except subprocess.CalledProcessError:
                errors.append(clip['url'])

        if errors:
            QMessageBox.warning(self, "Ошибка", f"Не удалось скачать клипы:\n" + "\n".join(errors))
        else:
            QMessageBox.information(self, "Готово", "Выбранные клипы успешно скачаны.")
        
        self.status_label.setText("Готово.")
   
    
    def preview_clip(self, clip_url):
        try:
            self.status_label.setText("Получение прямой ссылки...")
            QApplication.processEvents()

            result = subprocess.run(
                ["yt-dlp", "-f", "mp4", "-g", clip_url],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            direct_url = result.stdout.strip()
            print("Direct URL:", direct_url)

            # Открываем отдельное окно предпросмотра
            self.preview_window = PreviewWindow(self.instance, direct_url)
            self.preview_window.show()
            self.setWindowIcon(QIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)))

            self.status_label.setText("Предпросмотр открыт.")
        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось получить ссылку на видео:\n{e.stderr}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

        
    def download_clip(self, clip_url, clip_info):
        # Формируем предложенное имя файла
        suggested_name = f"{clip_info['channel']} - {clip_info['title']}.mp4"
        
        # Запускаем диалог сохранения с предложенным именем
        save_path, _ = QFileDialog.getSaveFileName(self, "Сохранить клип как", suggested_name, "Видео (*.mp4)")
        if not save_path:
            return

        try:
            # yt-dlp принимает путь с расширением, поэтому если пользователь не дописал .mp4, добавим
            if not save_path.lower().endswith(".mp4"):
                save_path += ".mp4"

            # Скачиваем с помощью yt-dlp
            subprocess.run(["yt-dlp", "-o", save_path, clip_url], check=True)
            QMessageBox.information(self, "Готово", "Клип успешно скачан.")
        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось скачать клип:\n{e}")

    def open_url(self, row, column):
        if column == 3:
            url = self.table.item(row, column).text()
            QDesktopServices.openUrl(QUrl(url))
          
class PreviewWindow(QWidget):
    def __init__(self, vlc_instance, direct_url):
        super().__init__()
        self.setWindowTitle("Предпросмотр клипа")
        self.resize(640, 360)
        self.setStyleSheet("background-color: black;")

        self.vlc_instance = vlc_instance
        self.direct_url = direct_url
        self.mediaplayer = self.vlc_instance.media_player_new()

        layout = QVBoxLayout()
        self.video_frame = QFrame()
        self.video_frame.setStyleSheet("background-color: black;")
        layout.addWidget(self.video_frame)
        self.setLayout(layout)

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform.startswith('win'):
            self.mediaplayer.set_hwnd(int(self.video_frame.winId()))

        media = self.vlc_instance.media_new(self.direct_url)
        media.add_option('--network-caching=500')
        media.add_option('--http-continuous')
        media.add_option('--no-video-title-show')
        self.mediaplayer.set_media(media)
        self.mediaplayer.play()

    def closeEvent(self, event):
        self.mediaplayer.stop()
        event.accept()
        
class VideoEditorTab(QWidget):
    def __init__(self):
        super().__init__()
        self.video_path = None
        self.cap = None
        self.frame = None
        self.save_folder = None
        self.cutting_thread = None
        self.frame_for_display = None
        self.playing = False
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        
        # Инициализация прямоугольников
        self.rect1 = QRectF(100, 100, 300, 200)  # Первый прямоугольник (зеленый)
        self.rect2 = QRectF(500, 200, 300, 200)  # Второй прямоугольник (красный)
        
        self.setup_ui()

    def setup_ui(self):
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(15)

        # Левая панель (16:9)
        left_panel = QVBoxLayout()
        left_panel.setSpacing(15)

        # Панель инструментов
        tool_panel = QHBoxLayout()
        self.load_btn = QPushButton("Load Video")
        self.load_btn.setIcon(QIcon.fromTheme("document-open"))
        self.load_btn.clicked.connect(self.load_video)
        tool_panel.addWidget(self.load_btn)

        self.save_btn = QPushButton("Set Output")
        self.save_btn.setIcon(QIcon.fromTheme("folder"))
        self.save_btn.clicked.connect(self.selectSaveFolder)
        self.save_btn.setEnabled(False)
        tool_panel.addWidget(self.save_btn)

        # Кнопки управления воспроизведением
        self.play_btn = QPushButton("▶")
        self.play_btn.clicked.connect(self.toggle_playback)
        self.play_btn.setEnabled(False)
        tool_panel.addWidget(self.play_btn)

        left_panel.addLayout(tool_panel)

        # Основной холст для видео 16:9
        self.scene = QGraphicsScene()
        self.canvas_view = QGraphicsView(self.scene)
        self.canvas_view.setFixedSize(960, 540)  # 16:9
        self.canvas_view.setStyleSheet("background-color: black;")

        # Видеоэлемент
        self.video_item = QGraphicsVideoItem()
        self.video_item.setPos(0, 0)
        self.video_item.setSize(QSizeF(960, 540))
        self.scene.addItem(self.video_item)

        # Прямоугольники для выделения областей
        self.area1_item = self.scene.addRect(
            self.rect1, 
            QPen(QColor(0, 255, 0, 180), 2), 
            QBrush(QColor(0, 255, 0, 60))
        )
        self.area2_item = self.scene.addRect(
            self.rect2, 
            QPen(QColor(255, 0, 0, 180), 2), 
            QBrush(QColor(255, 0, 0, 60))
        )

        # Сделаем прямоугольники перемещаемыми
        self.area1_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.area1_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.area2_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.area2_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)

        left_panel.addWidget(self.canvas_view)

        # Панель управления обработкой
        control_panel = QHBoxLayout()
        self.start_btn = QPushButton("Start Processing")
        self.start_btn.setIcon(QIcon.fromTheme("media-playback-start"))
        self.start_btn.clicked.connect(self.startCutting)
        self.start_btn.setEnabled(False)
        control_panel.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setIcon(QIcon.fromTheme("media-playback-stop"))
        self.stop_btn.clicked.connect(self.stopCutting)
        self.stop_btn.setEnabled(False)
        control_panel.addWidget(self.stop_btn)

        left_panel.addLayout(control_panel)

        # Прогресс бар
        self.progress = QProgressBar()
        left_panel.addWidget(self.progress)

        # Правая панель - предпросмотр 9:16
        right_panel = QVBoxLayout()
        right_panel.setSpacing(10)

        preview_label = QLabel("Preview (9:16)")
        preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_panel.addWidget(preview_label)

        self.preview_canvas = QLabel()
        self.preview_canvas.setFixedSize(360, 640)  # 9:16
        self.preview_canvas.setStyleSheet("background-color: black;")
        right_panel.addWidget(self.preview_canvas)

        # Добавляем панели в основной макет
        main_layout.addLayout(left_panel, 70)  # 70% ширины
        main_layout.addLayout(right_panel, 30)  # 30% ширины
        self.setLayout(main_layout)

        # Подключаем сигналы изменения прямоугольников
        self.scene.selectionChanged.connect(self.update_preview)

    def detect_face_area(self, frame):
        mp_face = mp.solutions.face_detection
        h, w, _ = frame.shape

        with mp_face.FaceDetection(model_selection=0, min_detection_confidence=0.5) as face_det:
            results = face_det.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if results.detections:
                bbox = results.detections[0].location_data.relative_bounding_box
                x = int(bbox.xmin * w)
                y = int(bbox.ymin * h)
                width = int(bbox.width * w)
                height = int(bbox.height * h)
                return x, y, width, height
        return None

    def load_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите видео", "", 
            "Видео файлы (*.mp4 *.avi *.mov)"
        )
        if not path:
            return
            
        self.video_path = path
        self.cap = cv2.VideoCapture(path)
        
        # Устанавливаем видео в QMediaPlayer
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_item)
        self.media_player.setSource(QUrl.fromLocalFile(path))
        
        # Получаем первый кадр для обработки
        ret, frame = self.cap.read()
        if not ret:
            QMessageBox.critical(self, "Ошибка", "Не удалось прочитать видео")
            return
            
        self.frame = frame
        self.show_frame_on_canvas(frame)
        
        # Автоматически определяем положение лица
        face_rect = self.detect_face_area(frame)
        if face_rect:
            x, y, w, h = face_rect
            self.area1_item.setRect(QRectF(x, y, w, h))
            
        # Устанавливаем красную область по центру
        self.set_red_area_center()
        
        self.save_btn.setEnabled(True)
        self.play_btn.setEnabled(True)
        self.start_btn.setEnabled(True)
        self.progress.setValue(0)
        
    def toggle_playback(self):
        if not self.playing:
            self.media_player.play()
            self.timer.start(30)  # обновление каждые 30 мс
            self.play_btn.setText("⏸")
            self.playing = True
        else:
            self.media_player.pause()
            self.timer.stop()
            self.play_btn.setText("▶")
            self.playing = False

    def update_frame(self):
        if self.cap:
            ret, frame = self.cap.read()
            if ret:
                self.frame = frame
                self.show_frame_on_canvas(frame)
                self.update_preview()
            else:
                # Достигнут конец видео
                self.timer.stop()
                self.play_btn.setText("▶")
                self.playing = False
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # Перемотка в начало

    def show_frame_on_canvas(self, frame):
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_frame.shape
        bytes_per_line = ch * w
        qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        self.frame_for_display = qt_image
    
    def set_red_area_center(self):
        """Устанавливает красную область по центру с соотношением 9:16"""
        canvas_width = self.canvas_view.width()
        canvas_height = self.canvas_view.height()
        
        # Рассчитываем размеры для соотношения 9:16
        area_width = min(canvas_width, int(canvas_height * 9/16))
        area_height = min(canvas_height, int(canvas_width * 16/9))
        
        # Центрируем
        x = (canvas_width - area_width) // 2
        y = (canvas_height - area_height) // 2
        
        self.area2_item.setRect(QRectF(x, y, area_width, area_height))
        self.update_preview()

    def update_preview(self):
        if self.frame is None:
            return
            
        frame_h, frame_w = self.frame.shape[:2]
        canvas_w = self.canvas_view.width()
        canvas_h = self.canvas_view.height()
        
        # Масштабируем координаты прямоугольников к размеру исходного кадра
        def scale_rect(rect):
            x = rect.x() * frame_w / canvas_w
            y = rect.y() * frame_h / canvas_h
            w = rect.width() * frame_w / canvas_w
            h = rect.height() * frame_h / canvas_h
            return QRect(int(x), int(y), int(w), int(h))
            
        rect1 = scale_rect(self.area1_item.rect())
        rect2 = scale_rect(self.area2_item.rect())
        
        # Определяем порядок - меньший по высоте сверху
        if rect1.height() < rect2.height():
            top_rect, bottom_rect = rect1, rect2
        else:
            top_rect, bottom_rect = rect2, rect1
            
        # Вырезаем и масштабируем области
        def crop_and_resize(rect, target_w, target_h):
            x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
            crop = self.frame[y:y+h, x:x+w]
            return cv2.resize(crop, (target_w, target_h), interpolation=cv2.INTER_AREA)
            
        preview_w = self.preview_canvas.width()
        total_h = top_rect.height() + bottom_rect.height()
        
        if total_h == 0:
            return
            
        top_h = int(preview_w * (top_rect.height() / top_rect.width()))
        bottom_h = int(preview_w * (bottom_rect.height() / bottom_rect.width()))
        
        # Если суммарная высота больше доступной, масштабируем
        if (top_h + bottom_h) > self.preview_canvas.height():
            scale_factor = self.preview_canvas.height() / (top_h + bottom_h)
            top_h = int(top_h * scale_factor)
            bottom_h = int(bottom_h * scale_factor)
            
        top_img = crop_and_resize(top_rect, preview_w, top_h)
        bottom_img = crop_and_resize(bottom_rect, preview_w, bottom_h)
        
        # Объединяем изображения
        combined = np.vstack((top_img, bottom_img))
        combined_rgb = cv2.cvtColor(combined, cv2.COLOR_BGR2RGB)
        
        # Отображаем в QLabel
        h, w, ch = combined_rgb.shape
        bytes_per_line = ch * w
        qimg = QImage(combined_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        self.preview_canvas.setPixmap(QPixmap.fromImage(qimg))

    def selectSaveFolder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения")
        if folder:
            self.save_folder = folder
            logger.info(f"Папка для сохранения: {folder}")

    def updateRect(self, area_widget, new_rect, was_resized=False):
        if area_widget == self.area1:
            self.current_rect1 = QRect(new_rect)
        elif area_widget == self.area2:
            self.current_rect2 = QRect(new_rect)
        
        self.updatePreview()

    def updatePreview(self):
        if self.frame is None:
            return

        frame_h, frame_w = self.frame.shape[:2]
        disp_w = self.canvas.width()
        disp_h = self.canvas.height()

        scale_w = frame_w / disp_w
        scale_h = frame_h / disp_h

        # Корректируем координаты с учетом масштаба
        def scale_rect(rect):
            return QRect(
                int(rect.left() * scale_w),
                int(rect.top() * scale_h),
                int(rect.width() * scale_w),
                int(rect.height() * scale_h),
            )

        r1 = scale_rect(self.current_rect1)
        r2 = scale_rect(self.current_rect2)

        preview_width = self.preview_canvas.width()
        preview_height = self.preview_canvas.height()

        # Определяем порядок — меньший по высоте сверху
        if r1.height() < r2.height():
            top_rect, bottom_rect = r1, r2
        else:
            top_rect, bottom_rect = r2, r1

        total_h = top_rect.height() + bottom_rect.height()
        if total_h == 0:
            return

        # Распределяем высоту пропорционально
        top_scaled_h = int(preview_height * (top_rect.height() / total_h))
        bottom_scaled_h = preview_height - top_scaled_h

        def crop_and_resize(r, target_w, target_h):
            x, y, w, h = r.left(), r.top(), r.width(), r.height()
            # Защита от выхода за рамки исходного кадра
            x = max(0, min(x, frame_w - 1))
            y = max(0, min(y, frame_h - 1))
            w = min(w, frame_w - x)
            h = min(h, frame_h - y)
            if w <= 0 or h <= 0:
                return None
            crop = self.frame[y:y + h, x:x + w]
            if crop.size == 0:
                return None
            return cv2.resize(crop, (target_w, target_h), interpolation=cv2.INTER_AREA)

        top_img = crop_and_resize(top_rect, preview_width, top_scaled_h)
        bottom_img = crop_and_resize(bottom_rect, preview_width, bottom_scaled_h)

        if top_img is None or bottom_img is None:
            return

        combined = np.vstack((top_img, bottom_img))
        combined_rgb = cv2.cvtColor(combined, cv2.COLOR_BGR2RGB)

        h, w, ch = combined_rgb.shape
        bytes_per_line = ch * w
        qimg = QImage(combined_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

        self.preview_canvas.setPixmap(QPixmap.fromImage(qimg))

    def startCutting(self):
        if not self.video_path or not self.save_folder:
            QMessageBox.warning(self, "Внимание", "Выберите видео и папку для сохранения")
            return

        if self.frame is None:
            QMessageBox.warning(self, "Внимание", "Кадр видео не загружен")
            return

        frame_h, frame_w = self.frame.shape[:2]
        disp_w = self.canvas.width()
        disp_h = self.canvas.height()

        if disp_w == 0 or disp_h == 0:
            QMessageBox.warning(self, "Внимание", "Размер холста не может быть нулевым")
            return

        scale_w = frame_w / disp_w
        scale_h = frame_h / disp_h

        # Пересчёт координат прямоугольников из canvas в координаты видео с защитой от отрицательных и выходящих за пределы
        def scaled_rect(r):
            left = max(0, int(r.left() * scale_w))
            top = max(0, int(r.top() * scale_h))
            width = int(r.width() * scale_w)
            height = int(r.height() * scale_h)

            # Ограничение размеров, чтобы не выходить за кадр видео
            if left + width > frame_w:
                width = frame_w - left
            if top + height > frame_h:
                height = frame_h - top

            return QRect(left, top, width, height)

        real_rect1 = scaled_rect(self.current_rect1)
        real_rect2 = scaled_rect(self.current_rect2)

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.load_btn.setEnabled(False)
        self.save_btn.setEnabled(False)

        self.cutting_thread = VideoCuttingThread(
            self.video_path,
            self.save_folder,
            real_rect1,
            real_rect2
        )
        self.cutting_thread.progress_update.connect(self.progress.setValue)
        self.cutting_thread.finished.connect(self.cuttingFinished)
        self.cutting_thread.start()
        logger.info("Начата нарезка видео")


    def stopCutting(self):
        if self.cutting_thread and self.cutting_thread.isRunning():
            self.cutting_thread.terminate()
            self.cutting_thread.wait()
            logger.info("Нарезка видео остановлена пользователем")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.load_btn.setEnabled(True)
            self.save_btn.setEnabled(True)

    def cuttingFinished(self):
        QMessageBox.information(self, "Готово", "Нарезка видео завершена!")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.load_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.progress.setValue(100)

class DraggableRect(QWidget):
    def __init__(self, parent, rect: QRect, controller=None, color=QColor(0, 255, 0, 120)):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.controller = controller
        self.color = color
        self.dragging = False
        self.resizing = False
        self.resize_margin = 10
        self.drag_start_pos = QPoint()
        self.rect_start_pos = QPoint()
        self.setGeometry(rect)
        
        # Эффекты для красоты
        self.setStyleSheet("""
            border: 2px dashed rgba(255, 255, 255, 0.5);
            border-radius: 4px;
        """)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self.color.darker(), 2)
        painter.setPen(pen)
        painter.setBrush(self.color)

        rect = QRect(0, 0, self.width(), self.height())
        painter.drawRect(rect)

        resize_rect = QRect(
            rect.right() - self.resize_margin,
            rect.bottom() - self.resize_margin,
            self.resize_margin,
            self.resize_margin
        )
        painter.fillRect(resize_rect, self.color.darker(200))
        
    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        if QRect(0, 0, self.width(), self.height()).contains(pos):
            self.dragging = True
            self.drag_start_pos = pos
            self.rect_start_pos = self.pos()
            if abs(pos.x() - self.width()) <= self.resize_margin and abs(pos.y() - self.height()) <= self.resize_margin:
                self.resizing = True
            else:
                self.resizing = False
        else:
            super().mousePressEvent(event)


    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()

        if self.dragging:
            if self.resizing:
                new_width = max(20, pos.x())
                new_height = max(20, pos.y())
                max_width = self.parent().width() - self.x()
                max_height = self.parent().height() - self.y()
                new_width = min(new_width, max_width)
                new_height = min(new_height, max_height)
                self.setFixedSize(new_width, new_height)
            else:
                delta = pos - self.drag_start_pos
                new_pos = self.rect_start_pos + delta
                new_x = max(0, min(new_pos.x(), self.parent().width() - self.width()))
                new_y = max(0, min(new_pos.y(), self.parent().height() - self.height()))
                self.move(new_x, new_y)

            if self.controller:
                new_rect = QRect(self.x(), self.y(), self.width(), self.height())
                self.controller.updateRect(self, new_rect, was_resized=self.resizing)
        else:
            if abs(pos.x() - self.width()) <= self.resize_margin and abs(pos.y() - self.height()) <= self.resize_margin:
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif QRect(0, 0, self.width(), self.height()).contains(pos):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)


    def mouseReleaseEvent(self, event):
        was_resized = self.resizing
        self.dragging = False
        self.resizing = False
        if self.controller:
            self.controller.updateRect(self, QRect(self.x(), self.y(), self.width(), self.height()), was_resized=was_resized)
            self.controller.updatePreview()

class VideoCuttingThread(QThread):
    progress_update = pyqtSignal(int)
    
    def __init__(self, video_path, save_folder, rect1, rect2):
        super().__init__()
        self.video_path = None
        self.save_folder = save_folder
        self.rect1 = rect1
        self.rect2 = rect2
        self.running = True
        self.part_duration = 180

    @staticmethod
    def split_video_ffmpeg_only(input_path, chunk_duration=180):

        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries',
                 'format=duration', '-of',
                 'default=noprint_wrappers=1:nokey=1', input_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT
            )
            duration = float(result.stdout.decode('utf-8').strip())  # Декодируем bytes в строку
        except Exception as e:
            print(f"Не удалось получить длительность: {e}")
            return

        num_parts = math.ceil(duration / chunk_duration)
        base_name, ext = os.path.splitext(input_path)

        for i in range(num_parts):
            start_time = i * chunk_duration
            output_name = f"{base_name}_part_{i+1}{ext}"
            cmd = [
                'ffmpeg',
                '-y',
                '-i', input_path,
                '-ss', str(start_time),
                '-t', str(chunk_duration),
                '-c:v', 'copy',
                '-c:a', 'copy',
                output_name
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        os.remove(input_path) 

    def run(self):
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            logger.error("Не удалось открыть видео для нарезки")
            return

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps
        logger.info(f"Всего кадров: {total_frames}, длительность: {duration:.2f} сек")

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        rect_w, rect_h = self.rect1.width(), self.rect1.height()

        center_x = width // 2
        center_y = height // 2

        new_x = center_x - rect_w // 2
        new_y = center_y - rect_h // 2

        new_x = max(0, min(new_x, width - rect_w))
        new_y = max(0, min(new_y, height - rect_h))

        self.rect1 = QRect(new_x, new_y, rect_w, rect_h)

        out_width, out_height = 1080, 1920
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')

        if self.rect1.height() < self.rect2.height():
            top_rect, bottom_rect = self.rect1, self.rect2
        else:
            top_rect, bottom_rect = self.rect2, self.rect1

        frame_index = 0
        part_number = 1
        frames_per_part = int(self.part_duration * fps)
        current_part_frames = 0

        temp_folder = os.path.join(self.save_folder, "temp_parts")
        os.makedirs(temp_folder, exist_ok=True)

        out_path = os.path.join(temp_folder, f"part_{part_number}.mp4")
        out = cv2.VideoWriter(out_path, fourcc, fps, (out_width, out_height))

        while self.running:
            ret, frame = cap.read()
            if not ret:
                break

            def safe_crop(rect):
                x, y, w, h = rect.left(), rect.top(), rect.width(), rect.height()
                x = max(0, x)
                y = max(0, y)
                w = max(1, w)
                h = max(1, h)
                x2 = min(frame.shape[1], x + w)
                y2 = min(frame.shape[0], y + h)
                return frame[y:y2, x:x2]

            crop_top = safe_crop(top_rect)
            crop_bottom = safe_crop(bottom_rect)

            total_h = crop_top.shape[0] + crop_bottom.shape[0]
            if total_h == 0:
                continue

            top_scaled_height = int(out_height * (crop_top.shape[0] / total_h))
            bottom_scaled_height = out_height - top_scaled_height

            top_resized = cv2.resize(crop_top, (out_width, top_scaled_height), interpolation=cv2.INTER_AREA)
            bottom_resized = cv2.resize(crop_bottom, (out_width, bottom_scaled_height), interpolation=cv2.INTER_AREA)

            combined_frame = np.vstack((top_resized, bottom_resized))
            out.write(combined_frame)

            current_part_frames += 1
            frame_index += 1

            if current_part_frames >= frames_per_part or frame_index == total_frames:
                out.release()
                logger.info(f"Часть {part_number} сохранена: {out_path}")

                final_part_path = os.path.join(self.save_folder, f"part_{part_number}.mp4")
                start_time = (part_number - 1) * self.part_duration
                self.add_audio_to_video(out_path, final_part_path, start_time)
                os.remove(out_path)

                if frame_index < total_frames:
                    part_number += 1
                    current_part_frames = 0
                    out_path = os.path.join(temp_folder, f"part_{part_number}.mp4")
                    out = cv2.VideoWriter(out_path, fourcc, fps, (out_width, out_height))

            progress_percent = int(frame_index / total_frames * 100)
            self.progress_update.emit(progress_percent)

        cap.release()

        try:
            for f in os.listdir(temp_folder):
                os.remove(os.path.join(temp_folder, f))
            os.rmdir(temp_folder)
            logger.info("Временные файлы удалены")
        except Exception as e:
            logger.warning(f"Не удалось удалить временные файлы: {e}")

        self.progress_update.emit(100)
        logger.info("Нарезка видео на части завершена")
        
    def add_audio_to_video(self, input_video_path, output_video_path, start_time):
        command = [
            'ffmpeg',
            '-y',
            '-i', input_video_path,
            '-ss', str(start_time),
            '-i', self.video_path,
            '-t', str(self.part_duration),
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-shortest',
            output_video_path
        ]
        logger.info(f"Добавление аудио к видео: {output_video_path} (время начала: {start_time} сек)")
        try:
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logger.info("Аудио успешно добавлено")
        except subprocess.CalledProcessError as e:
            logger.error(f"Ошибка при добавлении аудио: {e.stderr.decode()}")
                   

    def stop(self):
        self.running = False    
        
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Устанавливаем стиль Fusion для красивого темного интерфейса
    app.setStyle("Fusion")
    
    # Создаем и показываем главное окно
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())        
    
