# Backtest sonuçları (Adım 6)

`python -m backtest` tarafından üretilir; elle düzenlenmez. Tasarım: `docs/adim-5-6-tasarim.md`.

Modeller: M0 = V1 (aralık ~ Normal), M1 = BG/NBD, M3 = MBG/NBD; ciro tahmininde sepet M2 (Gamma-Gamma).

- Senaryo başına 20 tohum × 2000 müşteri; gözlem 730 gün, kalibrasyon ilk 547.5 gün (18 ay), bekleme son 182.5 gün (6 ay).
- Değerlendirmeye kalibrasyon sonundan önce edinilmiş müşteriler girer. Etiket: kalibrasyon sonunda gerçekten hayatta mı.
- Değerler tohumlar üzerinden ortalama ± standart sapma.

## Varsayımlar (belgede sayısı verilmeyen değerler)

- BG/NBD gerçek parametreleri (S0; S1/S2/S4/S5'te bırakma Beta'sı, S3'te λ Gamma'sı): katalogdaki berber profili, r = 3, α = 63, a = 1, b = 19.
- Harcama (tüm senaryolar): Gamma-Gamma, p = 6, q = 4, γ = 200 (ortalama sepet 400 TL; S5'te 900 TL'ye ölçeklenir).
- S1: μ_i ~ Gamma(şekil 3, ortalama 30 g); aralık ~ Gamma(k = 8).
- S2/S4: grup içinde μ sabit (haftalik %5 μ=7 g, aylik %65 μ=30 g, seyrek %20 μ=50 g, tek_seferlik %10); bırakma S1'deki gibi (her tekrar ziyaretten sonra p ~ Beta(a, b)); tek seferlik müşteri ilk ziyaret anında kaybolur.
- S3: ömür ~ Üstel(ortalama 540 g), edinimden itibaren.
- S4 sepet çarpanları: haftalik ×1.4, aylik ×1, seyrek ×0.9, tek_seferlik ×1.
- S5 (HİPOTEZ): %55 tek seferlik (ilk ziyaret anında kaybolur); kalanlar S1'deki gibi düzenli, μ_i ~ Gamma(şekil 3, ortalama 35 g), bırakma S1'deki gibi.
- Bağımsızlık tanısı: tekrar ziyaretli müşterilerde x (tekrar ziyaret sayısı) ile m̄ arasında Pearson.

## Senaryolar

| Kod | Ne bozulur | Değerlendirilen müşteri | Gerçek ölü oranı |
|---|---|---|---|
| S0 | Hiçbir şey bozulmaz (BG/NBD varsayımları) | 1505 ± 14 | 0.336 ± 0.009 |
| S1 | Poisson bozulur: düzenli aralıklar, Gamma(k=8) | 1496 ± 16 | 0.328 ± 0.011 |
| S2 | Gamma heterojenliği bozulur: grup karışımı | 1500 ± 16 | 0.352 ± 0.013 |
| S3 | Ziyaret sonrası bırakma bozulur: sürekli zamanda üstel ömür | 1500 ± 18 | 0.370 ± 0.011 |
| S4 | Harcama–sıklık bağımsızlığı bozulur (S2 grupları) | 1499 ± 19 | 0.355 ± 0.010 |
| S5 | Güzellik salonu: %55 tek seferlik, kalanlar düzenli (35 g), sepet 900 TL | 1494 ± 15 | 0.682 ± 0.013 |

## Ayrım gücü ve kalibrasyon: M0, M1, M3

Tek seferlik satırları yalnızca o grubun müşterileridir; grubun hepsi ölü olduğundan AUC tanımsızdır (—), Brier = ortalama P(hayatta)².

