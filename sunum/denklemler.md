# Damla motoru (hızlı mod) ve gaz motoru: denklemler

Bu belge `damla_motoru.py` (hızlı mod) ve `gaz_motoru.py` dosyalarındaki hesapları **kodun gerçekte çalıştığı sırayla**
anlatıyor. Her adımda sembollerin anlamı, kalibre edilmiş değerler (parametre dosyasından) ve kaynak var.
Kod değiştirilmedi. Belge `v_yarisma` etiketindeki koda göre yazıldı (2026-11-12).

**Kaynak sayfaları hakkında.**
- **Taranan klasörler** (2026-11-12): `/mnt/ssd/nasaspaceapp/metinler/` (makale metinleri), `/mnt/ssd/nasaspaceapp/pdfler/`,
  FLEX12 ve BASS makale klasörleri.
- **"doğrulandı":** kaynak bu klasörlerde bulundu ve denklemin ya da değerin geçtiği yer okundu. Sayfa numarası
  derginin baskı sayfasıdır; baskı öncesi kopyalarda PDF sayfası verildi.
- **"doğrulanamadı":** kaynak klasörlerde yok (kitaplar ve bazı eski makaleler). Yazılan künye kod notundan geliyor,
  kontrol edilmedi.
- Bulunan kaynak dosyalarının adları sondaki "Kaynak dosyaları" tablosunda.

Bölüm 3'te, kodun başındaki açıklama listesinde (docstring) yanlış ya da eksik olan maddeler ayrıca listelendi.

---

## 1. Damla motoru — hızlı mod (`damla_motoru.py`, `hizli_hesap` → `_hizli_son` → `hizli_ozet`)

**Ne yapıyor:** bir sıvı yakıt damlasının durgun ya da kısmi g ortamında yanıp yanmayacağını, yanma hızını (K)
ve hangi çapta söneceğini hesaplıyor. Damlanın çapı d₀'dan 0,04·d₀'a kadar 49 adımda küçültülür
(`D_ORAN`). Her çapta damla "yarı durağan" kabul edilir: o anki çap için kararlı hal çözülür.

### 1.0 Sabitler

| sembol | anlamı | değer | kaynak |
|---|---|---|---|
| R_u | evrensel gaz sabiti | 8314,46 J/(kmol·K) | — |
| σ | Stefan–Boltzmann sabiti | 5,670·10⁻⁸ W/(m²·K⁴) | — |
| P₀ | referans basınç | 101 325 Pa | — |
| T∞ | ortam sıcaklığı | 298 K | — |
| T_sönme | bunun altındaki alev söndü sayılır | 1200 K | mühendislik eşiği (kod) |
| d/d₀ ≥ 0,85 | "hemen söndü" etiketi | 0,85 | `psi_flex.py` ile aynı etiket kuralı |

**Yakıt verileri** (M, T_b kaynama, T_c kritik sıcaklık, L_b buharlaşma ısısı, ρ_l sıvı yoğunluğu, c_l, Q alt ısıl değer):
NIST WebBook, Yaws (2003), Perry's 8. baskı (**doğrulanamadı**: kitaplar klasörlerde yok).
Tek adım kimya katsayıları A, E_a = 30 kcal/mol, a, b: Westbrook & Dryer (1981), *Combust. Sci. Technol.* 27:31–43,
Tablo 2. 1-propanol tabloda yok, etanol değerleri kullanılıyor.

**Gaz özellikleri** (viskozite μ_i, ısıl iletkenlik λ_i, c_p,i, ikili difüzyon D_ij):
- Cantera ile önceden hesaplanmış tablodan okunuyor (`damla_ozellikleri.json`, 250–3000 K, 50 K adım).
- Karışım kuralları:
  - viskozite: Wilke (1950), *J. Chem. Phys.* 18:517;
  - iletkenlik: Mathur, Tondon & Saxena (1967), *Mol. Phys.* 12:569 (**doğrulanamadı**: klasörlerde yok).
- Ağır yakıtların Lennard-Jones parametreleri Tee–Gotoh–Stewart (1966) korelasyonundan (`damla_ozellik_uret.py`).

### 1.1 Ortam bileşimi

```
X_O2 = oksijen / 100,   X_seyreltici = 1 − X_O2          (ya da verilen bileşim)
Y_i  = X_i M_i / Σ X_j M_j                                 kütle kesri
```

### 1.2 Stokiyometri

```
n_O2 = n_C + n_H/4 − (alkolse 1/2)        1 mol yakıt için gereken O2 molü
ν    = n_O2 · 31,999 / M_F                kg O2 / kg yakıt
```
Alev bileşimi Y_f: 1 kg buhar, stokiyometrik O2 ile yanar. Ürün CO₂ ve H₂O'dur; O₂'yle gelen inert gaz da eklenir.
Alkol damlasında emilen su (Y_wl) ürünlere eklenir.

### 1.3 Döngü (8 tur; T_f, χ_R ve Y_wl her turda yarı yarıya güncellenir)

Başlangıç: T_f = 2000 K, T_s = 300 K, χ_R = 0, Y_wl = 0.

**a) Yüzey sıcaklığı T_s:** iki denklem eşitlenir, 22 adım ikiye bölme ile.

```
B        = [ c_p (T∞ − T_s) + Y_O∞ Q (1 − Y_wl)(1 − χ_R) / (ν (1 − Y_wl)) ] / L(T_s)        aktarım sayısı
Y_Fs,enerji = (B − Y_O∞ / (ν(1−Y_wl))) / (1 + B)
X_Fs     = [ x_F p_sat,F(T_s) + (1 − x_F) p_sat,su(T_s) ] / p                              Raoult (sıvıda su varsa)
Y_Fs,denge = X_Fs M_v / (X_Fs M_v + (1 − X_Fs) M_f)
```
| sembol | anlamı |
|---|---|
| B | Spalding aktarım sayısı (buharlaşmayı süren "itici güç") |
| c_p | iç bölge özgül ısısı: alev bileşiminde, (T_s+T_f)/2'de |
| Y_O∞ | ortamda O₂ kütle kesri |
| Q | yakıtın alt ısıl değeri (J/kg) |
| χ_R | ışınımla kaybedilen ısı oranı |
| Y_wl, x_F | sıvıdaki su kütle kesri; sıvıda yakıt mol kesri |
| L(T) | buharlaşma ısısı, Watson (1943): L = L_b [(T_c − T)/(T_c − T_b)]^0,38 (*Ind. Eng. Chem.* 35:398; **doğrulanamadı**, klasörlerde yok) |
| p_sat | doyma basıncı, Clausius–Clapeyron, sabit L_b ile: p_sat = P₀ exp[L_b M/R_u (1/T_b − 1/T)] |
| M_v, M_f | buharın ve alev bileşiminin mol kütlesi |

