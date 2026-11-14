# gaz_motoru.py — rapor (2026-11-12)

Gaz yakıtlar için yarı-durağan fizik motoru (damla_motoru hızlı moduyla aynı mantık: kararlı hal + ışınım +
Damköhler). Bağımsız dosya; çalışma anında yalnız numpy + `gaz_ozellikleri.json`.

## Özet ve bilinen sınırlar (DONDURULDU: tek ışınım çarpanı + gri geri emme, `gaz_test_kayit/v3.json`)

**Dürüst AUC / doğruluk, geometri başına**
| geometri | test | n | AUC | doğruluk | kalibrasyon durumu |
|---|---|---|---|---|---|
| düz brülör (BRE) | test serisi (gün) dışarıda, 8 kat | 59 | 0.946 | 0.81 | kalibre (etilen/N2, 25 mm, µg) |
| küre | BRE ile kalibre -> Irace 2021 | 4 | 1.00 | 0.75 | ölçülmüş, n çok küçük |
| jet | literatür kontrol seti | 263 | 0.816 | 0.77 | **kalibre değil** (SLICE tablosu yok) |
Kontrol seti alt kümeleri: 1 g 0.850 (n 147), µg 0.791 (n 115, yalnız 11 söner).
Termokimya: T_ad medyan hata 19 K (PSI-10, 147 test).

**Bilinen sınırlar**
- **50 mm brülör:** PSI-20'de tutuşan 6 alevin hiçbiri için kararlı yanma bulunmuyor (0/6). Model yarım küre
  ışınım hacmiyle büyük brülörde ışınımı fazla tahmin ediyor olabilir. Gri geri emme ve is modeli bunu değiştirmedi.
  50 mm (ve 25 mm dışı) brülör sonuçlarına güvenme.
- **Metan (BRE):** tutuşan 5 alevin 2'si "yanabilir" (2/5). Metan etiketli veriyle kalibre edilmedi; motor metan
  alevlerinde fazla sönme öngörüyor olabilir.
- **Düşük basınç:** 1 bar verisiyle kalibre edip 0.56-0.71 bar'da test edince AUC 0.774, q'' hatası ~%65
  (tersi 0.912). Tüm veriyle bile ~1 bar'da saf etilen / yüksek O2'deki 3 kararlı test "söner" tarafında.
  Basınç dış değerlemesi zayıf.
- Etiketli verinin tamamı tek sette (BRE, 59 test). CH4, H2, C3H8, He/CO2, 1 g ve jet için çıktıda
  `kalibre_degil: true`.

