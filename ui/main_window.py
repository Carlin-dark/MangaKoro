from __future__ import annotations

import logging
import qtawesome as qta

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QUrl
from PyQt6.QtGui import QColor, QPixmap, QIcon, QDesktopServices
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

QFrame#sidebar { background: #111827; border-right: 1px solid #1f2937; }
QPushButton#sidebar_btn { 
    background: transparent; border: 0; text-align: left; padding: 12px 18px; 
    font-size: 14px; font-weight: 600; color: #9ca3af; border-radius: 8px; 
}
QPushButton#sidebar_btn:hover { background: #1f2937; color: #60a5fa; }
QPushButton#sidebar_btn:checked { background: #3b82f6; color: #ffffff; }

QLineEdit, QComboBox, QListWidget, QSpinBox { 
    background: #1f2937; border: 1px solid #374151; border-radius: 8px; 
    padding: 10px; color: #f3f4f6; selection-background-color: #3b82f6; 
}
QLineEdit:focus, QComboBox:focus, QListWidget:focus { border: 1px solid #60a5fa; outline: none; }

QPushButton { 
    background: #1f2937; border: 1px solid #374151; border-radius: 8px; 
    padding: 10px 16px; color: #f3f4f6; font-weight: 600; 
}
QPushButton:hover { background: #374151; border-color: #4b5563; }
QPushButton#primary { background: #3b82f6; border: 0; color: #ffffff; }
QPushButton#primary:hover { background: #2563eb; }
QPushButton#icon_btn { background: transparent; border: 1px solid #374151; padding: 6px; }
QPushButton#icon_btn:hover { background: #1f2937; border-color: #60a5fa; }

QFrame#card { background: #111827; border: 1px solid #1f2937; border-radius: 12px; }
QFrame#card:hover { border: 1px solid #60a5fa; background: #1f2937; }
QLabel#muted { color: #9ca3af; font-size: 12px; }
QLabel#badge { background: #374151; border-radius: 6px; padding: 4px 8px; color: #93c5fd; font-size: 11px; font-weight: bold;}

QScrollArea { border: 0; background: transparent; }
QGroupBox { font-weight: 700; border: 1px solid #374151; border-radius: 8px; margin-top: 14px; padding-top: 14px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #60a5fa; font-size: 16px;}
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
            logging.exception("Worker falhou")
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

        form.addRow("Status:", self.status)
        form.addRow("Ordenar por:", self.order)
        form.addRow("Idioma principal:", self.languages)
        form.addRow("Incluir Tags:", self.included_tags)
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
            "included_tags": split_tags(self.included_tags)
        }

class MangaCard(QFrame):
    clicked = pyqtSignal(dict)
    def __init__(self, manga, favorite=False):
        super().__init__()
        self.manga = manga
        self.setObjectName("card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(190)
        self.setFixedHeight(340) 

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
        title.setStyleSheet("font-weight: 700; padding: 4px 2px 0px 2px; font-size: 13px; color: #f3f4f6;")
        layout.addWidget(title)
        
        meta_text = f"{manga.get('status', 'unknown').capitalize()} • {manga.get('year', 'N/A')}"
        meta = QLabel(meta_text)
        meta.setObjectName("muted")
        layout.addWidget(meta)
        layout.addStretch()

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
        self.client.db = self.db 
        self.filters = {}
        self.current_offset = 0
        self.is_searching = False

        self.build_ui()
        self.load_home() # Carrega interface inicial categorizada

    def build_ui(self):
        root = QWidget()
        main_h_layout = QHBoxLayout(root)
        main_h_layout.setContentsMargins(0, 0, 0, 0)
        main_h_layout.setSpacing(0)

        # 1. Sidebar
        self.nav = QFrame()
        self.nav.setObjectName("sidebar")
        self.nav.setFixedWidth(240)
        self.nav.setVisible(True) 

        sidebar_layout = QVBoxLayout(self.nav)
        sidebar_layout.setContentsMargins(16, 24, 16, 24)
        sidebar_layout.setSpacing(10)

        brand = QLabel(" MangaKoro")
        brand.setStyleSheet("font-size: 22px; font-weight: 800; color: #60a5fa; margin-bottom: 20px;")
        sidebar_layout.addWidget(brand)

        self.btn_home = QPushButton(" Início (Categorias)")
        self.btn_home.setIcon(qta.icon('fa5s.home', color='#9ca3af'))
        
        self.btn_favs = QPushButton(" Salvos")
        self.btn_favs.setIcon(qta.icon('fa5s.bookmark', color='#9ca3af'))
        
        self.btn_hist = QPushButton(" Histórico")
        self.btn_hist.setIcon(qta.icon('fa5s.history', color='#9ca3af'))
        
        self.btn_sets = QPushButton(" Configurações")
        self.btn_sets.setIcon(qta.icon('fa5s.cog', color='#9ca3af'))

        for btn in (self.btn_home, self.btn_favs, self.btn_hist, self.btn_sets):
            btn.setObjectName("sidebar_btn")
            btn.setIconSize(QSize(18, 18))
            sidebar_layout.addWidget(btn)

        self.btn_home.clicked.connect(self.load_home)
        self.btn_favs.clicked.connect(self.show_favorites)
        self.btn_hist.clicked.connect(self.show_history)
        self.btn_sets.clicked.connect(self.show_settings)

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
        toggle_menu.clicked.connect(lambda: self.nav.setVisible(not self.nav.isVisible()))
        header.addWidget(toggle_menu)
        header.addStretch()

        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar mangá...")
        self.search.setFixedWidth(400)
        self.search.returnPressed.connect(lambda: self.trigger_search(0))
        
        search_btn = QPushButton(" Buscar")
        search_btn.setIcon(qta.icon('fa5s.search', color='#ffffff'))
        search_btn.setObjectName("primary")
        search_btn.clicked.connect(lambda: self.trigger_search(0))
        
        header.addWidget(self.search)
        header.addWidget(search_btn)

        filter_btn = QPushButton(" Filtros")
        filter_btn.setIcon(qta.icon('fa5s.sliders-h', color='#f3f4f6'))
        filter_btn.clicked.connect(self.show_filters)
        header.addWidget(filter_btn)

        content_v_layout.addLayout(header)

        self.heading = QLabel("Carregando...")
        self.heading.setStyleSheet("font-size: 28px; font-weight: 800; letter-spacing: -0.5px;")
        content_v_layout.addWidget(self.heading)

        self.status = QLabel("")
        self.status.setObjectName("muted")
        content_v_layout.addWidget(self.status)

        # Container Principal Scrollável
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.main_container = QWidget()
        self.main_layout = QVBoxLayout(self.main_container)
        self.scroll.setWidget(self.main_container)
        content_v_layout.addWidget(self.scroll)

        # Controles de Paginação (Ocultos por padrão)
        self.pagination_box = QWidget()
        pag_layout = QHBoxLayout(self.pagination_box)
        self.btn_prev = QPushButton(" Página Anterior")
        self.btn_prev.setIcon(qta.icon('fa5s.arrow-left', color='#ffffff'))
        self.btn_prev.clicked.connect(lambda: self.trigger_search(max(0, self.current_offset - self.db.setting("search_limit", 24))))
        
        self.btn_next = QPushButton(" Próxima Página ")
        self.btn_next.setIcon(qta.icon('fa5s.arrow-right', color='#ffffff'))
        self.btn_next.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.btn_next.clicked.connect(lambda: self.trigger_search(self.current_offset + self.db.setting("search_limit", 24)))
        
        pag_layout.addStretch()
        pag_layout.addWidget(self.btn_prev)
        pag_layout.addWidget(self.btn_next)
        pag_layout.addStretch()
        self.pagination_box.setVisible(False)
        content_v_layout.addWidget(self.pagination_box)

        main_h_layout.addWidget(content_area)
        self.setCentralWidget(root)

    def clear_container(self):
        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # --- CATEGORIAS INICIAIS ---
    def load_home(self):
        self.is_searching = False
        self.pagination_box.setVisible(False)
        self.search.clear()
        self.heading.setText("Início")
        self.status.setText("Buscando novidades no MangaDex...")
        self.clear_container()

        def fetch_categories():
            res = {}
            res["🔥 Em Alta (MangaDex)"] = self.client.search(order="followedCount", limit=15)
            res["⚔️ Ação e Aventura"] = self.client.search(included_tags=["391b0423-d847-456f-aff0-8b0cfc03066b"], limit=15)
            res["❤️ Romance"] = self.client.search(included_tags=["423e2eae-a7a2-4a8b-ac03-a8351462d71d"], limit=15)
            
            if self.db.setting("adult", False):
                res["🔞 Conteúdo Adulto (+18)"] = self.client.search(content_ratings=["pornographic", "erotica"], limit=15)
            return res

        self.worker = Worker(fetch_categories)
        self.worker.done.connect(self.render_home)
        self.worker.failed.connect(self.show_error)
        self.worker.start()

    def render_home(self, categories: dict):
        self.status.setText("Explorando por categorias")
        self.clear_container()
        
        for title, mangas in categories.items():
            if mangas:
                group = QGroupBox(title)
                group_layout = QVBoxLayout(group)
                
                h_scroll = QScrollArea()
                h_scroll.setWidgetResizable(True)
                h_scroll.setFixedHeight(370)
                h_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                h_scroll.setStyleSheet("QScrollArea { border: 0; background: transparent; }")
                
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
                
                for m in mangas:
                    card = MangaCard(m, self.db.is_favorite(m["id"]))
                    card.clicked.connect(self.show_details)
                    row_layout.addWidget(card)
                
                h_scroll.setWidget(row_widget)
                group_layout.addWidget(h_scroll)
                self.main_layout.addWidget(group)
        
        self.main_layout.addStretch()

    # --- RESULTADOS DE BUSCA & PAGINAÇÃO ---
    def trigger_search(self, offset: int = 0):
        self.is_searching = True
        self.current_offset = offset
        self.heading.setText("Resultados da Busca")
        self.status.setText(f"Pesquisando... (Página {offset // self.db.setting('search_limit', 24) + 1})")
        self.clear_container()
        
        search_filters = dict(self.filters)
        search_filters["limit"] = self.db.setting("search_limit", 24)

        self.worker = Worker(lambda: self.client.search(self.search.text(), offset=offset, **search_filters))
        self.worker.done.connect(self.render_grid)
        self.worker.failed.connect(self.show_error)
        self.worker.start()

    def render_grid(self, mangas):
        self.clear_container()
        grid = QGridLayout()
        grid.setSpacing(18)
        
        for index, manga in enumerate(mangas):
            card = MangaCard(manga, self.db.is_favorite(manga["id"]))
            card.clicked.connect(self.show_details)
            grid.addWidget(card, index // 5, index % 5)
            
        grid_widget = QWidget()
        grid_widget.setLayout(grid)
        self.main_layout.addWidget(grid_widget)
        self.main_layout.addStretch()

        if self.is_searching:
            self.pagination_box.setVisible(True)
            self.btn_prev.setEnabled(self.current_offset > 0)
            self.btn_next.setEnabled(len(mangas) == self.db.setting("search_limit", 24))
            self.status.setText(f"{len(mangas)} obras exibidas nesta página")

    def show_favorites(self):
        self.is_searching = False
        self.pagination_box.setVisible(False)
        self.heading.setText("Sua Coleção")
        self.render_grid(self.db.favorites())

    def show_history(self):
        self.is_searching = False
        self.pagination_box.setVisible(False)
        self.heading.setText("Últimas Leituras")
        items = self.db.history()
        self.render_grid([item["manga"] for item in items])

    def show_error(self, error):
        self.status.setText(error)
        QMessageBox.warning(self, "Erro de Conexão", error)

    def show_filters(self):
        dialog = FilterDialog(self)
        if dialog.exec():
            self.filters = dialog.values()
            self.trigger_search(0)

    def show_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Preferências MangaKoro")
        dialog.setMinimumWidth(450)
        form = QFormLayout(dialog)
        form.setSpacing(15)

        lang = QComboBox()
        lang.addItems(["pt-br", "en", "es", "ja"])
        lang.setCurrentText(self.db.setting("language", "pt-br"))

        quality = QComboBox()
        quality.addItems(["Original (Alta Resolução)", "Comprimida (Economia de Dados)"])
        quality.setCurrentText(self.db.setting("quality", "Original (Alta Resolução)"))

        limit = QSpinBox()
        limit.setRange(10, 100)
        limit.setValue(self.db.setting("search_limit", 24))
        
        adult = QCheckBox("Permitir conteúdo adulto (+18)")
        adult.setChecked(self.db.setting("adult", False))

        reader_mode = QComboBox()
        reader_mode.addItems(["Rolagem Contínua", "Página Única", "Página Dupla"])
        reader_mode.setCurrentIndex(self.db.setting("reader_mode", 0))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        form.addRow("Idioma Preferencial:", lang)
        form.addRow("Qualidade do Leitor:", quality)
        form.addRow("Modo de Leitura Padrão:", reader_mode)
        form.addRow("Resultados por Página:", limit)
        form.addRow(adult)
        form.addRow(buttons)

        if dialog.exec():
            self.db.set_setting("language", lang.currentText())
            self.db.set_setting("quality", quality.currentText())
            self.db.set_setting("search_limit", limit.value())
            self.db.set_setting("adult", adult.isChecked())
            self.db.set_setting("reader_mode", reader_mode.currentIndex())

    # --- MODAL DE DETALHES ---
    def show_details(self, manga):
        dialog = QDialog(self)
        dialog.setWindowTitle(manga["title"])
        dialog.resize(950, 750)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)

        header = QHBoxLayout()
        cover_lbl = QLabel("Capa...")
        cover_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover_lbl.setFixedSize(220, 310)
        cover_lbl.setStyleSheet("background: #1f2937; border-radius: 12px; border: 1px solid #374151;")
        
        cover_worker = CoverWorker(manga.get("cover", ""))
        cover_worker.loaded.connect(lambda data: self.set_dialog_cover(cover_lbl, data))
        cover_worker.start()
        header.addWidget(cover_lbl)

        info = QVBoxLayout()
        info.setContentsMargins(16, 0, 0, 0)
        info.addWidget(QLabel(f"<h1 style='margin:0; font-size:28px; color:#f3f4f6;'>{manga['title']}</h1>"))
        
        # Novas informações completas no Modal
        author_text = manga.get('author', 'Desconhecido')
        details_html = (
            f"<div style='font-size: 14px; line-height: 1.6;'>"
            f"<span style='color:#9ca3af;'>Autor:</span> <b style='color:#60a5fa;'>{author_text}</b> &nbsp;|&nbsp; "
            f"<span style='color:#9ca3af;'>Status:</span> <b>{manga['status'].capitalize()}</b> &nbsp;|&nbsp; "
            f"<span style='color:#9ca3af;'>Lançamento:</span> <b>{manga['year']}</b><br>"
            f"<span style='color:#9ca3af;'>Classificação:</span> <span id='badge'>{manga['content_rating'].upper()}</span>"
            f"</div>"
        )
        info.addWidget(QLabel(details_html))
        
        tags_str = " • ".join(manga["tags"])
        tags_lbl = QLabel(f"<span style='color:#93c5fd; font-size: 12px;'>{tags_str}</span>")
        tags_lbl.setWordWrap(True)
        info.addWidget(tags_lbl)

        desc = QLabel(manga["description"])
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #d1d5db; margin-top: 10px; line-height: 1.5; font-size: 14px;")
        desc.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        scroll_desc = QScrollArea()
        scroll_desc.setWidget(desc)
        scroll_desc.setWidgetResizable(True)
        info.addWidget(scroll_desc)
        
        # Botões de Ação Horizontal
        action_btns = QHBoxLayout()
        
        fav_btn = QPushButton(" Remover dos Salvos" if self.db.is_favorite(manga["id"]) else " Salvar Coleção")
        fav_btn.setIcon(qta.icon('fa5s.bookmark', color='#f3f4f6'))
        fav_btn.setMinimumHeight(45)
        fav_btn.clicked.connect(lambda: (self.db.toggle_favorite(manga), fav_btn.setText(" Remover dos Salvos" if self.db.is_favorite(manga["id"]) else " Salvar Coleção")))
        
        web_btn = QPushButton(" Abrir no MangaDex")
        web_btn.setIcon(qta.icon('fa5s.external-link-alt', color='#f3f4f6'))
        web_btn.setMinimumHeight(45)
        web_btn.setObjectName("primary")
        web_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(f"https://mangadex.org/title/{manga['id']}")))

        action_btns.addWidget(fav_btn)
        action_btns.addWidget(web_btn)
        info.addLayout(action_btns)

        header.addLayout(info)
        layout.addLayout(header)

        # Capítulos
        chap_header = QHBoxLayout()
        chap_header.addWidget(QLabel("<h3 style='margin-top:15px; color:#60a5fa;'>Lista de Capítulos</h3>"))
        
        load_all_btn = QPushButton(" Ver todos os idiomas")
        load_all_btn.setIcon(qta.icon('fa5s.globe', color='#f3f4f6'))
        load_all_btn.setStyleSheet("padding: 6px 12px; background: #374151;")
        chap_header.addWidget(load_all_btn)
        layout.addLayout(chap_header)

        chapters_list = QListWidget()
        chapters_list.setStyleSheet("font-size: 14px; padding: 5px;")
        layout.addWidget(chapters_list)

        status_chap = QLabel("Carregando banco de dados...")
        status_chap.setObjectName("muted")
        layout.addWidget(status_chap)

        langs = [self.db.setting("language", "pt-br")]

        def fetch_chaps(target_langs):
            status_chap.setText("Buscando capítulos via API...")
            chapters_list.clear()
            w = Worker(lambda: self.client.chapters(manga["id"], target_langs))
            w.done.connect(lambda res: self.fill_chapters(chapters_list, res, manga, status_chap, dialog))
            w.failed.connect(lambda err: status_chap.setText(f"Erro: {err}"))
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
            pix = pix.scaled(220, 310, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            label.setPixmap(pix)

    def fill_chapters(self, widget, chapters, manga, status_label, dialog):
        widget.clear()
        if not chapters:
            status_label.setText("Nenhum capítulo neste idioma. Tente 'Ver todos os idiomas'.")
            return

        status_label.setText(f"{len(chapters)} capítulos disponíveis (Dê duplo-clique para ler)")
        for ch in chapters:
            item = QListWidgetItem(qta.icon('fa5s.book-open', color='#9ca3af'), f" Cap. {ch['chapter']} [{ch['language']}] - {ch['title']} ({ch['group']})")
            item.setData(Qt.ItemDataRole.UserRole, ch)
            item.setSizeHint(QSize(0, 36))
            widget.addItem(item)

        widget.itemDoubleClicked.connect(lambda item: self.open_reader(manga, item.data(Qt.ItemDataRole.UserRole), chapters, dialog))

    def open_reader(self, manga, chapter, chapters, dialog):
        dialog.accept()
        reader = ReaderWindow(manga, chapter, chapters, self.db)
        reader.show()
        self._readers = getattr(self, "_readers", []) + [reader]