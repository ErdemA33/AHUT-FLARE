"""Yerel depo: profil, ayarlar ve vaka kütüphanesi.

Vaka dosyası biçimi (.ahut) düz JSON'dur — sıkıştırılmaz, çünkü aynı dosyanın
ileride bir GitHub deposunda yayımlanması ve orada okunabilir/karşılaştırılabilir
olması isteniyor. Dosya kendi kendine yeterlidir: girdiler, sonuçlar, grafik
verileri, yazar ve yorumlar hep birlikte durur.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

BICIM = "ahut-vaka"
BICIM_SURUMU = 1
UZANTI = ".ahut"

_kilit = threading.RLock()


def _simdi() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _oku_json(yol: Path, varsayilan):
    try:
        return json.loads(yol.read_text(encoding="utf-8"))
    except Exception:
        return varsayilan


def _yaz_json(yol: Path, veri) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(yol.suffix + ".tmp")
    gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
    gecici.replace(yol)


VARSAYILAN_AYARLAR = {
    "dil": "tr",
    "birimler": {"basinc": "kPa", "akis": "cm/s"},
    "gorunum": "acik",   # "acik" (ANSYS klasik) | "koyu"
    "son_vakalar": [],
}

VARSAYILAN_PROFIL = {
    "ad": "",
    "kurum": "",
    "rol": "",
    "baglanti": "",
    "kurulus": _simdi(),
    # Paylaşım deposu. Jeton yalnızca bu dosyada durur; paylaşılan vaka
    # dosyasına (paket_yap) girmez, ekranda da gizli gösterilir.
    "github_depo": "",
    "github_jeton": "",
}


class Depo:
    def __init__(self, veri: Path, ornekler_kaynak: Path | None = None):
        self.veri = veri
        self.vakalar = veri / "cases"
        self.ornekler = veri / "examples"
        # Paketlenmiş sürümde örnek vakalar paketin içinde (salt okunur) durur;
        # kullanıcının yazılabilir klasörü boş olabilir. İkisi de taranır.
        self.ornekler_kaynak = ornekler_kaynak
        self.ayar_dosyasi = veri / "settings.json"
        self.profil_dosyasi = veri / "profile.json"
        self.dizin_dosyasi = self.vakalar / "index.json"
        for k in (self.veri, self.vakalar, self.ornekler):
            k.mkdir(parents=True, exist_ok=True)

    def _ornek_klasorleri(self):
        yollar = [self.ornekler]
        if self.ornekler_kaynak and self.ornekler_kaynak.resolve() != self.ornekler.resolve():
            yollar.append(self.ornekler_kaynak)
        return [y for y in yollar if y.is_dir()]

    # ------------------------------------------------------------ ayarlar
    def ayarlar(self) -> dict:
        return {**VARSAYILAN_AYARLAR, **_oku_json(self.ayar_dosyasi, {})}

    def ayar_yaz(self, yeni: dict) -> dict:
        with _kilit:
            a = {**self.ayarlar(), **(yeni or {})}
            _yaz_json(self.ayar_dosyasi, a)
            return a

    # ------------------------------------------------------------ profil
    def profil(self) -> dict:
        return {**VARSAYILAN_PROFIL, **_oku_json(self.profil_dosyasi, {})}

    def profil_yaz(self, yeni: dict) -> dict:
        with _kilit:
            p = {**self.profil(), **(yeni or {})}
            p["guncelleme"] = _simdi()
            _yaz_json(self.profil_dosyasi, p)
            return p

    # ------------------------------------------------------------ vaka paketi
    def paket_yap(self, *, girdi, sonuc, baslik="", aciklama="", etiketler=None,
                  onayar=None, llm_yorum=None, render=None, vaka_id=None, uygulama=None,
                  supurme=None) -> dict:
        """Hesaplama sonucunu paylaşılabilir .ahut sözlüğüne çevirir."""
        return {
            "bicim": BICIM,
            "bicim_surumu": BICIM_SURUMU,
            "id": vaka_id or uuid.uuid4().hex[:12],
            "baslik": baslik or self._otomatik_baslik(girdi, sonuc),
            "aciklama": aciklama or "",
            "etiketler": list(etiketler or self._otomatik_etiketler(girdi, sonuc, onayar)),
            "yazar": {k: self.profil().get(k, "") for k in ("ad", "kurum", "rol", "baglanti")},
            "olusturma": _simdi(),
            "guncelleme": _simdi(),
            "uygulama": uygulama or {},
            "onayar": onayar,
            "girdi": girdi,
            "sonuc": sonuc,
            "llm_yorum": llm_yorum,
            "render": render,
            "supurme": supurme,          # parametre süpürmesi sonucu (varsa)
            "yorumlar": [],
        }

    @staticmethod
    def _otomatik_baslik(girdi, sonuc) -> str:
        t = (sonuc or {}).get("tahmin") or {}
        g = (girdi or {}).get("g")
        ortam = "ISS" if g is not None and g < 0.01 else "Ay/Mars" if g is not None and g < 0.9 else "Dünya"
        return f"{(girdi or {}).get('malzeme', '?')} · {ortam} · %{(girdi or {}).get('oksijen', '?')} O₂" + (
            f" · {t.get('risk_seviyesi')}" if t.get("risk_seviyesi") else ""
        )

    @staticmethod
    def _otomatik_etiketler(girdi, sonuc, onayar) -> list[str]:
        g = (girdi or {}).get("g")
        etiket = [str((girdi or {}).get("malzeme", "")).lower()]
        if g is not None:
            etiket.append("mikro-g" if g < 0.01 else "kismi-g" if g < 0.9 else "dunya-g")
        if onayar and onayar != "Özel":
            etiket.append(str(onayar).lower().replace(" ", "-"))
        seviye = ((sonuc or {}).get("tahmin") or {}).get("risk_seviyesi")
        if seviye:
            etiket.append(str(seviye).lower().replace(" ", "-"))
        return [e for e in dict.fromkeys(etiket) if e]

    @staticmethod
    def ozet(paket: dict) -> dict:
        """Kütüphane listesinde gösterilen hafif kayıt (grafik verisi taşımaz)."""
        t = ((paket.get("sonuc") or {}).get("tahmin")) or {}
        g = paket.get("girdi") or {}
        return {
            "id": paket.get("id"),
            "baslik": paket.get("baslik"),
            "aciklama": (paket.get("aciklama") or "")[:300],
            "etiketler": paket.get("etiketler") or [],
            "yazar": (paket.get("yazar") or {}).get("ad") or "",
            "olusturma": paket.get("olusturma"),
            "guncelleme": paket.get("guncelleme"),
            "onayar": paket.get("onayar"),
            "malzeme": g.get("malzeme"),
            "g": g.get("g"),
            "oksijen": g.get("oksijen"),
            "basinc": g.get("basinc"),
            "akis": g.get("akis"),
            "risk_seviyesi": t.get("risk_seviyesi"),
            "yanma_ihtimali": t.get("yanma_ihtimali"),
            "guvenlik_katsayisi": t.get("guvenlik_katsayisi"),
            # güven: v2 varsa o (güven skoru v2), yoksa eski v1; guven_v1 ayrıca
            "guven": ((t.get("guven_v2") or {}).get("skor") if (t.get("guven_v2") or {}).get("skor") is not None
                      else (t.get("guven") or {}).get("skor")),
            "guven_v1": (t.get("guven") or {}).get("skor"),
            "yorum_sayisi": len(paket.get("yorumlar") or []),
            "llm_var": bool(paket.get("llm_yorum")),
        }

    # ------------------------------------------------------------ kütüphane
    def _dosya(self, vaka_id: str) -> Path:
        guvenli = "".join(c for c in str(vaka_id) if c.isalnum() or c in "-_")
        if not guvenli:
            raise ValueError("geçersiz vaka kimliği")
        return self.vakalar / (guvenli + UZANTI)

    def kaydet(self, paket: dict) -> dict:
        with _kilit:
            paket.setdefault("id", uuid.uuid4().hex[:12])
            paket["guncelleme"] = _simdi()
            _yaz_json(self._dosya(paket["id"]), paket)
            self._dizin_guncelle(paket)
            return self.ozet(paket)

    def oku(self, vaka_id: str) -> dict | None:
        return _oku_json(self._dosya(vaka_id), None)

    def sil(self, vaka_id: str) -> bool:
        with _kilit:
            try:
                self._dosya(vaka_id).unlink()
            except FileNotFoundError:
                return False
            dizin = [o for o in self._dizin() if o.get("id") != vaka_id]
            _yaz_json(self.dizin_dosyasi, dizin)
            return True

    def listele(self) -> list[dict]:
        with _kilit:
            dizin = self._dizin()
            dosyalar = {p.stem for p in self.vakalar.glob("*" + UZANTI)}
            if {o.get("id") for o in dizin} != dosyalar:  # elle dosya eklendi/silindi
                dizin = self._dizin_kur()
            return sorted(dizin, key=lambda o: o.get("guncelleme") or "", reverse=True)

    def _dizin(self) -> list[dict]:
        d = _oku_json(self.dizin_dosyasi, [])
        return d if isinstance(d, list) else []

    def _dizin_kur(self) -> list[dict]:
        dizin = []
        for p in self.vakalar.glob("*" + UZANTI):
            paket = _oku_json(p, None)
            if isinstance(paket, dict) and paket.get("id"):
                dizin.append(self.ozet(paket))
        _yaz_json(self.dizin_dosyasi, dizin)
        return dizin

    def _dizin_guncelle(self, paket: dict) -> None:
        ozet = self.ozet(paket)
        dizin = [o for o in self._dizin() if o.get("id") != ozet["id"]]
        dizin.append(ozet)
        _yaz_json(self.dizin_dosyasi, dizin)

    # ------------------------------------------------------------ içe / dışa aktarma
    @staticmethod
    def dogrula(paket) -> dict:
        if not isinstance(paket, dict) or paket.get("bicim") != BICIM:
            raise ValueError("Bu dosya bir AHUT vaka dosyası değil.")
        if int(paket.get("bicim_surumu") or 0) > BICIM_SURUMU:
            raise ValueError("Dosya daha yeni bir sürümle oluşturulmuş; uygulamayı güncelleyin.")
        if not isinstance(paket.get("girdi"), dict):
            raise ValueError("Vaka dosyasında girdi bölümü yok.")
        return paket

    def disa_aktar(self, vaka_id: str, hedef: Path) -> str:
        paket = self.oku(vaka_id)
        if paket is None:
            raise ValueError("Vaka bulunamadı.")
        hedef = Path(hedef)
        if hedef.suffix.lower() != UZANTI:
            hedef = hedef.with_suffix(UZANTI)
        _yaz_json(hedef, paket)
        return str(hedef)

    def ice_aktar(self, kaynak: Path) -> dict:
        paket = self.dogrula(_oku_json(Path(kaynak), None))
        paket["id"] = uuid.uuid4().hex[:12]  # çakışmasın
        paket["ice_aktarma"] = _simdi()
        return self.kaydet(paket)

    # ------------------------------------------------------------ topluluk (ilk sürüm: yerel örnekler)
    def topluluk(self) -> list[dict]:
        liste, gorulen = [], set()
        for klasor in self._ornek_klasorleri():
            for p in sorted(klasor.glob("*" + UZANTI)):
                paket = _oku_json(p, None)
                if not isinstance(paket, dict) or paket.get("bicim") != BICIM:
                    continue
                if paket.get("id") in gorulen:
                    continue
                gorulen.add(paket.get("id"))
                o = self.ozet(paket)
                o["kaynak"] = "ornek"
                liste.append(o)
        return liste

    def topluluk_oku(self, vaka_id: str) -> dict | None:
        for klasor in self._ornek_klasorleri():
            for p in klasor.glob("*" + UZANTI):
                paket = _oku_json(p, None)
                if isinstance(paket, dict) and paket.get("id") == vaka_id:
                    return paket
        return None
