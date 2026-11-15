# TEKNIK_VERI (okuma: `grep -A12 "^## ANAHTAR" TEKNIK_VERI.md`)
Kural: her sayının sonunda kaynak var. Sayılar düz yazılır. Kaynak kısaltmaları: DN = DEVIR_NOTU.md, OL = olay.log, RX = constant/fluid/reactions, RP = constant/fluid/radiationProperties, XLS = ham xlsx, CSV = veri/islenmis/saffire3_sample1.csv.

## PARAM
- R1: CH4^1 + 1.5 O2^1 = CO + 2 H2O. A = 249200000000000, Ta = 24358 K, theta1 = 15.1064 (kilitli, hedef_02, tutuşma 3.686 s). [DN 4, OL, RX]
- R2: CO^1 + 0.5 O2^1 = CO2. A = 50000000000000, Ta = 20100 K, theta2 = 16.654 (kalibre edilmedi). [DN 4, RX; theta2 oturumda hesaplandı: ln(50000000000000) - 20100/1350]
- Parametreleştirme: theta = ln k(1350 K); A = exp(theta) * exp(Ta/1350); orkestrator.py a_hesapla(theta1, Ta), theta1_of(A, Ta), TREF = 1350. [orkestrator.py:103-108]
- Izgara m (A çarpanı) aslında theta1'i Ta0 = 24358'de belirler: A = a_hesapla(theta1_of(m*A0, TA0), Ta), A0 = 4000000000000. [orkestrator2.py:9]
- Reaksiyon mertebeleri: her girenin üssü 1 (katsayı ile aynı değil). [RX:17, RX:25]
- Hız sabiti: k1(1350 K) = 3636000, k2(1350 K) = 17090000 (oturumda hesaplandı).
- Sayısal: maxCo 0.5, maxDeltaT 0.00002 s, 4 çekirdek. [DN 4]

## MODEL_AYAR
- Radyasyon: P1, solverFreq 1, greyMean (CO2, H2O polinomları), saçılma ve is yok. [RP]
- G sınırları (Marshak): giriş/çıkış/üst/taban epsilon 1.0, sibal 0.8, tel 0.7. [0/fluid/G]
- Giriş hızı 0.2453 m/s, tel 183 W, 7.986 s sonra kapanır. Geometri: örnek x = 0.15-1.09 m, tel x = 0.15625 m, akışkan y = 0-0.30 m. [DN 4]

## SENSOR_HARITA
- Model sensörleri (0.02 s aralık, postProcessing altında): fluid/sensGaz/0/T: B (0.47, 0.003), C (0.49, 0.010), E (0.77, 0.008), F (0.79, 0.015). sibal/sensYuzey/0/T: A (0.45, -0.00003), D (0.75, -0.00003). fluid/sensRadMenba/0/G: x = 0.20, 0.30, 0.40, 0.50, 0.60 (y = 0.29). fluid/sensRadAkis/0/G: x = 0.70, 0.80, 0.90, 1.00, 1.05. [DN 9; dosyalarda doğrulandı]
- Deney TC7-TC12 = A-F (çıkarım, Saffire-I şeması, NTRS 20180005168 sl.26): A 30 cm yüzey, B 32 cm 3 mm, C 34 cm 10 mm, D 60 cm yüzey, E 62 cm 8 mm, F 64 cm 15 mm. Model x = deney x + 0.15 m. [DN 6]
- Radyometre vekili = G/4 (W/m2) * 0.1 = mW/cm2 (izotrop üst sınır). R1, R3 ilk yarıyı, R2, R4 ikinci yarıyı görüyor. [DN 6, 9]
- Plume TC1-TC6 ve anemometre konumları bulunamadı; modelde sensörleri yok. [DN 6]

## DENEY_VERI
- Kaynak XLS: tek sayfa "Calibrated Data", 65 sütun, yaklaşık 32600 satır, 0.033 s aralık. CSV: 20910 veri satırı, kolonlar elapsed_time_s, co2_pct, o2_pct, anemometer1/2, pressure_Pa, radiometer1-4_mW_cm2, humidity, inlet_temp_K, plume_temp1-6_K, sample_temp1-6_K, igniter_current_A, igniter_voltage_V. [oturumda okundu]
- Igniter başlangıcı: elapsed 59.994 s (zaman = telemetri). [DN 3]
- Radyometre taban değeri negatif (yaklaşık -17 mW/cm2): eşikler tabana göre. [XLS ilk satırlar]
- CO2 ve O2 yavaş, küresel (0.3947 -> 0.5961 %, 400-700 s); kalibrasyon penceresinde (0-8 s) gürültüde. [XLS özet]

