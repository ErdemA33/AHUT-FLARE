# Gaz motoru — veri envanteri (2026-11-12)

## 0) Yerleştirme (~/Downloads'tan KOPYA; md5 aynı)

| Dosya | İçerik (başlıklardan ve makalelerden doğrulandı) | Kopyalandığı yer |
|---|---|---|
| PSI-23_Experimental table_ACME s-Flame.csv | ACME **s-Flame** (Law/Tse; küresel gözenekli brülör): gün, atmosfer, yakıt şişesi, tutuşan alev sayısı | `PSI_SFLAME/` |
| PSI-10_Experimental table_Flame Design_Normal Flame.csv | ACME **Flame Design** (Axelbaum/Sunderland; 6.4 mm gözenekli küre, normal alev): test başına debi, O2, p, Z_st, T_ad | `PSI_SFLAME/` (aynı küresel brülör ailesi; ayrı deney) |
| PSI-20_Experimental table_ACME BRE.csv | ACME **BRE** (Quintiere/Sunderland; 25/50 mm düz brülör): gün, brülör çapı, yakıt şişesi, tutuşan alevlerin O2 değerleri | `PSI_BRE/` |
| PSI-21_Experimental table_CLD Flame.csv | ACME **CLD Flame** (Long/Smooke; eş-akışlı jet, 2.1 mm iç boru, hava): yakıt derişim aralığı, tutuşma sayısı | `gaz_veri/` (SLICE değil) |
| PSI-22_Experimental table_ACME E-FIELD Flames.csv | ACME **E-FIELD** (Dunn-Rankin; eş-akış + gaz jeti, hava 21/79, elektrot): derişim, polarite | `gaz_veri/` (SLICE değil) |

**SLICE tablosu ~/Downloads'ta ve diskte yok** → `PSI_SLICE/` boş. SLICE makaleleri (Cao 2014 PROCI 35;
Giassi 2016 CNF; Ma 2014 PROCI 35) yalnız şekil + oran veriyor (µg alevleri 1 g'dekinden ~%28 uzun; L_f ∝ ṁ).

Makalelerden çıkarılan tablolar (`gaz_veri/`, kaynak: `gaz_veri/KAYNAK.md`):
- `bre_dehghani2021_tablo2.csv` — Dehghani ve ark. 2021 CNF 228:315, **Tablo 2: 59 ISS BRE testi** (29 FT, 30 SE)
- `flame_design_irace2021.csv` — Irace ve ark. 2021 CNF 229:111373, Tablo 1-2 (4 uzun süreli küre alevi)

Sütun yorumları makaleden (tahmin yok): X_f = brülör gazında C2H4 mol oranı (gerisi N2); m'' = yakıt karışımı
kütle akısı (25 mm yüzey); q''_ctr / q''_off = r=0 / 9.5 mm sensörleri; q''_cal = kalorimetre (makale: kenar
tasarım hatası, belirsiz); X_r = radyometreden ışınım oranı; FT = akış kesildi (kararlı), SE = kendiliğinden söndü.
PSI özetlerindeki "N3, N4.." / "CH5.." / "C2H5.." hücreleri elektronik tablo otomatik doldurma artığı (aynı
satırdaki deney türü "nitrogen-diluted", bir üst satır CH4/C2H4) -> N2 / CH4 / C2H4 okundu; "3400%" = 34.

## 1) Her deneyde ne ölçülmüş

| Deney | Yakıt | Oksidan / seyreltici | Basınç | Akış | Alev boyutu | Sıcaklık | Sönme |
|---|---|---|---|---|---|---|---|
| BRE (Dehghani T2) | C2H4, %50 C2H4/N2 | O2/N2, X_O2 0.18-0.40 | 0.56-1.04 bar | m'' 1.0-12.1 g/m²s | y_f, r_f (mm) | — (q'', X_r) | **FT/SE etiketi**, yanma süresi |
| BRE (PSI-20 özet) | C2H4, %50 C2H4, **CH4**; 25 ve **50 mm** | O2/N2 21-40 % | "değişti, tabloda yok" | yok | yok | yok | yalnız tutuşma sayısı |
| Flame Design (PSI-10) | C2H4 (127), C3H8 (20); X_fuel 0.1-1 | O2/N2, 0.20-0.40 | 0.93-1.04 atm | ṁ_yakıt, ṁ_N2 (mg/s) | yok | T_ad (hesap) | **yok** |
| Flame Design (Irace) | C2H4 ± N2 | O2/N2 0.19-0.39 | 1 bar | mg/s | R_f(t) (şekil), kuramsal R_f | TFP (şekil); sönmede 1140 K | 4 test: 3 yanar, 1 ışınım sönmesi |
| s-Flame (PSI-23) | H2, CH4, H2/CH4, C2H4 | ~21/30 % O2, **N2 veya He** | ~1 atm | yok | yok | yok | yalnız tutuşma sayısı |
| CLD / E-FIELD | CH4, C2H4 (N2 ile 10-100 %) | hava | ~1 atm | MFC üst sınırı / 15-19 cm/s | yok | yok | yalnız tutuşma |

## 2) Veri setindeki gaz noktaları

`veri_temiz.csv`: 6925 gaz satırı (hepsi `gas_jet`; 330'unda sondu_mu, 764'ünde min O2). Etiketli hali
`etiketli_gemma3.csv`: **336 gaz noktası** (risk_modeli'nin kullandığı; görevdeki "~355"e karşılık geliyor):
- kaynak: diğer 322, NASA (NTRS) 14; 111 makale; deney 256, simülasyon 80
- platform: normal_g 195, drop_tower 61, sounding_rocket 15, parabolic 13, shuttle 10, ISS 7, ? 35
- g: µg 141 (yalnız **11 söner**), kısmi 5, 1 g 190 (54 söner); yanan oranı %81
- 263'ü motorla değerlendirilebildi; 73'ü dışarıda (44 yakıt tanınmadı: DME, n-heptan, "hicot", ...;
  29 kimyasal bastırıcı seyreltici: CF3H, CF3Br, Br2, SF6, Fe(CO)5 — motorda kimyasal inhibisyon yok)

## 3) Kalibrasyon / dürüst test ayrımı (uygulanan)

- **Kalibrasyon:** yalnız BRE Dehghani Tablo 2 (59 test, tek etiketli PSI-kalitesinde set). Geometri
  katsayıları (k_v, k_y) yalnız boyut ölçümlerinden (etiket kullanmaz).
- **Dürüst testler:** BRE gün dışarıda (8 kat), X_f / basınç / O2 dışarıda; BRE → küre (Irace 4 etiketli test),
  küre → BRE; PSI-10 T_ad/Z_st; PSI-20 (CH4, 50 mm), PSI-23 (He, H2), CLD/E-FIELD (jet) pozitif-yalnız;
  `etiketli_gemma3` gaz noktaları (literatür kontrolü, kalibrasyona hiç girmez).
