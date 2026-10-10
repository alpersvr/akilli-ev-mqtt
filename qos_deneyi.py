# qos_deneyi.py
# ------------------------------------------------------------
# QoS 0 / 1 / 2 GECİKME VE KAYIP DENEYİ
#
# Her ölçümde:
#   1. Bir abone (alıcı) ve bir yayıncı (gönderici) broker'a bağlanır.
#   2. Yayıncı sabit hızda N mesaj gönderir. Her mesajın içinde sıra
#      numarası ve gönderildiği an yazılıdır.
#   3. Abone her mesajın ne zaman geldiğini kaydeder.
#        gecikme = varış anı - gönderiliş anı
#        kayıp   = gönderilen ama hiç gelmeyen mesajlar
#        kopya   = aynı sıra numarasıyla birden fazla gelen mesajlar
#
# Bu işlem 3 ağ senaryosunda × 3 QoS seviyesinde × birkaç tekrarla yapılır.
# Yayıncı ve abone aynı programda çalıştığı için ikisi de aynı saati kullanır;
# bu sayede gecikme mikrosaniye hassasiyetle ölçülebilir.
#
# Sonuçlar "sonuclar/<tarih-saat>/" klasörüne CSV olarak yazılır.
# Grafikler için ardından: python qos_grafik.py
# ------------------------------------------------------------

import argparse
import csv
import json
import os
import platform
import socket
import statistics
import threading
import time
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

import paho.mqtt.client as mqtt
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties

import ayarlar
from ag_simulatoru import AgSimulatoru

# ============================================================
# DENEY AYARLARI
# ============================================================

QOS_SEVIYELERI = [0, 1, 2]

# Ağ senaryoları. "ag" None ise istemciler broker'a doğrudan bağlanır.
SENARYOLAR = [
    {"ad": "ideal", "aciklama": "Doğrudan bağlantı (localhost)", "ag": None},
    {"ad": "gecikmeli", "aciklama": "Her yönde 40 ± 10 ms gecikme",
     "ag": {"gecikme_ms": 40, "sapma_ms": 10, "ortalama_kopma_s": None}},
    {"ad": "kesintili", "aciklama": "40 ± 10 ms gecikme + ortalama 3 sn'de bir bağlantı kopması",
     "ag": {"gecikme_ms": 40, "sapma_ms": 10, "ortalama_kopma_s": 3}},
]

AG_SIMULATORU_PORTU = 1885  # Simülatörün dinleyeceği port
YUK_BOYUTU = 64             # Her mesajın bayt cinsinden boyutu (sensör verisi büyüklüğünde)
BOSALTMA_SURESI_S = 20      # Gönderim bitince geciken mesajlar için en fazla bekleme
OTURUM_SURESI_S = 60        # Kopmada broker'ın oturumu (abonelik + kuyruk) saklama süresi


# ============================================================
# MQTT YARDIMCILARI
# ============================================================

def istemci_baglan(kimlik, adres, port, mesaj_gelince=None, baglaninca=None):
    """
    Deney için bir MQTT v5 istemcisi oluşturup bağlar.

    Kalıcı oturum (persistent session) kullanıyoruz: bağlantı koparsa broker
    bu istemcinin aboneliklerini ve ulaştıramadığı QoS 1/2 mesajlarını
    OTURUM_SURESI_S boyunca saklar. Yeniden bağlanınca kaldığı yerden devam
    edilir. QoS'un vaat ettiği güvence ancak bu şekilde çalışır.
    """
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=kimlik, protocol=mqtt.MQTTv5)
    # Bağlantı koparsa 1-2 saniye içinde yeniden bağlan
    client.reconnect_delay_set(min_delay=1, max_delay=2)
    if mesaj_gelince:
        client.on_message = mesaj_gelince
    if baglaninca:
        client.on_connect = baglaninca

    ozellikler = Properties(PacketTypes.CONNECT)
    ozellikler.SessionExpiryInterval = OTURUM_SURESI_S
    # MQTT_CLEAN_START_FIRST_ONLY: ilk bağlantıda temiz oturum aç,
    # kopup yeniden bağlanınca eski oturumu devam ettir.
    client.connect(adres, port, keepalive=10,
                   clean_start=mqtt.MQTT_CLEAN_START_FIRST_ONLY, properties=ozellikler)
    client.loop_start()
    return client


def istemci_kapat(client):
    """Bağlantıyı kapatır ve broker'dan oturumu hemen silmesini ister."""
    ozellikler = Properties(PacketTypes.DISCONNECT)
    ozellikler.SessionExpiryInterval = 0
    client.disconnect(properties=ozellikler)
    client.loop_stop()


# ============================================================
# TEK BİR ÖLÇÜM
# ============================================================

