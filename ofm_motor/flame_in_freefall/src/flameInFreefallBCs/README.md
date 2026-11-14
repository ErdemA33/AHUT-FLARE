# flameInFreefallBCs

Mikrogravitede ince katı kumaştan (SIBAL) alev yayılımı için piroliz sınır
koşulu kütüphanesi. Çözücü **değiştirilmez**; bu bağımsız kütüphane standart
`multicomponentFluid` çözücüsüne vakadan `libs` ile yüklenir.

Hedef: OpenFOAM **14** (Foundation, openfoam.org), native Ubuntu kurulumu.
Kütüphane adı: `libFlameInFreefallBCs.so`.

## Durum

| Adım | İçerik | Durum |
|------|--------|-------|
| 1 | Dosya iskeleti (sınıf tanımları, Make dosyaları) | tamam |
| 2 | Fizik (Arrhenius, `rho_s`, enerji dengesi, Stefan hızı) | **tamam (bu commit)** |
| 3 | Derleme | tamam (libFlameInFreefallBCs.so bağlandı) |
| 4 | Küçük test vakası + `kontrol.py` | tamam (çalıştırma kullanıcıda) |

Adım 2'de üç BC'nin de fiziği yazıldı: ortak başlık (`pyrolysisArrhenius`),
`pyrolysisFuelFraction` (Robin), `pyrolysisTemperature`, `pyrolysisVelocity`.

## Üç sınır koşulu

| BC | Taban sınıf | Görev | rho_s |
|----|-------------|-------|-------|
| `pyrolysisFuelFraction` | `mixedFvPatchScalarField` (Robin) | yakıt (CH4) kütle kesri | **yazar** |
| `pyrolysisTemperature`  | `mixedFvPatchScalarField` | yüzey sıcaklığı | okur |
| `pyrolysisVelocity`     | `fixedValueFvPatchVectorField` | Stefan üfleme hızı | okur |

`rho_s` yazma hakkı yalnızca `pyrolysisFuelFraction`'da; diğer ikisi salt-okur.
Ortak Arrhenius/parametre: `pyrolysisArrhenius.{H,C}` (serbest fonksiyonlar,
ortak taban sınıf yok).

## Adım 2 kararları (onaylandı)

1. **Birim:** `rho_s` dict'te `g/m²` yazılı kalır; `readPyrolysisDict` okuma
   anında ×1e-3 ile `kg/m²`'ye çevirir (tek nokta, `// g/m^2 -> kg/m^2`).
   Kodun geri kalanı SI; `m_dot` böylece `kg/m²/s`.
2. **Stefan hızı:** üçüncü BC `pyrolysisVelocity`, `U = (m_dot/ρ_gaz)·(−nf)`.
3. **Sıcaklık kapanışı:** mixed, `valueFraction=0`, `refGrad=−m_dot·L/k_gaz`.
   Sabit eşik (T_threshold) **kaldırıldı**; Arrhenius düşük T'de kendiliğinden
   ~0 (daha pürüzsüz). `R=8.314` sabiti koda gömülü.
4. **Ortak başlık:** serbest fonksiyonlar (`readPyrolysisDict`, `arrheniusRate`,
   `updateRhoS`).

## Örnek alınan OF14 kaynak dosyaları

OF14 sözdizimi tahmin edilmedi; resmi Foundation kaynağı (dev/master, telif
2011–2026) referans alındı. Yerel karşılıkları (diff için):

- `$FOAM_SRC/finiteVolume/fields/fvPatchFields/basic/mixed/mixedFvPatchField.{H,C}`
- `$FOAM_SRC/finiteVolume/fields/fvPatchFields/derived/inletOutlet/inletOutletFvPatchField.{H,C}`
- `$FOAM_SRC/finiteVolume/fields/fvPatchFields/basic/fixedValue/fixedValueFvPatchField.{H,C}`
- Duvar `kappaEff`/`DEff` erişimi + mixed ısı-akısı kalıbı:
  `$FOAM_SRC/ThermophysicalTransportModels/thermophysicalTransportModel/...`,
  `.../fluid/fluidThermophysicalTransportModel/...`,
  `.../coupledThermophysicalTransportModels/externalTemperature/externalTemperatureFvPatchScalarField.C`
  (OF14: `kappa`/`D` termo nesnesinde değil, transport modelinde;
  `patch().mesh().lookupType<...>()` ile alınır.)

