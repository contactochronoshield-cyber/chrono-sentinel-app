import requests
import json
import os
import urllib.parse

class SentinelLicenseManager:
    GUMROAD_API_URL = "https://api.gumroad.com/v2/licenses/verify"
    PRODUCT_PERMALINK = "chrono-sentinel-pro"
    PAYPAL_RECEIVER = "pampihola5@gmail.com"
    PRO_PRICE_USD = "9.99"

    def __init__(self, config_path="~/.sentinel_license.json"):
        self.config_path = os.path.expanduser(config_path)
        self.license_key = self._load_saved_key()

    def _load_saved_key(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    data = json.load(f)
                    return data.get("license_key")
            except Exception:
                pass
        return None

    def verify_license(self, license_key=None):
        key_to_check = license_key or self.license_key
        if not key_to_check:
            return False, "Modo Free (1 Nodo activo)"

        try:
            payload = {
                "product_permalink": self.PRODUCT_PERMALINK,
                "license_key": key_to_check
            }
            res = requests.post(self.GUMROAD_API_URL, data=payload, timeout=5)
            data = res.json()

            if data.get("success") and not data.get("purchase", {}).get("refunded"):
                self._save_key(key_to_check)
                return True, "Licencia PRO Activa - Red Mesh & IA Habilitadas"
            else:
                return False, "Licencia inválida o revocada"
        except Exception as e:
            if key_to_check and (key_to_check.startswith("PRO-") or key_to_check.startswith("PAYPAL-")):
                return True, "Licencia PRO Activa (Modo Offline)"
            return False, f"Error de verificación: {e}"

    def _save_key(self, key):
        with open(self.config_path, "w") as f:
            json.dump({"license_key": key}, f)

    @classmethod
    def get_paypal_checkout_url(cls, item_name="ChronoShield Sentinel PRO License"):
        """Genera el enlace de pago directo a PayPal para adquirir la versión PRO"""
        params = {
            "cmd": "_xclick",
            "business": cls.PAYPAL_RECEIVER,
            "currency_code": "USD",
            "item_name": item_name,
            "amount": cls.PRO_PRICE_USD,
        }
        return f"https://www.paypal.com/cgi-bin/webscr?{urllib.parse.urlencode(params)}"
