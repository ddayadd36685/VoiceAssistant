import sys
import json
import math
import threading
import websocket
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QMenu, QSystemTrayIcon,
    QGraphicsOpacityEffect
)
from PyQt6.QtCore import (
    Qt, QPoint, QPointF, pyqtSignal, QObject, QTimer, QPropertyAnimation,
    QEasingCurve, QRect, QRectF
)
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QAction, QIcon, QCursor, QFont, QFontMetrics,
    QRadialGradient, QPen, QConicalGradient
)

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
                msg = payload.get("message", "")
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

        self._text = ""
        self._font = QFont("Segoe UI", 12, QFont.Weight.DemiBold)
        self._max_text_width = 360
        self._pad_x = 16
        self._pad_y = 12
        self._radius = 12
        self._glow = 18

        self._bg = QColor(20, 20, 30, 220)
        self._border = QColor(0, 255, 204, 90)
        self._text_color = QColor(0, 255, 204, 255)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)
        
        self.hide_timer = QTimer(self)
        self.hide_timer.timeout.connect(self.fade_out)
        self.hide_timer.setSingleShot(True)
        
        self.opacity_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self.opacity_anim.setDuration(300)
        self.opacity_anim.finished.connect(self._on_anim_finished)

    def _on_anim_finished(self):
        if self._opacity_effect.opacity() <= 0.001:
            self.hide()

    def _recalc_size(self):
        fm = QFontMetrics(self._font)
        text_flags = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap)
        rect = fm.boundingRect(QRect(0, 0, self._max_text_width, 2000), text_flags, self._text)
        content_w = rect.width() + self._pad_x * 2
        content_h = rect.height() + self._pad_y * 2
        self.setFixedSize(content_w + self._glow * 2, content_h + self._glow * 2)

    def show_message(self, text, duration=4000):
        self._text = text
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

        glow_rect = QRectF(self._glow / 2, self._glow / 2, self.width() - self._glow, self.height() - self._glow)
        body_rect = glow_rect.adjusted(self._glow / 2, self._glow / 2, -self._glow / 2, -self._glow / 2)

        center = body_rect.center()
        max_r = max(body_rect.width(), body_rect.height()) * 0.75
        glow = QRadialGradient(center, max_r + self._glow)
        glow.setColorAt(0.0, QColor(self._border.red(), self._border.green(), self._border.blue(), 90))
        glow.setColorAt(1.0, QColor(self._border.red(), self._border.green(), self._border.blue(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawRoundedRect(glow_rect, self._radius + self._glow * 0.5, self._radius + self._glow * 0.5)

        painter.setBrush(QBrush(self._bg))
        painter.setPen(QPen(self._border, 1.0))
        painter.drawRoundedRect(body_rect, self._radius, self._radius)

        text_rect = body_rect.adjusted(self._pad_x, self._pad_y, -self._pad_x, -self._pad_y)
        painter.setPen(self._text_color)
        painter.setFont(self._font)
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap), self._text)

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
        
        # Text Bubble
        self.bubble = BubbleLabel(None)
        
        # Connect signals
        self.worker.state_changed.connect(self.update_state)
        self.worker.text_received.connect(self.show_bubble)
        
        # Dragging logic
        self.old_pos = None

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
        # Position bubble to the right of the ball
        ball_pos = self.geometry().topRight()
        self.bubble.move(ball_pos.x() + 10, ball_pos.y() + 20)
        self.bubble.show_message(text)

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
            self.move(self.pos() + delta)
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

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
        
        quit_action = QAction("Exit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)
        menu.exec(event.globalPos())

    def closeEvent(self, event):
        try:
            self.bubble.hide()
        except Exception:
            pass
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
