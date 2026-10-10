# otomasyon.py
# ------------------------------------------------------------
# OTOMASYON MERKEZİ (Hem Subscriber hem Publisher)
#
# Evin "beyni". Tüm sensörleri ve cihaz durumlarını dinler,
# aşağıdaki kurallara göre eyleyicilere komut gönderir:
#
#   KURAL 1 - Akıllı aydınlatma:
#       Hareket algılanırsa lambayı aç. Hareket bittikten
#       LAMBA_KAPANMA_SURESI saniye sonra lambayı kapat.
#
#   KURAL 2 - İklim kontrolü (histerezisli termostat):
#       Sıcaklık >= 26 °C  -> klima soğutmaya başlar, 23 °C'ye inince kapanır
#       Sıcaklık <= 19 °C  -> klima ısıtmaya başlar, 22 °C'ye çıkınca kapanır
#
#   KURAL 3 - Güvenlik:
#       Alarm "kurulu" iken kapı açılırsa veya hareket algılanırsa
#       alarmı çaldır.
#
# Cihazlar birbirini tanımaz; hepsi sadece broker ile konuşur.
# Kurallar tek bir yerde toplandığı için değiştirmek kolaydır.
# ------------------------------------------------------------

import threading
import time

import ayarlar
import ortak

CIHAZ_ID = "otomasyon-merkezi"
ETIKET = "OTOMASYON"

# Evin bilinen son durumu. None = o cihazdan henüz haber gelmedi
# (ör. program çalışmıyor). Bilinmeyen cihaza komut göndermiyoruz.
ev = {
    "lamba": None,
    "klima": None,
    "alarm": None,
    "hareket": "yok",
    # Lambanın kapanma sayacının başladığı an (hareket bitince veya lamba açılınca)
    "sayac_baslangic": 0.0,
}

# Mesajlar paho'nun arka plan iş parçacığında (thread), zamanlayıcı kontrolü
# ise ana programda çalışır. İkisi 'ev' sözlüğünü aynı anda değiştirmesin
# diye bir kilit (lock) kullanıyoruz: kilidi alan iş bitirene kadar diğeri bekler.
kilit = threading.Lock()


def komut_gonder(client, cihaz_topic, istenen_durum, sebep):
    """Bir eyleyiciye komut gönderir ve nedenini ekrana yazar."""
    print(f"[{ETIKET}] {sebep} -> {cihaz_topic}: {istenen_durum}")
    ortak.json_yayinla(client, cihaz_topic + ayarlar.KOMUT_EKI, {"durum": istenen_durum})


# ------------------------------------------------------------
# KURALLAR
# ------------------------------------------------------------

def hareket_degisti(client, durum, eski_mesaj):
    ev["hareket"] = durum
    if durum == "yok":
        # Hareket bitti: lambanın kapanma sayacını başlat.
        ev["sayac_baslangic"] = time.time()
        return

    # Broker'ın sakladığı (retain) eski bir mesajsa, bu yeni bir olay değildir.
    if eski_mesaj:
        return

    # KURAL 1: Hareket var ve lamba kapalı -> lambayı aç
    if ev["lamba"] == "kapali":
        komut_gonder(client, ayarlar.LAMBA_TOPIC, "acik", "KURAL 1: Hareket algılandı")

    # KURAL 3: Alarm kuruluyken hareket -> alarmı çaldır
    if ev["alarm"] == "kurulu":
        komut_gonder(client, ayarlar.ALARM_TOPIC, "caliyor", "KURAL 3: Alarm kuruluyken hareket!")


def kapi_degisti(client, durum, eski_mesaj):
    if durum != "acik" or eski_mesaj:
        return
    # KURAL 3: Alarm kuruluyken kapı açıldı -> alarmı çaldır
    if ev["alarm"] == "kurulu":
        komut_gonder(client, ayarlar.ALARM_TOPIC, "caliyor", "KURAL 3: Alarm kuruluyken kapı açıldı!")


