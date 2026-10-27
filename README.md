# MQTT Tabanlı Akıllı Ev Simülasyonu

Donanım kullanmadan, tüm cihazları Python ile simüle eden MQTT tabanlı bir akıllı ev projesi.
Broker olarak yerel **Mosquitto**, istemci kütüphanesi olarak **paho-mqtt** (2.x) kullanılır.

| Aşama | İçerik | Durum |
|---|---|---|
| 1 | Sanal sıcaklık sensörü + ekrana yazan abone | ✅ |
| 2 | Kapı, hareket, lamba, klima, alarm + otomasyon kuralları | ✅ |
| 3 | Tarayıcıda izleme ve kontrol paneli | ✅ |
| 4 | QoS 0/1/2 gecikme ve kayıp deneyi + grafikler | ✅ |

## Mimari

```
  SENSÖRLER (ölçer)                                    EYLEYİCİLER (değiştirir)
  sicaklik_sensoru.py ─┐                          ┌──> lamba.py
  hareket_sensoru.py  ─┼──>  MOSQUITTO BROKER  <──┼──> klima.py
  kapi_sensoru.py     ─┘          ▲     │         └──> alarm.py
                                  │     ▼
                     otomasyon.py (kurallar)    abone.py (izleme ekranı)
                                  ▲
                                  │ WebSocket (port 9001)
                        Tarayıcıdaki panel (panel/)
```

Tarayıcıdaki panel de ayrı bir MQTT istemcisidir. Broker'a WebSocket üzerinden bağlanır, diğer programlarla aynı topic'leri kullanır.

Hiçbir program diğerini doğrudan tanımaz. Herkes sadece broker ile konuşur.
Sensörler veriyi yayınlar. Otomasyon bu veriyi dinler, kurallara göre eyleyicilere komut gönderir.
Eyleyiciler komutu uygulayıp yeni durumlarını yayınlar.

## Topic (konu) düzeni

| Topic | Kim yayınlar | Örnek içerik |
|---|---|---|
| `ev/salon/sicaklik` | Sıcaklık sensörü | `{"sicaklik": 24.5, "birim": "C", ...}` |
| `ev/dis/sicaklik` | Sıcaklık sensörü (dış ortam) | `{"sicaklik": 30.2, "birim": "C", ...}` |
| `ev/salon/hareket` | Hareket sensörü | `{"durum": "var"}` / `"yok"` |
| `ev/giris/kapi` | Kapı sensörü | `{"durum": "acik"}` / `"kapali"` |
| `ev/salon/lamba` | Lamba | `{"durum": "acik"}` / `"kapali"` |
| `ev/salon/klima` | Klima | `{"durum": "kapali"}` / `"sogutma"` / `"isitma"` |
| `ev/giris/alarm` | Alarm | `{"durum": "devre_disi"}` / `"kurulu"` / `"caliyor"` |
| `ev/salon/lamba/komut` | Otomasyon / kullanıcı | `{"durum": "acik"}` |
| `ev/salon/klima/komut` | Otomasyon / kullanıcı | `{"durum": "sogutma"}` |
| `ev/giris/alarm/komut` | Otomasyon / kullanıcı | `{"durum": "kurulu"}` |
| `ev/sistem/baglanti/<cihaz_id>` | Her cihaz / broker | `cevrimici` / `cevrimdisi` |

Kullanılan MQTT özellikleri:

- **Retain:** Durum mesajları broker'da saklanır. Sonradan bağlanan bir program (ör. 3. aşamadaki panel) son durumu hemen öğrenir.
- **Last Will (LWT):** Bir cihaz beklenmedik şekilde koparsa broker onun yerine `cevrimdisi` yayınlar.
- **Joker karakter `#`:** `abone.py`, `ev/#` ile evdeki tüm mesajları tek abonelikle alır.

## Otomasyon kuralları (`otomasyon.py`)

