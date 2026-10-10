# abone.py
# ------------------------------------------------------------
# ABONE / İZLEYİCİ (Subscriber)
#
# Broker'a bağlanır, "ev/#" topic'ine abone olur ve evdeki TÜM
# mesajları (sensör verileri, cihaz durumları, komutlar, bağlantı
# bilgileri) ekrana okunaklı biçimde yazar. Sistemde neler olduğunu
# izlemek için kullanılır; hiçbir şeyi kontrol etmez.
# ------------------------------------------------------------

import os
from datetime import datetime

import ayarlar
import ortak

# Aynı anda birden fazla izleme ekranı açılabilsin diye kimliğe programın
# süreç numarasını (PID) ekliyoruz. Kimlikler aynı olsaydı broker her yeni
# bağlananda eskisini düşürürdü.
CIHAZ_ID = f"ekran-abone-{os.getpid()}"
ETIKET = "ABONE"


def mesaj_gelince(client, userdata, msg):
    """
    Abone olunan topic'e her mesaj geldiğinde paho bu fonksiyonu çağırır.
    msg.topic   -> mesajın geldiği topic (ör. ev/salon/sicaklik)
    msg.payload -> mesajın içeriği (bayt olarak gelir)
    msg.retain  -> True ise broker'ın sakladığı eski (son bilinen) mesajdır
    """
    simdi = datetime.now().strftime("%H:%M:%S")
    veri = ortak.json_coz(msg)

    # Mesajın içeriğini türüne göre kısa ve okunaklı hale getir.
    if veri is None:
        # JSON değil (ör. "cevrimici" gibi düz metin)
        icerik = msg.payload.decode("utf-8", "replace")
    elif "sicaklik" in veri:
        icerik = f"{veri['sicaklik']} °{veri.get('birim', 'C')}"
    elif "durum" in veri:
        icerik = veri["durum"]
    else:
        icerik = str(veri)

    if msg.topic.endswith(ayarlar.KOMUT_EKI):
        icerik = f"KOMUT: {icerik}"
    if msg.retain:
        icerik += "  (kayıtlı son durum)"

    # :<32 -> topic adını 32 karakterlik alana sola yaslayarak yaz (hizalı görünsün)
    print(f"[{simdi}] {msg.topic:<32} {icerik}")


if __name__ == "__main__":
    client = ortak.istemci_olustur(
        CIHAZ_ID,
        ETIKET,
        abonelikler=[ayarlar.ABONE_TOPIC],
        mesaj_gelince=mesaj_gelince,
        baglanti_bildir=False,  # İzleme ekranı evin bir cihazı değil
    )
    print(f"[{ETIKET}] Mesajlar bekleniyor... (Çıkış: Ctrl+C)")
    ortak.calistir(client, CIHAZ_ID, ETIKET)