Kaynaklar:
- **Spalding (1953)**, "The combustion of liquid fuels", *4th Symp. (Int.) Combust.*, s. 847–864 (**doğrulandı**).
  - Aktarım sayısı B'nin yanmalı hali: §3.3, s. 853.
  - Durgun ortamdaki küre için ṁ c/k = ln(1 + B) ve buharlaşma sabiti λ = 8 k ln(1 + B) / (ρ_l c): §4, durum (2), s. 854.
    Bu, 1.3e'deki K formülünün kaynağı.
  - OCR kalitesi düşük; formüller sayfa görüntüsüyle karşılaştırılarak okundu.
- **Godsave (1953)**, "Studies of the combustion of drops in a fuel spray — the burning of single drops of fuel",
  *4th Symp. (Int.) Combust.*, s. 818–830 (**doğrulandı**). d² yasası x² = x₀² − λt Eş. (15), §3.21, s. 823.
  Ölçülen buharlaşma sabitleri Tablo 1'de, s. 825.
- **Ders kitapları:** Law (2006) *Combustion Physics* ve Turns (2012) *An Introduction to Combustion* 3. bs. Bölüm 10
  (**doğrulanamadı**: kitaplar klasörlerde yok).

**b) Alev sıcaklığı T_f:**
```
T_f,ad = T_s + (L / c_p) [ (1 + B) / (1 + Y_O∞/ν) − 1 ]
T_f    = T_f,ad                                   (T_f,ad ≤ 2000 K ise)
       = 2000 + a / (1 + a/700),  a = T_f,ad − 2000   (üstündeyse; ayrışma için yumuşak tavan, en çok ~2700 K)
```
Ayrışma tavanı kodda tanımlı bir mühendislik yaklaşımı (gaz motorundaki Cantera'ya uydurulmuş düzeltmeyle aynı şey değil).

**c) İç bölge taşınım özelliği (λ/c_p)_iç:**
- Bileşim: yüzey bileşimi (yakıt buharı, su, alev ürünleri) ile alev bileşiminin ortalaması.
- Sıcaklık: (T_s+T_f)/2.
- Yöntem: değişken özellikli iç bölge yaklaşımı. Kod notu: Law & Law (1977) (**doğrulanamadı**: klasörlerde yok).

**d) Taşınım düzeltmesi Nu/2** (yalnız g > 10⁻⁴ g₀ ya da akış > 0 ise; yoksa Nu/2 = 1):
```
Nu/2 = 1 + c · Pr^(1/3) · (Re² + Gr)^n
Gr   = g (T_f − T∞)/T∞ · d³ / ν_k² · r(g)⁴
Re   = U d / ν_k
r(g) = log-doğrusal rampa: g ≤ 10⁻⁴ g₀ → 0,  g ≥ 10⁻² g₀ → 1
```
| sembol | anlamı | değer | kaynak |
|---|---|---|---|
| c | taşınım katsayısı | **0,3** (sabit) | Ranz & Marshall (1952), *Chem. Eng. Prog.* 48:141 ve 48:173 |
| n | üs | **0,25** (sabit) | aynı; doğal taşınımla birleşik hali Faeth (1977), *Prog. Energy Combust. Sci.* 3:191 |
| d | o anki damla çapı | — | — |
| ν_k | kinematik viskozite | ortam bileşimi, film sıcaklığı (T_f+T∞)/2 | — |
| U | zorlanmış akış hızı | girdi | — |

Bu düzeltme yaklaşıktır: küresel simetri bozulur, bağıntı yalnız ortalama etkiyi verir.

Doğrulama durumu:
- **1 g:** 96 noktada sınandı, AUC 0,60.
  - Aşama 5a'da c ve n serbest bırakılınca makale-dışarıda AUC 0,64'e çıktı ama doğruluk düştü ve K(1 g)/K(µg) oranı
    1,94 oldu (literatür 1,2–1,5). Bu yüzden benimsenmedi.
- **Zorlanmış akış:** doğrulanamadı, koşulları tam bir ölçüm bulunamadı.
- **Rampa (10⁻⁴–10⁻² g arası):** bir mühendislik varsayımı, bu aralıkta veri yok.

**e) Buharlaşma hızı ve yanma hızı:**
```
ṁ = 4π (λ/c_p)_iç · kz · r_s · ln(1 + B) · (Nu/2)                kg/s
K = 8 (λ/c_p)_iç · kz · ln(1 + B) · (Nu/2) / ρ_l                 m²/s  (d² = d₀² − K t)
```
| sembol | anlamı | değer | kaynak |
|---|---|---|---|
| kz | iç bölge özelliği için düzeltme çarpanı | **0,774** (bootstrap 16–84 %: 0,755–0,781) | FLEX ile kalibre |
| r_s | damla yarıçapı | — | — |
| ρ_l | sıvı yoğunluğu | yakıt tablosu | NIST / Yaws |

**f) Alev yarıçapı:**
```
FSR = ln(1 + B) / ln(1 + Y_O∞/ν)                           yarı-durağan alev/damla oranı
r_f = e^(ln_fsr) · FSR · r_s^(1−β) · r₀^β / (Nu/2)
```
| sembol | anlamı | değer | kaynak |
|---|---|---|---|
| ln_fsr | yarı-durağan kuram µg'de alevi fazla uzak verir (heptanda ~30 kat yerine FLEX ölçümü ~9 kat); düzeltme | **−0,896 → çarpan 0,408** (bootstrap −1,02…−0,85) | FLEX alev çapı ölçümü: NASA/TP-2015-216046 Ek B, s. 29–305 (sayısallaştırma) |
| β | alevin damla küçülürken ne kadar "geride kaldığı" (β = 0 yarı-durağan, β = 1 sabit alev, β > 1 alev büyür) | **1,278** (bootstrap 1,26–1,50; üst sınır 1,5) | FLEX ile kalibre; fikir: Nayagam ve ark. (2012) *Combust. Flame* 159:3583, Farouk & Dryer (2011), Choi & Dryer (2001) |
| r₀ | ilk damla yarıçapı | — | — |

