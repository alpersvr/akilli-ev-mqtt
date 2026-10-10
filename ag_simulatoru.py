# ag_simulatoru.py
# ------------------------------------------------------------
# AĞ SİMÜLATÖRÜ (TCP vekil / proxy)
#
# Sorun: Bilgisayarın kendi içinde (localhost) ağ kusursuzdur. Mesajlar
# 1 ms'den kısa sürede ulaşır ve hiç kaybolmaz. Bu ortamda QoS 0, 1, 2
# arasında fark görülmez.
#
# Çözüm: İstemciler broker'a doğrudan değil, bu programın açtığı bir
# "ara kapıya" bağlanır. Program aradaki trafiği broker'a aktarırken:
#   - Her veri parçasını belirli bir süre bekleterek GECİKME ekler,
#   - Rastgele anlarda tüm bağlantıları aniden keserek KOPMA yaratır
#     (Wi-Fi'nin bir anlığına gitmesi gibi).
#
#       istemci  <-->  [ AgSimulatoru :1885 ]  <-->  broker :1883
#
# Not: MQTT, TCP üzerinde çalışır ve TCP tek tek paket kaybını kendisi
# düzeltir. Bu yüzden MQTT'de kayıp gerçekte BAĞLANTI KOPTUĞUNDA olur.
# Simülatör de kaybı bu şekilde oluşturuyor.
# ------------------------------------------------------------

import asyncio
import random
import threading


