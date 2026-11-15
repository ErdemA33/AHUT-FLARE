# Yangın Riski Dashboard'u — Tasarım Belgesi

Bu belge dashboard ekibi için yazıldı. Dashboard'da **ne gösterileceğini** ve **her öğenin verisinin nereden geleceğini** tanımlar. Arayüz teknolojisinden bağımsızdır.

- **Hedef:** yerel olarak, ayrı pencerede çalışan bir masaüstü uygulaması.
- **Arka uç:** proje klasöründeki Python kodu (`predict.py`).
- **Kısa API notu:** `DASHBOARD_DELIVERY.md`. Bu belge onun genişletilmiş hâlidir.

**Gösterim kuralı:** Belgede `tahmin.alan.alt_alan` biçimi, `tahmin()` çağrısının döndürdüğü sözlükteki alanı gösterir.

- Örnek: `tahmin.guven.skor` → `tahmin(...)["guven"]["skor"]`.
- `oksijen_egrisi.ihtimal` gibi yazımlar, aşağıdaki yardımcı fonksiyonların çıktısındaki alanlardır.

---

## 0. Genel mimari

```
 [Arayüz]  --girdiler-->  tahmin(**kosul)                 --> sonuç sözlüğü (JSON)        ~0,1–0,6 sn
                          oksijen_egrisi(**kosul)         --> grafik (a)                   ~0,1–0,3 sn
                          yanabilirlik_haritasi(**kosul)  --> grafik (b)                   ~0,15–0,2 sn
                          akis_egrisi(**kosul)            --> grafik (c)                   ~0,01 sn
                          yakin_deneyler(**kosul)         --> yakın deney tablosu          ~0,005 sn
                          tahmin(**kosul, llm=True)       --> + llm_yorum   (ARKA PLANDA)  ~25 sn
```

- **`kosul` sözlüğü** bütün fonksiyonlara aynen verilir. Anahtarları `tahmin()`'in parametreleridir (bkz. §1.2). Fazladan anahtarlar (`llm` gibi) yardımcı fonksiyonlarda yok sayılır.
- **Hepsi aynı süreçte çalışır.**
  - `import tahmin` bir kez yapılır (~0,4 sn); model ilk çağrıda yüklenip bellekte kalır.
  - Bu yüzden Python tarafı her hesaplamada yeniden başlatılmamalıdır.
  - Arayüz Python dışı bir dildeyse, uzun yaşayan bir Python yardımcı süreci (stdin/stdout JSON ya da yerel soket) önerilir.
