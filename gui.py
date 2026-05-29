import csv
import logging
import os
import re
import sys
import tempfile
import traceback
import webbrowser
from datetime import datetime, timedelta
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QTableView,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import (
    CONFIG_PATH,
    LOG_PATH,
    NEWSPAPERS,
    load_body_keywords,
    load_config,
    load_exclude_keywords,
    normalize_keywords,
    save_body_keywords,
    save_exclude_keywords,
    update_config,
)
from crawler import NaverPaperCrawler
from database import Database
from online_crawler import crawl_online_candidates


logger = logging.getLogger(__name__)


class ReportViewerDialog(QDialog):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("완성된 아침보고 결과물 (클립보드에 자동 복사됨)")
        self.resize(720, 560)
        layout = QVBoxLayout(self)
        
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(text)
        layout.addWidget(self.text_edit, 1)
        
        button_row = QHBoxLayout()
        copy_btn = QPushButton("클립보드에 다시 복사")
        copy_btn.clicked.connect(self.copy_to_clipboard)
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        button_row.addStretch(1)
        button_row.addWidget(copy_btn)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)
        
    def copy_to_clipboard(self):
        QApplication.clipboard().setText(self.text_edit.toPlainText())
        QMessageBox.information(self, "알림", "클립보드에 복사되었습니다.")


def format_display_time(value):
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%m-%d %H:%M")
    except Exception:
        return str(value)


def section_sort_key(value):
    text = value or ""
    match = re.search(r"(\d+)", text)
    if match:
        return int(match.group(1)), text
    return 9999, text


class SortableItem(QStandardItem):
    def __lt__(self, other):
        left = self.data(Qt.UserRole)
        right = other.data(Qt.UserRole) if other else None
        if left is not None and right is not None:
            return left < right
        return super().__lt__(other)


APP_STYLESHEET = """
QMainWindow {
    background: #15183C;
}

QWidget {
    font-family: "Malgun Gothic", "Segoe UI", sans-serif;
    font-size: 10pt;
    color: #202334;
}

QTabWidget::pane {
    border: 1px solid #D8DCE8;
    background: #F4F6FB;
}

QTabBar::tab {
    background: #29153C;
    color: #EDEBFF;
    padding: 10px 18px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background: #7742CC;
    color: #FFFFFF;
}

QTabBar::tab:hover {
    background: #A193EA;
    color: #15183C;
}

QLabel {
    color: #202334;
    font-weight: 600;
}

QCheckBox {
    color: #202334;
    font-weight: 600;
    spacing: 7px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
}

QCheckBox::indicator:unchecked {
    background: #FFFFFF;
    border: 1px solid #C9CEDA;
    border-radius: 3px;
}

QCheckBox::indicator:checked {
    background: #7742CC;
    border: 1px solid #7742CC;
    border-radius: 3px;
}

QLineEdit,
QComboBox,
QDateEdit {
    background: #FFFFFF;
    color: #202334;
    border: 1px solid #C9CEDA;
    border-radius: 6px;
    padding: 7px 9px;
    min-height: 20px;
}

QLineEdit:focus,
QComboBox:focus,
QDateEdit:focus,
QTextEdit:focus,
QTableView:focus {
    border: 1px solid #4664E6;
}

QComboBox::drop-down,
QDateEdit::drop-down {
    background: #7742CC;
    border: none;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    width: 28px;
}

QComboBox QAbstractItemView {
    background: #FFFFFF;
    color: #202334;
    selection-background-color: #4664E6;
    selection-color: #FFFFFF;
    border: 1px solid #C9CEDA;
}

QPushButton {
    background: #7742CC;
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 8px 14px;
    font-weight: 700;
}

QPushButton:hover {
    background: #A193EA;
    color: #15183C;
}

QPushButton:pressed {
    background: #4664E6;
    color: #FFFFFF;
}

QPushButton:disabled {
    background: #B8BDCB;
    color: #F4F6FB;
}

QTableView {
    background: #FFFFFF;
    alternate-background-color: #F7F8FC;
    color: #1F2430;
    gridline-color: #E3E6EE;
    border: 1px solid #C9CEDA;
    border-radius: 6px;
    selection-background-color: #4664E6;
    selection-color: #FFFFFF;
}

QHeaderView::section {
    background: #29153C;
    color: #FFFFFF;
    padding: 8px;
    border: none;
    border-right: 1px solid #49325E;
    font-weight: 700;
}

QTextEdit {
    background: #FFFFFF;
    color: #1F2430;
    border: 1px solid #C9CEDA;
    border-radius: 6px;
    padding: 10px;
    selection-background-color: #4664E6;
    selection-color: #FFFFFF;
}

QSplitter::handle {
    background: #D8DCE8;
}

QStatusBar {
    background: #29153C;
    color: #FFFFFF;
}

QMessageBox {
    background: #F4F6FB;
}

QMessageBox QLabel {
    color: #202334;
    font-weight: 500;
}
"""


class BodyFetchWorker(QThread):
    progress = Signal(int, int)
    finished = Signal(int)
    failed = Signal(str)

    def __init__(self, article_ids, force=False):
        super().__init__()
        self.article_ids = article_ids
        self.force = force

    def run(self):
        try:
            crawler = NaverPaperCrawler()
            done = 0
            for article_id in self.article_ids:
                crawler.fetch_and_store_body(article_id, self.force)
                done += 1
                self.progress.emit(done, len(self.article_ids))
            self.finished.emit(done)
        except Exception:
            logger.exception("Body fetch worker failed")
            self.failed.emit(traceback.format_exc())


class ListCrawlWorker(QThread):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, date, fetch_first_page_bodies=False):
        super().__init__()
        self.date = date
        self.fetch_first_page_bodies = fetch_first_page_bodies

    def run(self):
        try:
            crawler = NaverPaperCrawler()
            result = crawler.crawl_date(
                self.date,
                fetch_first_page_bodies=self.fetch_first_page_bodies,
            )
            self.finished.emit(result)
        except Exception:
            logger.exception("List crawl worker failed")
            self.failed.emit(traceback.format_exc())


class RangeCrawlWorker(QThread):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, dates):
        super().__init__()
        self.dates = dates

    def run(self):
        try:
            crawler = NaverPaperCrawler()
            result = {"total": 0, "inserted": 0, "body_fetched": 0, "pages": 0, "failures": []}
            for date in self.dates:
                item = crawler.crawl_date(date)
                for key in ["total", "inserted", "body_fetched", "pages"]:
                    result[key] += item.get(key, 0)
                result["failures"].extend(item.get("failures", []))
            self.finished.emit(result)
        except Exception:
            logger.exception("Range crawl worker failed")
            self.failed.emit(traceback.format_exc())