def olcum_yap(senaryo, qos, tekrar, mesaj_sayisi, hiz):
    """Bir senaryo + QoS + tekrar için ölçüm yapar, sonuçları döndürür."""
    kimlik_eki = f"{senaryo['ad']}-q{qos}-t{tekrar}-{os.getpid()}"
    topic = f"deney/{kimlik_eki}"  # Her ölçüm kendi topic'ini kullanır, birbirine karışmaz

    # 1) Gerekirse ağ simülatörünü başlat. Tohum = tekrar numarası: aynı
    #    tekrardaki QoS 0, 1, 2 ölçümleri aynı kopma zamanlarını yaşar (adil kıyas).
    ag = None
    adres, port = ayarlar.BROKER_ADRESI, ayarlar.BROKER_PORTU
    if senaryo["ag"]:
        ag = AgSimulatoru(AG_SIMULATORU_PORTU, ayarlar.BROKER_ADRESI, ayarlar.BROKER_PORTU,
                          tohum=tekrar, **senaryo["ag"])
        ag.baslat()
        adres, port = "127.0.0.1", AG_SIMULATORU_PORTU

    # 2) Abone: gelen her mesajın gecikmesini kaydeder
    alinanlar = {}  # sıra numarası -> [gecikme_ms, gecikme_ms (kopya), ...]
    kilit = threading.Lock()
    abone_hazir = threading.Event()

    def mesaj_gelince(client, userdata, msg):
        varis = time.perf_counter()
        veri = json.loads(msg.payload)
        with kilit:
            alinanlar.setdefault(veri["sira"], []).append((varis - veri["t"]) * 1000)

    def abone_baglaninca(client, userdata, flags, reason_code, properties):
        if not reason_code.is_failure:
            # Oturum devam ediyorsa abonelik zaten vardır; tekrar abone olmak zararsızdır.
            client.subscribe(topic, qos=qos)

    abone = istemci_baglan(f"deney-abone-{kimlik_eki}", adres, port,
                           mesaj_gelince=mesaj_gelince, baglaninca=abone_baglaninca)
    abone.on_subscribe = lambda *args: abone_hazir.set()
    if not abone_hazir.wait(timeout=10):
        raise RuntimeError("Abone, aboneliği tamamlayamadı.")

    yayinci = istemci_baglan(f"deney-yayinci-{kimlik_eki}", adres, port)
    for _ in range(100):  # Bağlantıyı en fazla 10 sn bekle
        if yayinci.is_connected():
            break
        time.sleep(0.1)

    # 3) Mesajları sabit hızda gönder
    baslangic = time.perf_counter()
    for sira in range(mesaj_sayisi):
        hedef_an = baslangic + sira / hiz
        bekle = hedef_an - time.perf_counter()
        if bekle > 0:
            time.sleep(bekle)
        yuk = json.dumps({"sira": sira, "t": time.perf_counter()})
        yuk = yuk.ljust(YUK_BOYUTU)  # Sabit boyut için boşlukla doldur
        # Bağlantı yokken QoS 0 mesajı hemen atılır; QoS 1/2 kuyrukta bekletilir.
        yayinci.publish(topic, yuk, qos=qos)
    gonderim_bitti = time.perf_counter()

    # 4) Geciken mesajları bekle (QoS 1/2 kopmadan sonra yeniden gönderilir)
    while time.perf_counter() - gonderim_bitti < BOSALTMA_SURESI_S:
        with kilit:
            gelen = len(alinanlar)
        if gelen >= mesaj_sayisi:
            break
        # QoS 0'da kaybolan mesaj asla gelmez; kısa bekleyip bırak.
        if qos == 0 and time.perf_counter() - gonderim_bitti > 2:
            break
        time.sleep(0.1)
    time.sleep(0.5)  # Son anda gelebilecek kopyalar için kısa bir pay

    # 5) Temizlik
    istemci_kapat(yayinci)
    istemci_kapat(abone)
    kopma = 0
    if ag:
        ag.durdur()
        kopma = ag.kopma_sayisi

    # 6) Sonuçları hesapla
    with kilit:
        kopya = {s: len(g) - 1 for s, g in alinanlar.items()}
        ilk_gecikme = {s: g[0] for s, g in alinanlar.items()}
    gecikmeler = sorted(ilk_gecikme.values())
    alinan = len(gecikmeler)

    def yuzdelik(p):
        if not gecikmeler:
            return float("nan")
        return gecikmeler[min(len(gecikmeler) - 1, int(round(p / 100 * (len(gecikmeler) - 1))))]

    ozet = {
        "senaryo": senaryo["ad"],
        "qos": qos,
        "tekrar": tekrar,
        "gonderilen": mesaj_sayisi,
        "alinan": alinan,
        "kayip": mesaj_sayisi - alinan,
        "kayip_orani_yuzde": round(100 * (mesaj_sayisi - alinan) / mesaj_sayisi, 3),
        "kopya": sum(kopya.values()),
        "ortalama_ms": round(statistics.fmean(gecikmeler), 3) if gecikmeler else "",
        "medyan_ms": round(statistics.median(gecikmeler), 3) if gecikmeler else "",
        "p95_ms": round(yuzdelik(95), 3) if gecikmeler else "",
        "p99_ms": round(yuzdelik(99), 3) if gecikmeler else "",
        "en_buyuk_ms": round(gecikmeler[-1], 3) if gecikmeler else "",
        "baglanti_kopmasi": kopma,
        "gonderim_suresi_s": round(gonderim_bitti - baslangic, 2),
    }
    satirlar = [
        {"senaryo": senaryo["ad"], "qos": qos, "tekrar": tekrar, "sira": s,
         "alindi": int(s in ilk_gecikme),
         "gecikme_ms": round(ilk_gecikme[s], 4) if s in ilk_gecikme else "",
         "kopya": kopya.get(s, 0)}
        for s in range(mesaj_sayisi)
    ]
    return ozet, satirlar


