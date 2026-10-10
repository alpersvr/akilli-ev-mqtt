# eyleyici.py
# ------------------------------------------------------------
# EYLEYİCİ (ACTUATOR) ŞABLONU
#
# Sensörler ortamı ÖLÇER (sıcaklık, hareket...). Eyleyiciler ise
# ortamı DEĞİŞTİRİR (lamba yakar, klima soğutur, alarm çalar).
#
# Lamba, klima ve alarm aynı şekilde çalışır:
#   1. "<topic>/komut" adresinden komut bekler, ör. {"durum": "acik"}
#   2. Komut geçerliyse durumunu değiştirir
#   3. Yeni durumunu "<topic>" adresine yayınlar
#
# Bu ortak davranışı bir kez burada, bir "sınıf" (class) olarak yazıyoruz.
# lamba.py, klima.py ve alarm.py bu sınıfı kullanır.
# ------------------------------------------------------------

import ayarlar
import ortak


class Eyleyici:
    def __init__(self, cihaz_id, etiket, topic, gecerli_durumlar, baslangic_durumu):
        """
        cihaz_id         : Benzersiz cihaz adı, ör. "salon-lamba-01"
        etiket           : Ekranda görünecek kısa ad, ör. "LAMBA"
        topic            : Durumun yayınlanacağı topic, ör. "ev/salon/lamba"
        gecerli_durumlar : Kabul edilen durumlar, ör. ["acik", "kapali"]
        baslangic_durumu : Program açıldığındaki durum
        """
        self.cihaz_id = cihaz_id
        self.etiket = etiket
        self.topic = topic
        self.komut_topic = topic + ayarlar.KOMUT_EKI
        self.gecerli_durumlar = gecerli_durumlar
        self.durum = baslangic_durumu

        self.client = ortak.istemci_olustur(
            cihaz_id,
            etiket,
            abonelikler=[self.komut_topic],
            mesaj_gelince=self._komut_gelince,
            # Bağlanır bağlanmaz mevcut durumu duyur.
            baglaninca=lambda client: self.durumu_yayinla(),
        )

    def durumu_yayinla(self):
        """Mevcut durumu (retain ile) yayınlar."""
        ortak.json_yayinla(self.client, self.topic,
                           {"cihaz_id": self.cihaz_id, "durum": self.durum},
                           retain=True)

    def _komut_gelince(self, client, userdata, msg):
        """Komut topic'ine mesaj gelince paho bu fonksiyonu çağırır."""
        veri = ortak.json_coz(msg)
        istenen = veri.get("durum") if veri else None

        if istenen not in self.gecerli_durumlar:
            print(f"[{self.etiket}] Geçersiz komut yok sayıldı: {msg.payload.decode('utf-8', 'replace')}"
                  f"  (geçerli durumlar: {', '.join(self.gecerli_durumlar)})")
            return

        eski = self.durum
        self.durum = istenen
        if eski != istenen:
            self.durum_degisti(eski, istenen)
        # Durum aynı kalsa bile yayınlıyoruz: komutu gönderen,
        # komutunun işlendiğini böylece anlar.
        self.durumu_yayinla()

    def durum_degisti(self, eski, yeni):
        """Durum değişince çağrılır. Alt sınıflar farklı bir şey yazdırabilir."""
        print(f"[{self.etiket}] {eski} -> {yeni}")

    def adim(self, client):
        """Her saniye çağrılır. Varsayılan olarak bir şey yapmaz (alarm bunu kullanır)."""
        pass

    def calistir(self):
        """Cihazı başlatır; Ctrl+C'ye kadar çalışır."""
        print(f"[{self.etiket}] Başlangıç durumu: {self.durum}. "
              f"Komutlar '{self.komut_topic}' adresinden bekleniyor. (Çıkış: Ctrl+C)")
        ortak.calistir(self.client, self.cihaz_id, self.etiket, adim=self.adim, aralik=1)
