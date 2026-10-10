# lamba.py
# ------------------------------------------------------------
# SANAL LAMBA (Eyleyici)
#
# "ev/salon/lamba/komut" adresinden {"durum": "acik"} veya
# {"durum": "kapali"} komutu bekler, durumunu "ev/salon/lamba"
# adresine yayınlar. Tüm işi eyleyici.py içindeki Eyleyici sınıfı yapar.
# ------------------------------------------------------------

import ayarlar
from eyleyici import Eyleyici

if __name__ == "__main__":
    lamba = Eyleyici(
        cihaz_id="salon-lamba-01",
        etiket="LAMBA",
        topic=ayarlar.LAMBA_TOPIC,
        gecerli_durumlar=["acik", "kapali"],
        baslangic_durumu="kapali",
    )
    lamba.calistir()
