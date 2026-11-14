# AHUT – FLARE

**F**ire · **L**earning · **A**nalysis · **R**esearch · **E**ngine

**Mikro yerçekiminde yangın güvenliği analiz ortamı.**
NASA PSI mikro yerçekimi yanma deneylerinden öğrenilmiş bir risk modelini, yarı-ampirik bir fizik motoruyla birlikte çalıştırır; uzay aracı kabinleri ile Ay ve Mars üsleri için malzeme yanabilirlik kararı üretir.

AHUT — Ankara Havacılık ve Uzay Teknolojileri Hackathon Takımı · NASA Space Apps Challenge 2026 · MIT lisansı

---

## Ne yapar

Bir ortam (yerçekimi, basınç, oksijen, seyreltici gaz) ve bir malzeme verirsiniz; program şunları döndürür:

| Çıktı | Anlamı |
|---|---|
| **Risk seviyesi** | DÜŞÜK / ORTA / YÜKSEK / ÇOK YÜKSEK |
| **Yanma ihtimali** | 0–1, belirsizlik aralığıyla |
| **Sönme sınırı** | Bu yüzdenin altında alev söner |
| **Güvenlik katsayısı** | `sönme sınırı / ortam oksijeni`; 1'in altı yanabilir demektir |
| **Güven skoru** | 0–100; sonuca ne kadar güvenilebileceği |
| **Uyarılar** | Eksik girdiler, çelişkiler, kısmi yerçekimi sınırlaması |

Yanında üç grafik: oksijen eğrisi, yerçekimi × oksijen yanabilirlik haritası ve akış eğrisi; ayrıca bu koşula en yakın gerçek NASA deneylerinin listesi.

Yanına iki çözümleme aracı daha:

**Parametre süpürmesi** — bir girdiyi (oksijen, basınç, yerçekimi, akış, kalınlık) aralık boyunca değiştirir ve her noktada riski hesaplar. En kıymetli çıktısı **güvenlik eşiği**: güvenlik katsayısının 1'in altına düştüğü değer, yani "bu malzeme için oksijeni en fazla kaça kadar çıkarabilirim" sorusunun cevabı. Nokta başına 0,3–1,2 sn, en fazla 120 nokta.

**Vaka karşılaştırma** — kütüphaneden iki vakayı (ya da ekrandaki çözüm ile bir kaydı) yan yana koyar; farklı girdileri sarı ile işaretler, sonuçları tek tabloda verir ve iki oksijen eğrisini üst üste çizer.

---

## Kurulum (kullanıcı)

`AHUT-FLARE-Kurulum.exe` → İleri → Kur. Windows 10/11 dışında bir şey gerekmez; Python, model ve veri programın içinde gelir.

Ayrıntı için [BENIOKU.txt](BENIOKU.txt).

---

## Geliştirme ortamı

```bash
conda create -n yangin python=3.12
conda activate yangin
pip install -r gereksinimler.txt
python ahut_flare.py
```

> Python **3.12** gerekir. Model `scikit-learn 1.4.1.post1` ile eğitilmiştir ve aynı sürümle açılmalıdır; 3.13+ bu sürümü desteklemez.

**Linux (sudo gerekmez):**

```bash
./calistir.sh              # ilk açılışta .venv kurar (--system-site-packages) ve pywebview'i pip ile yükler
./calistir.sh --sinama     # pencere açmadan kendini sınar
```

Linux'ta pencere GTK (WebKit2GTK 4.1) ile açılır; dağıtımdan `python3-gi` ve `gir1.2-webkit2-4.1` gerekir.
Arayüz ve `render/` aynı yerel kökenden (yalnız 127.0.0.1) sunulur, çünkü pywebview sayfayı kendi HTTP sunucusundan açar
ve `file://` videolar yüklenmez. pywebview'in `eval`/`new Function` kullanımı sayfanın CSP'sine takıldığı için
`ahut_flare.py::pywebview_hazirla` bunları eval'siz karşılıklarıyla değiştirir (CSP gevşetilmez). Windows'ta bu iki uyarlama uygulanmaz, eski davranış korunur.

**Backend klasörü (`motor/`):** ana klasördeki güncel dosyalarla `python3 motor_esitle.py` eşitler (DASHBOARD.md §5).
Backend'in yazdığı dosyalar (`malzeme_onbellek.json`, `topluluk/topluluk.sqlite`, `loglar/tahmin_kayit.jsonl`)
`YANGIN_VERI_KLASORU`'na (= `veri/`) gider; `motor/` salt okunur olabilir. Yerel denemede EVREN anahtarı bir üst
klasördeki `evren_anahtar.txt`'den okunur (kopyalanmaz; `EVREN_ANAHTAR_DOSYASI` ile değiştirilebilir).