## DENEY_EGRI (igniter başlangıcı = 0)
- R1: +1 3.0 s, +3 3.76 s, +10 5.31 s. R3: 3.07, 3.70, 5.28. R2: 17.52, 24.98, 96.43. R4: 16.37, 25.9, 91.38. Gürültü sd ~0.2 mW/cm2. [DN 6]
- TC9 (C): +5 K 4.19 s, +20 K 4.75 s, +100 K 7.03 s; 6 s'de +69 K; 10 s'de 429.4 K; 20 s'de 463 K. [DN 6]
- Bağımsız kanal başlangıçları (6 sigma): R1/R3 3.1 s, TC9 4.29, TC12 5.71, TC8 6.76, TC7 8.45, plume TC3 6.4, TC4 6.8, TC2 7.1, TC1 8.3. Hiçbir kanal "gaz tutuştu" demiyor (belirsiz 3.1-5.1 s). [DN 6]

## MODEL_EGRI
- hedef_02 (6 s, ön): TC9 probu +5 K 3.54 s, +20 K 5.08 s, +100 K 5.59 s, 5.8 s'de +121 K. Radyometre vekili +1 1.0 s, +3 2.5 s, +10 3.9 s. Gaz maks T alevde ~2206 K. [DN 7]
- Oturumda bakılan fark: TC9 -%15.5, +%6.9, -%20.5; radyometre -%67, -%32, -%26 (model - deney)/deney. [oturum hesabı, DN 7 verisiyle]
- Tutuşma zamanı (gaz T > 1500 K, 6 s ufuk): Ta 24358: m 54.77 -> 4.2084, m 62.3 -> 3.68568, m 64 -> 3.61484, m 75 -> 3.2974, m 100 -> 2.926. Ta 21000: m 55 -> 3.207, m 75 -> 2.766, m 100 -> 2.487. Ta 28012 theta1 14.978: tutuşma yok. [DN 5, OL]
- T_eff modeli: ln k(T_eff) = theta1 - Ta*(1/T_eff - 1/1350); 8 noktaya uyum T_eff = 1170 K (DN: 1195 K), ln t = 0.2468 u^2 - 6.7668 u + 47.2349, en büyük kalan ln t'de 0.0246 (~0.09 s). Aynı t_ign konturu: theta1 = c + 0.000096079*Ta (T_eff 1195). [oturum hesabı]
- R2 taraması (R1 kilitli): (-,-) 4.246 s, (+,+) 3.443, (-,+) tutuşma yok (6 s), (+,-) 3.310; merkez 3.686. [DN 5]

## KOSU
- sensorlu_hedef02: hedef_02 parametreleri, ufuk 8.5 s, tutuşmada durmuyor, sensörlü. Başlangıç 22:51. İzleme: kosular/sensorlu_hedef02/izle.sh. [DN 1, OL]
- sensorlu_hedef02 sonucu: 08.11 01:51'de durum=zaman_asimi, t_son = 7.53486 s (ufuk 8.5 s'ye ulaşmadı; duvar süresi 10812 s ≈ 3 saat sınırı), t_ign = 3.68568 s, T_maks = 2207.88 K. Veri 7.535 s'ye kadar. [OL 01:51:48]

## KARAR
- Kalibrasyon sensör eğrileriyle yapılacak: R1/R3, TC8, TC9 (TC12 gerekirse); doğrulama: R2/R4, TC10-TC12, yayılma hızı 2.3 mm/s. [DN 8]
- Ta2 sabit tutma ve sweep ayrıntısı: analizden sonra karar.
- 5. çekirdek, 20 mikrosaniye sınırını gevşetme yapılmaz. [DN 8]

## ACIK
- Sensörlü koşu analizi (fark türü: kayma / genlik / şekil).
- Plume TC ve anemometre konumları; radyometre vekili güvenilirliği; K3 (250-300 s) maliyeti; Nl 14 / maxCo 0.3 duyarlılığı. [DN 11]
- Disk 11 GB boş (08.11), koşu başına ~1 GB.