| Senaryo | M0 AUC | M1 AUC | M3 AUC | M0 Brier | M1 Brier | M3 Brier |
|---|---|---|---|---|---|---|
| S0 | 0.911 ± 0.009 | 0.935 ± 0.007 | 0.926 ± 0.008 | 0.240 ± 0.008 | 0.082 ± 0.005 | 0.087 ± 0.005 |
| S1 | 0.956 ± 0.006 | 0.964 ± 0.005 | 0.959 ± 0.005 | 0.111 ± 0.005 | 0.067 ± 0.006 | 0.071 ± 0.006 |
| S2 | 0.953 ± 0.008 | 0.698 ± 0.013 | 0.953 ± 0.007 | 0.103 ± 0.006 | 0.177 ± 0.007 | 0.078 ± 0.005 |
| S3 | 0.943 ± 0.006 | 0.836 ± 0.013 | 0.958 ± 0.005 | 0.219 ± 0.007 | 0.117 ± 0.006 | 0.073 ± 0.005 |
| S4 | 0.952 ± 0.009 | 0.697 ± 0.018 | 0.953 ± 0.007 | 0.102 ± 0.007 | 0.182 ± 0.010 | 0.081 ± 0.006 |
| S5 | 0.961 ± 0.006 | 0.229 ± 0.010 | 0.977 ± 0.003 | 0.078 ± 0.007 | 0.596 ± 0.012 | 0.057 ± 0.005 |
| S2 · tek seferlik | — | — | — | 0.048 ± 0.019 | 1.000 ± 0.000 | 0.125 ± 0.026 |
| S4 · tek seferlik | — | — | — | 0.044 ± 0.018 | 1.000 ± 0.000 | 0.122 ± 0.024 |
| S5 · tek seferlik | — | — | — | 0.044 ± 0.007 | 1.000 ± 0.000 | 0.011 ± 0.002 |

## Bekleme dönemi tahmini: ziyaret (M1, M3) ve ciro (+ M2)

M0 ziyaret/ciro tahmini üretmez (belgede tanımı yok).

| Senaryo | M1 ziyaret MAE | M3 ziyaret MAE | M1 ziyaret toplam hata % | M3 ziyaret toplam hata % | M1+M2 ciro MAE (TL) | M3+M2 ciro MAE (TL) | M1+M2 ciro toplam hata % | M3+M2 ciro toplam hata % |
|---|---|---|---|---|---|---|---|---|
| S0 | 2.49 ± 0.07 | 2.50 ± 0.07 | +1.4 ± 2.6 | +0.8 ± 2.5 | 1057 ± 45 | 1062 ± 46 | +1.7 ± 3.1 | +1.2 ± 2.9 |
| S1 | 1.94 ± 0.08 | 1.97 ± 0.07 | +3.1 ± 2.1 | +3.3 ± 2.1 | 876 ± 40 | 889 ± 40 | +2.9 ± 3.0 | +3.0 ± 3.0 |
| S2 | 1.59 ± 0.04 | 1.49 ± 0.05 | +3.4 ± 2.3 | +5.0 ± 2.3 | 715 ± 19 | 686 ± 22 | +4.2 ± 3.0 | +5.8 ± 3.0 |
| S3 | 2.67 ± 0.08 | 2.63 ± 0.08 | +3.7 ± 3.3 | +3.4 ± 3.2 | 1141 ± 46 | 1127 ± 45 | +3.4 ± 3.2 | +3.2 ± 3.1 |
| S4 | 1.60 ± 0.05 | 1.51 ± 0.06 | +4.8 ± 1.7 | +6.1 ± 1.8 | 759 ± 37 | 736 ± 39 | +4.2 ± 2.7 | +4.9 ± 3.1 |
| S5 | 0.98 ± 0.06 | 0.92 ± 0.06 | +2.5 ± 3.1 | +11.0 ± 2.7 | 953 ± 59 | 924 ± 59 | +3.2 ± 4.1 | +11.6 ± 3.7 |

## Parametre geri kazanımı (S0)

S0 BG/NBD ile üretilir; M3 (MBG/NBD) burada yanlış belirlenmiş modeldir (ilk ziyaret sonrası bırakma fırsatı sayar), bu yüzden a/(a+b) sistematik olarak düşük çıkması beklenir.

| Parametre | Gerçek | Tahmin | Ortalama göreli hata |
|---|---|---|---|
| M1 r | 3 | 3.033 ± 0.160 | %4.4 |
| M1 alfa | 63 | 63.913 ± 3.795 | %5.0 |
| M1 a | 1 | 0.961 ± 0.302 | %21.6 |
| M1 b | 19 | 18.649 ± 7.421 | %27.0 |
| M1 a/(a+b) | 0.05 | 0.050 ± 0.005 | %7.0 |
| M3 r | 3 | 3.136 ± 0.173 | %6.5 |
| M3 alfa | 63 | 65.836 ± 3.913 | %6.7 |
| M3 a/(a+b) | 0.05 | 0.038 ± 0.003 | %23.2 |
| M2 p | 6 | 6.213 ± 1.603 | %18.9 |
| M2 q | 4 | 4.054 ± 0.170 | %3.4 |
| M2 gamma | 200 | 209.266 ± 53.900 | %19.7 |

