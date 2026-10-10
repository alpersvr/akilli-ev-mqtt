# klima.py
# ------------------------------------------------------------
# SANAL KLİMA (Eyleyici)
#
# "ev/salon/klima/komut" adresinden {"durum": "sogutma"},
# {"durum": "isitma"} veya {"durum": "kapali"} komutu bekler.
# Durumunu "ev/salon/klima" adresine yayınlar.
#
# Klimanın odayı gerçekten soğutması/ısıtması sicaklik_sensoru.py
# içinde simüle edilir: sensör klimanın durumunu dinler ve sıcaklığı
# buna göre değiştirir.
# ------------------------------------------------------------

import ayarlar
from eyleyici import Eyleyici

if __name__ == "__main__":
    klima = Eyleyici(
        cihaz_id="salon-klima-01",
        etiket="KLIMA",
        topic=ayarlar.KLIMA_TOPIC,
        gecerli_durumlar=["kapali", "sogutma", "isitma"],
        baslangic_durumu="kapali",
    )
    klima.calistir()
