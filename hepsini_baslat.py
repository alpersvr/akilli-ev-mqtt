# hepsini_baslat.py
# ------------------------------------------------------------
# TÜM CİHAZLARI TEK KOMUTLA BAŞLATICI
#
# 7 programı ayrı ayrı 7 terminalde açmak yerine, bu dosya hepsini
# aynı anda ayrı süreçler (process) olarak başlatır. Her cihaz yine
# kendi bağımsız MQTT istemcisidir; gerçek bir evdeki gibi.
# Ctrl+C'ye basınca hepsi birlikte düzgünce kapanır.
#
# abone.py bu listede YOK: onu ayrı bir terminalde açıp evdeki
# tüm trafiği temiz bir ekranda izleyebilirsiniz.
# ------------------------------------------------------------

import socket
import subprocess
import sys
import time
from pathlib import Path

import ayarlar

# Önce eyleyiciler ve otomasyon açılır ki sensörlerin ilk mesajlarını kaçırmasınlar.
PROGRAMLAR = [
    "lamba.py",
    "klima.py",
    "alarm.py",
    "otomasyon.py",
    "sicaklik_sensoru.py",
    "hareket_sensoru.py",
    "kapi_sensoru.py",
]


def broker_calisiyor_mu():
    """Broker'ın portuna kısa bir bağlantı deneyerek çalışıp çalışmadığına bakar."""
    try:
        with socket.create_connection((ayarlar.BROKER_ADRESI, ayarlar.BROKER_PORTU), timeout=2):
            return True
    except OSError:
        return False


def main():
    if not broker_calisiyor_mu():
        print("HATA: Broker'a ulaşılamadı. Önce başka bir terminalde 'mosquitto -v' çalıştırın.")
        return

    klasor = Path(__file__).parent
    surecler = []
    for program in PROGRAMLAR:
        # sys.executable = şu an kullanılan Python (sanal ortamdaki)
        # -u = çıktıyı bekletmeden hemen ekrana yaz
        surecler.append(subprocess.Popen([sys.executable, "-u", str(klasor / program)], cwd=klasor))
        time.sleep(0.3)

    print(f"\n>>> {len(surecler)} program çalışıyor. Hepsini durdurmak için Ctrl+C <<<\n")

    try:
        # Programlardan biri beklenmedik şekilde kapanana kadar bekle.
        while all(s.poll() is None for s in surecler):
            time.sleep(0.5)
        print("\nBir program beklenmedik şekilde kapandı; diğerleri de durduruluyor...")
        for s in surecler:
            if s.poll() is None:
                s.terminate()
    except KeyboardInterrupt:
        # Terminalde Ctrl+C'ye basılınca sinyal tüm programlara zaten gider;
        # biz sadece hepsinin kapanmasını bekliyoruz.
        print("\nTüm programlar durduruluyor...")

    for s in surecler:
        try:
            s.wait(timeout=5)
        except subprocess.TimeoutExpired:
            s.kill()
    print("Hepsi kapandı.")


if __name__ == "__main__":
    main()
