from datetime import time
import os
import ollama
import markdown
import json
from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtWebEngineWidgets import QWebEngineView

from tools import get_current_date, fetch_url_content

CONFIG_FILE = "client_config.json"
CHAT_HISTORY_FILE = "chat_histories.json"  # <-- Add this line

ollama_client = ollama.Client(host="http://servery:11434")
try:
    models_response = ollama_client.list()
    models_list = models_response.get("models", [])
    model_names = [m.model for m in models_list]
except Exception as e:
    model_names = []
    print(f"Error fetching models: {e}")

selected_model = model_names[0] if model_names else None
system_prefix = "You are a helpful assistant."

def make_json_safe(obj):
    """Recursively convert unserializable objects to strings."""
    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_json_safe(i) for i in obj]
    try:
        json.dumps(obj)
        return obj
    except Exception:
        return str(obj)

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)

def load_chat_histories():
    if os.path.exists(CHAT_HISTORY_FILE):
        try:
            with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return []
                return json.loads(content)
        except Exception as e:
            print(f"Error loading chat histories: {e}")
    return []

def save_chat_histories(histories):
    try:
        # Make all histories JSON safe
        safe_histories = make_json_safe(histories)
        with open(CHAT_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(safe_histories, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving chat histories: {e}")

class ChatBubble(QtWidgets.QWidget):
    def __init__(self, message, role="assistant", think_content=None, last_json=None, parent=None, on_height_ready=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(8)
        if role == "user":
            icon = "🧑"
            bubble_color = "#e6f0fa"
            border_color = "#b3d1f2"
            align = QtCore.Qt.AlignmentFlag.AlignRight
        else:
            icon = "🤖"
            bubble_color = "#fffbe6"
            border_color = "#f2e6b3"
            align = QtCore.Qt.AlignmentFlag.AlignLeft

        icon_label = QtWidgets.QLabel(icon)
        icon_label.setFont(QtGui.QFont("Segoe UI Emoji", 14))
        icon_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        bubble = QtWidgets.QFrame()
        bubble.setStyleSheet(
            f"""
            background: {bubble_color};
            border-radius: 8px;
            border: 2.5px solid {border_color};
            """
        )
        bubble_layout = QtWidgets.QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(8, 4, 8, 4)
        bubble_layout.setSpacing(2)

        import re
        html = markdown.markdown(message, extensions=["tables", "fenced_code", "codehilite"])
        web_bg = bubble_color
        css = f"""
        <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; background: {web_bg}; color: #222; }}
        pre, code {{ background: #f5f5f5; border-radius: 4px; padding: 2px 4px; }}
        pre {{ padding: 8px; }}
        table {{ border-collapse: collapse; }}
        th, td {{ border: 1px solid #ccc; padding: 4px 8px; }}
        </style>
        """
        html = f"<!DOCTYPE html><html><head>{css}</head><body>{html}</body></html>"

        webview = QWebEngineView()
        webview.setHtml(html)
        webview.setMaximumWidth(480)

        # Set initial height to one text row
        font = QtGui.QFont("Segoe UI", 13)
        metrics = QtGui.QFontMetrics(font)
        one_row_height = metrics.lineSpacing() + 8  # +8 for padding
        webview.setMinimumHeight(one_row_height)
        webview.setMaximumHeight(one_row_height)
        webview.setFixedHeight(one_row_height)
        webview.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Minimum)
        webview.setStyleSheet("background: transparent; border: none;")
        webview.page().setBackgroundColor(QtGui.QColor(web_bg))
        bubble_layout.addWidget(webview)

        # Adjust height after content loads
        def adjust_height():
            def set_height():
                webview.page().runJavaScript(
                    """
                    (function() {
                        var body = document.body, html = document.documentElement;
                        return Math.max(
                            body.scrollHeight, body.offsetHeight, 
                            html.clientHeight, html.scrollHeight, html.offsetHeight
                        );
                    })();
                    """,
                    lambda h: (
                        webview.setMinimumHeight(one_row_height),
                        webview.setMaximumHeight(16777215),
                        webview.setFixedHeight(int(h) + 8 if h and int(h) > 0 else one_row_height),
                        on_height_ready() if on_height_ready else None
                    )
                )
            try:
                webview.loadFinished.disconnect()
            except Exception:
                pass
            webview.loadFinished.connect(lambda _: QtCore.QTimer.singleShot(50, set_height))
        QtCore.QTimer.singleShot(0, adjust_height)

        # Tooltip for think_content
        if think_content and role == "assistant":
            self._tooltip_timer = None

            def show_custom_tooltip(event):
                if self._tooltip_timer:
                    self._tooltip_timer.stop()
                    self._tooltip_timer.deleteLater()
                    self._tooltip_timer = None

                def actually_show():
                    if icon_label.underMouse():
                        global_pos = QtGui.QCursor.pos() + QtCore.QPoint(24, 12)
                        QtWidgets.QToolTip.showText(
                            global_pos,
                            f'<div style="max-width:180px;white-space:pre-wrap;">{think_content}</div>',
                            icon_label
                        )
                self._tooltip_timer = QtCore.QTimer()
                self._tooltip_timer.setSingleShot(True)
                self._tooltip_timer.timeout.connect(actually_show)
                self._tooltip_timer.start(180)
                return super(QtWidgets.QLabel, icon_label).enterEvent(event)

            def hide_custom_tooltip(event):
                if self._tooltip_timer:
                    self._tooltip_timer.stop()
                    self._tooltip_timer.deleteLater()
                    self._tooltip_timer = None
                QtWidgets.QToolTip.hideText()
                return super(QtWidgets.QLabel, icon_label).leaveEvent(event)

            icon_label.enterEvent = show_custom_tooltip
            icon_label.leaveEvent = hide_custom_tooltip

        # --- Double-click event for assistant icon to show request/response ---
        if role == "assistant":
            def show_response_dialog(event):
                dlg = QtWidgets.QDialog(self)
                dlg.setWindowTitle("Ollama Request/Response")
                dlg.resize(700, 500)
                layout = QtWidgets.QVBoxLayout(dlg)
                tabs = QtWidgets.QTabWidget()
                # Show request/response if available
                if last_json and isinstance(last_json, dict):
                    req_text = QtWidgets.QPlainTextEdit()
                    req_text.setReadOnly(True)
                    req_text.setPlainText(json.dumps(last_json.get("request", {}), indent=2, ensure_ascii=False))
                    tabs.addTab(req_text, "Request")
                    resp_text = QtWidgets.QPlainTextEdit()
                    resp_text.setReadOnly(True)
                    resp_text.setPlainText(json.dumps(last_json.get("response", {}), indent=2, ensure_ascii=False))
                    tabs.addTab(resp_text, "Response")
                else:
                    info = QtWidgets.QLabel("No request/response data available for this message.")
                    layout.addWidget(info)
                layout.addWidget(tabs)
                btn = QtWidgets.QPushButton("Close")
                btn.clicked.connect(dlg.accept)
                layout.addWidget(btn)
                dlg.exec()
            icon_label.mouseDoubleClickEvent = show_response_dialog

        if role == "user":
            layout.addStretch()
            layout.addWidget(bubble)
            layout.addWidget(icon_label)
        else:
            layout.addWidget(icon_label)
            layout.addWidget(bubble)
            layout.addStretch()

class ChatHistoryListWidget(QtWidgets.QListWidget):
    """Custom QListWidget to support trash icon for each item."""
    delete_chat_signal = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._icon_size = 18
        self._icon_padding = 10
        self._text_padding = 14
        self._vertical_padding = 27  # 18 * 1.5 = 27, increase by 50%
        self._trash_icon = QtGui.QIcon.fromTheme("edit-delete")
        if self._trash_icon.isNull():
            # Fallback to emoji if no icon found
            self._trash_pixmap = QtGui.QPixmap(18, 18)
            self._trash_pixmap.fill(QtCore.Qt.GlobalColor.transparent)
            painter = QtGui.QPainter(self._trash_pixmap)
            painter.end()
        else:
            self._trash_pixmap = self._trash_icon.pixmap(self._icon_size, self._icon_size)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QtGui.QPainter(self.viewport())
        for i in range(self.count()):
            rect = self.visualItemRect(self.item(i))
            # Add vertical padding (now increased by 50%)
            padded_rect = rect.adjusted(0, self._vertical_padding, 0, -self._vertical_padding)
            # Draw trash icon
            icon_rect = QtCore.QRect(
                padded_rect.left() + self._icon_padding,
                padded_rect.center().y() - self._icon_size // 2,
                self._icon_size,
                self._icon_size
            )
            painter.drawPixmap(icon_rect, self._trash_pixmap)
            # Draw label to the right of the icon
            text_rect = QtCore.QRect(
                icon_rect.right() + self._text_padding,
                padded_rect.top(),
                padded_rect.width() - (icon_rect.width() + self._icon_padding + self._text_padding),
                padded_rect.height()
            )
            hist = self.item(i).data(QtCore.Qt.ItemDataRole.UserRole)
            label = hist["title"] if hist and "title" in hist else self.item(i).text()
            painter.setPen(self.palette().color(QtGui.QPalette.ColorRole.Text))
            painter.drawText(text_rect, int(QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft), label)
        painter.end()

    def sizeHintForRow(self, row):
        # Increase row height for extra padding (now increased by 50%)
        base = super().sizeHintForRow(row)
        return base + 2 * self._vertical_padding

    def mousePressEvent(self, event):
        for i in range(self.count()):
            rect = self.visualItemRect(self.item(i))
            icon_rect = QtCore.QRect(
                rect.left() + self._icon_padding,
                rect.center().y() - self._icon_size // 2,
                self._icon_size,
                self._icon_size
            )
            if icon_rect.contains(event.pos()):
                self.delete_chat_signal.emit(i)
                return  # Don't select the item if trash is clicked
        super().mousePressEvent(event)

class ChatVBoxLayout(QtWidgets.QVBoxLayout):
    """A QVBoxLayout that always scrolls its parent QScrollArea to the bottom when a widget is added."""
    def __init__(self, parent_widget, scroll_area):
        super().__init__(parent_widget)
        self._scroll_area = scroll_area

    def addWidget(self, widget, stretch=0, alignment=QtCore.Qt.AlignmentFlag(0)):
        super().addWidget(widget, stretch, alignment)

    def insertWidget(self, index, widget, stretch=0, alignment=QtCore.Qt.AlignmentFlag(0)):
        super().insertWidget(index, widget, stretch, alignment)

    def scroll_to_bottom(self):
        if self._scroll_area and self._scroll_area.widget():
            self._scroll_area.widget().adjustSize()
            QtCore.QCoreApplication.processEvents()
            scrollbar = self._scroll_area.verticalScrollBar()
            end_value = scrollbar.maximum()
            # Animate only if not already at the bottom
            if scrollbar.value() != end_value:
                anim = QtCore.QPropertyAnimation(scrollbar, b"value")
                anim.setDuration(400)
                anim.setStartValue(scrollbar.value())
                anim.setEndValue(end_value)
                anim.setEasingCurve(QtCore.QEasingCurve.Type.InOutQuad)
                # Keep a reference to prevent garbage collection
                self._scroll_anim = anim
                anim.start()
            else:
                scrollbar.setValue(end_value)

# --- Add to config section ---
DEFAULT_PROFILES = [
    {"name": "Default", "prefix": "You are a helpful assistant."}
]

def load_profiles():
    config = load_config()
    return config.get("profiles", DEFAULT_PROFILES.copy())

def save_profiles(profiles):
    config = load_config()
    config["profiles"] = profiles
    save_config(config)

def get_selected_profile_idx():
    config = load_config()
    return config.get("selected_profile_idx", 0)

def set_selected_profile_idx(idx):
    config = load_config()
    config["selected_profile_idx"] = idx
    save_config(config)

class MainWindow(QtWidgets.QMainWindow):
    update_chat_signal = QtCore.pyqtSignal(str, object, object)  # reply, think_content, last_json
    scroll_to_bottom_signal = QtCore.pyqtSignal()
    update_thinking_label_signal = QtCore.pyqtSignal(str)  # <-- Already present

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.profiles = load_profiles()
        self.selected_profile_idx = get_selected_profile_idx()
        global system_prefix
        system_prefix = self.profiles[self.selected_profile_idx]["prefix"]
        self.setWindowTitle("Client Window")
        self.resize(800, 600)
        if "geometry" in self.config:
            self.restoreGeometry(QtCore.QByteArray.fromHex(self.config["geometry"].encode()))

        # Load chat histories from disk
        self.chat_histories = load_chat_histories()
        if not self.chat_histories:
            self.chat_histories = []
        self.current_history_idx = None
        self.chat_history = []

        main_widget = QtWidgets.QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QtWidgets.QHBoxLayout(main_widget)

        # Left panel
        left_panel = QtWidgets.QVBoxLayout()
        main_layout.addLayout(left_panel, 0)

        # Model dropdown
        model_label = QtWidgets.QLabel("Model")
        left_panel.addWidget(model_label)
        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.addItems(model_names)
        initial_model = self.config.get("selected_model")
        if initial_model and initial_model in model_names:
            self.model_combo.setCurrentText(initial_model)
        self.model_combo.currentTextChanged.connect(self.save_model)
        left_panel.addWidget(self.model_combo)

        # Prefix button
        # prefix_btn = QtWidgets.QPushButton("Prefix")
        # prefix_btn.clicked.connect(self.open_prefix_modal)
        # left_panel.addWidget(prefix_btn)

        # --- Profile selection panel (replace prefix button) ---
        profile_label = QtWidgets.QLabel("Profiles")
        left_panel.addWidget(profile_label)
        add_profile_btn = QtWidgets.QPushButton("+ New Profile")
        add_profile_btn.clicked.connect(self.add_new_profile)
        left_panel.addWidget(add_profile_btn)
        self.profile_list = QtWidgets.QListWidget()
        self.profile_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.profile_list.itemSelectionChanged.connect(self.on_profile_select)
        self.profile_list.itemDoubleClicked.connect(self.edit_profile_dialog)
        left_panel.addWidget(self.profile_list)
        self.refresh_profile_list()
        self.profile_list.setCurrentRow(self.selected_profile_idx)

        # Chat history panel
        self.chat_history_list = ChatHistoryListWidget()
        self.chat_history_list.itemSelectionChanged.connect(self.on_chat_history_select)
        self.chat_history_list.delete_chat_signal.connect(self.delete_chat_by_index)
        add_chat_btn = QtWidgets.QPushButton("+ New Chat")
        add_chat_btn.clicked.connect(self.add_new_chat)
        left_panel.addWidget(add_chat_btn)
        left_panel.addWidget(self.chat_history_list, 1)

        # Right panel (vertical splitter)
        right_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        main_layout.addWidget(right_splitter, 1)

        # Chat area (scrollable)
        chat_area_widget = QtWidgets.QWidget()
        # Replace QVBoxLayout with ChatVBoxLayout
        self.chat_scroll = QtWidgets.QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setStyleSheet("""
    QScrollArea { border: none; background: transparent; }
    QScrollBar:vertical, QScrollBar:horizontal {
        width: 0px;
        height: 0px;
        background: transparent;
    }
""")
        self.chat_area_layout = ChatVBoxLayout(chat_area_widget, self.chat_scroll)
        self.chat_area_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.chat_area_layout.setSpacing(0)
        self.chat_area_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_scroll.setWidget(chat_area_widget)

        # Prompt area container (packs prompt at the bottom)
        prompt_area = QtWidgets.QWidget()
        prompt_area_layout = QtWidgets.QVBoxLayout(prompt_area)
        prompt_area_layout.setContentsMargins(0, 0, 0, 0)
        prompt_area_layout.setSpacing(0)
        prompt_area_layout.addWidget(self.chat_scroll, 1)  # stretch=1, fills available space

        # Command prompt (styled like user chat bubble, with user icon)
        self.prompt_container = QtWidgets.QWidget()
        prompt_layout = QtWidgets.QHBoxLayout(self.prompt_container)
        prompt_layout.setContentsMargins(8, 4, 8, 4)
        prompt_layout.setSpacing(8)

        user_icon_label = QtWidgets.QLabel("🧑")
        user_icon_label.setFont(QtGui.QFont("Segoe UI Emoji", 14))
        user_icon_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        self.command_prompt = QtWidgets.QTextEdit()
        self.command_prompt.setFixedHeight(60)
        self.command_prompt.installEventFilter(self)
        # Style to match user chat bubble
        self.command_prompt.setStyleSheet("""
            QTextEdit {
                background: #e6f0fa;
                border: 2.5px solid #b3d1f2;
                border-radius: 8px;
                padding: 8px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
                color: #222;
                margin-left: 0px;
                margin-right: 0px;
            }
        """)

        prompt_layout.addStretch(1)
        prompt_layout.addWidget(self.command_prompt, 6)  # 6/8 = 75%
        prompt_layout.addWidget(user_icon_label, 1)      # 1/8 = 12.5%

        prompt_area_layout.addWidget(self.prompt_container, 0)

        right_splitter.addWidget(prompt_area)

        # Now install event filter for chat_history_list (after command_prompt is created)
        self.chat_history_list.installEventFilter(self)

        self.add_new_chat_if_needed()
        self.update_chat_signal.connect(self.update_chat)
        self.scroll_to_bottom_signal.connect(self.chat_area_layout.scroll_to_bottom)
        self.update_thinking_label_signal.connect(self.update_thinking_label)  # <-- Already present

    def save_model(self, text):
        self.config["selected_model"] = text
        save_config(self.config)

    def open_prefix_modal(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Edit System Message Prefix")
        dlg.resize(400, 300)
        layout = QtWidgets.QVBoxLayout(dlg)
        text_area = QtWidgets.QTextEdit()
        text_area.setPlainText(system_prefix)
        layout.addWidget(text_area)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(btns)
        btns.accepted.connect(lambda: self.save_prefix(dlg, text_area))
        btns.rejected.connect(dlg.reject)
        dlg.exec()

    def save_prefix(self, dlg, text_area):
        global system_prefix
        system_prefix = text_area.toPlainText()
        self.config["system_prefix"] = system_prefix
        save_config(self.config)
        dlg.accept()

    def add_new_chat_if_needed(self):
        # Helper to ensure at least one chat exists on startup
        if not self.chat_histories:
            self.add_new_chat()
        else:
            self.current_history_idx = 0
            self.chat_history = list(self.chat_histories[0]["history"])
            self.refresh_chat_history_list()
            self.chat_history_list.setCurrentRow(0)
            self.clear_chat_area()
            for msg in self.chat_history:
                think_content = msg.get("think_content") if msg.get("role") == "assistant" else None
                last_json = msg.get("last_json") if msg.get("role") == "assistant" else None
                self.add_chat_bubble(msg["content"], msg["role"], think_content=think_content, last_json=last_json)

    def add_new_chat(self):
        self.chat_history = []
        self.chat_histories.append({"title": "New chat", "history": []})
        self.current_history_idx = len(self.chat_histories) - 1
        self.refresh_chat_history_list()
        self.chat_history_list.setCurrentRow(self.current_history_idx)
        self.clear_chat_area()
        save_chat_histories(self.chat_histories)  # <-- Save after adding

    def on_chat_history_select(self):
        idx = self.chat_history_list.currentRow()
        if idx < 0 or idx >= len(self.chat_histories):
            return
        self.current_history_idx = idx
        self.chat_history = list(self.chat_histories[idx]["history"])
        self.clear_chat_area()
        for msg in self.chat_history:
            think_content = msg.get("think_content") if msg.get("role") == "assistant" else None
            # last_json = msg.get("last_json") if msg.get("role") == "assistant" else None
            self.add_chat_bubble(msg["content"], msg["role"], think_content=think_content, last_json=None)  # <-- Remove last_json

    def clear_chat_area(self):
        # Remove thinking label if present
        self.remove_thinking_bubble()
        while self.chat_area_layout.count():
            item = self.chat_area_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def add_chat_bubble(self, text, role="assistant", think_content=None, last_json=None):
        # Remove thinking label if present before adding a new bubble
        self.remove_thinking_bubble()
        bubble = ChatBubble(
            text, role=role, think_content=think_content, last_json=None,  # <-- Remove last_json from history
            on_height_ready=lambda: QtCore.QTimer.singleShot(0, self.scroll_to_bottom_signal.emit)
        )
        self.chat_area_layout.addWidget(bubble)

        QtCore.QTimer.singleShot(100, lambda: self.scroll_to_bottom_signal.emit())

    def eventFilter(self, obj, event):
        # Handle delete key for chat history deletion
        if obj == self.chat_history_list and event.type() == QtCore.QEvent.Type.KeyPress:
            if event.key() == QtCore.Qt.Key.Key_Delete:
                self.delete_selected_chat()
                return True
        # Defensive: check if command_prompt exists before comparing
        if hasattr(self, "command_prompt") and obj == self.command_prompt and event.type() == QtCore.QEvent.Type.KeyPress:
            if event.key() == QtCore.Qt.Key.Key_Return and not event.modifiers():
                self.on_command_prompt_enter()
                return True
        return super().eventFilter(obj, event)

    def delete_chat_by_index(self, idx):
        if idx < 0 or idx >= len(self.chat_histories):
            return
        del self.chat_histories[idx]
        if not self.chat_histories:
            self.add_new_chat()
        else:
            # Select the next chat, or previous if last was deleted
            if idx >= len(self.chat_histories):
                idx = len(self.chat_histories) - 1
            self.current_history_idx = idx
            self.chat_history = list(self.chat_histories[idx]["history"])
            self.refresh_chat_history_list()
            self.chat_history_list.setCurrentRow(idx)
            self.clear_chat_area()
            for msg in self.chat_history:
                self.add_chat_bubble(msg["content"], msg["role"])
        self.refresh_chat_history_list()
        save_chat_histories(self.chat_histories)  # <-- Save after delete

    def delete_selected_chat(self):
        idx = self.chat_history_list.currentRow()
        if idx < 0 or idx >= len(self.chat_histories):
            return
        del self.chat_histories[idx]
        if not self.chat_histories:
            self.add_new_chat()
        else:
            # Select the next chat, or previous if last was deleted
            if idx >= len(self.chat_histories):
                idx = len(self.chat_histories) - 1
            self.current_history_idx = idx
            self.chat_history = list(self.chat_histories[idx]["history"])
            self.refresh_chat_history_list()
            self.chat_history_list.setCurrentRow(idx)
            self.clear_chat_area()
            for msg in self.chat_history:
                self.add_chat_bubble(msg["content"], msg["role"])
        self.refresh_chat_history_list()
        save_chat_histories(self.chat_histories)  # <-- Save after delete

    def on_command_prompt_enter(self):
        text = self.command_prompt.toPlainText().strip()
        if text:
            self.add_chat_bubble(text, role="user")
            self.command_prompt.clear()
            self.chat_history.append({"role": "user", "content": text})
            if self.current_history_idx is not None:
                self.chat_histories[self.current_history_idx]["history"] = list(self.chat_history)
                first_user = next((m for m in self.chat_history if m["role"] == "user"), None)
                if first_user:
                    words = first_user["content"].split()
                    self.chat_histories[self.current_history_idx]["title"] = " ".join(words[:6]) + ("..." if len(words) > 6 else "")
                self.refresh_chat_history_list()
                save_chat_histories(self.chat_histories)  # <-- Save after user message
            last_json = {"request": None, "response": None}
            self.add_thinking_bubble()
            QtCore.QTimer.singleShot(100, lambda: self.ollama_query(text, last_json))

    def add_thinking_bubble(self, tool_name=None):
        # Remove any existing thinking label before adding a new one
        self.remove_thinking_bubble()

        # Hide the prompt panel while thinking
        self.prompt_container.setVisible(False)

        # Create a container widget for padding
        container = QtWidgets.QWidget()
        h_layout = QtWidgets.QHBoxLayout(container)
        h_layout.setContentsMargins(8, 0, 0, 0)
        h_layout.setSpacing(8)  # Spacing between icon and label
        h_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)  # <-- Ensure left alignment

        label = QtWidgets.QLabel("💡")
        label.setFont(QtGui.QFont("Arial", 18))
        label.setStyleSheet("background: transparent; padding: 2px;")  # <-- No border
        h_layout.addWidget(label)

        # Add thinking label (bold)
        self._thinking_text_label = QtWidgets.QLabel()
        font = QtGui.QFont()
        font.setBold(True)
        self._thinking_text_label.setFont(font)
        self._thinking_text_label.setStyleSheet("background: transparent; color: #222; padding: 2px;")  # <-- No border
        h_layout.addWidget(self._thinking_text_label)
        if tool_name:
            self._thinking_text_label.setText(f"Using tool <{tool_name}>")
        else:
            self._thinking_text_label.setText("Thinking...")

        self.chat_area_layout.addWidget(container)
        self._thinking_label = container

        # Add fade animation
        effect = QtWidgets.QGraphicsOpacityEffect(label)
        label.setGraphicsEffect(effect)
        anim = QtCore.QPropertyAnimation(effect, b"opacity")
        anim.setDuration(1200)
        anim.setStartValue(0.2)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QtCore.QEasingCurve.Type.InOutQuad)
        anim.setLoopCount(1)  # Only once, we'll restart manually

        def on_finished():
            # Reverse direction and restart
            if anim.direction() == QtCore.QAbstractAnimation.Direction.Forward:
                anim.setDirection(QtCore.QAbstractAnimation.Direction.Backward)
            else:
                anim.setDirection(QtCore.QAbstractAnimation.Direction.Forward)
            anim.start()

        anim.finished.connect(on_finished)
        anim.start()
        self._thinking_anim = anim

    def update_thinking_label(self, tool_name=None):
        # Accepts a string or None
        if hasattr(self, "_thinking_text_label") and self._thinking_text_label:
            if tool_name:
                self._thinking_text_label.setText(f"Using tool {tool_name}")
            else:
                self._thinking_text_label.setText("Thinking...")

    def remove_thinking_bubble(self):
        has = hasattr(self, "_thinking_label") and self._thinking_label
        # Stop and delete animation if present
        if hasattr(self, "_thinking_anim") and self._thinking_anim:
            self._thinking_anim.stop()
            self._thinking_anim = None
        if hasattr(self, "_thinking_label") and self._thinking_label:
            self.chat_area_layout.removeWidget(self._thinking_label)
            self._thinking_label.deleteLater()
            self._thinking_label = None
        if hasattr(self, "_thinking_text_label"):
            self._thinking_text_label = None
        # Show the prompt panel again when not thinking
        if hasattr(self, "prompt_container"):
            self.prompt_container.setVisible(True)
            # Give focus to the command prompt when it becomes visible
            QtCore.QTimer.singleShot(0, self.command_prompt.setFocus)

    def update_chat(self, reply, think_content, last_json):
        self.remove_thinking_bubble()
        self.add_chat_bubble(reply, role="assistant", think_content=think_content, last_json=None)  # <-- Remove last_json
        # Save after assistant reply
        if self.current_history_idx is not None:
            save_chat_histories(self.chat_histories)

    def refresh_chat_history_list(self):
        self.chat_history_list.clear()
        for hist in self.chat_histories:
            item = QtWidgets.QListWidgetItem()
            # Store the history dict for custom painting
            item.setData(QtCore.Qt.ItemDataRole.UserRole, hist)
            # Set a custom size hint for 50% taller rows
            base_height = self.chat_history_list.fontMetrics().height()
            # Estimate a good width (adjust as needed)
            width = 220
            # 2.5x the font height is a good starting point for a "tall" row
            item.setSizeHint(QtCore.QSize(width, int(base_height * 2.5)))
            self.chat_history_list.addItem(item)

    def refresh_profile_list(self):
        self.profile_list.clear()
        for prof in self.profiles:
            item = QtWidgets.QListWidgetItem(prof["name"])
            self.profile_list.addItem(item)

    def on_profile_select(self):
        idx = self.profile_list.currentRow()
        if idx < 0 or idx >= len(self.profiles):
            return
        self.selected_profile_idx = idx
        set_selected_profile_idx(idx)
        global system_prefix
        system_prefix = self.profiles[idx]["prefix"]

    def add_new_profile(self):
        new_profile = {"name": "New Profile", "prefix": "You are a helpful assistant."}
        self.profiles.append(new_profile)
        save_profiles(self.profiles)
        self.refresh_profile_list()
        self.profile_list.setCurrentRow(len(self.profiles) - 1)
        self.edit_profile_dialog(self.profile_list.currentItem())

    def edit_profile_dialog(self, item):
        idx = self.profile_list.row(item)
        if idx < 0 or idx >= len(self.profiles):
            return
        prof = self.profiles[idx]
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Edit Profile")
        dlg.resize(400, 320)
        layout = QtWidgets.QVBoxLayout(dlg)
        name_label = QtWidgets.QLabel("Profile Name:")
        name_edit = QtWidgets.QLineEdit(prof["name"])
        layout.addWidget(name_label)
        layout.addWidget(name_edit)
        prefix_label = QtWidgets.QLabel("Prefix:")
        prefix_edit = QtWidgets.QTextEdit(prof["prefix"])
        layout.addWidget(prefix_label)
        layout.addWidget(prefix_edit)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(btns)
        def save_profile():
            prof["name"] = name_edit.text().strip() or "Profile"
            prof["prefix"] = prefix_edit.toPlainText()
            self.profiles[idx] = prof
            save_profiles(self.profiles)
            self.refresh_profile_list()
            self.profile_list.setCurrentRow(idx)
            # If this is the selected profile, update system_prefix
            if idx == self.selected_profile_idx:
                global system_prefix
                system_prefix = prof["prefix"]
            dlg.accept()
        btns.accepted.connect(save_profile)
        btns.rejected.connect(dlg.reject)
        dlg.exec()

    def ollama_query(self, text, last_json):
        import re
        import threading
        def run():
            try:
                model = self.model_combo.currentText() or selected_model
                # --- Use selected profile's prefix ---
                prefix = self.profiles[self.selected_profile_idx]["prefix"]
                messages = [
                    {"role": "control", "content": "thinking"},
                    {"role": "system", "content": "Enable deep thinking subroutine."},
                    {"role": "system", "content": prefix},
                ] + self.chat_history
                last_json["request"] = {"model": model, "messages": messages}
                tools_text = self.config.get("tools", "").strip()
                response = None
                tool_error = False
                if tools_text:
                    last_json["request"]["tools"] = tools_text
                    try:
                        response = ollama_client.chat(model=model, messages=messages, tools=[get_current_date, fetch_url_content])
                    except Exception as e:
                        if hasattr(e, "args") and e.args and "does not support tools" in str(e.args[0]):
                            tool_error = True
                            response = ollama_client.chat(model=model, messages=messages)
                        else:
                            raise
                else:
                    response = ollama_client.chat(model=model, messages=messages)
                last_json["response"] = response
                tool_calls = response.get("message", {}).get("tool_calls")
                if tool_calls and not tool_error:
                    tool_results = []
                    for call in tool_calls:
                        tool_name = call.function.name
                        arguments = call.function.arguments
                        print(f"Tool call: {tool_name}, Arguments: {arguments}")
                        # Use the signal to update the thinking label in the main thread
                        self.update_thinking_label_signal.emit(tool_name)
                        # Now process the tool
                        if tool_name == "get_current_date":
                            result = get_current_date(**arguments) if isinstance(arguments, dict) else get_current_date()
                        elif tool_name == "fetch_url_content":
                            result = fetch_url_content(**arguments) if isinstance(arguments, dict) else fetch_url_content()
                        else:
                            result = f"Unknown tool: {tool_name}"
                        tool_results.append({"role": "tool", "content": result, 'name': tool_name})
                    messages = messages + [{
                        "role": "system",
                        "tool_calls": [{
                            'function': {
                                'name': call.function.name,
                                'arguments': call.function.arguments
                            }
                        } for call in tool_calls],
                    }] + tool_results
                    try:
                        tool_response = ollama_client.chat(model=model, messages=messages, tools=[get_current_date, fetch_url_content])
                    except Exception as e:
                        if hasattr(e, "args") and e.args and "does not support tools" in str(e.args[0]):
                            tool_response = ollama_client.chat(model=model, messages=messages)
                        else:
                            raise
                    reply = tool_response.get("message", {}).get("content", "No response.")
                    think_match = re.search(r"<think>(.*?)</think>", reply, re.DOTALL | re.IGNORECASE)
                    think_content = think_match.group(1).strip() if think_match else None
                    if think_match:
                        reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL | re.IGNORECASE).strip()
                else:
                    # Reset thinking label if no tool is being used
                    self.update_thinking_label_signal.emit("")
                    reply = response.get("message", {}).get("content", "No response.")
                    think_match = re.search(r"<think>(.*?)</think>", reply, re.DOTALL | re.IGNORECASE)
                    think_content = think_match.group(1).strip() if think_match else None
                    if think_match:
                        reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL | re.IGNORECASE).strip()
            except Exception as e:
                import traceback
                reply = f"Error: {e}\n{traceback.format_exc()}"
                think_content = None
            # --- Save think_content and last_json with assistant message ---
            self.chat_history.append({
                "role": "assistant",
                "content": reply,
                "think_content": think_content
                # "last_json": last_json  # <-- Remove this line
            })
            if self.current_history_idx is not None:
                self.chat_histories[self.current_history_idx]["history"] = list(self.chat_history)
                self.refresh_chat_history_list()
            self.update_chat_signal.emit(reply, think_content, last_json)
        # When starting, show "Thinking..." by default
        QtCore.QTimer.singleShot(0, lambda: self.add_thinking_bubble())
        threading.Thread(target=run, daemon=True).start()

    def closeEvent(self, event):
        self.config["geometry"] = self.saveGeometry().toHex().data().decode()
        self.config["selected_model"] = self.model_combo.currentText()
        self.config["profiles"] = self.profiles
        self.config["selected_profile_idx"] = self.selected_profile_idx
        save_config(self.config)
        save_chat_histories(self.chat_histories)
        event.accept()

if __name__ == "__main__":
    import sys
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6 import QtWidgets, QtCore

    app = QtWidgets.QApplication(sys.argv)

    # Create dummy after QApplication to pre-initialize WebEngine
    dummy = QWebEngineView()
    dummy.deleteLater()

    # Now show your main window
    win = MainWindow()
    win.show()

    sys.exit(app.exec())