class OnlineCrawlWorker(QThread):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, start_dt=None, end_dt=None, exclude_keywords=None):
        super().__init__()
        self.start_dt = start_dt
        self.end_dt = end_dt
        self.exclude_keywords = exclude_keywords

    def run(self):
        try:
            result = crawl_online_candidates(
                start_dt=self.start_dt,
                end_dt=self.end_dt,
                exclude_keywords=self.exclude_keywords,
            )
            self.finished.emit(result)
        except Exception:
            logger.exception("Online crawl worker failed")
            self.failed.emit(traceback.format_exc())


class KeywordBodyDialog(QDialog):
    def __init__(self, summary, keywords, exclude_keywords=None, parent=None):
        super().__init__(parent)
        self.action = "skip"
        self.setWindowTitle("기본 검색어 설정")
        self.resize(520, 380)

        layout = QVBoxLayout(self)
        if summary:
            summary_label = QLabel(summary)
            summary_label.setWordWrap(True)
            layout.addWidget(summary_label)

        guide = QLabel("수집 및 검색에 기본으로 사용될 키워드들을 입력하세요. 쉼표(,) 또는 줄바꿈으로 구분합니다.")
        guide.setWordWrap(True)
        layout.addWidget(guide)

        self.keyword_text = QTextEdit()
        self.keyword_text.setPlainText(", ".join(keywords))
        layout.addWidget(QLabel("포함 키워드"))
        layout.addWidget(self.keyword_text, 1)

        self.exclude_keyword_text = QTextEdit()
        self.exclude_keyword_text.setMaximumHeight(80)
        self.exclude_keyword_text.setPlainText(", ".join(exclude_keywords or []))
        layout.addWidget(QLabel("제외 키워드"))
        layout.addWidget(self.exclude_keyword_text)

        button_row = QHBoxLayout()
        collect_btn = QPushButton("적용 및 즉시 검색")
        save_skip_btn = QPushButton("설정 저장")
        skip_btn = QPushButton("취소")
        collect_btn.clicked.connect(lambda: self.finish("collect"))
        save_skip_btn.clicked.connect(lambda: self.finish("save_skip"))
        skip_btn.clicked.connect(lambda: self.finish("skip"))
        button_row.addStretch(1)
        button_row.addWidget(skip_btn)
        button_row.addWidget(save_skip_btn)
        button_row.addWidget(collect_btn)
        layout.addLayout(button_row)

    def finish(self, action):
        self.action = action
        self.accept()

    def keywords(self):
        raw = self.keyword_text.toPlainText().replace(",", "\n").splitlines()
        return normalize_keywords(raw)

    def exclude_keywords(self):
        raw = self.exclude_keyword_text.toPlainText().replace(",", "\n").splitlines()
        return normalize_keywords(raw)


