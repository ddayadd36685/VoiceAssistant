import sys
import json
import math
import re
from pathlib import Path
import threading
import websocket
import yaml
from voice_assistant.mcp_client import ensure_mcp_config_files
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QMenu, QSystemTrayIcon,
    QGraphicsOpacityEffect, QDialog, QTabWidget, QFormLayout, QHBoxLayout,
    QPushButton, QDoubleSpinBox, QSpinBox, QLineEdit, QTableWidget,
    QTableWidgetItem, QFileDialog, QMessageBox, QHeaderView, QAbstractItemView,
    QComboBox
)
from PyQt6.QtCore import (
    Qt, QPoint, QPointF, pyqtSignal, QObject, QTimer, QPropertyAnimation,
    QEasingCurve, QRect, QRectF
)
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QAction, QIcon, QCursor, QFont, QFontMetrics,
    QRadialGradient, QPen, QConicalGradient, QPainterPath, QLinearGradient
)

RESTART_EXIT_CODE = 190

class BackendWorker(QObject):
    state_changed = pyqtSignal(str) # new_state
    text_received = pyqtSignal(str) # asr/intent/action text
    
    def __init__(self, ws_url="ws://127.0.0.1:8000/v1/events"):
        super().__init__()
        self.ws_url = ws_url
        self.ws = None
        self.running = True

    def run(self):
        while self.running:
            try:
                self.ws = websocket.WebSocketApp(
                    self.ws_url,
                    on_open=self.on_open,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close
                )
                self.ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                print(f"WS connection failed: {e}")
                import time
                time.sleep(3) # Reconnect delay

    def on_open(self, ws):
        print("Connected to backend")

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            evt_type = data.get("type")
            payload = data.get("data", {})
            
            if evt_type == "initial_state":
                self.state_changed.emit(payload.get("state", "IDLE"))
                
            elif evt_type == "state_changed":
                self.state_changed.emit(payload.get("to", "IDLE"))
                
            elif evt_type == "wakeword_detected":
                self.text_received.emit(f"Wake: {payload.get('keyword')}")
                
            elif evt_type == "asr_result":
                self.text_received.emit(f"Heard: {payload.get('text')}")
                
            elif evt_type == "action_finished":
                ok = payload.get("success")
                msg = payload.get("message", "")
                if ok is True:
                    self.text_received.emit(f"ResultOK: {msg}")
                elif ok is False:
                    self.text_received.emit(f"ResultFAIL: {msg}")
                else:
                    self.text_received.emit(f"Result: {msg}")
                
        except Exception as e:
            print(f"Msg parse error: {e}")

    def on_error(self, ws, error):
        print(f"WS Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print("WS Closed")

    def stop(self):
        self.running = False
        ws = self.ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

class BubbleLabel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._kind = "info"
        self._title = ""
        self._subtitle = ""
        self._title_font = QFont("Segoe UI", 12, QFont.Weight.DemiBold)
        self._subtitle_font = QFont("Segoe UI", 10, QFont.Weight.Medium)
        self._max_text_width = 360
        self._pad_x = 16
        self._pad_y = 12
        self._radius = 14
        self._glow = 16
        self._icon_size = 20
        self._gap = 10

        self._bg = QColor(18, 18, 22, 230)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)
        
        self.hide_timer = QTimer(self)
        self.hide_timer.timeout.connect(self.fade_out)
        self.hide_timer.setSingleShot(True)
        
        self.opacity_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self.opacity_anim.setDuration(300)
        self.opacity_anim.finished.connect(self._on_anim_finished)

        self._on_closed = None

    def _on_anim_finished(self):
        if self._opacity_effect.opacity() <= 0.001:
            self.hide()
            cb = self._on_closed
            self._on_closed = None
            if cb is not None:
                try:
                    cb()
                except Exception:
                    pass

    def _recalc_size(self):
        title_fm = QFontMetrics(self._title_font)
        subtitle_fm = QFontMetrics(self._subtitle_font)
        flags = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap)

        title_rect = title_fm.boundingRect(QRect(0, 0, self._max_text_width, 2000), flags, self._title)
        subtitle_rect = subtitle_fm.boundingRect(QRect(0, 0, self._max_text_width, 2000), flags, self._subtitle)

        text_w = max(title_rect.width(), subtitle_rect.width())
        text_h = title_rect.height() + (6 if self._subtitle else 0) + subtitle_rect.height()

        content_w = self._pad_x * 2 + self._icon_size + self._gap + text_w
        content_h = self._pad_y * 2 + max(self._icon_size, text_h)
        self.setFixedSize(int(content_w + self._glow * 2), int(content_h + self._glow * 2))

    def show_message(self, kind, title, subtitle="", duration=3200, on_closed=None):
        self._kind = kind
        self._title = title
        self._subtitle = subtitle
        self._on_closed = on_closed
        self._recalc_size()
        self._opacity_effect.setOpacity(0.0)
        self.show()
        
        self.opacity_anim.stop()
        self.opacity_anim.setStartValue(0.0)
        self.opacity_anim.setEndValue(1.0)
        self.opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.opacity_anim.start()
        
        self.hide_timer.start(duration)

    def fade_out(self):
        self.opacity_anim.stop()
        self.opacity_anim.setStartValue(self._opacity_effect.opacity())
        self.opacity_anim.setEndValue(0.0)
        self.opacity_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self.opacity_anim.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._kind == "success":
            accent = QColor(0, 255, 204, 200)
        elif self._kind == "error":
            accent = QColor(255, 70, 110, 220)
        elif self._kind == "listening":
            accent = QColor(255, 70, 110, 200)
        elif self._kind == "thinking":
            accent = QColor(180, 80, 255, 210)
        else:
            accent = QColor(0, 255, 204, 170)

        border = QColor(accent.red(), accent.green(), accent.blue(), 90)

        glow_rect = QRectF(self._glow / 2, self._glow / 2, self.width() - self._glow, self.height() - self._glow)
        body_rect = glow_rect.adjusted(self._glow / 2, self._glow / 2, -self._glow / 2, -self._glow / 2)

        center = body_rect.center()
        max_r = max(body_rect.width(), body_rect.height()) * 0.75
        glow = QRadialGradient(center, max_r + self._glow)
        glow.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 70))
        glow.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawRoundedRect(glow_rect, self._radius + self._glow * 0.5, self._radius + self._glow * 0.5)

        bg_grad = QLinearGradient(body_rect.topLeft(), body_rect.bottomRight())
        bg_grad.setColorAt(0.0, QColor(self._bg.red(), self._bg.green(), self._bg.blue(), self._bg.alpha()))
        bg_grad.setColorAt(1.0, QColor(10, 10, 14, self._bg.alpha()))
        painter.setBrush(QBrush(bg_grad))
        painter.setPen(QPen(border, 1.0))
        painter.drawRoundedRect(body_rect, self._radius, self._radius)

        content = body_rect.adjusted(self._pad_x, self._pad_y, -self._pad_x, -self._pad_y)
        icon_rect = QRectF(content.left(), content.center().y() - self._icon_size / 2, self._icon_size, self._icon_size)

        painter.setBrush(QBrush(QColor(accent.red(), accent.green(), accent.blue(), 60)))
        painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 140), 1.0))
        painter.drawEllipse(icon_rect)

        painter.setPen(QPen(QColor(255, 255, 255, 230), 1.7))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        if self._kind == "success":
            p1 = QPointF(icon_rect.left() + self._icon_size * 0.28, icon_rect.top() + self._icon_size * 0.55)
            p2 = QPointF(icon_rect.left() + self._icon_size * 0.45, icon_rect.top() + self._icon_size * 0.72)
            p3 = QPointF(icon_rect.left() + self._icon_size * 0.75, icon_rect.top() + self._icon_size * 0.32)
            path.moveTo(p1)
            path.lineTo(p2)
            path.lineTo(p3)
            painter.drawPath(path)
        elif self._kind == "error":
            p1 = QPointF(icon_rect.left() + self._icon_size * 0.32, icon_rect.top() + self._icon_size * 0.32)
            p2 = QPointF(icon_rect.left() + self._icon_size * 0.68, icon_rect.top() + self._icon_size * 0.68)
            p3 = QPointF(icon_rect.left() + self._icon_size * 0.68, icon_rect.top() + self._icon_size * 0.32)
            p4 = QPointF(icon_rect.left() + self._icon_size * 0.32, icon_rect.top() + self._icon_size * 0.68)
            path.moveTo(p1)
            path.lineTo(p2)
            path.moveTo(p3)
            path.lineTo(p4)
            painter.drawPath(path)
        else:
            dot = QRectF(
                icon_rect.center().x() - self._icon_size * 0.07,
                icon_rect.center().y() - self._icon_size * 0.07,
                self._icon_size * 0.14,
                self._icon_size * 0.14,
            )
            painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(dot)

        text_left = icon_rect.right() + self._gap
        text_rect = QRectF(text_left, content.top(), content.right() - text_left, content.height())

        painter.setPen(QColor(245, 247, 255, 235))
        painter.setFont(self._title_font)
        title_fm = QFontMetrics(self._title_font)
        title_height = title_fm.boundingRect(QRect(0, 0, int(text_rect.width()), 2000), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap), self._title).height()
        painter.drawText(QRectF(text_rect.left(), text_rect.top(), text_rect.width(), title_height + 2), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap), self._title)

        if self._subtitle:
            painter.setPen(QColor(accent.red(), accent.green(), accent.blue(), 220))
            painter.setFont(self._subtitle_font)
            painter.drawText(QRectF(text_rect.left(), text_rect.top() + title_height + 6, text_rect.width(), text_rect.height() - title_height - 6), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap), self._subtitle)


