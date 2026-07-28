"""Markdown Viewer PyQt5 three-column application."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PyQt5.QtCore import QEvent, Qt, QTimer, QUrl
from PyQt5.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QKeySequence,
    QPixmap,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
)
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QShortcut,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.file_loader import read_file
from src.core.file_type_detector import FileType, detect_file
from src.core.parser import MarkdownAnalyzer
from src.core.yaml_renderer import render_frontmatter_dict_to_html, render_yaml_to_html
from src.utils.config import load_config, load_history, save_config, save_history
from src.utils.file_association import associate_files, disassociate_files
from src.utils.search import find_in_text

VIEW_RENDERED = "Rendered"
VIEW_ORIGINAL = "Original"
FILE_MASK = (
    "Markdown/YAML files (*.md *.markdown *.mdx *.yaml *.yml);;"
    "All files (*)"
)

def _is_color_dark(hex_color: str) -> bool:
    """Check if a hex color is dark (for choosing appropriate text colors)."""
    try:
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        # Using relative luminance formula
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return luminance < 0.5
    except (ValueError, TypeError, IndexError):
        return False


def _is_system_dark_theme() -> bool:
    """Detect if the OS is using a dark theme (Windows only)."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return value == 0
    except (OSError, ValueError, TypeError):
        return False