class AgSimulatoru:
    def __init__(self, dinleme_portu, hedef_adres, hedef_port,
                 gecikme_ms=0.0, sapma_ms=0.0, ortalama_kopma_s=None, tohum=None):
        """
        dinleme_portu    : İstemcilerin bağlanacağı port (ör. 1885)
        hedef_adres/port : Gerçek broker'ın adresi (ör. localhost:1883)
        gecikme_ms       : Her yönde eklenecek ortalama gecikme (milisaniye)
        sapma_ms         : Gecikmeye eklenecek rastgele oynama (± milisaniye)
        ortalama_kopma_s : Bağlantılar ortalama kaç saniyede bir kopsun (None = hiç)
        tohum            : Rastgele sayı tohumu. Aynı tohum = aynı kopma zamanları.
                           Böylece her QoS seviyesi aynı ağ koşullarında denenir.
        """
        self.dinleme_portu = dinleme_portu
        self.hedef_adres = hedef_adres
        self.hedef_port = hedef_port
        self.gecikme_s = gecikme_ms / 1000
        self.sapma_s = sapma_ms / 1000
        self.ortalama_kopma_s = ortalama_kopma_s
        self.kopma_sayisi = 0

        # İki ayrı rastgele sayı üreteci: kopma zamanları sadece tohuma bağlı
        # kalsın, kaç veri parçası gönderildiğinden etkilenmesin.
        self._kopma_rastgele = random.Random(tohum)
        self._gecikme_rastgele = random.Random(tohum)

        self._dongu = None
        self._durdur_olayi = None
        self._is_parcacigi = None
        self._baglantilar = set()  # Açık (istemci, broker) bağlantı çiftleri

    # ---------- Dışarıdan kullanılan iki fonksiyon ----------

    def baslat(self):
        """Simülatörü arka planda başlatır ve hazır olmasını bekler."""
        hazir = threading.Event()
        self._is_parcacigi = threading.Thread(target=lambda: asyncio.run(self._ana(hazir)), daemon=True)
        self._is_parcacigi.start()
        if not hazir.wait(timeout=5):
            raise RuntimeError("Ağ simülatörü başlatılamadı.")

    def durdur(self):
        """Tüm bağlantıları kapatır ve simülatörü durdurur."""
        if self._dongu:
            self._dongu.call_soon_threadsafe(self._durdur_olayi.set)
            self._is_parcacigi.join(timeout=5)

    # ---------- İç işleyiş (asyncio ile) ----------
    # asyncio: Tek bir iş parçacığında birçok bağlantıyı aynı anda
    # yönetmeyi sağlayan Python kütüphanesi. "await" gördüğünüz yerlerde
    # program beklerken diğer bağlantıların işlerine geçer.

    async def _ana(self, hazir):
        self._dongu = asyncio.get_running_loop()
        self._durdur_olayi = asyncio.Event()
        sunucu = await asyncio.start_server(self._yeni_baglanti, "127.0.0.1", self.dinleme_portu)

        kesici = None
        if self.ortalama_kopma_s:
            kesici = asyncio.create_task(self._kesici())

        hazir.set()
        async with sunucu:
            await self._durdur_olayi.wait()
            if kesici:
                kesici.cancel()
            self._hepsini_kes()

    async def _yeni_baglanti(self, istemci_okuyucu, istemci_yazici):
        """Bir istemci bağlanınca çağrılır: broker'a ikinci bir bağlantı açar."""
        try:
            broker_okuyucu, broker_yazici = await asyncio.open_connection(self.hedef_adres, self.hedef_port)
        except OSError:
            istemci_yazici.transport.abort()
            return

        cift = (istemci_yazici, broker_yazici)
        self._baglantilar.add(cift)
        try:
            # İki yönü aynı anda aktar: istemci -> broker ve broker -> istemci
            await asyncio.gather(
                self._aktar(istemci_okuyucu, broker_yazici),
                self._aktar(broker_okuyucu, istemci_yazici),
                return_exceptions=True,
            )
        finally:
            self._baglantilar.discard(cift)
            for yazici in cift:
                yazici.transport.abort()

    async def _aktar(self, okuyucu, yazici):
        """
        Bir yöndeki veriyi gecikmeli olarak aktarır. Okunan her veri parçası
        "teslim zamanı" ile bir kuyruğa konur; ayrı bir görev zamanı gelince
        karşı tarafa yazar. Sıra hiçbir zaman bozulmaz (TCP'de olduğu gibi).
        """
        kuyruk = asyncio.Queue()

        async def gonderici():
            while True:
                teslim_zamani, veri = await kuyruk.get()
                if veri is None:
                    return
                bekleme = teslim_zamani - self._dongu.time()
                if bekleme > 0:
                    await asyncio.sleep(bekleme)
                yazici.write(veri)
                await yazici.drain()

        gonderme_gorevi = asyncio.create_task(gonderici())
        son_teslim = 0.0
        try:
            while veri := await okuyucu.read(65536):
                gecikme = max(0.0, self.gecikme_s + self._gecikme_rastgele.uniform(-self.sapma_s, self.sapma_s))
                # Önceki parçadan önce teslim edilmesin (sıra korunur)
                son_teslim = max(self._dongu.time() + gecikme, son_teslim)
                kuyruk.put_nowait((son_teslim, veri))
            # Karşı taraf bağlantıyı düzgünce kapattı: kuyruktakileri teslim et
            kuyruk.put_nowait((0.0, None))
            await gonderme_gorevi
            yazici.transport.abort()
        finally:
            gonderme_gorevi.cancel()

    async def _kesici(self):
        """Rastgele aralıklarla tüm bağlantıları aniden keser."""
        while True:
            # Üstel dağılım: "ortalama X saniyede bir" olan rastgele olaylar için
            # kullanılan standart dağılım (ör. arıza, ağ kopması).
            await asyncio.sleep(self._kopma_rastgele.expovariate(1 / self.ortalama_kopma_s))
            if self._baglantilar:
                self.kopma_sayisi += 1
                self._hepsini_kes()

    def _hepsini_kes(self):
        for istemci_yazici, broker_yazici in list(self._baglantilar):
            # abort(): bağlantıyı "hoşça kal" demeden, aniden kopar
            istemci_yazici.transport.abort()
            broker_yazici.transport.abort()
