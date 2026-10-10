# ortak.py
# ------------------------------------------------------------
# TÜM CİHAZLARIN KULLANDIĞI ORTAK MQTT YARDIMCILARI
#
# Her cihaz programı broker'a bağlanmak, JSON mesaj göndermek,
# Ctrl+C ile düzgün kapanmak gibi aynı işleri yapar. Bu kodu her
# dosyaya ayrı ayrı yazmak yerine burada bir kez yazıp her yerden
# kullanıyoruz. Bir hata düzeltilecekse tek bir yerden düzeltilir.
# ------------------------------------------------------------

import json
import time
from datetime import datetime

import paho.mqtt.client as mqtt

import ayarlar


def zaman_damgasi():
    """Şu anki zamanı '2026-10-10T16:10:46' biçiminde döndürür."""
    return datetime.now().isoformat(timespec="seconds")


def baglanti_topic(cihaz_id):
    """Cihazın çevrimiçi/çevrimdışı bilgisinin yazıldığı topic."""
    return f"{ayarlar.BAGLANTI_TOPIC_KOKU}/{cihaz_id}"


def istemci_olustur(cihaz_id, etiket, abonelikler=(), mesaj_gelince=None, baglaninca=None,
                    baglanti_bildir=True):
    """
    Ayarları yapılmış bir MQTT istemcisi oluşturur ve döndürür.

    cihaz_id        : Broker'ın bu istemciyi tanıdığı benzersiz ad. DİKKAT: Aynı
                      ad ile ikinci bir istemci bağlanırsa broker ilkini düşürür!
    etiket          : Ekrana yazarken başa eklenecek kısa ad, ör. "LAMBA"
    abonelikler     : Bağlanınca abone olunacak topic'lerin listesi
    mesaj_gelince   : Mesaj gelince çağrılacak fonksiyon (isteğe bağlı)
    baglaninca      : Bağlantı kurulunca ek olarak çağrılacak fonksiyon (isteğe bağlı)
    baglanti_bildir : True ise çevrimiçi/çevrimdışı bilgisi yayınlanır. Evin
                      cihazları için True, izleme ekranları için False kullanırız.
    """
    # userdata: istemciye iliştirilen ve sonradan okunabilen küçük bir not.
    # calistir() fonksiyonu kapanışta bu bilgiye bakar.
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cihaz_id,
                         userdata={"baglanti_bildir": baglanti_bildir})

    if baglanti_bildir:
        # LAST WILL (son vasiyet): Cihaz beklenmedik şekilde koparsa
        # (program çöker, ağ gider...) broker bu mesajı bizim yerimize yayınlar.
        # retain=True: Broker bu mesajı saklar, sonradan abone olan da görür.
        client.will_set(baglanti_topic(cihaz_id), "cevrimdisi", qos=ayarlar.QOS, retain=True)

    def _baglaninca(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"[{etiket}] Bağlantı reddedildi, sebep: {reason_code}")
            return
        print(f"[{etiket}] Broker'a bağlandı: {ayarlar.BROKER_ADRESI}:{ayarlar.BROKER_PORTU}")
        if baglanti_bildir:
            client.publish(baglanti_topic(cihaz_id), "cevrimici", qos=ayarlar.QOS, retain=True)

        # Abonelikler burada yapılır: bağlantı kopup yeniden kurulursa
        # abonelikler de otomatik olarak yenilenmiş olur.
        for topic in abonelikler:
            client.subscribe(topic, qos=ayarlar.QOS)
            print(f"[{etiket}] '{topic}' dinleniyor.")

        if baglaninca:
            baglaninca(client)

    def _kopunca(client, userdata, flags, reason_code, properties):
        # Normal kapanışta (bizim disconnect() çağrımız) bir şey yazmıyoruz.
        if reason_code.is_failure:
            print(f"[{etiket}] Bağlantı koptu ({reason_code}). Yeniden bağlanılıyor...")

    client.on_connect = _baglaninca
    client.on_disconnect = _kopunca
    if mesaj_gelince:
        client.on_message = mesaj_gelince
    return client


def json_yayinla(client, topic, veri, retain=False):
    """
    Bir sözlüğü (dict) zaman damgası ekleyerek JSON metnine çevirir ve yayınlar.

    retain=True ise broker bu topic'teki SON mesajı saklar. Böylece sonradan
    bağlanan bir program (ör. 3. aşamadaki panel) cihazın güncel durumunu
    hemen öğrenir. Durum mesajlarında True, komutlarda False kullanıyoruz.
    """
    veri = {**veri, "zaman": zaman_damgasi()}
    metin = json.dumps(veri, ensure_ascii=False)
    client.publish(topic, metin, qos=ayarlar.QOS, retain=retain)
    return metin


def json_coz(msg):
    """
    Gelen MQTT mesajının içeriğini sözlüğe (dict) çevirir.
    İçerik geçerli bir JSON nesnesi değilse None döndürür.
    """
    try:
        veri = json.loads(msg.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return veri if isinstance(veri, dict) else None


def calistir(client, cihaz_id, etiket, adim=None, aralik=1.0):
    """
    Programın ana döngüsü. Broker'a bağlanır, Ctrl+C'ye basılana kadar
    her 'aralik' saniyede bir 'adim(client)' fonksiyonunu çağırır,
    sonunda bağlantıyı düzgünce kapatır.
    """
    try:
        client.connect(ayarlar.BROKER_ADRESI, ayarlar.BROKER_PORTU, ayarlar.KEEPALIVE_SANIYE)
    except ConnectionRefusedError:
        print(f"[{etiket}] HATA: Broker'a bağlanılamadı. Mosquitto çalışıyor mu?")
        return

    # Ağ trafiğini arka planda yöneten döngüyü başlat.
    client.loop_start()

    # Bağlantının tamamlanmasını en fazla 5 saniye bekle.
    for _ in range(50):
        if client.is_connected():
            break
        time.sleep(0.1)

    try:
        while True:
            if adim:
                adim(client)
            time.sleep(aralik)
    except KeyboardInterrupt:
        # Kullanıcı Ctrl+C'ye bastığında buraya düşeriz.
        print(f"\n[{etiket}] Durduruluyor...")
    finally:
        # Normal kapanışta Last Will gönderilmez; bu yüzden "cevrimdisi"
        # bilgisini kendimiz yayınlıyoruz ve iletilmesini bekliyoruz.
        if client.user_data_get()["baglanti_bildir"]:
            bilgi = client.publish(baglanti_topic(cihaz_id), "cevrimdisi", qos=ayarlar.QOS, retain=True)
            if bilgi.rc == mqtt.MQTT_ERR_SUCCESS:
                bilgi.wait_for_publish(timeout=2)
        # Önce bağlantıyı kapat, sonra arka plan döngüsünü durdur.
        client.disconnect()
        client.loop_stop()
        print(f"[{etiket}] Bağlantı kapatıldı.")
