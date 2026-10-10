# sicaklik_sensoru.py
# ------------------------------------------------------------
# SANAL SICAKLIK SENSÖRÜ (Publisher / Yayıncı)
#
# Gerçek bir sensör yerine, gerçekçi sıcaklık değerleri üreten
# bir program. Belirli aralıklarla ölçümü MQTT broker'a gönderir.
#
# 2. aşamada eklenen: Sensör aynı zamanda klimanın durumunu dinler.
# Böylece simülasyonda "oda fiziği" de olur:
#   - Klima kapalı  -> oda yavaş yavaş dış sıcaklığa yaklaşır
#   - Klima soğutma -> oda soğur
#   - Klima ısıtma  -> oda ısınır
# ------------------------------------------------------------

import random

import ayarlar
import ortak

# Bu cihazın benzersiz adı. Broker her istemciyi bu kimlikle tanır.
CIHAZ_ID = "salon-sicaklik-01"
ETIKET = "SICAKLIK"

sicaklik = 24.0          # Başlangıç sıcaklığı
klima_durumu = "kapali"  # Klimadan haber gelene kadar kapalı varsayıyoruz


def klima_mesaji_gelince(client, userdata, msg):
    """Klima durumunu yayınladığında çağrılır; son durumu not ederiz."""
    global klima_durumu
    veri = ortak.json_coz(msg)
    if veri and "durum" in veri:
        klima_durumu = veri["durum"]


def sonraki_sicaklik(simdiki, klima):
    """
    Bir sonraki ölçüm değerini hesaplar. Küçük rastgele bir 'gürültü'
    ekleyerek değerlerin gerçek bir sensör gibi biraz oynamasını sağlar.
    """
    gurultu = random.uniform(-0.1, 0.1)

    if klima == "sogutma":
        degisim = -0.4
    elif klima == "isitma":
        degisim = +0.4
    else:
        # Klima kapalıyken fark ne kadar büyükse o kadar hızlı ısınır/soğur.
        degisim = (ayarlar.DIS_SICAKLIK - simdiki) * 0.05

    yeni = simdiki + degisim + gurultu
    yeni = max(10.0, min(40.0, yeni))  # Değeri makul bir aralıkta tut
    return round(yeni, 1)              # Virgülden sonra 1 basamak


def adim(client):
    """Her YAYIN_ARALIGI_SANIYE saniyede bir çağrılır: ölç ve yayınla."""
    global sicaklik
    sicaklik = sonraki_sicaklik(sicaklik, klima_durumu)

    # Mesajı JSON formatında hazırlayıp yayınla. retain=True sayesinde
    # sonradan bağlanan programlar son ölçümü hemen alır.
    metin = ortak.json_yayinla(client, ayarlar.SICAKLIK_TOPIC,
                               {"cihaz_id": CIHAZ_ID, "sicaklik": sicaklik, "birim": "C"},
                               retain=True)
    print(f"[{ETIKET}] Gönderildi -> {ayarlar.SICAKLIK_TOPIC}: {metin}")


# Bu dosya doğrudan çalıştırıldığında (python sicaklik_sensoru.py) burası çalışır.
if __name__ == "__main__":
    client = ortak.istemci_olustur(
        CIHAZ_ID,
        ETIKET,
        abonelikler=[ayarlar.KLIMA_TOPIC],
        mesaj_gelince=klima_mesaji_gelince,
    )
    print(f"[{ETIKET}] Her {ayarlar.YAYIN_ARALIGI_SANIYE} saniyede bir "
          f"'{ayarlar.SICAKLIK_TOPIC}' adresine veri gönderilecek. (Çıkış: Ctrl+C)")
    ortak.calistir(client, CIHAZ_ID, ETIKET, adim=adim, aralik=ayarlar.YAYIN_ARALIGI_SANIYE)
