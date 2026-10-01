"""Adım 5a: model kütüphanesi (veritabanı yok). Tasarım: docs/adim-5-6-tasarim.md

  v1            M0: aralık ~ Normal modeli (MusteriAnalizi.py'nin çekirdeği)
  bgnbd         M1: BG/NBD (Fader, Hardie & Lee, 2005)
  gamma_gamma   M2: Gamma-Gamma harcama modeli
  ozellikler    ziyaret geçmişinden (x, t_x, T, m̄)
  riskteki_para Riskteki Para tanımı

Zaman birimi: gün. Model içi hesaplar float64; para raporlamada Decimal'e çevrilir.
"""
