# hareket_sensoru.py
# ------------------------------------------------------------
# SANAL HAREKET SENSÖRÜ (Publisher / Yayıncı)
#
# Gerçek PIR sensörleri gibi, odada hareket olup olmadığını bildirir.
# Rastgele aralıklarla "biri odaya giriyor", birkaç saniye hareket
# ediyor ve sonra hareket bitiyor. Sadece durum DEĞİŞTİĞİNDE mesaj
# gönderir: {"durum": "var"} veya {"durum": "yok"}
# ------------------------------------------------------------

import random
import time

import ayarlar
import ortak

CIHAZ_ID = "salon-hareket-01"
ETIKET = "HAREKET"

# Sensörün anlık durumu. Bu değişkenler fonksiyonlar arasında
# paylaşıldığı için dosyanın en üstünde (global olarak) tanımlı.
hareket_var = False
hareket_bitis_zamani = 0.0


def durumu_yayinla(client):
    durum = "var" if hareket_var else "yok"
    ortak.json_yayinla(client, ayarlar.HAREKET_TOPIC,
                       {"cihaz_id": CIHAZ_ID, "durum": durum}, retain=True)
    print(f"[{ETIKET}] Hareket {durum.upper()}")


def adim(client):
    """Her saniye çağrılır, hareket olup olmadığına karar verir."""
    global hareket_var, hareket_bitis_zamani
    simdi = time.time()

    if not hareket_var and random.random() < ayarlar.HAREKET_OLASILIGI:
        # Biri odaya girdi: 3-8 saniye boyunca hareket olacak.
        hareket_var = True
        hareket_bitis_zamani = simdi + random.uniform(3, 8)
        durumu_yayinla(client)

    elif hareket_var and simdi >= hareket_bitis_zamani:
        # Hareket süresi doldu.
        hareket_var = False
        durumu_yayinla(client)


if __name__ == "__main__":
    client = ortak.istemci_olustur(CIHAZ_ID, ETIKET, baglaninca=durumu_yayinla)
    print(f"[{ETIKET}] Hareketler '{ayarlar.HAREKET_TOPIC}' adresine bildirilecek. (Çıkış: Ctrl+C)")
    ortak.calistir(client, CIHAZ_ID, ETIKET, adim=adim, aralik=1)
