# ayarlar.py
# ------------------------------------------------------------
# Projedeki ortak ayarlar bu dosyada toplanır.
# Broker adresi, topic adları, otomasyon eşikleri gibi değerler
# değişirse sadece burayı düzenlemek yeterli olur; diğer dosyalar
# ayarları buradan okur.
# ------------------------------------------------------------

# ============================================================
# BROKER BAĞLANTISI
# ============================================================

# Mosquitto broker'ın çalıştığı bilgisayarın adresi.
# Broker kendi bilgisayarımızda olduğu için "localhost" kullanıyoruz.
BROKER_ADRESI = "localhost"

# MQTT'nin varsayılan (şifresiz) bağlantı portu 1883'tür.
BROKER_PORTU = 1883

# Broker, istemciden bu kadar saniye ses çıkmazsa bağlantının
# koptuğunu varsayar. paho bu süre içinde otomatik "ping" atar.
KEEPALIVE_SANIYE = 60

# Tarayıcılar doğrudan MQTT konuşamaz; WebSocket üzerinden bağlanırlar.
# Mosquitto bu porttan da dinler (bkz. mosquitto.conf). 3. aşamadaki panel kullanır.
WEBSOCKET_PORTU = 9001

# Panel web sayfasının yayınlanacağı port: http://localhost:8000
PANEL_PORTU = 8000

# Mesajların iletim garantisi seviyesi (0, 1 veya 2).
# 1 = mesaj en az bir kez ulaştırılır. 4. aşamada 0, 1 ve 2 karşılaştırılacak.
QOS = 1

# ============================================================
# TOPIC'LER (KONULAR)
# Düzen: ev/<oda>/<cihaz>
#   - Cihaz kendi DURUMUNU bu topic'e yayınlar.
#   - Eyleyiciler (lamba, klima, alarm) KOMUTLARI "<topic>/komut"
#     adresinden dinler. Ör: ev/salon/lamba/komut
# ============================================================

# Sensörler (sadece veri yayınlar)
SICAKLIK_TOPIC = "ev/salon/sicaklik"
HAREKET_TOPIC = "ev/salon/hareket"
KAPI_TOPIC = "ev/giris/kapi"

# Eyleyiciler (komut alır, durumunu yayınlar)
LAMBA_TOPIC = "ev/salon/lamba"
KLIMA_TOPIC = "ev/salon/klima"
ALARM_TOPIC = "ev/giris/alarm"

# Komut topic'i = cihaz topic'i + bu ek
KOMUT_EKI = "/komut"

# Her cihaz bağlanınca buraya "cevrimici" yazar. Beklenmedik şekilde
# koparsa broker otomatik olarak "cevrimdisi" yazar (Last Will özelliği).
# Ör: ev/sistem/baglanti/salon-lamba-01
BAGLANTI_TOPIC_KOKU = "ev/sistem/baglanti"

# Abonenin dinleyeceği topic filtresi.
# "#" joker karakteri "ev/" altındaki TÜM topic'leri kapsar.
ABONE_TOPIC = "ev/#"

# ============================================================
# SİMÜLASYON AYARLARI
# ============================================================

# Sıcaklık sensörünün kaç saniyede bir ölçüm göndereceği.
YAYIN_ARALIGI_SANIYE = 2

# Klima kapalıyken oda sıcaklığı yavaş yavaş bu değere yaklaşır.
# 30 = yaz senaryosu (klima soğutur). 12 yaparsanız kış senaryosu
# olur ve klimanın ısıtmaya geçtiğini görürsünüz.
DIS_SICAKLIK = 30.0

# Her saniye için "biri odaya girdi" olasılığı (0.05 = %5).
HAREKET_OLASILIGI = 0.05

# Kapı kapalıyken her saniye için "kapı açıldı" olasılığı (0.02 = %2).
KAPI_ACILMA_OLASILIGI = 0.02

# ============================================================
# OTOMASYON KURALLARI
# ============================================================

# Hareket bittikten kaç saniye sonra lamba kendiliğinden kapansın.
LAMBA_KAPANMA_SURESI = 15

# Klima eşikleri (°C). Başlama ve durma değerlerinin farklı olması
# (histerezis) klimanın sürekli aç-kapa yapmasını önler.
KLIMA_SOGUTMA_BASLA = 26.0   # bu değere çıkınca soğutmaya başla
KLIMA_SOGUTMA_DUR = 23.0     # bu değere inince soğutmayı kapat
KLIMA_ISITMA_BASLA = 19.0    # bu değere inince ısıtmaya başla
KLIMA_ISITMA_DUR = 22.0      # bu değere çıkınca ısıtmayı kapat
