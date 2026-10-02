# Backtest sonuçları (Adım 6)

Bu sonuçlar kanonik sıra (Adım 4b-1) öncesi koddan üretildi; (μ, κ) adımında yeniden üretilecek.

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
| S0 | 0.911 ± 0.009 | 0.935 ± 0.007 | 0.926 ± 0.008 | 0.240 ± 0.008 | 0.082 ± 0.005 | 0.086 ± 0.005 |
| S1 | 0.956 ± 0.006 | 0.964 ± 0.005 | 0.959 ± 0.005 | 0.111 ± 0.005 | 0.067 ± 0.006 | 0.071 ± 0.006 |
| S2 | 0.953 ± 0.008 | 0.698 ± 0.013 | 0.953 ± 0.007 | 0.103 ± 0.006 | 0.177 ± 0.007 | 0.078 ± 0.005 |
| S3 | 0.943 ± 0.006 | 0.836 ± 0.013 | 0.958 ± 0.005 | 0.219 ± 0.007 | 0.117 ± 0.006 | 0.073 ± 0.005 |
| S4 | 0.952 ± 0.009 | 0.697 ± 0.018 | 0.953 ± 0.007 | 0.102 ± 0.007 | 0.182 ± 0.010 | 0.081 ± 0.006 |
| S5 | 0.961 ± 0.006 | 0.228 ± 0.010 | 0.977 ± 0.003 | 0.078 ± 0.007 | 0.597 ± 0.012 | 0.057 ± 0.005 |
| S2 · tek seferlik | — | — | — | 0.048 ± 0.019 | 1.000 ± 0.000 | 0.124 ± 0.026 |
| S4 · tek seferlik | — | — | — | 0.044 ± 0.018 | 1.000 ± 0.000 | 0.121 ± 0.024 |
| S5 · tek seferlik | — | — | — | 0.044 ± 0.007 | 1.000 ± 0.000 | 0.011 ± 0.002 |

## Bekleme dönemi tahmini: ziyaret (M1, M3) ve ciro (+ M2)

M0 ziyaret/ciro tahmini üretmez (belgede tanımı yok).

| Senaryo | M1 ziyaret MAE | M3 ziyaret MAE | M1 ziyaret toplam hata % | M3 ziyaret toplam hata % | M1+M2 ciro MAE (TL) | M3+M2 ciro MAE (TL) | M1+M2 ciro toplam hata % | M3+M2 ciro toplam hata % |
|---|---|---|---|---|---|---|---|---|
| S0 | 2.49 ± 0.07 | 2.50 ± 0.07 | +1.3 ± 2.6 | +0.6 ± 2.5 | 1057 ± 45 | 1062 ± 46 | +1.7 ± 3.1 | +0.9 ± 2.9 |
| S1 | 1.94 ± 0.08 | 1.97 ± 0.07 | +3.1 ± 2.1 | +3.1 ± 2.1 | 876 ± 40 | 890 ± 40 | +2.8 ± 3.0 | +2.8 ± 3.1 |
| S2 | 1.59 ± 0.04 | 1.49 ± 0.05 | +3.2 ± 2.3 | +5.0 ± 2.3 | 715 ± 19 | 686 ± 22 | +4.0 ± 3.0 | +5.9 ± 3.0 |
| S3 | 2.67 ± 0.07 | 2.63 ± 0.08 | +3.5 ± 3.3 | +3.3 ± 3.2 | 1141 ± 46 | 1127 ± 45 | +3.3 ± 3.2 | +3.1 ± 3.1 |
| S4 | 1.60 ± 0.05 | 1.51 ± 0.06 | +4.7 ± 1.7 | +6.2 ± 1.8 | 760 ± 37 | 736 ± 39 | +4.0 ± 2.8 | +5.0 ± 3.1 |
| S5 | 0.99 ± 0.06 | 0.92 ± 0.06 | +1.9 ± 3.2 | +11.1 ± 2.7 | 956 ± 60 | 924 ± 59 | +2.5 ± 4.3 | +11.7 ± 3.7 |

## Parametre geri kazanımı (S0)