**g) Işınım kaybı (optik ince, Planck ortalama):**
```
Q_rad = C_rad · 4σ · (p/P₀) · (X_CO2 a_CO2(T_f) + X_H2O a_H2O(T_f)) · (T_f⁴ − T∞⁴) · (4/3) π r_f³
χ_R   = min( Q_rad / (ṁ Q (1 − Y_wl)), 0,97 )
```
| sembol | anlamı | değer | kaynak |
|---|---|---|---|
| C_rad | ışınım çarpanı (optik ince üst sınıra göre; yeniden soğurma payı) | **0,30** (sabit, ln_Crad = −1,204) | fiziksel aralıkta sabitlendi (Aşama 2e) |
| a_CO2, a_H2O | Planck ortalama soğurma katsayısı, 1/(m·atm), T'nin 5. derece polinomu (300–2500 K) | — | Barlow ve ark., TNF Workshop (RADCAL uydurması), www.sandia.gov/TNF |
| X_CO2, X_H2O | alev bileşimindeki mol kesirleri | — | — |

Yalnız gaz (CO₂/H₂O) ışınımı hesaplanıyor; is (kurum) ışınımı yok. Geri emme (`DAMLA_GERI_EMME`) kapalı: Aşama 2g'de
denendi, dürüst testi kötüleştirdi.

**h) Su emme (yalnız metanol, etanol, 1-propanol):**
```
Y_H2O,s  = (1 − Y_Fs) · Y_f,H2O                        yüzeydeki su buharı
dm_w/dt  = k_w · π d² · Y_H2O,s
Δt       = Δ(d²) / K_ort                               d² eğrisinden zaman
Y_wl     = min( m_w / m_l , 0,8 )                      m_l = ρ_l π d³/6
```
| sembol | anlamı | değer | kaynak |
|---|---|---|---|
| k_w | su emme katsayısı [kg/(m²·s)] | **e^(−3,022) = 0,0487** (bootstrap 0,046–0,058) | FLEX ile kalibre; fikir: Marchese & Dryer (1996), Dryer ve ark. (2014) FLEX (**doğrulanamadı**: ikisi de klasörlerde yok. Klasördeki NASA-CR, Marchese & Dryer "Transient numerical modeling of the combustion of bi-component liquid droplets: ethanol/water mixtures" (`19970003276`) aynı konuda, ama kodun atıf yaptığı yayın değil) |

Emilen su üç şeyi değiştirir: Raoult yasasıyla yakıt buharını azaltır, L'yi artırır, alevi seyreltir.

### 1.4 Sönme ölçütü (Damköhler + sıcaklık), `_hizli_son`

```
ln Da = ln(r_f² / α_f) + ln A + (a + b − 1) ln ρ_f + b ln Y_O∞ − T_a / T_f
sönük = (ln Da < 0)  ya da  (T_f < 1200 K)
```
| sembol | anlamı | değer | kaynak |
|---|---|---|---|
| α_f | alevdeki ısıl yayınım λ/(ρ c_p) | — | — |
| ρ_f | alev yoğunluğu p M_f / (R_u T_f) | — | — |
| A, a, b | tek adım hız sabiti ve üsleri | yakıt tablosu | Westbrook & Dryer (1981) Tablo 2 |
| ln A düzeltmesi | lnA_NC7H16, lnA_CH3OH | **0** (sabit) | veriden belirlenemedi (Aşama 2c) |
| T_a | aktivasyon sıcaklığı | **15 098 K** (30 kcal/mol, sabit) | Westbrook & Dryer (1981) |

Kalibre edilmemiş yakıtlar (etanol, n-dekan, 1-propanol), kalibre yakıtların ln A düzeltmelerinin ortalamasını
alır (= 0).

> **Dikkat:** bu ölçütün birimleri tutarlı değil ve kimyasal sönme bu motorda pratikte devre dışı.
> Ayrıntı: Bölüm 4, "Bilinen sınırlar".

### 1.5 Sonuçların özetlenmesi, `hizli_ozet`

```
marj  = min( ln Da , (T_f − 1200 K) / 100 K )                  iki ölçütün kötüsü
yanma = σ( min_{d ≥ 0,85 d₀} marj / s )                         σ(x) = 1/(1 + e^(−x))
```
| sembol | anlamı | değer |
|---|---|---|
| s | yanma olasılığının yumuşaklığı (istatistiksel genişlik) | **2,515** (bootstrap 2,40–5,15) |

- **Sönme çapı:** marj'ın ilk kez 0'ın altına düştüğü çap. İki ızgara noktası arasında doğrusal ara değerle bulunur.
- **Ortalama K:** sönmeye kadar d² eğrisi boyunca alınır.
  ```
  t_son = Σ Δ(d²) / K_ort,       K = (d₀² − d_son²) / t_son
  ```
- **En az oksijen:** diğer gazların oranı sabit tutularak O₂ %1–60 arasında 0,25'lik adımlarla taranır.
  Yanma ≥ 0,5 olan en düşük O₂ değeri sonuç olur.
- **Sönme türü:** ışınım kapatılıp (C_rad → 0) yeniden hesaplanır.
  - Sönme kalkıyorsa ya da sönme çapı yarıdan fazla küçülüyorsa "ışınım".
  - Değilse "kimyasal".
- **Soğuk alev (ampirik kural, kalibre değil):** üç koşul birlikte sağlanırsa var sayılır: yakıt n-alkan (heptan, dekan),
  sıcak alev damla bitmeden söner ve ortamda He < %10.
  - Süre: t = (d_s² − (0,5 d_s)²) / (0,5 K).
  - Kaynak: Nayagam ve ark. (2012) *Combust. Flame* 159:3583; Farouk & Dryer (2014).
  - Etiketlere göre isabet %87. Bu örneklem içi bir sonuç, dürüst test değil.

### 1.6 Kalibrasyon özeti