def sicaklik_degisti(client, sicaklik):
    klima = ev["klima"]
    if klima is None or sicaklik is None:
        return  # Klima programı çalışmıyor ya da veri bozuk

    # KURAL 2: Histerezisli termostat
    if klima == "kapali":
        if sicaklik >= ayarlar.KLIMA_SOGUTMA_BASLA:
            komut_gonder(client, ayarlar.KLIMA_TOPIC, "sogutma", f"KURAL 2: Oda çok sıcak ({sicaklik} °C)")
        elif sicaklik <= ayarlar.KLIMA_ISITMA_BASLA:
            komut_gonder(client, ayarlar.KLIMA_TOPIC, "isitma", f"KURAL 2: Oda çok soğuk ({sicaklik} °C)")
    elif klima == "sogutma" and sicaklik <= ayarlar.KLIMA_SOGUTMA_DUR:
        komut_gonder(client, ayarlar.KLIMA_TOPIC, "kapali", f"KURAL 2: Oda yeterince soğudu ({sicaklik} °C)")
    elif klima == "isitma" and sicaklik >= ayarlar.KLIMA_ISITMA_DUR:
        komut_gonder(client, ayarlar.KLIMA_TOPIC, "kapali", f"KURAL 2: Oda yeterince ısındı ({sicaklik} °C)")


def lamba_degisti(durum):
    if durum == "acik" and ev["lamba"] != "acik":
        # Lamba (elle ya da otomatik) yeni açıldı: sayacı sıfırla ki
        # hareket olmasa bile hemen kapanmasın.
        ev["sayac_baslangic"] = time.time()
    ev["lamba"] = durum


# ------------------------------------------------------------
# MQTT OLAYLARI
# ------------------------------------------------------------

def mesaj_gelince(client, userdata, msg):
    """Dinlenen topic'lerden herhangi birine mesaj gelince çağrılır."""
    veri = ortak.json_coz(msg)
    if veri is None:
        return

    # msg.retain = True ise bu mesaj broker'ın sakladığı eski bir durumdur
    # (biz bağlanmadan önce yayınlanmış).
    with kilit:
        if msg.topic == ayarlar.HAREKET_TOPIC:
            hareket_degisti(client, veri.get("durum"), msg.retain)
        elif msg.topic == ayarlar.KAPI_TOPIC:
            kapi_degisti(client, veri.get("durum"), msg.retain)
        elif msg.topic == ayarlar.SICAKLIK_TOPIC:
            sicaklik_degisti(client, veri.get("sicaklik"))
        elif msg.topic == ayarlar.LAMBA_TOPIC:
            lamba_degisti(veri.get("durum"))
        elif msg.topic == ayarlar.KLIMA_TOPIC:
            ev["klima"] = veri.get("durum")
        elif msg.topic == ayarlar.ALARM_TOPIC:
            ev["alarm"] = veri.get("durum")


def zamanlayici_kontrol(client):
    """Her saniye çağrılır. KURAL 1'in 'süre doldu, lambayı kapat' kısmı."""
    with kilit:
        gecen = time.time() - ev["sayac_baslangic"]
        if ev["lamba"] == "acik" and ev["hareket"] == "yok" and gecen >= ayarlar.LAMBA_KAPANMA_SURESI:
            komut_gonder(client, ayarlar.LAMBA_TOPIC, "kapali",
                         f"KURAL 1: {ayarlar.LAMBA_KAPANMA_SURESI} sn hareket yok")
            # Komut tekrar tekrar gönderilmesin diye sayacı yeniden başlat.
            ev["sayac_baslangic"] = time.time()


if __name__ == "__main__":
    client = ortak.istemci_olustur(
        CIHAZ_ID,
        ETIKET,
        abonelikler=[
            ayarlar.SICAKLIK_TOPIC,
            ayarlar.HAREKET_TOPIC,
            ayarlar.KAPI_TOPIC,
            ayarlar.LAMBA_TOPIC,
            ayarlar.KLIMA_TOPIC,
            ayarlar.ALARM_TOPIC,
        ],
        mesaj_gelince=mesaj_gelince,
    )
    print(f"[{ETIKET}] Kurallar etkin:\n"
          f"  KURAL 1: Hareket -> lamba açık, {ayarlar.LAMBA_KAPANMA_SURESI} sn hareketsizlik -> kapalı\n"
          f"  KURAL 2: >= {ayarlar.KLIMA_SOGUTMA_BASLA} °C soğut (<= {ayarlar.KLIMA_SOGUTMA_DUR} °C dur), "
          f"<= {ayarlar.KLIMA_ISITMA_BASLA} °C ısıt (>= {ayarlar.KLIMA_ISITMA_DUR} °C dur)\n"
          f"  KURAL 3: Alarm kuruluyken kapı/hareket -> alarm çalar")
    ortak.calistir(client, CIHAZ_ID, ETIKET, adim=zamanlayici_kontrol, aralik=1)
