from __future__ import annotations

import logging
import qtawesome as qta

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QPixmap, QIcon
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget, QGroupBox, QSpinBox
)

from api.client import MangaDexClient
from db.database import Database
from ui.reader import ReaderWindow
from utils.cache import image_bytes

STYLE = """
QMainWindow, QDialog { background-color: #0b0f19; color: #e2e8f0; }
QWidget { color: #e2e8f0; font-family: 'Segoe UI', system-ui, sans-serif; }

/* Menu Lateral */
QFrame#sidebar { background: #111827; border-right: 1px solid #1f2937; }
QPushButton#sidebar_btn { 
    background: transparent; border: 0; text-align: left; padding: 12px 18px; 
    font-size: 14px; font-weight: 600; color: #9ca3af; border-radius: 8px; 
}
QPushButton#sidebar_btn:hover { background: #1f2937; color: #60a5fa; }
QPushButton#sidebar_btn:checked { background: #3b82f6; color: #ffffff; }

/* Componentes de Entrada */
QLineEdit, QComboBox, QListWidget, QSpinBox { 
    background: #1f2937; border: 1px solid #374151; border-radius: 8px; 
    padding: 10px; color: #f3f4f6; selection-background-color: #3b82f6; 
}
QLineEdit:focus, QComboBox:focus, QListWidget:focus { border: 1px solid #60a5fa; outline: none; }

/* Botões Gerais */
QPushButton { 
    background: #1f2937; border: 1px solid #374151; border-radius: 8px; 
    padding: 10px 16px; color: #f3f4f6; font-weight: 600; 
}
QPushButton:hover { background: #374151; border-color: #4b5563; }
QPushButton#primary { background: #3b82f6; border: 0; color: #ffffff; }
QPushButton#primary:hover { background: #2563eb; }
QPushButton#icon_btn { background: transparent; border: 1px solid #374151; padding: 6px; }
QPushButton#icon_btn:hover { background: #1f2937; border-color: #60a5fa; }

/* Cards de Mangá */
QFrame#card { background: #111827; border: 1px solid #1f2937; border-radius: 12px; }
QFrame#card:hover { border: 1px solid #60a5fa; background: #1f2937; }
QLabel#muted { color: #9ca3af; font-size: 12px; }
QLabel#badge { background: #374151; border-radius: 6px; padding: 4px 8px; color: #93c5fd; font-size: 11px; }

QScrollArea { border: 0; background: transparent; }
QGroupBox { font-weight: 700; border: 1px solid #374151; border-radius: 8px; margin-top: 14px; padding-top: 14px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #60a5fa; }
"""


class Worker(QThread):
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn())
        except Exception as exc:
            logging.exception("Worker MangaKoro falhou")
            self.failed.emit(str(exc))


class CoverWorker(QThread):
    loaded = pyqtSignal(bytes)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            self.loaded.emit(image_bytes(self.url))
        except Exception:
            logging.exception("Falha ao carregar capa: %s", self.url)
            self.loaded.emit(b"")


class FilterDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Filtros Avançados")
        self.setMinimumWidth(450)
        layout = QVBoxLayout(self)

        rating_box = QGroupBox("Classificação de Conteúdo")
        rating_layout = QHBoxLayout(rating_box)
        self.ratings = {
            "safe": QCheckBox("Safe"),
            "suggestive": QCheckBox("Suggestive"),
            "erotica": QCheckBox("Erotica"),
            "pornographic": QCheckBox("+18")
        }
        for cb in self.ratings.values():
            rating_layout.addWidget(cb)
        self.ratings["safe"].setChecked(True)
        layout.addWidget(rating_box)

        form = QFormLayout()
        self.status = QComboBox()
        self.status.addItems(["Todos", "ongoing", "completed", "cancelled", "hiatus"])

        self.order = QComboBox()
        self.order.addItems(["Relevância", "Mais populares", "Última atualização", "Ano de lançamento"])

        self.languages = QComboBox()
        self.languages.addItems(["pt-br", "en", "es", "ja", "Todos"])

        self.included_tags = QLineEdit()
        self.included_tags.setPlaceholderText("IDs de tags (separados por vírgula)")

        self.excluded_tags = QLineEdit()
        self.excluded_tags.setPlaceholderText("IDs de tags a excluir")

        form.addRow("Status:", self.status)
        form.addRow("Ordenar por:", self.order)
        form.addRow("Idioma principal:", self.languages)
        form.addRow("Incluir Tags:", self.included_tags)
        form.addRow("Excluir Tags:", self.excluded_tags)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        order_map = {
            "Relevância": None,
            "Mais populares": "followedCount",
            "Última atualização": "latestUploadedChapter",
            "Ano de lançamento": "year"
        }
        selected_ratings = [key for key, cb in self.ratings.items() if cb.isChecked()]
        split_tags = lambda field: [tag.strip() for tag in field.text().split(",") if tag.strip()]

        lang = self.languages.currentText()
        languages_val = [] if lang == "Todos" else [lang]

        return {
            "content_ratings": selected_ratings,
            "status": [] if self.status.currentIndex() == 0 else [self.status.currentText()],
            "order": order_map[self.order.currentText()],
            "languages": languages_val,
            "included_tags": split_tags(self.included_tags),
            "excluded_tags": split_tags(self.excluded_tags)
        }