## LITERATUR (kaynak PDF'ler yerelde tutuldu, repoya konmadı)
- Cui & Liao 2024, Combust. Flame 261, 113299 (Saffire I ve IV modeli): gaz fazı tek adımlı, ikinci mertebeden toplu Arrhenius, E = 113000 J/mol (Ta = 13592 K), Bg = 1 × 10^13 cm3/g/s; gaz radyasyonu RTE ile, gri yüzey radyasyonu; iki adımlı katı piroliz (Tablo 2): Es1 171.44 kJ/mol (tabloda "J/mol" yazılmış), As1 2.53 × 10^11 1/s, n1 1.035; Es2 245.89, As2 2.11 × 10^13, n2 2.357; latent ısı 300 J/g, TL 300 K; örnek alan yoğunluğu 18.2 mg/cm2, kalınlık 0.03175 cm; akış 20 cm/s. [Numerical-study...pdf satır 150-176, 236-250]
- Doğruluk ölçüsü (aynı makale, Tablo 4): yayılma hızı Saffire I deney 1.81, model 2.12 mm/s (+%17.13); Saffire IV 3.50 / 3.35 (-%6.94); piroliz uzunluğu +%3.90 ve -%5.78. Yazarlar "makul, hata ~%17 içinde" diyor. [satır 262-310]
- Li vd. 2019 (PROCI): yayılma hızı Saffire I 1.81 deney, 2.06 model (+%13.8); Saffire II 2.03 / 1.67 (-%17.7); yanma uzunluğu +%19 / -%15; ısıtma bölgesi Gauss dağılımlı, toplam 145 W civarı. "Within 20%". [li2019.txt satır 247-256]
- Is (soot) radyasyonu: Cui 2024'te toplam enerjinin %5'i, soot radyasyonu %19'a kadar çıkabilir; kırmızı alev gözlenmiş. Bizim modelde is yok (sootModel none). [satır 345-364]
- BIZIM piroliz (constant/sibal/fvModels): A1 162600000000, E1 161440 J/mol, n1 1.035; A2 21130000000000, E2 245890, n2 2.357. Adım 2 aynı; adım 1 Cui 2024 Tablo 2'den FARKLI (A1 2.53 × 10^11, E1 171.44). 600-700 K'de bizim k1 değeri 3.6-4.8 kat büyük (hesap: k = A exp(-E/RT)): 600 K 0.001432 / 0.000300; 700 K 0.145843 / 0.040705. Kaynak (Li & Liao 2018 / Li 2021) ile doğrulanacak. [oturum hesabı]
- ÇÖZÜM (08.11): bizim A1 = 1.626e11 ve E1 = 1.6144e5 kaynağı [S3] Zhao 2017 (SIBAL) (optimizasyon_matched/literatur_araligi.md satır 27-54). Cui 2024 Tablo 2'deki 171.44 kJ/mol ve 2.53e11 farklı bir literatür değeri, yani hata değil literatür yayılımı. Aralık: E1 125-188 kJ/mol (pamuk iplik TGA 153 ± 2, merserize 188), A1 1.0e10-1.626e11. n1 = 1.035 ve n2 = 2.357 kaynağı artık biliniyor: Cui 2024 Tablo 2 (literatur_araligi.md "kaynak bulunamadı" notu güncellenmeli). Tel Ta 13591 K [S7 pamuk buharı, toplam mertebe 2]. par.nsf.gov bu makineden erişilemiyor (bağlantı zaman aşımı), Li & Liao 2018 / Li 2021 metinleri indirilemedi.
- BIZIM gaz fazı: Ta 24358 K = E 202512 J/mol (literatür 113000 J/mol). Birim ve formülasyon farkı var (molar CH4 vekili vs kütle bazlı toplu yakıt); karşılaştırmadan önce anlamı netleştirilecek.
- Vekil model/ML kaynağı: Georgalis vd., arXiv 2411.16693 (2B slab burner DNS: 64 Latin hypercube koşusu, GP vekil, Bayesian kalibrasyon). Bulunacak: SIBAL kinetik tablosu Li & Liao 2018 CST 190 (10.1080/00102202.2018.1489380) ve Combust. Flame 227 (2021) 39-51 (10.1016/j.combustflame.2020.12.042) (arama sonucu, doğrulanmadı).

