"""Telefon numarası normalleştirme (saf fonksiyon, veritabanı yok).

Hedef biçim E.164'tür; veritabanındaki musteriler_telefon_e164_check kısıtıyla aynı desen kullanılır.
"""

import re

_E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")
_AYIRICILAR = re.compile(r"[\s\-.()]")
_RAKAMLAR = re.compile(r"^[0-9]+$")


def telefon_normallestir(ham: str | None) -> str | None:
    if ham is None:
        return None
    numara = _AYIRICILAR.sub("", ham)
    if not numara:
        return None

    govde = numara[1:] if numara.startswith("+") else numara
    if not _RAKAMLAR.match(govde):
        raise ValueError("Telefon numarası yalnızca rakam içermelidir (başta tek bir '+' olabilir)")

    if numara.startswith("+"):
        pass
    elif numara.startswith("00"):
        numara = "+" + numara[2:]
    elif numara.startswith("0") and len(numara) == 11:
        numara = "+90" + numara[-10:]
    elif len(numara) == 10:                     # 0 ile başlamadığı yukarıda elendi
        numara = "+90" + numara
    elif numara.startswith("90") and len(numara) == 12:
        numara = "+" + numara

    if not _E164.match(numara):
        raise ValueError("Geçersiz telefon numarası; örnek: 0532 123 45 67 veya +905321234567")
    return numara