class _DropForwardPlainTextEdit(QPlainTextEdit):
    """QPlainTextEdit that forwards file drops to a callback instead of inserting text."""
    def __init__(self, drop_callback, parent=None):
        super().__init__(parent)
        self._drop_callback = drop_callback
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path:
                    self._drop_callback(path)
                    break
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class _DropForwardTextBrowser(QTextBrowser):
    """QTextBrowser that forwards file drops to a callback instead of inserting text."""
    def __init__(self, drop_callback, parent=None):
        super().__init__(parent)
        self._drop_callback = drop_callback
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path:
                    self._drop_callback(path)
                    break
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class MainWindow(QMainWindow):
    """Three-column: title nav | preview | source."""

    def __init__(self) -> None:
        super().__init__()
        self._content = ""
        self._filepath = ""
        self._parser = MarkdownAnalyzer()
        self._config = load_config()
        self._html_doc = ""
        self._current_titles = []
        self._current_view = VIEW_RENDERED
        self._search_results = []
        self._search_index = 0
        self._heading_index = -1
        self._scroll_positions = {}
        self._modified = False
        self.setWindowTitle("Markdown Viewer")
        w = self._config.get("window", {})
        if w.get("maximized", False):
            # Defer maximize until the window is actually shown to avoid
            # a flash of white/unmaximized state at startup.
            QTimer.singleShot(0, self.showMaximized)
        else:
            self.resize(int(w.get("width", 1400)), int(w.get("height", 800)))
        self._build_ui()
        self._build_menubar()
        self.statusBar().showMessage("Ready")
        self.setAcceptDrops(True)  # Enable drag & drop for files
        self._refresh_recent_menu()

    def _build_ui(self) -> None:
        """Build the three-column layout."""
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        self._splitter = QSplitter(Qt.Horizontal)
        root.addWidget(self._splitter, 1)

        # Left: title tree with header bar (matches center column)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)
        left_header = QFrame()
        left_header.setFixedHeight(28)
        lh_layout = QHBoxLayout(left_header)
        lh_layout.setContentsMargins(4, 2, 4, 2)
        lh_layout.setSpacing(4)
        lh_layout.addStretch()
        lv.addWidget(left_header)
        self._title_tree = QTreeWidget()
        self._title_tree.setHeaderLabel("Titles")
        self._title_tree.itemClicked.connect(self._on_title_clicked)
        lv.addWidget(self._title_tree, 1)
        self._splitter.addWidget(left)

        # Center: source editor with header bar + close button
        source_wrapper = QWidget()
        sv = QVBoxLayout(source_wrapper)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(0)
        # Source header with close button
        source_header = QFrame()
        source_header.setFixedHeight(28)
        sh_layout = QHBoxLayout(source_header)
        sh_layout.setContentsMargins(4, 2, 4, 2)
        sh_layout.setSpacing(4)
        self._close_btn = QPushButton("\u2715")
        self._close_btn.setFixedSize(28, 28)
        self._close_btn.setToolTip("Close document")
        self._close_btn.clicked.connect(self._close_document)
        sh_layout.addWidget(self._close_btn)
        sh_layout.addStretch()
        self._source_header = source_header
        self._source_header.setAcceptDrops(True)
        self._source_header.installEventFilter(self)
        sv.addWidget(source_header)
        # Source editor
        self._source = _DropForwardPlainTextEdit(self._load_file)
        font_size = self._config.get("font_size", 9)
        self._source.setFont(QFont("Consolas", font_size))
        self._source.textChanged.connect(self._on_source_changed)
        self._highlighter = MarkdownHighlighter(self._source.document())
        sv.addWidget(self._source, 1)
        self._splitter.addWidget(source_wrapper)

        # Right: preview with header bar (matches center column)
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        right_header = QFrame()
        right_header.setFixedHeight(28)
        rh_layout = QHBoxLayout(right_header)
        rh_layout.setContentsMargins(4, 2, 4, 2)
        rh_layout.setSpacing(4)
        rh_layout.addStretch()
        self._right_header = right_header
        self._right_header.setAcceptDrops(True)
        self._right_header.installEventFilter(self)
        rv.addWidget(right_header)
        self._preview = _DropForwardTextBrowser(self._load_file)
        self._preview.setOpenExternalLinks(True)
        self._preview.setOpenLinks(False)
        self._preview.anchorClicked.connect(self._on_anchor_clicked)
        # Ensure preview wraps long lines when font size changes
        self._preview.setLineWrapMode(QTextEdit.WidgetWidth)
        self._preview.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        preview_font = QFont("SimSun", font_size)
        self._preview.setFont(preview_font)
        self._preview.document().setDefaultFont(preview_font)
        rv.addWidget(self._preview, 1)
        # Also allow file drops on the preview viewport
        self._preview.viewport().installEventFilter(self)
        self._splitter.addWidget(right)
        sizes = self._config.get("window", {}).get("splitter", [160, 520, 520])
        if len(sizes) != 3:
            sizes = [160, 520, 520]
        self._splitter.setSizes([int(x) for x in sizes])
        # Dynamic image re-scaling when splitter is dragged
        self._splitter.splitterMoved.connect(self._schedule_preview_update)

        # Search bar (hidden by default, toggled by Ctrl+F)
        self._search_bar = QFrame()
        search_layout = QHBoxLayout(self._search_bar)
        search_layout.setContentsMargins(4, 2, 4, 2)
        search_layout.setSpacing(4)
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search...")
        self._search_input.returnPressed.connect(self._do_search)
        self._search_input.textChanged.connect(self._on_search_text_changed)
        search_layout.addWidget(self._search_input)
        self._search_label = QLabel("")
        search_layout.addWidget(self._search_label)
        btn_prev = QPushButton("\u25B2")  # up triangle
        btn_prev.setFixedWidth(24)
        btn_prev.clicked.connect(self._search_previous)
        search_layout.addWidget(btn_prev)
        btn_next = QPushButton("\u25BC")  # down triangle
        btn_next.setFixedWidth(24)
        btn_next.clicked.connect(self._search_next)
        search_layout.addWidget(btn_next)
        btn_close = QPushButton("\u2715")  # x
        btn_close.setFixedWidth(24)
        btn_close.clicked.connect(lambda: self._search_bar.hide())
        search_layout.addWidget(btn_close)
        self._search_bar.hide()
        root.addWidget(self._search_bar)
        # Ctrl+F shortcut
        shortcut_search = QShortcut(QKeySequence.Find, self)
        shortcut_search.activated.connect(self._toggle_search_bar)

    def _build_menubar(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        open_action = file_menu.addAction("&Open...")
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._on_open)
        file_menu.addSeparator()
        self._recent_menu = file_menu.addMenu("&Recent")
        self._save_action = file_menu.addAction("&Save")
        self._save_action.setShortcut(QKeySequence.Save)
        self._save_action.triggered.connect(self._save_file)
        save_as_action = file_menu.addAction("Save &As...")
        save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_action.triggered.connect(self._save_file_as)
        close_doc_action = file_menu.addAction("&Close Document")
        close_doc_action.setShortcut(QKeySequence("Ctrl+W"))
        close_doc_action.triggered.connect(self._close_document)
        quit_action = file_menu.addAction("E&xit")
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)

        view_menu = bar.addMenu("&View")
        self._view_rendered = view_menu.addAction("&Rendered")
        self._view_rendered.setCheckable(True)
        self._view_rendered.setChecked(True)
        self._view_rendered.triggered.connect(lambda _: self._set_view(VIEW_RENDERED))
        self._view_original = view_menu.addAction("&Original")
        self._view_original.setCheckable(True)
        self._view_original.triggered.connect(lambda _: self._set_view(VIEW_ORIGINAL))
        view_menu.addSeparator()
        zoom_in = view_menu.addAction("Zoom &In")
        zoom_in.setShortcut(QKeySequence.ZoomIn)
        zoom_in.triggered.connect(self._increase_font)
        zoom_out = view_menu.addAction("Zoom &Out")
        zoom_out.setShortcut(QKeySequence.ZoomOut)
        zoom_out.triggered.connect(self._decrease_font)

        theme_menu = bar.addMenu("&Theme")
        self._theme_group = []
        for mode, label in [("light", "&Light"), ("dark", "&Dark"), ("system", "&System")]:
            a = theme_menu.addAction(label)
            a.setCheckable(True)
            a.setData(mode)
            a.triggered.connect(lambda _, m=mode: self._set_theme(m))
            self._theme_group.append(a)
        mode = self._config.get("theme", "light")
        for a in self._theme_group:
            a.setChecked(a.data() == mode)
        self._apply_theme(mode)

        nav_menu = bar.addMenu("&Navigate")
        prev_heading = nav_menu.addAction("&Previous Heading")
        prev_heading.setShortcut("Ctrl+Shift+Up")
        prev_heading.triggered.connect(lambda: self._go_to_heading(delta=-1))
        next_heading = nav_menu.addAction("&Next Heading")
        next_heading.setShortcut("Ctrl+Shift+Down")
        next_heading.triggered.connect(lambda: self._go_to_heading(delta=1))

        tools_menu = bar.addMenu("&Tools")
        associate_action = tools_menu.addAction("&Associate .md/.yaml files")
        associate_action.triggered.connect(self._on_associate_files)
        disassociate_action = tools_menu.addAction("&Remove file association")
        disassociate_action.triggered.connect(self._on_disassociate_files)

        help_menu = bar.addMenu("&Help")
        about_action = help_menu.addAction("&About")
        about_action.triggered.connect(self._show_about)

    def _show_about(self) -> None:
        QMessageBox.information(
            self,
            "About Markdown Viewer",
            "Markdown Viewer - Three-column viewer with YAML support.",
        )

    def _on_associate_files(self) -> None:
        """Register file associations for .md/.yaml files."""
        success = associate_files()
        if success:
            QMessageBox.information(
                self,
                "File Association",
                "File association registered successfully.\n\n"
                "You can now right-click any .md/.yaml file → Open with → Markdown Viewer → Always.",
            )
        else:
            QMessageBox.warning(
                self,
                "File Association",
                "Failed to register file association.\n\n"
                "Please try running as administrator or check permissions.",
            )

    def _on_disassociate_files(self) -> None:
        """Remove file associations for .md/.yaml files."""
        reply = QMessageBox.question(
            self,
            "Remove File Association",
            "Remove file association for .md/.yaml files?\n\n"
            "This will remove Markdown Viewer from the Open with list.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            success = disassociate_files()
            if success:
                QMessageBox.information(
                    self,
                    "File Association",
                    "File association removed successfully.",
                )
            else:
                QMessageBox.warning(
                    self,
                    "File Association",
                    "Failed to remove file association.\n\n"
                    "Please try running as administrator or check permissions.",
                )

    def _set_view(self, mode: str) -> None:
        self._current_view = mode
        self._view_rendered.setChecked(mode == VIEW_RENDERED)
        self._view_original.setChecked(mode == VIEW_ORIGINAL)
        if mode == VIEW_RENDERED:
            self._preview.setHtml(self._html_doc)
        else:
            self._preview.setPlainText(self._content)

    def _on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open File", "", FILE_MASK
        )
        if path:
            self._load_file(path)

    def _load_file(self, path: str) -> None:
        """Read, parse and display the file."""
        # Check for unsaved changes before loading new file
        result = self._confirm_save()
        if result == QMessageBox.Cancel:
            return
        elif result == QMessageBox.Save:
            self._save_file()
        # Save scroll position of previous file
        if self._filepath:
            self._save_scroll_position()
        try:
            content = read_file(path)
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, "Error", f"Cannot read file:\n{exc}")
            return
        self._filepath = str(Path(path).resolve())
        self._content = content
        self._parser.parse(content)
        self._html_doc = self._parser.html
        # 若存在 YAML front matter，渲染并前置到 body HTML 之前
        if self._parser.frontmatter:
            fm_html = render_frontmatter_dict_to_html(self._parser.frontmatter)
            self._html_doc = fm_html + self._html_doc
        # 为图片添加内联样式和 HTML 属性，确保自适应右栏宽度
        if self._html_doc:
            self._html_doc = self._html_doc.replace(
                '<img ',
                '<img width="100%" style="max-width: 100%; height: auto; display: block; margin: 0 auto;" ',
            )
        self._current_titles = self._parser.titles
        ft = detect_file(path)
        fname = Path(path).name
        self.setWindowTitle(f"Markdown Viewer - {fname}")
        self._title_tree.clear()
        self._build_title_tree()
        if ft == FileType.MARKDOWN:
            base_url = QUrl.fromLocalFile(str(Path(self._filepath).parent) + "/")
            self._preview.document().setBaseUrl(base_url)
            self._pre_scale_resources()
            self._preview.setHtml(self._html_doc)
            line_info = f", {len(self._current_titles)} headings"
        elif ft == FileType.YAML:
            rendered = _render_yaml_safe(content)
            self._html_doc = rendered
            base_url = QUrl.fromLocalFile(str(Path(self._filepath).parent) + "/")
            self._preview.document().setBaseUrl(base_url)
            self._preview.setHtml(rendered)
            line_info = ""
        else:
            self._preview.setPlainText(content)
            line_info = ""
        self._source.setPlainText(content)
        # Restore scroll position if previously saved
        self._restore_scroll_position(path)
        self.statusBar().showMessage(f"{fname}  |  {len(content)} chars{line_info}")
        self._add_to_history(path)
        self._refresh_recent_menu()

    def _build_title_tree(self) -> None:
        if not self._current_titles:
            ph = QTreeWidgetItem(["No headings found"])
            ph.setFlags(ph.flags() & ~Qt.ItemIsSelectable)
            self._title_tree.addTopLevelItem(ph)
            self._title_tree.expandAll()
            return
        items = []
        for t in self._current_titles:
            indent = "  " * max(0, t.level - 1)
            item = QTreeWidgetItem([f"{indent}H{t.level}: {t.text}"])
            item.setData(0, Qt.UserRole, t.line_no)
            items.append(item)
        self._title_tree.addTopLevelItems(items)
        self._title_tree.expandAll()

    def _on_title_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        line_no = item.data(0, Qt.UserRole)
        if not line_no:
            return
        self._jump_to_heading_line(line_no)

    def _go_to_heading(self, delta: int) -> None:
        """Navigate to previous/next heading (called from menu shortcuts)."""
        titles = getattr(self, "_current_titles", []) or []
        if not titles:
            self.statusBar().showMessage("No headings to navigate", 2000)
            return

        idx = getattr(self, "_heading_index", -1)
        if idx < 0:
            # Initialize: find current position
            current = self._source.textCursor()
            current_block = self._source.document().findBlock(current.position())
            current_line = current_block.blockNumber() + 1
            for i, t in enumerate(titles):
                if t.line_no >= current_line:
                    idx = i - 1
                    break
            else:
                idx = len(titles) - 1

        # Move to next/previous heading
        idx = (idx + delta) % len(titles)
        idx = max(idx, 0)
        self._heading_index = idx
        target = titles[idx]
        self._jump_to_heading_line(target.line_no)
        self.statusBar().showMessage(f"Heading {idx + 1}/{len(titles)}: {target.text}", 2000)

    def _jump_to_heading_line(self, line_no: int) -> None:
        """Jump both source and preview to the given markdown line number."""
        if line_no < 1:
            return

        # Update source editor (direct line number mapping)
        source_cursor = self._source.textCursor()
        source_cursor.movePosition(source_cursor.Start)
        source_cursor.movePosition(
            source_cursor.Down, source_cursor.MoveAnchor, line_no - 1
        )
        self._source.setTextCursor(source_cursor)

        # Update preview by searching for the heading text
        # HTML-rendered blocks don't map 1:1 to markdown lines, so we find the text instead
        titles = getattr(self, "_current_titles", []) or []
        target_title = None
        for idx, t in enumerate(titles):
            if t.line_no == line_no:
                target_title = t
                self._heading_index = idx
                break

        if target_title:
            # Search for the heading text in preview and scroll to it
            html_doc = self._preview.document()
            cursor = html_doc.find(target_title.text, 0)  # Search from start
            if not cursor.isNull():
                self._preview.setTextCursor(cursor)
                self._preview.ensureCursorVisible()
            # If text search fails, fall back to block number (may work for early headings)
            else:
                block = html_doc.findBlockByNumber(max(0, line_no - 1))
                if block.isValid():
                    preview_cursor = self._preview.textCursor()
                    preview_cursor.setPosition(block.position())
                    self._preview.setTextCursor(preview_cursor)
                    self._preview.ensureCursorVisible()


    def _add_to_history(self, path: str) -> None:
        h = load_history()
        h = [x for x in h if x.get("path") != path]
        h.insert(0, {"path": path, "time": _now_iso()})
        save_history(h[:50])

    def _refresh_recent_menu(self) -> None:
        self._recent_menu.clear()
        history = load_history()[:15]
        if not history:
            a = QAction("(empty)", self)
            a.setEnabled(False)
            self._recent_menu.addAction(a)
            return
        for entry in history:
            p = entry.get("path", "")
            if not p or not Path(p).exists():
                continue
            a = QAction(Path(p).name, self)
            a.setToolTip(p)
            a.triggered.connect(lambda _, pp=p: self._load_file(pp))
            self._recent_menu.addAction(a)
        self._recent_menu.addSeparator()
        ca = QAction("Clear History", self)
        ca.triggered.connect(self._clear_history)
        self._recent_menu.addAction(ca)

    def _clear_history(self) -> None:
        save_history([])
        self._refresh_recent_menu()

    def _on_anchor_clicked(self, url) -> None:
        QDesktopServices.openUrl(url)

    def dragEnterEvent(self, event) -> None:
        """Handle drag enter event - accept file drops."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        """Handle drop event - open dropped file."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path and Path(file_path).is_file():
                    self._load_file(file_path)
                    break
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def eventFilter(self, obj, event) -> bool:
        """Allow file drops on column headers and preview area."""
        preview = getattr(self, '_preview', None)
        if preview is not None and obj in (preview, preview.viewport()):
            if event.type() == QEvent.DragEnter or event.type() == QEvent.DragMove:
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                    return True
            elif event.type() == QEvent.Drop and event.mimeData().hasUrls():
                    for url in event.mimeData().urls():
                        path = url.toLocalFile()
                        if path and Path(path).exists():
                            self._load_file(path)
                            break
                    event.acceptProposedAction()
                    return True
        if obj in (getattr(self, '_source_header', None), getattr(self, '_right_header', None)):
            if event.type() == QEvent.DragEnter:
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                    return True
            elif event.type() == QEvent.Drop and event.mimeData().hasUrls():
                    for url in event.mimeData().urls():
                        path = url.toLocalFile()
                        if path and Path(path).exists():
                            self._load_file(path)
                            break
                    event.acceptProposedAction()
                    return True
        return super().eventFilter(obj, event)

    def wheelEvent(self, event) -> None:
        """Handle mouse wheel event - zoom with Ctrl+Wheel."""
        if event.modifiers() == Qt.ControlModifier:
            # Ctrl + Wheel: zoom in/out
            delta = event.angleDelta().y()
            if delta > 0:
                self._increase_font()
            elif delta < 0:
                self._decrease_font()
            event.accept()
        else:
            # Normal wheel: scroll
            super().wheelEvent(event)

    def _increase_font(self) -> None:
        self._adjust_font(1)

    def _decrease_font(self) -> None:
        self._adjust_font(-1)

    def _adjust_font(self, delta: int) -> None:
        for w in (self._source,):
            f = QFont(w.font())
            f.setPointSize(max(f.pointSize() + delta, 6))
            w.setFont(f)
        # QTextBrowser: update both widget font and document default font
        pf = QFont(self._preview.font())
        pf.setPointSize(max(pf.pointSize() + delta, 6))
        self._preview.setFont(pf)
        self._preview.document().setDefaultFont(pf)

    def closeEvent(self, event) -> None:
        result = self._confirm_save()
        if result == QMessageBox.Cancel:
            event.ignore()
            return
        elif result == QMessageBox.Save:
            self._save_file()
        # Save scroll position of current file
        self._save_scroll_position()
        self._persist_scroll_positions()
        c = self._config
        c.setdefault("window", {})
        # Save normal geometry so we can restore exact size when not maximized
        geom = self.normalGeometry()
        c["window"]["width"] = geom.width()
        c["window"]["height"] = geom.height()
        c["window"]["splitter"] = self._splitter.sizes()
        c["window"]["maximized"] = self.isMaximized()
        save_config(c)
        super().closeEvent(event)

    def _on_source_changed(self) -> None:
        """Re-render preview when source text changes (debounced)."""
        if not self._filepath:
            return
        self._schedule_preview_update()

    def _schedule_preview_update(self) -> None:
        """Start debounce timer for preview re-render (used by source changes and splitter resize)."""
        try:
            self._debounce_timer.stop()
        except AttributeError:
            self._debounce_timer = QTimer(self)
            self._debounce_timer.setSingleShot(True)
            self._debounce_timer.timeout.connect(self._do_render_preview)
        # Larger files get longer debounce to avoid UI freezes
        content_len = len(self._source.toPlainText())
        if content_len > 1_000_000:
            delay = 500
        elif content_len > 500_000:
            delay = 400
        else:
            delay = 300
        self._debounce_timer.start(delay)

    def _do_render_preview(self) -> None:
        """Actual render triggered by debounce timer."""
        content = self._source.toPlainText()
        ft = detect_file(self._filepath)
        if ft == FileType.MARKDOWN:
            self._parser.parse(content)
            self._html_doc = self._parser.html
            if self._parser.frontmatter:
                fm_html = render_frontmatter_dict_to_html(self._parser.frontmatter)
                self._html_doc = fm_html + self._html_doc
            # 为图片添加内联样式，确保自适应右栏宽度
            if self._html_doc:
                self._html_doc = self._html_doc.replace(
                    '<img ',
                    '<img style="max-width: 100%; height: auto; display: block; margin: 0 auto;" ',
                )
            base_url = QUrl.fromLocalFile(str(Path(self._filepath).parent) + "/")
            self._preview.document().setBaseUrl(base_url)
            self._pre_scale_resources()
            self._preview.setHtml(self._html_doc)
        elif ft == FileType.YAML:
            rendered = _render_yaml_safe(content)
            self._html_doc = rendered
            base_url = QUrl.fromLocalFile(str(Path(self._filepath).parent) + "/")
            self._preview.document().setBaseUrl(base_url)
            self._preview.setHtml(rendered)
        else:
            self._preview.setPlainText(content)

    def _pre_scale_resources(self) -> None:
        """Pre-scale all <img> resources to fit the preview pane width.

        QTextDocument checks its resource cache via resource(ImageResource, url)
        when rendering <img> tags. By registering pre-scaled QPixmaps here
        (BEFORE setHtml), we bypass the need for CSS that Qt 5.15's rich text
        engine doesn't support.
        """
        import re

        html = getattr(self, "_html_doc", "")
        if not html:
            return

        srcs = re.findall(r'<img[^>]+src="([^"]+)"', html)
        if not srcs:
            return

        # Determine max render width from the preview pane's current width
        max_width = self._preview.viewport().width()
        if max_width <= 20:
            max_width = self._preview.width()
        max_width = max(max_width - 20, 100)  # 10px padding each side, floor 100px

        doc = self._preview.document()
        base_path = str(Path(self._filepath).parent) if self._filepath else ""
        base_url = QUrl.fromLocalFile(base_path + "/")

        for src in srcs:
            # Skip external URLs (only handle local files)
            if src.startswith(("http://", "https://", "ftp://")):
                continue

            # Resolve src against the document's base URL (handles relative paths)
            resolved_url = base_url.resolved(QUrl(src))
            img_path = resolved_url.toLocalFile()

            if not img_path or not Path(img_path).exists():
                continue

            pixmap = QPixmap(img_path)
            if pixmap.isNull():
                continue

            # Scale if wider than the preview pane
            if pixmap.width() > max_width:
                pixmap = pixmap.scaledToWidth(max_width, Qt.SmoothTransformation)

            # Register with the exact resolved URL QTextDocument will look up
            doc.addResource(QTextDocument.ImageResource, resolved_url, pixmap)

    def _is_modified(self) -> bool:
        """Check if the current document has unsaved changes."""
        if not self._filepath:
            return False
        return self._source.toPlainText() != self._content

    def _confirm_save(self) -> int:
        """Show save confirmation dialog. Returns QMessageBox.Yes/No/Cancel."""
        if not self._is_modified():
            return QMessageBox.No
        result = QMessageBox.question(
            self,
            "Unsaved Changes",
            "Document has been modified. Save changes?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        return result

    def _save_file(self) -> None:
        """Save current source content to disk (Ctrl+S)."""
        if not self._filepath:
            return
        content = self._source.toPlainText()
        try:
            with open(self._filepath, "w", encoding="utf-8") as f:
                f.write(content)
            self._content = content
            self.statusBar().showMessage(f"Saved: {Path(self._filepath).name}", 3000)
        except OSError as exc:
            QMessageBox.critical(self, "Save Error", f"Cannot save file: {exc}")

    def _save_file_as(self) -> None:
        """Save current source content to a new file (Ctrl+Shift+S)."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save As", "", FILE_MASK
        )
        if not path:
            return
        self._filepath = path
        self._save_file()

    def _close_document(self) -> None:
        """Close the current document without closing the app."""
        if not self._filepath:
            return
        result = self._confirm_save()
        if result == QMessageBox.Cancel:
            return
        elif result == QMessageBox.Save:
            self._save_file()
        self._save_scroll_position()
        self._filepath = ""
        self._content = ""
        self._html_doc = ""
        self._current_titles = []
        self._heading_index = -1
        self._source.clear()
        self._preview.clear()
        self._title_tree.clear()
        self._search_results = []
        self._search_index = 0
        self._search_input.clear()
        self._search_label.setText("")
        self._source.setExtraSelections([])
        self.setWindowTitle("Markdown Viewer")
        self.statusBar().showMessage("Ready")

    # ---- Search ----

    def _toggle_search_bar(self) -> None:
        """Toggle search bar visibility."""
        if self._search_bar.isVisible():
            self._search_bar.hide()
        else:
            self._search_bar.show()
            self._search_input.setFocus()
            self._search_input.selectAll()

    def _on_search_text_changed(self, text: str) -> None:
        """Live search as user types."""
        if text:
            self._do_search()
        else:
            self._search_results = []
            self._search_index = 0
            self._search_label.setText("")
            self._source.extraSelections([])

    def _do_search(self) -> None:
        """Execute search and update highlight + label."""
        query = self._search_input.text()
        content = self._source.toPlainText()
        self._search_results = find_in_text(content, query)
        self._search_index = 0
        if self._search_results:
            self._search_label.setText(f"1/{len(self._search_results)}")
            self._highlight_search_results()
            self._jump_to_search_result(0)
        else:
            self._search_label.setText("0/0")
            self._source.setExtraSelections([])

    def _search_next(self) -> None:
        """Move to next search match."""
        if not self._search_results:
            return
        self._search_index = (self._search_index + 1) % len(self._search_results)
        self._search_label.setText(f"{self._search_index + 1}/{len(self._search_results)}")
        self._jump_to_search_result(self._search_index)

    def _search_previous(self) -> None:
        """Move to previous search match."""
        if not self._search_results:
            return
        self._search_index = (self._search_index - 1) % len(self._search_results)
        self._search_label.setText(f"{self._search_index + 1}/{len(self._search_results)}")
        self._jump_to_search_result(self._search_index)

    def _jump_to_search_result(self, index: int) -> None:
        """Jump editor cursor to the given search result index."""
        if index < 0 or index >= len(self._search_results):
            return
        result = self._search_results[index]
        cursor = self._source.textCursor()
        cursor.movePosition(cursor.Start)
        cursor.movePosition(cursor.Down, cursor.MoveAnchor, result.line_no - 1)
        cursor.movePosition(cursor.Right, cursor.MoveAnchor, result.column - 1)
        cursor.movePosition(cursor.Right, cursor.KeepAnchor, len(result.text))
        self._source.setTextCursor(cursor)
        self._source.ensureCursorVisible()

    def _highlight_search_results(self) -> None:
        """Highlight all search matches in the editor."""
        selections = []
        for result in self._search_results:
            cursor = self._source.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.movePosition(cursor.Down, cursor.MoveAnchor, result.line_no - 1)
            cursor.movePosition(cursor.Right, cursor.MoveAnchor, result.column - 1)
            cursor.movePosition(cursor.Right, cursor.KeepAnchor, len(result.text))
            sel = QTextEdit.ExtraSelection()
            sel.cursor = cursor
            sel.format.setBackground(QColor(255, 255, 0))  # yellow highlight
            selections.append(sel)
        self._source.setExtraSelections(selections)

    def keyPressEvent(self, event) -> None:
        """Handle Escape to close search bar."""
        if event.key() == Qt.Key_Escape and self._search_bar.isVisible():
            self._search_bar.hide()
            return
        super().keyPressEvent(event)

    # ---- Scroll position memory ----

    def _save_scroll_position(self) -> None:
        """Save current scroll positions for the active file."""
        if not self._filepath:
            return
        self._scroll_positions[self._filepath] = {
            "editor_scroll": self._source.verticalScrollBar().value(),
        }

    def _restore_scroll_position(self, path: str) -> None:
        """Restore scroll position for a previously opened file."""
        # Check in-memory cache first, then config
        pos = self._scroll_positions.get(path)
        if pos is None:
            saved = self._config.get("scroll_positions", {})
            pos = saved.get(path)
        if pos:
            self._source.verticalScrollBar().setValue(pos.get("editor_scroll", 0))

    def _persist_scroll_positions(self) -> None:
        """Write current scroll positions to config.json."""
        self._config["scroll_positions"] = self._scroll_positions
        save_config(self._config)

    def _set_theme(self, mode: str) -> None:
        """Set theme mode and update menu checkmarks."""
        self._config["theme"] = mode
        for a in self._theme_group:
            a.setChecked(a.data() == mode)
        self._apply_theme(mode)

    def _set_custom_theme(self, colors: dict) -> None:
        """Set custom theme colors and apply."""
        self._config["theme"] = "system"
        self._config["custom_colors"] = colors
        for a in self._theme_group:
            a.setChecked(a.data() == "system")
        self._apply_theme("system")

    def _apply_theme(self, mode: str) -> None:
        """Apply palette based on mode: light / dark / system (custom)."""
        app = QApplication.instance()
        if not app:
            return

        if mode == "system":
            # Detect OS theme and route to the corresponding mode
            if _is_system_dark_theme():
                self._apply_theme("dark")
            else:
                self._apply_theme("light")
            return
        elif mode == "dark":
            colors = self._config.get("custom_colors", {})
            bg = colors.get("background", "#0f0f0f")
            fg = colors.get("foreground", "#e0e0e0")
            accent = colors.get("accent", "#0078d7")
            highlight = colors.get("highlight", "#0078d7")
            if fg == "#000000":
                fg = "#e0e0e0"
            from PyQt5.QtGui import QColor, QPalette
            pal = QPalette()
            pal.setColor(QPalette.Window, QColor(bg))
            pal.setColor(QPalette.WindowText, QColor(fg))
            pal.setColor(QPalette.Base, QColor(bg))
            pal.setColor(QPalette.AlternateBase, QColor(40, 40, 40))
            pal.setColor(QPalette.ToolTipBase, QColor(bg))
            pal.setColor(QPalette.ToolTipText, QColor(fg))
            pal.setColor(QPalette.Text, QColor(fg))
            pal.setColor(QPalette.Button, QColor(53, 53, 53))
            pal.setColor(QPalette.ButtonText, QColor(fg))
            pal.setColor(QPalette.BrightText, QColor(255, 0, 0))
            pal.setColor(QPalette.Link, QColor(accent))
            pal.setColor(QPalette.Highlight, QColor(highlight))
            pal.setColor(QPalette.HighlightedText, QColor(fg))
            app.setPalette(pal)
            # Remove individual widget stylesheets — use app-level stylesheet instead
            self._source.setStyleSheet("")
            self._preview.setStyleSheet("")
            self._title_tree.setStyleSheet("")
            self._title_tree.header().setStyleSheet("")
            self._preview.document().setDefaultStyleSheet(
                f"body {{ background-color: {bg}; color: {fg}; word-wrap: break-word; overflow-wrap: break-word; }} "
                f"a {{ color: {accent}; }} "
                f"code, pre {{ background-color: {bg}; color: {fg}; word-wrap: break-word; overflow-wrap: break-word; white-space: pre-wrap; }} "
                f"img {{ max-width: 100%; height: auto; }} "
                f"table {{ border-collapse: collapse; }} "
                f"th, td {{ border: 1px solid #888; padding: 4px 8px; }} "
                f"h1 {{ font-size: 24pt; }} "
                f"h2 {{ font-size: 18pt; }} "
                f"h3 {{ font-size: 16pt; }} "
                f"h4 {{ font-size: 14pt; }} "
                f"h5 {{ font-size: 12pt; }} "
                f"h6 {{ font-size: 12pt; }}"
            )
            self.menuBar().setStyleSheet("")
            self.statusBar().setStyleSheet("")
            app.setStyleSheet(
                f"QMainWindow {{ background-color: {bg}; }}"
                f"QPlainTextEdit {{ background-color: {bg}; color: {fg}; }}"
                f"QTextBrowser {{ background-color: {bg}; color: {fg}; }}"
                f"QTreeWidget {{ background-color: {bg}; color: {fg}; }}"
                f"QTreeWidget::item {{ color: {fg}; }}"
                f"QTreeWidget::item:selected {{ background-color: {accent}; color: {fg}; }}"
                f"QHeaderView {{ background-color: {bg}; color: {fg}; }}"
                f"QHeaderView::section {{ background-color: {bg}; color: {fg}; border: 1px solid #555; }}"
                f"QMenuBar {{ background-color: {bg}; color: {fg}; }}"
                f"QMenuBar::item {{ background-color: {bg}; color: {fg}; }}"
                f"QMenuBar::item:selected {{ background-color: {accent}; color: {fg}; }}"
                f"QStatusBar {{ background-color: {bg}; color: {fg}; }}"
                f"QToolTip {{ color: {fg}; background-color: {bg}; border: 1px solid #555; }}"
                f"QMenu {{ background-color: {bg}; color: {fg}; }}"
                f"QMenu::item {{ color: {fg}; }}"
                f"QMenu::item:selected {{ background-color: {accent}; color: {fg}; }}"
                f"QMessageBox {{ background-color: {bg}; color: {fg}; }}"
                f"QLabel {{ color: {fg}; }}"
                f"QPushButton {{ color: #000000; }}"
                f"QScrollBar:vertical {{ background-color: {bg}; }}"
                f"QScrollBar::handle:vertical {{ background-color: #444; }}"
                f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ background-color: {accent}; }}"
            )
            # Update syntax highlighter for dark mode
            self._highlighter.set_dark_mode(True)
        else:
            self._source.setStyleSheet("")
            self._preview.setStyleSheet("")
            self._title_tree.setStyleSheet("")
            self._title_tree.header().setStyleSheet("")
            self._preview.document().setDefaultStyleSheet(
                "body { word-wrap: break-word; overflow-wrap: break-word; } "
                "a { color: #0078d7; } "
                "code, pre { word-wrap: break-word; overflow-wrap: break-word; white-space: pre-wrap; } "
                "img { max-width: 100%; height: auto; } "
                "table { border-collapse: collapse; } "
                "th, td { border: 1px solid #ccc; padding: 4px 8px; } "
                "h1 { font-size: 24pt; } "
                "h2 { font-size: 18pt; } "
                "h3 { font-size: 16pt; } "
                "h4 { font-size: 14pt; } "
                "h5 { font-size: 12pt; } "
                "h6 { font-size: 12pt; }"
            )
            self.menuBar().setStyleSheet("")
            self.statusBar().setStyleSheet("")
            app.setStyleSheet("")
            app.setPalette(app.style().standardPalette())
            # Update syntax highlighter for light mode
            self._highlighter.set_dark_mode(False)


def _html_escape(text: str) -> str:
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _render_yaml_safe(content: str) -> str:
    try:
        import yaml
        data = yaml.safe_load(content)
        if data is None:
            data = {}
        return render_yaml_to_html(data)
    except (yaml.YAMLError, ValueError, TypeError, AttributeError):
        return f"<pre>{_html_escape(content)}</pre>"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MarkdownHighlighter(QSyntaxHighlighter):
    """Minimal Markdown syntax highlighter for QPlainTextEdit."""

    def __init__(self, parent=None, dark_mode: bool = False) -> None:
        super().__init__(parent)
        self._dark_mode = dark_mode
        self._rules = []
        self._setup_rules()

    def set_dark_mode(self, dark: bool) -> None:
        """Update highlight colors for dark/light mode."""
        self._dark_mode = dark
        self._rules.clear()
        self._setup_rules()
        self.rehighlight()

    def _setup_rules(self) -> None:
        # Colors based on theme
        if self._dark_mode:
            self._default_color = QColor(220, 220, 220)  # light gray for regular text
            heading_color = QColor(100, 180, 255)         # bright blue
            list_color = QColor(180, 180, 180)            # light gray
            code_color = QColor(100, 180, 255)            # bright blue
        else:
            self._default_color = QColor(0, 0, 0)         # black for regular text
            heading_color = QColor(0, 120, 215)           # standard blue
            list_color = QColor(100, 100, 100)            # medium gray
            code_color = QColor(0, 120, 215)              # standard blue

        # Heading formats (h1-h6): bold + color
        for level in range(1, 7):
            fmt = QTextCharFormat()
            fmt.setForeground(heading_color)
            fmt.setFontWeight(QFont.Bold)
            self._rules.append((f"^#{'#' * (level - 1)}\\s.+", fmt))

        # List items
        fmt_list = QTextCharFormat()
        fmt_list.setForeground(list_color)
        self._rules.append(("^[\\*\\-]\\s.+", fmt_list))

        # Fenced code block
        fmt_code = QTextCharFormat()
        fmt_code.setForeground(code_color)
        fmt_code.setFontFamily("Consolas")
        self._rules.append(("^```.+", fmt_code))

    def highlightBlock(self, text: str) -> None:
        # Set default color for ALL text first (regular text, no pattern match)
        default_fmt = QTextCharFormat()
        default_fmt.setForeground(self._default_color)
        self.setFormat(0, len(text), default_fmt)

        # Then apply pattern-specific formats on top
        for pattern, fmt in self._rules:
            import re
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


