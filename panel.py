# panel.py
# ------------------------------------------------------------
# SMALL WEB SERVER THAT STARTS THE MONITORING AND CONTROL PANEL
#
# Serves the web page in the "panel/" folder at http://localhost:8000
# and opens the browser. The server has nothing to do with MQTT:
# once the page is open, the browser connects to Mosquitto over
# WebSocket ITSELF, so the panel is an MQTT client like every other
# device in the home.
#
# The server's only extra job: hand the topic names and thresholds in
# config.py to the page at "/config.json". This keeps the settings in
# one place (config.py) instead of repeating them in JavaScript.
# ------------------------------------------------------------

import functools
import json
import socket
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import config

PANEL_FOLDER = Path(__file__).parent / "panel"


def panel_config():
    """Prepares the settings the page needs as a dict."""
    return {
        "websocket_port": config.WEBSOCKET_PORT,
        "qos": config.QOS,
        "command_suffix": config.COMMAND_SUFFIX,
        "connection_topic_root": config.CONNECTION_TOPIC_ROOT,
        "subscribe_topic": config.SUBSCRIBE_TOPIC,
        "topics": {
            "temperature": config.TEMPERATURE_TOPIC,
            "outdoor_temperature": config.OUTDOOR_TEMPERATURE_TOPIC,
            "motion": config.MOTION_TOPIC,
            "door": config.DOOR_TOPIC,
            "lamp": config.LAMP_TOPIC,
            "ac": config.AC_TOPIC,
            "alarm": config.ALARM_TOPIC,
        },
        "ac_thresholds": {
            "cooling_start": config.AC_COOLING_START,
            "cooling_stop": config.AC_COOLING_STOP,
            "heating_start": config.AC_HEATING_START,
            "heating_stop": config.AC_HEATING_STOP,
        },
        "lamp_off_delay": config.LAMP_OFF_DELAY,
    }


class PanelRequestHandler(SimpleHTTPRequestHandler):
    """Called for every request from the browser."""

    def do_GET(self):
        if self.path == "/config.json":
            body = json.dumps(panel_config(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            # Everything else (index.html, panel.js...) is served from the panel/ folder.
            super().do_GET()

    def end_headers(self):
        # Don't let the browser cache files: after changing the code,
        # reloading the page is enough to see the new version.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format, *args):
        # Don't print every request (keeps the screen clean).
        pass


def websocket_open():
    try:
        with socket.create_connection((config.BROKER_HOST, config.WEBSOCKET_PORT), timeout=2):
            return True
    except OSError:
        return False


def main():
    if not websocket_open():
        print(f"WARNING: Could not reach the broker's WebSocket port ({config.WEBSOCKET_PORT}).\n"
              f"         Make sure Mosquitto was started with the project settings:\n"
              f"         mosquitto -c mosquitto.conf -v\n"
              f"         (The panel will still open and connect by itself once the broker is up.)\n")

    handler = functools.partial(PanelRequestHandler, directory=str(PANEL_FOLDER))
    try:
        server = ThreadingHTTPServer(("localhost", config.PANEL_PORT), handler)
    except OSError:
        print(f"ERROR: Port {config.PANEL_PORT} is in use. The panel may already be open.")
        return

    url = f"http://localhost:{config.PANEL_PORT}"
    print(f"[PANEL] Serving at {url}. (Quit: Ctrl+C)")

    # With "--no-browser" the browser is not opened automatically (for testing).
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[PANEL] Shutting down...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
