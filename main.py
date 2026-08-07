"""
Chrono Sentinel - Monitor de Infraestructura (v2)
Free: 1 nodo en vivo.
PRO (licencia Gumroad): multi-nodo + alertas de umbral.
AAP acustico: pendiente para v1.1 (requiere resolver formato de audio en Android).
"""

import json
import os
import time
import uuid
from urllib.parse import urlencode

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.network.urlrequest import UrlRequest
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle

# --- Tema tactico ---
BG = (0.04, 0.05, 0.06, 1)
PANEL = (0.09, 0.11, 0.13, 1)
CYAN = (0.16, 0.85, 0.85, 1)
AMBER = (0.95, 0.7, 0.1, 1)
GREEN = (0.2, 0.9, 0.4, 1)
RED = (0.95, 0.25, 0.25, 1)
GREY = (0.5, 0.5, 0.5, 1)
FG = (0.85, 0.9, 0.92, 1)

REFRESH_SECONDS = 4
ALERT_THRESHOLD = 85
ALERT_COOLDOWN_SECONDS = 300
FREE_NODE_LIMIT = 1

GUMROAD_PRODUCT_PERMALINK = "chrono-sentinel-pro"
GUMROAD_VERIFY_URL = "https://api.gumroad.com/v2/licenses/verify"

LICENSE_FILENAME = "license.json"
NODES_FILENAME = "nodes.json"


def _data_path(filename):
    app = App.get_running_app()
    data_dir = app.user_data_dir if app else "."
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, filename)


def load_license_state():
    path = _data_path(LICENSE_FILENAME)
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return bool(data.get("is_pro", False)), data.get("license_key", "")
        except (json.JSONDecodeError, OSError):
            return False, ""
    return False, ""


def save_license_state(is_pro, license_key):
    with open(_data_path(LICENSE_FILENAME), "w") as f:
        json.dump({"is_pro": is_pro, "license_key": license_key}, f)


def load_nodes():
    path = _data_path(NODES_FILENAME)
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_nodes(nodes):
    with open(_data_path(NODES_FILENAME), "w") as f:
        json.dump(nodes, f)


def send_alert_notification(title, message):
    try:
        from plyer import notification
        notification.notify(title=title, message=message, timeout=10)
    except Exception:
        pass


def level_color(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return CYAN
    if v >= ALERT_THRESHOLD:
        return RED
    if v >= 60:
        return AMBER
    return GREEN


class NodeCard(BoxLayout):
    def __init__(self, node, on_remove, is_pro_getter, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None, height=140,
                          padding=10, spacing=4, **kwargs)
        self.node = node
        self.on_remove = on_remove
        self.is_pro_getter = is_pro_getter
        self._last_alert = {}

        with self.canvas.before:
            Color(*PANEL)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync_bg, size=self._sync_bg)

        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=28)
        header.add_widget(Label(text=node["name"], color=CYAN, bold=True, halign="left"))
        remove_btn = Button(text="Quitar", size_hint_x=None, width=80,
                             background_color=RED, font_size=12)
        remove_btn.bind(on_press=lambda *a: self.on_remove(self.node["id"]))
        header.add_widget(remove_btn)
        self.add_widget(header)

        self.status_lbl = Label(text="Esperando...", color=GREY, size_hint_y=None,
                                 height=20, font_size=12)
        self.add_widget(self.status_lbl)

        self.stats_lbl = Label(text="CPU -- | RAM -- | Disco -- | Red --",
                                color=FG, size_hint_y=None, height=24, font_size=13)
        self.add_widget(self.stats_lbl)

    def _sync_bg(self, *args):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def fetch(self, dt=None):
        UrlRequest(self.node["url"], on_success=self._on_success,
                   on_failure=self._on_fail, on_error=self._on_fail, timeout=6)

    def _on_success(self, request, result):
        if isinstance(result, str):
            result = json.loads(result)
        cpu = result.get("cpu", 0)
        ram = result.get("ram", 0)
        disk = result.get("disk", 0)
        net = result.get("net", "--")

        self.status_lbl.text = "En linea"
        self.status_lbl.color = GREEN
        self.stats_lbl.text = f"CPU {cpu}% | RAM {ram}% | Disco {disk}% | Red {net}"

        if self.is_pro_getter():
            self._check_alert("CPU", cpu)
            self._check_alert("RAM", ram)
            self._check_alert("Disco", disk)

    def _on_fail(self, request, error):
        self.status_lbl.text = "Error de conexion"
        self.status_lbl.color = RED

    def _check_alert(self, metric_name, value):
        try:
            v = float(value)
        except (TypeError, ValueError):
            return
        if v < ALERT_THRESHOLD:
            return
        now = time.time()
        last = self._last_alert.get(metric_name, 0)
        if now - last < ALERT_COOLDOWN_SECONDS:
            return
        self._last_alert[metric_name] = now
        send_alert_notification(
            f"Chrono Sentinel: {self.node['name']}",
            f"{metric_name} al {v:.0f}% — revisa el nodo"
        )