## Gamma-Gamma bağımsızlık tanısı (Pearson, tekrar ziyaretli müşteriler)

Tanı fonksiyonu x ile m̄ arasındadır; x/T sütunu ek bilgidir (x edinim süresiyle karışır).

| Senaryo | x ile m̄ | x/T ile m̄ |
|---|---|---|
| S0 | 0.002 ± 0.028 | 0.003 ± 0.022 |
| S1 | 0.012 ± 0.035 | 0.003 ± 0.026 |
| S2 | -0.001 ± 0.030 | -0.009 ± 0.029 |
| S3 | -0.002 ± 0.035 | -0.003 ± 0.028 |
| S4 | 0.080 ± 0.040 | 0.114 ± 0.044 |
| S5 | 0.008 ± 0.038 | 0.010 ± 0.034 |

## Segment kırılımı (S2)

AUC, tek sınıflı segmentte (ör. tek seferlik müşterilerin hepsi ölü) tanımsızdır: —.

| Segment | Müşteri | Ölü oranı | Ort. P(hayatta) M0 / M1 / M3 | M0 AUC | M1 AUC | M3 AUC | M0 Brier | M1 Brier | M3 Brier | Ziyaret toplam hata % M1 / M3 | Ciro toplam hata % M1 / M3 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| haftalik | 75 ± 10 | 0.615 ± 0.074 | 0.325 / 0.467 / 0.478 | 0.988 ± 0.012 | 0.991 ± 0.013 | 0.988 ± 0.015 | 0.050 ± 0.026 | 0.062 ± 0.023 | 0.073 ± 0.024 | -14.8 ± 10.0 / -20.8 ± 9.7 | -13.6 ± 11.1 / -19.8 ± 11.3 |
| aylik | 975 ± 20 | 0.283 ± 0.012 | 0.598 / 0.815 / 0.779 | 0.947 ± 0.011 | 0.953 ± 0.010 | 0.939 ± 0.009 | 0.101 ± 0.009 | 0.090 ± 0.007 | 0.075 ± 0.007 | -0.7 ± 2.0 / +2.6 ± 1.8 | -0.0 ± 3.1 / +3.3 ± 3.0 |
| seyrek | 301 ± 15 | 0.190 ± 0.028 | 0.626 / 0.884 / 0.822 | 0.928 ± 0.024 | 0.942 ± 0.020 | 0.916 ± 0.022 | 0.150 ± 0.013 | 0.083 ± 0.013 | 0.064 ± 0.010 | +9.9 ± 3.8 / +21.0 ± 4.0 | +10.2 ± 5.1 / +21.2 ± 5.5 |
| tek_seferlik | 149 ± 8 | 1.000 ± 0.000 | 0.057 / 1.000 / 0.214 | — | — | — | 0.048 ± 0.019 | 1.000 ± 0.000 | 0.125 ± 0.026 | — / — | — / — |

## Segment kırılımı (S4)

AUC, tek sınıflı segmentte (ör. tek seferlik müşterilerin hepsi ölü) tanımsızdır: —.

