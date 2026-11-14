# Kilitli motor (12.11.2026)

Saffire-III S1 için kilitlenen fizik motoru. Kaynak koşu: `dalga_J4`. Bu tarihten sonra parametre değişmez.

## İçerik
- `MOTOR_KILIT.json`: bütün parametreler, kütüphane md5 (ddea5b2b3f16717807ed823d318c4ac5) ve seçim gerekçesi.
- `motor/kinetik/`: gaz kimyası. `reactions` (2 adımlı CH4 / CO), `chemistryProperties` (Rosenbrock34),
  `reactionProperties` (laminar yanma). Çözücü OpenFOAM 14'ün kendisi.
- `motor/radyasyon/`: ışınım. `radiationProperties` (fvDOM nPhi 4, greyMean, Cf 0.52), `fvModels` (ışınımı açar).
  Çözücü OpenFOAM 14'ün kendisi. Sınır yayıcılıkları vakada: `vaka/0/fluid/G`, `IDefault`.
- `motor/piroliz/`: katı ayrışması (bizim kodumuz).
  - `fvModels` (A1, E1, n1, A2, E2, n2, XL0), `physicalProperties` (SIBAL ρ, Cv, κ).
  - `kaynak/`: `libFlameInFreefallSolid.so` kaynağı. `sibalPyrolysis` (iki adımlı piroliz + T1 enerji düzeltmesi),
    `coupledPyrolysisSpecies`, `coupledPyrolysisVelocity` (piroliz gazını akışkana veren sınır koşulları).
  - Derleme: `motor/piroliz/Allwmake`.
- `vaka/`: Saffire-III S1 vakası (2B, Nl 7 ağı hazır; `0/`, `constant/`, `system/`).
  - Koşu: `vaka/Allrun` (motor dosyalarını `motor/` klasöründen vakaya kopyalar, 4 çekirdek, 10 s).
  - Ağı baştan üretmek: `mesh_olustur.py` → `blockMesh` → `splitMeshRegions -cellZones -overwrite`.

## Ana ayarlar
| Kısım | Değer |
|---|---|
| Çözücü | OpenFOAM 14 `foamMultiRun` (fluid, sibal, tel) |
| Gaz kimyası | 2 adım: CH4 + 1.5 O2 → CO + 2 H2O (A 775116600000000, Ta 24358); CO + 0.5 O2 → CO2 |
| Piroliz gazı | Y_F0 0.3215 (CH4 vekili, kalanı N2) |
| Piroliz | A1 162600000000, E1 161440, n1 1.035; A2 21130000000000, E2 245890, n2 2.357 |
| Buharlaşma ısısı | XL0 753000 J/kg |
| Işınım | fvDOM (nPhi 4), greyMean soğurma, Cf 0.52 |
| Yayıcılık | numune 0.8, tel 0.7, tavan 0.6 |
| Tutucu | numune önü ve arkası 0.058 m kaymasız |
| Ateşleyici | 2.2535 W (model), 7.986 s'de kapanır |
| Ortam | 0.2453 m/s, 99451 Pa, 294.32 K, 0 g |

## Doğruluk (10 s, Saffire-III S1)
| Ölçü | D | δ | σ̃_M |
|---|---|---|---|
| τ 0.37 s, TC8 hariç | 68.9 | 1.08 | 0.33 |
| τ 0, tüm sensörler | 54.7 | 1.39 | 0.68 |