# ============================================================
# ANA PROGRAM
# ============================================================

def port_acik_mi(adres, port):
    try:
        with socket.create_connection((adres, port), timeout=2):
            return True
    except OSError:
        return False


def csv_yaz(yol, satirlar):
    with open(yol, "w", newline="", encoding="utf-8") as f:
        yazici = csv.DictWriter(f, fieldnames=list(satirlar[0].keys()))
        yazici.writeheader()
        yazici.writerows(satirlar)


def main():
    parser = argparse.ArgumentParser(description="MQTT QoS 0/1/2 gecikme ve kayıp deneyi")
    parser.add_argument("--mesaj", type=int, default=500, help="Her ölçümde gönderilecek mesaj sayısı (varsayılan 500)")
    parser.add_argument("--hiz", type=float, default=50, help="Saniyede gönderilecek mesaj (varsayılan 50)")
    parser.add_argument("--tekrar", type=int, default=3, help="Her ölçümün tekrar sayısı (varsayılan 3)")
    parser.add_argument("--hizli", action="store_true", help="Hızlı deneme: 100 mesaj, 1 tekrar")
    args = parser.parse_args()
    if args.hizli:
        args.mesaj, args.tekrar = 100, 1

    if not port_acik_mi(ayarlar.BROKER_ADRESI, ayarlar.BROKER_PORTU):
        print("HATA: Broker'a ulaşılamadı. Önce 'mosquitto -c mosquitto.conf' çalıştırın.")
        return
    if port_acik_mi("127.0.0.1", AG_SIMULATORU_PORTU):
        print(f"HATA: {AG_SIMULATORU_PORTU} portu kullanımda. Başka bir deney çalışıyor olabilir.")
        return

    klasor = Path(__file__).parent / "sonuclar" / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    klasor.mkdir(parents=True)

    toplam = len(SENARYOLAR) * len(QOS_SEVIYELERI) * args.tekrar
    tahmini_dk = toplam * (args.mesaj / args.hiz + 4) / 60
    print(f"Deney başlıyor: {len(SENARYOLAR)} senaryo × {len(QOS_SEVIYELERI)} QoS × {args.tekrar} tekrar = "
          f"{toplam} ölçüm, her biri {args.mesaj} mesaj @ {args.hiz:g} mesaj/sn.")
    print(f"Tahmini süre: ~{tahmini_dk:.0f} dakika. Sonuçlar: {klasor}\n")

    ozetler, tum_satirlar = [], []
    sayac = 0
    for senaryo in SENARYOLAR:
        print(f"--- Senaryo: {senaryo['ad']} ({senaryo['aciklama']}) ---")
        for tekrar in range(1, args.tekrar + 1):
            for qos in QOS_SEVIYELERI:
                sayac += 1
                ozet, satirlar = olcum_yap(senaryo, qos, tekrar, args.mesaj, args.hiz)
                ozetler.append(ozet)
                tum_satirlar.extend(satirlar)
                print(f"[{sayac:>2}/{toplam}] QoS {qos} · tekrar {tekrar}:  "
                      f"alınan {ozet['alinan']}/{ozet['gonderilen']}  "
                      f"kayıp %{ozet['kayip_orani_yuzde']:<6g} kopya {ozet['kopya']:<3} "
                      f"medyan {ozet['medyan_ms'] or '-':>8} ms   p95 {ozet['p95_ms'] or '-':>8} ms   "
                      f"kopma {ozet['baglanti_kopmasi']}")
                # Ara sonuçları her ölçümde kaydet: deney yarıda kesilirse veri kaybolmasın
                csv_yaz(klasor / "ozet.csv", ozetler)
        print()

    csv_yaz(klasor / "olcumler.csv", tum_satirlar)
    bilgi = {
        "tarih": datetime.now().isoformat(timespec="seconds"),
        "mesaj_sayisi": args.mesaj,
        "hiz_mesaj_sn": args.hiz,
        "tekrar": args.tekrar,
        "yuk_boyutu_bayt": YUK_BOYUTU,
        "senaryolar": SENARYOLAR,
        "mqtt_surumu": "5",
        "paho_mqtt": version("paho-mqtt"),
        "python": platform.python_version(),
        "isletim_sistemi": platform.platform(),
    }
    (klasor / "deney_bilgisi.json").write_text(json.dumps(bilgi, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Bitti. Sonuçlar '{klasor}' klasöründe.")
    print("Grafikleri çizmek için:  python qos_grafik.py")


if __name__ == "__main__":
    main()
