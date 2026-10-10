# QoS deneyi özet tablosu

| Senaryo | QoS | Kayıp % (ort.) | Kayıp % (min–maks) | Kopya (ort.) | Medyan (ms) | p95 (ms) | p99 (ms) | Kopma (ort.) |
|---|---|---|---|---|---|---|---|---|
| İdeal ağ | 0 | 0.00 | 0.00–0.00 | 0.0 | 0.63 | 0.94 | 1.13 | 0.0 |
| İdeal ağ | 1 | 0.00 | 0.00–0.00 | 0.0 | 0.80 | 1.24 | 1.49 | 0.0 |
| İdeal ağ | 2 | 0.00 | 0.00–0.00 | 0.0 | 1.42 | 2.00 | 2.45 | 0.0 |
| Gecikmeli ağ | 0 | 0.00 | 0.00–0.00 | 0.0 | 83.05 | 96.83 | 100.81 | 0.0 |
| Gecikmeli ağ | 1 | 0.00 | 0.00–0.00 | 0.0 | 82.01 | 94.82 | 99.01 | 0.0 |
| Gecikmeli ağ | 2 | 0.00 | 0.00–0.00 | 0.0 | 252.88 | 273.27 | 281.79 | 0.0 |
| Kesintili ağ | 0 | 15.80 | 9.80–21.80 | 0.0 | 82.68 | 96.38 | 100.88 | 2.0 |
| Kesintili ağ | 1 | 0.00 | 0.00–0.00 | 6.5 | 84.81 | 916.46 | 1162.40 | 2.0 |
| Kesintili ağ | 2 | 0.00 | 0.00–0.00 | 0.0 | 256.18 | 1289.15 | 1386.95 | 2.0 |

Gecikme yüzdelikleri tüm tekrarlardaki mesajlar birleştirilerek hesaplanmıştır. Kayıp ve kopya değerleri tekrarların ortalamasıdır.