| Segment | Müşteri | Ölü oranı | Ort. P(hayatta) M0 / M1 / M3 | M0 AUC | M1 AUC | M3 AUC | M0 Brier | M1 Brier | M3 Brier | Ziyaret toplam hata % M1 / M3 | Ciro toplam hata % M1 / M3 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| haftalik | 78 ± 8 | 0.572 ± 0.055 | 0.359 / 0.513 / 0.517 | 0.990 ± 0.011 | 0.995 ± 0.007 | 0.989 ± 0.008 | 0.049 ± 0.021 | 0.066 ± 0.025 | 0.071 ± 0.028 | -13.1 ± 9.2 / -20.4 ± 9.2 | -13.5 ± 11.1 / -20.8 ± 11.2 |
| aylik | 969 ± 22 | 0.287 ± 0.012 | 0.596 / 0.816 / 0.781 | 0.949 ± 0.008 | 0.955 ± 0.007 | 0.941 ± 0.009 | 0.100 ± 0.007 | 0.094 ± 0.007 | 0.079 ± 0.007 | +0.9 ± 1.7 / +4.2 ± 2.0 | +1.5 ± 2.0 / +4.7 ± 2.3 |
| seyrek | 302 ± 13 | 0.197 ± 0.019 | 0.633 / 0.885 / 0.825 | 0.903 ± 0.033 | 0.922 ± 0.029 | 0.896 ± 0.033 | 0.148 ± 0.017 | 0.089 ± 0.014 | 0.071 ± 0.012 | +11.6 ± 3.3 / +22.8 ± 3.5 | +12.5 ± 3.4 / +23.7 ± 3.9 |
| tek_seferlik | 150 ± 12 | 1.000 ± 0.000 | 0.054 / 1.000 / 0.213 | — | — | — | 0.044 ± 0.018 | 1.000 ± 0.000 | 0.122 ± 0.024 | — / — | — / — |

## Segment kırılımı (S5)

AUC, tek sınıflı segmentte (ör. tek seferlik müşterilerin hepsi ölü) tanımsızdır: —.

| Segment | Müşteri | Ölü oranı | Ort. P(hayatta) M0 / M1 / M3 | M0 AUC | M1 AUC | M3 AUC | M0 Brier | M1 Brier | M3 Brier | Ziyaret toplam hata % M1 / M3 | Ciro toplam hata % M1 / M3 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| duzenli | 678 ± 21 | 0.299 ± 0.016 | 0.565 / 0.820 / 0.728 | 0.949 ± 0.010 | 0.958 ± 0.010 | 0.902 ± 0.014 | 0.118 ± 0.011 | 0.110 ± 0.011 | 0.112 ± 0.010 | -5.0 ± 2.9 / +5.7 ± 2.5 | -4.3 ± 3.9 / +6.3 ± 3.5 |
| tek_seferlik | 816 ± 20 | 1.000 ± 0.000 | 0.053 / 1.000 / 0.056 | — | — | — | 0.044 ± 0.007 | 1.000 ± 0.000 | 0.011 ± 0.002 | — / — | — / — |

## Güvenilirlik tabloları (tüm tohumlar birleştirilmiş)

Her kutu: müşteri sayısı, tahmin edilen ortalama P(hayatta), gerçek hayatta oranı.


### S0

| Kutu | M0 n | M0 tahmin | M0 gerçek | M1 n | M1 tahmin | M1 gerçek | M3 n | M3 tahmin | M3 gerçek |
|---|---|---|---|---|---|---|---|---|---|
| [0.0, 0.1) | 12558 | 0.008 | 0.301 | 5953 | 0.018 | 0.018 | 5847 | 0.018 | 0.021 |
| [0.1, 0.2) | 1286 | 0.148 | 0.809 | 850 | 0.145 | 0.166 | 881 | 0.145 | 0.177 |
| [0.2, 0.3) | 1231 | 0.250 | 0.877 | 648 | 0.249 | 0.241 | 644 | 0.247 | 0.261 |
| [0.3, 0.4) | 1273 | 0.350 | 0.887 | 549 | 0.351 | 0.348 | 613 | 0.349 | 0.372 |
| [0.4, 0.5) | 1485 | 0.451 | 0.907 | 590 | 0.451 | 0.447 | 591 | 0.452 | 0.433 |
| [0.5, 0.6) | 1853 | 0.553 | 0.925 | 690 | 0.551 | 0.554 | 724 | 0.553 | 0.575 |
| [0.6, 0.7) | 2455 | 0.653 | 0.943 | 1034 | 0.652 | 0.631 | 1004 | 0.652 | 0.636 |
| [0.7, 0.8) | 3599 | 0.754 | 0.953 | 1537 | 0.755 | 0.744 | 1642 | 0.753 | 0.737 |
| [0.8, 0.9) | 3304 | 0.844 | 0.957 | 3966 | 0.859 | 0.852 | 4073 | 0.860 | 0.859 |
| [0.9, 1.0) | 1059 | 0.951 | 0.947 | 14286 | 0.951 | 0.951 | 14084 | 0.946 | 0.945 |

