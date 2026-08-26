from __future__ import annotations

import logging
import qtawesome as qta

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QMainWindow, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget

from api.client import MangaDexClient
from utils.cache import image_bytes


class PageWorker(QThread):
    loaded = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, chapter_id: str, data_saver: bool = False):
        super().__init__()
        self.chapter_id = chapter_id
        self.data_saver = data_saver

    def run(self):
        try:
            pages = MangaDexClient().pages(self.chapter_id, data_saver=self.data_saver)
            self.loaded.emit(pages)
        except Exception as exc:
            logging.exception("Falha ao carregar páginas do capítulo %s", self.chapter_id)
            self.failed.emit(str(exc))


class ImageWorker(QThread):
    loaded = pyqtSignal(list)

    def __init__(self, urls):
        super().__init__()
        self.urls = urls

    def run(self):
        try:
            self.loaded.emit([image_bytes(url) for url in self.urls])
        except Exception:
            logging.exception("Falha ao baixar imagens do leitor")
            self.loaded.emit([])


class ReaderWindow(QMainWindow):
    def __init__(self, manga: dict, chapter: dict, chapters: list[dict], database):
        super().__init__()
        self.manga, self.chapter, self.chapters, self.database = manga, chapter, chapters, database
        self.page_index = 0

        self.setWindowTitle(f"MangaKoro Leitor: {manga['title']} - Cap. {chapter['chapter']}")
        self.resize(1200, 900)
        
        # Styleshoot específico para o leitor, priorizando foco no conteúdo
        self.setStyleSheet("""
            QMainWindow { background: #030712; } 
            QLabel { color: #f3f4f6; }
            QComboBox, QSpinBox { background: #1f2937; border: 1px solid #374151; border-radius: 6px; padding: 6px; color: white;}
            QPushButton { background: #1f2937; border: 1px solid #374151; border-radius: 6px; padding: 6px 12px; color: white; font-weight: bold;}
            QPushButton:hover { background: #374151; border: 1px solid #60a5fa;}
        """)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        bar = QWidget()
        bar.setObjectName("readerBar")
        bar.setStyleSheet("#readerBar { background: #111827; border-bottom: 1px solid #1f2937; }")
        
        controls = QHBoxLayout(bar)
        controls.setContentsMargins(12, 10, 12, 10)

        close = QPushButton(" Sair")
        close.setIcon(qta.icon('fa5s.times', color='#ef4444'))
        close.clicked.connect(self.close)

        self.chapter_box = QComboBox()
        self.chapter_box.addItems([f"Cap. {c['chapter']} • {c['language']}" for c in chapters])
        self.chapter_box.setCurrentIndex(next((i for i, c in enumerate(chapters) if c['id'] == chapter['id']), 0))
        self.chapter_box.currentIndexChanged.connect(self.change_chapter)

        self.mode = QComboBox()
        self.mode.addItems(["Rolagem Vertical", "Página Única", "Dupla Página"])
        self.mode.setCurrentIndex(self.database.setting("reader_mode", 0))
        self.mode.currentIndexChanged.connect(self.render_pages)

        self.bg = QComboBox()
        self.bg.addItems(["Fundo Preto", "Fundo Cinza", "Fundo Branco"])
        self.bg.currentIndexChanged.connect(self.change_background)

        self.zoom = QSpinBox()
        self.zoom.setRange(25, 250)
        self.zoom.setValue(100)
        self.zoom.setSuffix("%")
        self.zoom.valueChanged.connect(self.render_pages)

        previous = QPushButton(" Anterior")
        previous.setIcon(qta.icon('fa5s.chevron-left', color='white'))
        previous.clicked.connect(self.previous_page)
        
        next_page = QPushButton(" Próxima ")
        next_page.setIcon(qta.icon('fa5s.chevron-right', color='white'))
        next_page.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        next_page.clicked.connect(self.next_page)

        controls.addWidget(close)
        
        title_lbl = QLabel(f"<b>{manga['title']}</b>")
        title_lbl.setStyleSheet("font-size: 16px; margin: 0 16px; color: #60a5fa;")
        controls.addWidget(title_lbl)
        
        for widget in (self.chapter_box, self.mode, self.bg, self.zoom):
            controls.addWidget(widget)

        controls.addStretch()
        controls.addWidget(previous)
        controls.addWidget(next_page)

        layout.addWidget(bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: 0; background: #030712; }")
        
        self.page_host = QWidget()
        self.pages_layout = QVBoxLayout(self.page_host)
        self.pages_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.pages_layout.setSpacing(10) # Espaço entre as páginas
        self.scroll.setWidget(self.page_host)
        
        layout.addWidget(self.scroll)

        self.setCentralWidget(root)
        self.worker = None
        self.load_pages()

    def load_pages(self):
        self.statusBar().setStyleSheet("background: #111827; color: #9ca3af;")
        self.statusBar().showMessage("Sincronizando imagens com o MangaDex...")
        quality_setting = self.database.setting("quality", "Original")
        is_saver = "Comprimida" in quality_setting

        self.worker = PageWorker(self.chapter["id"], data_saver=is_saver)
        self.worker.loaded.connect(self.show_pages)
        self.worker.failed.connect(lambda error: self.statusBar().showMessage(error))
        self.worker.start()

    def show_pages(self, urls: list[str]):
        if not urls:
            self.statusBar().showMessage("Falha: Nenhuma imagem encontrada no servidor para este capítulo.")
            return
        self.statusBar().showMessage(f"Iniciando download de {len(urls)} páginas...")
        self.image_worker = ImageWorker(urls)
        self.image_worker.loaded.connect(self.show_images)
        self.image_worker.start()

    def show_images(self, images: list[bytes]):
        self.images = images
        self.page_index = 0
        self.render_pages()
        self.database.add_history(self.chapter, self.manga)
        self.statusBar().showMessage(f"Sucesso! {len(images)} páginas carregadas e prontas.")

    def render_pages(self):
        if not hasattr(self, "images"):
            return
        while self.pages_layout.count():
            item = self.pages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        width = max(300, int(self.scroll.viewport().width() * self.zoom.value() / 100))
        if self.mode.currentIndex() == 0: # Vertical Scroll
            groups = [[data] for data in self.images]
        elif self.mode.currentIndex() == 1: # Single Page
            groups = [[self.images[self.page_index]]] if self.images else []
        else: # Double Page
            groups = [self.images[self.page_index:self.page_index + 2]] if self.images else []

        for group in groups:
            row = QHBoxLayout()
            row.setSpacing(0)
            row.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.pages_layout.addLayout(row)
            
            for data in group:
                label = QLabel("Falha na renderização")
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                pixmap = QPixmap()
                pixmap.loadFromData(data)
                if not pixmap.isNull():
                    target_w = width if len(group) == 1 else width // 2
                    label.setPixmap(pixmap.scaledToWidth(target_w, Qt.TransformationMode.SmoothTransformation))
                row.addWidget(label)

    def previous_page(self):
        if hasattr(self, "images"):
            self.page_index = max(0, self.page_index - (2 if self.mode.currentIndex() == 2 else 1))
            self.render_pages()

    def next_page(self):
        if hasattr(self, "images"):
            self.page_index = min(max(0, len(self.images) - 1), self.page_index + (2 if self.mode.currentIndex() == 2 else 1))
            self.render_pages()

    def change_chapter(self, index: int):
        self.chapter = self.chapters[index]
        self.load_pages()

    def change_background(self, index: int):
        colors = ["#030712", "#1f2937", "#f3f4f6"]
        self.scroll.setStyleSheet(f"QScrollArea {{ background: {colors[index]}; border: 0; }}")