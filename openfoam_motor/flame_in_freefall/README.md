# y: Saffire-III Sample 1 OpenFOAM motoru (taşınabilir paket)

2B OpenFOAM 14 modeli: gaz (multicomponentFluid) + SIBAL katı (piroliz) + Kanthal tel, foamMultiRun ile çok bölgeli.
Kalibrasyon: ml/ (CFD'siz Python: tasarım, özellik çıkarımı, GP vekil, history matching).

## 1. Gereksinimler (yeni bilgisayar)
- Linux (Ubuntu 22.04+ önerilir), en az 4 çekirdek, 16 GB RAM, 15 GB boş disk (her koşu ~1.2 GB).
- OpenFOAM 14 (Foundation). Kurulum: https://openfoam.org/download/14-ubuntu/
  Varsayılan bashrc yolu /opt/openfoam14/etc/bashrc; farklıysa: `export OF_BASHRC=/yol/etc/bashrc`
- Python 3.10+ ve: numpy, scipy, matplotlib, pyyaml, pytest (`pip install numpy scipy matplotlib pyyaml pytest`)

## 2. Özel kütüphaneleri derle (bir kez)
```
bash kur.sh
```
Bu, src/flameInFreefallBCs ve src/flameInFreefallSolid kütüphanelerini `wmake libso` ile derler
(`~/OpenFOAM/<kullanıcı>-14/platforms/.../lib` içine libFlameInFreefallBCs.so ve libFlameInFreefallSolid.so).
Bunlar olmadan piroliz ve yüzey sınır koşulları çalışmaz.

## 3. Testler (CFD yok, ~20 s)
```
cd vakalar/_kalibrasyon && python3 -m pytest ml -q
```
Beklenen: 69 geçer, 6 başarısız. Başarısız 6 test (T4 ×3, T13 ×3) eski koşu sonuçlarını (kosular/sensorlu_hedef02 ve
r2_*, izgara_* vb.) okur; paket bunları içermez. Bu beklenen bir durumdur, motorun hatası değildir.
Tam 75 geçme için o koşu klasörlerini vakalar/_kalibrasyon/kosular/ altına kopyalayın.
(İki güvenlik testi, test_T14 ve test_T3, bir foamMultiRun çalışırken başarısız olur; koşu yokken geçer.)

## 4. Bir vaka koşmak
Güvenlik: CFD, `vakalar/_kalibrasyon/ml/ONAY_CFD` dosyası YOKKEN başlamaz. Başlatmadan önce:
```
touch vakalar/_kalibrasyon/ml/ONAY_CFD
cd vakalar/_kalibrasyon
python3 -c "from ml import tasarim as T, kos_et as K; X=T.faz_a(8,7)[0]; print(K.kos_et('faz_a_01', X[0], 'A', 7.5))"
```
Bu, tasarım noktası 0'ı 7.5 s'lik koşu olarak 4 çekirdekte (mpirun -np 4) başlatır; sonuç kosular/faz_a_01.
İzleme: `bash kosular/faz_a_01/izle.sh` (kosular/ içindeki bir önceki koşudan kopyala; paket örnek içermez, bkz. NOTLAR).
Tek koşu kuralı: aynı anda iki koşu başlatma (ml/KILIT ve foamMultiRun kontrolü engeller).

## 5. Klasör yapısı
- src/: özel OpenFOAM kütüphaneleri (kaynak)
- vakalar/test_uzun_Nl7_Co05/: temel vaka (mesh + ayarlar; 15411 akışkan, 952 katı, 131 tel hücre)
- vakalar/_kalibrasyon/: orkestrator.py (koşu yöneticisi), karsilastir_sensor.py, ml/, notlar (KURALLAR.md, TEKNIK_VERI.md, DEVIR_NOTU.md, SABAH_RAPORU.md)
- veri/islenmis/saffire3_sample1.csv: deney sensör verisi (Saffire-III Sample 1)
- optimizasyon_matched/kapasite/izle.py: termal bekçi (acpitz ≥ 98 °C'de koşuyu iptal eder; sensör yoksa kapat)

## NOTLAR
- Termal bekçi /sys/class/thermal/thermal_zone* içinde "acpitz" arar. Bu bilgisayarda yoksa orkestratör `acpitz()` NaN döner; kontrol edin.
- orkestrator.py ACPI_MAX = 60 °C üstünde 10 dk soğuma bekler; yeni bilgisayarda sensör farklıysa değeri ayarlayın.
- Süre ölçüsü: bizim makinede 1 s simülasyon ≈ 1200–1500 s duvar (4 çekirdek); 7.5 s koşu ≈ 2.5–3 saat.
- Kosu sonuçları (kosular/, sonuclar.json, olay.log) pakete konmadı. Eski koşu verisine bağlı testler (T4, T13, bazı özellik testleri) bu pakette çalışmaz.