| Kural | Koşul | Eylem |
|---|---|---|
| 1. Akıllı aydınlatma | Hareket algılandı | Lambayı aç |
| | 15 sn boyunca hareket yok | Lambayı kapat |
| 2. İklim kontrolü | Sıcaklık ≥ 26 °C | Klima soğutma (23 °C'ye inince kapanır) |
| | Sıcaklık ≤ 19 °C | Klima ısıtma (22 °C'ye çıkınca kapanır) |
| 3. Güvenlik | Alarm kuruluyken kapı açıldı veya hareket var | Alarmı çaldır |

Sıcaklık sensörü klimanın durumunu da dinler. Klima soğuttuğunda oda gerçekten soğur, kapandığında dış sıcaklığa doğru yeniden ısınır.
Bu sayede ekranda kapalı döngü bir termostat davranışı görülür. Tüm eşikler `ayarlar.py` içinden değiştirilebilir.

## Dosyalar

| Dosya | Ne işe yarar? |
|---|---|
| `ayarlar.py` | Broker adresi, topic adları, olasılıklar, kural eşikleri. **Tüm ayarlar burada.** |
| `ortak.py` | Herkesin kullandığı yardımcılar: istemci oluşturma, JSON gönderme/çözme, ana döngü, düzgün kapanış. |
| `eyleyici.py` | Lamba/klima/alarm için ortak şablon (sınıf): komut dinle → durumu değiştir → durumu yayınla. |
| `sicaklik_sensoru.py` | 2 sn'de bir salon ve dış ortam sıcaklığını yayınlar. Klimanın etkisini simüle eder. |
| `hareket_sensoru.py` | Rastgele zamanlarda "biri odaya girdi" olayı üretir. |
| `kapi_sensoru.py` | Rastgele zamanlarda kapının açılıp kapanmasını üretir. |
| `lamba.py` | Sanal lamba (açık/kapalı). |
| `klima.py` | Sanal klima (kapalı/soğutma/ısıtma). |
| `alarm.py` | Sanal alarm (devre dışı/kurulu/çalıyor). Çalarken siren uyarısı yazar. |
| `otomasyon.py` | Evin beyni: tüm sensörleri dinler, kurallara göre komut gönderir. |
| `abone.py` | İzleme ekranı: `ev/#` altındaki tüm mesajları hizalı biçimde yazar. |
| `mosquitto.conf` | Projeye özel broker ayarı: 1883 (Python) ve 9001 (WebSocket, panel) portları. |
| `panel.py` | Paneli http://localhost:8000 adresinde yayınlar, tarayıcıyı açar, `ayarlar.py`'yi sayfaya `/ayarlar.json` olarak verir. |
| `panel/index.html` | Panelin yapısı: kartlar, yazılar, düğmeler. |
| `panel/panel.css` | Panelin görünümü (açık/koyu tema, telefon uyumu). |
| `panel/panel.js` | Panelin davranışı: MQTT bağlantısı, ekranı güncelleme, grafik, düğmelerden komut gönderme. |
| `panel/mqtt.min.js` | Tarayıcı için hazır MQTT kütüphanesi (mqtt.js 5.10.1). Projeye kopyalandığı için internet gerekmez. Elle düzenlenmez. |
| `hepsini_baslat.py` | 7 programı (abone hariç) tek komutla başlatır, Ctrl+C ile hepsini kapatır. |
| `ag_simulatoru.py` | Deney için ağ simülatörü: istemci ile broker arasına girip gecikme ekler ve bağlantıyı rastgele koparır. |
| `qos_deneyi.py` | QoS 0/1/2 deneyini yürütür, sonuçları `sonuclar/<tarih-saat>/` klasörüne CSV olarak yazar. |
| `qos_grafik.py` | Deney sonuçlarından grafikleri ve özet tabloyu üretir. |
| `requirements.txt` | Gerekli Python kütüphaneleri (`paho-mqtt`, `matplotlib`). |

## Kurulum (bir kez yapılır)

```bash
cd ~/akilli-ev-mqtt
python3 -m venv .venv                 # sanal ortam oluştur
source .venv/bin/activate             # sanal ortamı etkinleştir
pip install -r requirements.txt       # paho-mqtt'yi kur
```

## Çalıştırma

**Terminal 1: Broker (proje ayarlarıyla)**

```bash
cd ~/akilli-ev-mqtt
mosquitto -c mosquitto.conf -v
```

`-c mosquitto.conf` olmadan da Python programları çalışır, ancak panelin kullandığı WebSocket portu (9001) açılmaz.

**Terminal 2: İzleme ekranı**

```bash
cd ~/akilli-ev-mqtt && source .venv/bin/activate
python abone.py
```

**Terminal 3: Tüm ev**

```bash
cd ~/akilli-ev-mqtt && source .venv/bin/activate
python hepsini_baslat.py
```

**Terminal 4: Panel**

```bash
cd ~/akilli-ev-mqtt && source .venv/bin/activate
python panel.py
```

Tarayıcı kendiliğinden açılır. Açılmazsa adres çubuğuna http://localhost:8000 yazın.
Terminal 2'deki izleme ekranı isteğe bağlıdır; panelde de bir olay günlüğü vardır.

İsterseniz programları tek tek de çalıştırabilirsiniz (`python lamba.py`, `python otomasyon.py` ...). Her biri bağımsızdır.

Durdurmak için ilgili terminalde **Ctrl+C**.

## Panelde neler var?

- **Salon iklimi:** Anlık sıcaklık ve son 3 dakikanın grafiği. Grafikte otomasyon eşikleri ve klimanın çalıştığı anlar (alttaki mavi/turuncu şerit) görünür. Klima modu buradan değiştirilebilir.
- **Aydınlatma:** Lambayı aç/kapat, hareket durumu, lambanın kaç saniye sonra kapanacağı. "Hareket simüle et" düğmesi sensör adına 4 sn'lik bir hareket olayı yayınlar.
- **Güvenlik:** Alarmı kur / devre dışı bırak, kapı durumu, "Kapı açılmasını simüle et".
- **Cihazlar:** Last Will mesajlarından oluşan çevrimiçi/çevrimdışı listesi. Bir cihazı kapatırsanız ilgili kartta kırmızı "Çevrimdışı" etiketi çıkar.
- **Olay günlüğü:** Gelen tüm MQTT mesajları. Komutlar mavi satırla vurgulanır, kaynağı (panel, simülasyon) parantez içinde yazar.

**Demo önerisi:** Paneli açın → "Kur" ile alarmı kurun → "Hareket simüle et" düğmesine basın. Lamba yanar, alarm çalar ve olay günlüğünde zincirin tamamı görünür: sensör → otomasyon komutu → eyleyici durumu.

**Not:** Panelden verilen komut otomasyon kurallarına ters düşerse otomasyon onu düzeltir. Örneğin oda 24 °C'deyken klimayı ısıtmaya alırsanız, bir sonraki ölçümde otomasyon klimayı kapatır (ısıtma 22 °C'de durur).

## Elle komut gönderme (ayrı bir terminalden)

```bash
# Alarmı kur (evden çıktınız) -> kapı açılınca veya hareket olunca çalar
mosquitto_pub -t ev/giris/alarm/komut -m '{"durum":"kurulu"}'

# Alarmı sustur / devre dışı bırak
mosquitto_pub -t ev/giris/alarm/komut -m '{"durum":"devre_disi"}'

# Lambayı elle aç (15 sn hareket olmazsa otomasyon kapatır)
mosquitto_pub -t ev/salon/lamba/komut -m '{"durum":"acik"}'

# Sahte bir hareket olayı gönder (sensörü taklit et)
mosquitto_pub -t ev/salon/hareket -m '{"durum":"var"}'
```

**Kış senaryosu:** `ayarlar.py` içinde `DIS_SICAKLIK = 12.0` yapıp programları yeniden başlatın. Klimanın ısıtmaya geçtiğini görürsünüz.

## Sık karşılaşılan hatalar

| Hata | Çözüm |
|---|---|
| `HATA: Broker'a bağlanılamadı/ulaşılamadı` | Terminal 1'de `mosquitto -c mosquitto.conf -v` çalışıyor olmalı. |
| Panelde "Broker bağlantısı yok" yazıyor | Mosquitto `-c mosquitto.conf` olmadan başlatılmış; WebSocket portu kapalı. Kapatıp ayar dosyasıyla yeniden başlatın. |
| Panel açılıyor ama boş/eski görünüyor | Sayfayı yenileyin (Cmd+R). `ayarlar.py`'yi değiştirdiyseniz `panel.py`'yi yeniden başlatın. |
| `8000 portu kullanımda` | Panel zaten açık; ikinci kez başlatmaya gerek yok. |
| `ModuleNotFoundError: No module named 'paho'` | Sanal ortam etkin değil. `source .venv/bin/activate` komutunu çalıştırın. |
| `Address already in use` (mosquitto başlatırken) | Broker zaten çalışıyor (muhtemelen `brew services` ile). Tekrar başlatmaya gerek yok. |
| Bir program sürekli "Bağlantı koptu" yazıyor | Aynı programı iki kez açmış olabilirsiniz. Aynı `cihaz_id` ile bağlanan ikinci istemci ilkini düşürür. |
| Kod değiştirdim ama davranış değişmedi | Çalışan programlar eski kodla devam eder. Ctrl+C ile kapatıp yeniden başlatın. |

## 4. aşama: QoS deneyi

### Ne ölçülüyor?

Bir yayıncı sabit hızda (varsayılan 50 mesaj/sn) 500 mesaj gönderir, bir abone bunları alır. Her mesajın içinde sıra numarası ve gönderildiği an yazılıdır.

| Ölçüt | Tanım |
|---|---|
| Gecikme | Mesajın gönderildiği andan abonenin onu aldığı ana kadar geçen süre (uçtan uca). |
| Kayıp | Gönderilip hiç ulaşmayan mesajların oranı. |
| Kopya | Aynı mesajın birden fazla kez ulaşması. |

Yayıncı ve abone aynı programda çalışır. İkisi de aynı saati kullandığı için gecikme mikrosaniye hassasiyetle ölçülür.

### Ağ senaryoları

Bilgisayarın kendi içindeki (localhost) ağ kusursuzdur. Bu ortamda üç QoS seviyesi arasında kayıp farkı görülmez. Bu yüzden `ag_simulatoru.py` istemcilerle broker arasına girer:

| Senaryo | Koşul |
|---|---|
| İdeal | Doğrudan bağlantı |
| Gecikmeli | Her yönde 40 ± 10 ms gecikme (yavaş bir mobil ağ gibi) |
| Kesintili | Gecikme + ortalama 3 sn'de bir bağlantının aniden kopması (Wi-Fi'nin gidip gelmesi gibi) |