- **Veri:** 261 FLEX testi (psi_flex_testler.csv).
- **Kayıp:** yanar/söner etiketi (ikili çapraz entropi) + K hatası (σ = 0,10, log) + sönme çapı hatası (σ = 0,10)
  + FLEX alev çapı oranı (σ = 0,15).
- **Serbest parametreler:** β, kz, s, ln_kw, ln_fsr.
- **Sabit parametreler:** C_rad = 0,3, T_a = 15 098 K, ln A = 0, c = 0,3, n = 0,25.
- **Belirsizlik:** 50 kalibrasyonluk deney grubu bootstrap'ı; aralıklar yukarıdaki tablolarda (16–84 %).
- **Dürüst test:** N₂ ile kalibre edip CO₂ + He testlerinde denendi: AUC 0,805.
  - Yakıtlardan biri kalibrasyon dışında bırakıldığında: heptan 0,883, metanol 0,800.

---

## 2. Gaz motoru (`gaz_motoru.py`, `hesapla`)

**Ne yapıyor:** gaz yakıt alevinin (küre, düz brülör ya da jet) yanıp yanmayacağını, kayıplı alev sıcaklığını,
alev boyutunu ve sönme türünü hesaplıyor. Yaklaşım yarı durağan: kararlı hal, ışınım ve Damköhler ölçütü.

### 2.0 Sabitler ve veriler

| sembol | anlamı | değer | kaynak |
|---|---|---|---|
| T∞ | ortam sıcaklığı | 298,15 K | — |
| S_L,ref | stokiyometrik yakıt-hava laminer alev hızı (1 atm) | CH₄ 0,37 · C₂H₄ 0,68 · C₂H₆ 0,41 · C₃H₈ 0,43 · H₂ 2,10 m/s | Law (2006) *Combustion Physics* Böl. 7 derlemesi (kod notu; **doğrulanamadı**, kitap klasörlerde yok) |
| T_kr | kritik (sönme) alev sıcaklığı | C₂H₄ 1100 · C₃H₈ 1200 · C₂H₆ 1200 · CH₄ 1300 · H₂ 1070 K | Ayrıntı aşağıdaki listede |
| T_a | aktivasyon sıcaklığı | 15 098 K | Westbrook & Dryer (1981), damla motoruyla aynı |
| a_q | metan-hava karşı akış sönme gerinimi | 380 1/s | Puri & Seshadri (1986) *Combust. Flame* 65:137 |
| S_L ∝ p^(−0,4) | basınç üssü | −0,4 | Law (2006) |
| µg jet uzaması | µg jet alevi 1 g'dekinden uzun | %28 | Ayrıntı aşağıdaki listede |
| en/boy | jet alevi boy/en oranı | 3 | **VARSAYIM** |
| K_taban | jet tabanı gerinimi a = U/(K_taban d) | 10 | **VARSAYIM** |
| K_üflenme | kopmuş alev ln Da_taban < −ln 5 iken üflenir | 5 | **VARSAYIM** |
| χ_maks | kayıp oranı üst sınırı | 0,97 | — |

**T_kr kaynakları:**
- **Etilen, propan, metan (1100 / 1200 / 1300 K):** Snegirev, "On radiative extinction of microgravity diffusion flames"
  (**doğrulandı**). Değerler Özet'te (s. 1) ve s. 9'da.
  - Klasördeki kopya (`W4309552902`) hakem öncesi el yazması; derginin künyesi dosyada yok. Kodda "Snegirev 2022" yazıyor;
    yıl ve dergi bu dosyadan doğrulanamadı.
- **Irace ve ark. (2021) ölçümü, 1140 K:** *Combust. Flame* 229:111373 (**doğrulandı**). Makalenin s. 8'inde, alev 3
  (etilen) için: ölçülen sönme sıcaklığı 1140 K, benzetimde 1135 K.
- **H₂, 1070 K:** Lecoustre, Sunderland, Chao & Axelbaum, "Modeled quenching limits of spherical hydrogen diffusion flames"
  (**doğrulandı**).
  - **Künye düzeltmesi:** *Proc. Combust. Inst.* 34 (**2013**) 887–894. Kodda 2012 yazıyor; 2012 çevrimiçi yayın yılı.
  - Değer s. 893'te, Sonuçlar 3. madde. 1070 K, normal (yakıt içeride) alevlerin sönme sınırındaki en düşük tepe sıcaklığı.
    Ters alevlerde bu değer 903 K.
- **Etan:** propanın değeri (1200 K) kullanılıyor. Bu kodun kendi varsayımı, kaynağı yok.

**µg jet uzaması (%28):** Cao, Ma, Bennett ve ark., "A computational and experimental study of coflow laminar
methane/air diffusion flames: effects of fuel dilution, inlet velocity, and gravity", *Proc. Combust. Inst.* 35
(**doğrulandı**).
- Klasördeki kopya baskı öncesi (`10.1016_j.proci.2014.05.138`); dergi sayfa numarası dosyada yok.
- PDF s. 4, Şekil 4 tartışması: kaldırmasız alevler 1 g'dekinden ortalama %22 (hesap) ve %28 (ölçüm) daha uzun.
  Kod ölçülen değeri (%28) kullanıyor.
- Bu sonuç metan/hava eş akışlı alevlerinden; kod onu tüm yakıtların jetlerine uyguluyor.

Gaz özellikleri `gaz_ozellikleri.json` tablosundan okunuyor (Cantera ön hesabı: h, c_p, μ, λ, D).
Karışım kuralları damla motoruyla aynı (Wilke; Mathur–Tondon–Saxena).

### 2.1 Termokimya, `termokimya`

```
ν    = Σ_yakıt Y_F,i (n_C + n_H/4) · 31,998 / M_i            kg O2 / kg yakıt akımı
Z_st = 1 / (1 + ν / Y_O2,∞)                                  stokiyometrik karışım kesri
Y_st = Z_st Y_F + (1 − Z_st) Y_O                             stokiyometrik karışım
Y_p  = Y_st içindeki yakıt ve O2 → CO2 + H2O (inertler aynen) ürün bileşimi
Δh   = [h(Y_st, T∞) − h(Y_p, T∞)] / Z_st                      yakıt akımının kg'ı başına ısı
T_tam: h(Y_p, T_tam) = h(Y_st, T∞)                           tam yanma adyabatik sıcaklığı (40 adım ikiye bölme)
T_ad = T_tam − ΔT_ayr
ΔT_ayr = (a0 + a1 log10(p/P0)) · x² / (1 + b0 x),   x = max(T_tam − T1, 0)
```
| sembol | değer | kaynak |
|---|---|---|
| T1 | 1740 K | Cantera HP dengesine uydurma (3920 nokta; ortalama mutlak hata 15,9 K, en çok 95 K) |
| a0 | 4,415·10⁻⁴ | aynı |
| a1 | −9,813·10⁻⁵ | aynı |
| b0 | 4,238·10⁻⁴ | aynı |