**Is hipotezi neden reddedildi** (ayrıntı: aşağıdaki "Is (kurum) ışınımı hipotezi")
Hipotez: C_rad = 1.43 etilen isini telafi ediyor ve metana fazla ışınım veriyor. Gaz (C_gaz = 1) + is
(smoke point ölçekli; Kent 1986, SFPE, SPICE) modeli BRE'de iyileşti: gün dışarıda AUC 0.966, düşük basınçta
AUC 0.902. Ama:
1. Kural ölçütü olan kontrol seti kötüleşti: AUC 0.816 -> 0.786 (1 g'de 0.850 -> 0.799).
2. Irace'in issiz, seyreltik etilen alevi ışınımla söndü; is modeli bu alevin yanacağını öngörüyor.
   Demek ki issiz alev de saf gaz kuramından fazla ışıyor; C_rad yalnız isi telafi etmiyor.
3. Hedefler tutmadı: metan 3/5 (serbest C_gaz'la 5/5 ama C_gaz fiziksel sınırda), 50 mm 0/6.
4. µg BRE alevleri mavi (Dehghani 2021); uydurulan 1.6 ppm is gözlemle uyuşmuyor. BRE kazancı büyük olasılıkla
   ışınımın sıcaklık biçiminin düzelmesinden, is fiziğinden değil.
Açık aday: bant doygunluğunu içeren ışınım (WSGG / Leckner).

## Dosyalar
| Dosya | İş |
|---|---|
| `gaz_isinim.py` | ışınım kaybı + geri emme (bağımsız modül; damla motoru da kullanabilir) |
| `gaz_motoru.py` | motor + arayüz + veri okuyucular + kalibrasyon (`--kalibre`, `--dogrula`, `--profil`, `--grafik`) |
| `gaz_dogrulama.py` | dürüst testler, profil, grafik (gaz_motoru.py bayraklarıyla çağrılır) |
| `gaz_ozellik_uret.py` | Cantera ön hesabı (ayrı venv'de bir kez) -> `gaz_ozellikleri.json` |
| `gaz_motoru_parametreleri.json` | kalibre sayılar + sabit literatür sayıları |
| `gaz_dogrulama.csv` / `_ozet.csv` / `_ozet.json` | nokta bazında tahminler / özet ölçütler |
| `gaz_profil.csv` | literatürde sabitlenen T_kr ve a_q için profil |
| `gaz_motoru.png` | BRE kararlılık haritası (2 basınç), boyut, X_r, q'', T_ad kontrolleri |
| `gaz_test.py`, `gaz_test_kayit/` | regresyon testi (v1, v2 kayıtları) |
| `gaz_veri/`, `gaz_veri_envanteri.md` | makaleden çıkarılan tablolar, kaynaklar, veri envanteri |

Arayüz: `gaz_motoru(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi, seyreltici="n2", **ek)`
-> `yanma, min_oksijen, sicaklik, alev_yaricapi / alev_boyu, sonme_turu (isinim/kimyasal/yok), mesafe,
kalibre_degil` (+ `sicaklik_adyabatik, isinim_orani, isi_akisi_kW_m2, kopma, Z_st, uyarilar`).
`kalinlik` = kaynak boyutu (küre çapı / brülör çapı / lüle çapı), `akis` = yakıt çıkış hızı; ya da
`debi_mg_s`, `kutle_akisi_g_m2s`, `yakit_orani`. `motor.py`'ye bağlanmadı (o dosya diğer oturumun).

## Kalibrasyon (BRE, Dehghani 2021 Tablo 2, 59 ISS testi)
scipy L-BFGS-B, fiziksel sınırlar, 8 başlangıç — **8'i de aynı minimuma** (61.42-61.46) iniyor.

| sayı | değer | anlam |
|---|---|---|
| C_rad | 1.47 | optik ince ışınım çarpanı (1 = saf kuram) |
| k_s | 0.69 | brülöre geri iletim çarpanı |
| s | 0.60 | yanma olasılığı sigmoid genişliği |
| k_v, k_y | 0.357, 0.687 | yarım küre kuramından boyut düzeltmesi (yalnız boyut ölçümünden, etiketsiz) |
| T_kr | C2H4 1100, C3H8 1200, CH4 1300, H2 1070 K | **sabit, literatür** (Snegirev 2022; Lecoustre 2012) |
| a_q, T_a, S_L | 380 1/s (CH4-hava), 15098 K, S_L,ref tablosu | **sabit, literatür** (Puri & Seshadri 1986; WD 1981; Law 2006) |

Profil (`gaz_profil.csv`): T_kr(C2H4) için kayıp en düşük 1050 K (59.5), literatür 1100 K'de 61.4 (~1σ);
<900 K düz. a_q'nun taranan değerleri (38-3800) içinde en iyisi literatür değeri 380. -> İkisi de literatürde.

## Sonuçlar

### Geometri başına AUC (dürüst)
| geometri | test | n | AUC | doğruluk |
|---|---|---|---|---|
| düz (BRE) | gün (8 seri) dışarıda | 59 | **0.946** | 0.81 |
| küre | BRE ile kalibre -> Irace 2021 | 4 | 1.00 | 0.75 |
| jet | literatür kontrol seti (kalibre değil) | 263 | **0.816** | 0.77 |

### BRE içinde dışarıda bırakma
| eğitim -> test | n | AUC | doğ. | X_r hata | q'' hata | y_f hata | R_eff hata |
|---|---|---|---|---|---|---|---|
| içeride (eğitim hatası) | 59 | 0.959 | 0.83 | 0.042 | %13 | %13 | %9 |
| gün dışarıda | 59 | 0.946 | 0.81 | 0.045 | %18 | %12 | %9 |
| X_f=1 -> X_f=0.5 (yakıt seyreltme) | 27 | 0.971 | 0.89 | 0.046 | %10 | %18 | %10 |
| X_f=0.5 -> X_f=1 | 32 | 0.929 | 0.78 | 0.047 | %24 | %11 | %9 |
| 1 bar -> 0.56-0.71 bar | 35 | **0.783** | 0.74 | 0.117 | **%68** | %10 | %10 |
| 0.56-0.71 bar -> 1 bar | 24 | 0.903 | 0.75 | 0.077 | %48 | %20 | %9 |
| X_O2 >= 0.30 -> < 0.30 | 27 | 1.000 | 0.93 | 0.027 | %16 | %20 | %14 |
(X_r ve q'' yalnız FT testlerinde: SE alevlerinin ölçümü geçici rejimde.)

### Deney bazında
- BRE -> küre (Irace): 4 testin sıralaması doğru (AUC 1), ışınımla sönen alev 3 sınırda yanlış tarafta
  (yanma 0.53). Alev 3'te model T_f = **1110 K**, ölçülen sönme sıcaklığı **1140 K**. R_f, Irace'in kuramsal
  yarıçaplarından medyan %5.2 sapıyor (ρD kaynağı farkı: Cantera vs Irace'in sabit ρ0D0'ı).
- Küre (4 test) -> BRE: geometri kuramsal (yarım küre) alınırsa **AUC 0.50** (geometri aktarılamıyor);
  geometri yalnız BRE boyut ölçümünden (etiketsiz) alınırsa AUC 0.943 — ışınım çarpanı C_rad iki deney
  arasında aktarılabiliyor (küreden 1.49, BRE'den 1.43).
- PSI-10 Flame Design (147 sayısal test): **T_ad medyan hata 19 K** (ort -17, en çok 29), Z_st en çok 0.0002.
  Tabloda sönme sonucu yok -> yanma değerlendirilemez.
- Pozitif-yalnız (tutuşmuş alevler; "yanabilir" = donanım debi aralığında yanan bir debi var):
  s-Flame 22/23 (He 14/14, N2 8/9, H2 içeren 11/11); PSI-20 BRE C2H4 31/37, **CH4 2/5**, **50 mm 0/6**;
  CLD 32/32, E-FIELD 32/32, CLD aralık altı 30/31. Dikkat: tutuşma kararlı yanma demek değil
  (Dehghani'nin 59 tutuşmasının 30'u SE).

### Literatür kontrol seti (etiketli_gemma3 gaz, kalibrasyonda yok)
| alt küme | n | AUC | doğruluk |
|---|---|---|---|
| hepsi | 263 | 0.816 | 0.77 |
| **1 g** (kaldırma kontrolü) | 147 | 0.850 | 0.78 |
| µg | 115 | 0.794 | 0.76 (yalnız 11 söner!) |
| seyreltici verilmiş | 134 | 0.729 | 0.65 |
Kontrol: 1 g metan jeti havada min O2 %15.0 (cup-burner literatürü ~%15.4).

### Sıcaklık / yarıçap / boy
T_ad: 19 K (PSI-10). Kayıplı alev sıcaklığı: Irace alev 3'te 1110 vs 1140 K. BRE alev boyu y_f %12,
hacim-eşdeğer yarıçap %9 (gün dışarıda). Küre R_f: Irace kuramına %5. Jet L_f: ölçüm yok (SLICE tablosu yok).

## Işınım geri emme düzeltmesi (2. adım, tutuldu)
`gaz_isinim.py`: Q_rad = Q_ince · f(τ), f = (1-e^-τ)/τ, τ = (κ_P,alev + κ_P,ortam) · L_m, L_m = 3.6 V/A (Hottel
ortalama ışın yolu; Modest 2013 §10.6). Ortam CO2/H2O katkısı aynı L_m ile (varsayım). `GAZ_GERI_EMME=0` kapatır.

| ölçüt | önce | sonra |
|---|---|---|
| BRE gün dışarıda AUC / doğruluk | 0.943 / 0.831 | 0.946 / 0.814 (59'da 1 test) |
| BRE gün dışarıda X_r / q'' hatası | 0.047 / %19 | 0.045 / %18 |
| basınç dışarıda (1 bar -> düşük) AUC | 0.783 | 0.774 |
| **hedef: 50 mm brülör** yanabilir | 0/6 | **0/6** |
| **hedef: BRE-CH4** yanabilir | 2/5 | **2/5** |
| kontrol seti (bir kez, en sonda) AUC / doğ. | 0.816 / 0.768 | 0.816 / 0.768 (µg 0.794 -> 0.791) |

**Hedefler düzelmedi.** Sebebi: gri Planck ortalamasıyla τ çok küçük (BRE medyan 0.06, en çok 0.29; 50 mm'de
0.08-0.11; CH4'te 0.02-0.03), kayıp yalnız %1-5 iner. 50 mm alevlerinin kararlı çıkması için χ_r'nin
0.66'dan ~0.5'e (≈%25) inmesi gerekir. Ayrıca C_rad 1.43 -> 1.47'ye çıkarak düzeltmeyi kısmen telafi etti.
BRE ve kontrol seti kötüleşmediği için kural gereği tutuldu. Etkisi en çok CO2'li ortamda (propan jeti %18 O2 /
CO2: χ_r 0.76 -> 0.67).
Bir sonraki aday: bant doygunluğunu içeren düzeltme (Leckner 1972 toplam yayınırlık bağıntıları ya da WSGG,
ör. Smith-Shen-Friedman 1982 / Bordbar 2014). Gri Planck τ'su bant merkezlerinin erken kalınlaşmasını
görmüyor. Katsayılar doğrulanmış bir kaynaktan alınmalı; bu adımda eklemedim.

## Is (kurum) ışınımı hipotezi (3. adım, TUTULMADI)
Hipotez: C_rad = 1.43 etilen isini telafi ediyor; metana / büyük aleve aynı çarpan fazla ışınım veriyor.
Model (`GAZ_IS_MODELI=1`): κ = C_gaz κ_gaz + κ_is,  κ_is = C_is f_v I T,  C_gaz = 1 (saf kuram, sabit);
f_v (ppm) yalnız etilen BRE'den kalibre. Ortak geri emme (gaz_isinim.py). Kaynaklar (makale klasöründen):
- I (is eğilimi, etilen = 1) = ṁ_sp(C2H4)/ṁ_sp: Kent 1986 CNF 63:349 Tablo 1 (C2H4 3.84, C3H8 7.87 mg/s ->
  C3H8 0.49); CH4 = 0 (SFPE Böl. 36: ölçülmüş smoke point yok, >0.24 m; SPICE / Dotson & Sunderland 2010
  AIAA 2010-1105: ISS'te metanla smoke point bulunamadı); C2H6 0.40 (SFPE boyları 0.097 / 0.24 m).
- C_is = 1200 1/(m K): SFPE 5. bs. Tablo 4.11 gaz alevlerinde κ_S/(f_v T) = 1113-1247 (Rayleigh biçimi, Modest §11).
- SPICE µg smoke point'leri (C2H4 37-105 mm, 1.62-3.89 mg/s; C3H8 46-105 mm) sıralamayı doğruluyor.

Kalibrasyon: f_v = 1.61 ppm, k_s 0.70, s 0.31 (kayıp 58.4 -> 39.3; çok tepeli yüzey, 8 başlangıcın 2'si en iyi).

| ölçüt | tek çarpan (tutulan) | is, C_gaz=1 | is, C_gaz serbest [0.7-1.3] |
|---|---|---|---|
| BRE gün dışarıda AUC / doğ. | 0.946 / 0.814 | **0.966 / 0.864** | 0.963 / 0.881 |
| BRE gün dışarıda X_r / q'' | 0.045 / %18 | 0.040 / %13 | 0.035 / %10 |
| basınç dışarıda (1 bar -> düşük) | 0.774 / 0.743 | **0.902 / 0.800** | 0.931 / 0.829 |
| O2 dışarıda (yüksek -> düşük) | 1.000 / 0.926 | 1.000 / 0.852 | 1.000 / 0.852 |
| **hedef: BRE-CH4 (5)** | 2/5 | **3/5** | 5/5 (C_gaz sınırda: 0.70) |
| **hedef: 50 mm (6)** | 0/6 | **0/6** | 0/6 |
| PSI-20 C2H4 pozitif | 31/37 | 28/37 | 28/37 |
| BRE -> küre (Irace 4) AUC | 1.000 | 0.667 | 0.667 |
| kontrol seti (bir kez, en sonda) | 0.816 / 0.768 | **0.786 / 0.764** | (bakılmadı) |
| kontrol 1 g / µg AUC | 0.850 / 0.791 | 0.799 / 0.780 | |

Karar: BRE iyileşti ama **kontrol seti kötüleşti** (AUC -0.03, 1 g'de -0.05) -> kural gereği tutulmadı,
varsayılan tek çarpana döndü (çıktılar ve test v3 ile birebir). Hipotezi zayıflatan bulgular:
1. Irace alev 3 (%13 etilen; Irace: hiçbir alevde is ışıması yok) ışınımla söndü; is modeliyle "yanar" (0.96,
   T_f 1201 K), tek çarpanla sınırda (0.53, 1108 K; ölçülen sönme 1140 K). İssiz alev de C_gaz=1'den fazla ışıyor.
2. Dehghani 2021: µg BRE alevleri mavi, is ışınımı önemli görünmüyor; 1.6 ppm ortalama f_v gözle sarı alev demek.
3. Serbest C_gaz alt sınıra dayanıyor; BRE kazancı büyük olasılıkla is fiziğinden değil, κ_is ∝ T teriminin
   ışınımın sıcaklık bağımlılığını değiştirmesinden (biçim düzeltmesi).
4. 50 mm hiç değişmedi: sorun yakıt-özgü değil, geometri/ışınım hacmi.
Sonraki: WSGG / Leckner (bant doygunluğu: büyük alev ve ışınımın sıcaklık biçimi). Is modeli kodda duruyor
(`GAZ_IS_MODELI=1` / `serbest`), sonuçları `gaz_deneyler/`.

## Zayıf yanlar
1. **Tek etiketli PSI-kalitesinde set:** BRE, C2H4/N2, O2/N2 ortam, 25 mm. CH4, H2, C3H8, He, CO2, 50 mm,
   1 g ve jetler etiketli veriyle kalibre değil (`kalibre_degil: true`).
2. **Basınç dış değerlemesi zayıf:** 1 bar ile kalibre edip düşük basınçta AUC 0.78, q'' hatası %68. Tüm veriyle
   bile ~1 bar'da saf C2H4 / yüksek O2'deki 3 FT testi "söner" bölgesinde (gaz_motoru.png sol üst).
3. **Büyük brülör / CH4:** 50 mm'de hiçbir debide kararlı alev bulunmuyor, CH4'te 2/5 (gri geri emme düzeltmesinden sonra da). Yarım küre ışınım
   hacmi yassı alevde fazla olabilir. Düzlemsel film modeli denendi, geri alındı (içeride AUC 0.95 -> 0.88,
   q'' %14 -> %68).
4. **Jet:** kopma / üflenme sabitleri (K_taban = 10, K_üflenme = 5, en/boy = 3) VARSAYIM; literatür setinde
   akış ve lüle çapı çoğunlukla yok, yani o test esasen termokimyasal sınırı ölçüyor.
5. **Literatür setine ilk geliştirmede 4 kez bakıldı; geri emme ve is adımlarında her birinde yalnız en sonda 1 kez.** 1 g tüy boyu düzeltmesi bir fizik makullük durumundan
   (2 mg/s metan sızıntısı) çıktı ama kontrol AUC'si 0.79 -> 0.82 oldu: hafif sızıntı riski.
6. Kimya kaba: H2 ve karışımlarda mol ağırlıklı S_L, tek T_a; C2H6'nın T_kr'si propandan; bütan = propan.
   Kimyasal bastırıcılar (CF3Br, CF3H ...) desteklenmiyor.
7. Yarı-durağan: µg alevleri dakikalarca büyüyor; model kararlı hali (en büyük alevi) değerlendiriyor.
   Brülör sıcaklığı 300 K sabit (Irace: 773 K'e kadar). Is ışınımı yok (1 g'deki isli alevlerde ışınım düşük kalır).
8. Geliştirme sırasında bulunup düzeltilen hata: He taşınım verisi birim hatası (Cantera yapıcısı SI bekliyor)
   tüm viskozite/iletkenlik tablosunu bozmuştu; düzeltildi, gaz_test.py artık tabloları literatürle denetliyor.

## Sistem python3'üyle çalışma (venv'siz)
```
$ cd /tmp && /usr/bin/python3 -I ~/nasaspaceapp/gaz_test.py
TAMAM   1. çalışma anında yalnız numpy (cantera/scipy/pandas/sklearn yok)  yüklenen: []
TAMAM   1. python yorumlayıcısı  /usr/bin/python3 3.12.3, numpy 1.26.4
TAMAM   2. taşınım tabloları literatürle <= %6  en büyük sapma %5.4
TAMAM   3. PSI-10 T_ad medyan hata <= 30 K  19.1 K (147 test)
...
14/14 denetim tamam, 0.6 s
```
`sys.prefix = /usr`, numpy `/usr/lib/python3/dist-packages`. Cantera yalnız ön hesapta, scratchpad'deki ayrı
venv'de (Cantera 3.2.0) kullanıldı; yeniden üretmek için `gaz_ozellik_uret.py` başlığına bakın.

## Çekirdek kullanımı
Kalibrasyon öncesi `pgrep python` + `ps %CPU > 20` ile meşgul python işleri sayıldı (`bos_cekirdek()`),
işçi = 16 - meşgul, en çok 14; her işçide OMP_NUM_THREADS=1. Çalıştırmalarda 14, 6 ve 11 işçi kullanıldı
(diğer oturumun yükü değiştikçe).