class ToastManager(QObject):
    def __init__(self):
        super().__init__()
        self._toasts = []

    def _cleanup(self):
        self._toasts = [t for t in self._toasts if t.isVisible()]

    def _layout(self, anchor_rect: QRect, screen_geo: QRect, prefer_left: bool):
        self._cleanup()
        if not self._toasts:
            return

        margin = 10
        gap = 10
        x = anchor_rect.left() - margin if prefer_left else anchor_rect.right() + margin
        y = anchor_rect.top() + 14

        for toast in self._toasts:
            tw = toast.width()
            th = toast.height()

            tx = x - tw if prefer_left else x
            ty = y

            if tx < screen_geo.left() + margin:
                tx = screen_geo.left() + margin
            if tx + tw > screen_geo.right() - margin:
                tx = screen_geo.right() - margin - tw

            if ty + th > screen_geo.bottom() - margin:
                ty = screen_geo.bottom() - margin - th
            if ty < screen_geo.top() + margin:
                ty = screen_geo.top() + margin

            toast.move(int(tx), int(ty))
            y = ty + th + gap

    def show_toast(self, kind: str, title: str, subtitle: str, anchor_rect: QRect, screen_geo: QRect, prefer_left: bool):
        toast = BubbleLabel(None)
        self._toasts.insert(0, toast)

        def _closed():
            self._cleanup()
            self._layout(anchor_rect, screen_geo, prefer_left)

        toast.show_message(kind, title, subtitle, on_closed=_closed)
        self._layout(anchor_rect, screen_geo, prefer_left)
        return toast