S_L hesabı için referans sıcaklık T_ref ayrıca hesaplanıyor: aynı yakıt saf halde, havada, 1 atm'de T_ad.

### 2.2 Ortam taşınım özellikleri ve alev boyutu (kayıpsız)

```
ρD   = ρ∞ D_O2(298 K, p) · (T_ch / 298)^0,5,   T_ch = (298 + T_ad)/2
L_z  = ln[ 1 / (1 − Z_st) ]
Küre:      R₀ = ṁ / (4π ρD L_z)                       (Irace ve ark. 2021, Eş. 8–9; aşağıya bakın)
Düz (BRE): R₀ = R_h = ṁ / (2π ρD L_z)                 yarım küre eşdeğeri
           R_s,eş = 2 R_b / π                         disk iletkenliği 4λR_b = yarım küre 2πλR_s (Carslaw & Jaeger 1959)
Jet:       L_R0 = (ṁ / ρ_F) / (4π D∞ ln(1 + 1/S))     Roper (1977) *Combust. Flame* 29:219
           S = (Σ X_F,i (n_C + n_H/4)) / X_O2,∞      stokiyometrik oksitleyici/yakıt mol oranı
```
D_O2 karışım içinde Blanc/Wilke kuralıyla bulunuyor; saf O₂ ortamında öz-difüzyon kullanılıyor.

**Irace ve ark. (2021)**, *Combust. Flame* 229:111373 (**doğrulandı**):
- **Eş. (8), s. 6:** alev **çapı** d = ṁ / (2π ρD ln[1/(1 − Z_st)]). Kodun R₀ = ṁ/(4π ρD L_z) formülü bunun yarıçap hali; tutarlı.
- **Eş. (9), s. 6:** ρD = ρ₀D₀ (T_ch/298 K)^(1/2), T_ch = (298 K + T_ad)/2. Kodla aynı.
- **Fark:** Irace ρ₀ için N₂ yoğunluğunu (1146 g/m³), D₀ için O₂'nin N₂ içindeki difüzyonunu (20,4 mm²/s) alıyor. Kod ise
  gerçek ortam karışımının ρ·D_O2 değerini kullanıyor. Ortam N₂ değilse (He, CO₂) ikisi farklı sonuç verir.

### 2.3 Enerji dengesi: kayıplı alev sıcaklığı T_f (32 adım ikiye bölme)

```
f(T_f) = T_f − T∞ − (T_ad − T∞) (1 − χ_r(T_f) − χ_s(T_f)) = 0
```
Her denenen T_f için `kayiplar(T_f)` şunları hesaplar:

**a) Kaldırma düzeltmesi (küre ve düz; jette Nu/2 = 1):**
```
Gr   = g (T_f − T∞)/T∞ · (2R_b)³ / ν_k² · r_g⁴           R_b: küre R₀, düz R_s,eş + k_v R₀
Nu/2 = 1 + 0,3 Pr^(1/3) Gr^(1/4)                         Ranz & Marshall (1952); Faeth (1977)
R    = küre: max(R_b / (Nu/2), 1,02 R_s,eş)
       düz:  R_s,eş + (R_b − R_s,eş) / (Nu/2)
```
r_g, damla motorundaki rampanın aynısı (10⁻⁴–10⁻² g₀ arası log-doğrusal). Film özellikleri: ortam ile ürünlerin ortalama
bileşiminde, (T_f+T∞)/2'de.

**b) Jet alev boyu:**
```
L_R = L_R0 · (T∞ / T_ad)^0,67                            Roper (1977)
Ri  = g L_R (T_f − T∞)/T∞ / U²,   w = r_g Ri / (1 + Ri)
L_f = L_R (1 + 0,28 (1 − w))                             µg'de %28 uzama (Cao ve ark. 2014)
```

**c) Alev hacmi ve yüzeyi:**
- **Küre:** V = 4/3 π (R³ − R_s³), A = 4πR².
- **Düz:** yarım küre. V = 2/3 π R³, A = 3πR² (kubbe + taban).
- **Jet:** uzamış sferoit. V = π L_f w_f²/6 ve w_f = L_f/3. Yüzeyi Knud Thomsen yaklaşığıyla hesaplanıyor (±%1).

**d) Işınım kaybı (gaz ışınımı + geri emme):**
```
κ_P   = (p/P0) (X_CO2 a_CO2(T_f) + X_H2O a_H2O(T_f))           ürün bileşiminde; ortam için de aynı formül
Q_ince = C_rad · 4σ κ_P,alev (T_f⁴ − T∞⁴) V
L_m   = 3,6 V / A                                               Hottel ortalama ışın yolu
τ     = (κ_P,alev + κ_P,ortam) L_m
Q_rad = Q_ince · (1 − e^(−τ)) / τ
χ_r   = Q_rad / (ṁ Δh)
```
| sembol | anlamı | değer | kaynak |
|---|---|---|---|
| C_rad | ışınım çarpanı | **e^0,383 = 1,47** | BRE (59 ISS testi) ile kalibre |
| a_CO2, a_H2O | Planck ortalama soğurma | damla motoruyla aynı polinom | Barlow ve ark., TNF/RADCAL |
| L_m ≈ 3,6 V/A | ortalama ışın yolu | — | Hottel & Sarofim (1967); Modest (2013) *Radiative Heat Transfer* 3. bs. §10.6 |
| f(τ) | gri, izotermal hacim için geri emme | — | Modest (2013); Siegel & Howell (**doğrulanamadı**: kitaplar klasörlerde yok; §10.6 kod notundan) |

Kodun varsayılanı `GAZ_IS_MODELI = "0"`: is (kurum) ışınımı yok, yalnız C_rad çarpanı var.
Ortamın soğurma katsayısı kodda T_f'de hesaplanıyor (T∞'da değil). Bu kodun bir varsayımı.