### S1

| Kutu | M0 n | M0 tahmin | M0 gerçek | M1 n | M1 tahmin | M1 gerçek | M3 n | M3 tahmin | M3 gerçek |
|---|---|---|---|---|---|---|---|---|---|
| [0.0, 0.1) | 10099 | 0.004 | 0.126 | 4931 | 0.022 | 0.000 | 4648 | 0.022 | 0.000 |
| [0.1, 0.2) | 629 | 0.147 | 0.830 | 858 | 0.143 | 0.000 | 923 | 0.144 | 0.000 |
| [0.2, 0.3) | 565 | 0.252 | 0.880 | 537 | 0.247 | 0.000 | 545 | 0.248 | 0.000 |
| [0.3, 0.4) | 650 | 0.350 | 0.895 | 460 | 0.348 | 0.000 | 455 | 0.349 | 0.000 |
| [0.4, 0.5) | 701 | 0.450 | 0.923 | 391 | 0.450 | 0.000 | 403 | 0.448 | 0.002 |
| [0.5, 0.6) | 873 | 0.553 | 0.932 | 352 | 0.552 | 0.009 | 391 | 0.551 | 0.005 |
| [0.6, 0.7) | 1128 | 0.652 | 0.944 | 366 | 0.650 | 0.027 | 389 | 0.653 | 0.031 |
| [0.7, 0.8) | 1585 | 0.752 | 0.956 | 551 | 0.756 | 0.216 | 507 | 0.755 | 0.160 |
| [0.8, 0.9) | 2495 | 0.855 | 0.960 | 2150 | 0.867 | 0.708 | 1754 | 0.866 | 0.621 |
| [0.9, 1.0) | 11188 | 0.974 | 0.966 | 19317 | 0.954 | 0.956 | 19898 | 0.953 | 0.951 |

### S2

| Kutu | M0 n | M0 tahmin | M0 gerçek | M1 n | M1 tahmin | M1 gerçek | M3 n | M3 tahmin | M3 gerçek |
|---|---|---|---|---|---|---|---|---|---|
| [0.0, 0.1) | 10376 | 0.004 | 0.091 | 1758 | 0.038 | 0.000 | 4894 | 0.027 | 0.000 |
| [0.1, 0.2) | 597 | 0.148 | 0.844 | 977 | 0.147 | 0.000 | 965 | 0.145 | 0.000 |
| [0.2, 0.3) | 599 | 0.250 | 0.858 | 636 | 0.247 | 0.000 | 668 | 0.249 | 0.000 |
| [0.3, 0.4) | 642 | 0.352 | 0.883 | 565 | 0.350 | 0.000 | 484 | 0.346 | 0.002 |
| [0.4, 0.5) | 697 | 0.450 | 0.894 | 484 | 0.448 | 0.000 | 434 | 0.451 | 0.002 |
| [0.5, 0.6) | 900 | 0.552 | 0.939 | 395 | 0.550 | 0.000 | 462 | 0.549 | 0.017 |
| [0.6, 0.7) | 1101 | 0.653 | 0.928 | 477 | 0.648 | 0.000 | 517 | 0.650 | 0.091 |
| [0.7, 0.8) | 1607 | 0.754 | 0.955 | 594 | 0.753 | 0.008 | 815 | 0.755 | 0.337 |
| [0.8, 0.9) | 2476 | 0.855 | 0.953 | 1109 | 0.863 | 0.371 | 3285 | 0.864 | 0.781 |
| [0.9, 1.0) | 11007 | 0.974 | 0.956 | 23007 | 0.964 | 0.827 | 17478 | 0.953 | 0.946 |

### S3