OF14'e özgü noktalar: eşleme ctor `const fieldMapper&`; taban `map/reset`
(autoMap/rmap yok); iF'siz kopya `= delete`; dict okuma
`Field("value", iF.dimensions(), dict, size)`; kayıt `makePatchTypeField`;
küçük değer sabiti `small` (SMALL değil).

## Derlemede doğrulanacak noktalar (adım 3)

Bu ortamda OF14 olmadığından derlenemedi. Compile sırasında bakılacak,
sürüme duyarlı yerler:

- `pyrolysisVelocity`: `rho_gaz` için kayıtlı `"rho"` alanı kullanılıyor;
  multicomponentFluid bu alanı kayıtlı tutar.
- `-nf` yönü: üfleme domain *içine* olmalı; mesh oryantasyonuna göre işareti
  doğrula.
- `Make/options`: include/lib listesi gerçek multicomponentFluid çözücüsünün
  `Make/options`'ından alındı; "undefined reference" gelirse oradan eşle.

## Derleme

```sh
. /opt/openfoam14/etc/bashrc     # kendi OF14 ortam yolun
cd ~/flame-in-freefall
./Allwmake                        # -> $FOAM_USER_LIBBIN/libFlameInFreefallBCs.so
```

`system/controlDict`: `libs ("libFlameInFreefallBCs.so");`

## constant/pyrolysisProperties (adım 4'te vakaya)

```
A            1.626e11;   // 1/s
E            1.6144e5;   // J/mol
n            1.035;      // -
rho_s_ref    24.387;     // g/m^2  (okuma aninda kg/m^2'ye cevrilir)
rho_s_init   136.5;      // g/m^2
L_pyrolysis  3.0e5;      // J/kg
fuelSpecies  CH4;
```

## `pyrolysisFuelFraction` kapanışı (onaylandı: mixed/Robin)

Yüzey yakıt-tür dengesi (dış normal `nf`, piroliz gazı saf yakıt):

    snGrad = alpha*(1 - Y_f),   alpha = m_dot/(rho*D)   [1/m]

OF mixed formuna eşlenmesi:

    refValue      = 1
    refGrad       = 0
    valueFraction = alpha/(alpha + deltaCoeffs)

`m_dot=0` → `valueFraction=0` (saf zeroGradient, yakıt yok); `m_dot` büyürken
`valueFraction→1` (yüzey saf yakıt). `pyrolysisVelocity`'nin konvektif
akısıyla çift sayım yok (BC yalnızca difüzyon ilişkisini kurar, taşınımı
çözücü `phi`/`U` üzerinden hesaplar).

## Test vakası — `vakalar/piroliz_tek_hucre/`

2B kanal (0.10 × 0.02 m), altta 1 cm `sample` yüzeyi, soldan 20 cm/s hava.
`counterFlowFlame2D` tutorial'ı temel alındı (termo/çözüm dosyaları birebir),
kimya kapalı (`constant/reactions` boş) — alev yok, smoke-test.

Yüzey BC'leri: `sample`'da `U→pyrolysisVelocity`, `CH4→pyrolysisFuelFraction`;
`T` ise bilinen 300→700 K lineer rampa (`uniformFixedValue`) ile sürülür ki
`m_dot`'un Arrhenius'a uyumu doğrulanabilsin (bu smoke-test için
`pyrolysisTemperature` yerine rampa; gerçek alev vakasında `pyrolysisTemperature`
kullanılır).

`rho_s` alanı çözücüye ait değil: kütüphane `READ_IF_PRESENT`+`AUTO_WRITE` ile
kaydeder (yoksa `rho_s_init`=0.1365 kg/m² ile başlatır), `calculated` patch ile
değerleri diske yazar.

Çalıştırma + doğrulama:

```sh
cd ~/flame-in-freefall/vakalar/piroliz_tek_hucre
blockMesh
foamRun                 # solver controlDict'ten (multicomponentFluid)
python3 kontrol.py      # sample rho_s'ten olculen m_dot'u Arrhenius ile karsilastirir
```

`kontrol.py` sentetik Arrhenius verisiyle doğrulandı; anlamlı piroliz
bölgesinde (~T≥520 K) sapma %5'in altında, düşük-T aralıkları "ihmal".