class SentinelRoot(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=16, spacing=10, **kwargs)
        Window.clearcolor = BG

        self.add_widget(Label(
            text="CHRONO SENTINEL", color=CYAN, bold=True,
            font_size=26, size_hint_y=None, height=42
        ))
        self.add_widget(Label(
            text="Monitor de infraestructura en vivo", color=GREY,
            size_hint_y=None, height=20, font_size=12
        ))

        self.nodes = load_nodes()
        self.node_cards = {}

        self.node_list_layout = BoxLayout(orientation="vertical", size_hint_y=None, spacing=8)
        self.node_list_layout.bind(minimum_height=self.node_list_layout.setter("height"))

        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(self.node_list_layout)
        self.add_widget(scroll)

        add_node_btn = Button(text="+ Agregar nodo", size_hint_y=None, height=44,
                               background_color=CYAN)
        add_node_btn.bind(on_press=self.show_add_node_popup)
        self.add_widget(add_node_btn)

        self.is_pro, _saved_key = load_license_state()

        self.pro_status_lbl = Label(
            text=self._pro_status_text(), color=GREEN if self.is_pro else GREY,
            size_hint_y=None, height=24, font_size=12
        )
        self.add_widget(self.pro_status_lbl)

        self.pro_btn = Button(
            text="Version PRO activa" if self.is_pro else "Activar PRO (licencia Gumroad)",
            size_hint_y=None, height=44,
            background_color=GREEN if self.is_pro else AMBER
        )
        self.pro_btn.bind(on_press=self.show_pro_popup)
        self.add_widget(self.pro_btn)

        aap_btn = Button(text="AAP acustico — en desarrollo (v1.1)", size_hint_y=None,
                          height=40, background_color=(0.25, 0.25, 0.27, 1), font_size=12)
        aap_btn.bind(on_press=self.show_aap_notice)
        self.add_widget(aap_btn)

        for node in self.nodes:
            self._add_node_card(node)

        Clock.schedule_interval(self._poll_all, REFRESH_SECONDS)

    def _pro_status_text(self):
        if self.is_pro:
            return "PRO activo: nodos ilimitados + alertas de umbral"
        return f"Free: hasta {FREE_NODE_LIMIT} nodo. PRO desbloquea multi-nodo y alertas."

    def _poll_all(self, dt):
        for card in self.node_cards.values():
            card.fetch()

    def _add_node_card(self, node):
        card = NodeCard(node, on_remove=self.remove_node, is_pro_getter=lambda: self.is_pro)
        self.node_cards[node["id"]] = card
        self.node_list_layout.add_widget(card)
        card.fetch()

    def remove_node(self, node_id):
        self.nodes = [n for n in self.nodes if n["id"] != node_id]
        save_nodes(self.nodes)
        card = self.node_cards.pop(node_id, None)
        if card:
            self.node_list_layout.remove_widget(card)

    def show_add_node_popup(self, *args):
        if not self.is_pro and len(self.nodes) >= FREE_NODE_LIMIT:
            content = BoxLayout(orientation="vertical", padding=12, spacing=8)
            content.add_widget(Label(
                text=f"La version gratuita permite {FREE_NODE_LIMIT} nodo.\n"
                     "Activa PRO para monitorear varios nodos a la vez.",
                color=FG
            ))
            close_btn = Button(text="Entendido", size_hint_y=None, height=40)
            popup = Popup(title="Limite alcanzado", content=content, size_hint=(0.85, 0.4))
            close_btn.bind(on_press=popup.dismiss)
            content.add_widget(close_btn)
            popup.open()
            return

        content = BoxLayout(orientation="vertical", padding=12, spacing=8)
        name_input = TextInput(hint_text="Nombre del nodo (ej. Servidor Bogota)",
                                multiline=False, size_hint_y=None, height=44,
                                background_color=(0.1, 0.12, 0.14, 1), foreground_color=FG)
        url_input = TextInput(hint_text="http://IP:5000/api/status", multiline=False,
                               size_hint_y=None, height=44,
                               background_color=(0.1, 0.12, 0.14, 1), foreground_color=FG)
        content.add_widget(name_input)
        content.add_widget(url_input)

        feedback_lbl = Label(text="", color=RED, size_hint_y=None, height=24)
        content.add_widget(feedback_lbl)

        btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=44, spacing=8)
        save_btn = Button(text="Guardar", background_color=CYAN)
        cancel_btn = Button(text="Cancelar")
        btn_row.add_widget(save_btn)
        btn_row.add_widget(cancel_btn)
        content.add_widget(btn_row)

        popup = Popup(title="Agregar nodo", content=content, size_hint=(0.9, 0.55))
        cancel_btn.bind(on_press=lambda *a: popup.dismiss())

        def do_save(*a):
            name = name_input.text.strip()
            url = url_input.text.strip()
            if not name or not url:
                feedback_lbl.text = "Completa nombre y URL"
                return
            node = {"id": str(uuid.uuid4()), "name": name, "url": url}
            self.nodes.append(node)
            save_nodes(self.nodes)
            self._add_node_card(node)
            popup.dismiss()

        save_btn.bind(on_press=do_save)
        popup.open()

    def show_aap_notice(self, *args):
        content = BoxLayout(orientation="vertical", padding=12, spacing=8)
        content.add_widget(Label(
            text="El modulo AAP (deteccion acustica de sabotaje)\n"
                 "ya funciona en Termux via linea de comandos.\n\n"
                 "Integrarlo aqui requiere resolver el formato\n"
                 "de grabacion de audio de Android (3gp) antes\n"
                 "de poder correr el analisis FFT. Queda para\n"
                 "la siguiente version.",
            color=FG
        ))
        close_btn = Button(text="Cerrar", size_hint_y=None, height=40)
        popup = Popup(title="AAP acustico", content=content, size_hint=(0.9, 0.6))
        close_btn.bind(on_press=popup.dismiss)
        content.add_widget(close_btn)
        popup.open()

    def show_pro_popup(self, *args):
        if self.is_pro:
            content = BoxLayout(orientation="vertical", padding=12, spacing=8)
            content.add_widget(Label(
                text="Tu licencia PRO ya esta activa en este dispositivo.\n\n"
                     "Nodos ilimitados y alertas de umbral desbloqueados.",
                color=FG
            ))
            close_btn = Button(text="Cerrar", size_hint_y=None, height=40)
            popup = Popup(title="Chrono Sentinel PRO", content=content, size_hint=(0.85, 0.5))
            close_btn.bind(on_press=popup.dismiss)
            content.add_widget(close_btn)
            popup.open()
            return

        content = BoxLayout(orientation="vertical", padding=12, spacing=8)
        content.add_widget(Label(
            text="Compra la licencia en Gumroad y pega aqui\ntu clave de licencia:",
            color=FG, size_hint_y=None, height=60
        ))
        key_input = TextInput(hint_text="XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX",
                               multiline=False, size_hint_y=None, height=44,
                               background_color=(0.1, 0.12, 0.14, 1), foreground_color=FG)
        content.add_widget(key_input)

        self.pro_feedback_lbl = Label(text="", color=AMBER, size_hint_y=None, height=28)
        content.add_widget(self.pro_feedback_lbl)

        btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=44, spacing=8)
        verify_btn = Button(text="Verificar", background_color=CYAN)
        cancel_btn = Button(text="Cancelar")
        btn_row.add_widget(verify_btn)
        btn_row.add_widget(cancel_btn)
        content.add_widget(btn_row)

        popup = Popup(title="Activar Chrono Sentinel PRO", content=content, size_hint=(0.9, 0.55))
        cancel_btn.bind(on_press=lambda *a: popup.dismiss())
        verify_btn.bind(on_press=lambda *a: self.verify_license(key_input.text.strip(), popup))
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
