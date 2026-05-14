import csv
import logging
import os
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


def format_display_time(value):
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%m-%d %H:%M")
    except Exception:
        return str(value)


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
        self.setWindowTitle("키워드 기사 찾기")
        self.resize(520, 360)

        layout = QVBoxLayout(self)
        summary_label = QLabel(summary)
        summary_label.setWordWrap(True)
        layout.addWidget(summary_label)

        guide = QLabel("아래 키워드가 제목 또는 요약에 포함된 기사만 먼저 골라냅니다. 쉼표 또는 줄바꿈으로 구분하세요.")
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
        collect_btn = QPushButton("키워드 기사만 보기")
        save_skip_btn = QPushButton("키워드 저장만")
        skip_btn = QPushButton("건너뛰기")
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
    HEADERS = ["ID", "날짜", "유형", "언론사", "게재면/분야", "게재시간", "제목", "링크"]

    def __init__(self):
        super().__init__()
        self.db = Database()
        self.current_rows = []
        self.worker = None
        self.list_worker = None
        self.online_worker = None
        self.pending_keyword_lookup = None
        self.active_keyword_filter = None
        self.progress_dialog = None
        self.setWindowTitle("네이버 신문게재 기사 수집기")
        self.resize(1280, 760)
        self.setStyleSheet(APP_STYLESHEET)
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self._build_articles_tab()
        self._build_settings_tab()
        self.refresh_categories()
        self.search()
        QTimer.singleShot(1200, self.start_startup_online_refresh)

    def _build_articles_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        filters = QGridLayout()
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("yyyyMMdd")
        self.start_date_edit.setDateTime(self.start_date_edit.dateTime().currentDateTime())
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("yyyyMMdd")
        self.end_date_edit.setDateTime(self.end_date_edit.dateTime().currentDateTime())
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
        self.keyword_edit.setPlaceholderText("키워드")
        self.keyword_edit.setMinimumWidth(420)

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

        search_btn = QPushButton("검색")
        search_btn.clicked.connect(self.search_with_auto_crawl)
        keyword_body_top_btn = QPushButton("키워드 기사 찾기")
        keyword_body_top_btn.clicked.connect(self.fetch_keyword_bodies)

        filters.addWidget(QLabel("시작일"), 0, 0)
        filters.addWidget(self.start_date_edit, 0, 1)
        filters.addWidget(QLabel("종료일"), 0, 2)
        filters.addWidget(self.end_date_edit, 0, 3)
        filters.addWidget(QLabel("언론사"), 0, 4)
        filters.addWidget(self.newspaper_combo, 0, 5)
        filters.addWidget(QLabel("유형"), 0, 6)
        filters.addWidget(self.article_type_combo, 0, 7)
        filters.addWidget(QLabel("게재면/분야"), 1, 0)
        filters.addWidget(self.section_combo, 1, 1)
        filters.addWidget(QLabel("범위"), 1, 2)
        filters.addWidget(self.scope_combo, 1, 3)
        filters.addWidget(QLabel("키워드"), 2, 0)
        filters.addWidget(self.keyword_edit, 2, 1, 1, 3)
        filters.addWidget(self.exclude_keyword_edit, 2, 4, 1, 2)
        filters.addWidget(keyword_body_top_btn, 2, 6)
        filters.addWidget(search_btn, 2, 7)
        filters.setColumnStretch(5, 1)
        filters.setColumnStretch(7, 1)
        layout.addLayout(filters)

        self.keyword_edit.returnPressed.connect(self.search_with_auto_crawl)
        self.exclude_keyword_edit.returnPressed.connect(self.search_with_auto_crawl)
        self.article_type_combo.currentTextChanged.connect(self.handle_article_type_changed)
        self.section_combo.lineEdit().returnPressed.connect(self.search_with_auto_crawl)
        self.newspaper_combo.lineEdit().returnPressed.connect(self.search_with_auto_crawl)
        self.start_date_edit.editingFinished.connect(self.search_with_auto_crawl)
        self.end_date_edit.editingFinished.connect(self.search_with_auto_crawl)

        splitter = QSplitter(Qt.Vertical)
        self.table = QTableView()
        self.model = QStandardItemModel(0, len(self.HEADERS))
        self.model.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.clicked.connect(self.handle_table_click)
        self.table.doubleClicked.connect(self.handle_table_double_click)
        self.table.selectionModel().selectionChanged.connect(self.show_selected_detail)
        self.table.setColumnHidden(0, True)
        self.table.setColumnWidth(6, 420)
        self.table.setColumnWidth(7, 360)
        splitter.addWidget(self.table)

        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        self.detail_title = QLabel("선택한 기사 없음")
        self.detail_title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail_summary = QTextEdit()
        self.detail_summary.setReadOnly(True)
        self.detail_summary.setMaximumHeight(110)
        self.body_text = QTextEdit()
        self.body_text.setReadOnly(True)

        category_row = QHBoxLayout()
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        apply_category_btn = QPushButton("선택 기사 카테고리 저장")
        apply_category_btn.clicked.connect(self.apply_category_to_selected)
        bulk_category_btn = QPushButton("다중 선택 일괄 부여")
        bulk_category_btn.clicked.connect(self.apply_category_to_selected)
        category_row.addWidget(QLabel("카테고리"))
        category_row.addWidget(self.category_combo, 1)
        category_row.addWidget(apply_category_btn)
        category_row.addWidget(bulk_category_btn)
        category_row.addWidget(QLabel("카테고리 필터"))
        category_row.addWidget(self.category_filter_combo)

        action_row = QHBoxLayout()
        selected_body_btn = QPushButton("선택 항목 본문 수집")
        open_url_btn = QPushButton("본문 TXT 열기")
        report_btn = QPushButton("보고 양식")
        export_csv_btn = QPushButton("CSV 내보내기")
        save_txt_btn = QPushButton("TXT 저장")
        selected_body_btn.clicked.connect(self.fetch_bodies_for_selected)
        open_url_btn.clicked.connect(self.open_selected_body_txt)
        report_btn.clicked.connect(self.copy_report_format)
        export_csv_btn.clicked.connect(self.export_csv)
        save_txt_btn.clicked.connect(self.save_selected_txt)
        for btn in [
            selected_body_btn,
            open_url_btn,
            report_btn,
            export_csv_btn,
            save_txt_btn,
        ]:
            action_row.addWidget(btn)
        action_row.addStretch(1)

        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail_summary)
        detail_layout.addLayout(category_row)
        detail_layout.addLayout(action_row)
        detail_layout.addWidget(self.body_text, 1)
        splitter.addWidget(detail_widget)
        splitter.setSizes([420, 300])
        layout.addWidget(splitter, 1)
        self.tabs.addTab(tab, "기사")

    def _build_settings_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()
        self.gemini_key_edit = QLineEdit()
        self.gemini_key_edit.setEchoMode(QLineEdit.Password)
        self.gemini_key_edit.setText(load_config().get("gemini_api_key", ""))
        form.addRow("Gemini API Key", self.gemini_key_edit)
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

    def search(self):
        self.active_keyword_filter = None
        date_from, date_to = self.selected_date_range()
        rows = self.db.search_articles(
            date_from=date_from,
            date_to=date_to,
            newspaper=self.newspaper_combo.currentText(),
            paper_section=self.section_combo.currentText().strip(),
            keyword=self.keyword_edit.text().strip(),
            search_scope=self.scope_combo.currentData(),
            category=self.category_filter_combo.currentText(),
            article_type=self.article_type_combo.currentText(),
            exclude_keywords=normalize_keywords(self.exclude_keyword_edit.text().replace(",", "\n").splitlines()),
        )
        self.show_rows(rows)

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
        if not missing:
            self.search()
            return
        if self.list_worker and self.list_worker.isRunning():
            self.info("목록 수집이 이미 진행 중입니다.")
            return
        self.show_progress(f"신문 목록 수집 중입니다. ({len(missing)}일)", 0, 0)
        self.list_worker = RangeCrawlWorker(missing)
        self.list_worker.finished.connect(self.range_crawl_finished)
        self.list_worker.failed.connect(lambda msg: self.worker_failed("목록 수집 중 오류가 발생했습니다.", msg))
        self.list_worker.start()

    def range_crawl_finished(self, result):
        self.close_progress()
        self.refresh_categories()
        self.search()
        self.statusBar().showMessage(
            f"목록 수집 완료: 확인 {result['total']}건, 신규 {result['inserted']}건",
            5000,
        )

    def selected_date_range(self):
        start_qdate = self.start_date_edit.date()
        end_qdate = self.end_date_edit.date()
        if start_qdate > end_qdate:
            self.start_date_edit.blockSignals(True)
            self.end_date_edit.blockSignals(True)
            self.start_date_edit.setDate(end_qdate)
            self.end_date_edit.setDate(start_qdate)
            self.start_date_edit.blockSignals(False)
            self.end_date_edit.blockSignals(False)
            self.statusBar().showMessage("시작일과 종료일이 바뀌어 자동으로 바로잡았습니다.", 5000)
            start_qdate, end_qdate = end_qdate, start_qdate
        return start_qdate.toString("yyyyMMdd"), end_qdate.toString("yyyyMMdd")

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
        self.current_rows = rows
        self.model.setRowCount(0)
        for row in rows:
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
            model_items = [QStandardItem(value) for value in items]
            for item in model_items:
                item.setEditable(False)
            self.model.appendRow(model_items)
        self.table.resizeRowsToContents()

    def selected_article_ids(self):
        indexes = self.table.selectionModel().selectedRows()
        ids = []
        for index in indexes:
            ids.append(int(self.model.item(index.row(), 0).text()))
        return ids

    def selected_article_id(self):
        ids = self.selected_article_ids()
        return ids[0] if ids else None

    def show_selected_detail(self):
        article_id = self.selected_article_id()
        if not article_id:
            self.detail_title.setText("선택한 기사 없음")
            self.detail_summary.clear()
            self.body_text.clear()
            return
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
        self.detail_summary.setPlainText(self.format_report_rows([row]))
        self.body_text.setPlainText(row["body"] or "")
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
        )
        if not rows:
            self.info("저장된 목록 중 키워드 매칭 기사가 없습니다.")
            return
        self.active_keyword_filter = (keywords, exclude_keywords)
        self.show_rows(rows)
        self.info(f"키워드 매칭 기사 {len(rows)}건만 목록에 표시했습니다. 필요한 기사를 선택한 뒤 선택 항목 본문 수집을 누르세요.")

    def handle_table_double_click(self, index):
        if index.column() != 7:
            self.load_selected_body()

    def handle_table_click(self, index):
        if index.column() == 7:
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
        config = load_config()
        last = config.get("last_online_crawl_at")
        if last:
            try:
                if datetime.now() - datetime.fromisoformat(last) < timedelta(hours=3):
                    return
            except Exception:
                pass
        self.start_online_worker(
            start_dt=datetime.now() - timedelta(hours=4),
            end_dt=datetime.now(),
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
        if self.progress_dialog:
            self.progress_dialog.setMaximum(total)
            self.progress_dialog.setValue(done)
            self.progress_dialog.setLabelText(f"본문 수집 중입니다. ({done}/{total})")

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
        ids = self.selected_article_ids()
        if not ids:
            self.info("보고 양식으로 복사할 기사를 선택해 주세요.")
            return
        rows = [self.db.get_article(article_id) for article_id in ids]
        rows = [row for row in rows if row]
        text = self.format_report_rows(rows)
        QApplication.clipboard().setText(text)
        self.detail_summary.setPlainText(text)
        self.info("보고 양식을 클립보드에 복사했습니다.")

    def show_body_result_rows(self, rows):
        self.detail_title.setText(f"본문 수집 결과 {len(rows)}건")
        self.detail_summary.setPlainText(self.format_report_rows(rows))
        previews = []
        for row in rows:
            body = (row["body"] or "").strip()
            if len(body) > 700:
                body = body[:700].rstrip() + "..."
            previews.append(
                f"[{self.article_meta(row)}] {row['title']}\n"
                f"{body or '(본문 없음)'}"
            )
        self.body_text.setPlainText("\n\n---\n\n".join(previews))

    def format_report_rows(self, rows):
        blocks = []
        for row in rows:
            newspaper = self.short_newspaper_name(row["newspaper"])
            section = self.report_section(row)
            blocks.append(f"※{row['title']}/{newspaper} {section}\n{self.report_url(row['url'])}")
        return "\n\n".join(blocks)

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

    def save_settings(self):
        keywords = normalize_keywords(self.body_keywords_edit.toPlainText().replace(",", "\n").splitlines())
        exclude_keywords = normalize_keywords(self.exclude_keywords_edit.toPlainText().replace(",", "\n").splitlines())
        update_config({
            "gemini_api_key": self.gemini_key_edit.text().strip(),
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