S0 BG/NBD ile üretilir; M3 (MBG/NBD) burada yanlış belirlenmiş modeldir (ilk ziyaret sonrası bırakma fırsatı sayar), bu yüzden a/(a+b) sistematik olarak düşük çıkması beklenir.

| Parametre | Gerçek | Tahmin | Ortalama göreli hata |
|---|---|---|---|
| M1 r | 3 | 3.027 ± 0.160 | %4.4 |
| M1 alfa | 63 | 63.790 ± 3.789 | %4.9 |
| M1 a | 1 | 0.982 ± 0.334 | %22.5 |
| M1 b | 19 | 19.169 ± 8.245 | %28.4 |
| M1 a/(a+b) | 0.05 | 0.050 ± 0.005 | %7.2 |
| M3 r | 3 | 3.128 ± 0.173 | %6.3 |
| M3 alfa | 63 | 65.654 ± 3.896 | %6.5 |
| M3 a/(a+b) | 0.05 | 0.038 ± 0.003 | %24.1 |
| M2 p | 6 | 6.213 ± 1.604 | %18.9 |
| M2 q | 4 | 4.054 ± 0.170 | %3.4 |
| M2 gamma | 200 | 209.262 ± 53.899 | %19.7 |

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
| haftalik | 75 ± 10 | 0.615 ± 0.074 | 0.325 / 0.466 / 0.478 | 0.988 ± 0.012 | 0.991 ± 0.012 | 0.988 ± 0.015 | 0.050 ± 0.026 | 0.062 ± 0.023 | 0.073 ± 0.024 | -15.7 ± 10.2 / -20.7 ± 9.8 | -14.5 ± 11.2 / -19.7 ± 11.3 |
| aylik | 975 ± 20 | 0.283 ± 0.012 | 0.598 / 0.815 / 0.779 | 0.947 ± 0.011 | 0.953 ± 0.010 | 0.939 ± 0.009 | 0.101 ± 0.009 | 0.090 ± 0.007 | 0.075 ± 0.007 | -0.8 ± 2.0 / +2.6 ± 1.8 | -0.1 ± 3.1 / +3.3 ± 3.0 |
| seyrek | 301 ± 15 | 0.190 ± 0.028 | 0.626 / 0.885 / 0.822 | 0.928 ± 0.024 | 0.942 ± 0.020 | 0.916 ± 0.022 | 0.150 ± 0.013 | 0.084 ± 0.013 | 0.064 ± 0.010 | +9.9 ± 3.8 / +21.0 ± 4.0 | +10.2 ± 5.1 / +21.2 ± 5.5 |
| tek_seferlik | 149 ± 8 | 1.000 ± 0.000 | 0.057 / 1.000 / 0.214 | — | — | — | 0.048 ± 0.019 | 1.000 ± 0.000 | 0.124 ± 0.026 | — / — | — / — |

## Segment kırılımı (S4)

AUC, tek sınıflı segmentte (ör. tek seferlik müşterilerin hepsi ölü) tanımsızdır: —.

| Segment | Müşteri | Ölü oranı | Ort. P(hayatta) M0 / M1 / M3 | M0 AUC | M1 AUC | M3 AUC | M0 Brier | M1 Brier | M3 Brier | Ziyaret toplam hata % M1 / M3 | Ciro toplam hata % M1 / M3 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| haftalik | 78 ± 8 | 0.572 ± 0.055 | 0.359 / 0.513 / 0.517 | 0.990 ± 0.011 | 0.994 ± 0.007 | 0.989 ± 0.008 | 0.049 ± 0.021 | 0.066 ± 0.025 | 0.071 ± 0.028 | -13.6 ± 9.4 / -20.4 ± 9.2 | -13.9 ± 11.3 / -20.7 ± 11.2 |
| aylik | 969 ± 22 | 0.287 ± 0.012 | 0.596 / 0.816 / 0.781 | 0.949 ± 0.008 | 0.955 ± 0.007 | 0.941 ± 0.009 | 0.100 ± 0.007 | 0.094 ± 0.007 | 0.079 ± 0.007 | +0.9 ± 1.7 / +4.2 ± 2.0 | +1.4 ± 2.0 / +4.8 ± 2.3 |
| seyrek | 302 ± 13 | 0.197 ± 0.019 | 0.633 / 0.885 / 0.825 | 0.903 ± 0.033 | 0.922 ± 0.029 | 0.896 ± 0.033 | 0.148 ± 0.017 | 0.090 ± 0.014 | 0.071 ± 0.012 | +11.5 ± 3.2 / +22.9 ± 3.5 | +12.4 ± 3.4 / +23.8 ± 3.9 |
| tek_seferlik | 150 ± 12 | 1.000 ± 0.000 | 0.054 / 1.000 / 0.212 | — | — | — | 0.044 ± 0.018 | 1.000 ± 0.000 | 0.121 ± 0.024 | — / — | — / — |

