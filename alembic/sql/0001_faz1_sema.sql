-- =====================================================================
-- MÜŞTERİ DAVRANIŞ PANOSU - FAZ 1 VERİTABANI ŞEMASI
-- Hedef: PostgreSQL 15+   (view'larda security_invoker için 15 gerekir)
-- Kullanım: BOŞ bir veritabanında tek seferde çalıştırılır.
--   createdb -U postgres panosu
--   psql -U postgres -d panosu -f faz1_sema.sql
--
-- Tasarım ilkeleri
--   * Çok kiracılı (multi-tenant): her iş tablosunda isletme_id + Row-Level Security.
--     Oturum başına: SELECT set_config('app.isletme_id', '<uuid>', true);
--   * Kiracı bütünlüğü: alt tablolar (isletme_id, x_id) BİLEŞİK yabancı anahtarla bağlanır;
--     bir işletmenin satırı, başka işletmenin müşterisine bağlanamaz.
--   * Para: NUMERIC(12,2). Zaman: timestamptz (UTC). Anahtar: UUID.
--   * Kapsam DIŞI (bilinçli): stok, muhasebe, prim, adisyon, randevu takvimi (ERP alanı).
--   * Süperkullanıcı RLS'yi atlar. RLS'yi görmek için: SET ROLE panosu_app;
-- =====================================================================


CREATE EXTENSION IF NOT EXISTS citext;

-- ---------------------------------------------------------------------
-- 0. UYGULAMA ROLÜ (RLS bu role uygulanır)
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'panosu_app') THEN
    CREATE ROLE panosu_app NOLOGIN;
  END IF;
END $$;

-- ---------------------------------------------------------------------
-- 1. OTURUM BAĞLAMI VE ORTAK FONKSİYONLAR
-- ---------------------------------------------------------------------
CREATE FUNCTION aktif_isletme() RETURNS uuid
LANGUAGE sql STABLE AS
$$ SELECT NULLIF(current_setting('app.isletme_id', true), '')::uuid $$;

CREATE FUNCTION aktif_kullanici() RETURNS uuid
LANGUAGE sql STABLE AS
$$ SELECT NULLIF(current_setting('app.kullanici_id', true), '')::uuid $$;

CREATE FUNCTION guncelleme_zamani_ayarla() RETURNS trigger
LANGUAGE plpgsql AS
$$
BEGIN
  NEW.guncelleme_zamani := now();
  RETURN NEW;
END
$$;

-- ---------------------------------------------------------------------
-- 2. GLOBAL TABLOLAR (kiracıya bağlı olmayanlar)
-- ---------------------------------------------------------------------
CREATE TABLE abonelik_planlari (
  plan_kodu       text PRIMARY KEY,
  ad              text NOT NULL,
  aylik_ucret     numeric(12,2) NOT NULL CHECK (aylik_ucret >= 0),
  para_birimi     char(3) NOT NULL DEFAULT 'TRY',
  musteri_limiti  integer CHECK (musteri_limiti > 0),          -- NULL = sınırsız
  aktif_mi        boolean NOT NULL DEFAULT true
);

-- Yer tutucu: gerçek plan/fiyatlar Faz 0 görüşmelerinden sonra belirlenecek.
INSERT INTO abonelik_planlari (plan_kodu, ad, aylik_ucret, musteri_limiti)
VALUES ('ucretsiz', 'Ücretsiz', 0, 50);