MQTT, TCP üzerinde çalışır ve TCP tek tek kaybolan paketleri kendisi yeniden gönderir. Bu yüzden MQTT'de gerçek kayıp **bağlantı koptuğunda** oluşur; simülatör de kaybı bu şekilde yaratır.
Aynı tekrardaki QoS 0, 1 ve 2 ölçümleri aynı rastgele tohumla, yani **aynı anlarda kopan bağlantılarla** yapılır; karşılaştırma adildir.

Deneyde MQTT 5 ve kalıcı oturum (persistent session) kullanılır. Bağlantı koptuğunda broker aboneliği ve teslim edilemeyen QoS 1/2 mesajlarını saklar. QoS'un vaat ettiği güvence ancak böyle çalışır.

### Çalıştırma

Ölçümün temiz olması için önce evin programlarını (`hepsini_baslat.py`, panel) kapatın. Broker'ı `-v` **olmadan** başlatın, çünkü binlerce satır log yazmak ölçümü yavaşlatır:

```bash
# Terminal 1
cd ~/akilli-ev-mqtt
mosquitto -c mosquitto.conf

# Terminal 2
cd ~/akilli-ev-mqtt && source .venv/bin/activate
pip install -r requirements.txt          # matplotlib için bir kez
python qos_deneyi.py                     # ~7 dakika (3 senaryo × 3 QoS × 3 tekrar)
python qos_grafik.py                     # grafikleri ve tabloyu üretir
```