## Segment kırılımı (S5)

AUC, tek sınıflı segmentte (ör. tek seferlik müşterilerin hepsi ölü) tanımsızdır: —.

| Segment | Müşteri | Ölü oranı | Ort. P(hayatta) M0 / M1 / M3 | M0 AUC | M1 AUC | M3 AUC | M0 Brier | M1 Brier | M3 Brier | Ziyaret toplam hata % M1 / M3 | Ciro toplam hata % M1 / M3 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| duzenli | 678 ± 21 | 0.299 ± 0.016 | 0.565 / 0.821 / 0.729 | 0.949 ± 0.010 | 0.957 ± 0.010 | 0.902 ± 0.014 | 0.118 ± 0.011 | 0.111 ± 0.011 | 0.112 ± 0.010 | -5.6 ± 3.0 / +5.8 ± 2.5 | -5.0 ± 4.1 / +6.4 ± 3.5 |
| tek_seferlik | 816 ± 20 | 1.000 ± 0.000 | 0.053 / 1.000 / 0.056 | — | — | — | 0.044 ± 0.007 | 1.000 ± 0.000 | 0.011 ± 0.002 | — / — | — / — |

## Güvenilirlik tabloları (tüm tohumlar birleştirilmiş)

Her kutu: müşteri sayısı, tahmin edilen ortalama P(hayatta), gerçek hayatta oranı.


### S0

| Kutu | M0 n | M0 tahmin | M0 gerçek | M1 n | M1 tahmin | M1 gerçek | M3 n | M3 tahmin | M3 gerçek |
|---|---|---|---|---|---|---|---|---|---|
| [0.0, 0.1) | 12558 | 0.008 | 0.301 | 5949 | 0.018 | 0.018 | 5847 | 0.018 | 0.021 |
| [0.1, 0.2) | 1286 | 0.148 | 0.809 | 851 | 0.145 | 0.166 | 879 | 0.145 | 0.177 |
| [0.2, 0.3) | 1231 | 0.250 | 0.877 | 647 | 0.249 | 0.241 | 640 | 0.247 | 0.259 |
| [0.3, 0.4) | 1273 | 0.350 | 0.887 | 552 | 0.351 | 0.348 | 615 | 0.349 | 0.376 |
| [0.4, 0.5) | 1485 | 0.451 | 0.907 | 586 | 0.451 | 0.444 | 584 | 0.451 | 0.432 |
| [0.5, 0.6) | 1853 | 0.553 | 0.925 | 694 | 0.551 | 0.556 | 730 | 0.553 | 0.579 |
| [0.6, 0.7) | 2455 | 0.653 | 0.943 | 1035 | 0.653 | 0.631 | 1004 | 0.652 | 0.630 |
| [0.7, 0.8) | 3599 | 0.754 | 0.953 | 1536 | 0.755 | 0.743 | 1654 | 0.754 | 0.735 |
| [0.8, 0.9) | 3304 | 0.844 | 0.957 | 3976 | 0.859 | 0.853 | 4085 | 0.860 | 0.861 |
| [0.9, 1.0) | 1059 | 0.951 | 0.947 | 14277 | 0.951 | 0.951 | 14065 | 0.946 | 0.945 |

### S1