class MainWindow(QMainWindow):
    HEADERS = ["선택", "ID", "날짜", "유형", "언론사", "게재면/분야", "게재시간", "제목", "링크"]

    def __init__(self):
        super().__init__()
        self.db = Database()
        self.db.cleanup_old_uncategorized_caches() # Clean old cache on startup
        self.current_rows = []
        self.worker = None
        self.list_worker = None
        self.online_worker = None
        self.pending_keyword_lookup = None
        self.progress_dialog = None
        
        # Debounce timer for auto-search on datetime edit changes
        self.date_change_timer = QTimer(self)
        self.date_change_timer.setSingleShot(True)
        self.date_change_timer.timeout.connect(self.search)
        
        self.setWindowTitle("네이버 신문게재 기사 수집기")
        self.resize(1280, 760)
        self.setStyleSheet(APP_STYLESHEET)
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self._build_articles_tab()
        self._build_settings_tab()
        self.refresh_categories()
        
        # Load saved custom keywords or default keywords if none saved
        from config import load_body_keywords
        self.keyword_edit.setText(", ".join(load_body_keywords()))
        
        self.search()
        
        # Bind Ctrl+S shortcut for quick saving
        from PySide6.QtGui import QKeySequence, QShortcut
        self.save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self.save_shortcut.activated.connect(self.save_current_article_summary_and_category)
        
        QTimer.singleShot(1200, self.start_startup_online_refresh)

    def _build_articles_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        filters = QGridLayout()
        from PySide6.QtWidgets import QDateTimeEdit
        
        self.start_date_edit = QDateTimeEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setKeyboardTracking(False)
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        
        self.end_date_edit = QDateTimeEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setKeyboardTracking(False)
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        
        # Default start=12 hours ago, end=now
        now = datetime.now()
        start = now - timedelta(hours=12)
        from PySide6.QtCore import QDateTime
        self.start_date_edit.setDateTime(QDateTime.fromMSecsSinceEpoch(int(start.timestamp() * 1000)))
        self.end_date_edit.setDateTime(QDateTime.fromMSecsSinceEpoch(int(now.timestamp() * 1000)))
        
        self.date_edit = self.start_date_edit

        self.newspaper_combo = QComboBox()
        self.newspaper_combo.setEditable(True)
        self.newspaper_combo.addItem("전체")
        self.newspaper_combo.addItems(NEWSPAPERS.keys())

        self.article_type_combo = QComboBox()
        self.article_type_combo.addItems(["전체", "지면", "방송", "통신", "온라인"])

        self.section_combo = QComboBox()
        self.section_combo.setEditable(True)
        self.section_combo.addItem("")

        self.keyword_edit = QLineEdit()
        self.keyword_edit.setPlaceholderText("검색 키워드 (여러 개인 경우 쉼표나 공백으로 구분: OR 검색)")
        self.keyword_edit.setMinimumWidth(420)
        self.keyword_edit.setText(", ".join(load_body_keywords()))

        self.exclude_keyword_edit = QLineEdit()
        self.exclude_keyword_edit.setPlaceholderText("제외 키워드")
        self.exclude_keyword_edit.setMinimumWidth(260)
        self.exclude_keyword_edit.setText(", ".join(load_exclude_keywords()))

        self.scope_combo = QComboBox()
        self.scope_combo.addItem("제목", "title")
        self.scope_combo.addItem("제목+요약", "title_summary")
        self.scope_combo.addItem("제목+요약+본문", "title_summary_body")

        self.category_filter_combo = QComboBox()
        self.category_filter_combo.addItem("전체")
        
        # User strict report scope filter checkbox
        self.strict_scope_checkbox = QCheckBox("보고 범위만 보기 (지면/연합/타사 단독)")
        self.strict_scope_checkbox.setChecked(True)
        self.strict_scope_checkbox.stateChanged.connect(self.trigger_auto_search)

        self.include_foreign_checkbox = QCheckBox("해외 기사 포함")
        self.include_foreign_checkbox.setChecked(False)
        self.include_foreign_checkbox.stateChanged.connect(self.trigger_auto_search)

        self.quick_time_combo = QComboBox()
        self.quick_time_combo.addItems(["직접 설정", "-1시간", "-6시간", "-12시간", "-24시간"])
        self.quick_time_combo.currentTextChanged.connect(self.handle_quick_time_changed)
        
        self.start_date_edit.dateTimeChanged.connect(lambda: self.quick_time_combo.setCurrentIndex(0))
        self.end_date_edit.dateTimeChanged.connect(lambda: self.quick_time_combo.setCurrentIndex(0))
        
        # Connect automatic search trigger on datetime changes
        self.start_date_edit.dateTimeChanged.connect(self.trigger_auto_search)
        self.end_date_edit.dateTimeChanged.connect(self.trigger_auto_search)

        search_btn = QPushButton("검색")
        search_btn.clicked.connect(self.search_with_auto_crawl)
        keyword_body_top_btn = QPushButton("기본 검색어 설정")
        keyword_body_top_btn.clicked.connect(self.fetch_keyword_bodies)

        # Row 0: Time and Quick filters
        filters.addWidget(QLabel("시작일시"), 0, 0)
        filters.addWidget(self.start_date_edit, 0, 1)
        filters.addWidget(QLabel("종료일시"), 0, 2)
        filters.addWidget(self.end_date_edit, 0, 3)
        filters.addWidget(QLabel("시간 설정"), 0, 4)
        filters.addWidget(self.quick_time_combo, 0, 5)
        
        # Row 1: Source & Scope filters
        filters.addWidget(QLabel("언론사"), 1, 0)
        filters.addWidget(self.newspaper_combo, 1, 1)
        filters.addWidget(QLabel("유형"), 1, 2)
        filters.addWidget(self.article_type_combo, 1, 3)
        filters.addWidget(QLabel("게재면/분야"), 1, 4)
        filters.addWidget(self.section_combo, 1, 5)
        filters.addWidget(QLabel("범위"), 1, 6)
        filters.addWidget(self.scope_combo, 1, 7)
        
        # Row 2: Strict scope, Keywords & Actions
        filters.addWidget(self.strict_scope_checkbox, 2, 0)
        filters.addWidget(self.include_foreign_checkbox, 2, 1)
        filters.addWidget(QLabel("키워드"), 2, 2)
        filters.addWidget(self.keyword_edit, 2, 3, 1, 2)
        filters.addWidget(self.exclude_keyword_edit, 2, 5)
        filters.addWidget(keyword_body_top_btn, 2, 6)
        filters.addWidget(search_btn, 2, 7)

        filters.setColumnStretch(1, 1)
        filters.setColumnStretch(3, 1)
        filters.setColumnStretch(5, 1)
        filters.setColumnStretch(7, 1)
        layout.addLayout(filters)

        self.keyword_edit.returnPressed.connect(self.search_with_auto_crawl)
        self.exclude_keyword_edit.returnPressed.connect(self.search_with_auto_crawl)
        self.article_type_combo.currentTextChanged.connect(self.handle_article_type_changed)
        self.section_combo.lineEdit().returnPressed.connect(self.search_with_auto_crawl)
        self.newspaper_combo.lineEdit().returnPressed.connect(self.search_with_auto_crawl)

        splitter = QSplitter(Qt.Vertical)
        
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(6)
        
        self.select_all_checkbox = QCheckBox("기사 전체 선택 / 해제")
        self.select_all_checkbox.stateChanged.connect(self.handle_select_all_changed)
        table_layout.addWidget(self.select_all_checkbox)
        
        self.table = QTableView()
        self.model = QStandardItemModel(0, len(self.HEADERS))
        self.model.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setModel(self.model)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.clicked.connect(self.handle_table_click)
        self.table.doubleClicked.connect(self.handle_table_double_click)
        self.table.selectionModel().selectionChanged.connect(self.handle_selection_changed)
        
        self.table.setColumnHidden(1, True) # ID is column 1 now
        self.table.setColumnWidth(0, 55)   # Checkbox column width
        self.table.setColumnWidth(7, 420)  # Title column is index 7
        self.table.setColumnWidth(8, 360)  # Link column is index 8
        self.table.sortByColumn(2, Qt.DescendingOrder) # Date is index 2
        
        table_layout.addWidget(self.table, 1)
        splitter.addWidget(table_container)

        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        self.detail_title = QLabel("선택한 기사 없음")
        self.detail_title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        
        self.summary_label = QLabel("보고 요약문 (사용자 직접 편집 및 저장 가능):")
        self.detail_summary = QTextEdit()
        self.detail_summary.setReadOnly(False)  # Make it editable
        self.detail_summary.setMaximumHeight(75)
        self.detail_summary.setPlaceholderText("기사의 핵심 팩트 및 보고 요약문을 기입하세요. 미기입 시 자동으로 추출 요약이 제안됩니다.")
        
        category_row = QHBoxLayout()
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        
        apply_category_btn = QPushButton("사안(카테고리)/요약 저장")
        apply_category_btn.clicked.connect(self.save_current_article_summary_and_category)
        
        bulk_category_btn = QPushButton("다중 선택 카테고리 일괄 부여")
        bulk_category_btn.clicked.connect(self.apply_category_to_selected)
        
        category_row.addWidget(QLabel("사안(카테고리)"))
        category_row.addWidget(self.category_combo, 1)
        category_row.addWidget(apply_category_btn)
        category_row.addWidget(bulk_category_btn)
        category_row.addWidget(QLabel("사안 필터"))
        category_row.addWidget(self.category_filter_combo)

        action_row = QHBoxLayout()
        report_btn = QPushButton("작성 (본문 수집 + 보고서 출력)")
        open_url_btn = QPushButton("본문 TXT 열기")
        export_csv_btn = QPushButton("CSV 내보내기")
        save_txt_btn = QPushButton("TXT 저장")
        
        report_btn.clicked.connect(self.generate_report_flow)
        open_url_btn.clicked.connect(self.open_selected_body_txt)
        export_csv_btn.clicked.connect(self.export_csv)
        save_txt_btn.clicked.connect(self.save_selected_txt)
        
        for btn in [
            report_btn,
            open_url_btn,
            export_csv_btn,
            save_txt_btn,
        ]:
            action_row.addWidget(btn)
        action_row.addStretch(1)

        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.summary_label)
        detail_layout.addWidget(self.detail_summary)
        detail_layout.addLayout(category_row)
        detail_layout.addLayout(action_row)
        splitter.addWidget(detail_widget)
        splitter.setSizes([550, 170])
        layout.addWidget(splitter, 1)
        self.tabs.addTab(tab, "기사")

    def _build_settings_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()
        self.body_keywords_edit = QTextEdit()
        self.body_keywords_edit.setMaximumHeight(120)
        self.body_keywords_edit.setPlainText(", ".join(load_body_keywords()))
        form.addRow("본문 자동 수집 키워드", self.body_keywords_edit)
        self.exclude_keywords_edit = QTextEdit()
        self.exclude_keywords_edit.setMaximumHeight(90)
        self.exclude_keywords_edit.setPlainText(", ".join(load_exclude_keywords()))
        form.addRow("제외 키워드", self.exclude_keywords_edit)
        save_btn = QPushButton("설정 저장")
        save_btn.clicked.connect(self.save_settings)
        layout.addLayout(form)
        layout.addWidget(save_btn)
        layout.addWidget(QLabel(f"설정 파일: {CONFIG_PATH}"))
        layout.addWidget(QLabel(f"오류 로그: {LOG_PATH}"))
        layout.addStretch(1)
        self.tabs.addTab(tab, "환경 설정")

    def refresh_categories(self):
        categories = self.db.distinct_categories()
        current_filter = self.category_filter_combo.currentText() if hasattr(self, "category_filter_combo") else "전체"
        self.category_filter_combo.blockSignals(True)
        self.category_filter_combo.clear()
        self.category_filter_combo.addItem("전체")
        self.category_filter_combo.addItem("(미지정)")
        self.category_filter_combo.addItems(categories)
        index = self.category_filter_combo.findText(current_filter)
        self.category_filter_combo.setCurrentIndex(index if index >= 0 else 0)
        self.category_filter_combo.blockSignals(False)

        current = self.category_combo.currentText() if hasattr(self, "category_combo") else ""
        self.category_combo.clear()
        self.category_combo.addItem("")
        self.category_combo.addItems(categories)
        completer = QCompleter(categories, self.category_combo)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.category_combo.setCompleter(completer)
        self.category_combo.setCurrentText(current)

        section_current = self.section_combo.currentText()
        self.section_combo.clear()
        self.section_combo.addItem("")
        self.section_combo.addItems(self.db.distinct_sections())
        self.section_combo.setCurrentText(section_current)

    def trigger_auto_search(self):
        self.date_change_timer.start(500)

    def handle_quick_time_changed(self, text):
        if text == "직접 설정":
            return
        now = datetime.now()
        if text == "-1시간":
            start = now - timedelta(hours=1)
        elif text == "-6시간":
            start = now - timedelta(hours=6)
        elif text == "-12시간":
            start = now - timedelta(hours=12)
        elif text == "-24시간":
            start = now - timedelta(hours=24)
        else:
            return
        
        from PySide6.QtCore import QDateTime
        self.start_date_edit.blockSignals(True)
        self.end_date_edit.blockSignals(True)
        self.start_date_edit.setDateTime(QDateTime.fromMSecsSinceEpoch(int(start.timestamp() * 1000)))
        self.end_date_edit.setDateTime(QDateTime.fromMSecsSinceEpoch(int(now.timestamp() * 1000)))
        self.start_date_edit.blockSignals(False)
        self.end_date_edit.blockSignals(False)
        self.search()

    def selected_datetime_range_str(self):
        start_qdt = self.start_date_edit.dateTime()
        end_qdt = self.end_date_edit.dateTime()
        if start_qdt > end_qdt:
            self.start_date_edit.blockSignals(True)
            self.end_date_edit.blockSignals(True)
            self.start_date_edit.setDateTime(end_qdt)
            self.end_date_edit.setDateTime(start_qdt)
            self.start_date_edit.blockSignals(False)
            self.end_date_edit.blockSignals(False)
            self.statusBar().showMessage("시작 시간과 종료 시간이 바뀌어 자동으로 바로잡았습니다.", 5000)
            start_qdt, end_qdt = end_qdt, start_qdt
        return start_qdt.toString("yyyy-MM-dd HH:mm:00"), end_qdt.toString("yyyy-MM-dd HH:mm:59")

    def selected_date_range(self):
        start_qdt = self.start_date_edit.dateTime()
        end_qdt = self.end_date_edit.dateTime()
        if start_qdt > end_qdt:
            start_qdt, end_qdt = end_qdt, start_qdt
        return start_qdt.toString("yyyyMMdd"), end_qdt.toString("yyyyMMdd")

    def search(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.statusBar().showMessage("기사를 검색하는 중입니다...")
        QApplication.processEvents()
        try:
            self.active_keyword_filter = None
            dt_from, dt_to = self.selected_datetime_range_str()
            rows = self.db.search_articles(
                newspaper=self.newspaper_combo.currentText(),
                paper_section=self.section_combo.currentText().strip(),
                keyword=self.keyword_edit.text().strip(),
                search_scope=self.scope_combo.currentData(),
                category=self.category_filter_combo.currentText(),
                article_type=self.article_type_combo.currentText(),
                exclude_keywords=normalize_keywords(self.exclude_keyword_edit.text().replace(",", "\n").splitlines()),
                strict_report_scope=self.strict_scope_checkbox.isChecked(),
                datetime_from=dt_from,
                datetime_to=dt_to,
                exclude_foreign=not self.include_foreign_checkbox.isChecked(),
            )
            self.show_rows(rows)
            self.statusBar().showMessage(f"검색 완료: {len(rows)}건의 기사 로드됨", 4000)
        except Exception as exc:
            self.statusBar().showMessage("검색 중 오류 발생", 4000)
            logger.exception("Search failed")
            raise exc
        finally:
            QApplication.restoreOverrideCursor()

    def handle_article_type_changed(self, *_):
        if not self.active_keyword_filter:
            return
        keywords, exclude_keywords = self.active_keyword_filter
        self.show_keyword_lookup_rows(keywords, exclude_keywords, notify=False)

    def search_with_auto_crawl(self):
        dates = self.selected_dates()
        if len(dates) > 31:
            answer = QMessageBox.question(
                self,
                "기간 수집 확인",
                f"{len(dates)}일치 신문 목록을 확인합니다. 계속할까요?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        missing = [date for date in dates if not self.db.has_articles_for_date(date)]
        if missing:
            if self.list_worker and self.list_worker.isRunning():
                self.info("목록 수집이 이미 진행 중입니다.")
                return
            self.show_progress(f"신문 목록 수집 중입니다. ({len(missing)}일)", 0, 0)
            self.list_worker = RangeCrawlWorker(missing)
            self.list_worker.finished.connect(self.range_crawl_finished)
            self.list_worker.failed.connect(lambda msg: self.worker_failed("목록 수집 중 오류가 발생했습니다.", msg))
            self.list_worker.start()
            return

        # If paper articles already exist in local DB:
        # Check if the query range <= 3 days, and trigger a background online crawl if it was never run.
        if len(dates) <= 3:
            start_str, end_str = self.selected_date_range()
            start_dt = datetime.strptime(start_str, "%Y%m%d") - timedelta(days=1)
            start_dt = start_dt.replace(hour=18, minute=0, second=0)
            end_dt = datetime.strptime(end_str, "%Y%m%d").replace(hour=6, minute=0, second=0)
            
            from online_crawler import online_run_key
            run_key = online_run_key(start_dt, end_dt)
            if not self.db.crawl_run_completed(run_key):
                self.start_online_worker(start_dt, end_dt, load_exclude_keywords(), silent=True)

        self.search()

    def range_crawl_finished(self, result):
        self.close_progress()
        self.refresh_categories()
        self.search()
        self.statusBar().showMessage(
            f"목록 수집 완료: 확인 {result['total']}건, 신규 {result['inserted']}건",
            5000,
        )

    def selected_dates(self):
        start, end = self.selected_date_range()
        current = datetime.strptime(start, "%Y%m%d")
        last = datetime.strptime(end, "%Y%m%d")
        dates = []
        while current <= last:
            dates.append(current.strftime("%Y%m%d"))
            current += timedelta(days=1)
        return dates

    def show_rows(self, rows):
        self.table.setSortingEnabled(False)
        self.current_rows = rows
        self.model.setRowCount(0)
        for row in rows:
            # Column 0: Checkbox item
            chk_item = SortableItem("")
            chk_item.setCheckable(True)
            chk_item.setCheckState(Qt.Unchecked)
            chk_item.setData(0, Qt.UserRole)
            
            items = [
                str(row["id"]),
                row["date"],
                row["article_type"] or "",
                row["newspaper"],
                row["paper_section"] or "",
                format_display_time(row["published_at"]),
                row["title"],
                row["url"],
            ]
            sort_values = [
                int(row["id"]),
                row["date"] or "",
                row["article_type"] or "",
                row["newspaper"] or "",
                section_sort_key(row["paper_section"]),
                row["published_at"] or "",
                row["title"] or "",
                row["url"] or "",
            ]
            
            model_items = [chk_item]
            for i, (value, sort_value) in enumerate(zip(items, sort_values)):
                item = SortableItem(value)
                item.setData(sort_value, Qt.UserRole)
                if i == 7: # Index 7 in items is URL
                    from PySide6.QtGui import QColor, QFont
                    item.setForeground(QColor("#4664E6"))
                    font = item.font()
                    font.setUnderline(True)
                    item.setFont(font)
                model_items.append(item)
            for item in model_items:
                item.setEditable(False)
            self.model.appendRow(model_items)
        self.table.setSortingEnabled(True)
        self.table.resizeRowsToContents()

    def handle_selection_changed(self, selected, deselected):
        selected_rows = {index.row() for index in selected.indexes()}
        deselected_rows = {index.row() for index in deselected.indexes()}
        
        self.table.setSortingEnabled(False)
        for row in selected_rows:
            item = self.model.item(row, 0)
            if item:
                item.setCheckState(Qt.Checked)
        for row in deselected_rows:
            item = self.model.item(row, 0)
            if item:
                item.setCheckState(Qt.Unchecked)
        self.table.setSortingEnabled(True)
        self.show_selected_detail()

    def selected_article_ids(self):
        ids = []
        # 1. Gather ID of rows whose checkbox in column 0 is checked
        for row in range(self.model.rowCount()):
            item = self.model.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                id_item = self.model.item(row, 1) # ID is column 1
                if id_item:
                    ids.append(int(id_item.text()))
        # 2. Fallback: gather IDs from highlighted/selected table rows
        if not ids:
            indexes = self.table.selectionModel().selectedRows()
            for index in indexes:
                ids.append(int(self.model.item(index.row(), 1).text()))
        return ids

    def selected_article_id(self):
        ids = self.selected_article_ids()
        return ids[0] if ids else None

    def show_selected_detail(self):
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            self.detail_title.setText("선택한 기사 없음")
            self.detail_summary.clear()
            return
        article_id = int(self.model.item(indexes[0].row(), 1).text()) # ID is column 1
        row = self.db.get_article(article_id)
        if not row:
            return
        meta = " / ".join(value for value in [
            row["article_type"] or "",
            row["newspaper"],
            row["paper_section"] or "",
            format_display_time(row["published_at"]),
        ] if value)
        self.detail_title.setText(f"[{meta}] {row['title']}")
        
        # Display saved summary or suggest automated summary
        from report_generator import summary_passes_quality_gate, extractive_report_summary
        
        has_good_summary = False
        if row["summary"] and row["summary"].strip():
            if summary_passes_quality_gate(row["summary"], row):
                has_good_summary = True
                
        if has_good_summary:
            self.detail_summary.setPlainText(row["summary"])
        else:
            if row["body"] and row["body"].strip():
                try:
                    summary = extractive_report_summary(row)
                    self.detail_summary.setPlainText(summary)
                except Exception:
                    self.detail_summary.setPlainText(row["summary"] or "")
            else:
                self.detail_summary.setPlainText(row["summary"] or "")
                
        self.category_combo.setCurrentText(row["category"] or "")

    def crawl_selected_date(self):
        date = self.start_date_edit.date().toString("yyyyMMdd")
        if self.list_worker and self.list_worker.isRunning():
            self.info("목록 수집이 이미 진행 중입니다.")
            return
        self.show_progress("목록 수집 중입니다. 잠시만 기다려 주세요.", 0, 0)
        self.list_worker = ListCrawlWorker(
            date,
            fetch_first_page_bodies=False,
        )
        self.list_worker.finished.connect(self.list_worker_finished)
        self.list_worker.failed.connect(lambda msg: self.worker_failed("목록 수집 중 오류가 발생했습니다.", msg))
        self.list_worker.start()

    def list_worker_finished(self, result):
        self.close_progress()
        self.refresh_categories()
        self.search()
        summary = (
            "목록 수집 완료\n"
            f"확인: {result['total']}건\n"
            f"신규 저장: {result['inserted']}건\n"
            f"수집 페이지: {result.get('pages', 0)}쪽\n"
            f"본문 저장: {result.get('body_fetched', 0)}건"
        )
        self.ask_keyword_body_fetch(self.list_worker.date, summary)

    def ask_keyword_body_fetch(self, date, summary):
        dialog = KeywordBodyDialog(summary, load_body_keywords(), load_exclude_keywords(), self)
        dialog.exec()
        if dialog.action == "skip":
            self.statusBar().showMessage("목록 수집 완료", 5000)
            return

        keywords = save_body_keywords(dialog.keywords())
        exclude_keywords = save_exclude_keywords(dialog.exclude_keywords())
        if hasattr(self, "body_keywords_edit"):
            self.body_keywords_edit.setPlainText(", ".join(keywords))
        if hasattr(self, "exclude_keywords_edit"):
            self.exclude_keywords_edit.setPlainText(", ".join(exclude_keywords))
        if hasattr(self, "exclude_keyword_edit"):
            self.exclude_keyword_edit.setText(", ".join(exclude_keywords))
        if dialog.action == "save_skip":
            self.info("키워드를 저장했습니다.")
            return
        if not keywords:
            self.info("본문 수집에 사용할 키워드가 없습니다.")
            return

        rows = self.db.find_articles_by_keywords(
            date,
            keywords,
            exclude_keywords=exclude_keywords,
            include_existing_body=True,
            strict_report_scope=self.strict_scope_checkbox.isChecked(),
            exclude_foreign=not self.include_foreign_checkbox.isChecked(),
        )
        if not rows:
            self.info("저장된 목록 중 키워드 매칭 기사가 없습니다.")
            return
        self.active_keyword_filter = (keywords, exclude_keywords)
        self.show_rows(rows)
        self.info(f"키워드 매칭 기사 {len(rows)}건만 목록에 표시했습니다. 필요한 기사를 선택한 뒤 선택 항목 본문 수집을 누르세요.")

    def handle_select_all_changed(self, state):
        self.table.setSortingEnabled(False)
        check_state = Qt.Checked if state == Qt.Checked.value else Qt.Unchecked
        for row in range(self.model.rowCount()):
            item = self.model.item(row, 0)
            if item:
                item.setCheckState(check_state)
        self.table.setSortingEnabled(True)

    def handle_table_double_click(self, index):
        if index.column() not in (0, 8):
            self.load_selected_body()

    def handle_table_click(self, index):
        if index.column() == 8:
            self.open_selected_url()

    def load_selected_body(self, force=False):
        article_id = self.selected_article_id()
        if not article_id:
            self.info("기사를 선택해 주세요.")
            return
        self.start_body_worker([article_id], force=force)

    def fetch_bodies_for_selected(self):
        ids = self.selected_article_ids()
        if not ids:
            self.info("본문을 수집할 기사를 선택해 주세요.")
            return
        self.start_body_worker(ids, force=False)

    def fetch_keyword_bodies(self):
        dialog = KeywordBodyDialog(
            "선택 기간에서 키워드가 들어간 기사만 먼저 골라냅니다.",
            load_body_keywords(),
            normalize_keywords(self.exclude_keyword_edit.text().replace(",", "\n").splitlines()) or load_exclude_keywords(),
            self,
        )
        dialog.exec()
        if dialog.action == "skip":
            return
        keywords = save_body_keywords(dialog.keywords())
        exclude_keywords = save_exclude_keywords(dialog.exclude_keywords())
        if hasattr(self, "body_keywords_edit"):
            self.body_keywords_edit.setPlainText(", ".join(keywords))
        if hasattr(self, "exclude_keywords_edit"):
            self.exclude_keywords_edit.setPlainText(", ".join(exclude_keywords))
        if hasattr(self, "exclude_keyword_edit"):
            self.exclude_keyword_edit.setText(", ".join(exclude_keywords))
        if dialog.action == "save_skip":
            self.info("키워드를 저장했습니다.")
            return
        if not keywords:
            self.info("검색에 사용할 키워드가 없습니다.")
            return

        self.pending_keyword_lookup = (keywords, exclude_keywords)
        started = self.collect_online_keyword_candidates(keywords, exclude_keywords)
        if started:
            return
        self.show_keyword_lookup_rows(keywords, exclude_keywords)

    def show_keyword_lookup_rows(self, keywords, exclude_keywords, notify=True):
        date_from, date_to = self.keyword_lookup_date_range()
        rows = self.db.find_articles_by_keywords(
            None,
            keywords,
            exclude_keywords=exclude_keywords,
            include_existing_body=True,
            date_from=date_from,
            date_to=date_to,
            article_type=self.article_type_combo.currentText(),
            strict_report_scope=self.strict_scope_checkbox.isChecked(),
            exclude_foreign=not self.include_foreign_checkbox.isChecked(),
        )
        if not rows:
            self.active_keyword_filter = (keywords, exclude_keywords)
            self.show_rows([])
            if notify:
                self.info("키워드 매칭 기사가 없습니다.")
            return
        self.active_keyword_filter = (keywords, exclude_keywords)
        self.show_rows(rows)
        if notify:
            self.info(f"키워드 매칭 기사 {len(rows)}건만 목록에 표시했습니다. 유형 필터로 지면/통신/방송/온라인만 골라 볼 수 있습니다.")

    def keyword_lookup_date_range(self):
        start, end = self.selected_date_range()
        start_dt = datetime.strptime(start, "%Y%m%d") - timedelta(days=1)
        return start_dt.strftime("%Y%m%d"), end

    def start_startup_online_refresh(self):
        now = datetime.now()
        start_dt = (now - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
        end_dt = now.replace(hour=6, minute=0, second=0, microsecond=0)
        self.start_online_worker(
            start_dt=start_dt,
            end_dt=end_dt,
            exclude_keywords=load_exclude_keywords(),
            silent=True,
        )

    def collect_online_keyword_candidates(self, keywords, exclude_keywords):
        start, end = self.selected_date_range()
        start_dt = datetime.strptime(start, "%Y%m%d") - timedelta(days=1)
        start_dt = start_dt.replace(hour=18, minute=0, second=0)
        end_dt = datetime.strptime(end, "%Y%m%d").replace(hour=6, minute=0, second=0)
        return self.start_online_worker(start_dt, end_dt, exclude_keywords, silent=False)

    def start_online_worker(self, start_dt, end_dt, exclude_keywords, silent=False):
        if self.online_worker and self.online_worker.isRunning():
            self.statusBar().showMessage("온라인 후보 수집이 이미 진행 중입니다.", 5000)
            return False
        if not silent:
            self.show_progress("온라인 정치/사회 기사 후보를 확인하는 중입니다.", 0, 0)
        else:
            self.statusBar().showMessage("온라인 후보를 백그라운드로 확인하는 중입니다.", 5000)
        self.online_worker = OnlineCrawlWorker(start_dt, end_dt, exclude_keywords)
        self.online_worker.silent = silent
        self.online_worker.finished.connect(self.online_worker_finished)
        self.online_worker.failed.connect(lambda msg: self.worker_failed("온라인 후보 수집 중 오류가 발생했습니다.", msg))
        self.online_worker.start()
        return True

    def online_worker_finished(self, result):
        silent = bool(getattr(self.online_worker, "silent", False))
        if not silent:
            self.close_progress()
        update_config({"last_online_crawl_at": datetime.now().isoformat(timespec="seconds")})
        self.refresh_categories()
        if self.pending_keyword_lookup:
            keywords, exclude_keywords = self.pending_keyword_lookup
            self.pending_keyword_lookup = None
            self.show_keyword_lookup_rows(keywords, exclude_keywords)
            return
        if result.get("errors") and not silent:
            message = "\n".join(result["errors"][:8])
            if len(result["errors"]) > 8:
                message += f"\n... 외 {len(result['errors']) - 8}건"
            QMessageBox.warning(self, "온라인 수집 오류", message)
            return
        self.statusBar().showMessage(
            "온라인 후보는 이미 수집되어 저장된 결과를 사용합니다." if result.get("skipped")
            else f"온라인 후보 확인 {result['total']}건, 신규 {result['inserted']}건",
            5000,
        )

    @staticmethod
    def row_matches_keywords(row, keywords):
        haystack = f"{row['title'] or ''}\n{row['summary'] or ''}"
        return any(keyword in haystack for keyword in keywords)

    def start_body_worker(self, ids, force=False):
        if self.worker and self.worker.isRunning():
            self.info("본문 수집이 이미 진행 중입니다.")
            return
        self.show_progress("본문 수집 중입니다. 잠시만 기다려 주세요.", 0, len(ids))
        self.worker = BodyFetchWorker(ids, force=force)
        self.worker.progress.connect(self.body_worker_progress)
        self.worker.finished.connect(self.body_worker_finished)
        self.worker.failed.connect(lambda msg: self.worker_failed("본문 수집 중 오류가 발생했습니다.", msg))
        self.worker.start()

    def body_worker_progress(self, done, total):
        self.statusBar().showMessage(f"본문 수집 중 {done}/{total}")
        dialog = self.progress_dialog
        if dialog:
            try:
                dialog.setMaximum(total)
                dialog.setValue(done)
                dialog.setLabelText(f"본문 수집 중입니다. ({done}/{total})")
            except Exception:
                pass

    def body_worker_finished(self, count):
        self.close_progress()
        self.statusBar().showMessage(f"본문 수집 완료: {count}건", 5000)
        fetched_ids = list(getattr(self.worker, "article_ids", [])) if self.worker else []
        fetched_rows = [self.db.get_article(article_id) for article_id in fetched_ids]
        fetched_rows = [row for row in fetched_rows if row]
        if fetched_rows:
            self.show_rows(fetched_rows)
            self.show_body_result_rows(fetched_rows)
        else:
            self.show_selected_detail()

    def show_progress(self, message, minimum, maximum):
        self.close_progress()
        self.progress_dialog = QProgressDialog(message, "", minimum, maximum, self)
        self.progress_dialog.setWindowTitle("처리 중")
        self.progress_dialog.setCancelButton(None)
        self.progress_dialog.setWindowModality(Qt.ApplicationModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.show()
        QApplication.processEvents()

    def close_progress(self):
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

    def worker_failed(self, message, detail):
        self.close_progress()
        self.error(message, detail)

    def open_selected_url(self):
        article_id = self.selected_article_id()
        if not article_id:
            return
        row = self.db.get_article(article_id)
        if row:
            webbrowser.open(row["url"])

    def open_selected_body_txt(self):
        article_ids = self.selected_article_ids()
        if not article_ids:
            self.info("TXT로 열 기사를 선택해 주세요.")
            return
        missing = [article_id for article_id in article_ids if not (self.db.get_article(article_id)["body"] or "")]
        if missing:
            answer = QMessageBox.question(
                self,
                "본문 없음",
                f"선택한 기사 중 {len(missing)}건에 저장된 본문이 없습니다. 지금 본문을 불러온 뒤 TXT로 열까요?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                return
            crawler = NaverPaperCrawler(self.db)
            for article_id in missing:
                crawler.fetch_and_store_body(article_id, force=False)
        opened = 0
        for article_id in article_ids:
            row = self.db.get_article(article_id)
            if not row or not row["body"]:
                continue
            safe_title = "".join(ch if ch not in '\\/:*?"<>|' else "_" for ch in row["title"])[:80]
            path = os.path.join(tempfile.gettempdir(), f"{article_id}_{safe_title or 'naver_article'}.txt")
            content = (
                f"{row['title']}\n"
                f"{self.article_meta(row)}\n"
                f"{row['url']}\n\n"
                f"{row['body']}"
            )
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            os.startfile(path)
            opened += 1
        if not opened:
            self.info("TXT로 열 본문이 없습니다.")

    def copy_report_format(self):
        self.generate_report_flow()

    def show_body_result_rows(self, rows):
        self.detail_title.setText(f"본문 수집 결과 {len(rows)}건")
        self.detail_summary.setPlainText("")

    def generate_report_flow(self):
        ids = self.selected_article_ids()
        if not ids:
            self.info("보고서를 작성할 기사들을 선택해 주세요.")
            return
        
        # Check for articles missing body text
        missing = [article_id for article_id in ids if not (self.db.get_article(article_id)["body"] or "").strip()]
        
        if missing:
            if self.worker and self.worker.isRunning():
                self.info("이전 본문 수집 작업이 진행 중입니다. 잠시 기다려 주세요.")
                return
            
            self.show_progress("선택한 기사들의 본문을 수집 중입니다. 완료 후 보고서가 즉시 작성됩니다.", 0, len(missing))
            self.worker = BodyFetchWorker(missing, force=False)
            self.worker.progress.connect(self.body_worker_progress)
            
            def on_fetch_finished():
                self.close_progress()
                self.statusBar().showMessage(f"본문 수집 완료: {len(missing)}건. 보고서를 작성합니다.", 5000)
                self.show_completed_report(ids)
                
            self.worker.finished.connect(on_fetch_finished)
            self.worker.failed.connect(lambda msg: self.worker_failed("본문 수집 중 오류가 발생했습니다.", msg))
            self.worker.start()
        else:
            self.show_completed_report(ids)

    def show_completed_report(self, ids):
        rows = [self.db.get_article(article_id) for article_id in ids]
        rows = [row for row in rows if row]
        text = self.format_report_rows(rows)
        
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage("아침보고 텍스트를 취합하여 클립보드에 복사했습니다.", 5000)
        
        # Open dedicated popup report viewer
        dialog = ReportViewerDialog(text, self)
        dialog.exec()

    def format_report_rows(self, rows):
        from collections import defaultdict
        by_category = defaultdict(list)
        for row in rows:
            cat = row["category"]
            if not cat:
                from report_generator import recommend_category
                cat, confidence, reasons = recommend_category(row)
                cat = cat or "미분류 사안"
                try:
                    self.db.set_article_category(row["id"], cat)
                except Exception:
                    pass
            by_category[cat].append(row)
            
        blocks = []
        blocks.append("[아침보고]")
        blocks.append("")
        for cat, cat_rows in by_category.items():
            blocks.append(f"## {cat}")
            blocks.append("")
            cat_blocks = []
            for row in cat_rows:
                newspaper = self.short_newspaper_name(row["newspaper"])
                section = self.report_section(row)
                from report_generator import summary_passes_quality_gate, extractive_report_summary
                summary = (row["summary"] or "").strip()
                has_good_summary = summary and summary_passes_quality_gate(summary, row)
                if not has_good_summary and row["body"] and row["body"].strip():
                    try:
                        summary = extractive_report_summary(row)
                    except Exception:
                        pass
                summary_text = f"\n- {summary}" if summary else ""
                item_text = f"※ {row['title']}/{newspaper} {section}{summary_text}\n{self.report_url(row['url'])}"
                cat_blocks.append(item_text)
            blocks.append("\n\n\n".join(cat_blocks))
            blocks.append("")
            blocks.append("")
        return "\n".join(blocks).strip()

    @staticmethod
    def article_meta(row):
        parts = [row["newspaper"], row["date"]]
        if row["article_type"] and row["article_type"] != "지면":
            parts.append(row["article_type"])
        if row["paper_section"]:
            parts.append(row["paper_section"])
        if row["published_at"]:
            parts.append(format_display_time(row["published_at"]))
        return " / ".join(parts)

    @staticmethod
    def report_section(row):
        if (row["article_type"] or "지면") == "지면":
            return row["paper_section"] or ""
        parts = []
        if row["paper_section"]:
            parts.append(row["paper_section"])
        if row["published_at"]:
            parts.append(format_display_time(row["published_at"]))
        return " ".join(parts) or (row["article_type"] or "")

    @staticmethod
    def short_newspaper_name(name):
        names = {
            "경향신문": "경향",
            "국민일보": "국민",
            "동아일보": "동아",
            "문화일보": "문화",
            "서울신문": "서울",
            "세계일보": "세계",
            "조선일보": "조선",
            "중앙일보": "중앙",
            "한겨레": "한겨레",
            "한국일보": "한국",
        }
        return names.get(name, name)

    @staticmethod
    def report_url(url):
        return url.replace("https://n.news.naver.com/mnews/article/", "https://n.news.naver.com/article/")

    def export_csv(self):
        if not self.current_rows:
            self.info("내보낼 검색 결과가 없습니다.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "CSV 내보내기", "naver_news_results.csv", "CSV Files (*.csv)")
        if not path:
            return
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["date", "article_type", "newspaper", "paper_section", "published_at", "title", "url", "summary", "category", "body"])
            for row in self.current_rows:
                writer.writerow([
                    row["date"],
                    row["article_type"] or "",
                    row["newspaper"],
                    row["paper_section"] or "",
                    row["published_at"] or "",
                    row["title"],
                    row["url"],
                    row["summary"] or "",
                    row["category"] or "",
                    row["body"] or "",
                ])
        self.info("CSV 내보내기가 완료되었습니다.")

    def save_selected_txt(self):
        article_id = self.selected_article_id()
        if not article_id:
            self.info("기사를 선택해 주세요.")
            return
        row = self.db.get_article(article_id)
        if not row:
            return
        path, _ = QFileDialog.getSaveFileName(self, "TXT 저장", f"{row['title'][:40]}.txt", "Text Files (*.txt)")
        if not path:
            return
        content = (
            f"{row['title']}\n"
            f"{self.article_meta(row)}\n"
            f"{row['url']}\n"
            f"카테고리: {row['category'] or ''}\n\n"
            f"{row['body'] or ''}"
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        self.info("TXT 저장이 완료되었습니다.")

    def apply_category_to_selected(self):
        ids = self.selected_article_ids()
        if not ids:
            self.info("카테고리를 부여할 기사를 선택해 주세요.")
            return
        category = self.category_combo.currentText().strip()
        self.db.update_category(ids, category or None)
        self.refresh_categories()
        self.search()
        self.info(f"{len(ids)}건에 카테고리를 저장했습니다.")

    def save_current_article_summary_and_category(self):
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            self.info("저장할 기사를 선택해 주세요.")
            return
        article_id = int(self.model.item(indexes[0].row(), 1).text()) # ID is column 1
        summary = self.detail_summary.toPlainText().strip()
        category = self.category_combo.currentText().strip() or None
        self.db.update_summary_and_category(article_id, summary, category)
        self.refresh_categories()
        
        # Remember selection and scroll position
        selected_index = self.table.selectionModel().currentIndex()
        
        self.search()
        
        # Restore selection and scroll
        if selected_index.isValid():
            for row in range(self.model.rowCount()):
                if int(self.model.item(row, 1).text()) == article_id: # ID is column 1
                    self.table.selectRow(row)
                    self.table.scrollTo(self.model.index(row, 1))
                    break
                    
        self.statusBar().showMessage("기사 사안 및 요약문이 DB에 저장되었습니다. (Ctrl+S)", 5000)

    def save_settings(self):
        keywords = normalize_keywords(self.body_keywords_edit.toPlainText().replace(",", "\n").splitlines())
        exclude_keywords = normalize_keywords(self.exclude_keywords_edit.toPlainText().replace(",", "\n").splitlines())
        update_config({
            "body_keywords": keywords,
            "exclude_keywords": exclude_keywords,
        })
        if hasattr(self, "exclude_keyword_edit"):
            self.exclude_keyword_edit.setText(", ".join(exclude_keywords))
        self.info("설정을 저장했습니다.")

    def info(self, message):
        QMessageBox.information(self, "알림", message)

    def error(self, message, detail):
        logger.exception("%s %s", message, detail)
        QMessageBox.critical(self, "오류", f"{message}\n\n상세 로그: {LOG_PATH}")


def run_gui():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
