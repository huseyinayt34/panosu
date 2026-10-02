"""Türkçe biçimleme (rapor ve panel metinleri için). Para: 1.234,56 TL. Tarih: 9 Ekim 2026."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

AYLAR = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
         "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")


def para(tutar: Decimal | int | str | None, birim: str = "TL") -> str:
    """Decimal tutar → '1.234,56 TL' (binlik ayıracı nokta, ondalık virgül, 2 hane, yarım yukarı). None → '—'."""
    if tutar is None:
        return "—"
    deger = Decimal(tutar).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    isaret = "-" if deger < 0 else ""
    tam, kurus = f"{abs(deger):.2f}".split(".")
    gruplar = []
    while len(tam) > 3:
        gruplar.insert(0, tam[-3:])
        tam = tam[:-3]
    gruplar.insert(0, tam)
    return f"{isaret}{'.'.join(gruplar)},{kurus} {birim}".rstrip()


def tarih(gun: date | None) -> str:
    """date → '9 Ekim 2026'. None → '—'."""
    if gun is None:
        return "—"
    return f"{gun.day} {AYLAR[gun.month - 1]} {gun.year}"


def ay_adi(ay: date | None) -> str:
    """date → 'Eylül 2026'. None → '—'."""
    if ay is None:
        return "—"
    return f"{AYLAR[ay.month - 1]} {ay.year}"


def yuzde(oran: Decimal | float | None) -> str:
    """0.1234 → '%12' (Türkçe yüzde işareti önde). None → '—'."""
    if oran is None:
        return "—"
    return f"%{Decimal(str(oran)) * 100:.0f}"


def olasilik(p: Decimal | float | None) -> str:
    """Olasılık gösterimi: 0 → '%0'; 0 < p < 0,01 → '<%1'; 0,99 < p < 1 → '>%99'; diğerleri yuzde(p). None → '—'."""
    if p is None:
        return "—"
    d = Decimal(str(p))
    if 0 < d < Decimal("0.01"):
        return "<%1"
    if Decimal("0.99") < d < 1:
        return ">%99"
    return yuzde(d)


def ondalik(deger: Decimal | int | str | None, hane: int = 1) -> str:
    """Decimal → '13,5' (ondalık virgül, yarım yukarı, binlik ayıracı yok). None → '—'."""
    if deger is None:
        return "—"
    sonuc = Decimal(deger).quantize(Decimal(1).scaleb(-hane), rounding=ROUND_HALF_UP)
    if sonuc == 0:
        sonuc = abs(sonuc)                       # '-0,0' yazılmasın
    return f"{sonuc:.{hane}f}".replace(".", ",")
