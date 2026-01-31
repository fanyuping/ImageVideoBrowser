from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QSplitter, QTreeView,
                             QWidget, QVBoxLayout, QLabel, QStackedWidget, QSizePolicy)
from PyQt6.QtGui import (QFileSystemModel, QAction, QPixmap, QMovie)
from PyQt6.QtCore import (Qt, QDir, QUrl, QThread, pyqtSignal)


class ScanWorker(QThread):
    finished = pyqtSignal(list, str)  # 扫描出的列表, 目标文件路径

    def __init__(self, folder_path, media_extensions, target_file=None):
        super().__init__()
        self.folder_path = folder_path
        self.media_extensions = media_extensions
        self.target_file = target_file

    def run(self):
        media_list = []
        for root, dirs, files in os.walk(self.folder_path):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in self.media_extensions:
                    full_path = os.path.join(root, file)
                    media_list.append(full_path)
        media_list.sort()
        self.finished.emit(media_list, self.target_file or "")


class ImagePreviewWidget(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setMinimumSize(1, 1)
        self._pixmap = None
        self._movie = None

    def set_image(self, file_path):
        self.stop_movie()

        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.gif':
            self._movie = QMovie(file_path)
            self._movie.frameChanged.connect(self.update_movie_size)
            self.setMovie(self._movie)
            self._movie.start()
        else:
            self._pixmap = QPixmap(file_path)
            self.setMovie(None)
            self.update_pixmap()

    def stop_movie(self):
        if self._movie:
            self._movie.stop()
            self._movie = None
        self.setMovie(None)

    def update_pixmap(self):
        if self._pixmap and not self._pixmap.isNull():
            scaled_pixmap = self._pixmap.scaled(self.size(),
                                                Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation)
            self.setPixmap(scaled_pixmap)

    def update_movie_size(self):
        if self._movie:
            # Scale the movie to fit the label while keeping aspect ratio
            size = self.size()
            self._movie.setScaledSize(self._movie.currentPixmap().scaled(
                size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            ).size())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._movie:
            self.update_movie_size()
        else:
            self.update_pixmap()


class VideoPreviewWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.video_widget = QVideoWidget()
        layout.addWidget(self.video_widget)

        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)

    def set_video(self, file_path):
        self.media_player.setSource(QUrl.fromLocalFile(file_path))
        self.media_player.play()

    def stop(self):
        self.media_player.stop()

    def toggle_play(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image and Video Browser")
        self.resize(1200, 800)

        # State for navigation
        self.current_media_list = []
        self.current_index = -1
        self.media_extensions = {'.jpg', '.jpeg', '.png',
                                 '.gif', '.bmp', '.mp4', '.avi', '.mkv', '.mov'}

        # Main splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(self.splitter)

        # Left: File System Tree
        self.setup_tree_view()

        # Right: Preview Area
        self.setup_preview_area()

    def setup_tree_view(self):
        self.model = QFileSystemModel()
        self.model.setRootPath("")  # Shows drives on Windows

        self.model.setNameFilters(["*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp",
                                   "*.mp4", "*.avi", "*.mkv", "*.mov"])
        self.model.setNameFilterDisables(False)

        self.tree = QTreeView()
        self.tree.setModel(self.model)
        # Start at Computer level or root
        self.tree.setRootIndex(self.model.index(""))
        self.tree.setColumnWidth(0, 250)
        self.tree.hideColumn(1)  # Size
        self.tree.hideColumn(2)  # Type
        self.tree.hideColumn(3)  # Date Modified

        self.splitter.addWidget(self.tree)
        self.tree.selectionModel().selectionChanged.connect(self.on_selection_changed)

    def setup_preview_area(self):
        self.preview_widget = QStackedWidget()

        # 0: Placeholder
        self.placeholder = QLabel("请选择图片或视频进行预览")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_widget.addWidget(self.placeholder)

        # 1: Image Preview
        self.image_preview = ImagePreviewWidget()
        self.preview_widget.addWidget(self.image_preview)

        # 2: Video Preview
        self.video_preview = VideoPreviewWidget()
        self.preview_widget.addWidget(self.video_preview)

        self.splitter.addWidget(self.preview_widget)
        self.splitter.setStretchFactor(1, 1)

    def on_selection_changed(self, selected, deselected):
        indexes = selected.indexes()
        if not indexes:
            self.clear_media_state()
            return

        path = self.model.filePath(indexes[0])
        if os.path.isdir(path):
            self.scan_folder(path)
        elif os.path.isfile(path):
            ext = os.path.splitext(path)[1].lower()
            if ext in self.media_extensions:
                # If a file is selected, we scan its parent to allow sibling navigation
                self.scan_folder(os.path.dirname(path), target_file=path)
            else:
                self.clear_media_state()
        else:
            self.clear_media_state()

    def clear_media_state(self):
        self.current_media_list = []
        self.current_index = -1
        self.preview_widget.setCurrentIndex(0)
        self.video_preview.stop()

    def scan_folder(self, folder_path, target_file=None):
        # Stop previous scan if any
        if hasattr(self, 'scan_worker') and self.scan_worker.isRunning():
            self.scan_worker.terminate()
            self.scan_worker.wait()

        self.placeholder.setText("正在扫描媒体文件，请稍候...")
        self.preview_widget.setCurrentIndex(0)

        self.scan_worker = ScanWorker(
            folder_path, self.media_extensions, target_file)
        self.scan_worker.finished.connect(self.on_scan_finished)
        self.scan_worker.start()

    def on_scan_finished(self, media_list, target_file):
        self.current_media_list = media_list
        self.placeholder.setText("请选择图片或视频进行预览")

        if not self.current_media_list:
            self.clear_media_state()
            return

        if target_file and target_file in self.current_media_list:
            self.current_index = self.current_media_list.index(target_file)
        else:
            self.current_index = 0

        self.show_preview(self.current_media_list[self.current_index])

    def navigate_media(self, step):
        if not self.current_media_list:
            return

        new_index = self.current_index + step
        if 0 <= new_index < len(self.current_media_list):
            self.current_index = new_index
            self.show_preview(self.current_media_list[self.current_index])

    def show_preview(self, file_path):
        self.video_preview.stop()

        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
            self.image_preview.set_image(file_path)
            self.preview_widget.setCurrentIndex(1)
        elif ext in ['.mp4', '.avi', '.mkv', '.mov']:
            self.video_preview.set_video(file_path)
            self.preview_widget.setCurrentIndex(2)
        else:
            self.preview_widget.setCurrentIndex(0)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            if self.preview_widget.currentIndex() == 2:
                self.video_preview.toggle_play()
        elif event.key() == Qt.Key.Key_Left:
            self.navigate_media(-1)
        elif event.key() == Qt.Key.Key_Right:
            self.navigate_media(1)
        elif event.key() == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
                self.tree.show()
        elif event.key() == Qt.Key.Key_F11:
            if self.isFullScreen():
                self.showNormal()
                self.tree.show()
            else:
                self.showFullScreen()
                self.tree.hide()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        # delta > 0 is scroll up, delta < 0 is scroll down
        delta = event.angleDelta().y()
        if delta > 0:
            self.navigate_media(-1)  # Scroll up to previous
        elif delta < 0:
            self.navigate_media(1)  # Scroll down to next
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