| Kutu | M0 n | M0 tahmin | M0 gerçek | M1 n | M1 tahmin | M1 gerçek | M3 n | M3 tahmin | M3 gerçek |
|---|---|---|---|---|---|---|---|---|---|
| [0.0, 0.1) | 10099 | 0.004 | 0.126 | 4929 | 0.022 | 0.000 | 4642 | 0.022 | 0.000 |
| [0.1, 0.2) | 629 | 0.147 | 0.830 | 859 | 0.144 | 0.000 | 921 | 0.144 | 0.000 |
| [0.2, 0.3) | 565 | 0.252 | 0.880 | 535 | 0.247 | 0.000 | 545 | 0.248 | 0.000 |
| [0.3, 0.4) | 650 | 0.350 | 0.895 | 462 | 0.348 | 0.000 | 461 | 0.348 | 0.000 |
| [0.4, 0.5) | 701 | 0.450 | 0.923 | 391 | 0.450 | 0.000 | 399 | 0.448 | 0.003 |
| [0.5, 0.6) | 873 | 0.553 | 0.932 | 347 | 0.551 | 0.006 | 395 | 0.551 | 0.003 |
| [0.6, 0.7) | 1128 | 0.652 | 0.944 | 373 | 0.650 | 0.029 | 385 | 0.653 | 0.034 |
| [0.7, 0.8) | 1585 | 0.752 | 0.956 | 551 | 0.756 | 0.214 | 506 | 0.754 | 0.150 |
| [0.8, 0.9) | 2495 | 0.855 | 0.960 | 2143 | 0.867 | 0.707 | 1741 | 0.866 | 0.616 |
| [0.9, 1.0) | 11188 | 0.974 | 0.966 | 19323 | 0.954 | 0.956 | 19918 | 0.953 | 0.951 |

### S2

| Kutu | M0 n | M0 tahmin | M0 gerçek | M1 n | M1 tahmin | M1 gerçek | M3 n | M3 tahmin | M3 gerçek |
|---|---|---|---|---|---|---|---|---|---|
| [0.0, 0.1) | 10376 | 0.004 | 0.091 | 1748 | 0.037 | 0.000 | 4887 | 0.027 | 0.000 |
| [0.1, 0.2) | 597 | 0.148 | 0.844 | 974 | 0.147 | 0.000 | 970 | 0.145 | 0.000 |
| [0.2, 0.3) | 599 | 0.250 | 0.858 | 642 | 0.247 | 0.000 | 668 | 0.249 | 0.000 |
| [0.3, 0.4) | 642 | 0.352 | 0.883 | 558 | 0.350 | 0.000 | 486 | 0.346 | 0.002 |
| [0.4, 0.5) | 697 | 0.450 | 0.894 | 492 | 0.448 | 0.000 | 431 | 0.452 | 0.002 |
| [0.5, 0.6) | 900 | 0.552 | 0.939 | 401 | 0.550 | 0.000 | 464 | 0.549 | 0.017 |
| [0.6, 0.7) | 1101 | 0.653 | 0.928 | 466 | 0.648 | 0.000 | 518 | 0.651 | 0.093 |
| [0.7, 0.8) | 1607 | 0.754 | 0.955 | 596 | 0.752 | 0.008 | 814 | 0.755 | 0.337 |
| [0.8, 0.9) | 2476 | 0.855 | 0.953 | 1117 | 0.863 | 0.366 | 3277 | 0.864 | 0.782 |
| [0.9, 1.0) | 11007 | 0.974 | 0.956 | 23008 | 0.964 | 0.827 | 17487 | 0.953 | 0.946 |

### S3