Seçenekler:
- `python qos_deneyi.py --hizli`: 100 mesaj, 1 tekrar; yaklaşık 1 dakikada biter, denemek için.
- `--mesaj 1000 --hiz 100 --tekrar 5`: daha uzun ve daha güvenilir ölçüm.

### Çıktılar (`sonuclar/<tarih-saat>/`)

| Dosya | İçerik |
|---|---|
| `olcumler.csv` | Her mesaj için bir satır: senaryo, QoS, tekrar, sıra, ulaştı mı, gecikme, kopya sayısı |
| `ozet.csv` | Her ölçüm için bir satır: kayıp, kopya, ortalama/medyan/p95/p99 gecikme, kopma sayısı |
| `deney_bilgisi.json` | Deney parametreleri ve yazılım sürümleri (raporda "deney ortamı" için) |
| `1_kayip_orani.png` | Senaryo ve QoS'a göre kayıp oranı |
| `2_gecikme_dagilimi.png` | Gecikme dağılımı (kutu grafiği) |
| `3_gecikme_cdf.png` | Mesajların yüzde kaçının ne kadar sürede ulaştığı; eğrinin tavanı kayıbı da gösterir |
| `ozet.md` | Rapora kopyalanabilecek özet tablo |

### Beklenen sonuçlar (ve nedenleri)