class SettingsDialog(QDialog):
    def __init__(self, project_root: Path, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self.config_path = self.project_root / "config.yaml"
        self.file_config_path = self.project_root / "mcp_config" / "file_config.yaml"
        self.web_config_path = self.project_root / "mcp_config" / "web_config.yaml"
        ensure_mcp_config_files(self.project_root)

        self.setWindowTitle("设置")
        self.setMinimumWidth(760)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.restart_required = False
        self._initial_asr_provider = None

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs)

        self._init_main_config_tab()
        self._init_file_config_tab()
        self._init_web_config_tab()

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.save_btn = QPushButton("保存")
        self.cancel_btn = QPushButton("取消")
        self.save_btn.clicked.connect(self._on_save)
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.save_btn)
        layout.addLayout(btn_row)

        self.setStyleSheet("""
            QDialog {
                background-color: #0f0f14;
                color: #f2f5ff;
            }
            QTabWidget::pane {
                border: 1px solid rgba(255, 255, 255, 40);
                border-radius: 10px;
                top: -1px;
                background: rgba(20, 20, 28, 220);
            }
            QTabBar::tab {
                background: rgba(255, 255, 255, 18);
                padding: 10px 14px;
                margin-right: 6px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
            QTabBar::tab:selected {
                background: rgba(0, 255, 204, 28);
                border: 1px solid rgba(0, 255, 204, 70);
                border-bottom: none;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox {
                background: rgba(255, 255, 255, 10);
                border: 1px solid rgba(255, 255, 255, 35);
                border-radius: 8px;
                padding: 6px 10px;
                selection-background-color: rgba(0, 255, 204, 70);
            }
            QPushButton {
                background: rgba(255, 255, 255, 14);
                border: 1px solid rgba(255, 255, 255, 35);
                border-radius: 10px;
                padding: 8px 14px;
            }
            QPushButton:hover {
                border: 1px solid rgba(0, 255, 204, 90);
                background: rgba(0, 255, 204, 18);
            }
            QPushButton:pressed {
                background: rgba(0, 255, 204, 26);
            }
            QTableWidget {
                background: rgba(255, 255, 255, 6);
                border: 1px solid rgba(255, 255, 255, 35);
                border-radius: 10px;
                gridline-color: rgba(255, 255, 255, 18);
            }
            QTableWidget::item {
                padding: 6px 10px;
            }
            QTableWidget::item:selected {
                background: rgba(0, 255, 204, 22);
            }
            QTableWidget QLineEdit {
                background: rgba(15, 15, 20, 245);
                border: 1px solid rgba(0, 255, 204, 110);
                border-radius: 8px;
                padding: 6px 10px;
            }
            QHeaderView::section {
                background: rgba(255, 255, 255, 12);
                border: none;
                padding: 8px 10px;
            }
        """)

        self._load_all()

    def _read_yaml(self, path: Path):
        if not path.exists():
            return None
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _write_yaml(self, path: Path, data):
        text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
        path.write_text(text, encoding="utf-8")

    def _parse_keywords(self, s: str):
        raw = (s or "").strip()
        if not raw:
            return []
        parts = re.split(r"[,\，;\；\n]+", raw)
        out = []
        for p in parts:
            k = p.strip()
            if k:
                out.append(k)
        seen = set()
        uniq = []
        for k in out:
            if k in seen:
                continue
            uniq.append(k)
            seen.add(k)
        return uniq

    def _init_main_config_tab(self):
        tab = QWidget(self)
        v = QVBoxLayout(tab)
        form = QFormLayout()
        v.addLayout(form)

        self.audio_pre_roll = QDoubleSpinBox()
        self.audio_pre_roll.setDecimals(2)
        self.audio_pre_roll.setRange(0.0, 20.0)
        self.audio_pre_roll.setSingleStep(0.1)

        self.vad_silence_threshold = QSpinBox()
        self.vad_silence_threshold.setRange(0, 20000)
        self.vad_silence_threshold.setSingleStep(50)

        self.vad_max_recording = QDoubleSpinBox()
        self.vad_max_recording.setDecimals(1)
        self.vad_max_recording.setRange(0.5, 300.0)
        self.vad_max_recording.setSingleStep(0.5)

        self.vad_wakeup_silence_limit = QDoubleSpinBox()
        self.vad_wakeup_silence_limit.setDecimals(2)
        self.vad_wakeup_silence_limit.setRange(0.0, 20.0)
        self.vad_wakeup_silence_limit.setSingleStep(0.1)

        self.vad_wakeup_silence_ramp = QDoubleSpinBox()
        self.vad_wakeup_silence_ramp.setDecimals(2)
        self.vad_wakeup_silence_ramp.setRange(0.0, 20.0)
        self.vad_wakeup_silence_ramp.setSingleStep(0.1)

        self.kws_keywords_score = QDoubleSpinBox()
        self.kws_keywords_score.setDecimals(2)
        self.kws_keywords_score.setRange(0.0, 5.0)
        self.kws_keywords_score.setSingleStep(0.05)

        self.kws_keywords_threshold = QDoubleSpinBox()
        self.kws_keywords_threshold.setDecimals(3)
        self.kws_keywords_threshold.setRange(0.0, 1.0)
        self.kws_keywords_threshold.setSingleStep(0.01)

        self.kws_cooldown = QDoubleSpinBox()
        self.kws_cooldown.setDecimals(2)
        self.kws_cooldown.setRange(0.0, 60.0)
        self.kws_cooldown.setSingleStep(0.1)

        self.kws_wake_words = QLineEdit()
        self.kws_wake_words.setPlaceholderText("例如: 你好小梦, 小梦同学 (英文逗号分隔)")

        self.asr_provider = QComboBox()
        self.asr_provider.addItems(["sherpa", "funasr"])

        form.addRow("ASR 引擎 (需重启)", self.asr_provider)
        form.addRow("唤醒词 (需重启)", self.kws_wake_words)
        form.addRow("预录音时长（秒）", self.audio_pre_roll)
        form.addRow("静音阈值（RMS）", self.vad_silence_threshold)
        form.addRow("最大录音时长（秒）", self.vad_max_recording)
        form.addRow("唤醒后初始静音秒数", self.vad_wakeup_silence_limit)
        form.addRow("静音秒数递减时长（秒）", self.vad_wakeup_silence_ramp)
        form.addRow("唤醒词得分", self.kws_keywords_score)
        form.addRow("唤醒词阈值", self.kws_keywords_threshold)
        form.addRow("唤醒冷却（秒）", self.kws_cooldown)

        v.addStretch(1)
        self.tabs.addTab(tab, "主配置")

    def _create_table_tab(self, title: str, headers):
        tab = QWidget(self)
        v = QVBoxLayout(tab)

        table = QTableWidget(0, len(headers), tab)
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        if len(headers) > 1:
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(38)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed | QAbstractItemView.EditTrigger.AnyKeyPressed)
        table.setWordWrap(False)
        table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        v.addWidget(table)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("新增")
        del_btn = QPushButton("删除")
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch(1)
        v.addLayout(btn_row)

        self.tabs.addTab(tab, title)
        return tab, table, add_btn, del_btn

    def _init_file_config_tab(self):
        tab, table, add_btn, del_btn = self._create_table_tab("文件/应用", ["关键词（逗号分隔）", "路径"])
        self.file_table = table
        self.file_add_btn = add_btn
        self.file_del_btn = del_btn

        browse_btn = QPushButton("选择文件")
        row = tab.layout().itemAt(tab.layout().count() - 1).layout()
        row.insertWidget(2, browse_btn)
        self.file_browse_btn = browse_btn

        self.file_add_btn.clicked.connect(self._add_file_row)
        self.file_del_btn.clicked.connect(self._del_selected_file_row)
        self.file_browse_btn.clicked.connect(self._browse_file_path)

    def _init_web_config_tab(self):
        tab, table, add_btn, del_btn = self._create_table_tab("网站", ["关键词（逗号分隔）", "URL"])
        self.web_table = table
        self.web_add_btn = add_btn
        self.web_del_btn = del_btn

        self.web_add_btn.clicked.connect(self._add_web_row)
        self.web_del_btn.clicked.connect(self._del_selected_web_row)

    def _add_file_row(self):
        r = self.file_table.rowCount()
        self.file_table.insertRow(r)
        self.file_table.setItem(r, 0, QTableWidgetItem(""))
        self.file_table.setItem(r, 1, QTableWidgetItem(""))
        self.file_table.setCurrentCell(r, 0)

    def _del_selected_file_row(self):
        r = self.file_table.currentRow()
        if r >= 0:
            self.file_table.removeRow(r)

    def _browse_file_path(self):
        r = self.file_table.currentRow()
        if r < 0:
            return
        path, _ = QFileDialog.getOpenFileName(self, "选择文件", str(Path.home()))
        if path:
            self.file_table.setItem(r, 1, QTableWidgetItem(path))

    def _add_web_row(self):
        r = self.web_table.rowCount()
        self.web_table.insertRow(r)
        self.web_table.setItem(r, 0, QTableWidgetItem(""))
        self.web_table.setItem(r, 1, QTableWidgetItem(""))
        self.web_table.setCurrentCell(r, 0)

    def _del_selected_web_row(self):
        r = self.web_table.currentRow()
        if r >= 0:
            self.web_table.removeRow(r)

    def _load_all(self):
        data = self._read_yaml(self.config_path) or {}
        if not isinstance(data, dict):
            data = {}

        audio = data.get("audio", {})
        vad = data.get("vad", {})
        kws = data.get("kws", {})
        asr = data.get("asr", {})
        if not isinstance(audio, dict):
            audio = {}
        if not isinstance(vad, dict):
            vad = {}
        if not isinstance(kws, dict):
            kws = {}
        if not isinstance(asr, dict):
            asr = {}

        self.asr_provider.setCurrentText(str(asr.get("provider", "sherpa")))
        if self._initial_asr_provider is None:
            self._initial_asr_provider = self.asr_provider.currentText()
        self.audio_pre_roll.setValue(float(audio.get("pre_roll_sec", 2.0)))
        self.vad_silence_threshold.setValue(int(vad.get("silence_threshold", 500)))
        self.vad_max_recording.setValue(float(vad.get("max_recording_sec", 10.0)))
        self.vad_wakeup_silence_limit.setValue(float(vad.get("wakeup_silence_limit_sec", 2.5)))
        self.vad_wakeup_silence_ramp.setValue(float(vad.get("wakeup_silence_ramp_sec", 1.0)))
        self.kws_keywords_score.setValue(float(kws.get("keywords_score", 1.0)))
        self.kws_keywords_threshold.setValue(float(kws.get("keywords_threshold", 0.25)))
        self.kws_cooldown.setValue(float(kws.get("cooldown_sec", 2.0)))
        
        wake_words = kws.get("keywords", [])
        if isinstance(wake_words, list):
            self.kws_wake_words.setText(", ".join(str(w) for w in wake_words))
        else:
            self.kws_wake_words.setText(str(wake_words))

        file_data = self._read_yaml(self.file_config_path) or {}
        files = file_data.get("files", []) if isinstance(file_data, dict) else []
        self.file_table.setRowCount(0)
        if isinstance(files, list):
            for item in files:
                if not isinstance(item, dict):
                    continue
                keywords = item.get("keywords", [])
                path = item.get("path", "")
                if isinstance(keywords, list):
                    kw_str = "，".join(str(k) for k in keywords if str(k).strip())
                else:
                    kw_str = str(keywords or "")
                r = self.file_table.rowCount()
                self.file_table.insertRow(r)
                self.file_table.setItem(r, 0, QTableWidgetItem(kw_str))
                self.file_table.setItem(r, 1, QTableWidgetItem(str(path or "")))

        web_data = self._read_yaml(self.web_config_path) or {}
        websites = web_data.get("websites", []) if isinstance(web_data, dict) else []
        self.web_table.setRowCount(0)
        if isinstance(websites, list):
            for item in websites:
                if not isinstance(item, dict):
                    continue
                keywords = item.get("keywords", [])
                url = item.get("url", "")
                if isinstance(keywords, list):
                    kw_str = "，".join(str(k) for k in keywords if str(k).strip())
                else:
                    kw_str = str(keywords or "")
                r = self.web_table.rowCount()
                self.web_table.insertRow(r)
                self.web_table.setItem(r, 0, QTableWidgetItem(kw_str))
                self.web_table.setItem(r, 1, QTableWidgetItem(str(url or "")))

    def _collect_main_config(self):
        data = self._read_yaml(self.config_path) or {}
        if not isinstance(data, dict):
            data = {}

        audio = data.get("audio")
        vad = data.get("vad")
        kws = data.get("kws")
        asr = data.get("asr")
        if not isinstance(audio, dict):
            audio = {}
            data["audio"] = audio
        if not isinstance(vad, dict):
            vad = {}
            data["vad"] = vad
        if not isinstance(kws, dict):
            kws = {}
            data["kws"] = kws
        if not isinstance(asr, dict):
            asr = {}
            data["asr"] = asr
        
        asr["provider"] = self.asr_provider.currentText()

        audio["pre_roll_sec"] = float(self.audio_pre_roll.value())

        vad["silence_threshold"] = int(self.vad_silence_threshold.value())
        vad["max_recording_sec"] = float(self.vad_max_recording.value())
        vad["wakeup_silence_limit_sec"] = float(self.vad_wakeup_silence_limit.value())
        vad["wakeup_silence_ramp_sec"] = float(self.vad_wakeup_silence_ramp.value())

        kws["keywords_score"] = float(self.kws_keywords_score.value())
        kws["keywords_threshold"] = float(self.kws_keywords_threshold.value())
        kws["cooldown_sec"] = float(self.kws_cooldown.value())
        
        raw_words = self.kws_wake_words.text().strip()
        if raw_words:
            kws["keywords"] = [w.strip() for w in raw_words.replace("，", ",").split(",") if w.strip()]
        else:
            kws["keywords"] = []

        return data

    def _collect_file_config(self):
        out = {"files": []}
        for r in range(self.file_table.rowCount()):
            kw_item = self.file_table.item(r, 0)
            path_item = self.file_table.item(r, 1)
            kw_str = kw_item.text() if kw_item else ""
            path_str = path_item.text() if path_item else ""
            keywords = self._parse_keywords(kw_str)
            path_str = (path_str or "").strip()
            if not path_str:
                continue
            out["files"].append({"keywords": keywords, "path": path_str})
        return out

    def _collect_web_config(self):
        out = {"websites": []}
        for r in range(self.web_table.rowCount()):
            kw_item = self.web_table.item(r, 0)
            url_item = self.web_table.item(r, 1)
            kw_str = kw_item.text() if kw_item else ""
            url_str = url_item.text() if url_item else ""
            keywords = self._parse_keywords(kw_str)
            url_str = (url_str or "").strip()
            if not url_str:
                continue
            out["websites"].append({"keywords": keywords, "url": url_str})
        return out

    def _on_save(self):
        try:
            main_config = self._collect_main_config()
            new_provider = ""
            if isinstance(main_config, dict):
                asr = main_config.get("asr", {})
                if isinstance(asr, dict):
                    new_provider = str(asr.get("provider", "")).strip()
            if self._initial_asr_provider is not None and new_provider and new_provider != self._initial_asr_provider:
                self.restart_required = True

            self._write_yaml(self.config_path, main_config)
            self._write_yaml(self.file_config_path, self._collect_file_config())
            self._write_yaml(self.web_config_path, self._collect_web_config())
        except Exception:
            QMessageBox.critical(self, "保存失败", "保存配置时发生错误，请检查输入内容。")
            return
        self.accept()

