"""GitHub üzerinden vaka paylaşımı.

Sunucu yazmıyoruz: paylaşılan her vaka, bir GitHub deposundaki `vakalar/`
klasörüne düşen bir `.ahut` dosyasıdır. GitHub Pages o depoyu statik bir
site olarak yayımlar. Böylece hosting, veritabanı ve hesap sistemi gerekmez.

Yalnızca standart kütüphane kullanılır (urllib) — exe'ye yeni bağımlılık
girmesin diye `requests` bilerek kullanılmadı.

Yazma için ince ayarlı (fine-grained) bir kişisel erişim jetonu gerekir:
tek depoya `Contents: Read and write`. Jeton profil dosyasında durur,
hiçbir yerde ekrana yazılmaz ve depoya gönderilmez.
"""
from __future__ import annotations

import base64
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

API = "https://api.github.com"
KULLANICI_ETIKETI = "AHUT-FLARE/1.0"      # GitHub User-Agent ister; kişisel bilgi taşımaz
KLASOR = "vakalar"
ZAMAN_ASIMI = 20


class GitHubHatasi(Exception):
    pass


def _istek(yol: str, jeton: str | None = None, yontem: str = "GET", govde: dict | None = None,
           tam_url: str | None = None):
    url = tam_url or (API + yol)
    veri = json.dumps(govde).encode("utf-8") if govde is not None else None
    basliklar = {
        "Accept": "application/vnd.github+json",
        "User-Agent": KULLANICI_ETIKETI,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if veri is not None:
        basliklar["Content-Type"] = "application/json"
    if jeton:
        basliklar["Authorization"] = "Bearer " + jeton
    istek = urllib.request.Request(url, data=veri, headers=basliklar, method=yontem)
    try:
        with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as y:
            ham = y.read()
            return json.loads(ham) if ham else {}
    except urllib.error.HTTPError as e:
        try:
            ayrinti = json.loads(e.read() or b"{}").get("message", "")
        except Exception:
            ayrinti = ""
        raise GitHubHatasi(_hata_metni(e.code, ayrinti)) from None
    except urllib.error.URLError as e:
        raise GitHubHatasi(f"İnternete ulaşılamadı: {getattr(e, 'reason', e)}") from None
    except socket.timeout:
        raise GitHubHatasi("GitHub yanıt vermedi (zaman aşımı).") from None
    except json.JSONDecodeError:
        raise GitHubHatasi("GitHub'dan beklenmeyen bir yanıt geldi.") from None


def _hata_metni(kod: int, ayrinti: str) -> str:
    if kod == 401:
        return "Jeton geçersiz ya da süresi dolmuş. Profil ekranından yeni bir jeton girin."
    if kod == 403:
        if "rate limit" in ayrinti.lower():
            return "GitHub istek sınırına takıldı. Bir süre bekleyin ya da profile jeton ekleyin."
        return "Bu depoya yazma yetkisi yok. Jetonun 'Contents: Read and write' izni olmalı."
    if kod == 404:
        return "Depo ya da klasör bulunamadı. Profil ekranındaki kullanıcı/depo adını kontrol edin."
    if kod == 409:
        return "Depo boş görünüyor. GitHub'da depoyu açarken 'Add a README' seçeneğini işaretleyin."
    if kod == 422:
        return f"GitHub isteği kabul etmedi: {ayrinti or 'geçersiz içerik'}"
    return f"GitHub hatası (HTTP {kod}){': ' + ayrinti if ayrinti else ''}"


def depo_ayristir(metin: str) -> tuple[str, str]:
    """'Nikire55/ahut-flare', tam URL ya da boşluklu yazım -> (sahip, depo)."""
    m = re.search(r"github\.com[/:]([^/]+)/([^/\s#?]+)", str(metin or ""))
    if not m:
        m = re.match(r"^\s*([A-Za-z0-9._-]+)\s*/\s*([A-Za-z0-9._-]+)\s*$", str(metin or ""))
    if not m:
        raise GitHubHatasi("Depo adresi 'kullanici/depo' biçiminde olmalı (örn. Nikire55/ahut-flare).")
    return m.group(1), re.sub(r"\.git$", "", m.group(2))


class Depo:
    def __init__(self, adres: str, jeton: str | None = None, dal: str = "main"):
        self.sahip, self.repo = depo_ayristir(adres)
        self.jeton = (jeton or "").strip() or None
        self.dal = dal or "main"

    # ------------------------------------------------------------ bilgi
    @property
    def tam_ad(self) -> str:
        return f"{self.sahip}/{self.repo}"

    @property
    def site_adresi(self) -> str:
        return f"https://{self.sahip.lower()}.github.io/{self.repo}/"

    def vaka_adresi(self, dosya: str) -> str:
        return self.site_adresi + "#" + urllib.parse.quote(dosya)

    def sina(self) -> dict:
        """Depoya erişilebiliyor mu, yazma yetkisi var mı?"""
        d = _istek(f"/repos/{self.sahip}/{self.repo}", self.jeton)
        yazabilir = bool((d.get("permissions") or {}).get("push"))
        if self.jeton and not yazabilir:
            # fine-grained jetonlarda permissions alanı gelmeyebilir; yazmayı denemeden emin olamayız
            yazabilir = None
        return {
            "tam_ad": d.get("full_name"),
            "acik": not d.get("private", True),
            "dal": d.get("default_branch") or self.dal,
            "yazabilir": yazabilir,
            "site": self.site_adresi,
            "jeton_var": bool(self.jeton),
        }

    # ------------------------------------------------------------ okuma
    def liste(self) -> list[dict]:
        """vakalar/ klasöründeki .ahut dosyaları."""
        try:
            d = _istek(f"/repos/{self.sahip}/{self.repo}/contents/{KLASOR}?ref={self.dal}", self.jeton)
        except GitHubHatasi as e:
            if "bulunamadı" in str(e):
                return []            # klasör henüz yok: ilk paylaşımda oluşur
            raise
        if not isinstance(d, list):
            return []
        return [
            {"ad": x["name"], "yol": x["path"], "sha": x["sha"],
             "boyut": x.get("size"), "indirme": x.get("download_url")}
            for x in d
            if x.get("type") == "file" and str(x.get("name", "")).endswith(".ahut")
        ]

    def indir(self, indirme_adresi: str) -> dict:
        istek = urllib.request.Request(indirme_adresi, headers={"User-Agent": KULLANICI_ETIKETI})
        try:
            with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as y:
                return json.loads(y.read())
        except urllib.error.HTTPError as e:
            raise GitHubHatasi(_hata_metni(e.code, "")) from None
        except urllib.error.URLError as e:
            raise GitHubHatasi(f"Dosya indirilemedi: {getattr(e, 'reason', e)}") from None
        except json.JSONDecodeError:
            raise GitHubHatasi("Vaka dosyası okunamadı (bozuk JSON).") from None

    # ------------------------------------------------------------ yazma
    TR_HARF = str.maketrans("çğıöşüÇĞİıÖŞÜâîû", "cgiosucgiiosuaiu")

    @classmethod
    def dosya_adi(cls, paket: dict) -> str:
        """URL'de ve dosya sisteminde sorun çıkarmayan ad: türkçe harfler çevrilir."""
        g = paket.get("girdi") or {}
        parca = [
            datetime.now().strftime("%Y-%m-%d"),
            str(g.get("malzeme") or "vaka"),
            str(paket.get("onayar") or "ozel"),
            str(paket.get("id") or "")[:8],
        ]
        ad = "-".join(p for p in parca if p).translate(cls.TR_HARF).lower()
        ad = re.sub(r"[^a-z0-9._-]+", "-", ad)
        ad = re.sub(r"-{2,}", "-", ad).strip("-._")
        return (ad or "vaka") + ".ahut"

    def paylas(self, paket: dict, mesaj: str | None = None) -> dict:
        if not self.jeton:
            raise GitHubHatasi("Paylaşmak için profil ekranına GitHub jetonu girmelisiniz.")
        dosya = self.dosya_adi(paket)
        yol = f"{KLASOR}/{dosya}"
        icerik = json.dumps(paket, ensure_ascii=False, indent=1).encode("utf-8")

        govde = {
            "message": mesaj or f"vaka: {paket.get('baslik') or dosya}",
            "content": base64.b64encode(icerik).decode("ascii"),
            "branch": self.dal,
        }
        mevcut = self._sha(yol)
        if mevcut:
            govde["sha"] = mevcut      # aynı dosya varsa üstüne yaz

        d = _istek(f"/repos/{self.sahip}/{self.repo}/contents/{urllib.parse.quote(yol)}",
                   self.jeton, "PUT", govde)
        return {
            "dosya": dosya,
            "yol": yol,
            "commit": ((d.get("commit") or {}).get("html_url")),
            "github": ((d.get("content") or {}).get("html_url")),
            "site": self.vaka_adresi(dosya),
            "guncelleme": bool(mevcut),
        }

    # ------------------------------------------------------------ Pages sitesi
    SITE_DOSYALARI = ("index.html", "style.css", "base.js", "chart.js", "site.js", "README.md")

    def _dosya_yaz(self, yol: str, icerik: bytes, mesaj: str) -> bool:
        """Dosyayı deponun içine yazar. İçerik aynıysa dokunmaz (boş commit olmasın)."""
        mevcut = self._icerik(yol)
        if mevcut is not None and mevcut[1] == icerik:
            return False
        govde = {
            "message": mesaj,
            "content": base64.b64encode(icerik).decode("ascii"),
            "branch": self.dal,
        }
        if mevcut is not None:
            govde["sha"] = mevcut[0]
        _istek(f"/repos/{self.sahip}/{self.repo}/contents/{urllib.parse.quote(yol)}",
               self.jeton, "PUT", govde)
        return True

    def site_kur(self, kaynak_klasor) -> dict:
        """GitHub Pages sitesinin dosyalarını depoya yükler.

        Böylece kullanıcının elle dosya yüklemesi gerekmez: depoyu ve jetonu
        hazırlaması yeter, siteyi uygulama kurar.
        """
        if not self.jeton:
            raise GitHubHatasi("Siteyi kurmak için profil ekranına GitHub jetonu girmelisiniz.")
        from pathlib import Path as _P

        kaynak = _P(kaynak_klasor)
        yazilan, atlanan, eksik = [], [], []
        for ad in self.SITE_DOSYALARI:
            p = kaynak / ad
            if not p.exists():
                eksik.append(ad)
                continue
            if self._dosya_yaz(ad, p.read_bytes(), f"site: {ad}"):
                yazilan.append(ad)
            else:
                atlanan.append(ad)

        # site, depo bilgisini bu dosyadan da okuyabilsin (özel alan adı kullanılırsa)
        depo_json = json.dumps({"sahip": self.sahip, "repo": self.repo, "dal": self.dal},
                               ensure_ascii=False, indent=1).encode("utf-8")
        if self._dosya_yaz("depo.json", depo_json, "site: depo bilgisi"):
            yazilan.append("depo.json")
        else:
            atlanan.append("depo.json")

        return {"yazilan": yazilan, "degismeyen": atlanan, "eksik": eksik, "site": self.site_adresi}

    def _icerik(self, yol: str):
        """(sha, ham baytlar) ya da None."""
        try:
            d = _istek(f"/repos/{self.sahip}/{self.repo}/contents/{urllib.parse.quote(yol)}?ref={self.dal}",
                       self.jeton)
        except GitHubHatasi:
            return None
        if not isinstance(d, dict) or "sha" not in d:
            return None
        try:
            ham = base64.b64decode(d.get("content") or "")
        except Exception:
            ham = b""
        return d["sha"], ham

    def _sha(self, yol: str) -> str | None:
        try:
            d = _istek(f"/repos/{self.sahip}/{self.repo}/contents/{urllib.parse.quote(yol)}?ref={self.dal}",
                       self.jeton)
            return d.get("sha") if isinstance(d, dict) else None
        except GitHubHatasi:
            return None
