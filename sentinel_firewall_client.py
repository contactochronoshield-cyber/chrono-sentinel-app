import requests
import logging

class ChronoShieldClient:
    """
    Cliente de integración de Sentinel IA con Chrono Shield Networks Engine.
    Permite a los nodos de IA reportar y aplicar bloqueos dinámicos en tiempo real.
    """
    def __init__(self, api_host="127.0.0.1", api_port=8080):
        self.base_url = f"http://{api_host}:{api_port}"

    def check_health(self):
        """Verifica el estado operativo del motor Chrono Shield local"""
        try:
            res = requests.get(f"{self.base_url}/status", timeout=2)
            if res.status_code == 200:
                return res.json()
        except Exception as e:
            logging.error(f"[Sentinel IA] No se pudo conectar con Chrono Shield: {e}")
        return None

    def report_threat_to_firewall(self, domain_or_ip):
        """Aplica un bloqueo defensivo inmediato en el firewall local"""
        try:
            res = requests.post(
                f"{self.base_url}/block", 
                json={"domain": domain_or_ip}, 
                timeout=2
            )
            return res.status_code == 200
        except Exception as e:
            logging.error(f"[Sentinel IA] Error enviando regla de bloqueo: {e}")
            return False

if __name__ == "__main__":
    shield = ChronoShieldClient()
    status = shield.check_health()
    if status:
        print(f"[Sentinel IA] Conectado exitosamente a {status['engine']}")
        print(f"[Sentinel IA] Reglas activas en nodo: {status['blocked_domains_count']}")
