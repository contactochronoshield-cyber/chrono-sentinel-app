"""
Chrono Sentinel - Monitor de Infraestructura (v1 freemium)
Free: 1 nodo en vivo. PRO: multi-nodo + alertas + AAP acustico.
"""

import json
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

BG = (0.04, 0.05, 0.06, 1)
CYAN = (0.16, 0.85, 0.85, 1)
AMBER = (0.95, 0.7, 0.1, 1)
GREEN = (0.2, 0.9, 0.4, 1)
RED = (0.95, 0.25, 0.25, 1)
FG = (0.85, 0.9, 0.92, 1)

IS_PRO = False
REFRESH_SECONDS = 4


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

        pro_lbl = Label(text="PRO: multi-nodo, alertas, AAP acustico",
                         color=(0.5, 0.5, 0.5, 1), size_hint_y=None, height=28)
        self.add_widget(pro_lbl)
        pro_btn = Button(text="Desbloquear PRO", size_hint_y=None, height=44,
                          background_color=AMBER)
        pro_btn.bind(on_press=self.show_pro_popup)
        self.add_widget(pro_btn)

        self._event = None

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
        content = BoxLayout(orientation="vertical", padding=12, spacing=8)
        content.add_widget(Label(
            text="Version PRO: monitoreo multi-nodo,\nalertas push y deteccion acustica AAP.\n\nProximamente en la app.",
            color=FG
        ))
        close_btn = Button(text="Cerrar", size_hint_y=None, height=40)
        popup = Popup(title="Chrono Sentinel PRO", content=content,
                       size_hint=(0.85, 0.5))
        close_btn.bind(on_press=popup.dismiss)
        content.add_widget(close_btn)
        popup.open()


class SentinelApp(App):
    def build(self):
        self.title = "Chrono Sentinel"
        return SentinelRoot()


if __name__ == "__main__":
    SentinelApp().run()