**Videolar:** `python3 render_esle.py` OpenFOAM videolarını `render_eslesme.csv`'ye göre `render/`'a adlandırarak kopyalar.

Komut satırı seçenekleri:

```
python ahut_flare.py              gerçek model
python ahut_flare.py --mock       sahte veri (model yüklemeden arayüz denemesi)
python ahut_flare.py --ayikla     geliştirici araçları açık
python ahut_flare.py vaka.ahut    dosyayı açarak başlat
```

Arayüzde değişiklik yaptıktan sonra pencereyi kapatıp açmak yeterlidir; `--ayikla` ile açıkken sağ tık → Yenile de çalışır.

---

## Mimari

```
ahut_flare.py          giriş noktası: pywebview penceresi, yollar, --sinama
calistir.bat           geliştirme başlatıcısı (konsolsuz)
sorun_gider.bat        açılmıyorsa: paket kontrolü + kendi kendini sınama + konsollu açılış
cekirdek/
  kopru.py              ekranın çağırdığı Python API'si (HTTP yok, port yok)
  github.py             GitHub ile paylaşım (yalnızca stdlib urllib)
  depo.py               profil, ayarlar, .ahut vaka kütüphanesi
  sistem.py             işlemci ölçümü, render klasörü izleme
motor/                  model ve fizik motoru — DIŞARIDAN GELİR, DEĞİŞTİRİLMEZ
  tahmin.py             tek giriş noktası: tahmin(), oksijen_egrisi(), ...
  risk_modeli.py, motor.py, hafif_motor.py, motor_kontrol.py, llm_analiz.py
  modeller/risk.joblib  eğitilmiş risk modeli
  *.csv                 deney verisi ve önbellekler
  BACKEND_API.md        motorun sözleşmesi (alanlar, birimler, hata durumları)
arayuz/
  index.html            kabuk iskeleti
  stil/                 temel.css (marka) · kabuk.css (düzen) · icerik.css (ekranlar)
  js/                   dil.js · kopru.js · grafik.js · kabuk.js · uygulama.js
  marka/ yazi/ vendor/  logo, Montserrat, three.js
veri/                   yazılabilir: ayarlar, profil, vakalar/, ornekler/, topluluk önbelleği
site/                   GitHub Pages sitesinin kaynağı (uygulama depoya yükler)
render/                 OpenFOAM çıktıları buraya düşer
paketleme/              PyInstaller tarifi + Inno Setup betiği
```

**Ekran ile Python arasında HTTP yoktur.** `cekirdek/kopru.py` içindeki her genel metot, arayüzde `pywebview.api.<ad>()` olarak çağrılır ve bir Promise döner. Yerel sunucu açılmaz, port dinlenmez.

**`motor/` klasörüne dokunulmaz.** Model ekibi oradaki dosyaları güncellediğinde klasörü olduğu gibi değiştirmek yeterlidir; arayüz yalnızca `BACKEND_API.md`'de yazan alanlara bakar ve hepsinin `null` gelebileceğini varsayar.

---

## Arayüz düzeni

ANSYS Workbench / Mechanical düzeni örnek alınmıştır:

```
┌──────────────────────────────────────────────────────────┐
│ Dosya Düzen Görünüm Birimler Araçlar Profil Yardım       │  menü
├──────────────────────────────────────────────────────────┤
│ Yeni  Aç  Kaydet │ ▶ ÇÖZ  Yorum │ Rapor  Paylaş │ Sunum  │  araç çubuğu
├──────────────────────────────────────────────────────────┤
│ Başlangıç │ Vaka Kurulumu │ Çözüm │ Sonuçlar │ Kütüphane │  sekmeler
├────────────────┬─────────────────────────────────────────┤
│ ANAHAT         │                                         │
│  ▾ Vaka        │           GÖRSELLEŞTİRME                │
│    Ortam       │                                         │
│    Malzeme     │                                         │
│    Akış        ├─────────────────────────────────────────┤
├────────────────┤ Mesajlar │ Tablo Verisi │ Günlük        │
│ AYRINTILAR     │                                         │
│  ad │ değer    │                                         │
├────────────────┴─────────────────────────────────────────┤
│ Model hazır │ vaka │ süre │        işlemci │ v1.0.0      │  durum çubuğu
└──────────────────────────────────────────────────────────┘
```

Ağaçta bir düğüm seçilir, sol alttaki **Ayrıntılar** tablosundan değerleri girilir, **ÇÖZ**'e basılır; Çözüm sekmesi açılır, biter ve Sonuçlar sekmesine geçilir. Paneller fare ile yeniden boyutlandırılır, düzen saklanır.

---

## Vaka dosyası biçimi (`.ahut`)

