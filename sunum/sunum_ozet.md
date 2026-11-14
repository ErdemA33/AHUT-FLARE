# Sunum grafik paketi

Her grafiğin Türkçe (`_tr.png`) ve İngilizce (`_en.png`) sürümü var. Hepsi 200 dpi, aynı renk ve yazı stiliyle çizildi.
Grafikler yalnız mevcut sonuçlardan üretildi, yeni simülasyon koşulmadı. `tahmin.py`'ye yapılan çağrılar
`sunum_veri.py` ile `veri/` klasörüne kaydedildi.

- **Yeniden üretmek için:** `python3 sunum/sunum_veri.py` (~10 dk), ardından `python3 sunum/sunum_grafik.py`.
- **Renkler:** her bileşen her grafikte aynı renkte.
  - Risk modeli mavi, hafif motor (katı) turuncu, damla motoru (sıvı) yeşil.
  - Gaz motoru sarı, LLM mor, OpenFOAM pembe, deney ölçümü siyah.
  - Haritada mavi = söner, kırmızı = yanar; gri, %50 sınırı.

| # | Dosya | Tek cümlelik mesaj | Kaynak |
|---|---|---|---|
| a | `a_sistem_semasi_{tr,en}.png` | Girdi önce risk modeline ve yönlendiriciye gider. Yönlendirici yakıt türüne göre katı/sıvı/gaz motorunu seçer. Model ile motor dürüst test AUC'lerine göre birleştirilir, sonuca 0–100 arası güven skoru eklenir. LLM yalnız listede olmayan malzemeyi eşler ve isteğe bağlı yorum yazar. | `tahmin.py`, `motor.py`, `motor_kontrol.py`, `llm_analiz.py` |
| b | `b_durust_auc_{tr,en}.png` | Her bileşen görmediği veride rastgeleden belirgin biçimde iyi. Dürüst test AUC değerleri: risk modeli 0,878 (NASA), hafif motor 0,729, damla 0,805, gaz düz 0,946, gaz jet 0,816. Jet kalibre olmadığı için ağırlığı 0; OpenFOAM motoru henüz yok. | `motor_dogrulama.json` |
| c | `c_ay_mars_harita_{tr,en}.png` | NASA'nın önerdiği habitat atmosferinde (%30–34 O₂, 55–70 kPa) ince PMMA hem Ay'da hem Mars'ta neredeyse kesin yanıyor: birleşik ihtimal Ay'da 0,98, Mars'ta 0,96–0,97 (yalnız risk modeli: 0,998–0,999). %50 sınırı 70 kPa'da birleşik ihtimalle Ay ~%14,6, Mars ~%15,0 O₂; yalnız risk modeliyle Ay ~%15,7, Mars ~%15,8 (mavi kesik çizgi). | `sunum_veri.py` → `tahmin.py` (`yanma_birlesik`, `yanma_ihtimali`), PMMA 0,2 mm, akış bilinmiyor (en kötü durum) |
| d | `d_damla_kismi_g_{tr,en}.png` | Damla motoruna göre damla yanma hızı 1 g'de mikro-g'nin 1,26–1,31 katı; literatür aralığı 1,2–1,5. | `damla_kismi_g.csv`, `damla_dogrulama_ek.json` |
| e | `e_flex_d2_K_{tr,en}.png` | 2 mm n-heptan damlasında OpenFOAM yanma hızını FLEX ölçümünün ~1,8 katı veriyor (1,13'e karşı 0,57–0,67 mm²/s). Damla motoru 0,59 ile FLEX aralığında; sönme çapı 0,64 mm. | `of_tek_damla_sonuc.csv`, `of_kosular/tek_damla_isinimsiz.log`, `damla_flex_alev_noktalar.csv` (NASA/TP-2015-216046 grafiklerinden sayısallaştırma), `damla_motoru.py` |
| f | `f_guven_skoru_{tr,en}.png` | Güven skoru 100 × (0,4 veri + 0,3 uyum + 0,3 motor) formülüyle hesaplanıyor. Örnek: PMMA, ISS, %21 O₂. 279 yakın deney olduğu için veri bileşeni 1,00; uyum 1 − \|0,95 − 0,81\| = 0,86; motor bileşeni 0,75 (AUC 0,88). Skor 88/100. | `veri/ornek_guven.json` ← `tahmin.py`, `motor_kontrol.guven_skoru` |
| g | `g_kevlar_celiski_{tr,en}.png` | Listede olmayan Kevlar'ı LLM nomex'e eşliyor. ISS'te %21 O₂'de model 0,44 ("söner"), hafif motor 0,96 ("yanar") diyor; sistem çelişki uyarısı veriyor ve birleşik 0,64 sonucunu düşük güvenle (51/100) gösteriyor. Motor bileşeni 0 çünkü motorun bu bölgedeki AUC'si 0,50. | `veri/kevlar.json` ← `tahmin.py` (LLM eşlemesi önbellekten) |

## Notlar ve sınırlar

- **c — %50 sınırı:** birleşik sınır, hafif motorun düşük sınırı yüzünden olması gerekenden ~1 puan düşük
  olabilir (aşağıda "Çıkarılan grafik"). Bu yüzden haritaya yalnız risk modelinin sınırı da eklendi. Habitat kutusundaki
  sonuç (≥0,96) iki durumda da aynı.
- **c — basınç etkisi:** haritada basıncın etkisi zayıf, sınır çizgisi neredeyse dikey. Bu, modelin ve hafif motorun bu
  aralıkta basınca az duyarlı olmasından geliyor; ölçülmüş bir basınç etkisi olarak sunulmamalı.
- **d — kısmi g:** g > 0 için damla motorunun Ranz–Marshall/Faeth düzeltmesi kullanıldı.
  - Bu düzeltme 1 g verisinde kontrol edildi: FLEX-2 makale verisinde 65 noktada AUC 0,61; Aşama 5a'da veri_temiz eklenerek
    96 nokta ve 5 makalede AUC 0,60, doğruluk 0,79. Kısmi g için deney verisi yok.
  - Aşama 5a'da katsayı serbest bırakılınca makale-dışarıda AUC 0,64'e çıktı ama doğruluk 0,78'e düştü. Katsayı ızgara
    ucunda kaldı ve K(1 g)/K(µg) oranı 1,94 çıktı, literatür 1,2–1,5. Bu yüzden benimsenmedi.
    Ayrıntı: `damla_dogrulama_ek.json`, `deneyler/asama5a_tasinim.json`.
  - Literatür aralığı yaklaşıktır (Okajima & Kumagai 1975, Law & Faeth 1994).
- **e — FLEX verisi:** FLEX d² noktaları, NASA/TP-2015-216046'nın Ek B grafiklerinden sayısallaştırıldı.
  - Test 7, 51 ve 229 (rapor no. 235) kullanıldı; başka seriden taşan birkaç nokta (d²/d₀² > 1,05) atıldı.
  - Farklı ilk çapları karşılaştırabilmek için eksenler d₀² ile ölçeklendi; eğim K'yı verir.
  - OpenFOAM koşusu ışınımsız ve tek adım kimyalı. ×1,8 farkın nedeni nokta-damla buharlaşma modeli
    (`of_tek_damla.py` notu).
- **g — ekran çıktısı:** grafik, dashboard ekranının birebir görüntüsü değil, `tahmin.py` çıktısının sunum için
  çizilmiş bir taklidi. Alanlar ve uyarı metinleri birebir; İngilizce sürümde uyarılar çevrildi.

## Çıkarılan grafik: U eğrisi (eski d, sol panel)

Eski `d_yercekimi_sonme` grafiğinin sol paneli paketten çıkarıldı. Damla paneli tek başına `d_damla_kismi_g` oldu.
Eski dosyalar `of_kosular/` altında.

- **Sorun:** eğri yalnız hafif motordan geliyordu ve literatürle uyuşmuyor.
  - Hafif motorda en düşük sınır %6,8–8 O₂ (10⁻³–10⁻² g), Dünya'da %14,2.
  - Literatür: Takahashi ince PMMA µg MLOC %14,7 (6 cm/s akışla), 1 g LOI %17,0; 0,2 mm PMMA LOI %17,5.
  - BASS-II (PSI-25): %15'te 3–5 cm/s akışta yanıyor, 2 cm/s'de sönüyor. BASS (PSI-26): durgun ISS'te %21,7'de bile sönüyor.
- **Bileşenler ayrı ayrı** (durgun, PMMA 0,2 mm; tanı grafiği `deneyler/u_egrisi_tani_{tr,en}.png`):

  | g | risk modeli | hafif motor | birleşik |
  |---|---|---|---|
  | ISS (≤10⁻⁴) | %17,2 | %17,0 | %17,2 |
  | 10⁻² | %16,3 | %8,2 | %14,7 |
  | Ay 0,165 | %16,2 | %11,2 | %15,0 |
  | Mars 0,38 | %16,3 | %12,4 | %15,6 |
  | Dünya 1 | %16,3 | %14,2 | %16,1 |

  Risk modeli literatüre ~1 puan yakın ama g'ye neredeyse duyarsız, yani U şekli vermiyor. Hafif motor U şekli
  veriyor ama ~3–8 puan düşük.
- **Kaynak:** hafif motorun kalibrasyon verisinde (psi_etiketli*.csv) ince katılar için %15 O₂ altında hiç sönme etiketi
  yok, bu yüzden alt sınır kalibrasyonda serbest kalıyor. İnce katı grubunun aktivasyon sıcaklığı düşük (Ta ≈ 10 300 K),
  sınır alev sıcaklığına az bağlı ve motor düşük oksijende de "yanar" diyor. 1 g ince katı verisi de az.
- **Denenen düzeltme (geri alındı):** Takahashi'nin MLOC ve LOI değerlerinin iki yanına literatür çapa noktaları eklenip
  hafif motor yeniden kalibre edildi. U değerleri literatüre yaklaştı (ağırlık 10: Ay %14,75, Dünya %17,75), ama:
  - dürüst test (aileye göre 5'li GroupKFold) katı AUC'si 0,729 → 0,687'ye düştü (ağırlık 30: 0,672; 100: 0,571);
  - 10⁻³ g'de durgun ortamdaki minimum hâlâ ~%11, ISS durgunda %13,8 (BASS: %21,7'de bile söner) → daha da kötü.

  Kural gereği geri alındı. Motorun yapısı (sabit Tv'li yüzey ışınımı kaybı) bu sınırı tutmaya yetmiyor. Ayrıntı:
  `deneyler/u_egrisi_karar.json`.
