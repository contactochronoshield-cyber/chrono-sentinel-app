"""
Chrono Sentinel - Monitor de Infraestructura (v1 freemium)
Free: 1 nodo en vivo. PRO: multi-nodo + alertas + AAP acustico.
Licenciamiento PRO via Gumroad License Verification API.
"""

import json
import os
from urllib.parse import urlencode
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.network.urlrequest import UrlRequest
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle

# --- Tema tactico (mismo lenguaje visual del dashboard: fondo oscuro, acentos cian) ---
BG = (0.04, 0.05, 0.06, 1)
CYAN = (0.16, 0.85, 0.85, 1)
AMBER = (0.95, 0.7, 0.1, 1)
GREEN = (0.2, 0.9, 0.4, 1)
RED = (0.95, 0.25, 0.25, 1)
FG = (0.85, 0.9, 0.92, 1)

REFRESH_SECONDS = 4

# --- Gumroad ---
# Reemplaza esto con el "permalink" de tu producto en Gumroad
# (lo ves en la URL: gumroad.com/l/ESTE_ES_EL_PERMALINK)
GUMROAD_PRODUCT_PERMALINK = "chrono-sentinel-pro"
GUMROAD_VERIFY_URL = "https://api.gumroad.com/v2/licenses/verify"
LICENSE_FILENAME = "license.json"


def _license_path():
    app = App.get_running_app()
    data_dir = app.user_data_dir if app else "."
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, LICENSE_FILENAME)


def load_license_state():
    """Lee del disco si ya hay una licencia PRO validada localmente."""
    path = _license_path()
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return bool(data.get("is_pro", False)), data.get("license_key", "")
        except (json.JSONDecodeError, OSError):
            return False, ""
    return False, ""


def save_license_state(is_pro, license_key):
    path = _license_path()
    with open(path, "w") as f:
        json.dump({"is_pro": is_pro, "license_key": license_key}, f)


class StatRow(BoxLayout):
    def __init__(self, label_text, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=36, **kwargs)
        self.name_lbl = Label(text=label_text, color=FG, size_hint_x=0.4, halign="left")
        self.value_lbl = Label(text="--", color=CYAN, size_hint_x=0.6, halign="right")
        self.add_widget(self.name_lbl)
        self.add_widget(self.value_lbl)

    def set_value(self, text, color=CYAN):
        self.value_lbl.text = text
        self.value_lbl.color = color