## OKUMA_SONUCLARI (08.11 gece, CFD'siz)
- Sayisal duyarlilik (mevcut 0.8 s testleri, tel isitma fazi, tutusma YOK; gazProb T, 0.8 s) [olculdu: test_Nl5/test_Nl7/test_maxCo05 postProcessing]: Nl5 ile Nl7 farki tel yakini probelerde 1.96 K (0.00032 m), 20.66 K (0.001 m, T 467.7 / 447.1), 11.78 K (0.0002 m yanal); x = 0.2 m ve otesinde 0.05 K altinda. maxCo 0.3 ile 0.5 farki en fazla 0.14 K. Nl 14 ve maxCo 0.3 uzerinde tutusma zamani/TC varisi icin sayisal hata BILINMIYOR (kosu yok). Yorum (tahmin): tele yakin sensorlerde ag hatasi buyuk olabilir; ag yakinsamasi kanitlanmadi.
- [S10] Milosavljevic-Oja-Suuberg 1996: TAM METIN OKUNAMADI (osti.gov baglanti zaman asimi). Ozet [okundu: OSTI/ACS ozeti, arama]: ana selüloz yolu endotermik, yaklasik 538 J/g ucucu madde basina (esas olarak birincil katranin buharlasma gizli isisi); kömür olusumu ekzotermik, yaklasik 2 kJ/g kömür; DSC + TGA, 0.1-60 K/dak. => PLAN KOSULLU KURALI: XL0 = 300000 J/kg SABIT, "test edilemedi" listesine eklendi (ml/param.py XL0_SERBEST = False). Not: 538 J/g "ucucu basina" selüloz degeri, modelin XL0 tanimiyla (sibalPyrolysis) ayni buyukluk olmayabilir [bilinmiyor].
- Tel emisivitesi: Kanthal A-1 veri sayfasi "fully oxidized" toplam yayma katsayisi 0.70 (kanthal.com A-1 datasheet), sicakliga bagli egri yok [okundu: arama sonucu]. Modeldeki 0.7 bununla tutarli. Aralik (>=2 kaynak) YOK -> kumeye ALINMADI; tek deger. Oksitlenmemis/yeni tel icin daha dusuk olabilir [bilinmiyor: deneyde oksit durumu].
- Gaz sogurmasi: radiationProperties greyMean polinomlarinin kaynagi dogrulanamadi. Arama: OpenFOAM'da Smith-Shen-Friedman 1982 WSGG katsayilari ayri bir WSGGM modeli olarak anilir (arXiv 2207.13149, 2411.18467), greyMean ile esleme gorulmedi. Skaler aralik YOK -> kumeye ALINMADI [bilinmiyor: greyMean katsayi kaynagi OpenFOAM kaynak kodundan okunmali].
- Is (soot) radyasyonu: model sootModel none. Cui 2024: enerjinin %5'i, yerel %19'a kadar [olculdu: Cui 2024 metni]. Thomsen vd. (NTRS 20220012861, PCI 39): Saffire IV SIBAL, iki renkli pirometri, ortalama alev sicakligi ~1300 K, hata < 117 K; gaz ve is radyasyonunun onemli oldugu belirtilmis (arama ozeti; PDF indirildi ama metin cikarilamadi: ham PDF baytlari). Aralik YOK -> kumeye ALINMADI.
- SIBAL TGA kinetigi (Li & Liao 2018 CST 190; Li 2021 CNF 227): par.nsf.gov ve osti.gov bu makineden acilmiyor (baglanti zaman asimi) [olculdu]. Okunamadi.
- CFD yok: pgrep foamMultiRun = 0, ml/ONAY_CFD yok, sensorlu_hedef02 08.11 01:51'de bitti.

## KARAR (08.11 sabah)
- XL0 sabit (300000); serbest parametre 5: u, Ta1, theta_p, E1, eps_sibal. [kullanici karari, planin kosullu kurali]
- Erken radyometre testi dondurulmus tanim ml/karar.py ERKEN_RAD_* (oran 0.25) [tahmin: tasarim secimi, olculmedi].
- Tel eps kumede degil: 0.70 tek deger, kural (1)'e uymuyor; modelle tutarli olmasi tel eps'in yakin sensor farkinin nedeni olmadigini gostermez.
- delta_min listesi: ag hatasi kalemi Nl5-Nl7 = 20.66 K (tele 1 mm yakin, 0.8 s); tutusma zamani icin ag hatasi bilinmiyor.
- Denetci kapisi kullanicida (hook kapatilip calistirilacak); ONAY_CFD denetci bulgularindan sonra kullanici tarafindan olusturulacak.
