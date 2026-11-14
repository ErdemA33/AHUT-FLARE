# LLM yorum testi: gemma-4-31b vs glm-5.3

Tarih: 2026-11-08. `llm_analiz.yorumla()` ile 6 senaryo × 2 model. KARAR satırı kodla üretilir ve başa eklenir; sayı kontrolü otomatik, anlam hataları elle okunarak işaretlendi. Malzeme varsayılanları `tahmin.py`'den, akış bilinmiyor (None). glm-5.3 ilk turda 3 çağrıda HTTP 503 (model_capacity_exhausted) verdi; başarısızlar 30 sn arayla en fazla 3 kez daha denendi.

## Özet

| Senaryo | Model | Süre (s) | Doğrulanamayan sayı (otomatik) | Karar ile çelişki | Kelime | Biçim | Elle bulunan sorun |
|---|---|---|---|---|---|---|---|
| güvenli | gemma-4-31b | 33.0 | 0 | yok | 77 | ✓ | Hata yok. |
| güvenli | glm-5.3 | 114.6 | 0 | yok | 139 | ✓ | **Olgu hatası:** '29 yakın deneyden 24'ü sönmeyle sonuçlanmış' diyor; JSON'da 24 *yanan*, 5 sönen. **Yanlış iddia:** ISS (g=0,0001) için 'kısmi yerçekimi, en kötü senaryo yaklaşımı uygulandı' diyor; sınırlama bu koşulda yok. |
| tehlikeli | gemma-4-31b | 15.3 | 0 | yok | 75 | ✓ | Hata yok. |
| tehlikeli | glm-5.3 | 6.4 (3. deneme) | - | - | - | - | 4 denemede de HTTP 503 (model dolu); yorum alınamadı. |
| sınırda | gemma-4-31b | 18.0 | 0 | yok | 69 | ✓ | Hata yok. Katsayının 1'e çok yakın olduğunu doğru vurguluyor. |
| sınırda | glm-5.3 | 55.1 (2. deneme) | 0.25 | yok | 177 | ✓ | Sayılar doğru (1 yanan / 8 sönen dahil). 0.25 marjını kendisi hesaplamış (doğru ama JSON'da yok, işaretlendi). **177 kelime, 150 sınırını aşıyor.** |
| düşük güven | gemma-4-31b | 9.5 | 0 | yok | 78 | ✓ | Hata yok. |
| düşük güven | glm-5.3 | 88.3 | 1.5 | yok | 136 | ✓ | **Yanlış akıl yürütme:** motor min_oksijen 22.035 > ortam 15 iken yanma 0'ı 'tutarsızlık' sayıyor; aslında tutarlı (ortam sınırın altında -> söner). 1.5 marjını kendisi hesaplamış (işaretlendi). |
| kısmi g | gemma-4-31b | 45.8 | 0 | yok | 77 | ✓ | Hata yok. |
| kısmi g | glm-5.3 | 17.1 | 0 | yok | 150 | ✓ | Hata yok; motor yayılma hızı/sıcaklığını da doğru kullanıyor. Tam 150 kelime. |
| model-motor çelişkili | gemma-4-31b | 25.0 | 0 | yok | 81 | ✓ | Sayılar doğru ama **model-motor çelişkisi uyarısından hiç bahsetmiyor** (eksik). |
| model-motor çelişkili | glm-5.3 | 22.4 | 0 | kısmen | 134 | ✓ | Çelişkiyi doğru anlatıyor; ama 'oksijen sınırın üzerinde olsa da ... küçük bir oksijen artışı alevlenmeye yol açabilir' diyor; ortam zaten sınırın üstünde, alev şimdiden yanar (KARAR: tehlikeli). Mantık karışık. |

## Model karşılaştırması

| | gemma-4-31b | glm-5.3 |
|---|---|---|
| Başarılı yanıt | 6/6 (ilk denemede) | 5/6 (ilk turda 3/6; 503 nedeniyle tekrar gerekti) |
| Ortalama süre (başarılı) | 24,4 s (9,5–45,8) | 59,5 s (17,1–114,6) |
| Doğrulanamayan sayı (otomatik) | 0 | 2 (kendi hesapladığı marjlar: 1.5, 0.25) |
| Elle bulunan olgu / mantık hatası | 0 (1 eksik: çelişki uyarısı anılmadı) | 3 (ters sayı atfı, yanlış 'kısmi g' iddiası, yanlış 'tutarsızlık') + 1 karışık mantık |
| KARAR ile çelişki | yok | 1 kısmen |
| 150 kelime sınırı | hepsi uyuyor (69–81) | 1 aşım (177), diğerleri 134–150 |
| İçerik zenginliği | kısa, güvenli, bazen yüzeysel | ayrıntılı (güven bileşenleri, motor, uyarılar) ama hata payı yüksek |

**Öneri: gemma-4-31b** (varsayılan olarak kalsın).

## Bütün yorumlar

### güvenli — gemma-4-31b (33.0 s)

Koşul: pmma, O2 %12, 101 kPa, g=0.0001

```
KARAR: Risk DÜŞÜK | güvenlik katsayısı 1.438 > 1 (güvenli) | güven 88/100 (yeterli)

Gerekçe:
- Ortam oksijeni 12 iken sönme sınırı 17.25 olduğundan, güvenlik katsayısı 1.438 ile 1'in üzerindedir ve sistem güvenlidir.
- Yanma ihtimali 0.058 (%5.8) olup, %50 eşik değerinin çok altında olduğu için alev oluşumu beklenmemektedir.

Öneri: Mevcut oksijen seviyesinin sönme sınırının altında tutulması durumunda PMMA malzeme için ek bir önleme gerek yoktur; mevcut atmosferik koşullar yangın riskini minimize etmektedir.

Güvenilirlik: Analiz sonucu 88/100 skoruna sahiptir; bu değer 60 olan alt sınırın üzerinde olduğu için yüksek güvenilirliğe sahiptir.
```

### güvenli — glm-5.3 (114.6 s)

Koşul: pmma, O2 %12, 101 kPa, g=0.0001

```
KARAR: Risk DÜŞÜK | güvenlik katsayısı 1.438 > 1 (güvenli) | güven 88/100 (yeterli)

Gerekçe:
- Ortam oksijeni %12, sönme sınırı %17,25; güvenlik katsayısı 1,438 > 1 olduğundan koşullar sönme sınırının güvenli tarafında.
- Yanma ihtimali %5,8 olup %50 eşiğinin çok altında; alev yanar kabul edilmez.
- Güven skoru 88/100 (veri bileşeni 1,0, motor bileşeni 0,75, AUC 0,88) ile 60 eşiğinin üzerinde; 29 yakın deneyden 24'ü sönmeyle sonuçlanmış.

Öneri: PMMA ince levha, %12 oksijen ve 101 kPa koşullarında düşük risk taşımakta; ancak motor bileşeni 0,75 ve yayılma hızı 0,0 varsayımı ile belirsizlik %7,3 olduğu için standart yangın önleme prosedürleri (yerçekimsiz ortamda duman/parçacık izolasyonu, oksijen izleme) sürdürülmelidir.

Güvenilirlik: Sonuç yüksek güvenilirliktedir; veri bileşeni tam puan, 29 yakın deney ve 0,88 AUC güçlü kanıt oluşturuyor. Ancak motor bileşeni 0,75 ve kısmi yerçekimi (g = 0,0001) nedeniyle en kötü senaryo yaklaşımı uygulandığından, gerçek mikro yerçekimi davranışında sapma olabilir; bu durum güvenlik katsayısındaki 1,438 marjla telafi edilmektedir.
```

### tehlikeli — gemma-4-31b (15.3 s)

Koşul: n-heptane, O2 %19, 101 kPa, g=0.0001

```
KARAR: Risk ÇOK YÜKSEK | güvenlik katsayısı 0.645 < 1 (tehlikeli) | güven 84/100 (yeterli)

Gerekçe:
- Güvenlik katsayısı 0.645 ile 1'in altında olduğu için ortam tehlikeli sınıftadır.
- Yanma ihtimali 0.994 (%99.4) ile %50 eşiğinin çok üzerindedir ve alevlenme kesin gözükmektedir.
- Ortam oksijeni (19), sönme sınırının (12.25) üzerinde olduğundan yanmayı desteklemektedir.

Öneri: Oksijen seviyesini 12.25 değerinin altına düşürecek inertleme önlemleri alınmalı veya n-heptane yakıt kaynağı ortamdan tamamen izole edilmelidir.

Güvenilirlik: Analiz sonucu 84/100 skoruna sahiptir ve bu değer 60 olan alt sınırın üzerinde olduğu için yeterli güven düzeyindedir.
```

### tehlikeli — glm-5.3 (6.4 s)

Koşul: n-heptane, O2 %19, 101 kPa, g=0.0001

```
LLM yorumu alınamadı (HTTP 503: {"error":{"message":"Model şu anda dolu, lütfen kısa bir süre sonra tekrar deneyin.","type":"api_error","param":null,"code":"model_capacity_exhausted")
```

### sınırda — gemma-4-31b (18.0 s)

Koşul: silicone, O2 %23, 70 kPa, g=0.0001

```
KARAR: Risk ORTA | güvenlik katsayısı 1.011 > 1 (güvenli) | güven 60/100 (yeterli)

Gerekçe:
- Sönme sınırı 23.25 iken ortam oksijeni 23 olduğundan, güvenlik katsayısı 1.011 ile 1'in üzerindedir ve teorik olarak güvenli bölgededir.
- Yanma ihtimali 0.472 (%47.2) olup %50 eşiğinin altında kaldığı için alevlenme beklenmemektedir.

Öneri: Güvenlik katsayısının 1'e çok yakın olması nedeniyle, oksijen seviyesindeki küçük artışların risk oluşturabileceği göz önünde bulundurulmalı ve ortam izlenmelidir.

Güvenilirlik: Güven skoru 60/100 olarak belirlenmiş olup, bu değer analiz için yeterli sınırda kabul edilmektedir.
```

### sınırda — glm-5.3 (55.1 s)

Koşul: silicone, O2 %23, 70 kPa, g=0.0001

```
KARAR: Risk ORTA | güvenlik katsayısı 1.011 > 1 (güvenli) | güven 60/100 (yeterli)

Gerekçe:
- Sönme sınırı 23.25, ortam oksijeni 23; güvenlik katsayısı 1.011 > 1 olduğu için sınırın güvenli tarafında kalıyor ancak fark yalnızca 0.25 puanlık oksijen marjı ile çok dar.
- Yanma ihtimali %47.2 olup %50 eşiğinin altında kaldığından alev yanar kabul edilmiyor; ancak belirsizlik %20.4 ile yüksek olduğundan bu ihtimal eşik üstüne çıkabilir.
- Güven skoru 60/100; 60'ın altı düşük güven sayıldığından bu skor "yeterli"nin en alt sınırında. Yakın deney sayısı 9 olup 1'i yanmış, 8'i sönerek sonuçlanmış.

Öneri: Risk ORTA olarak değerlendirilmeli; güvenlik katsayısı 1.011 çok dar bir marjla güvenli bölgede olduğundan ve yanma ihtimali %47.2 ile eşik değerine yakın bulunduğundan, oksijen konsantrasyonunun 23.25'in altına düşürülmesi veya seyreltici ile kontrol altına alınması önerilir. Ayrıca belirsizliğin %20.4 olması nedeniyle ek deneylerle motor ve veri güveninin artırılması tavsiye edilir.

Güvenilirlik: Sonuç, düşük güven sınırında (60/100) ve yüksek belirsizlik (%20.4) ile üretilmiştir. Veri ve motor bileşenleri 0.6 düzeyinde olup 9 yakın deneyden yalnızca 1'i yanma ile sonuçlanmıştır; motor yöntemi az veri nedeniyle sınırlı doğrulukla uygulanmıştır. Bu nedenle karar yönü doğru olsa da marjın darlığı ve belirsizlik nedeniyle dikkatle yorumlanmalıdır.

⚠️ Doğrulanamayan sayılar: 0.25
```

### düşük güven — gemma-4-31b (9.5 s)

Koşul: cotton, O2 %15, 70 kPa, g=0.0001

```
KARAR: Risk ORTA | güvenlik katsayısı 1.1 > 1 (güvenli) | güven 0/100 (düşük)

Gerekçe:
- Sönme sınırı 16.5 ve ortam oksijeni 15 olduğundan, güvenlik katsayısı 1.1 ile 1'den büyüktür ve teknik olarak güvenli bölgededir.
- Yanma ihtimali 0.431 (%43.1) olup %50 eşiğinin altında kaldığı için alevlenme beklenmemektedir.
- Veri setindeki risk seviyesi doğrudan "ORTA" olarak tanımlanmıştır.

Öneri: Güvenlik katsayısı sınır değerine yakın olduğu için oksijen konsantrasyonunun daha sıkı takip edilmesi ve malzeme kalınlığının kontrol edilmesi önerilir.

Güvenilirlik: Güven skoru 0/100'dür; motorun sonuç verebileceği yakın deneylerin bulunmaması nedeniyle analiz düşük güvenilirlikliğe sahiptir.
```

### düşük güven — glm-5.3 (88.3 s)

Koşul: cotton, O2 %15, 70 kPa, g=0.0001

```
KARAR: Risk ORTA | güvenlik katsayısı 1.1 > 1 (güvenli) | güven 0/100 (düşük)

Gerekçe:
- Güvenlik katsayısı 1.1 (sönme sınırı 16.5 / ortam oksijeni 15) 1'in üzerinde; sayısal olarak güvenli bölgede, ancak marj dar.
- Yanma ihtimali %43.1 ile %50 eşiğinin altında; alev yanar kabul edilmiyor, bu ORTA riskle uyumlu.
- Güven 0/100: yakın deney yok (yakan 0, sönen 0), motor bileşeni ölçülemedi; belirsizlik %29.9 yüksek.

Öneri: Pamuk kumaş için 15% O₂, 70 kPa koşullarında sönme sınırına çok yakın olunduğundan (marj yalnızca 1.5 puan) oksijenin daha da düşürülmesi veya seyreltici akışıyla sınırın güvenle altına inilmesi önerilir. Ayrıca bu malzeme-koşum kombinasyonunda gerçek deney yapılmadığından, kullanım öncesi yerinde sönme testi yapılmalıdır.

Güvenilirlik: Düşük. Güven skoru 0/100; veri ve motor bileşenleri sıfır, yakın deney bulunmuyor. Motor min_oksijen değeri (22.035) ortam oksijeninden yüksek olmasına rağmen yanma 0.0 çıkmıştır; bu tutarsızlık motorun bu bölgede ölçülemediğini doğruluyor. Sonuç sayısal olarak tutarlı ama deneysel desteği yok.

⚠️ Doğrulanamayan sayılar: 1.5
```

### kısmi g — gemma-4-31b (45.8 s)

Koşul: pmma, O2 %30, 70 kPa, g=0.38

```
KARAR: Risk ÇOK YÜKSEK | güvenlik katsayısı 0.525 < 1 (tehlikeli) | güven 0/100 (düşük)

Gerekçe:
- Ortam oksijeni (30), sönme sınırının (15.75) çok üzerindedir; bu durum güvenlik katsayısını 0.525 yaparak sistemi tehlike bölgesine sokmuştur.
- Yanma ihtimali 0.999 (%99.9) ile belirlendiği için malzemenin kesinlikle alev alacağı öngörülmektedir.
- Kısmi yerçekimi senaryosunda, gerçek g değerindeki risk seviyesi olan "ÇOK YÜKSEK" durumu baz alınmıştır.

Öneri: Oksijen konsantrasyonu acilen sönme sınırının altına düşürülmeli veya PMMA malzeme yanmaz alternatiflerle değiştirilmelidir.

Güvenilirlik: Güven skoru 0/100'dür; motorun sonuç verdiği yakın deneylerin bulunmaması nedeniyle analiz düşük güvenilirlik taşımaktadır.
```

### kısmi g — glm-5.3 (17.1 s)

Koşul: pmma, O2 %30, 70 kPa, g=0.38

```
KARAR: Risk ÇOK YÜKSEK | güvenlik katsayısı 0.525 < 1 (tehlikeli) | güven 0/100 (düşük)

Gerekçe:
- Ortam oksijeni %30, sönme sınırı %15.75; güvenlik katsayısı 0.525 < 1 olduğundan atmosfer sönme sınırının üzerinde ve tehlikeli. Yanma ihtimali %99.9 ile %50 eşiğinin çok üzerinde; alev yanar kabul edilir.
- Kısmi yerçekimi (0.38 g) için deney verisi az olduğundan uzay, gerçek g ve Dünya sonuçlarının en kötüsü alınmış; tüm senaryolarda risk ÇOK YÜKSEK çıkmıştır.
- Güven skoru 0/100: yakın deney sayısı sıfır (yanan/sönen 0/0), motor bileşeni 0 ve motor yöntemi ölçülemedi; model bu koşulda doğrulanamamıştır.

Öneri: PMMA ince levha bu ortamda tutuşur ve yayılır (yayılma hızı 8.861, sıcaklık ~1800.7 K); bu malzemeyi %30 O₂ / 70 kPa koşullarından uzak tutun, oksijeni %15.75'in altına düşürecek seyreltme veya malzeme değişimi uygulayın ve yangın söndürme/izolasyon önlemi bulundurun.

Güvenilirlik: Sonuç düşük güvenlidir; güven 0/100 olup veri ve motor bileşenleri sıfır, kısmi g'de deney yokluğu nedeniyle en kötü durum yaklaşımı kullanılmıştır. Sayısal değerler yönlendiricidir; tasarım kararı için gerçek koşullarda doğrulama deneyi yapılmalıdır.
```

### model-motor çelişkili — gemma-4-31b (25.0 s)

Koşul: pmma, O2 %17, 101 kPa, g=1.0

```
KARAR: Risk ÇOK YÜKSEK | güvenlik katsayısı 0.926 < 1 (tehlikeli) | güven 88/100 (yeterli)

Gerekçe:
- Güvenlik katsayısı 0.926 olup, değerin 1'den küçük olması ortamı tehlikeli sınıfına sokmaktadır.
- Yanma ihtimali 0.847 (%84.7) ile %50 eşiğinin oldukça üzerindedir, bu durum alevin yanacağını göstermektedir.
- Ortam oksijeni (17), malzemenin sönme sınırının (15.75) üzerinde olduğu için yanmayı desteklemektedir.

Öneri: Oksijen seviyesini sönme sınırının altına düşürecek önlemler alınmalı veya PMMA malzeme daha yüksek sönme sınırına sahip alternatiflerle değiştirilmelidir.

Güvenilirlik: Analiz sonucu 88/100 güven skoruna sahiptir ve bu değer belirlenen 60 alt limitinin üzerinde olduğu için yeterli kabul edilmektedir.
```

### model-motor çelişkili — glm-5.3 (22.4 s)

Koşul: pmma, O2 %17, 101 kPa, g=1.0

```
KARAR: Risk ÇOK YÜKSEK | güvenlik katsayısı 0.926 < 1 (tehlikeli) | güven 88/100 (yeterli)

Gerekçe:
- Ortam oksijeni (%17) sönme sınırının (15,75) üzerinde olsa da güvenlik katsayısı 0,926 < 1 olarak hesaplanmış; bu, mevcut koşulların sönme sınırına çok yakın olduğunu ve küçük bir oksijen artışının alevlenmeye yol açabileceğini gösterir.
- Yanma ihtimali %84,7 olup %50 eşiğinin çok üzerindedir; PMMA'nın bu ortamda yanması beklenir.
- Model ile fizik motoru çelişmektedir: model "yanar", motor "söner" diyor; bu belirsizlik risk değerlendirmesini karmaşıklaştırmaktadır.

Öneri: Risk ÇOK YÜKSEK seviyesinde olduğundan, bu ortamda PMMA'nın kullanımından kaçınılmalı veya oksijen seviyesi sönme sınırının güvenli bir marjla altına düşürülerek (örneğin azaltılmış oksijen ortamı) testler tekrarlanmalıdır. Ayrıca model-motor çelişkisi giderilene kadar ek deneylerle doğrulama yapılmalıdır.

Güvenilirlik: Güven skoru 88/100 olup yeterli düzeydedir; veri bileşeni 1,0 ve motor bileşeni 0,765 ile modelin bu koşullar için güçlü tahmin kabiliyetine işaret eder. Ancak belirsizlik %8,2 ve model-motor çelişkisi göz önünde bulundurulmalıdır.
```