| Kutu | M0 n | M0 tahmin | M0 gerçek | M1 n | M1 tahmin | M1 gerçek | M3 n | M3 tahmin | M3 gerçek |
|---|---|---|---|---|---|---|---|---|---|
| [0.0, 0.1) | 13677 | 0.007 | 0.256 | 5218 | 0.021 | 0.009 | 6797 | 0.020 | 0.015 |
| [0.1, 0.2) | 1229 | 0.149 | 0.795 | 929 | 0.144 | 0.072 | 1084 | 0.146 | 0.131 |
| [0.2, 0.3) | 1138 | 0.249 | 0.866 | 665 | 0.250 | 0.165 | 763 | 0.251 | 0.229 |
| [0.3, 0.4) | 1219 | 0.351 | 0.903 | 639 | 0.348 | 0.250 | 680 | 0.351 | 0.326 |
| [0.4, 0.5) | 1398 | 0.451 | 0.921 | 615 | 0.451 | 0.317 | 680 | 0.451 | 0.413 |
| [0.5, 0.6) | 1725 | 0.553 | 0.941 | 634 | 0.553 | 0.451 | 769 | 0.554 | 0.525 |
| [0.6, 0.7) | 2325 | 0.654 | 0.969 | 864 | 0.654 | 0.564 | 1063 | 0.652 | 0.611 |
| [0.7, 0.8) | 3397 | 0.752 | 0.974 | 1497 | 0.754 | 0.675 | 1629 | 0.754 | 0.746 |
| [0.8, 0.9) | 3005 | 0.843 | 0.992 | 3365 | 0.860 | 0.845 | 3888 | 0.860 | 0.876 |
| [0.9, 1.0) | 878 | 0.952 | 0.986 | 15565 | 0.958 | 0.879 | 12638 | 0.946 | 0.973 |

### S4

| Kutu | M0 n | M0 tahmin | M0 gerçek | M1 n | M1 tahmin | M1 gerçek | M3 n | M3 tahmin | M3 gerçek |
|---|---|---|---|---|---|---|---|---|---|
| [0.0, 0.1) | 10381 | 0.004 | 0.089 | 1696 | 0.039 | 0.000 | 4863 | 0.028 | 0.000 |
| [0.1, 0.2) | 575 | 0.147 | 0.807 | 963 | 0.146 | 0.000 | 984 | 0.144 | 0.000 |
| [0.2, 0.3) | 583 | 0.251 | 0.849 | 651 | 0.248 | 0.000 | 623 | 0.247 | 0.000 |
| [0.3, 0.4) | 625 | 0.351 | 0.886 | 567 | 0.347 | 0.000 | 496 | 0.351 | 0.000 |
| [0.4, 0.5) | 730 | 0.449 | 0.895 | 449 | 0.447 | 0.000 | 433 | 0.446 | 0.002 |
| [0.5, 0.6) | 836 | 0.553 | 0.926 | 436 | 0.553 | 0.000 | 430 | 0.550 | 0.016 |
| [0.6, 0.7) | 1120 | 0.652 | 0.938 | 478 | 0.652 | 0.000 | 515 | 0.654 | 0.089 |
| [0.7, 0.8) | 1622 | 0.752 | 0.936 | 546 | 0.754 | 0.011 | 842 | 0.756 | 0.292 |
| [0.8, 0.9) | 2530 | 0.855 | 0.951 | 1134 | 0.863 | 0.337 | 3192 | 0.865 | 0.759 |
| [0.9, 1.0) | 10982 | 0.974 | 0.956 | 23064 | 0.965 | 0.821 | 17606 | 0.954 | 0.943 |

### S5

| Kutu | M0 n | M0 tahmin | M0 gerçek | M1 n | M1 tahmin | M1 gerçek | M3 n | M3 tahmin | M3 gerçek |
|---|---|---|---|---|---|---|---|---|---|
| [0.0, 0.1) | 19332 | 0.002 | 0.032 | 1084 | 0.021 | 0.000 | 15344 | 0.023 | 0.001 |
| [0.1, 0.2) | 412 | 0.147 | 0.580 | 288 | 0.148 | 0.000 | 1812 | 0.145 | 0.066 |
| [0.2, 0.3) | 347 | 0.251 | 0.706 | 200 | 0.246 | 0.000 | 1215 | 0.248 | 0.211 |
| [0.3, 0.4) | 402 | 0.350 | 0.749 | 166 | 0.351 | 0.000 | 934 | 0.350 | 0.335 |
| [0.4, 0.5) | 419 | 0.452 | 0.768 | 190 | 0.453 | 0.000 | 610 | 0.440 | 0.325 |
| [0.5, 0.6) | 500 | 0.553 | 0.794 | 228 | 0.550 | 0.000 | 163 | 0.549 | 0.061 |
| [0.6, 0.7) | 581 | 0.653 | 0.824 | 306 | 0.654 | 0.003 | 236 | 0.649 | 0.178 |
| [0.7, 0.8) | 809 | 0.752 | 0.848 | 378 | 0.751 | 0.005 | 390 | 0.756 | 0.495 |
| [0.8, 0.9) | 1310 | 0.853 | 0.887 | 563 | 0.855 | 0.089 | 1167 | 0.860 | 0.753 |
| [0.9, 1.0) | 5774 | 0.975 | 0.875 | 26483 | 0.986 | 0.357 | 8015 | 0.967 | 0.932 |