**e) Kaynağa geri iletim kaybı (küre ve düz; jette 0):**
```
Pe  = ṁ c_p,iç / (Ω λ_iç) · (1/R_s,eş − 1/R)          Ω = 4π küre, 2π düz
Q_s = k_s · ṁ c_p,iç (T_f − T_s) / (e^Pe − 1)
χ_s = Q_s / (ṁ Δh)
```
| sembol | anlamı | değer | kaynak |
|---|---|---|---|
| k_s | geri iletim çarpanı | **e^(−0,372) = 0,689** | BRE ile kalibre |
| T_s | kaynak (brülör) yüzey sıcaklığı | 300 K (girdi) | — |
| c_p,iç, λ_iç | yakıt akımı ile ürünlerin ortalama bileşiminde, (T_s+T_f)/2'de | — | Stefan akışlı küresel iletim; Law (2006) damla kuramı (**doğrulanamadı**: kitap klasörlerde yok) |

Debi küçüldükçe alev kaynağa yaklaşır, χ_s büyür ve düşük debide alev söner.

### 2.4 Gerinim ve Damköhler ölçütü

```
Küre: a = ṁ / (2π ρ_f R³)
Düz:  a = ṁ / (π ρ_f R³)
Jet:  a = 2U / L_f
+ kaldırma: a_b = r_g √( g (T_f − T∞)/T∞ / ℓ ),   ℓ = jet: L_f ; küre/düz: max(R, r_g L_R)     (Roper 1977)

S_L(T) = S_L,ref · exp[ −T_a/2 (1/T − 1/T_ref) ] · (p/P0)^(−0,4)                    Zeldovich; Law (2006)
ln Da  = ln( S_L(T_f)² / (α_hava a) ) − ln Da_q
ln Da_q = ln( S_L,CH4² / (α_hava,298K,1atm · 380) )                                  Puri & Seshadri (1986)
α_hava = havanın ısıl yayınımı, 298 K, ve p'ye göre ölçekli (P0/p)
```
α_hava için gerçek karışım değil havanınki kullanılıyor. Sebebi: S_L,ref de yakıt-hava değeri. Helyum gibi yayınımı yüksek
seyrelticilerde gerçek α kullanılsaydı kimyasal zaman yapay olarak büyürdü.

### 2.5 Sonuç

```
marj = min( ln Da , (T_f − T_kr) / 100 K )
Jet:   ln Da_taban = ln Da(T_ad, a = U / (K_taban · 2R_s))
       kopma = ln Da_taban < 0
       marj = min( marj , ln Da_taban + ln 5 )
yanma = σ( marj / s )
```
| sembol | anlamı | değer | kaynak |
|---|---|---|---|
| s | yanma olasılığının yumuşaklığı | **0,559** | BRE ile kalibre |

Diğer çıktılar:
- **Sönme türü:** yanma < 0,5 ise ışınım kaybı sıfırlanarak (χ_r = 0) marj yeniden hesaplanır. Marj > 0 çıkarsa sönme
  "ışınım", değilse "kimyasal" sayılır.
- **Düz brülöre ısı akısı:** q″ = Q_s / (π R_b²).
  - Kaynak: Dehghani, Sunderland, Quintiere & deRis, "Burning in microgravity: experimental results and analysis",
    *Combust. Flame* 228 (2021) 315–330 (**doğrulandı**).
  - Bu akıdan emüle edilen gazlaşma ısısı Eş. (21), s. 326'da:
    L = (q″_taşınım + q″_alev,ışınım − q″_yeniden ışınım) / ṁ″.
  - **Fark:** Dehghani'nin q″'su alevin ışınımını da içeriyor. Kodun q″'su yalnız kaynağa geri iletimden (Q_s) geliyor;
    ikisi bire bir aynı büyüklük değil.
  - Kalibrasyonda kullanılan BRE verisi aynı makalenin Tablo 2'sinde, s. 321.
- **Düz alev boyu:** y_f = k_y R₀ / (Nu/2), k_y = **0,687**.
- **Düz hacim-eşdeğer yarıçap:** R_eff = R_s,eş + k_v R₀, k_v = **0,357**. Snegirev şekli: V = 2/3 π r_f² y_f.
  - Snegirev el yazmasında (`W4309552902`) etkin yarıçapın hacim eşdeğeri olarak tanımı s. 12'de, Eş. (28)–(30)
    civarında. Formüllerin OCR'ı okunamıyor, bu yüzden **denklem numarası doğrulanamadı**. Yalnız tanım metni doğrulandı.
  k_v ve k_y BRE alev boyutu ölçümlerinden bulunuyor (etiket kullanılmadan).
- **En az oksijen:** damla motorundaki gibi O₂ %1–60 arasında 0,25'lik adımlarla taranır.

### 2.6 Kalibrasyon özeti

- **Veri:** 59 ISS BRE (etilen) testi (`gaz_veri/bre_dehghani2021_tablo2.csv`, Dehghani ve ark. 2021, Tablo 2).
- **Kalibre parametreler:** ln_Crad, ln_ks, s (+ geometri: k_v, k_y). Kayıp 58,4.
- **Literatür değerinde sabit tutulanlar:** T_kr, S_L,ref, T_a, a_q. Bunlar BRE verisinden belirlenemiyor.
- **Kalibre değil:** jet (SLICE), etilen dışındaki yakıtlar, 1 g. Bunlar yalnız literatür noktalarıyla ayrıca sınandı.
- **Dürüst test AUC:** düz brülör 0,946, jet 0,816. Jet kalibre olmadığı için sistemde ağırlığı 0.

---

## 3. Kodun açıklama listesindeki (docstring) yanlış ve eksikler

Liste: `damla_motoru.py` ve `gaz_motoru.py` dosyalarının başındaki "HIZLI MOD" ve "FİZİK" açıklamaları.
Kod değiştirilmedi. Doğrusu yukarıdaki bölümlerde yazılı.

### damla_motoru.py