| | QoS 0 | QoS 1 | QoS 2 |
|---|---|---|---|
| Garanti | En fazla bir kez | En az bir kez | Tam olarak bir kez |
| El sıkışma | Yok (PUBLISH) | 2 adım (PUBLISH → PUBACK) | 4 adım (PUBLISH → PUBREC → PUBREL → PUBCOMP) |
| Gecikmeli ağda gecikme | ≈ 2 × tek yön gecikmesi | QoS 0 ile aynı (broker PUBACK'i beklemeden iletir) | ≈ 3 katı (broker mesajı PUBREL gelince iletir, abone tarafında da aynı) |
| Kopmada kayıp | Var | Yok | Yok |
| Kopmada kopya | Yok | **Olabilir** | Yok |
| Kopmada gecikme kuyruğu | Yok (mesaj zaten kaybolur) | Uzun (yeniden bağlanmayı bekler) | Uzun |

### Deney sırasında bulunan bir sorun: QoS 2'de sessiz kayıp

İlk denemelerde QoS 2, kesintili ağda mesajların %14–26'sını **kaybetti**. QoS 2'nin garantisine göre bu olmamalıydı. Broker'ın ayrıntılı loglarında kaybolan her mesaj için şu satır görüldü:

```
Sending PUBREC to deney-yayinci-... (m68, rc151)     ← 151 = 0x97 "Quota exceeded"
```

**Neden?** Mosquitto, varsayılan olarak bir istemcinin aynı anda en fazla **20** onay bekleyen QoS 1/2 mesajı göndermesine izin verir (`max_inflight_messages 20`). paho-mqtt 2.1.0, bağlantı kopup yeniden kurulunca biriken mesajların hepsini aynı anda gönderiyor. Kütüphanenin `_messages_reconnect_reset_out` fonksiyonunda sayacı artıran satır yorum satırı haline getirilmiş. Broker 20'yi aşan mesajları reddediyor; paho ise bu ret kodunu kontrol etmeden mesajı "teslim edildi" sayıyor. MQTT 3.1.1 ile deneyince sorun daha da büyüdü, çünkü bu sürümde broker reddi bildirecek bir koda sahip değil.

**Çözüm:** `mosquitto.conf` içinde `max_inflight_messages 0` (sınırsız). Bu ayarla QoS 2 tüm denemelerde **kayıpsız ve kopyasız** çalıştı.

**Ders:** Protokolün verdiği garanti, ancak broker ve istemci kütüphanesi birbiriyle uyumlu çalıştığında geçerlidir. QoS 2 kullanmak tek başına "mesaj kaybolmaz" demek değildir; yapılandırma ve kütüphane davranışı da test edilmelidir.
