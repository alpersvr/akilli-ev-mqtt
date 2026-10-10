# qos_grafik.py
# ------------------------------------------------------------
# QoS DENEYİ GRAFİKLERİ VE ÖZET TABLOSU
#
# qos_deneyi.py'nin ürettiği CSV dosyalarını okur ve aynı klasöre şunları yazar:
#   1_kayip_orani.png       Senaryo ve QoS'a göre mesaj kaybı (%)
#   2_gecikme_dagilimi.png  Gecikme dağılımı (kutu grafiği)
#   3_gecikme_cdf.png       "Mesajların yüzde kaçı X ms içinde ulaştı?" eğrisi
#   ozet.md                 Rapora kopyalanabilecek özet tablo
#
# Kullanım:
#   python qos_grafik.py                       -> en son deneyin klasörü
#   python qos_grafik.py sonuclar/2026-10-10_17-03-55
# ------------------------------------------------------------

import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Ekran açmadan doğrudan dosyaya çiz
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

# ============================================================
# GÖRÜNÜM AYARLARI
# Renkler renk körlüğüne uygunluğu doğrulanmış bir paletten alınmıştır:
# her QoS seviyesinin rengi her grafikte aynıdır.
# ============================================================

QOS_RENK = {0: "#2a78d6", 1: "#eb6834", 2: "#1baf7a"}  # mavi, turuncu, yeşil-mavi
QOS_AD = {
    0: "QoS 0 · en fazla bir kez",
    1: "QoS 1 · en az bir kez",
    2: "QoS 2 · tam olarak bir kez",
}
SENARYO_AD = {"ideal": "İdeal ağ", "gecikmeli": "Gecikmeli ağ", "kesintili": "Kesintili ağ"}

ZEMIN = "#fcfcfb"
MURKEKKEP = "#0b0b0b"   # ana yazı rengi
IKINCIL = "#52514e"     # eksen yazıları
IZGARA = "#e1e0d9"      # ızgara çizgileri
EKSEN = "#c3c2b7"       # eksen çizgisi

plt.rcParams.update({
    "figure.facecolor": ZEMIN,
    "axes.facecolor": ZEMIN,
    "savefig.facecolor": ZEMIN,
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 10,
    "text.color": MURKEKKEP,
    "axes.labelcolor": IKINCIL,
    "axes.titlesize": 11,
    "axes.titleweight": "bold",
    "axes.titlecolor": MURKEKKEP,
    "axes.edgecolor": EKSEN,
    "axes.linewidth": 0.8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.color": IZGARA,
    "grid.linewidth": 0.8,
    "xtick.color": IKINCIL,
    "ytick.color": IKINCIL,
    "xtick.major.size": 0,
    "ytick.major.size": 0,
    "legend.frameon": False,
})


# ============================================================
# VERİYİ OKUMA
# ============================================================

def klasor_bul():
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    sonuclar = Path(__file__).parent / "sonuclar"
    klasorler = sorted(p for p in sonuclar.glob("*") if (p / "olcumler.csv").exists())
    if not klasorler:
        sys.exit("HATA: Sonuç bulunamadı. Önce 'python qos_deneyi.py' çalıştırın.")
    return klasorler[-1]


