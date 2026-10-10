# alarm.py
# ------------------------------------------------------------
# SANAL ALARM (Eyleyici)
#
# Üç durumu vardır:
#   devre_disi : Alarm kapalı, hiçbir şeye tepki vermez
#   kurulu     : Evden çıkılmış; kapı açılır veya hareket olursa
#                otomasyon alarmı çaldırır
#   caliyor    : Siren çalıyor; "devre_disi" komutu gelene kadar susmaz
#
# Komut örneği (ev/giris/alarm/komut): {"durum": "kurulu"}
# ------------------------------------------------------------

import ayarlar
from eyleyici import Eyleyici


class Alarm(Eyleyici):
    """
    Eyleyici sınıfının özel bir türü. Ondan farklı olarak,
    çalarken ekrana birkaç saniyede bir siren uyarısı yazar.
    """

    def __init__(self):
        super().__init__(
            cihaz_id="giris-alarm-01",
            etiket="ALARM",
            topic=ayarlar.ALARM_TOPIC,
            gecerli_durumlar=["devre_disi", "kurulu", "caliyor"],
            baslangic_durumu="devre_disi",
        )
        self.sayac = 0

    def adim(self, client):
        # Her saniye çağrılır; çalıyorsa 3 saniyede bir uyarı yaz.
        if self.durum == "caliyor":
            if self.sayac % 3 == 0:
                print("[ALARM] *** SİREN ÇALIYOR! *** "
                      "(susturmak için 'devre_disi' komutu gönderin)")
            self.sayac += 1
        else:
            self.sayac = 0


if __name__ == "__main__":
    Alarm().calistir()
