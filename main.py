"""
Chrono Sentinel - Monitor de Infraestructura (v0.3)
Free: 1 nodo en vivo.
PRO (licencia Gumroad): multi-nodo + alertas de umbral + deteccion de caida.
Nuevo en v0.3: historial (sparkline), deteccion de nodo caido, notificaciones
via ntfy.sh, soporte para endpoints JSON simple o texto tipo Prometheus.
AAP acustico: pendiente (requiere resolver formato de audio en Android).
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
HISTORY_LENGTH = 20
OFFLINE_AFTER_FAILURES = 3
SPARK_BLOCKS = "▁▂▃▄▅▆▇█"

GUMROAD_PRODUCT_PERMALINK = "chrono-sentinel-pro"
GUMROAD_VERIFY_URL = "https://api.gumroad.com/v2/licenses/verify"

LICENSE_FILENAME = "license.json"
NODES_FILENAME = "nodes.json"
SETTINGS_FILENAME = "settings.json"


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


def load_settings():
    path = _data_path(SETTINGS_FILENAME)
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_settings(settings):
    with open(_data_path(SETTINGS_FILENAME), "w") as f:
        json.dump(settings, f)


def send_local_notification(title, message):
    try:
        from plyer import notification
        notification.notify(title=title, message=message, timeout=10)
    except Exception:
        pass


def send_ntfy_notification(topic, title, message):
    if not topic:
        return
    url = f"https://ntfy.sh/{topic}"
    headers = {"Title": title, "Priority": "high"}
    try:
        UrlRequest(url, req_body=message.encode("utf-8"), req_headers=headers,
                   method="POST", on_failure=lambda *a: None, on_error=lambda *a: None,
                   timeout=8)
    except Exception:
        pass


def send_alert(title, message, ntfy_topic=None):
    send_local_notification(title, message)
    if ntfy_topic:
        send_ntfy_notification(ntfy_topic, title, message)


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


def sparkline(values):
    if not values:
        return ""
    out = []
    for v in values:
        try:
            v = float(v)
        except (TypeError, ValueError):
            v = 0
        idx = min(len(SPARK_BLOCKS) - 1, max(0, int(v / 100 * (len(SPARK_BLOCKS) - 1))))
        out.append(SPARK_BLOCKS[idx])
    return "".join(out)


def parse_metrics(raw_text):
    raw_text = raw_text.strip()
    try:
        data = json.loads(raw_text)
        return {
            "cpu": data.get("cpu", data.get("cpu_percent", 0)),
            "ram": data.get("ram", data.get("memory_percent", data.get("mem", 0))),
            "disk": data.get("disk", data.get("disk_percent", 0)),
            "hostname": data.get("hostname", data.get("host", "--")),
            "net": data.get("net", data.get("network", "--")),
        }
    except (json.JSONDecodeError, TypeError):
        pass

    metrics = {}
    for line in raw_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.replace("=", " ").split()
        if len(parts) < 2:
            continue
        name = parts[0].lower()
        try:
            value = float(parts[-1])
        except ValueError:
            continue
        metrics[name] = value

    cpu = next((v for n, v in metrics.items() if "cpu" in n), 0)
    ram = next((v for n, v in metrics.items() if "mem" in n or "ram" in n), 0)
    disk = next((v for n, v in metrics.items() if "disk" in n or "fs" in n), 0)
    return {"cpu": cpu, "ram": ram, "disk": disk, "hostname": "--", "net": "--"}


class NodeCard(BoxLayout):
    def __init__(self, node, on_remove, is_pro_getter, ntfy_getter, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None, height=170,
                          padding=10, spacing=4, **kwargs)
        self.node = node
        self.on_remove = on_remove
        self.is_pro_getter = is_pro_getter
        self.ntfy_getter = ntfy_getter
        self._last_alert = {}
        self._consecutive_failures = 0
        self._last_success_time = None
        self._cpu_history = []

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

        self.history_lbl = Label(text="Historial: --", color=GREY, size_hint_y=None,
                                  height=24, font_size=13)
        self.add_widget(self.history_lbl)

    def _sync_bg(self, *args):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def fetch(self, dt=None):
        UrlRequest(self.node["url"], on_success=self._on_success,
                   on_failure=self._on_fail, on_error=self._on_fail, timeout=6)

    def _on_success(self, request, result):
        if isinstance(result, (bytes, bytearray)):
            result = result.decode("utf-8", errors="ignore")
        if isinstance(result, str):
            parsed = parse_metrics(result)
        elif isinstance(result, dict):
            parsed = {
                "cpu": result.get("cpu", 0), "ram": result.get("ram", 0),
                "disk": result.get("disk", 0), "hostname": result.get("hostname", "--"),
                "net": result.get("net", "--"),
            }
        else:
            parsed = {"cpu": 0, "ram": 0, "disk": 0, "hostname": "--", "net": "--"}

        cpu, ram, disk = parsed["cpu"], parsed["ram"], parsed["disk"]
        net = parsed["net"]

        was_offline = self._consecutive_failures >= OFFLINE_AFTER_FAILURES
        self._consecutive_failures = 0
        self._last_success_time = time.time()

        self.status_lbl.text = "En linea"
        self.status_lbl.color = GREEN
        self.stats_lbl.text = f"CPU {cpu}% | RAM {ram}% | Disco {disk}% | Red {net}"

        try:
            self._cpu_history.append(float(cpu))
        except (TypeError, ValueError):
            self._cpu_history.append(0)
        self._cpu_history = self._cpu_history[-HISTORY_LENGTH:]
        self.history_lbl.text = f"Historial CPU: {sparkline(self._cpu_history)}"

        if was_offline and self.is_pro_getter():
            send_alert(f"Chrono Sentinel: {self.node['name']}",
                       "El nodo volvio a responder", self.ntfy_getter())

        if self.is_pro_getter():
            self._check_alert("CPU", cpu)
            self._check_alert("RAM", ram)
            self._check_alert("Disco", disk)

    def _on_fail(self, request, error):
        self._consecutive_failures += 1
        if self._consecutive_failures >= OFFLINE_AFTER_FAILURES:
            mins = "?"
            if self._last_success_time:
                mins = f"{int((time.time() - self._last_success_time) / 60)}m"
            self.status_lbl.text = f"SIN RESPUESTA (hace {mins})"
            self.status_lbl.color = RED
            if self.is_pro_getter():
                self._check_alert("_offline", 100, force_key="_offline")
        else:
            self.status_lbl.text = "Error de conexion"
            self.status_lbl.color = AMBER

    def _check_alert(self, metric_name, value, force_key=None):
        try:
            v = float(value)
        except (TypeError, ValueError):
            return
        key = force_key or metric_name
        if force_key is None and v < ALERT_THRESHOLD:
            return
        now = time.time()
        last = self._last_alert.get(key, 0)
        if now - last < ALERT_COOLDOWN_SECONDS:
            return
        self._last_alert[key] = now
        if force_key == "_offline":
            msg = f"Sin respuesta desde hace varios intentos — revisa el nodo"
        else:
            msg = f"{metric_name} al {v:.0f}% — revisa el nodo"
        send_alert(f"Chrono Sentinel: {self.node['name']}", msg, self.ntfy_getter())


class SentinelRoot(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=16, spacing=10, **kwargs)
        Window.clearcolor = BG

        self.settings = load_settings()

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

        notif_btn = Button(text="Configurar notificaciones (ntfy)", size_hint_y=None,
                            height=40, background_color=(0.2, 0.3, 0.32, 1), font_size=12)
        notif_btn.bind(on_press=self.show_notif_popup)
        self.add_widget(notif_btn)

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

        aap_btn = Button(text="AAP acustico — en desarrollo", size_hint_y=None,
                          height=40, background_color=(0.25, 0.25, 0.27, 1), font_size=12)
        aap_btn.bind(on_press=self.show_aap_notice)
        self.add_widget(aap_btn)

        for node in self.nodes:
            self._add_node_card(node)

        Clock.schedule_interval(self._poll_all, REFRESH_SECONDS)

    def _pro_status_text(self):
        if self.is_pro:
            return "PRO activo: nodos ilimitados + alertas + deteccion de caida"
        return f"Free: hasta {FREE_NODE_LIMIT} nodo. PRO desbloquea multi-nodo y alertas."

    def _get_ntfy_topic(self):
        return self.settings.get("ntfy_topic", "")

    def _poll_all(self, dt):
        for card in self.node_cards.values():
            card.fetch()

    def _add_node_card(self, node):
        card = NodeCard(node, on_remove=self.remove_node, is_pro_getter=lambda: self.is_pro,
                         ntfy_getter=self._get_ntfy_topic)
        self.node_cards[node["id"]] = card
        self.node_list_layout.add_widget(card)
        card.fetch()

    def remove_node(self, node_id):
        self.nodes = [n for n in self.nodes if n["id"] != node_id]
        save_nodes(self.nodes)
        card = self.node_cards.pop(node_id, None)
        if card:
            self.node_list_layout.remove_widget(card)

    def show_notif_popup(self, *args):
        content = BoxLayout(orientation="vertical", padding=12, spacing=8)
        content.add_widget(Label(
            text="Notificaciones via ntfy.sh (gratis, sin registro).\n"
                 "Elige un nombre de canal unico y suscribete\n"
                 "en la app ntfy o en ntfy.sh/tu-canal desde el navegador.",
            color=FG, size_hint_y=None, height=90
        ))
        topic_input = TextInput(text=self.settings.get("ntfy_topic", ""),
                                 hint_text="ej. chronosentinel-dani-2026",
                                 multiline=False, size_hint_y=None, height=44,
                                 background_color=(0.1, 0.12, 0.14, 1), foreground_color=FG)
        content.add_widget(topic_input)

        btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=44, spacing=8)
        save_btn = Button(text="Guardar", background_color=CYAN)
        cancel_btn = Button(text="Cancelar")
        btn_row.add_widget(save_btn)
        btn_row.add_widget(cancel_btn)
        content.add_widget(btn_row)

        popup = Popup(title="Notificaciones (ntfy)", content=content, size_hint=(0.9, 0.55))
        cancel_btn.bind(on_press=lambda *a: popup.dismiss())

        def do_save(*a):
            self.settings["ntfy_topic"] = topic_input.text.strip()
            save_settings(self.settings)
            popup.dismiss()

        save_btn.bind(on_press=do_save)
        popup.open()

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
        url_input = TextInput(hint_text="http://IP:5000/api/status o /metrics",
                               multiline=False, size_hint_y=None, height=44,
                               background_color=(0.1, 0.12, 0.14, 1), foreground_color=FG)
        content.add_widget(name_input)
        content.add_widget(url_input)
        content.add_widget(Label(
            text="Acepta JSON {cpu,ram,disk} o texto tipo\n"
                 "Prometheus/node_exporter (lineas 'metrica valor')",
            color=GREY, size_hint_y=None, height=40, font_size=11
        ))

        feedback_lbl = Label(text="", color=RED, size_hint_y=None, height=24)
        content.add_widget(feedback_lbl)

        btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=44, spacing=8)
        save_btn = Button(text="Guardar", background_color=CYAN)
        cancel_btn = Button(text="Cancelar")
        btn_row.add_widget(save_btn)
        btn_row.add_widget(cancel_btn)
        content.add_widget(btn_row)

        popup = Popup(title="Agregar nodo", content=content, size_hint=(0.9, 0.65))
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
                 "de poder correr el analisis FFT. Sigue pendiente.",
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
                     "Nodos ilimitados, alertas de umbral y deteccion\n"
                     "de caida desbloqueados.",
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