def csv_oku(yol):
    with open(yol, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def yuzdelik(sirali, p):
    """Sıralı listede p. yüzdelik değeri (ör. p=95 -> değerlerin %95'i bundan küçük)."""
    if not sirali:
        return float("nan")
    return sirali[min(len(sirali) - 1, int(round(p / 100 * (len(sirali) - 1))))]


def veriyi_hazirla(klasor):
    ozet = csv_oku(klasor / "ozet.csv")
    olcumler = csv_oku(klasor / "olcumler.csv")

    senaryolar = list(dict.fromkeys(s["senaryo"] for s in ozet))  # sırayı koru
    qoslar = sorted({int(s["qos"]) for s in ozet})

    # Her (senaryo, qos) için: tekrarların kayıp oranları, kopya ve kopma sayıları
    tekrarlar = defaultdict(list)
    for s in ozet:
        tekrarlar[(s["senaryo"], int(s["qos"]))].append(s)

    # Her (senaryo, qos) için: tüm tekrarlardaki mesajların gecikmeleri (birleştirilmiş)
    gecikmeler = defaultdict(list)
    gonderilen = defaultdict(int)
    for o in olcumler:
        anahtar = (o["senaryo"], int(o["qos"]))
        gonderilen[anahtar] += 1
        if o["alindi"] == "1":
            gecikmeler[anahtar].append(float(o["gecikme_ms"]))
    for g in gecikmeler.values():
        g.sort()

    return senaryolar, qoslar, tekrarlar, gecikmeler, gonderilen


# ============================================================
# GRAFİKLER
# ============================================================

def lejant_ekle(sekil, qoslar):
    tutamaclar = [plt.Line2D([], [], color=QOS_RENK[q], linewidth=6) for q in qoslar]
    sekil.legend(tutamaclar, [QOS_AD[q] for q in qoslar], loc="upper center",
                 ncol=len(qoslar), bbox_to_anchor=(0.5, 0.94), fontsize=9, handlelength=1.2)


def kayip_grafigi(klasor, senaryolar, qoslar, tekrarlar):
    sekil, eksen = plt.subplots(figsize=(8, 4.4))
    genislik = 0.26
    en_yuksek = 0
    for j, q in enumerate(qoslar):
        for i, s in enumerate(senaryolar):
            oranlar = [float(t["kayip_orani_yuzde"]) for t in tekrarlar[(s, q)]]
            ort = statistics.fmean(oranlar)
            x = i + (j - (len(qoslar) - 1) / 2) * genislik
            # edgecolor=zemin: yan yana çubuklar arasında ince bir boşluk bırakır
            eksen.bar(x, ort, genislik, color=QOS_RENK[q], edgecolor=ZEMIN, linewidth=1.5)
            if ort == 0:
                # Sıfır yükseklikli çubuk görünmez; rengi belli olsun diye tabana ince bir çizgi çek
                eksen.plot([x - genislik * 0.42, x + genislik * 0.42], [0, 0], color=QOS_RENK[q],
                           linewidth=3, solid_capstyle="butt", zorder=3)
            if len(oranlar) > 1 and max(oranlar) > min(oranlar):
                # İnce dikey çizgi: tekrarlar arasındaki en düşük-en yüksek aralık
                eksen.plot([x, x], [min(oranlar), max(oranlar)], color=MURKEKKEP, linewidth=1)
            en_yuksek = max(en_yuksek, max(oranlar))
            etiket = "%0" if ort == 0 else f"%{ort:.1f}"
            eksen.annotate(etiket, (x, max(oranlar)), xytext=(0, 4), textcoords="offset points",
                           ha="center", fontsize=8.5, color=IKINCIL)

    eksen.set_xticks(range(len(senaryolar)), [SENARYO_AD.get(s, s) for s in senaryolar])
    eksen.set_ylabel("Kaybolan mesajlar (%)")
    eksen.set_ylim(0, max(5, en_yuksek * 1.18))
    eksen.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"%{v:g}"))
    eksen.grid(axis="x", visible=False)
    sekil.suptitle("Mesaj kaybı oranı", x=0.06, ha="left", fontweight="bold", fontsize=12)
    lejant_ekle(sekil, qoslar)
    sekil.text(0.06, 0.01, "Çubuk: tekrarların ortalaması · ince çizgi: tekrarlar arasındaki en düşük–en yüksek değer",
               fontsize=8, color=IKINCIL)
    sekil.tight_layout(rect=(0, 0.03, 1, 0.89))
    sekil.savefig(klasor / "1_kayip_orani.png", dpi=200)
    plt.close(sekil)


def kutu_grafigi(klasor, senaryolar, qoslar, gecikmeler):
    sekil, eksenler = plt.subplots(1, len(senaryolar), figsize=(10, 4.2))
    for eksen, s in zip(eksenler, senaryolar):
        veriler = [gecikmeler[(s, q)] for q in qoslar]
        kutular = eksen.boxplot(
            veriler, positions=range(len(qoslar)), widths=0.55, whis=(5, 95), showfliers=False,
            patch_artist=True, medianprops={"color": MURKEKKEP, "linewidth": 1.5},
            whiskerprops={"color": IKINCIL, "linewidth": 1}, capprops={"color": IKINCIL, "linewidth": 1},
        )
        for kutu, q in zip(kutular["boxes"], qoslar):
            kutu.set_facecolor(QOS_RENK[q])
            kutu.set_alpha(0.85)
            kutu.set_edgecolor(ZEMIN)
        # Medyan değeri, QoS adının altına yazılır (grafiğin içinde çakışma olmasın)
        etiketler = [f"QoS {q}\n{statistics.median(v):.3g} ms" if v else f"QoS {q}"
                     for q, v in zip(qoslar, veriler)]
        eksen.set_xticks(range(len(qoslar)), etiketler)
        eksen.set_title(SENARYO_AD.get(s, s), loc="left")
        eksen.set_ylim(bottom=0)
        eksen.grid(axis="x", visible=False)
    eksenler[0].set_ylabel("Uçtan uca gecikme (ms)")
    sekil.suptitle("Gecikme dağılımı", x=0.06, ha="left", fontweight="bold", fontsize=12)
    lejant_ekle(sekil, qoslar)
    sekil.text(0.06, 0.01, "Kutu: mesajların ortadaki %50'si · kalın çizgi ve QoS adının altındaki sayı: medyan · "
                           "bıyıklar: %5–%95 aralığı · her panelin dikey ekseni kendi ölçeğindedir", fontsize=8, color=IKINCIL)
    sekil.tight_layout(rect=(0, 0.03, 1, 0.89))
    sekil.savefig(klasor / "2_gecikme_dagilimi.png", dpi=200)
    plt.close(sekil)