| Kutu | M0 n | M0 tahmin | M0 gerçek | M1 n | M1 tahmin | M1 gerçek | M3 n | M3 tahmin | M3 gerçek |
|---|---|---|---|---|---|---|---|---|---|
| [0.0, 0.1) | 13677 | 0.007 | 0.256 | 5218 | 0.021 | 0.009 | 6803 | 0.020 | 0.015 |
| [0.1, 0.2) | 1229 | 0.149 | 0.795 | 932 | 0.144 | 0.072 | 1083 | 0.146 | 0.130 |
| [0.2, 0.3) | 1138 | 0.249 | 0.866 | 665 | 0.250 | 0.167 | 764 | 0.251 | 0.233 |
| [0.3, 0.4) | 1219 | 0.351 | 0.903 | 640 | 0.349 | 0.252 | 673 | 0.351 | 0.324 |
| [0.4, 0.5) | 1398 | 0.451 | 0.921 | 611 | 0.451 | 0.316 | 685 | 0.451 | 0.413 |
| [0.5, 0.6) | 1725 | 0.553 | 0.941 | 630 | 0.552 | 0.449 | 764 | 0.554 | 0.527 |
| [0.6, 0.7) | 2325 | 0.654 | 0.969 | 867 | 0.654 | 0.562 | 1066 | 0.652 | 0.612 |
| [0.7, 0.8) | 3397 | 0.752 | 0.974 | 1503 | 0.754 | 0.675 | 1629 | 0.754 | 0.746 |
| [0.8, 0.9) | 3005 | 0.843 | 0.992 | 3360 | 0.860 | 0.847 | 3889 | 0.860 | 0.876 |
| [0.9, 1.0) | 878 | 0.952 | 0.986 | 15565 | 0.958 | 0.879 | 12635 | 0.946 | 0.973 |

### S4

| Kutu | M0 n | M0 tahmin | M0 gerçek | M1 n | M1 tahmin | M1 gerçek | M3 n | M3 tahmin | M3 gerçek |
|---|---|---|---|---|---|---|---|---|---|
| [0.0, 0.1) | 10381 | 0.004 | 0.089 | 1703 | 0.039 | 0.000 | 4866 | 0.028 | 0.000 |
| [0.1, 0.2) | 575 | 0.147 | 0.807 | 963 | 0.146 | 0.000 | 983 | 0.144 | 0.000 |
| [0.2, 0.3) | 583 | 0.251 | 0.849 | 660 | 0.248 | 0.000 | 622 | 0.246 | 0.000 |
| [0.3, 0.4) | 625 | 0.351 | 0.886 | 561 | 0.347 | 0.000 | 496 | 0.350 | 0.000 |
| [0.4, 0.5) | 730 | 0.449 | 0.895 | 443 | 0.447 | 0.000 | 435 | 0.446 | 0.002 |
| [0.5, 0.6) | 836 | 0.553 | 0.926 | 436 | 0.552 | 0.000 | 432 | 0.551 | 0.016 |
| [0.6, 0.7) | 1120 | 0.652 | 0.938 | 479 | 0.652 | 0.000 | 509 | 0.654 | 0.084 |
| [0.7, 0.8) | 1622 | 0.752 | 0.936 | 546 | 0.755 | 0.013 | 845 | 0.756 | 0.292 |
| [0.8, 0.9) | 2530 | 0.855 | 0.951 | 1128 | 0.863 | 0.337 | 3200 | 0.866 | 0.760 |
| [0.9, 1.0) | 10982 | 0.974 | 0.956 | 23065 | 0.965 | 0.821 | 17596 | 0.954 | 0.943 |

### S5

| Kutu | M0 n | M0 tahmin | M0 gerçek | M1 n | M1 tahmin | M1 gerçek | M3 n | M3 tahmin | M3 gerçek |
|---|---|---|---|---|---|---|---|---|---|
| [0.0, 0.1) | 19332 | 0.002 | 0.032 | 1082 | 0.021 | 0.000 | 15361 | 0.023 | 0.001 |
| [0.1, 0.2) | 412 | 0.147 | 0.580 | 287 | 0.146 | 0.000 | 1806 | 0.145 | 0.066 |
| [0.2, 0.3) | 347 | 0.251 | 0.706 | 209 | 0.244 | 0.000 | 1209 | 0.249 | 0.211 |
| [0.3, 0.4) | 402 | 0.350 | 0.749 | 165 | 0.350 | 0.000 | 931 | 0.350 | 0.337 |
| [0.4, 0.5) | 419 | 0.452 | 0.768 | 201 | 0.452 | 0.000 | 613 | 0.440 | 0.323 |
| [0.5, 0.6) | 500 | 0.553 | 0.794 | 227 | 0.551 | 0.000 | 166 | 0.550 | 0.072 |
| [0.6, 0.7) | 581 | 0.653 | 0.824 | 316 | 0.654 | 0.003 | 236 | 0.650 | 0.186 |
| [0.7, 0.8) | 809 | 0.752 | 0.848 | 374 | 0.752 | 0.005 | 392 | 0.756 | 0.500 |
| [0.8, 0.9) | 1310 | 0.853 | 0.887 | 556 | 0.855 | 0.094 | 1172 | 0.860 | 0.756 |
| [0.9, 1.0) | 5774 | 0.975 | 0.875 | 26469 | 0.986 | 0.357 | 8000 | 0.967 | 0.932 |