- **"Hesapla" düğmesi** sırayla `tahmin`, `oksijen_egrisi`, `yanabilirlik_haritasi`, `akis_egrisi` ve `yakin_deneyler` fonksiyonlarını çağırır. Toplam ~0,5–1 sn sürer; arayüz donmasın diye bu da tercihen ayrı bir iş parçacığında yapılmalıdır.
- **Bütün çıktılar** `json.dumps(..., allow_nan=False)` ile yazılabilir. Numpy tipi yoktur; eksik değerler `null` (Python'da `None`) olarak gelir.
- **Çalışma klasörü:** Uygulama Python tarafını proje klasöründe çalıştırmalıdır, çünkü dosya yolları göreli.

---

## SEKME 1 — "Vaka Kur"

### 1.1 Ortam ön ayarları

Tek tıkla girdileri doldurur. Ön ayar seçilince doldurduğu kutular hemen düzenlenebilir olmalıdır. Kullanıcı bir değeri değiştirirse ön ayar adı "Özel" olur.

| Ön ayar | g | Oksijen (%) | Basınç (kPa) | Not |
|---|---|---|---|---|
| Dünya kabini | 1 | 21 | 101,3 | |
| ISS | 1e-4 | 21 | 101,3 | |
| Ay üssü | 0,165 | 21 | 101,3 | O2 ve basınç verilmedi; Dünya havası varsayıldı, kullanıcı değiştirebilir |
| Mars üssü | 0,38 | 21 | 101,3 | Aynı not |
| NASA keşif atmosferi | *değişmez* | 34 | 56,5 | Sadece O2 ve basıncı değiştirir; g mevcut değerinde kalır |
| Saffire-VI benzeri | 1e-4 | 31 | 54 | Saffire deneyleri yörüngede (mikro-g) yapıldı |
| Özel | – | – | – | Hiçbir alanı değiştirmez |

Ön ayarlar seyrelticiyi `n2` yapar. Akış, malzeme ve numune alanlarına dokunmaz.

### 1.2 Girdiler

| Arayüz öğesi | Tür | `tahmin()` parametresi | Kurallar |
|---|---|---|---|
| Yerçekimi | sayı kutusu (bilimsel gösterim kabul edilmeli: `1e-4`) + yardımcı etiket "Dünya = 1" | `g` (zorunlu) | `g > 0` olmalı. 1e-5'ten küçük değerler model tarafından 1e-5 gibi ele alınır. |
| Oksijen | kaydırıcı **ve** sayı kutusu (birbirine bağlı) | `oksijen` (zorunlu), % | Aralık 5–60, adım 0,25 önerilir |
| Basınç | sayı kutusu | `basinc` (zorunlu), kPa | > 0 olmalı. Veri çoğunlukla 30–101 kPa aralığında. |
| Hava akışı | sayı kutusu (cm/s) + **"bilinmiyor"** onay kutusu | `akis` | "Bilinmiyor" işaretliyse `akis=None` gönderilir ve sayı kutusu pasif olur. `0` = durgun ortam (bilinmiyor ile aynı şey değil). |
| Malzeme | açılır liste: `pmma`, `sibal`, `cotton`, `nomex`, `silicone`, `n-heptane`, `methanol`, `methane`, **diğer** | `malzeme` (zorunlu) | "diğer" seçilince serbest metin kutusu açılır; yazılan ad aynen gönderilir. |
| Numune tipi | açılır liste: `thin_sheet`, `thick_sheet`, `fabric`, `rod`, `wire`, `sphere`, `droplet`, `pool`, `gas_jet` | `numune_tipi` | Boş bırakılabilir |
| Kalınlık | sayı kutusu (mm) | `kalinlik` | Boş bırakılabilir. Gaz jetinde gizlenebilir. |
| Ortam gazı (seyreltici) | açılır liste: `n2` (hava), `co2`, `he`, `ar`, `xe` | `seyreltici` | Varsayılan `n2` |
| (gelişmiş, isteğe bağlı) Yakıt türü, akış yönü | açılır liste | `yakit_turu`, `akis_yonu` | Varsayılan: boş |

**Malzeme seçilince varsayılanlar otomatik dolar.** Varsayılan değerler `predict.py` içindeki `MALZEME_VARSAYILAN` sözlüğündedir; arayüz bunları doğrudan okuyabilir (`from tahmin import MALZEME_VARSAYILAN`).

| Malzeme | Numune tipi | Kalınlık (mm) | Yakıt türü |
|---|---|---|---|
| pmma | thin_sheet | 0,2 | kati |
| sibal | fabric | 0,33 | kati |
| cotton | fabric | 0,3 | kati |
| nomex | fabric | 0,37 | kati |
| silicone | thin_sheet | 0,36 | kati |
| n-heptane | droplet | 1,0 | sivi |
| methanol | droplet | 1,0 | sivi |
| methane | gas_jet | – | gaz |

- **Gri işaret:** Otomatik dolan kutular gri yazıyla gösterilir ve yanlarına küçük "varsayılan" etiketi konur. Kullanıcı kutuyu değiştirince gri işaret kalkar.
- **Gönderim:** Arayüz gri (varsayılan) alanları **`None` olarak gönderir**; `tahmin()` aynı değeri kendisi doldurur. Böylece `tahmin.kullanilan_varsayilanlar` doğru kalır.
- **Doğrulama:** Hesaplamadan sonra gri işaretler `tahmin.kullanilan_varsayilanlar` ile kontrol edilebilir.
- **"diğer" malzeme:** Listede olmayan bir ad yazılırsa `tahmin()` onu yapay zekaya (EVREN) sınıflandırtır (bkz. §1.5).

### 1.5 Listede olmayan malzeme: yapay zeka önerisi
- **Listede sayılanlar:** açılır listedeki malzemeler ve veri setinde en az 5 deneyi olan malzemeler (`llm_analiz.bilinen_malzemeler()`).
- **Listede yoksa:**
  - `tahmin()` adı yapay zekaya sorar (temperature 0).
  - Cevap kodla denetlenir: izin verilen değerler, listede olmayan (uydurma) malzeme adı kabul edilmez, yakıt türü ile numune tipi tutarlı olmalı.
  - Hesap, önerilen **benzer malzeme** ile yapılır.
- **Ne kadar sürer:** ilk sorgu ~15–90 sn. Sonuç `material_cache.json`'a yazılır; aynı ad bir daha sorulmaz, çevrimdışı da çalışır.
- **Çıktı:** `tahmin.llm_siniflandirma`, alanları `girilen`, `durum` (`kabul` / `reddedildi` / `baglanti_yok`), `yakit_turu`, `benzer_malzeme`, `numune_tipi`, `gerekce`, `kaynak` (`llm` / `onbellek`).
- **Ekranda öneri kutusu olarak gösterilir:**
  > **Öneri —** "kevlar" listede yok. Yapay zeka **nomex** (katı, kumaş) malzemesine benzetti: "Kevlar ve Nomex … aromatik poliamid … kumaşlardır."
  > **[Onayla]** **[Değiştir]**
  - **Onayla:** Kutu kapanır, sonuç kalır.
  - **Değiştir:** Malzeme açılır listesi açılır; kullanıcı bir malzeme seçince yeniden hesaplanır.
  - Onaylanana kadar sonuç ekranında "malzeme yapay zeka önerisiyle eşlendi" etiketi durur.
- **Sınıflandırma yapılamazsa:**
  - **Ne zaman:** `durum` `reddedildi` ya da `baglanti_yok` olduğunda; örneğin anlamsız bir ad ya da internet yok.
  - **`tahmin()` ne döner:** Sayı üretmez; `yanma_ihtimali`, `risk_seviyesi` vb. `null` gelir.
  - **Uyarı:** "'…' malzemesi tanınmadı, listeden seçin (…)".
  - **Arayüz:** Bu uyarıyı gösterip malzeme listesini açmalı.
- **Uzun bekleme:** İlk sorgu uzun sürebildiği için listede olmayan bir adla "Hesapla" da arka planda çalıştırılmalı ve yüklenme göstergesi gösterilmeli.

### 1.6 Malzeme kütüphanesi ve eş anlamlı tanıma (2026-11-13)
- **Dosya:** `material_library.json` (44 malzeme; `material_library_generate.py` üretir). Her kayıt: ad, eş anlamlılar,
  yakıt türü, varsayılan numune ve kalınlık, `motor_benzeri`, kaynaklı özellikler (NIST WebBook, SFPE, `chemicals`),
  `durum` ("motorda kalibre" / "veri setinde N nokta var" / "veri yok"), uzayda kullanım. Modele girmez.
- **Tanıma sırası:** bilinen liste → kütüphane (ad / id / İngilizce ad / eş anlamlı; Türkçe-aksan duyarsız) → kullanıcı
  kütüphanesi (`<YANGIN_VERI_KLASORU>/user_materials.json`, yalnız `onay = onayli`) → LLM.
- **Yeni alan `tahmin.kutuphane_eslesme`:** `{girilen, id, ad, kaynak (kutuphane|kullanici), durum, motor_benzeri,
  model_malzeme, zayif_esleme, motor_agirligi_sifir}`. Kalibre değilse motor ağırlığı 0 ve uyarı; zayıf eşlemede
  "zayıf eşleme: <benzer>"; `motor_benzeri` boşsa motor çalışmaz ("Uygun motor yok").
- **`adimlar[no=2].ayrinti.kaynak`:** `liste | kutuphane | kullanici_kutuphanesi | llm | onbellek`.
- **Varsayılanlar:** `MALZEME_VARSAYILAN`'da olmayan tanınan malzeme (etilen, etan …) varsayılanı kütüphaneden alır.
- **Kullanıcı malzemesi önerisi:** `llm_analiz.malzeme_oner(ad)` (sınıflandırma + özellikler; hepsi "LLM önerisi,
  doğrulanmadı"). Onaysız kullanıcı malzemesi hiçbir hesaba girmez.

### 1.3 Düğmeler

| Düğme | Ne yapar | Süre | Arayüz davranışı |
|---|---|---|---|
| **Hesapla** | `tahmin(**kosul)` ve 4 yardımcı fonksiyon (§0) | ~0,5–1 sn | Sonuçlar Sekme 2 ve 3'e yazılır, vaka kayıtlı vakalara eklenir, log paneline satır düşer. Zorunlu alanlar boşsa pasif. |
| **Yapay zeka yorumu iste** | `tahmin(**kosul, llm=True)` | **~25 sn**; 429/503 ya da zaman aşımında 5 sn sonra bir kez daha dener, en kötü durumda birkaç dakika | **Arka planda** çalışır. Sekme 3'teki yorum kutusunda yüklenme göstergesi ("Yapay zeka yorumu hazırlanıyor… ~25 sn") gösterilir. Arayüz bu sürede kullanılabilir kalmalı. |

Yapay zeka yorumu için ek kurallar:
- Önce "Hesapla" yapılmış olmalı. Değilse düğme önce hesaplamayı yapar.
- Yorum gelince sadece `tahmin.llm_yorum` kullanılır. Diğer alanlar "Hesapla"nın sonucuyla aynıdır; yine de gelen sonuç vakaya kaydedilebilir.
- Girdiler bu sırada değiştirilip yeniden hesaplandıysa, gelen eski yorum **gösterilmemeli** ya da "önceki girdiler için" etiketiyle gösterilmeli. Bunun için gelen sonucun `girdi` alanı mevcut girdilerle karşılaştırılır.
- Aynı anda en fazla bir LLM isteği açık olmalı.

### 1.4 Kayıtlı vakalar

- **Liste:** Son 10 hesaplama tutulur, en yenisi üstte. 10'u aşınca en eskisi silinir.
- **Satır içeriği:**
  - Saat
  - Ön ayar adı (ya da "Özel")
  - Malzeme
  - g / O2 / basınç
  - Risk rozeti (`tahmin.risk_seviyesi`)
  - Güven skoru (`tahmin.guven.skor`)
- **Saklama:** Her vaka için `kosul` sözlüğü ve `tahmin()` çıktısının tamamı saklanır; varsa `llm_yorum` da eklenir. Kalıcılık için yerel bir JSON dosyası yeterli.
- **Tekrar açma:** Kayıtlı `kosul` girdilere yüklenir ve kayıtlı sonuç gösterilir. Model değişmiş olabileceği için "Yeniden hesapla" seçeneği de sunulur.
- **Karşılaştırma:** Listeden iki vaka seçilip yan yana açılır.
  - Gösterilenler:
    - Her iki vakanın girdileri (`tahmin.girdi`); farklı olan alanlar vurgulanır
    - `risk_seviyesi`
    - `yanma_ihtimali ± belirsizlik`
    - `sonme_siniri`
    - `guvenlik_katsayisi`
    - `guven.skor`
    - `motor.yanma`
    - `uyarilar` sayısı
  - İsteğe bağlı: iki vakanın oksijen eğrisi aynı grafikte çizilir (iki `oksijen_egrisi` çağrısı).

---

## SEKME 2 — "Analiz ve Loglar"

### 2.1 Ham sonuçlar

**Model**
| Öğe | Kaynak |
|---|---|
| Yanma ihtimali ± belirsizlik | `tahmin.yanma_ihtimali` ± `tahmin.belirsizlik` (ikisi de 0–1; yüzde olarak gösterilebilir) |
| Sönme sınırı (% O2) | `tahmin.sonme_siniri` (`null` → "bulunamadı") |
| Güvenlik katsayısı | `tahmin.guvenlik_katsayisi` |
| Kullanılan girdiler | `tahmin.girdi` (varsayılanlar dahil); `tahmin.kullanilan_varsayilanlar` ile işaretli |

**Sınırlama tablosu**
- Sadece `tahmin.sinirlama` `null` değilse gösterilir; bu durum 0,01 ≤ g < 0,9, yani Ay/Mars için geçerlidir.
- Diğer durumlarda tablo yerine "Bu yerçekiminde sınırlama yapılmadı" yazılır.

| Satır | g | Yanma ihtimali | Belirsizlik | Sönme sınırı | Güvenlik katsayısı | Risk |
|---|---|---|---|---|---|---|
| Uzay | `sinirlama.uzay.g` | `.yanma_ihtimali` | `.belirsizlik` | `.sonme_siniri` | `.guvenlik_katsayisi` | `.risk_seviyesi` |
| Gerçek g | `sinirlama.gercek_g.…` | … | … | … | … | … |
| Dünya | `sinirlama.dunya.…` | … | … | … | … | … |

Ana sonuç bu üçünün en kötüsüdür. Tablo altına şu not yazılır: "Ana sonuç en kötü satırdır (en yüksek ihtimal, en düşük sınır)."

**Fizik motoru**
| Öğe | Kaynak |
|---|---|
| Motor türü | `tahmin.motor_turu` (`yonlendirici` = yakıt türüne göre seçim; testte tek motor zorlanabilir) |
| Kullanılan motor | `tahmin.motor_kaynagi`: `damla` (sıvı damla, FLEX ile doğrulanmış damla motoru), `gaz` (gaz yakıt, `gas_engine.py`: BRE / s-Flame / jet), `hafif` (katı ve sıvı havuz, yarı-ampirik), `ofm_tablo` (OpenFOAM motorunun tablosu), `ofm+hafif` (tablo + hafif karışımı), `null` (motor sonuç vermedi) |
| Motorun dürüst test AUC'si | `tahmin.motor.motor_auc` (o motorun o yakıt grubunda, kalibrasyonda görmediği verideki AUC'si; `null` = doğrulama verisi yok **ya da yakıt/geometri kalibre değil → motor ağırlığı 0**). Damlada yakıt bazında (heptan, metanol: o yakıt dışarıda bırakılarak; etanol / n-dekan: `null`; 1-propanol: kontrol verisi). Gazda geometri bazında (düz 0,946; jet 0,816 kontrol seti ama jet her zaman `kalibre_degil`; küre `null`, 4 test). |
| Motor belirsizliği (yalnız damla) | `tahmin.motor_belirsizlik`: `{yanma, yanma_hizi_K, min_oksijen}` ± değerleri (FLEX deney grubu bootstrap, 50 kalibrasyon; ± = 16–84 yüzdelik yarı genişliği, yalnız kalibrasyon belirsizliği). Diğer motorlarda `null`. Gösterim: "motor yanma 0,77 ± 0,09". |
| Yakıt türü (motorun kullandığı) | `tahmin.motor.yakit_turu` (`kati` / `sivi` / `gaz`) |
| Damla motoruna özel | `tahmin.motor.yanma_hizi_K` (mm²/s), `tahmin.motor.sonme_capi` (mm; `null` = sönmedi), `sonme_turu` (`isinim` / `kimyasal` / `null`), `soguk_alev` (true/false) ve `soguk_alev_suresi_s` (kaba tahmin; true ise kırmızı not: "görünmeyen soğuk alev — yangın bitti sanılabilir"), `motor_kalibre` (yakıt FLEX'te var mı), `tasinim_dogrulanmadi` (akış > 0), `kismi_g_dogrulanmadi` (Ay/Mars), `isinim_temsili` (ışınım modelinin kısa açıklaması) |
| Gaz motoruna özel | `tahmin.motor.geometri` (`jet` / `kure` / `duz`; `numune_tipi`'nden: gas_jet → jet, porous_sphere / sızıntı / nokta kaynak → küre, flat / burner → düz), `sonme_turu` (`isinim` / `kimyasal` / `yok`), `alev_boyu` (mm; düz y_f, jet L_f), `alev_yaricapi` (mm; küre, düz), `kalibre_degil` (true → motor ağırlığı 0, nedeni `uyarilar`'da), ayrıca `sicaklik_adyabatik`, `isinim_orani`, `Z_st`, `debi_mg_s`, `kopma` (jet). **Not:** gaz motorunda ortam akışı modellenmiyor (`girdi.akis` kullanılmaz). |
| Motor yanma ihtimali | `tahmin.motor.yanma` |
| Motor sönme sınırı (% O2) | `tahmin.motor.min_oksijen` (alan yoksa "yok") |
| Yayılma hızı (mm/s) | `tahmin.motor.yayilma_hizi` (sıvı ve gazda yok) |
| Alev sıcaklığı (K) | `tahmin.motor.sicaklik` |
| Motorun kullandığı akış (cm/s) | `tahmin.motor_akis`. `girdi.akis` `null` ise yanına "(akış bilinmiyordu; 0/5/10/20 içinden en kötüsü)" yazılır. |

`tahmin.motor` `null` ise bölümde sadece "Fizik motoru bu koşulu bilmiyor" yazılır.

**Güven bileşenleri**
| Öğe | Kaynak |
|---|---|
| Skor (0–100) | `tahmin.guven.skor` |
| Veri bileşeni (0–1) | `tahmin.guven.veri_bileseni`; altında "yakın deney: `guven.yakin_deney`" |
| Uyum bileşeni (0–1) | `tahmin.guven.uyum_bileseni` (`null` → "hesaplanmadı: yakın deney yok"); altında "yakın deneylerin yanma oranı: `guven.yakin_deney_yanma_orani`" |
| Motor bileşeni (0–1) | `tahmin.guven.motor_bileseni`; altında `guven.motor_yontemi` metni ve `guven.yanan` / `guven.sonen` |
| Ağırlıklar | `tahmin.guven.agirliklar` (`veri`, `uyum`, `motor`) |

Formül de gösterilebilir: `skor = 100 × (veri·w_veri + uyum·w_uyum + motor·w_motor)`. Normal ağırlıklar 0,4 / 0,3 / 0,3'tür. Yakın deney yoksa 0,7 / 0 / 0,3 olur.

### 2.2 Yakındaki gerçek deneyler tablosu

**Kaynak:** `yakin_deneyler(**kosul, en_fazla=10)`.

| Sütun | Alan |
|---|---|
| Kaynak | `kaynak`: "NASA PSI", "makale (elle)" ya da "makale (otomatik, Gemma)" |
| Deney adı | `makale_id`. `aciklama` doluysa (NASA PSI satırları) ipucu metni olarak gösterilir. |
| Koşullar | `g`, `oksijen` (%), `basinc` (kPa), `akis` (cm/s), `malzeme` |
| Sonuç | `yanar`: 1 → "yandı" (kırmızı), 0 → "söndü" (yeşil), `null` → "–" |
| Link | `link`. Doluysa tıklanınca sistem tarayıcısında açılır; `null` ise boş. |

Tablo kuralları:
- **Kaynak güvenilirliği:** "makale (otomatik, Gemma)" satırları bir dil modeliyle makalelerden otomatik çıkarıldı ve daha az güvenilir. Bu satırlar soluk renkte ya da bir simgeyle gösterilmeli. NASA PSI ve elle çıkarılmış satırlar güvenilir etiketlidir.
- **Sıralama:** Satırlar yakınlığa göre sıralı gelir; arayüz yeniden sıralamamalıdır.
- **Başlık:** "Yakın deneyler (toplam `tahmin.guven.yakin_deney`, ilk 10 gösteriliyor)".
- **Boş liste:** "Bu koşula yakın gerçek deney yok — sonuç tamamen modele dayanıyor" yazılır.
- **Yinelenen satırlar:** Veride aynı koşulların birden fazla kaydı olabilir (aynı makalede tekrarlanan deneyler); tabloda yan yana aynı satırlar görülebilir.

### 2.3 Grafikler

Üç grafik de "Hesapla" ile yeniden çizilir.

**(a) Oksijen eğrisi** — kaynak: `oksijen_egrisi(**kosul)`
- x ekseni: `oksijen` (%5–60). y ekseni: `ihtimal` (0–1).
- Gölgeli belirsizlik bandı: `alt` ile `ust` arası.
- Dikey çizgiler:
  - Mevcut oksijen: `tahmin.girdi.oksijen`, düz çizgi, etiket "ortam".
  - Sönme sınırı: `oksijen_egrisi.sonme_siniri` (= `tahmin.sonme_siniri`), kesikli çizgi, etiket "sönme sınırı". `null` ise çizilmez.
- Yatay ince çizgi: y = 0,5 ("yanar/söner eşiği").
- Yakın deney noktaları: `yakin_deneyler(...)` çıktısı (gerekirse `en_fazla` artırılabilir).
  - Konum: x = `oksijen`; y = 1 (yandı) ya da 0 (söndü).
  - Görünüm: yandı kırmızı, söndü yeşil. Üst üste binmemeleri için hafif dikey kaydırma uygulanır.
  - Bu noktalar yakın deney tanımı gereği mevcut oksijenin ±3 puanı içindedir. Tüm eğri boyunca deney göstermek istenirse ileride ayrı bir fonksiyon gerekir.
- Kısmi g'de eğri uzay, gerçek g ve Dünya eğrilerinin en kötüsüdür. Grafik altına bir not konmalı.

**(b) Yanabilirlik haritası** — kaynak: `yanabilirlik_haritasi(**kosul, n_g=40, n_o2=40)`
- x ekseni: `g` (log ölçek, 1e-5…1). y ekseni: `oksijen` (%5–60).
- Hücre rengi `ihtimal[i][j]` ile belirlenir; `i` g indeksi, `j` oksijen indeksidir. Renk risk eşiklerine göre ayrık verilir:

  | Aralık | Renk |
  |---|---|
  | < 0,2 | yeşil |
  | 0,2–0,5 | sarı |
  | 0,5–0,8 | turuncu |
  | ≥ 0,8 | kırmızı |

  İsterseniz sürekli renk skalası da kullanılabilir.
- Mevcut vaka (`girdi.g`, `girdi.oksijen`) belirgin bir işaretle (artı ya da halka) gösterilir.
- Referans çizgileri (isteğe bağlı): ISS (1e-4), Ay (0,165), Mars (0,38), Dünya (1) için dikey çizgiler.
- Basınç, malzeme, akış ve diğer girdiler mevcut vakadan alınır. Haritada **en kötü durum alınmaz**; her g kendi değeriyle hesaplanır. Bu yüzden Ay/Mars sütunu ana sonuçtan daha iyimser görünebilir. Grafik altına not konmalı.

**(c) Akış eğrisi (U-şekli)** — kaynak: `akis_egrisi(**kosul)`
- x ekseni: `akis` (log ölçek, 0,1–100 cm/s, 40 nokta). y ekseni: `motor_yanma` (0–1).
- Yatay çizgi: 0,5.
- Mevcut akış: `girdi.akis` `null` değilse dikey çizgi çizilir. `null` ise `tahmin.motor_akis` kesikli çizgiyle ve "varsayılan en kötü akış" etiketiyle gösterilir. `motor_akis = 0` log eksende çizilemez; bu durumda grafiğin sol kenarında "0 (durgun)" diye not düşülür.
- Değer `null` olan noktalar çizilmez. Hepsi `null` ise "Fizik motoru bu koşulu bilmiyor" yazılır.
- Grafik başlığı motoru belirtmelidir: "Fizik motoru (`tahmin.motor_kaynagi`)". Bu grafik risk modeli değil, motor tahminidir.

### 2.4 Log paneli

Uygulama oturumu boyunca her hesaplama için bir satır tutulur, en yenisi üstte. Kalıcı log isteniyorsa yerel bir dosyaya da yazılabilir.

| Sütun | Kaynak |
|---|---|
| Zaman | Arayüzün kendi saati (çağrı başlangıcı) |
| Süre | `tahmin.sure_sn` (LLM çağrısında ~25 sn). İsterseniz grafik çağrılarının süresi ayrı ölçülüp eklenir. |
| Tür | "Hesapla" / "Yapay zeka yorumu" |
| Girdiler | `tahmin.girdi` (tek satır özet; tıklayınca tamamı) |
| Uyarılar | `tahmin.uyarilar` (sayısı + açılır liste) |
| Hata | Python tarafında istisna olduysa metni (bkz. §7) |

- **JSON indir:** Seçili satırın tam `tahmin()` çıktısı, `kosul` ile birlikte `.json` dosyası olarak kaydedilir. Grafik verileri de eklenebilir.
- **Önerilen dosya adı:** `vaka_<tarih-saat>_<malzeme>.json`.

### 2.5 Analiz adımları (`tahmin.adimlar`)

Log panelinde bir satıra tıklayınca, o hesaplamanın işlem kaydı **12 satırlık bir adım listesi** olarak açılır.

- **Kaynak:** `tahmin.adimlar`. Her zaman 12 öğe gelir, `no` 1'den 12'ye sıralıdır.
- **Öğe biçimi:** `{no, ad, sure_ms, karar, ayrinti}`.
  - `karar`: tek cümlelik özet. Satırda aynen gösterilir.
  - `ayrinti`: sözlük. Satır açılınca anahtar–değer olarak gösterilir.
  - `sure_ms`: adımın süresi (ms). Yan tarafta küçük, yatay bir süre çubuğu olarak çizilebilir.

| no | ad | `karar` örneği | Not |
|---|---|---|---|
| 1 | girdi ve varsayılanlar | "varsayılan kullanıldı: numune_tipi = thin_sheet, kalinlik = 0.2, yakit_turu = kati" | `ayrinti.girdi`, `ayrinti.akis_bilinmiyor` |
| 2 | malzeme tanıma | "listede: 'pmma'" / "LLM (önbellek): 'kevlar' -> 'nomex'" / "tanınmadı (...)" | liste, LLM önbelleği ya da EVREN |
| 3 | risk modeli | "p = 0.805 (g = 0.0001)" | Ay/Mars'ta yalnız gerçek g'nin hesabı |
| 4 | yönlendirici seçimi | "damla (motor_turu = yonlendirici)" | `ayrinti.neden` seçilme nedenini yazar; süre 5. adımdadır |
| 5 | fizik motoru | "yanma = 0.517, akış 0 cm/s" | `ayrinti.denenen_akislar`, `secilen_akis`, `motor_auc` |
| 6 | birleştirme ağırlıkları | "birleşik = 0.696 (model 0.622, motor 0.378)" | |
| 7 | Ay/Mars sınırlama | "uygulandı: en kötü durum '<uzay / gercek_g / dunya>'" ya da "uygulanmadı (g = …)" | `ayrinti`: uzay / gerçek g / Dünya |
| 8 | sönme sınırı ve güvenlik katsayısı | "sınır %17.25 O2, güvenlik katsayısı 0.821" | |
| 9 | güven skoru | "v2 75/100 (yüksek), v1 88/100" (PMMA ISS %21 durgun; örneklerin hepsi bu vakadan) | v2 bileşenleri ve cezaları |
| 10 | uyarılar | "3 uyarı" | `ayrinti.uyarilar` |
| 11 | LLM yorumu | "istenmedi (llm=False)" / "alındı" / "alınamadı" | |
| 12 | kayıt | "kapalı (TAHMIN_KAYIT ortam değişkeni yok)" ya da "yazıldı: <dosya>" | |

- **Atlanan adımlar:** malzeme tanınmadıysa 3–12. adımlar `karar = "atlandı (malzeme tanınmadı: sayı üretilmedi)"` ve `sure_ms = 0` ile gelir. Bunları gri gösterin.
- **Kayıt (12. adım):** `TAHMIN_KAYIT=/yol/analiz.jsonl` ortam değişkeni verilirse her `tahmin()` çıktısı o dosyaya bir JSON satırı olarak eklenir (adım listesi hariç). Verilmezse hiçbir dosya yazılmaz.

---

## SEKME 3 — "Sonuç ve Güvenlik"

Karar verecek kişinin bakacağı ekran. Öğeler önem sırasıyla yukarıdan aşağıya dizilir.

### 3.1 Büyük risk rozeti
- **Kaynak:** `tahmin.risk_seviyesi`.
- **Renkler:**

  | Seviye | Renk | `yanma_ihtimali` aralığı |
  |---|---|---|
  | DÜŞÜK | yeşil | < 0,2 |
  | ORTA | sarı | 0,2–0,5 |
  | YÜKSEK | turuncu | 0,5–0,8 |
  | ÇOK YÜKSEK | kırmızı | ≥ 0,8 |

- **Alt satır:** "Yanma ihtimali %`yanma_ihtimali×100` ± `belirsizlik×100`".
- **Renk körlüğü:** Rozette metin her zaman yazılı olmalı; renk tek başına bilgi taşımamalı.

### 3.2 Güvenlik katsayısı göstergesi
- **Kaynak:** `tahmin.guvenlik_katsayisi` (= sönme sınırı / ortam oksijeni).
- **Gösterge:** Yatay ölçek ya da kadran, 0–2 aralığı, 1'de belirgin işaret.
  - < 1 kırmızı: ortam oksijeni sönme sınırının üstünde, alev yanabilir.
  - ≥ 1 yeşil.
- **Değer `null` ise** gösterge gri olur ve "Hesaplanamadı — model %5–60 aralığında sönme sınırı bulamadı" yazılır. Uyarılarda da bu durumu anlatan bir satır vardır.
- **Cümle:** "Bu malzeme için oksijen en fazla **%X** olmalı."
  - X = `tahmin.sonme_siniri`.
  - Altına küçük not: "(model tahmini; güvenlik payı eklenmemiştir)".
  - `sonme_siniri` `null` ise cümle yerine "Güvenli oksijen üst sınırı hesaplanamadı." yazılır.
  - `sonme_siniri` 5 ise "%5 ya da daha az olmalı (taramanın alt ucu)" yazılır.

### 3.3 Güven skoru göstergesi
- **Kaynak:** `tahmin.guven.skor` (0–100).
- **Gösterge:** Yarım daire ya da çubuk.
- **Skor < 60:** Turuncu renk ve gösterge altında "⚠️ Düşük güven: bu koşula yakın deney az ya da fizik motoru orada zayıf. Sonucu dikkatle yorumlayın."
- **Eşik farkı:** Bu 60 eşiği yapay zeka yorumundaki ("60'ın altı düşük") eşikle aynıdır. `tahmin()` kendi uyarı listesine ancak skor < 50 olunca "Güven düşük" satırı ekler. Dolayısıyla 50–59 arasında gösterge uyarısı görünür ama uyarı listesinde satır olmaz; bu beklenen davranıştır.
- **Skor = 0:** bkz. §7.
- **Ayrıntı:** Tıklayınca Sekme 2'deki güven bileşenlerine gider.

### 3.3b Güven skoru v2 ve bileşen çubukları (`tahmin.guven_v2`)

v1 skoru (`tahmin.guven`) **aynen duruyor** ve kopyası `tahmin.guven_v1`'de. v2 ek bir alan; ikisi bir süre yan yana
gösterilebilir.

- **Formül:** `skor = 100 × (0,35·veri + 0,25·uyum + 0,25·motor + 0,15·kesinlik) × cezalar`.
  - **veri:** yakın deneylerin ağırlıklı sayısı / 15, en fazla 1.
    - Ağırlıklar: NASA PSI 1,0; makale (elle) 0,8; Gemma (otomatik) 0,5; topluluk onaylı 0,6; topluluk onaysız 0,2.
    - Etilende NASA ACME BRE testleri de NASA PSI olarak sayılır.
  - **uyum:** 1 − |yakın deneylerin (ağırlıklı) yanma oranı − birleşik ihtimal|.
    - Yakın deney yoksa `null` gelir; ağırlığı (0,25) veriye geçer.
  - **motor:** max(0, 2(dürüst AUC − 0,5)). Motor kalibre değilse ya da dürüst AUC yoksa 0.
  - **kesinlik:** 1 − 2 × (model belirsizliği ile motor belirsizliğinin büyüğü), 0–1 arasına kırpılır.
- **Cezalar** (çarpılır):
  - model–motor çelişkisi ×0,8;
  - kalibrasyon kapsamı dışı ×0,6: en yakın NASA / kalibrasyon noktası aynı malzeme ve g bandında `PENCERE` dışında;
  - malzeme LLM ile eşlendi ×0,8.
- **Bant:** `guven_v2.bant` → "yüksek" (≥ 75), "orta" (50–75), "düşük" (< 50).
- **Gösterim:**
  - Büyük sayı `guven_v2.skor` ve bant rozeti. Renkler: yüksek yeşil, orta sarı, düşük turuncu; metin her zaman yazılı olmalı.
  - Altında **dört yatay bileşen çubuğu**, `guven_v2.bilesenler.{veri, uyum, motor, kesinlik}` (0–1).
    - Her çubuğun yanında ağırlığı yazar: `guven_v2.agirliklar`.
    - `uyum` `null` ise o çubuk gri çizilir ve "yakın deney yok" yazılır.
  - Çubukların altında `guven_v2.ham_skor` → `guven_v2.skor` geçişi: "ham 66,3 × 0,8 (model–motor çelişkisi) × 0,8 (LLM eşlemesi) = 42" (kevlar örneği).
  - Her ceza `guven_v2.cezalar[]` öğesinden bir rozet olarak çizilir (`ad`, `carpan`; kapsam cezasında `mesafe`).
  - **Yakın deney kaynakları:** `guven_v2.yakin_deney_kaynaklari` küçük yığılmış çubuk ya da tablo olarak gösterilir:
    `{"NASA PSI": 214, "makale (elle)": 0, "Gemma (otomatik)": 65, "topluluk (onaylı)": 0, "topluluk (onaysız)": 0}`.
- **Örnek değerler** (integration_test.py, 2026-11-15):

  | vaka | v1 | v2 | bant |
  |---|---|---|---|
  | PMMA ISS %21 durgun | 88 | 75 | yüksek |
  | SIBAL ISS %21, 25 cm/s | 74 | 85 | yüksek |
  | metanol ISS %21 | 80 | 87 | yüksek |
  | etilen BRE %34, 57 kPa | 74 | 91 | yüksek |
  | PMMA Mars %21 | 34 | 50 | orta |
  | metan 1 g jet | 65 | 36 | düşük (jet kalibre değil, kapsam dışı) |
  | kevlar ISS (LLM → nomex) | 51 | 42 | düşük |
  | PMMA Ay %30, 70 kPa | 0 | 16 | düşük (yakın deney yok) |

### 3.4 Uyarılar listesi
- **Kaynak:** `tahmin.uyarilar`. Metinler **aynen** gösterilir; kısaltılmaz, yeniden yazılmaz.
- **Biçim:** Her uyarı ayrı satırda, ⚠️ simgesiyle.
- **Boş liste:** "Uyarı yok" yazılır.
- **Kullanılan varsayılanlar:** Listenin hemen altında ayrı bir kutuda gösterilir: "Kullanılan varsayılanlar: numune tipi = thin_sheet, kalınlık = 0,2 mm …" (kaynak: `tahmin.kullanilan_varsayilanlar`). `girdi.akis` `null` ise bu kutuya "hava akışı = bilinmiyor (en kötü durum)" da eklenir.

### 3.5 Yapay zeka yorumu kutusu
- **Kaynak:** `tahmin.llm_yorum`; sadece `llm=True` çağrısından sonra gelir.
- **Durumlar:**
  - Henüz istenmedi: "Yapay zeka yorumu için Sekme 1'deki düğmeyi kullanın" ya da kutunun kendi düğmesi.
  - Bekleniyor: yüklenme göstergesi.
  - Geldi: metin gösterilir.
- **Biçimlendirme:**
  - İlk satır (`KARAR:` ile başlar) **kalın** yazılır. Bu satır kodla üretilir, LLM tarafından değil.
  - Sonraki satırlar düz metindir: "Gerekçe:" maddeleri, "Öneri:", "Güvenilirlik:".
  - Metin "⚠️ Doğrulanamayan sayılar:" içeriyorsa kutunun arka planı **sarı** olur ve bu satır vurgulanır. LLM giriş verisinde olmayan bir sayı yazmış demektir.
- **Kalıcı not:** Kutunun altında "Yapay zeka yorumu yardımcıdır; karar için yukarıdaki sayılara bakın." yazar.

### 3.5b Birleşik yanma ihtimali
- **Kaynak:** `tahmin.yanma_birlesik` (0–1). Model ile fizik motorunun ağırlıklı ortalamasıdır.
- **Ağırlıklar:** `tahmin.agirliklar` (`model`, `motor`; toplamları 1).
  - Her birinin gücü, dürüst testteki AUC'sinin rastgeleden üstünlüğüdür: güç = max(0, 2·(AUC − 0,5)).
  - Model için NASA AUC'si (0,878) kullanılır.
  - Motor için `motor.motor_auc` kullanılır; OpenFOAM tablosu kullanıldıysa güç mesafeyle azaltılır.
  - Motorun doğrulaması yoksa (örneğin gaz) motor ağırlığı 0'dır.
- **Gösterim:** Risk rozetinin altında küçük bir satır: "Birleşik: %96 (model %56 · motor %44 — damla motoru)". Ağırlıklar ince bir yığılmış çubukla da gösterilebilir.
- **Rozet:** Risk rozeti ve güvenlik katsayısı **modelden** gelmeye devam eder. Birleşik ihtimal ek bilgidir; rozetin rengini değiştirmez.
- **İkisi de gösterilmeli:** Model (`yanma_ihtimali`) ve motor (`motor.yanma`) değerleri ayrı ayrı da gösterilmeye devam eder (§3.6).

### 3.6 Model ile motor karşılaştırma çubuğu
İki yatay çubuk aynı 0–1 ölçeğinde çizilir ve 0,5'te eşik çizgisi bulunur:
- "Risk modeli": `tahmin.yanma_ihtimali`
- "Fizik motoru (`tahmin.motor_kaynagi`)": `tahmin.motor.yanma`
- (isteğe bağlı) üçüncü çubuk "Birleşik": `tahmin.yanma_birlesik`, etiketinde `tahmin.agirliklar`

Ek bilgiler:
- **Sönme sınırları:** Çubukların altında model `tahmin.sonme_siniri` ile motor `tahmin.motor.min_oksijen` yan yana gösterilir.
- **Çelişki:** Biri 0,5'in üstünde, diğeri altındaysa çubuklar arasında "Model ile fizik motoru çelişiyor" etiketi gösterilir. `tahmin.uyarilar`'da "Model ve motor çelişiyor: model '…', motor '…' diyor." cümlesi bulunur.
- **Motor yoksa:** `tahmin.motor` `null` ise motor çubuğu gri olur ve "motor bu koşulu bilmiyor" yazılır.

---

## SEKME 4 — "Topluluk verisi"

Kullanıcıların kendi deneylerini ya da makaleden okudukları sonuçları eklediği sekme. Arka uç `community_data.py`'dir.
Veri `topluluk/topluluk.sqlite` dosyasında, internetsiz tutulur.

> **Sekmenin üstünde sabit not:** "Bu veri risk modeline ve fizik motorlarının kalibrasyonuna **girmez**. Yalnız
> güven skorunda (v2) yakın kayıt olarak sayılır: onaylı kayıt 0,6, onaysız kayıt 0,2 ağırlıkla."

### 4a.1 Form (tek kayıt) → `topluluk_veri.ekle(kayit)`

| Alan | Anahtar | Zorunlu | Not |
|---|---|---|---|
| Malzeme | `malzeme` | evet | serbest metin; listeden seçim önerilir |
| Yakıt türü | `yakit_turu` | – | kati / sivi / gaz |
| Numune tipi | `numune_tipi` | – | thin_sheet, fabric, droplet, gas_jet … |
| Kalınlık / çap (mm) | `kalinlik_mm` | – | damlada ilk çap |
| Yerçekimi (g₀) | `g` | evet | Dünya = 1, ISS ≈ 0,0001 |
| Oksijen (%) | `oksijen_yuzde` | evet | mol yüzdesi |
| Basınç (kPa) | `basinc_kpa` | evet | |
| Akış (cm/s) | `akis_cm_s` | – | |
| Seyreltici | `seyreltici` | – | n2 / he / co2 / ar |
| Sonuç | `sonuc` | evet | yandi / sondu |
| Yayılma hızı (mm/s) | `yayilma_hizi_mm_s` | – | |
| Yanma hızı K (mm²/s) | `K_mm2_s` | – | damla |
| Sönme çapı (mm) | `sonme_capi_mm` | – | damla |
| Kaynak türü | `kaynak_turu` | evet | doi / rapor / kendi_deney / makale_pdf |
| Kaynak | `kaynak` | evet | DOI, rapor no ya da deney defteri |
| Yöntem | `yontem` | – | kısa açıklama |
| Ekleyen | `ekleyen` | evet | |
| Tarih | `tarih` | – | boşsa bugün |

- **Dönen değer:** `{id, durum, etiketler, kontrol_notlari, mukerrer}`.
- **Kabul edilmezse** `topluluk_veri.ToplulukHatasi` fırlatılır. Mesajı (ör. "'oksijen_yuzde' = 150 fiziksel aralık
  dışında") formun altında kırmızıyla aynen gösterin.
- **Etiketler (reddetmez, uyarır):**
  - `celiski`: aynı koşuldaki NASA verisinin en az 2/3'ü ters sonuçta.
  - `birim_supheli`: ör. O₂ ≤ 1 (oran girilmiş olabilir), g ≈ 9,8 (m/s²), basınç < 5 kPa (atm/bar).
  - `llm_cikardi`: PDF'ten LLM ile çıkarıldı.
  - `ice_aktarildi`: paketten geldi.
  - `kontrol_notlari` her birinin gerekçesini yazar.
- **Mükerrer** (`mukerrer = true`): "Bu kayıt zaten var (id …)" yazın; yeni kayıt oluşmaz.

### 4a.2 CSV yükleme → `topluluk_veri.csv_yukle(dosya, ekleyen=None)`
- **Şablon:** `community_template.csv`, sütunlar yukarıdaki anahtarlar. "Şablonu indir" düğmesi bu dosyayı verir.
  `ekleyen = ORNEK` olan örnek satır yüklenmez.
- **Dönen değer:** `{eklenen, mukerrer, reddedilen: [{satir, sebep}], sonuclar}`.
  - Özeti gösterin: "12 eklendi, 1 mükerrer, 2 reddedildi".
  - Reddedilenleri satır numarası ve sebebiyle tablo halinde listeleyin.

### 4a.3 Liste → `topluluk_veri.listele(filtre)`
- **Filtreler:** `{"durum", "malzeme", "ekleyen", "etiket", "kaynak_turu"}`.
- **Sütunlar:** id, malzeme, g, O₂, basınç, sonuç, kaynak, ekleyen, tarih, durum, etiketler.
- **Durum renkleri** (metin her zaman yazılı):
  - `onaysiz` gri;
  - `onayli` yeşil;
  - `reddedildi` kırmızı, üstü çizili.
- **Etiket rozetleri:** `celiski` turuncu, `birim_supheli` sarı, `llm_cikardi` mor.
- Satıra tıklayınca `kontrol_notlari` ve moderatör bilgisi (`moderator`, `karar_tarihi`, `gerekce`) açılır.

### 4a.4 Moderatör
- **Düğmeler:** "Onayla" → `topluluk_veri.onayla(id, moderator)`, "Reddet" → `topluluk_veri.reddet(id, moderator, gerekce)`.
  Moderatör adı zorunlu.
- Düğmeler yalnız moderatör kipinde görünür. Yetkilendirme arayüzün işi; arka uçta kullanıcı yönetimi yok.

### 4a.5 Paylaşım paketi
- **Dışa aktar:** `topluluk_veri.disa_aktar("paket.json", filtre=None)`. Kayıtlar kaynak, durum, etiket ve notlarıyla
  JSON paketine yazılır.
- **İçe aktar:** `topluluk_veri.ice_aktar("paket.json")`.
  - Gelen kayıtlar **her zaman `onaysiz`** girer, etiketi `ice_aktarildi` olur.
  - Paketteki eski durum kontrol notuna yazılır.
  - Kayıtlar yine tüm kontrollerden geçer.
  - Özet: `{eklenen, mukerrer, reddedilen}`.

### 4a.6 PDF'ten aday kayıt (isteğe bağlı) → `topluluk_veri.pdf_ekle(dosya, ekleyen)`
- **Gereksinimler:** internet, EVREN anahtarı (`evren_anahtar.txt`) ve PyMuPDF (`pip install pymupdf`).
  - Eksik olanı bildiren hata mesajı aynen gösterilir: `InternetYokHatasi` ya da `ToplulukHatasi`.
  - Örnek: "PDF'ten veri çıkarmak için internet ve EVREN gerekir; ulaşılamadı …".
- **Çıkan kayıtlar:** hepsi `onaysiz`, etiketi `llm_cikardi`.
  - Bu kayıtlar kesinlikle moderatör onayından geçmeli.
  - Bu yol ağ ve PDF bağımlı olduğu için entegrasyon testinde yalnız hata mesajı sınanıyor.

---

## 4. Yardımcı fonksiyonlar (`predict.py`)

Ortak özellikler:
- Hepsi `tahmin()` ile aynı `kosul` anahtarlarını alır: `malzeme`, `oksijen`, `basinc`, `g`, `akis`, `kalinlik`, `numune_tipi`, `yakit_turu`, `akis_yonu`, `seyreltici`. Fazladan anahtarlar yok sayılır.
- Malzeme varsayılanları `tahmin()` ile aynı şekilde doldurulur.
- Çıktılar JSON'a yazılabilir (`dict` ya da `list`, `NaN` yok).

**Süre ölçümleri:**
- Bu makinede ölçüldü (model yüklü, 3 tekrar; dört farklı vaka: ISS, Mars, keşif atmosferi, n-heptan damla).
- "Soğuk" sütunu: yeni süreçte `import tahmin`'den sonraki ilk çağrı. Model yüklemesi dahil; import'un kendisi ayrıca ~0,4 sn.

| Fonksiyon | Sıcak süre | Soğuk ilk çağrı |
|---|---|---|
| `oksijen_egrisi` | 0,11 sn (Ay/Mars: 0,32 sn, üç g hesaplanır) | 0,37 sn |
| `yanabilirlik_haritasi` (40×40) | 0,15–0,18 sn | 0,42 sn |
| `akis_egrisi` | 0,01 sn | 0,01 sn |
| `yakin_deneyler` | 0,004–0,011 sn | 0,02 sn* |

\* Güven tablosu `engine_comparison.csv` güncelse bu süre geçerli. Dosya yoksa ya da model, motor veya parametreler değiştiyse tablo bir kez yeniden üretilir: hafif motorla ~2 sn, tablo motoruyla daha uzun. Bu durum `tahmin()` için de aynıdır. Geçerlilik dosya içeriğinin özetiyle kontrol edilir; kopyalamak ya da zip'ten açmak tabloyu geçersiz kılmaz.

### 4.1 `oksijen_egrisi(**kosul)`

```python
from tahmin import oksijen_egrisi
e = oksijen_egrisi(malzeme="pmma", oksijen=21, basinc=101.3, g=1e-4)
```

Çıktı (221 nokta: %5–60, 0,25 adım; burada birkaç nokta gösteriliyor):

```json
{
  "oksijen": [5.0, ..., 15.0, ..., 16.0, ..., 16.5, ..., 21.0, ..., 60.0],
  "ihtimal": [0.0236, ..., 0.2972, ..., 0.371, ..., 0.5161, ..., 0.9719, ..., 0.9958],
  "alt":     [0.0, ..., 0.0893, ..., 0.1608, ..., 0.3296, ..., 0.9457, ..., 0.9909],
  "ust":     [0.0483, ..., 0.5051, ..., 0.5811, ..., 0.7027, ..., 0.9981, ..., 1.0],
  "sonme_siniri": 16.5
}
```

- `alt` ve `ust` ihtimal ± belirsizlik değerleridir, 0–1'e kırpılmıştır.
- `sonme_siniri` her zaman `tahmin()`'in döndürdüğü `sonme_siniri` ile aynıdır (dört vakada kontrol edildi).
- `oksijen` girdisi bu fonksiyonda kullanılmaz ama verilebilir.

### 4.2 `yanabilirlik_haritasi(**kosul, n_g=40, n_o2=40)`

```python
from tahmin import yanabilirlik_haritasi
h = yanabilirlik_haritasi(malzeme="pmma", oksijen=21, basinc=101.3, g=1e-4, n_g=4, n_o2=5)
```

Çıktı (küçük ızgara örneği; dashboard 40×40 kullanmalı):

```json
{
  "g": [1e-05, 0.0004642, 0.02154, 1.0],
  "oksijen": [5.0, 18.75, 32.5, 46.25, 60.0],
  "ihtimal": [[0.0236, 0.9222, 0.994, 0.9952, 0.9958],
              [0.0351, 0.9851, 0.9989, 0.9991, 0.9992],
              [0.035, 0.9851, 0.9989, 0.9991, 0.9992],
              [0.0293, 0.989, 0.9992, 0.9994, 0.9995]]
}
```

- `ihtimal[i][j]`, `g[i]` ve `oksijen[j]` noktasının değeridir; satırlar g'ye göre dizilir.
- Çoğu çizim kütüphanesi satırları y eksenine koyar. Oksijeni y ekseninde göstermek için matrisin transpozu alınmalıdır.

### 4.3 `akis_egrisi(**kosul)`

```python
from tahmin import akis_egrisi
a = akis_egrisi(malzeme="pmma", oksijen=21, basinc=101.3, g=1e-4)
```

Çıktı (40 nokta, 0,1–100 cm/s, log aralıklı; burada her 6. nokta gösteriliyor):

```json
{
  "akis":        [0.1,    ..., 0.2894, ..., 0.8377, ..., 2.424,  ..., 7.017,  ..., 20.31,  ..., 58.78,  ..., 100.0],
  "motor_yanma": [0.5369, ..., 0.6324, ..., 0.8243, ..., 0.9431, ..., 0.9645, ..., 0.7615, ..., 0.1809, ..., ...]
}
```

- Yüksek akışta düşüş, üfleme ile sönmedir. Düşük akışta yanma ihtimali düşer, ama %21 O2'de 0,5'in altına inmez.
- Kullanıcının verdiği `akis` bu fonksiyonda kullanılmaz.

### 4.4 `yakin_deneyler(**kosul, en_fazla=10)`

**"Yakın deney" tanımı** (`motor_kontrol.yakin_maske`, güven skorundaki tanımın aynısı):
- aynı ana malzeme (`risk_modeli.malzeme_ana`: örneğin "black PMMA" → pmma),
- aynı g bandı (uzay < 0,01; kısmi 0,01–0,9; Dünya ≥ 0,9),
- |ΔO2| ≤ 3 puan,
- |Δlog₁₀ basınç| ≤ 0,3. Basıncı bilinmeyen deneyler basınç yüzünden elenmez.

Sıralama yakınlığa göredir: |ΔO2|/3 + |Δlog p|/0,3. Eşitlikte NASA ve elle çıkarılmış satırlar önce gelir.

`en_fazla` büyük verilirse toplam sayı `tahmin.guven.yakin_deney` ile aynı çıkar (üç vakada kontrol edildi: 279, 19, 3).

```python
from tahmin import yakin_deneyler
d = yakin_deneyler(malzeme="pmma", oksijen=17, basinc=101.3, g=1e-4, en_fazla=10)
```

Çıktı (ilk iki satır):

```json
[
  {"kaynak": "NASA PSI", "makale_id": "PSI-25_T3", "link": null,
   "aciklama": "NASA PSI-25 (BASS-II) – Experimental table",
   "g": 0.0001, "oksijen": 17.0, "basinc": 101.3, "akis": 10.0, "malzeme": "pmma", "yanar": 1},
  {"kaynak": "NASA PSI", "makale_id": "PSI-25_O15a", "link": null,
   "aciklama": "NASA PSI-25 (BASS-II) – Experimental table",
   "g": 0.0001, "oksijen": 16.9, "basinc": 101.3, "akis": 5.0, "malzeme": "pmma", "yanar": 1}
]
```

Makale satırı örneği (`g=1`, %21):

```json
{"kaynak": "makale (otomatik, Gemma)", "makale_id": "20010074095",
 "link": "https://ntrs.nasa.gov/citations/20010074095", "aciklama": null,
 "g": 1.0, "oksijen": 21.0, "basinc": 101.325, "akis": null, "malzeme": "pmma", "yanar": 1}
```

- `link`: Varsa DOI ya da NTRS adresidir. NASA PSI satırlarında URL yoktur; `link` `null` olur ve kaynak tablosunun adı `aciklama`'da yer alır.
- `malzeme`: Deneydeki özgün addır (örneğin "black polymethylmethacrylate").
- Spesifikasyondaki alanlara `aciklama` ve `akis` eklendi.

---

## 5. Gerekli dosyalar

Hepsi aynı klasörde olmalı ve Python o klasörden çalıştırılmalı.

| Dosya | Görevi | Gerekli mi |
|---|---|---|
| `predict.py` | Giriş noktası + grafik yardımcıları | evet |
| `risk_model.py` | Model sınıfları ve yardımcıları; model dosyasını açmak için gerekli | evet |
| `models/risk.joblib` | Eğitilmiş risk modeli | evet |
| `engine.py` | Fizik motoru seçici | evet |
| `light_engine.py` | Yarı-ampirik fizik motoru | evet |
| `light_engine_parameters.json` | Motorun kalibre parametreleri | evet |
| `engine_check.py` | Güven skoru ve yakın deney tanımı | evet |
| `engine_comparison.csv` | Deney + motor tablosu (önbellek): güven skoru ve yakın deneyler buradan | evet (güncel olmalı) |
| `light_engine_validation_points.csv` | Güvenin motor bileşeni için çapraz doğrulama tahminleri | evet |
| `psi_etiketli*.csv` (5 dosya), `labeled_gemma3.csv` | Önbelleği yeniden üretmek için deney verisi (`labeled_gemma3.csv` varken `data_clean.csv` gerekmez) | önbellek yeniden üretilecekse |
| `data_clean.csv` | Modeli yeniden eğitmek için (`python3 risk_model.py`); `tahmin()` için gerekmez | sadece yeniden eğitim |
| `llm_analysis.py` | Yapay zeka yorumu ve listede olmayan malzemenin sınıflandırılması | evet (tahmin() malzeme listesini buradan alır) |
| `material_cache.json` | Yapay zekanın sınıflandırdığı malzemeler (önbellek; çevrimdışı çalışma için) | önerilir (yoksa ilk sorguda oluşur) |
| `droplet_engine.py`, `droplet_engine_parameters.json`, `droplet_features.json` | Sıvı yakıt damla motoru (FLEX ile kalibre) ve gaz özellikleri | evet |
| `droplet_validation.csv` | Damla motorunun kalibrasyon dışı tahminleri (güven skorunda) | evet |
| `droplet_flex_flame_target.csv` | FLEX alev çapı ölçümü (sayısallaştırılmış; damla motorunun kalibrasyonunda) | yeniden kalibrasyon için |
| `droplet_cold_flame_label.csv`, `droplet_flex_report_matching.csv` | FLEX soğuk alev gözlemleri ve rapor → test eşlemesi | yeniden doğrulama için |
| `gas_engine.py`, `gas_engine_parameters.json`, `gas_features.json`, `gas_radiation.py` | Gaz yakıt motoru (BRE ile kalibre; jet kalibre değil) | evet (gaz yakıtlar) |
| `gas_validation_summary.json` | Gaz motorunun geometri başına dürüst AUC'si (`engine_validation_generate.py` okur) | yeniden üretim için |
| `engine_validation.json` | Her motorun dürüst test AUC'si (birleşik ihtimalin ağırlıkları) | evet |
| `evren_anahtar.txt` | EVREN API anahtarı. **Pakette yok:** `evren_key_EXAMPLE.txt`'yi kopyalayıp kendi anahtarınızı yazın | sadece `llm=True`, listede olmayan malzeme ve `pdf_ekle` |
| `community_data.py`, `community_template.csv` | Topluluk verisi katmanı (Sekme 4) ve CSV şablonu; depo ilk kullanımda `topluluk/` altında oluşur | Sekme 4 için |
| `integration_test.py` | Dashboard ekibinin tek test betiği: 10 vaka + internetsiz mod + topluluk akışı, GEÇTİ/KALDI tablosu | önerilir |
| `gas_data/bre_dehghani2021_table2.csv` | NASA ACME BRE testleri (güven v2'de etilen yakın deneyleri) | etilen için önerilir |
| `data_extract3.py`, `data_extract.py`, `clean.py` | PDF'ten veri çıkarma boru hattı (`pdf_ekle`) | sadece `pdf_ekle` |
| `MALZEME_VARSAYILAN` | `predict.py` içinde, ayrı dosya değil | – |

Ek not: Klasörde `openfoam_sonuclar.csv` bulunursa motor kendiliğinden `tablo` moduna geçer. Hafif motorda kalmak için ya bu dosyayı koymayın ya da `MOTOR_TURU=hafif` ortam değişkenini verin.

## 6. Kurulum

1. Python 3.10 ya da üstü kurulu olmalı.
2. Paketleri kurun:
   ```
   python3 -m pip install numpy pandas scikit-learn scipy joblib matplotlib
   ```
3. Kurulumu deneyin. Proje klasöründe şu komut JSON yazmalı:
   ```
   python3 predict.py --malzeme pmma --oksijen 21 --basinc 101.3 --g 1e-4
   ```

Paket notları:
- Geliştirme ortamındaki sürümler: numpy 1.26, pandas 2.1, scikit-learn 1.4, scipy 1.11, joblib 1.3, matplotlib 3.6.
- **scikit-learn sürümü sabitlenmeli.** `risk.joblib` farklı bir sürümle açılırsa uyarı verebilir ya da hiç açılmayabilir.
- `scipy` fizik motoru, `matplotlib` sadece önbellek yeniden üretilirken gerekir. Dashboard'un kendi grafikleri için matplotlib şart değil.
- Yapay zeka yorumu için internet erişimi (`evren-llmapi.ssyz.org.tr`) ve `evren_anahtar.txt` gerekir. Diğer her şey çevrimdışı çalışır.

> ⚠️ **`evren_anahtar.txt` gizlidir.**
> - Git'e eklenmemeli (`.gitignore`'a yazın), kurulum paketine konmamalı.
> - Sohbet ya da e-postayla paylaşılmamalı; ekran görüntüsüne ve loglara girmemeli.
> - Her kullanıcı kendi anahtarını bu dosyaya koyar.
> - Dashboard bu dosyayı okumaz, göstermez, düzenleme ekranı sunmaz. Kod anahtarı hiçbir çıktıya yazmaz.
> - Dashboard'un JSON indirme ve log özellikleri anahtarı içermez, çünkü `tahmin()` çıktısında anahtar yoktur.

---

## 7. Hata durumlarında ne gösterilecek

| Durum | Nasıl anlaşılır | Ne gösterilir |
|---|---|---|
| **Yapay zeka yorumu alınamadı** (anahtar yok, ağ yok, HTTP hatası, zaman aşımı) | `tahmin.llm_yorum` "LLM yorumu alınamadı" ile başlar. Aynı metin `uyarilar`'a da eklenir. | Yorum kutusu gri olur ve metin aynen gösterilir; örnek: "LLM yorumu alınamadı (zaman aşımı, 120 sn)". Yanında "Tekrar dene" düğmesi bulunur. Diğer sonuçlar geçerlidir ve ekranda kalır. `tahmin()` bu durumda istisna fırlatmaz. |
| **Malzeme listede yok, yapay zeka eşledi** | `llm_siniflandirma.durum == "kabul"`; uyarılarda "'kevlar' listede yok, LLM bunu 'nomex' malzemesine benzetti (…) — kontrol edin." | Sonuç gösterilir. Öneri kutusu "öneri — onayla/değiştir" olarak gösterilir (§1.5). |
| **Malzeme tanınmadı** (anlamsız ad, yapay zeka önerisi denetimden geçmedi ya da internet yok) | `llm_siniflandirma.durum` `reddedildi` / `baglanti_yok`; `yanma_ihtimali`, `risk_seviyesi` vb. `null`; uyarı "'…' malzemesi tanınmadı, listeden seçin (…)". | Sonuç kartları boş kalır, uyarı gösterilir ve malzeme listesi açılır. Hiçbir sayı uydurulmaz. |
| **Güven 0** | `guven.skor == 0`: yakın deney yok ve motor bileşeni ölçülemiyor (`guven.motor_yontemi` sebebi yazar). Örnek: Mars %30 O2, 70 kPa. | Güven göstergesi kırmızı; "Güven 0/100: bu koşulda hiç benzer deney yok, sonuç tamamen modelin dış değerlendirmesi (ekstrapolasyon)" yazılır. Risk rozeti gösterilir ama yarı saydam ya da "doğrulanmamış" etiketiyle. Yakın deney tablosu boş mesajı verir. |
| Sönme sınırı bulunamadı | `sonme_siniri` ve `guvenlik_katsayisi` `null`; uyarılarda açıklama var. | Güvenlik göstergesi gri ve "hesaplanamadı" yazılır (§3.2); oksijen eğrisinde sınır çizgisi çizilmez. |
| Fizik motoru bu koşulu bilmiyor | `motor` `null`; uyarılarda "Fizik motoru bu koşulu bilmiyor." | Motor alanları "yok" olarak gösterilir, karşılaştırma çubuğu gri olur, akış grafiği "motor bu koşulu bilmiyor" mesajını verir. |
| Model ile motor çelişiyor | Uyarılarda "Model ve motor çelişiyor: …" | Karşılaştırma çubuğunda etiket (§3.6) ve güven göstergesi yanında dikkat simgesi. |
| Yüksek belirsizlik | `belirsizlik > 0.3`; uyarılarda "Model belirsizliği yüksek" | Rozet altındaki "±" değeri turuncu yazılır. |
| Python tarafında istisna (model dosyası eksik, paket sürümü uyumsuz, geçersiz girdi) | `tahmin()` ya da yardımcı fonksiyon istisna fırlatır. | Uygulama çökmemeli. Hata penceresi "Hesaplama yapılamadı: <istisna türü ve mesajı>" der; log paneline hata satırı düşer; önceki sonuç ekranda "eski sonuç" etiketiyle kalır. |
| Geçersiz girdi (arayüz tarafında yakalanmalı) | g ≤ 0, basınç ≤ 0, oksijen 0–100 dışında, boş zorunlu alan | "Hesapla" pasif; ilgili kutu kırmızı çerçeve ve kısa açıklama gösterir. |
| İlk açılışta yavaşlık | Önbellek eksik ya da eski (bkz. §4 dipnotu) | "Veri hazırlanıyor…" yüklenme ekranı (hafif motorla birkaç saniye). |
