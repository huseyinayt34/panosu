-- =====================================================================
-- 0002: ÜYELİK PAKETLERİ VE YENİLEME RİSKİ (Adım 5b, tasarım: docs/adim-5b-tasarim.md)
-- BEGIN/COMMIT yok: Alembic her revizyonu kendi işleminde çalıştırır.
-- ("uyelikler" ve "abonelikler" adları kullanıcı üyeliği ve SaaS aboneliği için zaten kullanılıyor.)
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. MÜŞTERİ PAKETLERİ (stüdyo üyelikleri: süre bazlı veya giriş bazlı)
-- ---------------------------------------------------------------------
CREATE TABLE musteri_paketleri (
  paket_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  isletme_id         uuid NOT NULL DEFAULT aktif_isletme(),
  musteri_id         uuid NOT NULL,
  tur                text NOT NULL CHECK (tur IN ('sure','giris')),
  ad                 text NOT NULL,                             -- örn. '6 Aylık', '12 Giriş'
  baslangic_tarihi   date NOT NULL,
  bitis_tarihi       date,                                      -- sure: zorunlu; giris: opsiyonel son kullanma
  giris_hakki        integer,                                   -- giris: zorunlu ve > 0; sure: NULL
  ucret              numeric(12,2) NOT NULL CHECK (ucret >= 0), -- satış anındaki fiyat (fiyatlar sık değişir)
  durum              text NOT NULL DEFAULT 'aktif'
                     CHECK (durum IN ('aktif','bitti','iptal','donduruldu')),
  onceki_paket_id    uuid,                                      -- yenileme zinciri: aynı müşterinin önceki paketi
  dis_kaynak         text,
  dis_kimlik         text,
  olusturma_zamani   timestamptz NOT NULL DEFAULT now(),
  guncelleme_zamani  timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (isletme_id, musteri_id) REFERENCES musteriler (isletme_id, musteri_id),
  UNIQUE (isletme_id, paket_id),                                -- bileşik FK hedefi
  FOREIGN KEY (isletme_id, onceki_paket_id) REFERENCES musteri_paketleri (isletme_id, paket_id),
  CHECK (bitis_tarihi IS NULL OR bitis_tarihi > baslangic_tarihi),
  CHECK (
    (tur = 'sure'  AND bitis_tarihi IS NOT NULL AND giris_hakki IS NULL)
    OR (tur = 'giris' AND giris_hakki IS NOT NULL AND giris_hakki > 0)
  ),
  CHECK ((dis_kaynak IS NULL) = (dis_kimlik IS NULL))
);
CREATE UNIQUE INDEX paket_dis_kimlik_tekil_idx ON musteri_paketleri (isletme_id, dis_kaynak, dis_kimlik)
  WHERE dis_kimlik IS NOT NULL;
CREATE INDEX paket_aktif_bitis_idx ON musteri_paketleri (isletme_id, bitis_tarihi) WHERE durum = 'aktif';
CREATE INDEX paket_musteri_idx ON musteri_paketleri (isletme_id, musteri_id, baslangic_tarihi DESC);

-- ---------------------------------------------------------------------
-- 2. YENİLEME RİSKİ (model çıktısı)
-- ---------------------------------------------------------------------
-- riskteki_para = (1 − p_yenileme) × yenileme_tutari  ("kasaya girecek ya da girmeyecek para")
CREATE TABLE yenileme_riskleri (
  risk_id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  isletme_id         uuid NOT NULL DEFAULT aktif_isletme(),
  musteri_id         uuid NOT NULL,
  paket_id           uuid NOT NULL,
  hesaplama_tarihi   date NOT NULL,
  model_versiyonu    text NOT NULL,                             -- örn. 'mbgnbd-sim-v1'
  kalan_gun          integer,                                   -- süre bazlıda bitişe kalan gün
  kalan_giris        integer,                                   -- giriş bazlıda kalan hak
  p_hayatta_simdi    numeric(5,4) CHECK (p_hayatta_simdi BETWEEN 0 AND 1),
  p_yenileme         numeric(5,4) NOT NULL CHECK (p_yenileme BETWEEN 0 AND 1),
  yenileme_tutari    numeric(12,2) NOT NULL CHECK (yenileme_tutari >= 0),   -- = paketin ucret'i
  riskteki_para      numeric(12,2)
                     GENERATED ALWAYS AS (ROUND((1 - p_yenileme) * yenileme_tutari, 2)) STORED,
  hesaplanma_zamani  timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (isletme_id, musteri_id) REFERENCES musteriler (isletme_id, musteri_id),
  FOREIGN KEY (isletme_id, paket_id) REFERENCES musteri_paketleri (isletme_id, paket_id),
  UNIQUE (isletme_id, paket_id, hesaplama_tarihi, model_versiyonu)
);

