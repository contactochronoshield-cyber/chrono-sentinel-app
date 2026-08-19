import logging

class SentinelAIEngine:
    def __init__(self, is_pro=False):
        self.is_pro = is_pro

    def analyze_telemetry(self, cpu_usage, ram_usage, network_tx_kbps, firewall_client):
        if not self.is_pro:
            return {"status": "FREE_LIMIT", "msg": "Actualiza a PRO para análisis de IA"}

        if cpu_usage > 90.0 and network_tx_kbps > 15000:
            anomaly_msg = f"DDoS / Exfiltración detectada (CPU: {cpu_usage}%, TX: {network_tx_kbps} KB/s)"
            logging.warning(f"[SENTINEL IA] {anomaly_msg}")
            
            if firewall_client:
                firewall_client.report_threat_to_firewall("suspicious-exfiltration-stream.net")
            
            return {
                "threat_detected": True,
                "action_taken": "CHRONOSHIELD_AUTO_BLOCK",
                "details": anomaly_msg
            }

        return {"threat_detected": False, "status": "OPTIMAL"}
