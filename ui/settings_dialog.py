"""
Settings dialog — modern tabbed UI for editing all Raphael configuration.
Settings are saved to settings.toml in the user data directory.
"""

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QCompleter, QDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
    QDoubleSpinBox, QMessageBox, QDialogButtonBox, QScrollArea, QFrame,
    QAbstractItemView,
)

import config
from _user_settings.settings_manager import save
from orchestrator.endpoint_registry import Endpoint


# ── Premium Dark Teal Styling ─────────────────────────────────

_DARK_STYLE = """
QDialog {
    background-color: #0f172a;
    color: #cbd5e1;
    font-family: "Segoe UI", -apple-system, sans-serif;
    font-size: 12px;
}
QTabWidget::pane {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 8px;
}
QTabBar::tab {
    background-color: #1e293b;
    color: #94a3b8;
    border: 1px solid #1e293b;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 16px;
    margin-right: 4px;
    font-weight: 500;
}
QTabBar::tab:selected {
    background-color: #0f172a;
    color: #14b8a6;
    border-color: #1e293b;
    border-bottom-color: #0f172a;
    border-bottom: 2px solid #14b8a6;
}
QTabBar::tab:hover:!selected {
    background-color: #334155;
    color: #e2e8f0;
}
QGroupBox {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    margin-top: 16px;
    padding-top: 18px;
    font-size: 12px;
    font-weight: bold;
    color: #14b8a6;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 2px 8px;
    background-color: #1e293b;
    border-radius: 4px;
}
QLabel {
    color: #cbd5e1;
}
QLineEdit {
    background-color: #0f172a;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}
QLineEdit:focus {
    border: 1px solid #14b8a6;
}
QComboBox {
    background-color: #0f172a;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 10px;
    min-width: 150px;
}
QComboBox:focus {
    border: 1px solid #14b8a6;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left-width: 0px;
}
QComboBox QAbstractItemView {
    background-color: #0f172a;
    color: #f8fafc;
    selection-background-color: #1e293b;
    selection-color: #14b8a6;
    border: 1px solid #334155;
}
QSpinBox, QDoubleSpinBox {
    background-color: #0f172a;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 10px;
    min-width: 80px;
}
QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #14b8a6;
}
QCheckBox {
    spacing: 8px;
    font-size: 12px;
    color: #cbd5e1;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #334155;
    border-radius: 4px;
    background-color: #0f172a;
}
QCheckBox::indicator:checked {
    background-color: #14b8a6;
    border-color: #14b8a6;
}
QCheckBox::indicator:hover {
    border-color: #14b8a6;
}
QListWidget {
    background-color: #0f172a;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px;
    font-size: 13px;
}
QListWidget::item {
    background-color: #1e293b;
    color: #f8fafc;
    padding: 8px 14px;
    margin-bottom: 4px;
    border: 1px solid #334155;
    border-radius: 6px;
    min-height: 24px;
}
QListWidget::item:hover {
    background-color: #334155;
    border-color: #14b8a6;
}
QListWidget::item:selected {
    background-color: #0d9488;
    color: #ffffff;
    border: 1px solid #14b8a6;
    font-weight: bold;
}
QPushButton {
    background-color: #0f172a;
    color: #14b8a6;
    border: 1px solid #14b8a6;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #14b8a6;
    color: #0f172a;
}
QPushButton:pressed {
    background-color: #0d9488;
}
QScrollBar:vertical {
    border: none;
    background: #0f172a;
    width: 8px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #334155;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #14b8a6;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    border: none;
    background: none;
}
"""


# ── Helpers ────────────────────────────────────────────────────

def _make_section(title: str, parent: QWidget) -> QGroupBox:
    g = QGroupBox(title, parent)
    layout = QFormLayout()
    layout.setContentsMargins(16, 20, 16, 16)
    layout.setSpacing(12)
    layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
    g.setLayout(layout)
    return g


def _add_row(box: QGroupBox, label: str, widget: QWidget, help_text: str = ""):
    layout = box.layout()
    assert isinstance(layout, QFormLayout)
    lbl = QLabel(label)
    lbl.setStyleSheet("font-weight: 500; color: #f1f5f9;")
    layout.addRow(lbl, widget)
    if help_text:
        help_lbl = QLabel(help_text)
        help_lbl.setStyleSheet("color: #94a3b8; font-size: 11px; margin-top: -4px; margin-bottom: 4px;")
        layout.addRow("", help_lbl)


def _make_field(value: str, placeholder: str = "", password: bool = False) -> QLineEdit:
    field = QLineEdit(value)
    field.setPlaceholderText(placeholder)
    if password:
        field.setEchoMode(QLineEdit.EchoMode.Password)
    return field


class ScrollableTab(QWidget):
    """Base scrollable tab to prevent overflow."""
    def __init__(self, parent=None):
        super().__init__(parent)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._scroll_area = QScrollArea(self)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_area.setStyleSheet("background-color: transparent;")

        self.container = QWidget()
        self.container.setStyleSheet("background-color: transparent;")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(12, 12, 12, 12)
        self.container_layout.setSpacing(12)

        self._scroll_area.setWidget(self.container)
        main_layout.addWidget(self._scroll_area)

    def collect(self) -> dict:
        return {}


# ── Tabs ───────────────────────────────────────────────────────

class _DiscoverThread(QThread):
    """Background thread for model discovery without blocking the UI."""

    done = pyqtSignal(list)  # list[str] — discovered model IDs

    def __init__(self, base_url: str, api_key: str):
        super().__init__()
        self._base_url = base_url
        self._api_key = api_key

    def run(self):
        from orchestrator.health_check import discover_models
        models = discover_models(self._base_url, self._api_key)
        self.done.emit(models)