-- ---------------------------------------------------------------------
-- 3. TRIGGER'LAR
-- ---------------------------------------------------------------------
CREATE TRIGGER musteri_paketleri_guncelleme_zamani
  BEFORE UPDATE ON musteri_paketleri
  FOR EACH ROW EXECUTE FUNCTION guncelleme_zamani_ayarla();

CREATE TRIGGER musteri_paketleri_denetim
  AFTER INSERT OR UPDATE OR DELETE ON musteri_paketleri
  FOR EACH ROW EXECUTE FUNCTION denetim_kaydi_yaz('paket_id');

-- ---------------------------------------------------------------------
-- 4. ROW-LEVEL SECURITY (faz1'deki kalıp)
-- ---------------------------------------------------------------------
ALTER TABLE musteri_paketleri ENABLE ROW LEVEL SECURITY;
ALTER TABLE musteri_paketleri FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_izolasyonu ON musteri_paketleri
  USING (isletme_id = aktif_isletme()) WITH CHECK (isletme_id = aktif_isletme());

ALTER TABLE yenileme_riskleri ENABLE ROW LEVEL SECURITY;
ALTER TABLE yenileme_riskleri FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_izolasyonu ON yenileme_riskleri
  USING (isletme_id = aktif_isletme()) WITH CHECK (isletme_id = aktif_isletme());

-- ---------------------------------------------------------------------
-- 5. PANEL VIEW'I: her aktif paketin en güncel yenileme riski
-- ---------------------------------------------------------------------
CREATE VIEW v_yenileme_paneli WITH (security_invoker = true) AS
SELECT
  p.isletme_id,
  p.paket_id,
  p.musteri_id,
  m.ad_soyad,
  m.telefon_e164,
  EXISTS (
    SELECT 1 FROM v_gecerli_izinler i
    WHERE i.isletme_id = p.isletme_id AND i.musteri_id = p.musteri_id AND i.kanal = 'whatsapp'
  ) AS whatsapp_izni_var,
  (SELECT max(z.ziyaret_zamani) FROM ziyaretler z
   WHERE z.isletme_id = p.isletme_id AND z.musteri_id = p.musteri_id AND z.durum = 'tamamlandi') AS son_ziyaret,
  p.ad AS paket_adi,
  p.tur,
  p.bitis_tarihi,
  r.kalan_gun,
  r.kalan_giris,
  r.p_yenileme,
  r.yenileme_tutari,
  r.riskteki_para,
  r.hesaplama_tarihi,
  r.model_versiyonu
FROM musteri_paketleri p
JOIN musteriler m
  ON m.isletme_id = p.isletme_id AND m.musteri_id = p.musteri_id AND m.silindi_at IS NULL
JOIN LATERAL (
  SELECT y.*
  FROM yenileme_riskleri y
  WHERE y.isletme_id = p.isletme_id AND y.paket_id = p.paket_id
  ORDER BY y.hesaplama_tarihi DESC, y.hesaplanma_zamani DESC
  LIMIT 1
) r ON true
WHERE p.durum = 'aktif';

-- ---------------------------------------------------------------------
-- 6. YETKİLER (silme yok)
-- ---------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE ON musteri_paketleri, yenileme_riskleri TO panosu_app;
GRANT SELECT ON v_yenileme_paneli TO panosu_app;

COMMENT ON COLUMN musteri_paketleri.ucret IS 'Satış anındaki fiyat; yenileme tutarı olarak kullanılır.';
COMMENT ON COLUMN yenileme_riskleri.riskteki_para IS '(1 - p_yenileme) * yenileme_tutari (otomatik hesaplanır).';
