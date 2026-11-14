# Dashboard teslim notu — yangın riski tahmini

Tek giriş noktası `tahmin.py` içindeki `tahmin()` fonksiyonudur. Diğer dosyaları doğrudan çağırmanıza gerek yok.

## 1. Nasıl çağrılır

```python
from tahmin import tahmin

sonuc = tahmin("pmma", oksijen=30, basinc=70, g=0.38)          # hızlı (~0,1–0,6 sn)
sonuc = tahmin("pmma", oksijen=30, basinc=70, g=0.38, llm=True) # + LLM yorumu (~25 sn)
```

Komut satırından (JSON yazar):

```
python3 tahmin.py --malzeme pmma --oksijen 30 --basinc 70 --g 0.38 [--akis 5] [--llm]
```

- Program **proje klasöründen** çalıştırılmalı (dosya yolları göreli).
- İlk çağrı modeli yüklediği için biraz daha uzun sürer. Sunucuda modülü bir kez import edip açık tutun.
- Dönen sözlük `json.dumps` ile doğrudan yazılabilir: numpy tipi yok, NaN yerine `None`.

### Parametreler

| Parametre | Zorunlu | Birim / değer | Verilmezse |
|---|---|---|---|
| `malzeme` | ✅ | `pmma`, `sibal`, `cotton`, `nomex`, `silicone`, `n-heptane`, `methanol`, `methane` (başkası da olur ama daha belirsiz) | – |
| `oksijen` | ✅ | ortamdaki O2, % (örn. 21) | – |
| `basinc` | ✅ | kPa (Dünya = 101) | – |
| `g` | ✅ | Dünya = 1; ISS ≈ 1e-4; Ay 0,165; Mars 0,38 | – |
| `akis` | | hava akışı, cm/s; **0 = durgun ortam** | `None` = bilinmiyor → en kötü durum varsayılır |
| `kalinlik` | | mm | malzeme varsayılanı |
| `numune_tipi` | | `thin_sheet`, `fabric`, `droplet`, `gas_jet` … | malzeme varsayılanı |
| `yakit_turu` | | `kati`, `sivi`, `gaz` | malzeme varsayılanı |
| `akis_yonu` | | akışın alevle yönü | `None` |
| `seyreltici` | | `n2`, `co2`, `he` … | `"n2"` |
| `llm` | | `True` / `False` | `False` |

**Malzeme varsayılanları** (`numune_tipi`, kalınlık, yakıt türü):

| Malzeme | Numune tipi | Kalınlık | Yakıt türü |
|---|---|---|---|
| pmma | thin_sheet | 0,2 mm | katı |
| sibal | fabric | 0,33 mm | katı |
| cotton | fabric | 0,3 mm | katı |
| nomex | fabric | 0,37 mm | katı |
| silicone | thin_sheet | 0,36 mm | katı |
| n-heptane | droplet | 1 mm | sıvı |
| methanol | droplet | 1 mm | sıvı |
| methane | gas_jet | – | gaz |

Kullanılan varsayılanlar sonuçta `kullanilan_varsayilanlar` alanında listelenir.

## 2. Dönen JSON'un alanları

| Alan | Anlamı |
|---|---|
| `girdi` | Hesapta gerçekten kullanılan değerler (varsayılanlar dahil); `akis: null` akışın bilinmediğini gösterir. |
| `yanma_ihtimali` | Risk modeline göre alevin yanmaya devam etme ihtimali (0–1). |
| `belirsizlik` | Modeller arası standart sapma (0–1); 0,3'ün üstü uyarı üretir. |
| `risk_seviyesi` | İhtimalin sözel karşılığı: DÜŞÜK (<%20), ORTA (<%50), YÜKSEK (<%80), ÇOK YÜKSEK. |
| `sonme_siniri` | Bu O2 yüzdesinin altında alev söner (%5–60 aralığı taranır); `null` = aralıkta bulunamadı. |
| `guvenlik_katsayisi` | `sonme_siniri / oksijen`: 1'den büyükse güvenli, 1'den küçükse yanabilir; `null` = hesaplanamadı. |
| `sinirlama` | Sadece Ay/Mars gibi kısmi g'de dolu: uzay, gerçek g ve Dünya için ayrı sonuçlar; ana sonuç bunların en kötüsüdür. Diğer durumlarda `null`. |
| `motor` | Fizik motorunun ikinci görüşü: `yanma` (0–1), `min_oksijen` (%), `yayilma_hizi` (mm/s), `sicaklik` (K); motor bu koşulu bilmiyorsa `null`. |
| `motor_turu` | Kullanılan fizik motoru (`hafif` = yarı-ampirik motor; `openfoam_sonuclar.csv` varsa `tablo`). |
| `motor_akis` | Motorun kullandığı akış (cm/s); akış bilinmiyorsa 0/5/10/20 içinden en kötüsü. |
| `guven.skor` | Sonuca ne kadar güvenilebileceği (0–100); 50'nin altı düşük güvendir. |
| `guven.veri_bileseni` | Bu koşula yakın deney sayısının yeterliliği (0–1). |
| `guven.uyum_bileseni` | Yakın deneylerin yanma oranının modelle ne kadar uyuştuğu (0–1); yakın deney yoksa `null`. |
| `guven.motor_bileseni` | Fizik motorunun bu bölgedeki deneyleri ne kadar iyi tahmin ettiği (0–1). |
| `guven.agirliklar` | Skorda kullanılan ağırlıklar (normalde 0,4 veri + 0,3 uyum + 0,3 motor). |
| `guven.yakin_deney`, `yanan`, `sonen`, `motorlu_yakin_deney`, `yakin_deney_yanma_orani`, `motor_yontemi` | Skorun nasıl hesaplandığını gösteren ayrıntılar; ekranda "ayrıntı" altında gösterilebilir. |
| `kullanilan_varsayilanlar` | Kullanıcı vermediği için otomatik doldurulan alanlar. |
| `uyarilar` | Kısa Türkçe uyarı cümleleri listesi; boş liste uyarı olmadığını gösterir. |
| `sure_sn` | Çağrının sürdüğü süre (saniye). |
| `llm_yorum` | Sadece `llm=True` ise: LLM'in kısa Türkçe yorumu; başarısız olursa "LLM yorumu alınamadı (…)" metni. |

