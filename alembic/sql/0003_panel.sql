-- =====================================================================
-- 0003: PANEL (Adım 7, tasarım: docs/adim-7-tasarim.md)
--   isletme_giderleri : aylık sabit giderler (kâr/zarar ve başabaş için)
--   v_sessiz_uyeler   : aktif paketi olduğu hâlde gelmeyi bırakan üyeler (eşik uçta uygulanır)
-- BEGIN/COMMIT yok: Alembic her revizyonu kendi işleminde çalıştırır.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. İŞLETME GİDERLERİ
-- ---------------------------------------------------------------------
CREATE TABLE isletme_giderleri (
  gider_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  isletme_id         uuid NOT NULL DEFAULT aktif_isletme() REFERENCES isletmeler (isletme_id),
  ay                 date NOT NULL CHECK (EXTRACT(day FROM ay) = 1),          -- ayın ilk günü
  kategori           text NOT NULL CHECK (kategori IN ('kira','personel','faturalar','diger')),
  tutar              numeric(12,2) NOT NULL CHECK (tutar >= 0),
  aciklama           text,
  olusturma_zamani   timestamptz NOT NULL DEFAULT now(),
  guncelleme_zamani  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (isletme_id, ay, kategori)
);

CREATE TRIGGER isletme_giderleri_guncelleme_zamani
  BEFORE UPDATE ON isletme_giderleri
  FOR EACH ROW EXECUTE FUNCTION guncelleme_zamani_ayarla();

CREATE TRIGGER isletme_giderleri_denetim
  AFTER INSERT OR UPDATE OR DELETE ON isletme_giderleri
  FOR EACH ROW EXECUTE FUNCTION denetim_kaydi_yaz('gider_id');

ALTER TABLE isletme_giderleri ENABLE ROW LEVEL SECURITY;
ALTER TABLE isletme_giderleri FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_izolasyonu ON isletme_giderleri
  USING (isletme_id = aktif_isletme()) WITH CHECK (isletme_id = aktif_isletme());

-- ---------------------------------------------------------------------
-- 2. SESSİZ ÜYELER
-- ---------------------------------------------------------------------
-- Aktif paketi olan (durum 'aktif'; süre bazlıda bitis_tarihi ≥ bugün; giriş bazlıda kalan hak > 0 ve son kullanma
-- geçmemiş) ve en güncel yenileme riski kaydında p_hayatta_simdi değeri olan üyeler. "Bugün" ve ziyaret günleri
-- işletmenin yerel saat dilimiyle. Eşik filtresi (p_hayatta_simdi < esik) uçta uygulanır.
CREATE VIEW v_sessiz_uyeler WITH (security_invoker = true) AS
SELECT
  p.isletme_id,
  m.musteri_id,
  m.ad_soyad,
  m.telefon_e164,
  EXISTS (
    SELECT 1 FROM v_gecerli_izinler g
    WHERE g.isletme_id = p.isletme_id AND g.musteri_id = p.musteri_id AND g.kanal = 'whatsapp'
  ) AS whatsapp_izni_var,
  p.paket_id,
  p.ad AS paket_adi,
  p.tur,
  p.bitis_tarihi,
  CASE WHEN p.tur = 'sure'  THEN p.bitis_tarihi - b.gun END                     AS kalan_gun,
  CASE WHEN p.tur = 'giris' THEN GREATEST(p.giris_hakki - k.kullanilan, 0) END  AS kalan_giris,
  sz.son_ziyaret,
  b.gun - (sz.son_ziyaret AT TIME ZONE i.saat_dilimi)::date                      AS son_ziyaretten_gecen_gun,
  r.p_hayatta_simdi,
  r.p_yenileme,
  p.ucret AS paket_ucreti,
  r.riskteki_para,
  r.hesaplama_tarihi
FROM musteri_paketleri p
JOIN isletmeler i ON i.isletme_id = p.isletme_id
CROSS JOIN LATERAL (SELECT (now() AT TIME ZONE i.saat_dilimi)::date AS gun) b
JOIN musteriler m
  ON m.isletme_id = p.isletme_id AND m.musteri_id = p.musteri_id AND m.silindi_at IS NULL
JOIN LATERAL (
  SELECT y.p_hayatta_simdi, y.p_yenileme, y.riskteki_para, y.hesaplama_tarihi
  FROM yenileme_riskleri y
  WHERE y.isletme_id = p.isletme_id AND y.paket_id = p.paket_id
  ORDER BY y.hesaplama_tarihi DESC, y.hesaplanma_zamani DESC
  LIMIT 1
) r ON true
LEFT JOIN LATERAL (
  SELECT max(z.ziyaret_zamani) AS son_ziyaret
  FROM ziyaretler z
  WHERE z.isletme_id = p.isletme_id AND z.musteri_id = p.musteri_id AND z.durum = 'tamamlandi'
) sz ON true
LEFT JOIN LATERAL (
  SELECT count(*) AS kullanilan
  FROM ziyaretler z
  WHERE z.isletme_id = p.isletme_id AND z.musteri_id = p.musteri_id AND z.durum = 'tamamlandi'
    AND (z.ziyaret_zamani AT TIME ZONE i.saat_dilimi)::date >= p.baslangic_tarihi
    AND (p.bitis_tarihi IS NULL OR (z.ziyaret_zamani AT TIME ZONE i.saat_dilimi)::date <= p.bitis_tarihi)
) k ON true
WHERE p.durum = 'aktif'
  AND r.p_hayatta_simdi IS NOT NULL
  AND (
    (p.tur = 'sure' AND p.bitis_tarihi >= b.gun)
    OR (p.tur = 'giris' AND p.giris_hakki - k.kullanilan > 0 AND (p.bitis_tarihi IS NULL OR p.bitis_tarihi >= b.gun))
  );

-- ---------------------------------------------------------------------
-- 3. YETKİLER (silme yok)
-- ---------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE ON isletme_giderleri TO panosu_app;
GRANT SELECT ON v_sessiz_uyeler TO panosu_app;

COMMENT ON COLUMN isletme_giderleri.ay IS 'Ayın ilk günü; giderin ait olduğu ay.';
