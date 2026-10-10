# panel.py
# ------------------------------------------------------------
# İZLEME VE KONTROL PANELİNİ BAŞLATAN KÜÇÜK WEB SUNUCUSU
#
# "panel/" klasöründeki web sayfasını http://localhost:8000 adresinde
# yayınlar ve tarayıcıyı açar. Sunucunun MQTT ile bir ilgisi yoktur:
# sayfa açıldıktan sonra tarayıcı Mosquitto'ya WebSocket ile KENDİSİ
# bağlanır, yani panel de evdeki diğer cihazlar gibi bir MQTT istemcisidir.
#
# Sunucunun tek ek görevi: ayarlar.py içindeki topic adlarını ve eşikleri
# "/ayarlar.json" adresinden sayfaya vermek. Böylece ayarlar tek bir
# yerde (ayarlar.py) kalır, JavaScript tarafında tekrar yazılmaz.
# ------------------------------------------------------------

import functools
import json
import socket
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import ayarlar

PANEL_KLASORU = Path(__file__).parent / "panel"


def panel_ayarlari():
    """Sayfanın ihtiyaç duyduğu ayarları sözlük olarak hazırlar."""
    return {
        "websocket_portu": ayarlar.WEBSOCKET_PORTU,
        "qos": ayarlar.QOS,
        "komut_eki": ayarlar.KOMUT_EKI,
        "baglanti_topic_koku": ayarlar.BAGLANTI_TOPIC_KOKU,
        "abone_topic": ayarlar.ABONE_TOPIC,
        "topicler": {
            "sicaklik": ayarlar.SICAKLIK_TOPIC,
            "hareket": ayarlar.HAREKET_TOPIC,
            "kapi": ayarlar.KAPI_TOPIC,
            "lamba": ayarlar.LAMBA_TOPIC,
            "klima": ayarlar.KLIMA_TOPIC,
            "alarm": ayarlar.ALARM_TOPIC,
        },
        "klima_esikleri": {
            "sogutma_basla": ayarlar.KLIMA_SOGUTMA_BASLA,
            "sogutma_dur": ayarlar.KLIMA_SOGUTMA_DUR,
            "isitma_basla": ayarlar.KLIMA_ISITMA_BASLA,
            "isitma_dur": ayarlar.KLIMA_ISITMA_DUR,
        },
        "lamba_kapanma_suresi": ayarlar.LAMBA_KAPANMA_SURESI,
    }


class PanelIstekIsleyici(SimpleHTTPRequestHandler):
    """Tarayıcıdan gelen her istek için çağrılır."""

    def do_GET(self):
        if self.path == "/ayarlar.json":
            govde = json.dumps(panel_ayarlari(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(govde)))
            self.end_headers()
            self.wfile.write(govde)
        else:
            # Diğer her şey (index.html, panel.js...) panel/ klasöründen verilir.
            super().do_GET()

    def end_headers(self):
        # Tarayıcı dosyaları önbellekte tutmasın: kodu değiştirince
        # sayfayı yenilemek yeni hali göstermeye yetsin.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format, *args):
        # Her isteği ekrana yazmasın (ekran temiz kalsın).
        pass


def websocket_acik_mi():
    try:
        with socket.create_connection((ayarlar.BROKER_ADRESI, ayarlar.WEBSOCKET_PORTU), timeout=2):
            return True
    except OSError:
        return False


def main():
    if not websocket_acik_mi():
        print(f"UYARI: Broker'ın WebSocket portuna ({ayarlar.WEBSOCKET_PORTU}) ulaşılamadı.\n"
              f"       Mosquitto'yu proje ayarlarıyla başlattığınızdan emin olun:\n"
              f"       mosquitto -c mosquitto.conf -v\n"
              f"       (Panel yine açılacak ve broker gelince kendiliğinden bağlanacak.)\n")

    isleyici = functools.partial(PanelIstekIsleyici, directory=str(PANEL_KLASORU))
    try:
        sunucu = ThreadingHTTPServer(("localhost", ayarlar.PANEL_PORTU), isleyici)
    except OSError:
        print(f"HATA: {ayarlar.PANEL_PORTU} portu kullanımda. Panel zaten açık olabilir.")
        return

    adres = f"http://localhost:{ayarlar.PANEL_PORTU}"
    print(f"[PANEL] {adres} adresinde yayında. (Çıkış: Ctrl+C)")

    # "--tarayici-acma" verilirse tarayıcı otomatik açılmaz (test için).
    if "--tarayici-acma" not in sys.argv:
        webbrowser.open(adres)

    try:
        sunucu.serve_forever()
    except KeyboardInterrupt:
        print("\n[PANEL] Kapatılıyor...")
    finally:
        sunucu.server_close()


if __name__ == "__main__":
    main()