class FloatingBall(QWidget):
    def __init__(self, worker):
        super().__init__()
        self.worker = worker
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(160, 160)  # Larger canvas for glow effects
        
        # UI State
        self.current_state = "IDLE"
        self.base_color = QColor(0, 255, 204) # Cyberpunk Cyan
        
        # Animation State
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.update_animation)
        self.anim_timer.start(16) # ~60 FPS
        
        self.time_counter = 0.0
        self.pulse_scale = 1.0
        self.rotation_angle = 0.0
        self.particle_angle = 0.0
        
        self.toast_manager = ToastManager()
        
        # Connect signals
        self.worker.state_changed.connect(self.update_state)
        self.worker.text_received.connect(self.show_bubble)
        
        # Dragging logic
        self.old_pos = None

    def _show_toast(self, kind: str, title: str, subtitle: str = ""):
        ball_geo = self.geometry()
        center = ball_geo.center()
        screen = QApplication.screenAt(center)
        if screen is None:
            screen_geo = QApplication.primaryScreen().availableGeometry()
        else:
            screen_geo = screen.availableGeometry()
        prefer_left = center.x() > (screen_geo.left() + screen_geo.width() / 2)
        self.toast_manager.show_toast(kind, title, subtitle, ball_geo, screen_geo, prefer_left)

    def open_settings(self):
        project_root = Path(__file__).resolve().parents[2]
        dlg = SettingsDialog(project_root, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if getattr(dlg, "restart_required", False):
                self._show_toast("info", "ASR 已切换", "正在重启应用…")
                QTimer.singleShot(450, lambda: QApplication.instance().exit(RESTART_EXIT_CODE))
            else:
                self._show_toast("success", "设置已保存", "")

    def update_state(self, state):
        self.current_state = state
        if state == "IDLE":
            self.base_color = QColor(0, 255, 204) # Cyan
        elif state == "LISTENING":
            self.base_color = QColor(255, 50, 80) # Neon Red
        elif state == "THINKING":
            self.base_color = QColor(180, 80, 255) # Electric Purple
        elif state == "EXECUTING":
            self.base_color = QColor(255, 200, 0) # Gold

    def show_bubble(self, text):
        action_map = {
            "open_web": "打开网站",
            "open_file": "打开",
        }

        def display_target(raw_target: str) -> str:
            t = (raw_target or "").strip().strip("\"'").strip()
            if not t:
                return ""
            t2 = t.replace("\\", "/").rstrip("/")
            if "/" in t2:
                tail = t2.split("/")[-1].strip()
                return tail or t
            return t

        if text.startswith("Wake:"):
            kind = "info"
            title = "已唤醒"
            subtitle = text.replace("Wake:", "", 1).strip()
        elif text.startswith("Heard:"):
            kind = "listening"
            title = "我听到"
            subtitle = text.replace("Heard:", "", 1).strip()
        elif text.startswith("ResultOK:") or text.startswith("ResultFAIL:"):
            ok = text.startswith("ResultOK:")
            kind = "success" if ok else "error"
            title = "已完成" if ok else "执行失败"
            subtitle = text.split(":", 1)[1].strip()
        elif text.startswith("Result:"):
            raw = text.replace("Result:", "", 1).strip()
            raw = raw.replace("Executed ", "", 1).strip()

            status = ""
            left = raw
            if ":" in raw:
                maybe_left, maybe_status = raw.rsplit(":", 1)
                maybe_status = maybe_status.strip()
                if re.search(r"\b(success|ok|done|fail|failed|error)\b", maybe_status, re.IGNORECASE):
                    left = maybe_left.strip()
                    status = maybe_status

            ok = bool(re.search(r"\b(success|ok|done)\b", status, re.IGNORECASE))
            kind = "success" if ok else ("error" if status else "info")

            parts = left.split(None, 1)
            action = parts[0].strip() if parts else ""
            target = parts[1].strip() if len(parts) > 1 else ""

            action_cn = action_map.get(action, "")
            if action_cn:
                title = action_cn
                subtitle = display_target(target)
                if status:
                    subtitle = subtitle + (f"（{status}）" if subtitle else f"{status}")
            else:
                title = "已完成" if ok else ("执行失败" if status else "提示")
                subtitle = left + (f"（{status}）" if status else "")
        else:
            kind = "info"
            title = "提示"
            subtitle = text

        self._show_toast(kind, title, subtitle)

    def update_animation(self):
        self.time_counter += 0.05
        
        # Base breathing
        if self.current_state == "IDLE":
            self.pulse_scale = 1.0 + 0.05 * math.sin(self.time_counter)
            self.rotation_angle += 0.5
        elif self.current_state == "LISTENING":
            # Fast, erratic pulsing
            self.pulse_scale = 1.0 + 0.15 * math.sin(self.time_counter * 3)
            self.rotation_angle += 2.0
        elif self.current_state == "THINKING":
            self.pulse_scale = 1.0 + 0.02 * math.sin(self.time_counter * 5)
            self.rotation_angle += 5.0 # Fast spin
        elif self.current_state == "EXECUTING":
            self.pulse_scale = 1.0 + 0.1 * math.sin(self.time_counter * 2)
            self.rotation_angle += 1.0
            
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        center = QPointF(self.width() / 2, self.height() / 2)
        base_radius = 35.0
        
        # 1. Outer Glow (Large, faint)
        glow_radius = base_radius * self.pulse_scale * 1.8
        glow = QRadialGradient(center, glow_radius)
        glow.setColorAt(0.0, QColor(self.base_color.red(), self.base_color.green(), self.base_color.blue(), 100))
        glow.setColorAt(1.0, QColor(self.base_color.red(), self.base_color.green(), self.base_color.blue(), 0))
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, glow_radius, glow_radius)
        
        # 2. Rotating Ring (Thinking/Listening)
        if self.current_state in ["THINKING", "LISTENING", "IDLE"]:
            painter.save()
            painter.translate(center)
            painter.rotate(self.rotation_angle)
            
            ring_pen = QPen(QColor(255, 255, 255, 150))
            ring_pen.setWidth(2)
            ring_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            
            ring_radius = base_radius * 1.2
            
            # Draw segmented ring
            if self.current_state == "THINKING":
                # Spinning incomplete ring
                conical = QConicalGradient(QPointF(0,0), 0)
                conical.setColorAt(0.0, QColor(255, 255, 255, 0))
                conical.setColorAt(1.0, self.base_color)
                painter.setPen(QPen(QBrush(conical), 3))
                painter.drawArc(QRectF(-ring_radius, -ring_radius, ring_radius*2, ring_radius*2), 0, 360 * 16)
            else:
                # Decorative ticks
                painter.setPen(ring_pen)
                for i in range(4):
                    painter.rotate(90)
                    painter.drawArc(QRectF(-ring_radius, -ring_radius, ring_radius*2, ring_radius*2), 0, 45 * 16)
            
            painter.restore()

        # 3. Core Orb
        core_radius = base_radius * self.pulse_scale
        core_grad = QRadialGradient(center, core_radius)
        core_grad.setColorAt(0.0, QColor(255, 255, 255, 240)) # Bright center
        core_grad.setColorAt(0.4, self.base_color)
        core_grad.setColorAt(0.9, QColor(self.base_color.red(), self.base_color.green(), self.base_color.blue(), 150))
        core_grad.setColorAt(1.0, QColor(self.base_color.red(), self.base_color.green(), self.base_color.blue(), 0))
        
        painter.setBrush(QBrush(core_grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, core_radius, core_radius)
        
        # 4. State Icon / Letter (Optional overlay)
        painter.setPen(QColor(255, 255, 255, 200))
        font = QFont("Arial", 10, QFont.Weight.Bold)
        painter.setFont(font)
        # text = self.current_state[:1]
        # painter.drawText(QRectF(center.x()-10, center.y()-10, 20, 20), Qt.AlignmentFlag.AlignCenter, text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos:
            delta = event.globalPosition().toPoint() - self.old_pos
            new_pos = self.pos() + delta
            screen = QApplication.screenAt(event.globalPosition().toPoint())
            if screen is None:
                screen_geo = QApplication.primaryScreen().availableGeometry()
            else:
                screen_geo = screen.availableGeometry()

            x = max(screen_geo.left(), min(new_pos.x(), screen_geo.right() - self.width()))
            y = max(screen_geo.top(), min(new_pos.y(), screen_geo.bottom() - self.height()))
            self.move(x, y)
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None
        
        screen = QApplication.screenAt(self.geometry().center())
        if screen is None:
            screen_geo = QApplication.primaryScreen().availableGeometry()
        else:
            screen_geo = screen.availableGeometry()
        current_geo = self.geometry()
        
        target_x = current_geo.x()
        target_y = current_geo.y()
        
        # 1. Snap to Left or Right edge
        dist_to_left = abs(current_geo.left() - screen_geo.left())
        dist_to_right = abs(current_geo.right() - screen_geo.right())
        
        if dist_to_left < dist_to_right:
            target_x = screen_geo.left() + 5 # Small margin
        else:
            target_x = screen_geo.right() - current_geo.width() - 5
            
        # 2. Keep Y within screen bounds
        if current_geo.top() < screen_geo.top():
            target_y = screen_geo.top() + 5
        elif current_geo.bottom() > screen_geo.bottom():
            target_y = screen_geo.bottom() - current_geo.height() - 5
            
        # Animate to target position
        self.snap_anim = QPropertyAnimation(self, b"pos")
        self.snap_anim.setDuration(300)
        self.snap_anim.setStartValue(self.pos())
        self.snap_anim.setEndValue(QPoint(target_x, target_y))
        self.snap_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.snap_anim.start()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(30, 30, 40, 240);
                color: white;
                border: 1px solid #444;
                border-radius: 5px;
            }
            QMenu::item {
                padding: 5px 20px;
            }
            QMenu::item:selected {
                background-color: rgba(0, 255, 204, 50);
            }
        """)

        settings_action = QAction("设置", self)
        settings_action.triggered.connect(self.open_settings)
        menu.addAction(settings_action)
        
        quit_action = QAction("Exit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)
        menu.exec(event.globalPos())

    def closeEvent(self, event):
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    
    # Start worker thread
    worker = BackendWorker()
    worker_thread = threading.Thread(target=worker.run, daemon=True)
    worker_thread.start()
    
    # Create Floating Ball
    ball = FloatingBall(worker)
    ball.show()
    app.aboutToQuit.connect(worker.stop)
    exit_code = app.exec()
    worker.stop()
    return exit_code

if __name__ == "__main__":
    raise SystemExit(main())