class AddFallbackModelDialog(QDialog):
    """Custom premium dialog to select/type fallback models with fuzzy search."""
    def __init__(self, available_models: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Fallback Model")
        self.setStyleSheet(_DARK_STYLE)
        self.resize(400, 150)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        lbl = QLabel("Select or type a fallback model name:")
        lbl.setStyleSheet("font-weight: 500; color: #f1f5f9;")
        layout.addWidget(lbl)
        
        self.combo = QComboBox(self)
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo.setPlaceholderText("Select or enter model name…")
        
        # Filter empty items and dynamic info placeholders from the source list
        clean_models = [m for m in available_models if m and not m.startswith("dynamic")]
        self.combo.addItems(["", *clean_models])
        
        # Setup fuzzy completer
        completer = QCompleter(self)
        completer.setModel(self.combo.model())
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.combo.setCompleter(completer)
        
        layout.addWidget(self.combo)
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def get_selected(self) -> str:
        return self.combo.currentText().strip()


class AddEndpointDialog(QDialog):
    """Smart add-endpoint dialog with autocomplete, dynamic field visibility, and auto-test."""

    def __init__(self, endpoints: list, endpoint: Endpoint | None = None, parent=None):
        super().__init__(parent)
        self._endpoints = endpoints
        self._endpoint = endpoint
        self._edit_mode = endpoint is not None

        if self._edit_mode:
            self.setWindowTitle(f"Edit Endpoint — {endpoint.name}")  # type: ignore[union-attr]
        else:
            self.setWindowTitle("Add Endpoint")

        self._known_source: dict | None = None  # matched provider.json entry
        self._loaded_existing_ep_name: str | None = None  # Track if we loaded an existing endpoint
        self._all_source_models: list[str] = []
        self._discover_thread: _DiscoverThread | None = None
        self._disco_gen = 0  # incremented each time discovery starts; _on_discovery_done checks it to avoid stale callbacks
        self._discoving_models: list[str] = []  # discovered + already in combos
        self._processing_source = False  # guard against double fire from builtin.activated + textActivated
        self._last_source_text = ""  # track actual source changes, skipping completer popup-dismissal noise
        self._closed = False
        self.setMinimumWidth(560)
        self._build_ui()

        if self._edit_mode and endpoint is not None:
            self._load_endpoint_data(endpoint)

    # ── UI construction ──────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── Endpoint Source (autocomplete from provider.json) ──
        source_group = QGroupBox("Endpoint Source")
        src_layout = QFormLayout(source_group)
        src_layout.setSpacing(8)
        src_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Name: editable combo with live fuzzy search and suggestions
        self._source_combo = QComboBox()
        self._source_combo.setEditable(True)
        self._source_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._source_combo.setPlaceholderText("Search known providers or enter custom name…")
        self._source_combo.setMinimumWidth(300)

        # Populate once at startup to avoid clearing/rebuilding model while typing
        from orchestrator.provider_catalog import list_providers
        providers = list_providers()
        self._source_combo.addItem("")  # Empty initial option
        for src in providers:
            label = f"{src.get('label', src.get('name', '?'))}"
            self._source_combo.addItem(label, src)

        # Reuse the built-in completer with contains-based fuzzy matching
        # so that up/down arrow keys navigate the native dropdown correctly
        # while still showing suggestions as the user types.
        builtin = self._source_combo.completer()
        if builtin is not None:
            builtin.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            builtin.setFilterMode(Qt.MatchFlag.MatchContains)
            builtin.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            self._source_combo.setCompleter(builtin)
            builtin.activated.connect(self._on_source_text_changed)

        le = self._source_combo.lineEdit()
        if le is not None:
            le.textChanged.connect(self._update_ui_states)
        # textActivated fires on explicit selection from the native dropdown
        # or pressing Enter.  The completer's activated signal covers selections
        # from the suggestion popup.  Either way, run the full provider lookup
        # + dynamic discovery only when the user actually commits a choice.
        self._source_combo.textActivated.connect(self._on_source_text_changed)
        src_layout.addRow("Name", self._source_combo)

        # Source status label (known vs custom)
        self._source_status = QLabel("")
        self._source_status.setStyleSheet("color: #64748b; font-size: 11px; font-style: italic;")
        src_layout.addRow("", self._source_status)

        # Discovery status label (shown while fetching models dynamically)
        self._discovery_status = QLabel("")
        self._discovery_status.setStyleSheet("color: #f59e0b; font-size: 11px; font-style: italic;")
        self._discovery_status.setVisible(False)
        src_layout.addRow("", self._discovery_status)

        # Base URL — hidden when source is known
        self._url_field = _make_field("", "https://api.example.com/v1")
        self._url_field.textChanged.connect(self._update_ui_states)
        self._url_label = QLabel("Base URL")
        src_layout.addRow(self._url_label, self._url_field)

        # API Key — always visible
        self._key_field = _make_field("", "sk-...", password=True)
        src_layout.addRow("API Key", self._key_field)

        layout.addWidget(source_group)

        # ── Models ────────────────────────────────────────────
        models_box = QGroupBox("Models")
        mod_layout = QFormLayout(models_box)
        mod_layout.setSpacing(8)
        mod_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._text_model = self._make_model_combo("Primary LLM model")
        self._text_model.currentTextChanged.connect(self._update_ui_states)
        mod_layout.addRow("LLM Model", self._text_model)

        self._vision_model = self._make_model_combo("Vision / multimodal model")
        mod_layout.addRow("Vision Model", self._vision_model)

        self._fallback_list = QListWidget()
        self._fallback_list.setMaximumHeight(120)
        self._fallback_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        fb_row = QHBoxLayout()
        fb_row.addWidget(self._fallback_list, 1)
        fb_col = QVBoxLayout()
        fb_col.setSpacing(4)
        fb_add_btn = QPushButton("+ Add")
        fb_add_btn.clicked.connect(self._add_fallback)
        fb_rm_btn = QPushButton("- Remove")
        fb_rm_btn.clicked.connect(self._remove_fallback)
        fb_col.addWidget(fb_add_btn)
        fb_col.addWidget(fb_rm_btn)
        # Up/down reorder buttons for fallback models
        fb_up_btn = QPushButton("▲ Up")
        fb_up_btn.clicked.connect(lambda: self._move_fallback(-1))
        fb_down_btn = QPushButton("▼ Down")
        fb_down_btn.clicked.connect(lambda: self._move_fallback(1))
        fb_col.addWidget(fb_up_btn)
        fb_col.addWidget(fb_down_btn)
        fb_row.addLayout(fb_col)
        mod_layout.addRow("Fallbacks", fb_row)

        self._stt_model = self._make_model_combo("STT model (e.g. whisper)")
        mod_layout.addRow("STT Model", self._stt_model)

        self._tts_model = self._make_model_combo("TTS model (e.g. elevenlabs)")
        mod_layout.addRow("TTS Model", self._tts_model)

        layout.addWidget(models_box)

        # ── Auto-test ─────────────────────────────────────────
        self._test_check = QCheckBox("Test primary model after saving")
        self._test_check.setChecked(True)
        self._test_check.setStyleSheet("color: #94a3b8;")
        layout.addWidget(self._test_check)

        # ── Buttons ───────────────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        self._save_btn = QPushButton("Save & Test")
        self._save_btn.setStyleSheet("""
            QPushButton {
                background-color: #059669; color: white; font-weight: bold;
                padding: 8px 24px; border-radius: 6px; font-size: 13px;
            }
            QPushButton:hover { background-color: #10b981; }
            QPushButton:disabled { background-color: #334155; color: #64748b; }
        """)
        self._save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(self._save_btn)
        layout.addLayout(btn_layout)

        # Initial state: show base URL for custom, no source selected
        self._set_known_source(None)

    @staticmethod
    def _make_model_combo(placeholder: str) -> QComboBox:
        c = QComboBox()
        c.setEditable(True)
        c.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        c.setPlaceholderText(placeholder)
        c.setMinimumWidth(220)
        
        # Setup fuzzy completer to give search suggestion list as user types
        completer = QCompleter(c)
        completer.setModel(c.model())
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        c.setCompleter(completer)
        
        return c

    # ── Source autocomplete ──────────────────────────────────────

    def _on_source_text_changed(self, text: str):
        """Update self._known_source and load existing endpoint data if name matches."""
        # Guard against double fire: both builtin.activated and textActivated fire
        # when user selects from the completer popup.
        if self._processing_source:
            return
        # Skip if text hasn't actually changed (e.g. completer popup dismissal
        # re-fires activated with the same highlighted text).
        if text.strip() == self._last_source_text:
            return
        self._last_source_text = text.strip()
        self._processing_source = True
        try:
            self._do_source_changed(text)
        finally:
            self._processing_source = False

    def _do_source_changed(self, text: str):
        from orchestrator.provider_catalog import list_providers
        providers = list_providers()

        t = text.strip().lower()

        # Check if the name matches any existing endpoint
        matched_endpoint = None
        if t:
            for ep in self._endpoints:
                if ep.name.strip().lower() == t:
                    matched_endpoint = ep
                    break

        if matched_endpoint is not None:
            # Record that we loaded this existing endpoint
            self._loaded_existing_ep_name = matched_endpoint.name

            # Find if it matches a known provider
            matched = None
            for src in providers:
                label = f"{src.get('label', src.get('name', '?'))}".lower()
                name = f"{src.get('name', '')}".lower()
                url = f"{src.get('base_url', '')}".lower()
                if (matched_endpoint.name.strip().lower() in (label, name)) or (matched_endpoint.base_url.strip().rstrip("/").lower() == url.rstrip("/")):
                    matched = src
                    break

            self._set_known_source(matched)

            # Populate saved values
            self._url_field.setText(matched_endpoint.base_url)
            self._key_field.setText(matched_endpoint.api_key)
            self._set_combo_text_or_add(self._text_model, matched_endpoint.text_model)
            self._set_combo_text_or_add(self._vision_model, matched_endpoint.vision_model)
            self._set_combo_text_or_add(self._stt_model, matched_endpoint.stt_model)
            self._set_combo_text_or_add(self._tts_model, matched_endpoint.tts_model)

            self._fallback_list.clear()
            fbs = matched_endpoint.fallback_models or ([matched_endpoint.fallback_model] if matched_endpoint.fallback_model else [])
            for fb in fbs:
                if fb:
                    self._fallback_list.addItem(fb)
        else:
            # If they previously loaded an existing endpoint but have now typed away from it,
            # reset the fields so they don't carry over the old endpoint's credentials/settings.
            if self._loaded_existing_ep_name is not None:
                self._loaded_existing_ep_name = None
                self._url_field.setText("")
                self._key_field.setText("")
                self._text_model.setCurrentText("")
                self._vision_model.setCurrentText("")
                self._stt_model.setCurrentText("")
                self._tts_model.setCurrentText("")
                self._fallback_list.clear()
                self._set_known_source(None)

            # Proceed normally with provider search
            matched = None
            if t:
                for src in providers:
                    label = f"{src.get('label', src.get('name', '?'))}".lower()
                    name = f"{src.get('name', '')}".lower()
                    if t in (label, name):
                        matched = src
                        break

            if matched != self._known_source:
                self._set_known_source(matched)

    def _set_known_source(self, src: dict | None):
        """Toggle between known-source and custom-source UI state."""
        # Kill any in-flight discovery
        if self._discover_thread and self._discover_thread.isRunning():
            self._discover_thread.quit()
            self._discover_thread.wait()
            self._discover_thread = None

        self._known_source = src
        self._discovery_status.setVisible(False)

        if src is not None:
            # Known source: hide base URL, lock it, show status
            self._source_status.setText("Known source — base URL pre-set")
            self._url_field.setText(src.get("base_url", ""))
            self._url_field.setVisible(False)
            self._url_label.setVisible(False)

            # Populate model dropdowns from static data
            static_text: list[str] = [
                m for m in (src.get("text_models") or [])
                if m and not m.lower().startswith("dynamic") and not m.startswith("1000")
            ]
            default_text = src.get("text_model", "")
            if default_text and (default_text.lower().startswith("dynamic") or default_text.startswith("1000")):
                default_text = ""

            self._all_source_models = list(static_text)
            self._populate_model_combo(self._text_model, static_text, default_text)
            self._populate_model_combo(self._vision_model, src.get("vision_models") or [], src.get("vision_model", ""))
            self._populate_model_combo(self._stt_model, src.get("stt_models") or [], src.get("stt_model", ""))
            self._populate_model_combo(self._tts_model, src.get("tts_models") or [], src.get("tts_model", ""))

            # Trigger dynamic discovery if this source needs it
            if src.get("_needs_discovery"):
                self._start_discovery()
        else:
            # Custom source: show base URL field, clear status
            custom_text = self._source_combo.currentText().strip()
            if custom_text:
                self._source_status.setText("Custom endpoint — enter base URL manually")
            else:
                self._source_status.setText("Type to search, or enter custom source name")
            self._url_field.setVisible(True)
            self._url_label.setVisible(True)
            self._all_source_models = []

        # Update enable/disable field states progressively
        self._update_ui_states()

    def _update_ui_states(self):
        has_name = bool(self._source_combo.currentText().strip())
        is_known = self._known_source is not None

        # 2. Base URL field depends on Name being entered, and NOT being a known source
        show_url = has_name and not is_known
        self._url_field.setVisible(show_url)
        self._url_label.setVisible(show_url)
        self._url_field.setEnabled(show_url)

        has_url = bool(self._url_field.text().strip())

        # 3. API Key depends on:
        #    - Name entered
        #    - AND (is a known source OR (is custom source and has base URL entered))
        enable_key = has_name and (is_known or (not is_known and has_url))
        self._key_field.setEnabled(enable_key)

        # 4. Models (Text, STT, TTS) depend on key field being enabled
        self._text_model.setEnabled(enable_key)
        self._stt_model.setEnabled(enable_key)
        self._tts_model.setEnabled(enable_key)

        # Vision model is enabled only if key field is enabled AND (it's custom OR the known source has vision models or uses dynamic discovery)
        enable_vision = enable_key
        if is_known:
            vision_models = self._known_source.get("vision_models") or []  # type: ignore[union-attr]
            needs_disco = self._known_source.get("_needs_discovery", False)  # type: ignore[union-attr]
            if not vision_models and not needs_disco:
                enable_vision = False
        self._vision_model.setEnabled(enable_vision)
        if not enable_vision:
            self._vision_model.setCurrentText("")

        # 5. Remaining (Fallbacks, Save button, etc.) depend on a primary LLM model being selected/entered
        has_primary_model = bool(self._text_model.currentText().strip())
        enable_remaining = enable_key and has_primary_model

        self._fallback_list.setEnabled(enable_remaining)
        self._test_check.setEnabled(enable_remaining)
        self._save_btn.setEnabled(enable_remaining)

    def _load_endpoint_data(self, ep: Endpoint):
        """Pre-populate all form fields from an existing endpoint for editing."""
        self._source_combo.setCurrentText(ep.name)
        # Run source-changed logic to match provider catalog (enables discovery, model populators)
        self._do_source_changed(ep.name)
        self._last_source_text = ep.name.strip().lower()  # prevent stray completer re-trigger
        # Override all fields with actual endpoint values (respect overrides from catalog defaults)
        self._url_field.setText(ep.base_url)
        self._key_field.setText(ep.api_key)
        self._text_model.setCurrentText(ep.text_model)
        self._vision_model.setCurrentText(ep.vision_model)
        self._stt_model.setCurrentText(ep.stt_model)
        self._tts_model.setCurrentText(ep.tts_model)
        models = ep.fallback_models or ([ep.fallback_model] if ep.fallback_model else [])
        self._fallback_list.clear()
        for m in models:
            if m:
                self._fallback_list.addItem(m)
        self._update_ui_states()
        # Let _update_ui_states handle URL visibility based on provider matching

    # ── Dynamic model discovery ──────────────────────────────────

    def closeEvent(self, event):  # noqa: N802
        """Clean up background discovery thread when the dialog is closed."""
        self._closed = True
        if self._discover_thread and self._discover_thread.isRunning():
            self._discover_thread.quit()
            self._discover_thread.wait(2000)
        super().closeEvent(event)

    def _start_discovery(self):
        """Fetch models from the endpoint's ``/v1/models`` in background."""
        base_url = self._url_field.text().strip()
        api_key = self._key_field.text().strip()
        if not base_url:
            return

        self._discovery_status.setText("Fetching available models…")
        self._discovery_status.setVisible(True)

        self._disco_gen += 1
        self._discover_thread = _DiscoverThread(base_url, api_key)
        self._discover_thread.done.connect(self._on_discovery_done)
        self._discover_thread.start()

    def _on_discovery_done(self, models: list[str]):
        """Merge discovered models into the model combos."""
        gen = self._disco_gen  # snapshot before thread reference is cleared
        self._discovery_status.setVisible(False)
        self._discover_thread = None

        # Stale callback — user switched sources or dialog closed, ignore
        if gen != self._disco_gen or self._closed:
            return

        if not models:
            return

        # Merge discovered models into all source models
        existing = set(self._all_source_models)
        new_models = [m for m in models if m not in existing]
        if not new_models:
            return

        merged = self._all_source_models + new_models
        self._all_source_models = merged

        # Update text model combo
        current_text = self._text_model.currentText()
        self._populate_model_combo(self._text_model, merged, current_text or "")

        # Populate vision combo with ALL discovered models — model IDs from
        # providers like OpenCode don't carry capability flags (e.g. no
        # "vision" keyword), so the user decides which model is vision-capable.
        current_vision = self._vision_model.currentText()
        existing_vision = set(self._vision_model.itemText(i) for i in range(self._vision_model.count()))
        all_for_vision = sorted(existing_vision | set(merged))
        self._populate_model_combo(self._vision_model, all_for_vision, current_vision or "")

        self._source_status.setText(
            f"Known source — base URL pre-set  ({len(new_models)} models discovered)"
        )

    @staticmethod
    def _populate_model_combo(combo: QComboBox, items: list[str], default: str):
        combo.clear()
        combo.addItem("")
        for item in items:
            if item:
                combo.addItem(item)
        if default:
            combo.setCurrentText(default)

    @staticmethod
    def _set_combo_text_or_add(combo: QComboBox, text: str):
        if not text:
            combo.setCurrentText("")
            return
        index = combo.findText(text)
        if index == -1:
            combo.addItem(text)
        combo.setCurrentText(text)

    # ── Fallback management ──────────────────────────────────────

    def _add_fallback(self):
        """Add a model to the fallback list (primary LLM excluded)."""
        primary = self._text_model.currentText().strip()
        available = [m for m in self._all_source_models if m != primary]

        dlg = AddFallbackModelDialog(available, self)
        if dlg.exec() == 1:
            text = dlg.get_selected()
            if text:
                if text == primary:
                    QMessageBox.warning(self, "Invalid", "Primary LLM model cannot be a fallback.")
                    return
                # Check for duplicates (silently ignore if already exists)
                existing = []
                for i in range(self._fallback_list.count()):
                    item = self._fallback_list.item(i)
                    if item is not None:
                        existing.append(item.text().strip())
                if text in existing:
                    return
                self._fallback_list.addItem(text)

    def _remove_fallback(self):
        current = self._fallback_list.currentItem()
        if current:
            self._fallback_list.takeItem(self._fallback_list.row(current))

    def _move_fallback(self, direction: int):
        """Move the selected fallback model up (-1) or down (+1)."""
        row = self._fallback_list.currentRow()
        if row < 0:
            return
        new_row = row + direction
        if new_row < 0 or new_row >= self._fallback_list.count():
            return
        item = self._fallback_list.takeItem(row)
        self._fallback_list.insertItem(new_row, item)
        self._fallback_list.setCurrentRow(new_row)

    # ── Save & Test ──────────────────────────────────────────────

    def _on_save(self):
        """Validate, optionally test, then accept."""
        data = self.get_endpoint_data()
        errors = []

        if not data["name"]:
            errors.append("Endpoint name is required.")
        if not data["base_url"]:
            errors.append("Base URL is required.")
        if not data["api_key"]:
            pass  # key is optional (local models don't need one)
        if not data["text_model"]:
            errors.append("Primary LLM model is required.")

        # Validate fallback models don't include primary
        primary = data["text_model"]
        fallbacks = data["fallback_models"]
        if primary and fallbacks and primary in fallbacks:
            errors.append(f"Primary model '{primary}' cannot also be a fallback.")

        if errors:
            QMessageBox.warning(self, "Validation Error",
                                "\n\n".join(errors))
            return

        if self._test_check.isChecked():
            self._save_btn.setEnabled(False)
            self._save_btn.setText("Testing...")
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()  # render "Testing..." before blocking
            test_passed = self._run_test(data)
            if not test_passed:
                return

        self.accept()

    def _run_test(self, data: dict) -> bool:
        """Ping the endpoint in a blocking call (background thread for real usage)."""
        from orchestrator.health_check import ping_endpoint

        try:
            result = ping_endpoint(
                base_url=data["base_url"],
                api_key=data["api_key"],
                model=data["text_model"],
            )
            if result.ok:
                QMessageBox.information(
                    self, "Test Passed",
                    f"✅  {data['text_model']} responded OK ({result.latency_ms}ms)\n\n"
                    "Endpoint is ready to use."
                )
                return True
            else:
                reply = QMessageBox.warning(
                    self, "Test Failed",
                    f"❌  {data['text_model']} — {result.error}\n\n"
                    "Save anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                return reply == QMessageBox.StandardButton.Yes
        except Exception as e:
            reply = QMessageBox.warning(
                self, "Test Failed",
                f"❌  Testing crashed — {e}\n\n"
                "Save anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            return reply == QMessageBox.StandardButton.Yes
        finally:
            self._save_btn.setEnabled(True)
            self._save_btn.setText("Save & Test")

    # ── Data access ──────────────────────────────────────────────

    def get_endpoint_data(self) -> dict:
        fallback_items: list[str] = []
        for i in range(self._fallback_list.count()):
            item = self._fallback_list.item(i)
            if item and item.text().strip():
                fallback_items.append(item.text().strip())

        return {
            "name": self._source_combo.currentText().strip(),
            "base_url": self._url_field.text().strip().rstrip("/"),
            "api_key": self._key_field.text().strip(),
            "text_model": self._text_model.currentText().strip(),
            "vision_model": self._vision_model.currentText().strip(),
            "stt_model": self._stt_model.currentText().strip(),
            "tts_model": self._tts_model.currentText().strip(),
            "fallback_models": fallback_items,
            "fallback_model": fallback_items[0] if fallback_items else "",
        }

class EndpointsConfigTab(ScrollableTab):
    """Dynamic endpoint configuration — no hardcoded backends.

    Users can add/edit/delete/reorder any OpenAI-compatible endpoint.
    Each endpoint has name, base_url, api_key, text_model, vision_model,
    fallback_model, priority, and tags. Persisted to settings.toml.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._endpoints: list[Endpoint] = []
        self._card_widgets: list[QGroupBox] = []
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────

    def _build_ui(self):
        self._refresh_from_registry()

        header = _make_section("Manage Endpoints", self.container)
        info = QLabel(
            "Add any OpenAI-compatible API endpoint. "
            "Adjust endpoint priority order in the Priority tab."
        )
        info.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: normal;")
        header.layout().addRow("", info)  # type: ignore[union-attr]

        add_btn = QPushButton("+ Add Endpoint")
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #059669; color: white; font-weight: bold;
                padding: 8px 20px; border-radius: 6px; font-size: 13px;
            }
            QPushButton:hover { background-color: #10b981; }
        """)
        add_btn.clicked.connect(self._on_add)
        header.layout().addRow("", add_btn)  # type: ignore[union-attr]

        self.container_layout.addWidget(header)
        self._render_cards()

        self.container_layout.addStretch()

    def _refresh_from_registry(self):
        """Load current endpoints from the dynamic registry."""
        from orchestrator.endpoint_registry import all as _all_eps
        self._endpoints = list(_all_eps())

    def _render_cards(self):
        """Rebuild the endpoint card list."""
        # Remove old cards
        for card in self._card_widgets:
            self.container_layout.removeWidget(card)
            card.deleteLater()
        self._card_widgets.clear()

        self._refresh_from_registry()
        for i, ep in enumerate(self._endpoints):
            card = self._build_card(ep, i)
            self._card_widgets.append(card)
            self.container_layout.insertWidget(
                self.container_layout.count() - 1, card  # before stretch
            )

    def _build_card(self, ep: Endpoint, index: int) -> QGroupBox:
        """Build a card with all endpoint fields editable inline."""
        box = QGroupBox(ep.name)
        box.setObjectName(f"ep_card_{ep.name}")
        box.setStyleSheet("""
            QGroupBox#ep_card_* {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                margin-top: 12px;
                padding: 16px;
                font-weight: bold;
                color: #14b8a6;
            }
        """)
        layout = QFormLayout(box)
        layout.setSpacing(6)
        layout.setContentsMargins(12, 20, 12, 12)

        # Name field (full width) — read-only display
        name_field = _make_field(ep.name, placeholder="e.g. my-ollama")
        name_field.setObjectName(f"ep_name_{index}")
        name_field.setReadOnly(True)
        name_field.setStyleSheet("color: #e2e8f0; background: transparent; border: none; font-weight: bold;")
        name_field.setToolTip("Unique name for this endpoint")
        layout.addRow("Name", name_field)

        # Base URL — read-only display
        url_field = _make_field(ep.base_url, placeholder="https://api.example.com/v1")
        url_field.setObjectName(f"ep_url_{index}")
        url_field.setReadOnly(True)
        url_field.setStyleSheet("color: #94a3b8; background: transparent; border: none;")
        layout.addRow("Base URL", url_field)

        # API key (masked, read-only with toggle to peek)
        key_field = _make_field(ep.api_key, placeholder="sk-...", password=True)
        key_field.setObjectName(f"ep_key_{index}")
        key_field.setReadOnly(True)
        key_field.setStyleSheet("color: #94a3b8; background: transparent; border: none;")
        key_row = QHBoxLayout()
        key_row.addWidget(key_field, 1)
        key_toggle = QPushButton("[show]")
        key_toggle.setFixedWidth(36)
        key_toggle.clicked.connect(
            lambda checked, f=key_field: f.setEchoMode(
                QLineEdit.EchoMode.Normal if f.echoMode() == QLineEdit.EchoMode.Password
                else QLineEdit.EchoMode.Password
            )
        )
        key_row.addWidget(key_toggle)
        layout.addRow("API Key", key_row)

        # LLM Models row (Text & Vision only) — read-only display
        llm_grid = QHBoxLayout()
        text_model = _make_field(ep.text_model, placeholder="text model")
        text_model.setObjectName(f"ep_text_{index}")
        text_model.setReadOnly(True)
        text_model.setStyleSheet("color: #94a3b8; background: transparent; border: none;")
        vision_model = _make_field(ep.vision_model, placeholder="vision model")
        vision_model.setObjectName(f"ep_vision_{index}")
        vision_model.setReadOnly(True)
        vision_model.setStyleSheet("color: #94a3b8; background: transparent; border: none;")
        llm_grid.addWidget(QLabel("Text:"))
        llm_grid.addWidget(text_model, 1)
        llm_grid.addWidget(QLabel("Vision:"))
        llm_grid.addWidget(vision_model, 1)
        layout.addRow("LLM Models", llm_grid)

        # Fallback Models row — tag-style badges
        fb_widget = QWidget()
        fb_widget.setStyleSheet("background: transparent;")
        fb_layout = QHBoxLayout(fb_widget)
        fb_layout.setContentsMargins(0, 0, 0, 0)
        fb_layout.setSpacing(6)

        models = ep.fallback_models or ([ep.fallback_model] if ep.fallback_model else [])
        any_fb = False
        for fb_m in models:
            if fb_m:
                any_fb = True
                tag = QLabel(fb_m)
                tag.setStyleSheet(
                    "background-color: #0f172a; color: #94a3b8; "
                    "padding: 2px 8px; border-radius: 4px; "
                    "border: 1px solid #334155; font-size: 11px;"
                )
                fb_layout.addWidget(tag)
        if not any_fb:
            empty = QLabel("—")
            empty.setStyleSheet("color: #475569; font-style: italic;")
            fb_layout.addWidget(empty)
        fb_layout.addStretch()
        layout.addRow("Fallbacks", fb_widget)

        # STT / TTS Models row — read-only display
        audio_grid = QHBoxLayout()
        stt_model = _make_field(ep.stt_model, placeholder="STT model (e.g. whisper-large-v3)")
        stt_model.setObjectName(f"ep_stt_{index}")
        stt_model.setReadOnly(True)
        stt_model.setStyleSheet("color: #94a3b8; background: transparent; border: none;")
        tts_model = _make_field(ep.tts_model, placeholder="TTS model (e.g. eleven_multilingual_v2)")
        tts_model.setObjectName(f"ep_tts_{index}")
        tts_model.setReadOnly(True)
        tts_model.setStyleSheet("color: #94a3b8; background: transparent; border: none;")
        audio_grid.addWidget(QLabel("STT:"))
        audio_grid.addWidget(stt_model, 1)
        audio_grid.addWidget(QLabel("TTS:"))
        audio_grid.addWidget(tts_model, 1)
        layout.addRow("Audio Models", audio_grid)

        # Actions row — Edit opens the full dialog, Delete removes
        actions = QHBoxLayout()
        actions.addStretch()

        edit_btn = QPushButton("Edit")
        edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #0ea5e9; color: white; padding: 4px 14px;
                border-radius: 4px; font-weight: bold;
            }
            QPushButton:hover { background-color: #38bdf8; }
        """)
        edit_btn.clicked.connect(lambda checked, name=ep.name: self._on_edit(name))
        actions.addWidget(edit_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #991b1b; color: white; padding: 4px 14px;
                border-radius: 4px; font-weight: bold;
            }
            QPushButton:hover { background-color: #dc2626; }
        """)
        delete_btn.clicked.connect(lambda checked, name=ep.name: self._on_delete(name))
        actions.addWidget(delete_btn)

        layout.addRow("", actions)

        return box

    # ── Actions ──────────────────────────────────────────────────

    def _on_add(self):
        """Open the Add Endpoint dialog with provider picker and model dropdowns."""
        from orchestrator.endpoint_registry import Endpoint, add as _add_ep

        dialog = AddEndpointDialog(self._endpoints, parent=self)
        if not dialog.exec():
            return

        data = dialog.get_endpoint_data()
        if not data["name"] or not data["base_url"]:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Incomplete", "Name and Base URL are required.")
            return

        new_ep = Endpoint(
            name=data["name"],
            base_url=data["base_url"],
            api_key=data["api_key"],
            text_model=data["text_model"],
            vision_model=data["vision_model"],
            stt_model=data["stt_model"],
            tts_model=data["tts_model"],
            fallback_model=data.get("fallback_model", ""),
            fallback_models=data.get("fallback_models", []),
        )

        _add_ep(new_ep)
        self._render_cards()

    def _on_delete(self, name: str):
        """Confirm and delete an endpoint."""
        reply = QMessageBox.question(
            self, "Delete Endpoint",
            f'Delete endpoint "{name}"?\nThis cannot be undone.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            from orchestrator.endpoint_registry import remove
            remove(name)
            self._render_cards()

    def _on_edit(self, name: str):
        """Open the Add Endpoint dialog pre-loaded with the endpoint's data for editing."""
        from orchestrator.endpoint_registry import Endpoint, add as _add_ep, remove as _remove_ep

        # Find the endpoint by name
        ep = next((e for e in self._endpoints if e.name == name), None)
        if not ep:
            return

        dialog = AddEndpointDialog(self._endpoints, endpoint=ep, parent=self)
        if not dialog.exec():
            return

        data = dialog.get_endpoint_data()
        if not data["name"] or not data["base_url"]:
            QMessageBox.warning(self, "Incomplete", "Name and Base URL are required.")
            return

        new_ep = Endpoint(
            name=data["name"],
            base_url=data["base_url"],
            api_key=data["api_key"],
            text_model=data["text_model"],
            vision_model=data["vision_model"],
            stt_model=data["stt_model"],
            tts_model=data["tts_model"],
            fallback_model=data.get("fallback_model", ""),
            fallback_models=data.get("fallback_models", []),
        )

        # If the name changed, drop the old entry first
        if name != data["name"]:
            _remove_ep(name)
        _add_ep(new_ep)
        self._render_cards()

    def _read_cards(self):
        """Read field values from the card widgets into self._endpoints."""
        for i, card in enumerate(self._card_widgets):
            if i >= len(self._endpoints):
                break
            ep = self._endpoints[i]

            name_f = card.findChild(QLineEdit, f"ep_name_{i}")
            if name_f:
                ep.name = name_f.text().strip()

            url_f = card.findChild(QLineEdit, f"ep_url_{i}")
            if url_f:
                ep.base_url = url_f.text().strip()

            key_f = card.findChild(QLineEdit, f"ep_key_{i}")
            if key_f:
                ep.api_key = key_f.text().strip()

            text_f = card.findChild(QLineEdit, f"ep_text_{i}")
            if text_f:
                ep.text_model = text_f.text().strip()

            vision_f = card.findChild(QLineEdit, f"ep_vision_{i}")
            if vision_f:
                ep.vision_model = vision_f.text().strip()

            fallback_list_f = card.findChild(QListWidget, f"ep_fallback_list_{i}")
            if fallback_list_f:
                models = []
                for idx in range(fallback_list_f.count()):
                    item = fallback_list_f.item(idx)
                    if item and item.text().strip():
                        models.append(item.text().strip())
                ep.fallback_models = models
                ep.fallback_model = models[0] if models else ""

            stt_f = card.findChild(QLineEdit, f"ep_stt_{i}")
            if stt_f:
                ep.stt_model = stt_f.text().strip()

            tts_f = card.findChild(QLineEdit, f"ep_tts_{i}")
            if tts_f:
                ep.tts_model = tts_f.text().strip()

    # ── Save ─────────────────────────────────────────────────────

    def get_endpoint_names(self) -> list[str]:
        """Get names of all currently configured endpoints in the UI."""
        self._read_cards()
        return [ep.name for ep in self._endpoints if ep.name]

    def collect(self) -> dict:
        """
        Read all card fields, persist valid endpoints to registry,
        and return a minimal dict for the broader settings save.
        """
        self._read_cards()

        from orchestrator.endpoint_registry import add, all as _all_eps

        # Separate valid endpoints from invalid ones
        valid = []
        skipped = []
        for ep in self._endpoints:
            if ep.is_valid and ep.base_url not in ("https://", "http://"):
                valid.append(ep)
            else:
                label = ep.name or "(unnamed)"
                skipped.append(label)

        # Sort valid endpoints based on priority tab's text priority list if available
        dialog = self
        while dialog and not isinstance(dialog, QDialog):
            dialog = dialog.parent()  # type: ignore[assignment]
        if dialog and hasattr(dialog, "_priority_tab"):
            text_priority_list = dialog._priority_tab.collect().get("TEXT_PRIORITY", [])
            if text_priority_list:
                def sort_key(ep):
                    try:
                        return text_priority_list.index(ep.name)
                    except ValueError:
                        return len(text_priority_list)
                valid = sorted(valid, key=sort_key)

        # Persist valid endpoints
        for ep in valid:
            add(ep)

        # Remove endpoints no longer in the list
        kept_names = {ep.name for ep in valid}
        for ep in _all_eps():
            if ep.name not in kept_names:
                from orchestrator.endpoint_registry import remove
                remove(ep.name)

        # Warn about skipped endpoints
        if skipped:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "Skipped Endpoints",
                "The following endpoints have empty names or invalid URLs "
                "and were not saved:\n\n  "
                + "\n  ".join(skipped)
            )

        return {"LLM_BACKEND": valid[0].name if valid else ""}


class VoiceTab(ScrollableTab):
    """Voice configuration — ordered TTS/STT endpoint lists, voice selection, wake words."""

    _EDGETTS_VOICES = [
        "en-US-JennyNeural", "en-US-AriaNeural", "en-US-GuyNeural",
        "en-US-ChristopherNeural", "en-US-EricNeural",
        "te-IN-ShrutiNeural", "te-IN-MohanNeural",
        "hi-IN-SwaraNeural", "hi-IN-MadhurNeural",
        "en-IN-NeerjaNeural", "en-IN-PrabhatNeural",
        "en-GB-SoniaNeural", "en-GB-RyanNeural", "en-GB-LibbyNeural",
        "en-AU-NatashaNeural", "en-AU-WilliamNeural",
        "en-CA-ClaraNeural", "en-IE-EmilyNeural", "en-SG-LunaNeural",
        "fr-FR-DeniseNeural", "fr-FR-HenriNeural",
        "de-DE-KatjaNeural", "de-DE-ConradNeural",
        "es-ES-ElviraNeural", "es-ES-AlvaroNeural",
        "ja-JP-NanamiNeural", "ja-JP-KeitaNeural",
        "ko-KR-SunHiNeural", "ko-KR-InJoonNeural",
        "zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)

        # ── TTS ──
        g1 = _make_section("Text-to-Speech (Audio Output)", self.container)
        self._tts_enabled = QCheckBox("Enable TTS playback")
        self._tts_enabled.setChecked(getattr(config, "TTS_ENABLED", True))
        g1.layout().addRow("", self._tts_enabled)  # type: ignore[union-attr]

        # TTS order list
        self._tts_list = QListWidget()
        self._tts_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self._tts_list.setMinimumHeight(120)
        self._tts_list.setMaximumHeight(180)
        _add_row(g1, "TTS Endpoint Order", self._tts_list,
                 "Priority order — first is primary, rest are fallbacks. Drag or use buttons to reorder.")

        tts_btns = QHBoxLayout()
        self._tts_up = QPushButton("▲ Move Up")
        self._tts_up.clicked.connect(lambda: self._move_list_item(self._tts_list, -1))
        tts_btns.addWidget(self._tts_up)
        self._tts_down = QPushButton("▼ Move Down")
        self._tts_down.clicked.connect(lambda: self._move_list_item(self._tts_list, 1))
        tts_btns.addWidget(self._tts_down)
        tts_btns.addStretch()
        g1.layout().addRow("", tts_btns)  # type: ignore[union-attr]

        # Edge TTS voice selection
        self._edgetts_voice = QComboBox()
        self._edgetts_voice.addItems(self._EDGETTS_VOICES)
        self._edgetts_voice.setEditable(True)
        current_voice = getattr(config, "EDGETTS_VOICE", "en-US-JennyNeural")
        idx = self._edgetts_voice.findText(current_voice)
        if idx >= 0:
            self._edgetts_voice.setCurrentIndex(idx)
        else:
            self._edgetts_voice.setCurrentText(current_voice)
        _add_row(g1, "Edge TTS Voice", self._edgetts_voice,
                 "Voice speaker for Edge TTS (e.g. en-US-AriaNeural, te-IN-ShrutiNeural, hi-IN-SwaraNeural). Scroll or type.")

        # Speech Rate (Speed)
        self._tts_rate = QComboBox()
        rate_opts = ["-50%", "-30%", "-20%", "-10%", "+0% (Normal)", "+10%", "+20%", "+30%", "+50%"]
        self._tts_rate.addItems(rate_opts)
        curr_rate = getattr(config, "TTS_RATE", "+0%")
        r_idx = self._tts_rate.findText(curr_rate)
        if r_idx >= 0:
            self._tts_rate.setCurrentIndex(r_idx)
        elif curr_rate == "+0%":
            self._tts_rate.setCurrentIndex(4)
        else:
            self._tts_rate.setCurrentText(curr_rate)
        _add_row(g1, "Voice Rate (Speed)", self._tts_rate, "Speech speed adjustment (e.g. +20% faster, -20% slower).")

        # Speech Pitch
        self._tts_pitch = QComboBox()
        pitch_opts = ["-20Hz", "-10Hz", "-5Hz", "+0Hz (Normal)", "+5Hz", "+10Hz", "+20Hz"]
        self._tts_pitch.addItems(pitch_opts)
        curr_pitch = getattr(config, "TTS_PITCH", "+0Hz")
        p_idx = self._tts_pitch.findText(curr_pitch)
        if p_idx >= 0:
            self._tts_pitch.setCurrentIndex(p_idx)
        elif curr_pitch == "+0Hz":
            self._tts_pitch.setCurrentIndex(3)
        else:
            self._tts_pitch.setCurrentText(curr_pitch)
        _add_row(g1, "Voice Pitch", self._tts_pitch, "Tonal pitch height adjustment (e.g. +5Hz higher, -5Hz lower).")

        # Speech Volume
        self._tts_volume = QComboBox()
        vol_opts = ["-50%", "-20%", "+0% (Normal)", "+20%", "+50%"]
        self._tts_volume.addItems(vol_opts)
        curr_vol = getattr(config, "TTS_VOLUME", "+0%")
        v_idx = self._tts_volume.findText(curr_vol)
        if v_idx >= 0:
            self._tts_volume.setCurrentIndex(v_idx)
        elif curr_vol == "+0%":
            self._tts_volume.setCurrentIndex(2)
        else:
            self._tts_volume.setCurrentText(curr_vol)
        _add_row(g1, "Voice Volume", self._tts_volume, "Loudness adjustment (e.g. +20% louder, -20% softer).")

        self.container_layout.addWidget(g1)

        # ── STT ──
        g2 = _make_section("Speech-to-Text (Voice Commands)", self.container)
        self._stt_enabled = QCheckBox("Enable STT microphone listener")
        self._stt_enabled.setChecked(getattr(config, "STT_ENABLED", True))
        g2.layout().addRow("", self._stt_enabled)  # type: ignore[union-attr]

        # STT order list
        self._stt_list = QListWidget()
        self._stt_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self._stt_list.setMinimumHeight(140)
        self._stt_list.setMaximumHeight(200)
        _add_row(g2, "STT Endpoint Order", self._stt_list,
                 "Priority order — first is primary, rest are fallbacks. Drag or use buttons to reorder.")

        stt_btns = QHBoxLayout()
        self._stt_up = QPushButton("▲ Move Up")
        self._stt_up.clicked.connect(lambda: self._move_list_item(self._stt_list, -1))
        stt_btns.addWidget(self._stt_up)
        self._stt_down = QPushButton("▼ Move Down")
        self._stt_down.clicked.connect(lambda: self._move_list_item(self._stt_list, 1))
        stt_btns.addWidget(self._stt_down)
        stt_btns.addStretch()
        g2.layout().addRow("", stt_btns)  # type: ignore[union-attr]

        # Whisper Local Model Size
        self._whisper_model = QComboBox()
        self._whisper_model.addItems(["base", "tiny", "small", "medium"])
        current_whisper_model = getattr(config, "STT_WHISPER_LOCAL_MODEL", "base")
        w_idx = self._whisper_model.findText(current_whisper_model)
        if w_idx >= 0:
            self._whisper_model.setCurrentIndex(w_idx)
        _add_row(g2, "Local Whisper Model", self._whisper_model,
                 "Model size for offline local Whisper STT (base, tiny, small, medium).")

        # Wake words
        self._wake_words = _make_field(
            ",".join(getattr(config, "STT_WAKE_WORDS", ["hey raphael"])),
            "comma-separated wake words",
        )
        _add_row(g2, "Wake Words", self._wake_words, "Commands that wake Raphael from standby.")

        self._wake_required = QCheckBox("Wake word required to listen")
        self._wake_required.setChecked(getattr(config, "STT_WAKE_WORD_REQUIRED", True))
        g2.layout().addRow("", self._wake_required)  # type: ignore[union-attr]
        self.container_layout.addWidget(g2)

        # ── Interrupt ──
        g3 = _make_section("Conversation Interruptions", self.container)
        self._interrupt_words = _make_field(
            ",".join(getattr(config, "INTERRUPT_WORDS", ["stop", "cancel"])),
            "comma-separated interrupt words",
        )
        _add_row(g3, "Interrupt Words", self._interrupt_words, "Verbal cues that instantly stop active spoken output.")
        self.container_layout.addWidget(g3)

        self.container_layout.addStretch()

        # Populate lists
        self._populate_tts_list()
        self._populate_stt_list()

        # Connect signals for dynamic state synchronization
        self._tts_enabled.stateChanged.connect(self._sync_tts_state)
        self._stt_enabled.stateChanged.connect(self._sync_stt_state)

        # Initial sync
        self._sync_tts_state()
        self._sync_stt_state()

    # ── Helpers ───────────────────────────────────────────────

    def _populate_tts_list(self):
        """Fill the TTS order list: TTS-capable endpoints + edge-tts."""
        self._tts_list.clear()

        # Gather available TTS providers
        available: dict[str, str] = {"edge-tts": "edge-tts (built-in)"}
        from orchestrator.endpoint_registry import all as _all_eps
        for ep in _all_eps():
            if ep.tts_model:
                available[ep.name] = f"{ep.name}  ({ep.tts_model})"

        # Read saved order or derive from legacy config
        saved_order = getattr(config, "TTS_ORDER", None)
        if not saved_order:
            saved_order = ["edge-tts"]

        # Add items in saved order, then any missing
        added: set[str] = set()
        for name in saved_order:
            if name in available:
                self._add_list_item(self._tts_list, available[name], name)
                added.add(name)
        for name, label in available.items():
            if name not in added:
                self._add_list_item(self._tts_list, label, name)

    def _populate_stt_list(self):
        """Fill the STT order list: STTRegistry backends + STT-capable endpoints."""
        self._stt_list.clear()

        available: dict[str, str] = {}

        # Add registry-based backends (winrt, groq, etc.)
        try:
            from modules.stt_backends import STTRegistry
            for name in STTRegistry.available_backends():
                available[name] = f"{name}  (built-in)"
        except Exception:
            pass

        # Add endpoint-based STT backends
        from orchestrator.endpoint_registry import all as _all_eps
        for ep in _all_eps():
            if ep.stt_model:
                available[ep.name] = f"{ep.name}  ({ep.stt_model})"

        saved_order = getattr(config, "STT_PREFERRED_BACKENDS", None)
        if not saved_order:
            saved_order = ["winrt", "groq"]

        added: set[str] = set()
        for name in saved_order:
            if name in available:
                self._add_list_item(self._stt_list, available[name], name)
                added.add(name)
        for name, label in available.items():
            if name not in added:
                self._add_list_item(self._stt_list, label, name)

    @staticmethod
    def _add_list_item(lst: QListWidget, label: str, data: str):
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, data)
        lst.addItem(item)

    @staticmethod
    def _move_list_item(lst: QListWidget, direction: int):
        """Move the currently selected list item up (-1) or down (+1)."""
        row = lst.currentRow()
        if row < 0:
            return
        new_row = row + direction
        if new_row < 0 or new_row >= lst.count():
            return
        item = lst.takeItem(row)
        lst.insertItem(new_row, item)
        lst.setCurrentRow(new_row)

    def _get_order(self, lst: QListWidget) -> list[str]:
        """Extract the ordered list of endpoint names from a QListWidget."""
        result = []
        for i in range(lst.count()):
            name = lst.item(i).data(Qt.ItemDataRole.UserRole)  # type: ignore[union-attr]
            if name:
                result.append(name)
        return result

    def _sync_tts_state(self):
        enabled = self._tts_enabled.isChecked()
        self._tts_list.setEnabled(enabled)
        self._tts_up.setEnabled(enabled)
        self._tts_down.setEnabled(enabled)
        self._edgetts_voice.setEnabled(enabled)
    def _sync_stt_state(self):
        enabled = self._stt_enabled.isChecked()
        self._stt_list.setEnabled(enabled)
        self._stt_up.setEnabled(enabled)
        self._stt_down.setEnabled(enabled)
        self._wake_words.setEnabled(enabled)
        self._wake_required.setEnabled(enabled)

    # ── Collect ───────────────────────────────────────────────

    def collect(self) -> dict:
        tts_order = self._get_order(self._tts_list)
        stt_order = self._get_order(self._stt_list)

        # Derive legacy TTS_BACKEND from the first entry
        primary_tts = tts_order[0] if tts_order else "edge-tts"

        # Edge TTS voice & audio controls
        edgetts_voice = self._edgetts_voice.currentText().strip()
        tts_rate = self._tts_rate.currentText().split()[0].strip()
        tts_pitch = self._tts_pitch.currentText().split()[0].strip()
        tts_volume = self._tts_volume.currentText().split()[0].strip()

        return {
            "TTS_ENABLED": self._tts_enabled.isChecked(),
            "TTS_ORDER": tts_order,
            "TTS_BACKEND": primary_tts,
            "EDGETTS_VOICE": edgetts_voice,
            "TTS_RATE": tts_rate,
            "TTS_PITCH": tts_pitch,
            "TTS_VOLUME": tts_volume,
            "STT_ENABLED": self._stt_enabled.isChecked(),
            "STT_PREFERRED_BACKENDS": stt_order,
            "STT_WHISPER_LOCAL_MODEL": self._whisper_model.currentText().strip(),
            "STT_BACKEND": stt_order[0] if stt_order else "",
            "STT_WAKE_WORDS": [
                w.strip() for w in self._wake_words.text().split(",") if w.strip()
            ],
            "STT_WAKE_WORD_REQUIRED": self._wake_required.isChecked(),
            "INTERRUPT_WORDS": [
                w.strip() for w in self._interrupt_words.text().split(",") if w.strip()
            ],
        }


class GeneralTab(ScrollableTab):
    def __init__(self, parent=None):
        super().__init__(parent)

        # ── Conversation ──
        g1 = _make_section("Context & History", self.container)
        self._max_history = QSpinBox()
        self._max_history.setRange(10, 500)
        self._max_history.setValue(getattr(config, "MAX_HISTORY", 50))
        _add_row(g1, "Max History (turns)", self._max_history, "Maximum conversational history size limit.")
        self.container_layout.addWidget(g1)

        # ── Proactive Engine ──
        g2 = _make_section("Proactive Recommendations", self.container)
        self._proactive_enabled = QCheckBox("Enable proactive check-ins")
        self._proactive_enabled.setChecked(getattr(config, "PROACTIVE_ENABLED", True))
        g2.layout().addRow("", self._proactive_enabled)  # type: ignore[union-attr]

        self._proactive_cooldown = QSpinBox()
        self._proactive_cooldown.setRange(10, 600)
        self._proactive_cooldown.setValue(getattr(config, "PROACTIVE_COOLDOWN", 60))
        _add_row(g2, "Cooldown (seconds)", self._proactive_cooldown, "Idle seconds required before suggestions trigger.")

        self._proactive_min_interval = QSpinBox()
        self._proactive_min_interval.setRange(30, 3600)
        self._proactive_min_interval.setValue(getattr(config, "PROACTIVE_MIN_INTERVAL", 120))
        _add_row(g2, "Min Interval (seconds)", self._proactive_min_interval, "Minimum delay between proactive prompts.")
        self.container_layout.addWidget(g2)

        # ── Performance ──
        g3 = _make_section("Inference & Performance", self.container)
        self._max_tool_chars = QSpinBox()
        self._max_tool_chars.setRange(500, 50000)
        self._max_tool_chars.setValue(getattr(config, "MAX_TOOL_RESULT_CHARS", 5000))
        _add_row(g3, "Max Tool Output Size", self._max_tool_chars, "Truncates excessive tool payload strings to save prompt tokens.")

        self._read_timeout = QSpinBox()
        self._read_timeout.setRange(30, 600)
        self._read_timeout.setSuffix(" s")
        self._read_timeout.setValue(getattr(config, "LLM_READ_TIMEOUT", 180))
        _add_row(g3, "LLM Read Timeout", self._read_timeout, "Maximum wait time for API response streaming chunks.")

        self._connect_timeout = QSpinBox()
        self._connect_timeout.setRange(5, 60)
        self._connect_timeout.setSuffix(" s")
        self._connect_timeout.setValue(getattr(config, "LLM_CONNECT_TIMEOUT", 10))
        _add_row(g3, "LLM Connect Timeout", self._connect_timeout, "Maximum wait time to establish API connection handshake.")

        self._retry_backoff = QDoubleSpinBox()
        self._retry_backoff.setRange(1.0, 10.0)
        self._retry_backoff.setSingleStep(0.5)
        self._retry_backoff.setValue(getattr(config, "LLM_RETRY_BACKOFF", 1.5))
        _add_row(g3, "Retry Backoff Factor", self._retry_backoff, "Exponent multiplier applied to rate-limit recovery intervals.")

        self._bg_workers = QSpinBox()
        self._bg_workers.setRange(1, 16)
        self._bg_workers.setValue(getattr(config, "BACKGROUND_MAX_WORKERS", 4))
        _add_row(g3, "BG Worker Threads", self._bg_workers, "Number of concurrent threads allocated to background jobs.")
        self.container_layout.addWidget(g3)

        # ── Editor ──
        g4 = _make_section("External Applications", self.container)
        self._editor_path = _make_field(
            getattr(config, "EDITOR_PATH", ""),
            "e.g. code, notepad.exe, or absolute path",
        )
        _add_row(g4, "Default Text Editor", self._editor_path, "Command or executable used to modify file systems.")

        self._chrome_path = _make_field(
            getattr(config, "CHROME_PATH", ""),
            "Path to Chrome executable",
        )
        _add_row(g4, "Google Chrome Executable", self._chrome_path, "Custom installation path to chromium binary (optional).")
        self.container_layout.addWidget(g4)

        # ── Background ──
        g5 = _make_section("Background Notifications", self.container)
        self._bg_tts = QCheckBox("Notify via speech")
        self._bg_tts.setChecked(getattr(config, "BACKGROUND_NOTIFY_TTS", True))
        g5.layout().addRow("", self._bg_tts)  # type: ignore[union-attr]

        self._bg_log = QCheckBox("Notify via log feed")
        self._bg_log.setChecked(getattr(config, "BACKGROUND_NOTIFY_LOG", True))
        g5.layout().addRow("", self._bg_log)  # type: ignore[union-attr]

        self._bg_preview = QSpinBox()
        self._bg_preview.setRange(50, 2000)
        self._bg_preview.setValue(getattr(config, "BACKGROUND_RESULT_PREVIEW_CHARS", 300))
        _add_row(g5, "Log Preview Character Limit", self._bg_preview, "Preview character length limit inside background task feeds.")
        self.container_layout.addWidget(g5)

        self.container_layout.addStretch()

    def collect(self) -> dict:
        return {
            "MAX_HISTORY": self._max_history.value(),
            "PROACTIVE_ENABLED": self._proactive_enabled.isChecked(),
            "PROACTIVE_COOLDOWN": self._proactive_cooldown.value(),
            "PROACTIVE_MIN_INTERVAL": self._proactive_min_interval.value(),
            "MAX_TOOL_RESULT_CHARS": self._max_tool_chars.value(),
            "LLM_READ_TIMEOUT": self._read_timeout.value(),
            "LLM_CONNECT_TIMEOUT": self._connect_timeout.value(),
            "LLM_RETRY_BACKOFF": self._retry_backoff.value(),
            "BACKGROUND_MAX_WORKERS": self._bg_workers.value(),
            "EDITOR_PATH": self._editor_path.text().strip(),
            "CHROME_PATH": self._chrome_path.text().strip(),
            "BACKGROUND_NOTIFY_TTS": self._bg_tts.isChecked(),
            "BACKGROUND_NOTIFY_LOG": self._bg_log.isChecked(),
            "BACKGROUND_RESULT_PREVIEW_CHARS": self._bg_preview.value(),
        }


class FetchIPThread(QThread):
    """Background thread to fetch the public IP address without blocking the UI."""
    done = pyqtSignal(str)

    def run(self):
        import urllib.request
        urls = [
            "https://api.ipify.org",
            "https://icanhazip.com",
            "https://ifconfig.me/ip",
            "https://ident.me"
        ]
        ip = "Unknown (Check network connection)"
        for url in urls:
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    ip_str = response.read().decode("utf-8").strip()
                    if ip_str and (len(ip_str.split('.')) == 4 or ":" in ip_str):
                        ip = ip_str
                        break
            except Exception:
                continue
        self.done.emit(ip)


class ToolsTab(ScrollableTab):
    """Tab for managing tools settings (Email, Upstox, and IP info)."""
    def __init__(self, parent=None):
        super().__init__(parent)

        # ── Email Integration ──
        g1 = _make_section("Email Integration", self.container)
        self._email_user = _make_field(
            getattr(config, "EMAIL_USER", ""),
            "e.g. user@gmail.com",
        )
        _add_row(g1, "Email Address", self._email_user, "The sender email address (e.g. Gmail).")

        self._email_password = _make_field(
            getattr(config, "EMAIL_PASSWORD", ""),
            "e.g. abcd efgh ijkl mnop",
            password=True
        )

        pass_container = QWidget()
        pass_layout = QHBoxLayout(pass_container)
        pass_layout.setContentsMargins(0, 0, 0, 0)
        pass_layout.setSpacing(6)
        pass_layout.addWidget(self._email_password, 1)

        self._eye_btn = QPushButton("👁")
        self._eye_btn.setFixedSize(30, 28)
        self._eye_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._eye_btn.setToolTip("Show/Hide Password")
        self._eye_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #cbd5e1;
                border: 1px solid #334155;
                border-radius: 6px;
                font-size: 14px;
                padding: 0;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #14b8a6;
                border-color: #14b8a6;
            }
        """)
        self._eye_btn.clicked.connect(self._toggle_password_visibility)
        pass_layout.addWidget(self._eye_btn)

        _add_row(g1, "App Password", pass_container, "The App Password generated from your email account settings.")
        self.container_layout.addWidget(g1)

        # ── Upstox Analytics ──
        g2 = _make_section("Upstox Analytics", self.container)
        self._upstox_api_key = _make_field(
            getattr(config, "UPSTOX_ANALYTICS_API", ""),
            "JWT token for Upstox API authentication",
        )
        _add_row(g2, "Upstox JWT Key", self._upstox_api_key, "Your Upstox Analytics JWT access token.")

        self._ip_label = QLabel("Fetching public IP address...")
        self._ip_label.setStyleSheet("color: #14b8a6; font-weight: bold; font-family: Consolas; font-size: 12px;")
        _add_row(g2, "Your Public IP", self._ip_label, "Whitelist this IP address in your Upstox API settings to fetch profile details.")
        self.container_layout.addWidget(g2)

        self.container_layout.addStretch()

        self._fetch_ip()

    def _fetch_ip(self):
        self._ip_thread = FetchIPThread()
        self._ip_thread.done.connect(self._on_ip_fetched)
        self._ip_thread.start()

    def _on_ip_fetched(self, ip: str):
        self._ip_label.setText(ip)

    def _toggle_password_visibility(self):
        if self._email_password.echoMode() == QLineEdit.EchoMode.Password:
            self._email_password.setEchoMode(QLineEdit.EchoMode.Normal)
            self._eye_btn.setText("🙈")
        else:
            self._email_password.setEchoMode(QLineEdit.EchoMode.Password)
            self._eye_btn.setText("👁")

    def collect(self) -> dict:
        return {
            "EMAIL_USER": self._email_user.text().strip(),
            "EMAIL_PASSWORD": self._email_password.text().strip(),
            "UPSTOX_ANALYTICS_API": self._upstox_api_key.text().strip(),
        }


class PriorityTab(ScrollableTab):
    """Tab for managing LLM model capability priorities (Text and Vision)."""
    def __init__(self, parent=None):
        super().__init__(parent)

        # ── Text Priority ──
        g1 = _make_section("Text / Chat Capability Priority", self.container)
        self._text_list = QListWidget()
        self._text_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self._text_list.setMinimumHeight(140)
        self._text_list.setMaximumHeight(200)
        _add_row(g1, "Text Endpoints Priority", self._text_list,
                 "Order of endpoints for text/chat. First is primary, others are fallback order. Drag to reorder.")

        text_btns = QHBoxLayout()
        self._text_up = QPushButton("▲ Move Up")
        self._text_up.clicked.connect(lambda: self._move_list_item(self._text_list, -1))
        text_btns.addWidget(self._text_up)

        self._text_down = QPushButton("▼ Move Down")
        self._text_down.clicked.connect(lambda: self._move_list_item(self._text_list, 1))
        text_btns.addWidget(self._text_down)
        text_btns.addStretch()
        g1.layout().addRow("", text_btns)  # type: ignore[union-attr]
        self.container_layout.addWidget(g1)

        # ── Vision Priority ──
        g2 = _make_section("Vision / Multimodal Capability Priority", self.container)
        self._vision_list = QListWidget()
        self._vision_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self._vision_list.setMinimumHeight(140)
        self._vision_list.setMaximumHeight(200)
        _add_row(g2, "Vision Endpoints Priority", self._vision_list,
                 "Order of endpoints for vision/image queries. First is primary, others are fallback order. Drag to reorder.")

        vision_btns = QHBoxLayout()
        self._vision_up = QPushButton("▲ Move Up")
        self._vision_up.clicked.connect(lambda: self._move_list_item(self._vision_list, -1))
        vision_btns.addWidget(self._vision_up)

        self._vision_down = QPushButton("▼ Move Down")
        self._vision_down.clicked.connect(lambda: self._move_list_item(self._vision_list, 1))
        vision_btns.addWidget(self._vision_down)
        vision_btns.addStretch()
        g2.layout().addRow("", vision_btns)  # type: ignore[union-attr]
        self.container_layout.addWidget(g2)

        self.container_layout.addStretch()

    def _move_list_item(self, list_widget: QListWidget, direction: int):
        row = list_widget.currentRow()
        if row < 0:
            return
        target = row + direction
        if 0 <= target < list_widget.count():
            item = list_widget.takeItem(row)
            list_widget.insertItem(target, item)
            list_widget.setCurrentRow(target)

    def refresh(self, endpoint_names: list[str]):
        """Populate priority lists from the current endpoint names, preserving existing order."""
        # Get existing order from UI first
        existing_text_order = []
        for i in range(self._text_list.count()):
            item = self._text_list.item(i)
            if item is not None:
                existing_text_order.append(item.text())
        existing_vision_order = []
        for i in range(self._vision_list.count()):
            item = self._vision_list.item(i)
            if item is not None:
                existing_vision_order.append(item.text())

        # If UI lists are empty, load from config/saved settings
        if not existing_text_order:
            existing_text_order = getattr(config, "TEXT_PRIORITY", [])
        if not existing_vision_order:
            existing_vision_order = getattr(config, "VISION_PRIORITY", [])

        # Re-sort endpoint names preserving the stored/current order
        def sort_key_text(name):
            try:
                return existing_text_order.index(name)
            except ValueError:
                return 9999

        def sort_key_vision(name):
            try:
                return existing_vision_order.index(name)
            except ValueError:
                return 9999

        sorted_text_names = sorted(endpoint_names, key=sort_key_text)
        sorted_vision_names = sorted(endpoint_names, key=sort_key_vision)

        # Clear and repopulate lists
        self._text_list.clear()
        self._text_list.addItems(sorted_text_names)

        self._vision_list.clear()
        self._vision_list.addItems(sorted_vision_names)

    def collect(self) -> dict:
        text_priority = []
        for i in range(self._text_list.count()):
            item = self._text_list.item(i)
            if item is not None:
                text_priority.append(item.text())
        vision_priority = []
        for i in range(self._vision_list.count()):
            item = self._vision_list.item(i)
            if item is not None:
                vision_priority.append(item.text())
        return {
            "TEXT_PRIORITY": text_priority,
            "VISION_PRIORITY": vision_priority,
        }


# ── Dialog ─────────────────────────────────────────────────────

class SettingsDialog(QDialog):
    """Main settings dialog with tabbed interface."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Raphael Settings")

        # Calculate dynamic size based on primary screen height (75vh height, 80vh width)
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().size()  # type: ignore[union-attr]
        sh = screen.height()
        dialog_height = int(sh * 0.75)
        dialog_width = int(sh * 0.80)

        # Safe bounds fallback
        if dialog_height < 560:
            dialog_height = 560
        if dialog_width < 720:
            dialog_width = 720

        self.resize(dialog_width, dialog_height)
        self.setMinimumSize(720, 560)
        self.setStyleSheet(_DARK_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # Tabs
        self._tabs = QTabWidget()
        self._endpoints_tab = EndpointsConfigTab()
        self._priority_tab = PriorityTab()
        self._voice_tab = VoiceTab()
        self._general_tab = GeneralTab()
        self._tools_tab = ToolsTab()

        self._tabs.addTab(self._endpoints_tab, "Endpoints")
        self._tabs.addTab(self._priority_tab, "Priority")
        self._tabs.addTab(self._voice_tab, "Voice")
        self._tabs.addTab(self._general_tab, "General")
        self._tabs.addTab(self._tools_tab, "Tools")

        # Wire up tab changed signal to sync endpoints with Priority tab
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # Populate Priority tab initially
        self._priority_tab.refresh(self._endpoints_tab.get_endpoint_names())

        layout.addWidget(self._tabs, 1)

        # Buttons
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._on_save)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _on_tab_changed(self, index: int):
        if self._tabs.tabText(index) == "Priority":
            self._priority_tab.refresh(self._endpoints_tab.get_endpoint_names())

    def _on_save(self):
        """Collect all tab settings and persist to settings.toml."""
        settings = {}
        for tab in [self._endpoints_tab, self._priority_tab, self._voice_tab, self._general_tab, self._tools_tab]:
            settings.update(tab.collect())

        try:
            save(settings)
            # save() only writes sections from _SECTION_MAP — it does NOT
            # write [[endpoints]]. Re-save them so they survive in the file.
            from orchestrator.endpoint_registry import _save_to_settings, all as _all_eps
            _save_to_settings(_all_eps())

            QMessageBox.information(
                self, "Settings Saved",
                "Settings saved to settings.toml.\n\n"
                "Some changes (API keys, backends) will take effect "
                "after restarting or clicking the Reload (⟳) button in the controls panel.",
            )
            self.accept()
        except Exception as e:
            QMessageBox.warning(
                self, "Save Failed",
                f"Could not save settings:\n{e}",
            )