## 3. Ekranda mutlaka gösterilmesi gerekenler

1. **Risk seviyesi** (`risk_seviyesi`), renk koduyla.
2. **Güvenlik katsayısı** (`guvenlik_katsayisi`): 1'in altında olduğu açıkça belirtilmeli. `null` ise "hesaplanamadı" yazılmalı, 0 ya da boş bırakılmamalı.
3. **Güven skoru** (`guven.skor`): 50'nin altındaysa "düşük güven" vurgulanmalı.
4. **Uyarılar** (`uyarilar`): hepsi, kısaltmadan gösterilmeli.
5. **Kullanılan varsayılanlar** (`kullanilan_varsayilanlar`, ayrıca `girdi.akis` `null` ise "akış bilinmiyor"): kullanıcı neyin tahmin edildiğini görmeli.

Güven skoru düşükken risk seviyesi tek başına kesin bir sonuçmuş gibi sunulmamalı.

## 4. `llm=True` kullanımı

- Model ve motor sonucunun üstüne EVREN LLM'den (varsayılan model `gemma-4-31b`, `LLM_MODEL` ortam değişkeniyle değişir) kısa bir yorum ekler.
- Yorumun ilk satırındaki KARAR satırını kod üretir; LLM sadece gerekçeyi yazar.
- JSON'da karşılığı olmayan sayılar sonda "⚠️ Doğrulanamayan sayılar" olarak işaretlenir.
- **Süre ~25 sn.** HTTP 429/503 ya da zaman aşımında 5 sn bekleyip bir kez daha dener; en kötü durumda birkaç dakika sürebilir.
- **Arka planda çağrılmalı.** Önerilen akış:
  1. Önce `llm=False` ile sonucu hemen gösterin.
  2. Ardından `llm=True` çağrısını arka planda (thread, iş kuyruğu) yapın.
  3. Yorum gelince ekleyin.
- Hata durumunda istisna fırlatmaz: `llm_yorum` "LLM yorumu alınamadı …" ile başlar ve aynı mesaj `uyarilar`'a da eklenir.

## 5. Gerekli dosyalar

Hepsi aynı klasörde olmalı ve program o klasörden çalıştırılmalı.

| Dosya | Görevi |
|---|---|
| `tahmin.py` | Giriş noktası |
| `risk_modeli.py` | Risk modeli sınıfları ve yardımcıları (model dosyasını açmak için gerekli) |
| `modeller/risk.joblib` | Eğitilmiş risk modeli |
| `motor.py` | Fizik motoru seçici |
| `hafif_motor.py` | Yarı-ampirik fizik motoru |
| `hafif_motor_parametreleri.json` | Motorun kalibre parametreleri |
| `motor_kontrol.py` | Güven skoru hesabı |
| `motor_karsilastirma.csv` | Güven skoru için deney ve motor tablosu (önbellek) |
| `hafif_motor_dogrulama_noktalar.csv` | Güven skorundaki motor bileşeni için çapraz doğrulama tahminleri |
| `psi_etiketli*.csv` (5 dosya), `etiketli_gemma3.csv` | Önbellek eksik ya da eskiyse yeniden üretmek için deney verisi |
| `llm_analiz.py` | Sadece `llm=True` için |
| `evren_anahtar.txt` | Sadece `llm=True` için: EVREN API anahtarı |

Python 3 ve şu paketler gerekli: numpy, pandas, scikit-learn, scipy, joblib, matplotlib (matplotlib sadece önbellek yeniden üretilirken; sürümleri `requirements` olarak sabitlemek iyi olur; geliştirme ortamı: numpy 1.26, pandas 2.1, scikit-learn 1.4, scipy 1.11). `joblib` model dosyası aynı scikit-learn sürümüyle açılmalı.

> ⚠️ **`evren_anahtar.txt` gizlidir.**
> - Git'e eklenmemeli, sohbet ya da e-postayla paylaşılmamalı, ekran görüntüsüne ve loglara girmemeli.
> - Herkes kendi anahtarını bu dosyaya koymalı.
> - Kod anahtarı hiçbir yerde yazdırmaz.
> - Dosya yoksa `llm=True` çağrısı sadece "LLM yorumu alınamadı (… anahtar dosyası yok)" döner; diğer sonuçlar etkilenmez.

> Not: Klasörde `openfoam_sonuclar.csv` bulunursa motor otomatik olarak `tablo` moduna geçer. Hafif motorda kalmak için ya o dosyayı koymayın ya da `MOTOR_TURU=hafif` ortam değişkenini verin.