def cdf_grafigi(klasor, senaryolar, qoslar, gecikmeler, gonderilen):
    sekil, eksenler = plt.subplots(1, len(senaryolar), figsize=(10, 4.2), sharey=True)
    for eksen, s in zip(eksenler, senaryolar):
        for q in qoslar:
            g = gecikmeler[(s, q)]
            n = gonderilen[(s, q)]
            if not g:
                continue
            # y = bu gecikmeye kadar ulaşan mesajların GÖNDERİLENLERE oranı.
            # Kayıp mesajlar hiç ulaşmadığı için eğri %100'e çıkamaz: tavan = 100 - kayıp.
            y = [100 * (i + 1) / n for i in range(len(g))]
            eksen.step(g, y, where="post", color=QOS_RENK[q], linewidth=2)
            if y[-1] < 99.95:
                # Kayıp varsa eğrinin tavanını yaz (kaç mesaj hiç ulaşmadı)
                eksen.annotate(f"%{y[-1]:.1f} ulaştı", (g[-1], y[-1]), xytext=(-4, 8), textcoords="offset points",
                               ha="right", va="bottom", fontsize=8.5, color=IKINCIL)
        eksen.set_xscale("log")
        eksen.xaxis.set_major_locator(LogLocator(base=10, subs=(1, 2, 5)))
        eksen.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        eksen.xaxis.set_minor_formatter(NullFormatter())
        eksen.set_title(SENARYO_AD.get(s, s), loc="left")
        eksen.set_xlabel("Gecikme (ms, logaritmik)")
        eksen.set_ylim(0, 104)
        eksen.margins(x=0.12)
    eksenler[0].set_ylabel("Ulaşan mesajlar (%)")
    eksenler[0].yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"%{v:g}"))
    sekil.suptitle("Mesajların yüzde kaçı, ne kadar sürede ulaştı?", x=0.06, ha="left", fontweight="bold", fontsize=12)
    lejant_ekle(sekil, qoslar)
    sekil.text(0.06, 0.01, "Eğrinin bittiği yükseklik = ulaşan mesaj oranı (100 − kayıp). "
                           "Sağa uzanan kuyruk = bağlantı kopmasında bekleyip sonradan ulaşan mesajlar.",
               fontsize=8, color=IKINCIL)
    sekil.tight_layout(rect=(0, 0.03, 1, 0.89))
    sekil.savefig(klasor / "3_gecikme_cdf.png", dpi=200)
    plt.close(sekil)


# ============================================================
# ÖZET TABLO
# ============================================================

def ozet_tablosu(klasor, senaryolar, qoslar, tekrarlar, gecikmeler):
    satirlar = [
        "| Senaryo | QoS | Kayıp % (ort.) | Kayıp % (min–maks) | Kopya (ort.) | Medyan (ms) | p95 (ms) | p99 (ms) | Kopma (ort.) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in senaryolar:
        for q in qoslar:
            t = tekrarlar[(s, q)]
            kayip = [float(x["kayip_orani_yuzde"]) for x in t]
            kopya = statistics.fmean(int(x["kopya"]) for x in t)
            kopma = statistics.fmean(int(x["baglanti_kopmasi"]) for x in t)
            g = gecikmeler[(s, q)]
            satirlar.append(
                f"| {SENARYO_AD.get(s, s)} | {q} | {statistics.fmean(kayip):.2f} | {min(kayip):.2f}–{max(kayip):.2f} | "
                f"{kopya:.1f} | {statistics.median(g):.2f} | {yuzdelik(g, 95):.2f} | {yuzdelik(g, 99):.2f} | {kopma:.1f} |"
            )
    tablo = "\n".join(satirlar)
    (klasor / "ozet.md").write_text(
        "# QoS deneyi özet tablosu\n\n" + tablo + "\n\n"
        "Gecikme yüzdelikleri tüm tekrarlardaki mesajlar birleştirilerek hesaplanmıştır. "
        "Kayıp ve kopya değerleri tekrarların ortalamasıdır.\n",
        encoding="utf-8",
    )
    return tablo


def main():
    klasor = klasor_bul()
    senaryolar, qoslar, tekrarlar, gecikmeler, gonderilen = veriyi_hazirla(klasor)

    kayip_grafigi(klasor, senaryolar, qoslar, tekrarlar)
    kutu_grafigi(klasor, senaryolar, qoslar, gecikmeler)
    cdf_grafigi(klasor, senaryolar, qoslar, gecikmeler, gonderilen)
    tablo = ozet_tablosu(klasor, senaryolar, qoslar, tekrarlar, gecikmeler)

    print(tablo)
    print(f"\nGrafikler ve tablo '{klasor}' klasörüne kaydedildi:")
    for dosya in ["1_kayip_orani.png", "2_gecikme_dagilimi.png", "3_gecikme_cdf.png", "ozet.md"]:
        print(f"  - {dosya}")


if __name__ == "__main__":
    main()