| # | Listede yazan | Kodda gerçekte olan | Tür |
|---|---|---|---|
| 1 | `r_f = FSR r_s^(1-β) r_0^β` | `r_f = e^(ln_fsr) · FSR · r_s^(1−β) r₀^β / (Nu/2)`. Kalibre çarpan 0,408 listede yok (Aşama 2e'de eklendi) | **eksik, önemli** |
| 2 | `yanma = σ(min ln Da / s)` | `yanma = σ(min marj / s)`, `marj = min(ln Da, (T_f − 1200)/100)`. Sıcaklık ölçütü de olasılığa giriyor | **yanlış** |
| 3 | Damköhler'den sönme anlatılıyor | Kimyasal sönme pratikte devre dışı; ln Da birimleri tutarlı değil (Bölüm 4) | **eksik, önemli** |
| 4 | `Nu/2 = 1 + 0.3 Pr^(1/3) (Re² + Gr)^(1/4)`, "Gr terimi log rampa ile açılır" | Rampa Gr'yi r(g)⁴ ile çarpıyor (yani Gr^(1/4) terimi r ile ölçekleniyor). 0,3 ve 1/4 artık parametre (c_tasinim, n_tasinim), değerleri aynı | küçük düzeltme |
| 5 | B formülü saf yakıtla | Alkollerde su emme var: ısı ve O₂ ihtiyacı (1 − Y_wl) ile, L yakıt+su karışımı, yüzey dengesi Raoult. Su emme (k_w = 0,0487, kalibre) listede hiç yok | **eksik, önemli** |
| 6 | "T_f ... 2000 K üstünde yumuşak tavan" | Tavan: 2000 + a/(1 + a/700), en çok ~2700 K. Bu kodun kendi mühendislik formülü, kaynaklı değil | küçük düzeltme |
| 7 | χ_R = Q_rad/(ṁ Q) | `χ_R = min(Q_rad / (ṁ Q (1−Y_wl)), 0,97)`; T_f, χ ve Y_wl 8 turda yarı yarıya güncellenerek çözülüyor | küçük düzeltme |
| 8 | (yok) | Ortalama K, sönmeye kadar d² eğrisi boyunca alınıyor; sönme çapı ızgara noktaları arasında ara değerle | eksik |
| 9 | (yok) | Soğuk alev kuralı, sönme türü, en az oksijen taraması | eksik (çıktılar) |
| 10 | Q_rad: X_CO2, X_H2O "alevde" | Alev bileşimi stokiyometrik ürün + inert (yerel profil değil) | açıklama |
| 11 | "Kısmi g... 1 g'de sınandı" | 1 g testi 65 → 96 noktaya genişledi; AUC 0,60–0,61 | sayı güncel değil (`motor_kontrol` uyarısı güncel) |

### gaz_motoru.py

| # | Listede yazan | Kodda gerçekte olan | Tür |
|---|---|---|---|
| 1 | χ_s tüm geometriler için | Jette Q_s = 0 (kaynağa geri iletim yok) | eksik |
| 2 | S_L(T) ... T_ref | T_ref = aynı yakıtın saf halde havada, 1 atm'deki T_ad'si (ayrıca hesaplanıyor) | eksik |
| 3 | Jet üflenme | Kopmuş alev ln Da_taban < −ln 5 iken üfleniyor (K_üflenme = 5, VARSAYIM) | eksik |
| 4 | Geri emmede ortam κ_P | Kodda ortamın κ_P'si T_f'de hesaplanıyor | açıklama (varsayım) |
| 5 | L_f = Q_F (T∞/T_F)/(...) | Yakıt 298 K'de verildiği için T∞/T_F = 1; Q_F = ṁ/ρ_F (298 K, p) | açıklama |
| 6 | Küre R_f = ṁ/(4πρD ln[1/(1−Z_st)]) | Kaldırmada R = max(R_f/(Nu/2), 1,02 R_s) (alev kaynağın içine giremez) | eksik |
| 7 | Kalibre sayılar: "ln_Crad, ln_ks, s (+ k_v, k_y)" | Doğru. fv_ppm (is) parametresi var ama varsayılan modelde 0'a sabit | açıklama |

Kodun başındaki listelerde başka bir çelişki bulmadım. Formüller, sabitler ve kaynak adları kodla uyumlu.

---

## 4. Bilinen sınırlar

### 4.1 Damla motoru: ln Da birim tutarsızlığı, kimyasal sönme pratikte devre dışı

1.4'teki Damköhler ifadesi:
```
ln Da = ln(r_f² / α_f) + ln A + (a + b − 1) ln ρ_f + b ln Y_O∞ − T_a / T_f
```
**Birim sorunu:**
- A, Westbrook & Dryer (1981) Tablo 2'den aynen alınıyor. Bu değer **cgs ve mol tabanlı**: derişim mol/cm³, süre s.
- Formüldeki ρ_f ise **SI kütle yoğunluğu** (kg/m³). Y_O∞ de mol derişimi değil, kütle kesri.
- Bu yüzden ifadede gerçek tepkime hızı yok: yakıt ve O₂'nin mol derişimleri (ρY/M) ve cm³ → m³ dönüşümü eksik.
- Sonuç olarak ln Da'ya yakıta, basınca ve sıcaklığa bağlı, hesabı yapılmamış bir sabit karışıyor.
  ln Da'nın mutlak değeri fiziksel bir Damköhler sayısı olarak yorumlanamaz.

**Pratik etkisi.** FLEX'in 261 testinde hızlı mod, parametre dosyasındaki değerlerle çalıştırıldı (yalnız okuma; kod değişmedi):

| ölçüt | sonuç |
|---|---|
| sönme anında devrede olan ölçüt | **261 testin 261'inde T_f < 1200 K** |
| sönme anında ln Da < 0 olan test | **0** |
| sönme anındaki en küçük ln Da | 3,0 |
| ln Da < 0'a hiç düşen test | 118; hepsinde alev, ln Da düşmeden önce 1200 K'nin altına inmiş |
| 2 mm n-heptan, hava, ilk çapta | ln Da ≈ 14 |

Yani bu motorda sönmeyi her zaman alev sıcaklığı ölçütü (ışınım soğuması, T_f < 1200 K) belirliyor.
**Kimyasal sönme (Damköhler) ölçütü pratikte devre dışı.**

- **Kalibrasyonla uyumu:** Aşama 2c'de ln A ve T_a'nın kayıp profili tamamen düz çıkmıştı. Veriden belirlenemediği için
  Westbrook & Dryer değerine sabitlendi.
- **Doğrulanmamış rejim:** kimyasal sönmenin gerçekten önemli olduğu durumlar bu motorda doğru temsil edilmiyor olabilir.
  Örnek: çok küçük damlalarda kısa kalış süresiyle sönme, yüksek basınç, güçlü zorlanmış akış ile üfleme.
- **Olası hata yönü:** bu durumlarda alev sıcaklığı 1200 K'nin üstündeyse motor "yanar" der. Yani gerçekte olan bir
  kimyasal sönmeyi kaçırabilir; hata güvensiz yöne değil, "yanar" yönüne kayar.
- **Düzeltme yolu (yapılmadı):** derişimleri mol/m³'e, A'yı SI birimine çevirmek, ardından kritik Da değerini veriden
  kalibre etmek. Bu, FLEX dürüst testinin yeniden koşulmasını gerektirir. Bu görevde kod değiştirilmediği için uygulanmadı.

### 4.2 Diğer bilinen sınırlar (özet)

- **Damla, kısmi g ve zorlanmış akış:**
  - Kısmi g için deney verisi yok.
  - Zorlanmış akış düzeltmesi doğrulanamadı.
  - 1 g'de AUC 0,60.
- **Damla, kalibre edilmemiş yakıtlar:** etanol, n-dekan ve 1-propanol kalibre değil. Etanol ve n-dekanın verisi tek
  sınıflı (hepsi "yanar").
- **Gaz motoru, kalibre olmayan kısımlar:**
  - Jet, etilen dışındaki yakıtlar ve 1 g kalibre değil.
  - Jet tabanı ve üflenme katsayıları (K_taban = 10, K_üflenme = 5) varsayım.
- **İki motorda da ışınım:**
  - Yalnız gaz ışınımı (CO₂/H₂O, optik ince + gri düzeltme) var; is ışınımı yok.
  - Gaz motorunda C_rad = 1,47 kalibre değer, optik ince üst sınırın üstünde. Eksik is ışınımının etkisini de emiyor
    olabilir; bu bir yorum, doğrulanmadı.

---

## 5. Parametre özeti (sistemde kullanılan değerler)

| motor | parametre | değer | kalibre mi? |
|---|---|---|---|
| damla | C_rad | 0,30 | hayır (sabit) |
| damla | β | 1,278 | evet (FLEX) |
| damla | kz | 0,774 | evet |
| damla | s | 2,515 | evet |
| damla | k_w | 0,0487 kg/(m²·s) | evet |
| damla | e^(ln_fsr) | 0,408 | evet (FLEX alev çapı) |
| damla | T_a | 15 098 K | hayır (Westbrook & Dryer) |
| damla | ln A düzeltmesi | 0 | hayır |
| damla | c, n (taşınım) | 0,3; 0,25 | hayır (Ranz & Marshall) |
| gaz | C_rad | 1,47 | evet (BRE) |
| gaz | k_s | 0,689 | evet |
| gaz | s | 0,559 | evet |
| gaz | k_v, k_y | 0,357; 0,687 | evet (BRE alev boyutu) |
| gaz | T_kr, S_L,ref, T_a, a_q | yukarıdaki tablolar | hayır (literatür) |

Kaynak dosyalar: `damla_motoru_parametreleri.json` ("hizli" anahtarı, "bootstrap") ve `gaz_motoru_parametreleri.json`.

---

## 6. Kaynak dosyaları (doğrulama taraması, 2026-11-12)

| kaynak | sonuç | dosya |
|---|---|---|
| Spalding (1953), 4th Symp. 847–864 | doğrulandı: §3.3 s. 853, §4 s. 854 | `/mnt/ssd/nasaspaceapp/pdfler/10.1016_s0082-0784_53_80110-4.pdf` |
| Godsave (1953), 4th Symp. 818–830 | doğrulandı: Eş. (15) s. 823, Tablo 1 s. 825 | `/mnt/ssd/nasaspaceapp/pdfler/10.1016_s0082-0784_53_80107-4.pdf` |
| Irace ve ark. (2021), Combust. Flame 229:111373 | doğrulandı: Eş. (8)–(9) s. 6, 1140 K s. 8 | `metinler/10.1016_j.combustflame.2021.02.019.txt` |
| Snegirev, "On radiative extinction of microgravity diffusion flames" (el yazması) | doğrulandı: T_kr s. 1 ve s. 9. Eşdeğer yarıçap tanımı s. 12; denklem numarası doğrulanamadı | `metinler/W4309552902.txt` |
| Lecoustre ve ark., Proc. Combust. Inst. 34 (2013) 887–894 | doğrulandı: 1070 K s. 893; künye yılı düzeltildi | `metinler/10.1016_j.proci.2012.07.029.txt` |
| Cao ve ark., Proc. Combust. Inst. 35 (baskı öncesi) | doğrulandı: %22 / %28, PDF s. 4 | `metinler/10.1016_j.proci.2014.05.138.txt` |
| Dehghani ve ark. (2021), Combust. Flame 228:315–330 | doğrulandı: Eş. (21) s. 326, Tablo 2 s. 321 | `metinler/10.1016_j.combustflame.2021.01.035.txt` |
| NIST WebBook, Yaws (2003), Perry's | doğrulanamadı (klasörde yok) | — |
| Mathur, Tondon & Saxena (1967) | doğrulanamadı | — |
| Watson (1943) | doğrulanamadı | — |
| Law & Law (1977) | doğrulanamadı | — |
| Marchese & Dryer (1996); Dryer ve ark. (2014) | doğrulanamadı (yalnız ilgili bir NASA-CR var: `metinler/19970003276.txt`) | — |
| Law (2006), Turns (2012), Modest (2013), Siegel & Howell | doğrulanamadı (kitaplar klasörde yok) | — |

`metinler/` = `/mnt/ssd/nasaspaceapp/metinler/`. Westbrook & Dryer (1981), Ranz & Marshall (1952), Faeth (1977),
Roper (1977), Puri & Seshadri (1986), Wilke (1950) bu taramanın kapsamında değildi: bunlar için belgede zaten
"sayfa doğrulanmadı" notu yoktu. Roper (1977) klasörde var (`metinler/10.1016_0010-2180_77_90112-2.txt`, Combust.
Flame 29:219–226), ama formüllerin OCR'ı okunamadığı için denklem numarası kontrol edilemedi.