class SentinelRoot(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=16, spacing=10, **kwargs)

        with self.canvas.before:
            Color(*BG)
            self.bg_rect = Rectangle(size=Window.size, pos=self.pos)
        Window.bind(size=self._update_bg)

        self.add_widget(Label(
            text="CHRONO SENTINEL", color=CYAN, bold=True,
            font_size=24, size_hint_y=None, height=40
        ))
        self.status_lbl = Label(text="Desconectado", color=AMBER, size_hint_y=None, height=24)
        self.add_widget(self.status_lbl)

        self.server_input = TextInput(
            hint_text="http://IP:5000/api/status", multiline=False,
            size_hint_y=None, height=44, background_color=(0.1, 0.12, 0.14, 1),
            foreground_color=FG
        )
        self.add_widget(self.server_input)

        connect_btn = Button(text="Conectar", size_hint_y=None, height=44,
                              background_color=CYAN)
        connect_btn.bind(on_press=self.start_polling)
        self.add_widget(connect_btn)

        self.rows = {
            "hostname": StatRow("Nodo"),
            "cpu": StatRow("CPU"),
            "ram": StatRow("RAM"),
            "disk": StatRow("Disco"),
            "net": StatRow("Red"),
        }
        for row in self.rows.values():
            self.add_widget(row)

        # --- Seccion PRO (bloqueada en free) ---
        self.is_pro, saved_key = load_license_state()

        self.pro_status_lbl = Label(
            text=self._pro_status_text(),
            color=GREEN if self.is_pro else (0.5, 0.5, 0.5, 1),
            size_hint_y=None, height=28
        )
        self.add_widget(self.pro_status_lbl)

        self.pro_btn = Button(
            text="Version PRO activa" if self.is_pro else "Activar PRO (licencia Gumroad)",
            size_hint_y=None, height=44,
            background_color=GREEN if self.is_pro else AMBER
        )
        self.pro_btn.bind(on_press=self.show_pro_popup)
        self.add_widget(self.pro_btn)

        self._event = None

    def _pro_status_text(self):
        if self.is_pro:
            return "PRO: multi-nodo, alertas y AAP desbloqueados"
        return "PRO: multi-nodo, alertas, AAP acustico"

    def _update_bg(self, *args):
        self.bg_rect.size = Window.size

    def start_polling(self, *args):
        if self._event:
            self._event.cancel()
        self._event = Clock.schedule_interval(self.fetch_status, REFRESH_SECONDS)
        self.fetch_status(0)

    def fetch_status(self, dt):
        url = self.server_input.text.strip()
        if not url:
            self.status_lbl.text = "Ingresa la URL del servidor"
            self.status_lbl.color = RED
            return
        UrlRequest(url, on_success=self.on_success, on_failure=self.on_fail,
                   on_error=self.on_fail, timeout=6)

    def on_success(self, request, result):
        if isinstance(result, str):
            result = json.loads(result)
        self.status_lbl.text = "En linea"
        self.status_lbl.color = GREEN
        self.rows["hostname"].set_value(str(result.get("hostname", "--")))
        self.rows["cpu"].set_value(f"{result.get('cpu', 0)}%", self._level_color(result.get("cpu", 0)))
        self.rows["ram"].set_value(f"{result.get('ram', 0)}%", self._level_color(result.get("ram", 0)))
        self.rows["disk"].set_value(f"{result.get('disk', 0)}%", self._level_color(result.get("disk", 0)))
        self.rows["net"].set_value(str(result.get("net", "--")))

    def on_fail(self, request, error):
        self.status_lbl.text = "Error de conexion"
        self.status_lbl.color = RED

    @staticmethod
    def _level_color(value):
        try:
            v = float(value)
        except (TypeError, ValueError):
            return CYAN
        if v >= 85:
            return RED
        if v >= 60:
            return AMBER
        return GREEN

    def show_pro_popup(self, *args):
        if self.is_pro:
            content = BoxLayout(orientation="vertical", padding=12, spacing=8)
            content.add_widget(Label(
                text="Tu licencia PRO ya esta activa en este dispositivo.\n\n"
                     "Multi-nodo, alertas y AAP acustico desbloqueados.",
                color=FG
            ))
            close_btn = Button(text="Cerrar", size_hint_y=None, height=40)
            close_btn.bind(on_press=lambda *a: popup.dismiss())
            content.add_widget(close_btn)
            popup = Popup(title="Chrono Sentinel PRO", content=content,
                           size_hint=(0.85, 0.5))
            popup.open()
            return

        content = BoxLayout(orientation="vertical", padding=12, spacing=8)
        content.add_widget(Label(
            text="Compra la licencia en Gumroad y pega aqui\ntu clave de licencia:",
            color=FG, size_hint_y=None, height=60
        ))
        key_input = TextInput(
            hint_text="XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX",
            multiline=False, size_hint_y=None, height=44,
            background_color=(0.1, 0.12, 0.14, 1), foreground_color=FG
        )
        content.add_widget(key_input)

        self.pro_feedback_lbl = Label(text="", color=AMBER, size_hint_y=None, height=28)
        content.add_widget(self.pro_feedback_lbl)

        btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=44, spacing=8)
        verify_btn = Button(text="Verificar", background_color=CYAN)
        cancel_btn = Button(text="Cancelar")
        btn_row.add_widget(verify_btn)
        btn_row.add_widget(cancel_btn)
        content.add_widget(btn_row)

        popup = Popup(title="Activar Chrono Sentinel PRO", content=content,
                       size_hint=(0.9, 0.55))
        cancel_btn.bind(on_press=lambda *a: popup.dismiss())
        verify_btn.bind(
            on_press=lambda *a: self.verify_license(key_input.text.strip(), popup)
        )
        popup.open()

    def verify_license(self, license_key, popup):
        if not license_key:
            self.pro_feedback_lbl.text = "Ingresa una clave"
            self.pro_feedback_lbl.color = RED
            return
        self.pro_feedback_lbl.text = "Verificando..."
        self.pro_feedback_lbl.color = AMBER

        body = urlencode({
            "product_permalink": GUMROAD_PRODUCT_PERMALINK,
            "license_key": license_key,
        })
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        UrlRequest(
            GUMROAD_VERIFY_URL, req_body=body, req_headers=headers, method="POST",
            on_success=lambda req, res: self._on_license_success(req, res, license_key, popup),
            on_failure=self._on_license_fail,
            on_error=self._on_license_fail,
            timeout=8
        )

    def _on_license_success(self, request, result, license_key, popup):
        if isinstance(result, str):
            result = json.loads(result)
        if result.get("success"):
            self.is_pro = True
            save_license_state(True, license_key)
            self.pro_status_lbl.text = self._pro_status_text()
            self.pro_status_lbl.color = GREEN
            self.pro_btn.text = "Version PRO activa"
            self.pro_btn.background_color = GREEN
            popup.dismiss()
        else:
            self.pro_feedback_lbl.text = "Licencia invalida"
            self.pro_feedback_lbl.color = RED

    def _on_license_fail(self, request, error):
        self.pro_feedback_lbl.text = "Error de conexion, intenta de nuevo"
        self.pro_feedback_lbl.color = RED


class SentinelApp(App):
    def build(self):
        self.title = "Chrono Sentinel"
        return SentinelRoot()


if __name__ == "__main__":
    SentinelApp().run()