## S6 "Stüdyo": yenileme riski (Adım 5b)

- 20 tohum × 1500 üye, 2 yıl. Değerlendirme: kalibrasyon tarihinde (547.5. gün) aktif olan ve 60 gün içinde biten paketler.
- Paket karışımı (HİPOTEZ): 1 Aylık %45 (2500 TL), 3 Aylık %25 (6000 TL), 6 Aylık %15 (10000 TL), 12 Giriş %15 (800 TL); giriş paketi 60 gün sonra biter (hak kalsa da).
- Katılım: düzenli aralıklar (Gamma k = 8), μ_i ~ Gamma(şekil 3, ortalama 4 g); bırakma MBG/NBD tarzı, ilk ziyaret dahil her ziyaretten sonra p ~ Beta(1, 19).
- Gerçek yenileme: paket bittiğinde hayatta olan üye %90 olasılıkla aynı türü yeniler; hayatta olmayan yenilemez.
- M3-sim = MBG/NBD + sonsal yenileme olasılığı, kesin formül (`analitik/yenileme.py`, K61; v2'ye kadar N = 2 000 Monte Carlo). Kural = son 21 günde en fazla 1 giriş → yenilemez (0/1 skor).
- Riskteki Para hata % = (Σ (1 − P(yenileme)) × fiyat − gerçekleşen kayıp ciro) / gerçekleşen kayıp ciro; gerçekleşen kayıp = yenilenmeyen paketlerin fiyat toplamı.
- Bilinen sınırlamalar: M3, S5'te gelecekteki ziyaretleri ~%11 fazla tahmin etti, yenileme olasılığı aynı eğilimi taşıyabilir. Fiyat, kampanya, taşınma gibi davranış dışı yenileme nedenleri modelde yok (S6'da %10 olarak üretilir). Model gerçek yenileme verisiyle kalibre edilmedi (5c).

| Segment | Paket | Yenileme oranı | M3-sim AUC | Kural AUC | M3-sim Brier | Kural Brier | Gerçek kayıp (TL) | M3-sim Riskteki Para hata % | Kural Riskteki Para hata % |
|---|---|---|---|---|---|---|---|---|---|
| Tümü | 224 ± 15 | 0.582 ± 0.029 | 0.827 ± 0.034 | 0.720 ± 0.021 | 0.153 ± 0.016 | 0.241 ± 0.026 | 434115 ± 43725 | -13.2 ± 4.5 | -36.0 ± 4.8 |
| 1 Aylık | 95 ± 9 | 0.689 ± 0.056 | 0.711 ± 0.068 | 0.561 ± 0.042 | 0.187 ± 0.032 | 0.289 ± 0.058 | 73875 ± 15400 | -30.8 ± 11.3 | -73.9 ± 7.2 |
| 3 Aylık | 61 ± 8 | 0.524 ± 0.056 | 0.885 ± 0.049 | 0.789 ± 0.044 | 0.125 ± 0.027 | 0.202 ± 0.050 | 174000 ± 33548 | -10.0 ± 6.3 | -37.3 ± 6.5 |
| 6 Aylık | 26 ± 5 | 0.327 ± 0.111 | 0.950 ± 0.041 | 0.910 ± 0.049 | 0.085 ± 0.047 | 0.120 ± 0.065 | 172000 ± 36216 | -7.1 ± 9.3 | -16.6 ± 8.8 |
| 12 Giriş | 42 ± 4 | 0.577 ± 0.056 | 0.813 ± 0.067 | 0.699 ± 0.054 | 0.161 ± 0.035 | 0.264 ± 0.056 | 14240 ± 2429 | -18.3 ± 12.5 | -49.3 ± 14.2 |