CREATE TABLE kullanicilar (
  kullanici_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dis_kimlik_id      text UNIQUE,                               -- Clerk/Auth0 vb. kullanıcı kimliği
  eposta             citext NOT NULL UNIQUE,
  ad_soyad           text NOT NULL,
  son_giris_zamani   timestamptz,
  olusturma_zamani   timestamptz NOT NULL DEFAULT now(),
  guncelleme_zamani  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE isletmeler (
  isletme_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ad                 text NOT NULL,
  sektor             text CHECK (sektor IN ('berber','kuafor','guzellik','kafe','spor_salonu','diger')),
  para_birimi        char(3) NOT NULL DEFAULT 'TRY',            -- tüm tutarlar bu para biriminde
  saat_dilimi        text NOT NULL DEFAULT 'Europe/Istanbul',
  durum              text NOT NULL DEFAULT 'aktif' CHECK (durum IN ('aktif','askida','kapali')),
  olusturma_zamani   timestamptz NOT NULL DEFAULT now(),
  guncelleme_zamani  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE uyelikler (
  isletme_id         uuid NOT NULL REFERENCES isletmeler (isletme_id) ON DELETE CASCADE,
  kullanici_id       uuid NOT NULL REFERENCES kullanicilar (kullanici_id) ON DELETE CASCADE,
  rol                text NOT NULL CHECK (rol IN ('sahip','yonetici','calisan')),
  olusturma_zamani   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (isletme_id, kullanici_id)
);
CREATE INDEX uyelik_kullanici_idx ON uyelikler (kullanici_id);

CREATE TABLE abonelikler (
  abonelik_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  isletme_id           uuid NOT NULL DEFAULT aktif_isletme() REFERENCES isletmeler (isletme_id),
  plan_kodu            text NOT NULL REFERENCES abonelik_planlari (plan_kodu),
  durum                text NOT NULL CHECK (durum IN ('deneme','aktif','odeme_bekliyor','iptal')),
  donem_baslangic      date NOT NULL,
  donem_bitis          date,                                    -- NULL = süresiz (ücretsiz plan)
  odeme_saglayici_ref  text,                                    -- iyzico abonelik referansı
  olusturma_zamani     timestamptz NOT NULL DEFAULT now(),
  guncelleme_zamani    timestamptz NOT NULL DEFAULT now(),
  CHECK (donem_bitis IS NULL OR donem_bitis > donem_baslangic)
);
-- Bir işletmenin aynı anda tek geçerli aboneliği olabilir
CREATE UNIQUE INDEX abonelik_tek_gecerli_idx ON abonelikler (isletme_id)
  WHERE durum IN ('deneme','aktif','odeme_bekliyor');

-- ---------------------------------------------------------------------
-- 3. ÇEKİRDEK İŞ TABLOLARI
-- ---------------------------------------------------------------------
CREATE TABLE musteriler (
  musteri_id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  isletme_id            uuid NOT NULL DEFAULT aktif_isletme() REFERENCES isletmeler (isletme_id),
  ad_soyad              text NOT NULL,
  telefon_e164          text CHECK (telefon_e164 ~ '^\+[1-9][0-9]{7,14}$'),   -- örn. +905321234567
  eposta                citext,
  telegram_chat_id      bigint,
  kaynak                text NOT NULL DEFAULT 'manuel'
                        CHECK (kaynak IN ('manuel','csv','telegram','entegrasyon')),
  dis_kaynak            text,                                   -- içe aktarma kaynağı (örn. 'csv:2026-10')
  dis_kimlik            text,                                   -- kaynak sistemdeki kimlik (tekrar yüklemeyi güvenli yapar)
  notlar                text,
  silindi_at            timestamptz,                            -- soft delete
  anonimlestirildi_at   timestamptz,                            -- KVKK silme/anonimleştirme
  olusturma_zamani      timestamptz NOT NULL DEFAULT now(),
  guncelleme_zamani     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (isletme_id, musteri_id),                              -- bileşik FK hedefi
  CHECK ((dis_kaynak IS NULL) = (dis_kimlik IS NULL))
);
CREATE UNIQUE INDEX musteri_telefon_tekil_idx ON musteriler (isletme_id, telefon_e164)
  WHERE telefon_e164 IS NOT NULL AND silindi_at IS NULL;
CREATE UNIQUE INDEX musteri_telegram_tekil_idx ON musteriler (isletme_id, telegram_chat_id)
  WHERE telegram_chat_id IS NOT NULL AND silindi_at IS NULL;
CREATE UNIQUE INDEX musteri_dis_kimlik_tekil_idx ON musteriler (isletme_id, dis_kaynak, dis_kimlik)
  WHERE dis_kimlik IS NOT NULL;
CREATE INDEX musteri_isletme_idx ON musteriler (isletme_id) WHERE silindi_at IS NULL;

CREATE TABLE hizmetler (
  hizmet_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  isletme_id          uuid NOT NULL DEFAULT aktif_isletme() REFERENCES isletmeler (isletme_id),
  ad                  text NOT NULL,                            -- örn. 'Saç Kesimi', 'Sakal', 'Filtre Kahve'
  kategori            text,                                     -- örn. 'Kesim', 'Boya', 'Bakım', 'İçecek'
  liste_fiyati        numeric(12,2) CHECK (liste_fiyati >= 0),  -- varsayılan fiyat; gerçek tutar kalemde tutulur
  sure_dk             integer CHECK (sure_dk > 0),
  aktif_mi            boolean NOT NULL DEFAULT true,
  olusturma_zamani    timestamptz NOT NULL DEFAULT now(),
  guncelleme_zamani   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (isletme_id, hizmet_id),
  UNIQUE (isletme_id, ad)
);

-- Ziyaret = müşterinin işletmede bir kez bulunması.
-- toplam_tutar: müşterinin O ZİYARETTE ÖDEDİĞİ nihai tutar (ciro için tek doğruluk kaynağı).
-- Kalem dökümü (ziyaret_kalemleri) opsiyoneldir: CSV'de sadece toplam varsa kalem girilmez.
-- Sadece tarih bilinen kayıtlar için ziyaret_zamani = o günün 12:00'si (işletme yerel saati).
CREATE TABLE ziyaretler (
  ziyaret_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  isletme_id          uuid NOT NULL DEFAULT aktif_isletme(),
  musteri_id          uuid NOT NULL,
  ziyaret_zamani      timestamptz NOT NULL,
  durum               text NOT NULL DEFAULT 'tamamlandi'
                      CHECK (durum IN ('tamamlandi','iptal','gelmedi')),   -- churn yalnız 'tamamlandi' ile hesaplanır
  toplam_tutar        numeric(12,2) NOT NULL DEFAULT 0 CHECK (toplam_tutar >= 0),
  odeme_yontemi       text CHECK (odeme_yontemi IN ('nakit','kart','havale','diger')),
  kaynak              text NOT NULL DEFAULT 'manuel'
                      CHECK (kaynak IN ('manuel','csv','telegram','entegrasyon')),
  dis_kaynak          text,
  dis_kimlik          text,
  notlar              text,
  olusturma_zamani    timestamptz NOT NULL DEFAULT now(),
  guncelleme_zamani   timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (isletme_id, musteri_id) REFERENCES musteriler (isletme_id, musteri_id),
  UNIQUE (isletme_id, ziyaret_id),
  CHECK ((dis_kaynak IS NULL) = (dis_kimlik IS NULL))
);
CREATE UNIQUE INDEX ziyaret_dis_kimlik_tekil_idx ON ziyaretler (isletme_id, dis_kaynak, dis_kimlik)
  WHERE dis_kimlik IS NOT NULL;
CREATE INDEX ziyaret_musteri_zaman_idx ON ziyaretler (isletme_id, musteri_id, ziyaret_zamani DESC)
  WHERE durum = 'tamamlandi';
CREATE INDEX ziyaret_isletme_zaman_idx ON ziyaretler (isletme_id, ziyaret_zamani DESC);

CREATE TABLE ziyaret_kalemleri (
  kalem_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  isletme_id       uuid NOT NULL DEFAULT aktif_isletme(),
  ziyaret_id       uuid NOT NULL,
  hizmet_id        uuid,                                        -- NULL = katalogda olmayan serbest kalem
  aciklama         text,
  adet             integer NOT NULL DEFAULT 1 CHECK (adet > 0),
  birim_fiyat      numeric(12,2) NOT NULL CHECK (birim_fiyat >= 0),
  indirim_tutari   numeric(12,2) NOT NULL DEFAULT 0 CHECK (indirim_tutari >= 0),
  tutar            numeric(12,2) GENERATED ALWAYS AS (adet * birim_fiyat - indirim_tutari) STORED,
  olusturma_zamani timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (isletme_id, ziyaret_id) REFERENCES ziyaretler (isletme_id, ziyaret_id) ON DELETE CASCADE,
  FOREIGN KEY (isletme_id, hizmet_id)  REFERENCES hizmetler (isletme_id, hizmet_id),
  CHECK (hizmet_id IS NOT NULL OR aciklama IS NOT NULL),
  CHECK (adet * birim_fiyat >= indirim_tutari)
);
CREATE INDEX kalem_ziyaret_idx ON ziyaret_kalemleri (isletme_id, ziyaret_id);
CREATE INDEX kalem_hizmet_idx  ON ziyaret_kalemleri (isletme_id, hizmet_id);

-- ---------------------------------------------------------------------
-- 4. İLETİŞİM İZNİ (KVKK / ticari ileti) - eklemeli kayıt, geçmiş silinmez
-- ---------------------------------------------------------------------
CREATE TABLE musteri_izinleri (
  izin_id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  isletme_id              uuid NOT NULL DEFAULT aktif_isletme(),
  musteri_id              uuid NOT NULL,
  kanal                   text NOT NULL CHECK (kanal IN ('whatsapp','sms','telegram','eposta')),
  durum                   text NOT NULL CHECK (durum IN ('verildi','geri_cekildi')),
  kaynak                  text NOT NULL
                          CHECK (kaynak IN ('yazili_form','telegram_bot','iys','isletme_beyani','diger')),
  kayit_zamani            timestamptz NOT NULL DEFAULT now(),
  kaydeden_kullanici_id   uuid REFERENCES kullanicilar (kullanici_id),
  FOREIGN KEY (isletme_id, musteri_id) REFERENCES musteriler (isletme_id, musteri_id)
);
CREATE INDEX izin_guncel_idx ON musteri_izinleri (isletme_id, musteri_id, kanal, kayit_zamani DESC);

-- Her müşteri+kanal için EN SON kayıt 'verildi' ise izin geçerlidir.
CREATE VIEW v_gecerli_izinler WITH (security_invoker = true) AS
SELECT t.isletme_id, t.musteri_id, t.kanal, t.kayit_zamani AS izin_zamani
FROM (
  SELECT DISTINCT ON (isletme_id, musteri_id, kanal) *
  FROM musteri_izinleri
  ORDER BY isletme_id, musteri_id, kanal, kayit_zamani DESC
) t
WHERE t.durum = 'verildi';

-- ---------------------------------------------------------------------
-- 5. MODEL ÇIKTISI: CHURN RİSKİ VE "RİSKTEKİ PARA"
-- ---------------------------------------------------------------------
-- Tanımlar (hesaplamayı uygulama katmanı yapar, model_versiyonu ile birlikte saklanır):
--   ort_sepet_tutari     = müşterinin tamamlanan ziyaretlerinin ortalama tutarı
--   beklenen_aylik_ciro  = ort_sepet_tutari * 30 / ort_aralik_gun   (normal ritminde ayda bıraktığı para)
--   kacirilan_ciro       = ort_sepet_tutari * max(0, gecen_gun / ort_aralik_gun - 1)
--                          ("gelmesi gerekirken gelmediği için şu ana kadar kaçan ciro")
--   riskteki_para        = churn_riski * beklenen_aylik_ciro   (SÜTUN OLARAK OTOMATİK HESAPLANIR)
CREATE TABLE churn_skorlari (
  skor_id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  isletme_id              uuid NOT NULL DEFAULT aktif_isletme(),
  musteri_id              uuid NOT NULL,
  hesaplama_tarihi        date NOT NULL,
  model_versiyonu         text NOT NULL,
  ziyaret_sayisi          integer NOT NULL CHECK (ziyaret_sayisi >= 0),
  ort_aralik_gun          numeric(8,2),
  std_aralik_gun          numeric(8,2),
  son_gelisten_gecen_gun  integer NOT NULL CHECK (son_gelisten_gecen_gun >= 0),
  churn_riski             numeric(5,4) CHECK (churn_riski BETWEEN 0 AND 1),
  segment                 text NOT NULL
                          CHECK (segment IN ('GUVENLI','IZLENMELI','YUKSEK_RISK','KRITIK','YETERSIZ_VERI')),
  ort_sepet_tutari        numeric(12,2),
  beklenen_aylik_ciro     numeric(12,2),
  kacirilan_ciro          numeric(12,2),
  riskteki_para           numeric(12,2)
                          GENERATED ALWAYS AS (ROUND(churn_riski * beklenen_aylik_ciro, 2)) STORED,
  hesaplanma_zamani       timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (isletme_id, musteri_id) REFERENCES musteriler (isletme_id, musteri_id),
  UNIQUE (isletme_id, skor_id),
  UNIQUE (isletme_id, musteri_id, hesaplama_tarihi, model_versiyonu),
  CHECK ((segment = 'YETERSIZ_VERI') = (churn_riski IS NULL))
);
CREATE INDEX skor_panel_idx ON churn_skorlari
  (isletme_id, hesaplama_tarihi DESC, riskteki_para DESC NULLS LAST);

-- ---------------------------------------------------------------------
-- 6. KAMPANYA, MESAJ VE GERİ KAZANIM (ROI ölçümü)
-- ---------------------------------------------------------------------
CREATE TABLE kampanyalar (
  kampanya_id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  isletme_id              uuid NOT NULL DEFAULT aktif_isletme() REFERENCES isletmeler (isletme_id),
  ad                      text NOT NULL,
  tur                     text NOT NULL DEFAULT 'geri_kazanma'
                          CHECK (tur IN ('geri_kazanma','ozel_gun','diger')),
  varsayilan_kanal        text NOT NULL DEFAULT 'whatsapp'
                          CHECK (varsayilan_kanal IN ('whatsapp','sms','telegram','eposta')),
  mesaj_sablonu           text NOT NULL,                        -- örn. 'Merhaba {ad}, seni özledik! ...'
  atif_penceresi_gun      integer NOT NULL DEFAULT 14 CHECK (atif_penceresi_gun BETWEEN 1 AND 90),
  durum                   text NOT NULL DEFAULT 'taslak' CHECK (durum IN ('taslak','aktif','arsiv')),
  olusturan_kullanici_id  uuid REFERENCES kullanicilar (kullanici_id),
  olusturma_zamani        timestamptz NOT NULL DEFAULT now(),
  guncelleme_zamani       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (isletme_id, kampanya_id)
);

CREATE TABLE mesaj_gonderimleri (
  gonderim_id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  isletme_id               uuid NOT NULL DEFAULT aktif_isletme(),
  musteri_id               uuid NOT NULL,
  kampanya_id              uuid,
  skor_id                  uuid,                                -- mesajı tetikleyen risk skoru
  kanal                    text NOT NULL CHECK (kanal IN ('whatsapp','sms','telegram','eposta')),
  durum                    text NOT NULL DEFAULT 'hazirlandi'
                           CHECK (durum IN ('hazirlandi','gonderildi','iletildi','basarisiz')),
  mesaj_metni              text NOT NULL,
  hazirlayan_kullanici_id  uuid REFERENCES kullanicilar (kullanici_id),
  olusturma_zamani         timestamptz NOT NULL DEFAULT now(),
  gonderim_zamani          timestamptz,
  dis_mesaj_id             text,                                -- WhatsApp/SMS sağlayıcı mesaj kimliği
  hata_mesaji              text,
  FOREIGN KEY (isletme_id, musteri_id)  REFERENCES musteriler (isletme_id, musteri_id),
  FOREIGN KEY (isletme_id, kampanya_id) REFERENCES kampanyalar (isletme_id, kampanya_id),
  FOREIGN KEY (isletme_id, skor_id)     REFERENCES churn_skorlari (isletme_id, skor_id),
  UNIQUE (isletme_id, gonderim_id),
  CHECK (durum NOT IN ('gonderildi','iletildi') OR gonderim_zamani IS NOT NULL)
);
CREATE INDEX mesaj_musteri_idx ON mesaj_gonderimleri (isletme_id, musteri_id, olusturma_zamani DESC);

-- Geçerli izni olmayan müşteri için mesaj kaydı OLUŞTURULAMAZ.
CREATE FUNCTION izinsiz_mesaji_engelle() RETURNS trigger
LANGUAGE plpgsql AS
$$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM v_gecerli_izinler v
    WHERE v.isletme_id = NEW.isletme_id
      AND v.musteri_id = NEW.musteri_id
      AND v.kanal = NEW.kanal
  ) THEN
    RAISE EXCEPTION 'Müşteri % için % kanalında geçerli iletişim izni yok', NEW.musteri_id, NEW.kanal
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END
$$;

CREATE TRIGGER mesaj_izin_kontrol
  BEFORE INSERT ON mesaj_gonderimleri
  FOR EACH ROW EXECUTE FUNCTION izinsiz_mesaji_engelle();

-- Bir ziyaret en fazla bir mesaja, bir mesaj en fazla bir ziyarete atfedilir (ilk-temas atfı).
CREATE TABLE geri_kazanimlar (
  geri_kazanim_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  isletme_id           uuid NOT NULL DEFAULT aktif_isletme(),
  gonderim_id          uuid NOT NULL,
  ziyaret_id           uuid NOT NULL,
  geri_kazanilan_ciro  numeric(12,2) NOT NULL CHECK (geri_kazanilan_ciro >= 0),
  gun_farki            integer NOT NULL CHECK (gun_farki >= 0),
  olusturma_zamani     timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (isletme_id, gonderim_id) REFERENCES mesaj_gonderimleri (isletme_id, gonderim_id),
  FOREIGN KEY (isletme_id, ziyaret_id)  REFERENCES ziyaretler (isletme_id, ziyaret_id),
  UNIQUE (isletme_id, gonderim_id),
  UNIQUE (isletme_id, ziyaret_id)
);

-- ---------------------------------------------------------------------
-- 7. DENETİM KAYDI
-- ---------------------------------------------------------------------
CREATE TABLE denetim_kayitlari (
  denetim_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  isletme_id   uuid NOT NULL DEFAULT aktif_isletme(),
  kullanici_id uuid,
  eylem        text NOT NULL,
  tablo_adi    text NOT NULL,
  kayit_id     uuid,
  eski_deger   jsonb,
  yeni_deger   jsonb,
  zaman        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX denetim_kayit_idx ON denetim_kayitlari (isletme_id, tablo_adi, kayit_id, zaman DESC);

-- TG_ARGV[0] = birincil anahtar sütunu; TG_ARGV[1] = denetim kaydından ÇIKARILACAK (kişisel veri) sütunlar
CREATE FUNCTION denetim_kaydi_yaz() RETURNS trigger
LANGUAGE plpgsql AS
$$
DECLARE
  v_gizli text[] := CASE WHEN TG_ARGV[1] IS NULL THEN ARRAY[]::text[]
                         ELSE string_to_array(TG_ARGV[1], ',') END;
  v_eski  jsonb;
  v_yeni  jsonb;
  v_satir jsonb;
BEGIN
  IF TG_OP IN ('UPDATE','DELETE') THEN v_eski := to_jsonb(OLD) - v_gizli; END IF;
  IF TG_OP IN ('INSERT','UPDATE') THEN v_yeni := to_jsonb(NEW) - v_gizli; END IF;
  v_satir := COALESCE(v_yeni, v_eski);

  INSERT INTO denetim_kayitlari (isletme_id, kullanici_id, eylem, tablo_adi, kayit_id, eski_deger, yeni_deger)
  VALUES (
    (v_satir ->> 'isletme_id')::uuid,
    aktif_kullanici(),
    TG_OP,
    TG_TABLE_NAME,
    (v_satir ->> TG_ARGV[0])::uuid,
    v_eski,
    v_yeni
  );
  RETURN NULL;
END
$$;

CREATE TRIGGER musteriler_denetim
  AFTER INSERT OR UPDATE OR DELETE ON musteriler
  FOR EACH ROW EXECUTE FUNCTION
  denetim_kaydi_yaz('musteri_id', 'ad_soyad,telefon_e164,eposta,telegram_chat_id,notlar,dis_kimlik');

CREATE TRIGGER hizmetler_denetim
  AFTER INSERT OR UPDATE OR DELETE ON hizmetler
  FOR EACH ROW EXECUTE FUNCTION denetim_kaydi_yaz('hizmet_id');

CREATE TRIGGER kampanyalar_denetim
  AFTER INSERT OR UPDATE OR DELETE ON kampanyalar
  FOR EACH ROW EXECUTE FUNCTION denetim_kaydi_yaz('kampanya_id');

-- Ziyaret düzeltmeleri (tutar/durum değişikliği) para ile ilgili olduğu için izlenir; ilk eklemeler değil.
CREATE TRIGGER ziyaretler_denetim
  AFTER UPDATE OR DELETE ON ziyaretler
  FOR EACH ROW EXECUTE FUNCTION denetim_kaydi_yaz('ziyaret_id', 'notlar');

-- ---------------------------------------------------------------------
-- 8. guncelleme_zamani OTOMATİK GÜNCELLEME
-- ---------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['kullanicilar','isletmeler','abonelikler','musteriler',
                           'hizmetler','ziyaretler','kampanyalar'] LOOP
    EXECUTE format(
      'CREATE TRIGGER %I BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION guncelleme_zamani_ayarla()',
      t || '_guncelleme_zamani', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------
-- 9. ROW-LEVEL SECURITY (kiracı izolasyonu)
-- ---------------------------------------------------------------------
-- isletme_id sütunu olan tüm iş tabloları: yalnız aktif işletmenin satırları görünür/yazılır.
-- app.isletme_id ayarlı değilse HİÇBİR satır görünmez (güvenli varsayılan).
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['abonelikler','musteriler','hizmetler','ziyaretler','ziyaret_kalemleri',
                           'musteri_izinleri','churn_skorlari','kampanyalar','mesaj_gonderimleri',
                           'geri_kazanimlar','denetim_kayitlari'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_izolasyonu ON %I USING (isletme_id = aktif_isletme()) WITH CHECK (isletme_id = aktif_isletme())',
      t);
  END LOOP;
END $$;

-- isletmeler: aktif işletme + kullanıcının üyesi olduğu işletmeler (giriş sonrası işletme seçimi için)
ALTER TABLE isletmeler ENABLE ROW LEVEL SECURITY;
ALTER TABLE isletmeler FORCE ROW LEVEL SECURITY;
CREATE POLICY isletme_erisim ON isletmeler
  USING (
    isletme_id = aktif_isletme()
    OR isletme_id IN (SELECT u.isletme_id FROM uyelikler u WHERE u.kullanici_id = aktif_kullanici())
  )
  WITH CHECK (isletme_id = aktif_isletme());

-- uyelikler: okuma = aktif işletmenin üyeleri VEYA kullanıcının kendi üyelikleri; yazma = yalnız aktif işletme
ALTER TABLE uyelikler ENABLE ROW LEVEL SECURITY;
ALTER TABLE uyelikler FORCE ROW LEVEL SECURITY;
CREATE POLICY uyelik_okuma ON uyelikler FOR SELECT
  USING (isletme_id = aktif_isletme() OR kullanici_id = aktif_kullanici());
CREATE POLICY uyelik_yazma ON uyelikler
  USING (isletme_id = aktif_isletme())
  WITH CHECK (isletme_id = aktif_isletme());

-- kullanicilar: kendi kaydı + aktif işletmenin üyeleri. Kayıt (signup) sahip/yönetici bağlantısıyla yapılır.
ALTER TABLE kullanicilar ENABLE ROW LEVEL SECURITY;
CREATE POLICY kullanici_erisim ON kullanicilar
  USING (
    kullanici_id = aktif_kullanici()
    OR kullanici_id IN (SELECT u.kullanici_id FROM uyelikler u WHERE u.isletme_id = aktif_isletme())
  )
  WITH CHECK (kullanici_id = aktif_kullanici());

-- ---------------------------------------------------------------------
-- 10. ANALİZ VIEW'LARI  (security_invoker: RLS view'a da uygulanır)
-- ---------------------------------------------------------------------
CREATE VIEW v_musteri_ozet WITH (security_invoker = true) AS
SELECT
  m.isletme_id,
  m.musteri_id,
  m.ad_soyad,
  m.telefon_e164,
  count(z.ziyaret_id)                                             AS ziyaret_sayisi,
  min(z.ziyaret_zamani)                                           AS ilk_ziyaret,
  max(z.ziyaret_zamani)                                           AS son_ziyaret,
  COALESCE(sum(z.toplam_tutar), 0)::numeric(12,2)                 AS toplam_ciro,
  round(avg(z.toplam_tutar), 2)                                   AS ort_sepet_tutari,
  COALESCE(sum(z.toplam_tutar)
           FILTER (WHERE z.ziyaret_zamani >= now() - interval '90 days'), 0)::numeric(12,2)
                                                                  AS ciro_son_90_gun
FROM musteriler m
LEFT JOIN ziyaretler z
  ON z.isletme_id = m.isletme_id AND z.musteri_id = m.musteri_id AND z.durum = 'tamamlandi'
WHERE m.silindi_at IS NULL
GROUP BY m.isletme_id, m.musteri_id, m.ad_soyad, m.telefon_e164;

-- Müşteri x hizmet: "Ahmet en çok ne alıyor?" (kişiselleştirilmiş mesaj için)
CREATE VIEW v_musteri_hizmet_dagilimi WITH (security_invoker = true) AS
SELECT
  z.isletme_id,
  z.musteri_id,
  h.hizmet_id,
  COALESCE(h.ad, k.aciklama, 'Diğer')  AS hizmet_adi,
  sum(k.adet)                          AS adet,
  sum(k.tutar)                         AS ciro,
  max(z.ziyaret_zamani)                AS son_alim
FROM ziyaret_kalemleri k
JOIN ziyaretler z
  ON z.isletme_id = k.isletme_id AND z.ziyaret_id = k.ziyaret_id AND z.durum = 'tamamlandi'
LEFT JOIN hizmetler h
  ON h.isletme_id = k.isletme_id AND h.hizmet_id = k.hizmet_id
GROUP BY z.isletme_id, z.musteri_id, h.hizmet_id, COALESCE(h.ad, k.aciklama, 'Diğer');

-- Her müşterinin en güncel skoru (aynı gün birden çok model varsa en son hesaplanan)
CREATE VIEW v_guncel_churn_skorlari WITH (security_invoker = true) AS
SELECT DISTINCT ON (isletme_id, musteri_id) *
FROM churn_skorlari
ORDER BY isletme_id, musteri_id, hesaplama_tarihi DESC, hesaplanma_zamani DESC;

-- ANA PANEL: "Riskteki Para" listesi. Uygulama ORDER BY riskteki_para DESC ile çeker.
CREATE VIEW v_riskteki_para_paneli WITH (security_invoker = true) AS
SELECT
  s.isletme_id,
  s.musteri_id,
  m.ad_soyad,
  m.telefon_e164,
  s.hesaplama_tarihi,
  s.segment,
  s.churn_riski,
  s.son_gelisten_gecen_gun,
  s.ort_sepet_tutari,
  s.beklenen_aylik_ciro,
  s.kacirilan_ciro,
  s.riskteki_para,
  h.hizmet_adi AS en_cok_alinan_hizmet,
  EXISTS (
    SELECT 1 FROM v_gecerli_izinler i
    WHERE i.isletme_id = s.isletme_id AND i.musteri_id = s.musteri_id AND i.kanal = 'whatsapp'
  ) AS whatsapp_izni_var,
  (SELECT max(g.gonderim_zamani) FROM mesaj_gonderimleri g
   WHERE g.isletme_id = s.isletme_id AND g.musteri_id = s.musteri_id
     AND g.durum IN ('gonderildi','iletildi')) AS son_mesaj_zamani
FROM v_guncel_churn_skorlari s
JOIN musteriler m
  ON m.isletme_id = s.isletme_id AND m.musteri_id = s.musteri_id AND m.silindi_at IS NULL
LEFT JOIN LATERAL (
  SELECT d.hizmet_adi
  FROM v_musteri_hizmet_dagilimi d
  WHERE d.isletme_id = s.isletme_id AND d.musteri_id = s.musteri_id
  ORDER BY d.adet DESC, d.son_alim DESC
  LIMIT 1
) h ON true
WHERE s.segment IN ('IZLENMELI','YUKSEK_RISK','KRITIK');

-- Aylık geri kazanım özeti: aboneliği savunan rakam ("bu ay senin için X TL geri kazandık")
CREATE VIEW v_geri_kazanim_ozeti WITH (security_invoker = true) AS
SELECT
  gk.isletme_id,
  date_trunc('month', z.ziyaret_zamani)::date AS ay,
  count(DISTINCT z.musteri_id)                AS geri_kazanilan_musteri,
  sum(gk.geri_kazanilan_ciro)                 AS geri_kazanilan_ciro
FROM geri_kazanimlar gk
JOIN ziyaretler z ON z.isletme_id = gk.isletme_id AND z.ziyaret_id = gk.ziyaret_id
GROUP BY gk.isletme_id, date_trunc('month', z.ziyaret_zamani)::date;

-- Veri kalitesi: kalem toplamı ile ziyaret toplamı uyuşmayanlar (CSV hataları için)
CREATE VIEW v_ziyaret_tutar_uyumsuzluklari WITH (security_invoker = true) AS
SELECT z.isletme_id, z.ziyaret_id, z.musteri_id, z.toplam_tutar, k.kalem_toplami
FROM ziyaretler z
JOIN (
  SELECT isletme_id, ziyaret_id, sum(tutar) AS kalem_toplami
  FROM ziyaret_kalemleri
  GROUP BY isletme_id, ziyaret_id
) k ON k.isletme_id = z.isletme_id AND k.ziyaret_id = z.ziyaret_id
WHERE z.toplam_tutar <> k.kalem_toplami;

-- ---------------------------------------------------------------------
-- 11. İŞ FONKSİYONLARI
-- ---------------------------------------------------------------------
-- Yeni işletme + sahip üyeliği + ücretsiz abonelik. İşlemin (transaction) geri kalanı için
-- aktif işletmeyi yeni işletmeye ayarlar; bu yüzden BEGIN...COMMIT içinde çağrılmalıdır.
CREATE FUNCTION isletme_olustur(p_ad text, p_kullanici_id uuid, p_sektor text DEFAULT NULL)
RETURNS uuid
LANGUAGE plpgsql AS
$$
DECLARE
  v_id uuid := gen_random_uuid();
BEGIN
  PERFORM set_config('app.isletme_id', v_id::text, true);

  INSERT INTO isletmeler (isletme_id, ad, sektor) VALUES (v_id, p_ad, p_sektor);
  INSERT INTO uyelikler (isletme_id, kullanici_id, rol) VALUES (v_id, p_kullanici_id, 'sahip');
  INSERT INTO abonelikler (isletme_id, plan_kodu, durum, donem_baslangic)
  VALUES (v_id, 'ucretsiz', 'aktif', current_date);

  RETURN v_id;
END
$$;

-- Gönderilen mesajlardan sonra, kampanyanın atıf penceresi içinde gelen İLK tamamlanmış ziyareti
-- "geri kazanım" olarak eşler. Yeni eşleşen kayıt sayısını döndürür. Gece işinde çağrılır.
CREATE FUNCTION geri_kazanimlari_esle() RETURNS integer
LANGUAGE plpgsql AS
$$
DECLARE
  v_adet integer;
BEGIN
  INSERT INTO geri_kazanimlar (isletme_id, gonderim_id, ziyaret_id, geri_kazanilan_ciro, gun_farki)
  SELECT g.isletme_id, g.gonderim_id, zz.ziyaret_id, zz.toplam_tutar,
         GREATEST(0, zz.ziyaret_zamani::date - g.gonderim_zamani::date)
  FROM mesaj_gonderimleri g
  LEFT JOIN kampanyalar k
    ON k.isletme_id = g.isletme_id AND k.kampanya_id = g.kampanya_id
  JOIN LATERAL (
    SELECT z.ziyaret_id, z.toplam_tutar, z.ziyaret_zamani
    FROM ziyaretler z
    WHERE z.isletme_id = g.isletme_id
      AND z.musteri_id = g.musteri_id
      AND z.durum = 'tamamlandi'
      AND z.ziyaret_zamani >  g.gonderim_zamani
      AND z.ziyaret_zamani <= g.gonderim_zamani + make_interval(days => COALESCE(k.atif_penceresi_gun, 14))
    ORDER BY z.ziyaret_zamani
    LIMIT 1
  ) zz ON true
  WHERE g.isletme_id = aktif_isletme()
    AND g.durum IN ('gonderildi','iletildi')
    AND g.gonderim_zamani IS NOT NULL
  ORDER BY g.gonderim_zamani
  ON CONFLICT DO NOTHING;

  GET DIAGNOSTICS v_adet = ROW_COUNT;
  RETURN v_adet;
END
$$;

-- KVKK silme talebi: kişisel veriyi temizler, ciro/istatistik geçmişini korur.
CREATE FUNCTION musteri_anonimlestir(p_musteri_id uuid) RETURNS void
LANGUAGE plpgsql AS
$$
BEGIN
  UPDATE musteriler
  SET ad_soyad = 'Anonim Müşteri',
      telefon_e164 = NULL,
      eposta = NULL,
      telegram_chat_id = NULL,
      notlar = NULL,
      dis_kaynak = NULL,
      dis_kimlik = NULL,
      anonimlestirildi_at = now(),
      silindi_at = COALESCE(silindi_at, now())
  WHERE musteri_id = p_musteri_id AND isletme_id = aktif_isletme();

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Müşteri bulunamadı: %', p_musteri_id;
  END IF;

  UPDATE mesaj_gonderimleri SET mesaj_metni = '[silindi]'
  WHERE musteri_id = p_musteri_id AND isletme_id = aktif_isletme();

  UPDATE ziyaretler SET notlar = NULL
  WHERE musteri_id = p_musteri_id AND isletme_id = aktif_isletme();
END
$$;

-- ---------------------------------------------------------------------
-- 12. YETKİLER (uygulama rolü)
-- ---------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO panosu_app;

GRANT SELECT, INSERT, UPDATE ON
  isletmeler, uyelikler, abonelikler, musteriler, hizmetler, ziyaretler, ziyaret_kalemleri,
  musteri_izinleri, churn_skorlari, kampanyalar, mesaj_gonderimleri, geri_kazanimlar
TO panosu_app;

GRANT DELETE ON uyelikler, ziyaret_kalemleri TO panosu_app;   -- diğer tablolarda silme YOK (soft delete)
GRANT SELECT, UPDATE ON kullanicilar TO panosu_app;
GRANT SELECT ON abonelik_planlari TO panosu_app;
GRANT SELECT, INSERT ON denetim_kayitlari TO panosu_app;     -- denetim kaydı değiştirilemez/silinemez

GRANT SELECT ON
  v_gecerli_izinler, v_musteri_ozet, v_musteri_hizmet_dagilimi, v_guncel_churn_skorlari,
  v_riskteki_para_paneli, v_geri_kazanim_ozeti, v_ziyaret_tutar_uyumsuzluklari
TO panosu_app;

-- ---------------------------------------------------------------------
-- AÇIKLAMALAR
-- ---------------------------------------------------------------------
COMMENT ON COLUMN ziyaretler.toplam_tutar IS 'Müşterinin bu ziyarette ödediği nihai tutar; ciro için tek doğruluk kaynağı.';
COMMENT ON COLUMN churn_skorlari.riskteki_para IS 'churn_riski * beklenen_aylik_ciro (otomatik hesaplanır).';
COMMENT ON COLUMN churn_skorlari.kacirilan_ciro IS 'Müşteri normal ritmine göre gelmesi gerekirken gelmediği için şu ana kadar kaçan tahmini ciro.';
COMMENT ON TABLE  geri_kazanimlar IS 'Mesajdan sonra atıf penceresi içinde gerçekleşen ziyaretler; ROI kanıtı.';


-- =====================================================================
-- DUMAN TESTİ (elle çalıştır; kiracı izolasyonunu doğrular)
-- =====================================================================
-- 1) Sahip/superuser olarak kullanıcı ekle ve UUID'sini not al:
--      INSERT INTO kullanicilar (eposta, ad_soyad) VALUES ('deneme@ornek.com', 'Deneme') RETURNING kullanici_id;
-- 2) Uygulama rolüne geç, işletme ve müşteri oluştur (tek işlemde):
--      SET ROLE panosu_app;
--      BEGIN;
--        SELECT set_config('app.kullanici_id', '<kullanici_id>', true);
--        SELECT isletme_olustur('Deneme Berber', '<kullanici_id>', 'berber');
--        INSERT INTO musteriler (ad_soyad, telefon_e164) VALUES ('Ahmet Yılmaz', '+905321234567');
--        SELECT * FROM musteriler;          -- 1 satır görünmeli
--      COMMIT;
-- 3) Yeni işlemde işletme AYARLAMADAN:
--      SELECT count(*) FROM musteriler;     -- 0 dönmeli (RLS)
--      RESET ROLE;
