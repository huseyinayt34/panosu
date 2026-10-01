-- =====================================================================
-- 0004: KİMLİK DOĞRULAMA VE İŞLETME KAYDI (Adım 8, tasarım: docs/adim-8-tasarim.md)
--   kullanici_kimlik_bilgileri : Argon2id parola özetleri (panosu_app'e yetki yok; yalnız fonksiyonlarla)
--   oturumlar                  : yenileme tokenlarının SHA-256 özetleri (panosu_app'e yetki yok; yalnız fonksiyonlarla)
--   davetler                   : personel davet kodlarının SHA-256 özetleri (kiracı tablosu, RLS)
--   SECURITY DEFINER fonksiyonları: kayıt, giriş, oturum, davet kabulü
-- Parola düz metni veritabanına hiç gelmez; özet uygulamada hesaplanır.
-- BEGIN/COMMIT yok: Alembic her revizyonu kendi işleminde çalıştırır.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. PAROLA ÖZETLERİ (ayrı tablo: kullanicilar'daki SELECT yetkisi ve üye görünürlüğü buraya uzanmaz)
-- ---------------------------------------------------------------------
CREATE TABLE kullanici_kimlik_bilgileri (
  kullanici_id           uuid PRIMARY KEY REFERENCES kullanicilar (kullanici_id) ON DELETE CASCADE,
  parola_ozeti           text NOT NULL CHECK (parola_ozeti LIKE '$argon2id$%'),   -- PHC dizgesi; düz parola olamaz
  parola_degisme_zamani  timestamptz NOT NULL DEFAULT now(),
  basarisiz_giris        integer NOT NULL DEFAULT 0 CHECK (basarisiz_giris >= 0),
  kilit_bitis            timestamptz
);
ALTER TABLE kullanici_kimlik_bilgileri ENABLE ROW LEVEL SECURITY;
ALTER TABLE kullanici_kimlik_bilgileri FORCE ROW LEVEL SECURITY;      -- politika YOK: doğrudan erişim kapalı

-- ---------------------------------------------------------------------
-- 2. OTURUMLAR (yenileme tokenları; tek kullanımlık, aile bazında iptal)
-- ---------------------------------------------------------------------
CREATE TABLE oturumlar (
  oturum_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kullanici_id       uuid NOT NULL REFERENCES kullanicilar (kullanici_id) ON DELETE CASCADE,
  aile_id            uuid NOT NULL,                              -- ilk girişte oluşur; yenilemelerde aynı kalır
  token_ozeti        bytea NOT NULL UNIQUE,                      -- SHA-256(yenileme tokenı)
  secili_isletme_id  uuid REFERENCES isletmeler (isletme_id) ON DELETE SET NULL,   -- kiracı sütunu DEĞİL
  olusturma_zamani   timestamptz NOT NULL DEFAULT now(),
  son_kullanma       timestamptz NOT NULL,
  kullanilma_zamani  timestamptz,                                -- yenilendiğinde dolar
  iptal_zamani       timestamptz
);
CREATE INDEX oturum_aile_idx ON oturumlar (aile_id);
CREATE INDEX oturum_kullanici_idx ON oturumlar (kullanici_id);
ALTER TABLE oturumlar ENABLE ROW LEVEL SECURITY;
ALTER TABLE oturumlar FORCE ROW LEVEL SECURITY;                        -- politika YOK

-- ---------------------------------------------------------------------
-- 3. DAVETLER (kiracı tablosu)
-- ---------------------------------------------------------------------
CREATE TABLE davetler (
  davet_id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  isletme_id              uuid NOT NULL DEFAULT aktif_isletme() REFERENCES isletmeler (isletme_id),
  rol                     text NOT NULL CHECK (rol IN ('yonetici','calisan')),   -- 'sahip' davet edilemez
  kod_ozeti               bytea NOT NULL UNIQUE,                 -- SHA-256(davet kodu)
  olusturan_kullanici_id  uuid NOT NULL DEFAULT aktif_kullanici() REFERENCES kullanicilar (kullanici_id),
  son_kullanma            timestamptz NOT NULL DEFAULT now() + interval '7 days',
  kullanilma_zamani       timestamptz,
  kullanan_kullanici_id   uuid REFERENCES kullanicilar (kullanici_id),
  iptal_zamani            timestamptz,
  olusturma_zamani        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX davet_isletme_idx ON davetler (isletme_id, olusturma_zamani DESC);

CREATE TRIGGER davetler_denetim
  AFTER INSERT OR UPDATE OR DELETE ON davetler
  FOR EACH ROW EXECUTE FUNCTION denetim_kaydi_yaz('davet_id');

ALTER TABLE davetler ENABLE ROW LEVEL SECURITY;
ALTER TABLE davetler FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_izolasyonu ON davetler
  USING (isletme_id = aktif_isletme()) WITH CHECK (isletme_id = aktif_isletme());

GRANT SELECT, INSERT, UPDATE ON davetler TO panosu_app;

-- ---------------------------------------------------------------------
-- 4. SECURITY DEFINER FONKSİYONLARI
--    Hepsi: SET search_path = public, pg_temp; PUBLIC'ten EXECUTE geri alınır; yalnız panosu_app çalıştırır.
-- ---------------------------------------------------------------------

-- Kullanıcı + parola özeti tek seferde. E-posta varsa kullanicilar_eposta_key tekillik hatası yükselir (uç: 409).
CREATE FUNCTION kullanici_kaydet(p_eposta citext, p_ad_soyad text, p_parola_ozeti text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS
$$
DECLARE
  v_id uuid;
BEGIN
  INSERT INTO kullanicilar (eposta, ad_soyad) VALUES (p_eposta, p_ad_soyad) RETURNING kullanici_id INTO v_id;
  INSERT INTO kullanici_kimlik_bilgileri (kullanici_id, parola_ozeti) VALUES (v_id, p_parola_ozeti);
  RETURN v_id;
END
$$;

-- E-postayla kullanıcıyı bulur (RLS'nin girişte engellediği tek okuma).
CREATE FUNCTION giris_bilgisi(p_eposta citext)
RETURNS TABLE (kullanici_id uuid, parola_ozeti text, kilit_bitis timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
$$
  SELECT k.kullanici_id, b.parola_ozeti, b.kilit_bitis
  FROM kullanicilar k
  JOIN kullanici_kimlik_bilgileri b ON b.kullanici_id = k.kullanici_id
  WHERE k.eposta = p_eposta
$$;

-- Başarılı: sayaç sıfırlanır, son_giris_zamani yazılır. Başarısız: sayaç artar; 5'e ulaşınca 15 dk kilit ve sayaç
-- sıfırlanır (15 dakikada en fazla 5 deneme).
CREATE FUNCTION giris_sonucu_yaz(p_kullanici_id uuid, p_basarili boolean) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS
$$
BEGIN
  IF p_basarili THEN
    UPDATE kullanici_kimlik_bilgileri SET basarisiz_giris = 0, kilit_bitis = NULL WHERE kullanici_id = p_kullanici_id;
    UPDATE kullanicilar SET son_giris_zamani = now() WHERE kullanici_id = p_kullanici_id;
  ELSE
    UPDATE kullanici_kimlik_bilgileri
    SET basarisiz_giris = CASE WHEN basarisiz_giris + 1 >= 5 THEN 0 ELSE basarisiz_giris + 1 END,
        kilit_bitis     = CASE WHEN basarisiz_giris + 1 >= 5 THEN now() + interval '15 minutes' ELSE kilit_bitis END
    WHERE kullanici_id = p_kullanici_id;
  END IF;
END
$$;

-- Yalnızca özet yeniden hesaplandığında (parametre yükseltme); parola değişmediği için parola_degisme_zamani değişmez.
CREATE FUNCTION parola_ozeti_guncelle(p_kullanici_id uuid, p_yeni_ozet text) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS
$$
  UPDATE kullanici_kimlik_bilgileri SET parola_ozeti = p_yeni_ozet WHERE kullanici_id = p_kullanici_id
$$;

-- Yeni oturum ailesi. p_isletme verilirse kullanıcının o işletmenin üyesi olması gerekir.
CREATE FUNCTION oturum_ac(p_kullanici_id uuid, p_ozet bytea, p_isletme uuid, p_sure interval) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS
$$
DECLARE
  v_id uuid;
BEGIN
  IF p_isletme IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM uyelikler u WHERE u.isletme_id = p_isletme AND u.kullanici_id = p_kullanici_id
  ) THEN
    RAISE EXCEPTION 'Kullanıcı bu işletmenin üyesi değil' USING ERRCODE = 'insufficient_privilege';
  END IF;
  INSERT INTO oturumlar (kullanici_id, aile_id, token_ozeti, secili_isletme_id, son_kullanma)
  VALUES (p_kullanici_id, gen_random_uuid(), p_ozet, p_isletme, now() + p_sure)
  RETURNING oturum_id INTO v_id;
  RETURN v_id;
END
$$;

-- Tek kullanımlık yenileme. Kullanılmış token tekrar gelirse TÜM aile iptal edilir ve boş döner (çalıntı token).
-- Süresi geçmiş / iptal edilmiş / bilinmeyen token → boş. ÇAĞIRAN, boş sonuçta da işlemi COMMIT etmelidir
-- (aksi hâlde aile iptali geri alınır).
CREATE FUNCTION oturum_yenile(p_eski_ozet bytea, p_yeni_ozet bytea, p_sure interval)
RETURNS TABLE (kullanici_id uuid, secili_isletme_id uuid)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS
$$
#variable_conflict use_column
DECLARE
  o oturumlar%ROWTYPE;
BEGIN
  SELECT * INTO o FROM oturumlar t WHERE t.token_ozeti = p_eski_ozet FOR UPDATE;
  IF NOT FOUND THEN
    RETURN;
  END IF;
  IF o.kullanilma_zamani IS NOT NULL THEN
    UPDATE oturumlar t SET iptal_zamani = COALESCE(t.iptal_zamani, now()) WHERE t.aile_id = o.aile_id;
    RETURN;
  END IF;
  IF o.iptal_zamani IS NOT NULL OR o.son_kullanma <= now() THEN
    RETURN;
  END IF;
  UPDATE oturumlar t SET kullanilma_zamani = now() WHERE t.oturum_id = o.oturum_id;
  INSERT INTO oturumlar (kullanici_id, aile_id, token_ozeti, secili_isletme_id, son_kullanma)
  VALUES (o.kullanici_id, o.aile_id, p_yeni_ozet, o.secili_isletme_id, now() + p_sure);
  RETURN QUERY SELECT o.kullanici_id, o.secili_isletme_id;
END
$$;

-- Ailenin tamamını iptal eder (ailedeki herhangi bir tokenla).
CREATE FUNCTION oturum_kapat(p_ozet bytea) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS
$$
  UPDATE oturumlar SET iptal_zamani = COALESCE(iptal_zamani, now())
  WHERE aile_id = (SELECT aile_id FROM oturumlar WHERE token_ozeti = p_ozet)
$$;

-- İşletme seçimini yenileme oturumuna yazar (geçerli, kullanılmamış token; kullanıcı işletmenin üyesi olmalı).
CREATE FUNCTION oturum_isletme_degistir(p_ozet bytea, p_isletme uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS
$$
DECLARE
  o oturumlar%ROWTYPE;
BEGIN
  SELECT * INTO o FROM oturumlar t
  WHERE t.token_ozeti = p_ozet AND t.kullanilma_zamani IS NULL AND t.iptal_zamani IS NULL AND t.son_kullanma > now()
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Geçerli oturum bulunamadı' USING ERRCODE = 'invalid_authorization_specification';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM uyelikler u WHERE u.isletme_id = p_isletme AND u.kullanici_id = o.kullanici_id) THEN
    RAISE EXCEPTION 'Kullanıcı bu işletmenin üyesi değil' USING ERRCODE = 'insufficient_privilege';
  END IF;
  UPDATE oturumlar t SET secili_isletme_id = p_isletme WHERE t.oturum_id = o.oturum_id;
END
$$;

-- Geçerli davette: kullanıldı işaretle + üyelik ekle (tek işlem). Geçersiz / süresi geçmiş / kullanılmış / iptal → boş.
-- Kullanıcı zaten üyeyse unique_violation (uç: 409); davet tüketilmez.
CREATE FUNCTION davet_kabul(p_kod_ozeti bytea, p_kullanici_id uuid)
RETURNS TABLE (isletme_id uuid, rol text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS
$$
#variable_conflict use_column
DECLARE
  d davetler%ROWTYPE;
BEGIN
  SELECT * INTO d FROM davetler t WHERE t.kod_ozeti = p_kod_ozeti FOR UPDATE;
  IF NOT FOUND OR d.kullanilma_zamani IS NOT NULL OR d.iptal_zamani IS NOT NULL OR d.son_kullanma <= now() THEN
    RETURN;
  END IF;
  IF EXISTS (SELECT 1 FROM uyelikler u WHERE u.isletme_id = d.isletme_id AND u.kullanici_id = p_kullanici_id) THEN
    RAISE EXCEPTION 'Kullanıcı bu işletmenin zaten üyesi' USING ERRCODE = 'unique_violation';
  END IF;
  UPDATE davetler t SET kullanilma_zamani = now(), kullanan_kullanici_id = p_kullanici_id WHERE t.davet_id = d.davet_id;
  INSERT INTO uyelikler (isletme_id, kullanici_id, rol) VALUES (d.isletme_id, p_kullanici_id, d.rol);
  RETURN QUERY SELECT d.isletme_id, d.rol;
END
$$;

REVOKE ALL ON FUNCTION
  kullanici_kaydet(citext, text, text), giris_bilgisi(citext), giris_sonucu_yaz(uuid, boolean),
  parola_ozeti_guncelle(uuid, text), oturum_ac(uuid, bytea, uuid, interval), oturum_yenile(bytea, bytea, interval),
  oturum_kapat(bytea), oturum_isletme_degistir(bytea, uuid), davet_kabul(bytea, uuid)
FROM PUBLIC;
GRANT EXECUTE ON FUNCTION
  kullanici_kaydet(citext, text, text), giris_bilgisi(citext), giris_sonucu_yaz(uuid, boolean),
  parola_ozeti_guncelle(uuid, text), oturum_ac(uuid, bytea, uuid, interval), oturum_yenile(bytea, bytea, interval),
  oturum_kapat(bytea), oturum_isletme_degistir(bytea, uuid), davet_kabul(bytea, uuid)
TO panosu_app;

COMMENT ON TABLE kullanici_kimlik_bilgileri IS 'Argon2id parola özetleri. panosu_app doğrudan erişemez; yalnız SECURITY DEFINER fonksiyonları.';
COMMENT ON TABLE oturumlar IS 'Yenileme tokenlarının SHA-256 özetleri. panosu_app doğrudan erişemez; yalnız SECURITY DEFINER fonksiyonları.';