Düz JSON. Kendi kendine yeterlidir — başka bir bilgisayarda açılır, bir depoya konabilir, satır satır karşılaştırılabilir.

```jsonc
{
  "bicim": "ahut-vaka", "bicim_surumu": 1,
  "id": "891e846370a1",
  "baslik": "pmma · ISS · %21 O₂ · ÇOK YÜKSEK",
  "aciklama": "...", "etiketler": ["pmma", "mikro-g", "iss"],
  "yazar": { "ad": "...", "kurum": "...", "rol": "...", "baglanti": "..." },
  "olusturma": "2026-11-12T20:49:46", "guncelleme": "...",
  "uygulama": { "ad": "AHUT FLARE", "surum": "1.0.0" },
  "onayar": "ISS",
  "girdi":  { "malzeme": "pmma", "oksijen": 21, "basinc": 101.3, "g": 1e-4, ... },
  "sonuc":  { "tahmin": {...}, "oksijen_egrisi": {...}, "harita": {...},
              "akis_egrisi": {...}, "yakin": [...] },
  "llm_yorum": null,
  "supurme": { "parametre": "oksijen", "bas": 14, "son": 30, "adim": 1, "noktalar": [...] },
  "render": "pmma_g1e-4_o21_p101.3.mp4",
  "yorumlar": [ { "yazar": "...", "zaman": "...", "metin": "..." } ]
}
```

---

## Paylaşım: GitHub'ın kendisi arka uç

Sunucu, veritabanı ve hesap sistemi yoktur. Paylaşılan her vaka, bir GitHub
deposundaki `vakalar/` klasörüne düşen bir `.ahut` dosyasıdır; GitHub Pages
aynı depoyu statik bir site olarak yayımlar.

```
depo/
  index.html  stil.css  temel.js  grafik.js  site.js   <- Pages sitesi (uygulama yükler)
  depo.json                                            <- sahip/depo bilgisi
  vakalar/2026-11-14-pmma-iss-a1b2.ahut                <- paylaşılan vakalar
```

**Kurulum (bir kez):** GitHub'da *public* bir depo açın → Settings → Pages →
`main` / root. Ardından ince ayarlı bir kişisel erişim jetonu üretin (yalnızca o
depoya `Contents: Read and write`). Uygulamada **Profil → Paylaşım deposu**
bölümüne depo adını ve jetonu girin, **Siteyi Kur**'a basın: site dosyaları
depoya yüklenir.

**Paylaşma:** Araç çubuğundaki **Paylaş** → vaka depoya commit'lenir ve canlı
adresi verilir. Aynı vaka tekrar paylaşılırsa üstüne yazılır.

**Topluluk sekmesi** listeyi canlı çeker. İnternet yoksa son indirdiği listeyi
(önbellek) ve uygulamayla gelen örnekleri gösterir, başlıkta *çevrimdışı* yazar —
demo sırasında bağlantı giderse ekran boş kalmaz.

> Jeton yalnızca `veri/profil.json` içinde durur (`.gitignore`'da), ekrana hiç
> gönderilmez, paylaşılan vaka dosyasına yazılmaz ve kurulum paketine girmez.

---

## Paketleme

```bat
paketleme\exe_olustur.bat
```

1. PyInstaller ile `dist\AHUT FLARE\` üretilir (~250 MB, model ve veri dahil).
2. [Inno Setup 6](https://jrsoftware.org/isdl.php) kuruluysa `paketleme\Cikti\AHUT-FLARE-Kurulum.exe` oluşur.
3. Inno Setup yoksa taşınabilir `AHUT-FLARE-tasinabilir.zip` üretilir.

Kurulu sürümde yazılabilir dosyalar `%LOCALAPPDATA%\AHUT FLARE\` altındadır (Program Files'a yazılamaz). Exe'nin yanında `tasinabilir.txt` varsa her şey exe'nin yanında tutulur.

---

## Gizlilik ve güvenlik

- `evren_anahtar.txt` **gizlidir**: depoya girmez (`.gitignore`), kurulum paketine konmaz, ekranda ve günlükte yazdırılmaz.
- Program yapay zeka yorumu dışında internete çıkmaz; model, veri ve grafikler tamamen yereldir.
- Kaydedilen vakalar ve profil yalnızca kendi bilgisayarınızda durur; paylaşmak için dosyayı siz dışa aktarırsınız.

---

## Sorumluluk reddi

Sonuçlar model tahminidir. Güvenlik payı eklenmemiştir ve resmî bir malzeme kabul belgesi (ör. NASA-STD-6001) yerine geçmez. Güven skoru düşükken risk seviyesi tek başına kesin bir sonuç gibi kullanılmamalıdır.