class MangaCard(QFrame):
    clicked = pyqtSignal(dict)

    def __init__(self, manga, favorite=False):
        super().__init__()
        self.manga = manga
        self.setObjectName("card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(190)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 10)

        self.cover = QLabel("Carregando...")
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setFixedSize(172, 245)
        self.cover.setStyleSheet("background:#1f2937; border-radius:8px; color:#9ca3af;")
        
        self.cover_worker = CoverWorker(manga.get("cover", ""))
        self.cover_worker.loaded.connect(self.set_cover)
        self.cover_worker.start()
        layout.addWidget(self.cover)

        title = QLabel(("★ " if favorite else "") + manga.get("title", "Sem título"))
        title.setWordWrap(True)
        title.setMaxLength = 40
        title.setStyleSheet("font-weight: 700; padding: 6px 2px 0px 2px; font-size: 13px; color: #f3f4f6;")
        layout.addWidget(title)

        meta = QLabel(f"{manga.get('status', 'unknown').capitalize()} • {manga.get('content_rating', 'safe').capitalize()}")
        meta.setObjectName("muted")
        meta.setStyleSheet("padding: 0 2px;")
        layout.addWidget(meta)

    def mousePressEvent(self, event):
        self.clicked.emit(self.manga)

    def set_cover(self, data):
        pix = QPixmap()
        pix.loadFromData(data)
        if not pix.isNull():
            self.cover.setPixmap(pix.scaled(self.cover.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MangaKoro")
        self.resize(1300, 860)
        self.setStyleSheet(STYLE)
        
        self.db = Database()
        self.client = MangaDexClient()
        self.client.db = self.db  # Passa referência de configs para o cliente
        self.filters = {}

        self.build_ui()
        self.load_catalog()

    def build_ui(self):
        root = QWidget()
        main_h_layout = QHBoxLayout(root)
        main_h_layout.setContentsMargins(0, 0, 0, 0)
        main_h_layout.setSpacing(0)

        # 1. Sidebar Navigation
        self.nav = QFrame()
        self.nav.setObjectName("sidebar")
        self.nav.setFixedWidth(240)
        self.nav.setVisible(False) 

        sidebar_layout = QVBoxLayout(self.nav)
        sidebar_layout.setContentsMargins(16, 24, 16, 24)
        sidebar_layout.setSpacing(10)

        # Usando Ícone no Logo
        brand = QLabel(" MangaKoro")
        brand.setStyleSheet("font-size: 22px; font-weight: 800; color: #60a5fa; margin-bottom: 20px;")
        sidebar_layout.addWidget(brand)

        # Botões com ícones Qtawesome
        self.btn_home = QPushButton(" Descobrir")
        self.btn_home.setIcon(qta.icon('fa5s.compass', color='#9ca3af'))
        
        self.btn_favs = QPushButton(" Salvos")
        self.btn_favs.setIcon(qta.icon('fa5s.bookmark', color='#9ca3af'))
        
        self.btn_hist = QPushButton(" Histórico")
        self.btn_hist.setIcon(qta.icon('fa5s.history', color='#9ca3af'))
        
        self.btn_sets = QPushButton(" Configurações")
        self.btn_sets.setIcon(qta.icon('fa5s.cog', color='#9ca3af'))

        self.btn_about = QPushButton(" Sobre o MangaKoro")
        self.btn_about.setIcon(qta.icon('fa5s.info-circle', color='#9ca3af'))

        for btn in (self.btn_home, self.btn_favs, self.btn_hist, self.btn_sets, self.btn_about):
            btn.setObjectName("sidebar_btn")
            btn.setIconSize(QSize(18, 18))
            sidebar_layout.addWidget(btn)

        self.btn_home.clicked.connect(self.load_catalog)
        self.btn_favs.clicked.connect(self.show_favorites)
        self.btn_hist.clicked.connect(self.show_history)
        self.btn_sets.clicked.connect(self.show_settings)
        self.btn_about.clicked.connect(self.show_about)

        sidebar_layout.addStretch()
        main_h_layout.addWidget(self.nav)

        # 2. Área de Conteúdo
        content_area = QWidget()
        content_v_layout = QVBoxLayout(content_area)
        content_v_layout.setContentsMargins(24, 20, 24, 20)
        content_v_layout.setSpacing(20)

        # Cabeçalho
        header = QHBoxLayout()
        toggle_menu = QPushButton()
        toggle_menu.setIcon(qta.icon('fa5s.bars', color='#f3f4f6'))
        toggle_menu.setObjectName("icon_btn")
        toggle_menu.setFixedSize(42, 42)
        toggle_menu.clicked.connect(self.toggle_nav)
        header.addWidget(toggle_menu)

        header.addStretch()

        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar mangá no catálogo...")
        self.search.setFixedWidth(400)
        self.search.returnPressed.connect(self.load_catalog)
        
        # Search Icon inside QLineEdit is a bit tricky, adding it to button instead
        search_btn = QPushButton(" Buscar")
        search_btn.setIcon(qta.icon('fa5s.search', color='#ffffff'))
        search_btn.setObjectName("primary")
        search_btn.clicked.connect(self.load_catalog)
        
        header.addWidget(self.search)
        header.addWidget(search_btn)

        filter_btn = QPushButton(" Filtros")
        filter_btn.setIcon(qta.icon('fa5s.sliders-h', color='#f3f4f6'))
        filter_btn.clicked.connect(self.show_filters)
        header.addWidget(filter_btn)

        content_v_layout.addLayout(header)

        # Título da Área
        self.heading = QLabel("Descobrir Leituras")
        self.heading.setStyleSheet("font-size: 28px; font-weight: 800; letter-spacing: -0.5px;")
        content_v_layout.addWidget(self.heading)

        self.status = QLabel("Conectando ao MangaDex...")
        self.status.setObjectName("muted")
        content_v_layout.addWidget(self.status)

        # Grid
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(18)
        self.scroll.setWidget(self.grid_host)
        content_v_layout.addWidget(self.scroll)

        main_h_layout.addWidget(content_area)
        self.setCentralWidget(root)

    def toggle_nav(self):
        self.nav.setVisible(not self.nav.isVisible())

    def clear_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def load_catalog(self):
        self.heading.setText("Descobrir Leituras")
        self.status.setText("Pesquisando na biblioteca MangaDex...")
        self.clear_grid()
        
        # Adiciona filtros automáticos caso nada tenha sido selecionado ainda
        search_filters = dict(self.filters)
        if "languages" not in search_filters or not search_filters["languages"]:
            pref_lang = self.db.setting("language", "pt-br")
            if pref_lang != "all":
                search_filters["languages"] = [pref_lang]

        self.worker = Worker(lambda: self.client.search(self.search.text(), **search_filters))
        self.worker.done.connect(self.populate)
        self.worker.failed.connect(self.show_error)
        self.worker.start()

    def populate(self, mangas):
        self.status.setText(f"{len(mangas)} obras encontradas")
        self.clear_grid()
        for index, manga in enumerate(mangas):
            card = MangaCard(manga, self.db.is_favorite(manga["id"]))
            card.clicked.connect(self.show_details)
            self.grid.addWidget(card, index // 5, index % 5)
        self.grid.setRowStretch((len(mangas) // 5) + 1, 1)

    def show_favorites(self):
        self.heading.setText("Sua Coleção (Salvos)")
        self.populate(self.db.favorites())

    def show_history(self):
        self.heading.setText("Últimas Leituras")
        items = self.db.history()
        self.populate([item["manga"] for item in items])

    def show_error(self, error):
        self.status.setText(error)
        QMessageBox.warning(self, "Erro de Conexão", error)

    def show_filters(self):
        dialog = FilterDialog(self)
        if dialog.exec():
            self.filters = dialog.values()
            self.load_catalog()

    def show_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Preferências MangaKoro")
        dialog.setMinimumWidth(420)
        form = QFormLayout(dialog)
        form.setSpacing(12)

        lang = QComboBox()
        lang.addItems(["pt-br", "en", "es", "ja"])
        lang.setCurrentText(self.db.setting("language", "pt-br"))

        sec_lang = QComboBox()
        sec_lang.addItems(["en", "pt-br", "es", "ja", "Nenhum"])
        sec_lang.setCurrentText(self.db.setting("secondary_language", "en"))

        quality = QComboBox()
        quality.addItems(["Original (Alta Resolução)", "Comprimida (Economia de Dados)"])
        quality.setCurrentText(self.db.setting("quality", "Original (Alta Resolução)"))

        limit = QSpinBox()
        limit.setRange(10, 100)
        limit.setValue(self.db.setting("search_limit", 24))
        
        adult = QCheckBox("Permitir e exibir conteúdo adulto (+18)")
        adult.setChecked(self.db.setting("adult", False))

        reader_mode = QComboBox()
        reader_mode.addItems(["Rolagem Contínua", "Página Única", "Página Dupla"])
        reader_mode.setCurrentIndex(self.db.setting("reader_mode", 0))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        form.addRow("Idioma Preferencial:", lang)
        form.addRow("Idioma Alternativo:", sec_lang)
        form.addRow("Qualidade Padrão:", quality)
        form.addRow("Modo de Leitura:", reader_mode)
        form.addRow("Limite de Busca:", limit)
        form.addRow(adult)
        form.addRow(buttons)

        if dialog.exec():
            self.db.set_setting("language", lang.currentText())
            self.db.set_setting("secondary_language", sec_lang.currentText())
            self.db.set_setting("quality", quality.currentText())
            self.db.set_setting("search_limit", limit.value())
            self.db.set_setting("adult", adult.isChecked())
            self.db.set_setting("reader_mode", reader_mode.currentIndex())

    def show_about(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("Sobre o MangaKoro")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText("<b>MangaKoro v1.0</b>")
        msg.setInformativeText(
            "Um leitor de mangás de alto desempenho e design elegante.<br><br>"
            "<b>API Base:</b> MangaDex (v5)<br>"
            "<b>Linguagem:</b> Python 3<br>"
            "<b>Bibliotecas:</b> PyQt6, Requests, QtAwesome<br><br>"
            "Feito de fãs, para fãs, com foco absoluto em desempenho e experiência de leitura."
        )
        msg.exec()

    def show_details(self, manga):
        dialog = QDialog(self)
        dialog.setWindowTitle(manga["title"])
        dialog.resize(850, 700)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)

        # Info Header
        header = QHBoxLayout()
        cover_lbl = QLabel("Carregando Capa...")
        cover_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover_lbl.setFixedSize(200, 280)
        cover_lbl.setStyleSheet("background: #1f2937; border-radius: 10px;")
        
        cover_worker = CoverWorker(manga.get("cover", ""))
        cover_worker.loaded.connect(lambda data: self.set_dialog_cover(cover_lbl, data))
        cover_worker.start()
        header.addWidget(cover_lbl)

        info = QVBoxLayout()
        info.setContentsMargins(10, 0, 0, 0)
        info.addWidget(QLabel(f"<h1 style='margin:0; font-size:24px; color:#f3f4f6;'>{manga['title']}</h1>"))
        
        info_tags = QLabel(
            f"<span style='color:#9ca3af;'>Status:</span> <b>{manga['status'].capitalize()}</b> &nbsp;|&nbsp; "
            f"<span style='color:#9ca3af;'>Etária:</span> <b>{manga['content_rating'].capitalize()}</b>"
        )
        info.addWidget(info_tags)
        info.addWidget(QLabel("<span style='color:#60a5fa; font-size: 13px;'>" + " • ".join(manga["tags"][:6]) + "</span>"))

        desc = QLabel(manga["description"])
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #d1d5db; margin-top: 10px; line-height: 1.4;")
        desc.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        scroll_desc = QScrollArea()
        scroll_desc.setWidget(desc)
        scroll_desc.setWidgetResizable(True)
        info.addWidget(scroll_desc)
        
        header.addLayout(info)
        layout.addLayout(header)

        fav_btn = QPushButton(" Remover da Coleção" if self.db.is_favorite(manga["id"]) else " Salvar na Coleção")
        fav_btn.setIcon(qta.icon('fa5s.bookmark', color='#f3f4f6'))
        fav_btn.setMinimumHeight(42)
        fav_btn.clicked.connect(lambda: (self.db.toggle_favorite(manga), fav_btn.setText(" Remover da Coleção" if self.db.is_favorite(manga["id"]) else " Salvar na Coleção")))
        layout.addWidget(fav_btn)

        # Capítulos Section
        chap_header = QHBoxLayout()
        chap_header.addWidget(QLabel("<h3 style='margin:0; color:#60a5fa;'>Capítulos Traduzidos</h3>"))
        
        load_all_btn = QPushButton(" Ver todos os idiomas")
        load_all_btn.setIcon(qta.icon('fa5s.globe', color='#f3f4f6'))
        load_all_btn.setStyleSheet("font-size: 12px; padding: 6px 12px; background: #374151;")
        chap_header.addWidget(load_all_btn)
        layout.addLayout(chap_header)

        chapters_list = QListWidget()
        chapters_list.setStyleSheet("font-size: 14px; padding: 5px;")
        layout.addWidget(chapters_list)

        status_chap = QLabel("Carregando banco de dados de capítulos...")
        status_chap.setObjectName("muted")
        layout.addWidget(status_chap)

        langs = [self.db.setting("language", "pt-br")]
        sec = self.db.setting("secondary_language", "en")
        if sec and sec != "Nenhum":
            langs.append(sec)

        def fetch_chaps(target_langs):
            status_chap.setText("Buscando capítulos via API...")
            chapters_list.clear()
            w = Worker(lambda: self.client.chapters(manga["id"], target_langs))
            w.done.connect(lambda res: self.fill_chapters(chapters_list, res, manga, status_chap, dialog))
            w.failed.connect(lambda err: status_chap.setText(f"Erro no servidor MangaDex: {err}"))
            w.start()
            dialog._cw = w

        load_all_btn.clicked.connect(lambda: fetch_chaps(["all"]))
        fetch_chaps(langs)
        dialog.exec()

    def set_dialog_cover(self, label, data):
        pix = QPixmap()
        pix.loadFromData(data)
        if pix.isNull():
            label.setText("Erro de Capa")
        else:
            pix = pix.scaled(200, 280, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            label.setPixmap(pix)

    def fill_chapters(self, widget, chapters, manga, status_label, dialog):
        widget.clear()
        if not chapters:
            status_label.setText("Vazio para o seu idioma. Tente 'Ver todos os idiomas'.")
            return

        status_label.setText(f"{len(chapters)} disponíveis (Dê duplo-clique no capítulo para ler)")
        for ch in chapters:
            item = QListWidgetItem(qta.icon('fa5s.book-open', color='#9ca3af'), f" Cap. {ch['chapter']} [{ch['language']}] - {ch['title']} ({ch['group']})")
            item.setData(Qt.ItemDataRole.UserRole, ch)
            item.setSizeHint(QSize(0, 36))
            widget.addItem(item)

        # Ao dar double click, passa a janela de dialog para fechá-la automaticamente
        widget.itemDoubleClicked.connect(lambda item: self.open_reader(manga, item.data(Qt.ItemDataRole.UserRole), chapters, dialog))

    def open_reader(self, manga, chapter, chapters, dialog):
        dialog.accept() # Fecha a janela modal do mangá
        reader = ReaderWindow(manga, chapter, chapters, self.db)
        reader.show()
        self._readers = getattr(self, "_readers", []) + [reader]