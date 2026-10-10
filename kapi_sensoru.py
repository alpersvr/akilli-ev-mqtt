# kapi_sensoru.py
# ------------------------------------------------------------
# SANAL KAPI SENSÖRÜ (Publisher / Yayıncı)
#
# Gerçekte kapı kasasına takılan manyetik bir sensördür. Ara sıra
# kapı açılır, birkaç saniye sonra kapanır. Sadece durum
# DEĞİŞTİĞİNDE mesaj gönderir: {"durum": "acik"} veya {"durum": "kapali"}
# ------------------------------------------------------------

import random
import time

import ayarlar
import ortak

CIHAZ_ID = "giris-kapi-01"
ETIKET = "KAPI"

kapi_acik = False
kapanma_zamani = 0.0


def durumu_yayinla(client):
    durum = "acik" if kapi_acik else "kapali"
    ortak.json_yayinla(client, ayarlar.KAPI_TOPIC,
                       {"cihaz_id": CIHAZ_ID, "durum": durum}, retain=True)
    print(f"[{ETIKET}] Kapı {durum.upper()}")


def adim(client):
    """Her saniye çağrılır, kapının açılıp kapanmasına karar verir."""
    global kapi_acik, kapanma_zamani
    simdi = time.time()

    if not kapi_acik and random.random() < ayarlar.KAPI_ACILMA_OLASILIGI:
        # Kapı açıldı: 3-6 saniye açık kalacak.
        kapi_acik = True
        kapanma_zamani = simdi + random.uniform(3, 6)
        durumu_yayinla(client)

    elif kapi_acik and simdi >= kapanma_zamani:
        kapi_acik = False
        durumu_yayinla(client)


if __name__ == "__main__":
    client = ortak.istemci_olustur(CIHAZ_ID, ETIKET, baglaninca=durumu_yayinla)
    print(f"[{ETIKET}] Kapı olayları '{ayarlar.KAPI_TOPIC}' adresine bildirilecek. (Çıkış: Ctrl+C)")
    ortak.calistir(client, CIHAZ_ID, ETIKET, adim=adim, aralik=1)