## S6 "Stüdyo": yenileme riski (Adım 5b)

- 20 tohum × 1500 üye, 2 yıl. Değerlendirme: kalibrasyon tarihinde (547.5. gün) aktif olan ve 60 gün içinde biten paketler.
- Paket karışımı (HİPOTEZ): 1 Aylık %45 (2500 TL), 3 Aylık %25 (6000 TL), 6 Aylık %15 (10000 TL), 12 Giriş %15 (800 TL); giriş paketi 60 gün sonra biter (hak kalsa da).
- Katılım: düzenli aralıklar (Gamma k = 8), μ_i ~ Gamma(şekil 3, ortalama 4 g); bırakma MBG/NBD tarzı, ilk ziyaret dahil her ziyaretten sonra p ~ Beta(1, 19).
- Gerçek yenileme: paket bittiğinde hayatta olan üye %90 olasılıkla aynı türü yeniler; hayatta olmayan yenilemez.
- M3-sim = MBG/NBD + sonsal simülasyon (`analitik/yenileme.py`, N = 2 000). Kural = son 21 günde en fazla 1 giriş → yenilemez (0/1 skor).
- Riskteki Para hata % = (Σ (1 − P(yenileme)) × fiyat − gerçekleşen kayıp ciro) / gerçekleşen kayıp ciro; gerçekleşen kayıp = yenilenmeyen paketlerin fiyat toplamı.
- Bilinen sınırlamalar: M3, S5'te gelecekteki ziyaretleri ~%11 fazla tahmin etti, simülasyon aynı eğilimi taşıyabilir. Fiyat, kampanya, taşınma gibi davranış dışı yenileme nedenleri modelde yok (S6'da %10 olarak üretilir). Model gerçek yenileme verisiyle kalibre edilmedi (5c).

| Segment | Paket | Yenileme oranı | M3-sim AUC | Kural AUC | M3-sim Brier | Kural Brier | Gerçek kayıp (TL) | M3-sim Riskteki Para hata % | Kural Riskteki Para hata % |
|---|---|---|---|---|---|---|---|---|---|
| Tümü | 224 ± 15 | 0.582 ± 0.029 | 0.827 ± 0.033 | 0.720 ± 0.021 | 0.153 ± 0.016 | 0.241 ± 0.026 | 434115 ± 43725 | -13.2 ± 4.6 | -36.0 ± 4.8 |
| 1 Aylık | 95 ± 9 | 0.689 ± 0.056 | 0.710 ± 0.067 | 0.561 ± 0.042 | 0.187 ± 0.032 | 0.289 ± 0.058 | 73875 ± 15400 | -30.7 ± 11.2 | -73.9 ± 7.2 |
| 3 Aylık | 61 ± 8 | 0.524 ± 0.056 | 0.884 ± 0.048 | 0.789 ± 0.044 | 0.125 ± 0.027 | 0.202 ± 0.050 | 174000 ± 33548 | -10.0 ± 6.4 | -37.3 ± 6.5 |
| 6 Aylık | 26 ± 5 | 0.327 ± 0.111 | 0.950 ± 0.041 | 0.910 ± 0.049 | 0.085 ± 0.046 | 0.120 ± 0.065 | 172000 ± 36216 | -7.1 ± 9.2 | -16.6 ± 8.8 |
| 12 Giriş | 42 ± 4 | 0.577 ± 0.056 | 0.816 ± 0.065 | 0.699 ± 0.054 | 0.161 ± 0.035 | 0.264 ± 0.056 | 14240 ± 2429 | -18.4 ± 12.5 | -49.3 ± 14.2 |
