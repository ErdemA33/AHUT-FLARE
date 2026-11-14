#!/usr/bin/env python3
"""malzeme_kutuphanesi_uret.py — yerleşik malzeme kütüphanesini (malzeme_kutuphanesi.json) üretir.

    python3 malzeme_kutuphanesi_uret.py            # üret + kaynak denetimi
    python3 malzeme_kutuphanesi_uret.py --denetle  # yalnız denetle, yazma

İlke: ÖZELLİK UYDURULMAZ. Her sayının bir kaynağı vardır; bulunamayan alan boş (null) kalır.
  - NIST Chemistry WebBook (SRD 69): deneyler/malzeme_nist_ham.json (deneyler/malzeme_nist_cek.py ile çekildi);
    seçim kuralı aşağıda (nist_sec), değer değiştirilmez, yalnız birim çevrilir (kJ/mol -> MJ/kg, kJ/kg).
  - SFPE El Kitabı 5. baskı (Hurley ed., Springer 2016, ISBN 978-1-4939-2565-0) — bizim makale klasöründe
    (/mnt/ssd/nasaspaceapp/metinler/): Ek Tablo A.24, A.31, A.32, A.36, A.38, A.39 ve Bölüm 36 Tablo 36.5.
    Elle aktarılan her değer, kaynak metinde malzeme adından sonraki birkaç satırda AYNEN geçiyor mu diye
    denetlenir (denetle()); geçmiyorsa betik durur.
  - damla_motoru.py YAKIT tablosu (sıvı yoğunluğu, kaynamaya yakın sıcaklıkta; NIST/Yaws/Perry's).
  - chemicals (Caleb Bell) kütüphanesi: deneyler/malzeme_chemicals_ham.json (deneyler/malzeme_chemicals_cek.py);
    yalnız BOŞ alanları doldurur, her değerde chemicals'ın alt kaynağı (IEC, NFPA, CRC, Perry's, ATcT ...) yazılır.
  - Veri seti: motor_karsilastirma.csv (bütün etiketli noktalar) — nokta sayıları ad eşleşmesiyle sayılır.
Motor eşlemesi (motor_benzeri) ve varsayılan numune tipi BİZİM SEÇİMİMİZDİR (özellik değil); gerekçesi yazılır.
"uzayda_kullanim" kısa genel bilgidir, ölçüm değildir.
Kütüphane modele ya da motor kalibrasyonuna GİRMEZ; yalnız arayüzde gezinme ve eşleme önerisi içindir.
"""
import argparse
import json
import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
CIKTI = KOK / "malzeme_kutuphanesi.json"
NIST_HAM = KOK / "deneyler" / "malzeme_nist_ham.json"
CHEM_HAM = KOK / "deneyler" / "malzeme_chemicals_ham.json"   # deneyler/malzeme_chemicals_cek.py (dashboard/.venv)
# makale metinleri harici diskte; bağlama noktası oturuma göre değişir (MALZEME_METIN ortam değişkeni önce)
METIN = next((Path(x) for x in (__import__("os").environ.get("MALZEME_METIN"), "/mnt/ssd/nasaspaceapp/metinler",
                                 "/media/user/Extreme Pro/nasaspaceapp/metinler") if x and Path(x).is_dir()),
             Path("/mnt/ssd/nasaspaceapp/metinler"))
SFPE = "10.1007_978-1-4939-2565-0.txt"
SFPE36 = "10.1007_978-1-4939-2565-0_36.txt"
SFPE_AD = "SFPE El Kitabı 5. baskı (2016)"

# Kaynak tanımları: (dosya, başlangıç satırı, bitiş satırı) — tablo bölgesi; atıf metni
TABLO = {
    "A.24": (SFPE, 401786, 401934, f"{SFPE_AD}, Ek Tablo A.24 (sıvıların yaklaşık özellikleri, 1 atm), PDF s. 3447"),
    "A.31": (SFPE, 406164, 406703, f"{SFPE_AD}, Ek Tablo A.31 (plastiklerin yanma ısıları), PDF s. 3464–3466"),
    "A.32": (SFPE, 406704, 406899, f"{SFPE_AD}, Ek Tablo A.32 (çeşitli malzemelerin yanma ısıları), PDF s. 3467"),
    "A.36": (SFPE, 408153, 408878, f"{SFPE_AD}, Ek Tablo A.36 (polimerlerin ısıl özellikleri), PDF s. 3475–3478"),
    "A.37": (SFPE, 408879, 409316, f"{SFPE_AD}, Ek Tablo A.37 (minibüs plastik parçalarının ısıl özellikleri), PDF s. 3477–3478"),
    "A.38": (SFPE, 409317, 410839, f"{SFPE_AD}, Ek Tablo A.38 (net tam yanma ısıları ΔH_T), PDF s. 3479–3484"),
    "A.39": (SFPE, 410840, 413200, f"{SFPE_AD}, Ek Tablo A.39 (iyi havalanan yangın verimleri, ΔH_T), PDF s. 3485–"),
    "36.5": (SFPE36, 2506, 2660, f"{SFPE_AD}, Bölüm 36 (Khan, Tewarson, Chaos) Tablo 36.5 (LOI), s. 1165"),
}


def s(tablo, satir, deger, birim, not_=None, tur=None, ofset=None):
    """SFPE'den elle aktarılan değer: (tablo, kaynak metindeki satır etiketi, metindeki değer).
    ofset: değerin etiketten kaç hücre sonra geldiği (tablonun SUTUN düzeninden farklı satırlar için)."""
    return {"tablo": tablo, "etiket": satir, "metin": deger, "birim": birim, "not": not_, "tur": tur, "ofset": ofset}


# ------------------------------------------------------------------ malzemeler
# alanlar: id, ad, ad_en, es (eş anlamlılar), tur (kati/sivi/gaz), numune, motor_benzeri, eslesme_gerekce,
#          desen (veri setinde ad eşleşmesi, regex), uzay, sfpe {özellik: s(...)}, nist (NIST anahtarı), damla (YAKIT)
M = []


def ekle(**k):
    M.append(k)


# KATI ---------------------------------------------------------------
ekle(id="pmma", ad="PMMA", ad_en="Poly(methyl methacrylate)",
     es=["pleksiglas", "akrilik", "Plexiglas", "Perspex", "acrylic", "polimetil metakrilat"], tur="kati",
     numune="thin_sheet", motor_benzeri="pmma", eslesme_gerekce="kendisi (hafif motor kalibrasyon verisinde)",
     desen=r"pmma|methyl ?methacrylate|methy1 methacrylate|polymethacrylate|polymethyl-methacrylate|poly-methyl",
     uzay="Saffire ve BASS deneylerinde referans numune; pencere ve panel malzemesi",
     sfpe={"isil_deger_net": s("A.38", "Polymethyl-methacrylate", "25.2c", "MJ/kg"),
           "yogunluk": s("A.36", "Polymethylmethacrylate (PMMA)", "378–383 1.19", "10^3 kg/m3", tur="A36"),
           "LOI": s("36.5", "Polymethylmethacrylate (PMMA)", "17", "%")})
ekle(id="polycarbonate", ad="Polikarbonat", ad_en="Polycarbonate",
     es=["PC", "Lexan", "Makrolon", "polikarbonat"], tur="kati", numune="thin_sheet", motor_benzeri="pmma",
     eslesme_gerekce="termoplastik levha; kalibre levha malzemesi PMMA (PC kömürleşir, PMMA kömürleşmez: zayıf eşleme)",
     desen=r"polycarbonate|\bpc\b|lexan", uzay="kask vizörü, pencere ve koruyucu kapaklar (Lexan)",
     sfpe={"isil_deger_net": s("A.38", "Polycarbonate", "29.7c", "MJ/kg"),
           "yogunluk": s("A.36", "Polycarbonate (PC)", "500–580 1.20", "10^3 kg/m3", tur="A36"),
           "LOI": s("36.5", "Polycarbonate (PC)", "26", "%")})
ekle(id="polyethylene", ad="Polietilen", ad_en="Polyethylene",
     es=["PE", "HDPE", "LDPE", "yüksek yoğunluklu polietilen", "alçak yoğunluklu polietilen"], tur="kati",
     numune="thin_sheet", motor_benzeri="pmma", eslesme_gerekce="eriyen termoplastik levha; kalibre levha malzemesi PMMA",
     desen=r"polyethylene|\bhdpe\b|\bldpe\b|^pe$|\bpe-insulated|b-ldpe|ldpe[–-]", uzay="radyasyon kalkanı, torba ve ambalaj; kablo yalıtımı",
     sfpe={"isil_deger_net": s("A.38", "Polyethylene", "43.6", "MJ/kg"),
           "yogunluk": s("A.36", "Polyethylene (PE) high density (HD)", "380–443 0.94–0.96", "10^3 kg/m3",
                         not_="HDPE; LDPE 0,93 (aynı tablo)", tur="A36"),
           "LOI": s("36.5", "Polyethylene (PE)", "18", "%")})
ekle(id="polypropylene", ad="Polipropilen", ad_en="Polypropylene",
     es=["PP", "polipropilen"], tur="kati", numune="thin_sheet", motor_benzeri="pmma",
     eslesme_gerekce="eriyen termoplastik levha; kalibre levha malzemesi PMMA", desen=r"polypropylene|^pp$",
     uzay="kap, kapak ve ambalaj parçaları",
     sfpe={"isil_deger_net": s("A.38", "Polypropylene", "43.4", "MJ/kg"),
           "yogunluk": s("A.37", "Reservoir", "0.90", "10^3 kg/m3",
                         not_="ikinci kaynak: A.37'de üç PP parçası (depo, kapak, kaplama) 0,90. A.36 OCR metninde "
                              "0,96 yazıyor (şüpheli); A.37 kullanıldı")})
ekle(id="nylon", ad="Naylon (poliamid)", ad_en="Nylon (polyamide)",
     es=["poliamid", "PA6", "PA66", "Velcro", "cırt bant", "nylon"], tur="kati", numune="fabric",
     motor_benzeri="cotton", eslesme_gerekce="sentetik kumaş (Velcro); kalibre kumaşlardan havada kolay yanan pamuk (varsayım)",
     desen=r"nylon|polyamide|velcro(?!.*nomex)", uzay="Velcro cırt bantlar (kabinde her yerde), kayış ve torbalar",
     sfpe={"isil_deger_net": s("A.38", "Nylon", "30.8c", "MJ/kg"),
           "yogunluk": s("A.36", "Polyamide (PA, nylon) 6", "432–497 1.13–1.20", "10^3 kg/m3", tur="A36", not_="PA6"),
           "LOI": s("36.5", "Polyamide 6 (PA6)-nylon", "21", "%", not_="PA6")})
ekle(id="nomex", ad="Nomex", ad_en="Nomex (meta-aramid)",
     es=["aramid kumaş", "meta-aramid", "Nomex HT90-40", "poli(m-fenilen izoftalamid)"], tur="kati",
     numune="fabric", motor_benzeri="nomex", eslesme_gerekce="kendisi (hafif motor kalibrasyon verisinde)",
     desen=r"nomex", uzay="mürettebat giysisi, saklama torbaları (CTB), Velcro (Nomex)",
     sfpe={"isil_deger": s("A.32", "Nomex™", "27.0–28.7", "MJ/kg",
                           not_="A.32'de tek değer; brüt/net sütunu OCR metninde ayırt edilemedi")})
ekle(id="kevlar", ad="Kevlar", ad_en="Kevlar (para-aramid)",
     es=["para-aramid", "aramid", "poli(p-fenilen tereftalamid)"], tur="kati", numune="fabric",
     motor_benzeri="nomex", eslesme_gerekce="aramid kumaş (yapay zeka sınıflandırması da nomex dedi; malzeme_onbellek.json)",
     desen=r"kevlar|aramid(?!.*epoxy)|^phenolic/aramid", uzay="mikrometeor/döküntü kalkanı (Whipple), giysi katmanları",
     sfpe={"LOI": s("36.5", "Polyaramide (Kevlar)", "28", "%")})
ekle(id="ptfe", ad="Teflon (PTFE)", ad_en="PTFE (polytetrafluoroethylene)",
     es=["Teflon", "politetrafloroetilen", "PTFE"], tur="kati", numune="thin_sheet", motor_benzeri="silicone",
     eslesme_gerekce="kalibre malzemeler arasında en zor yanan levha; ZAYIF eşleme (PTFE LOI 95: havada yanmaz)",
     desen=r"ptfe|teflon|tetrafluoroethylene(?!.*etfe)", uzay="kablo yalıtımı, conta ve Beta kumaşı kaplaması",
     sfpe={"isil_deger_net": s("A.38", "Teﬂon TFE", "6.2c", "MJ/kg"),
           "yogunluk": s("A.36", "Polytetraﬂuoroethylene (PTFE)", "630–700 2.15–2.18", "10^3 kg/m3", tur="A36"),
           "LOI": s("36.5", "Polytetraﬂuoroethylene (PTFE)", "95", "%")})
ekle(id="kapton", ad="Kapton (poliimid)", ad_en="Kapton (polyimide)",
     es=["poliimid", "polyimide", "PI", "PMDA-ODA"], tur="kati", numune="thin_sheet", motor_benzeri="silicone",
     eslesme_gerekce="zor yanan ince film; ZAYIF eşleme", desen=r"kapton|polyimide|polypromellitimide",
     uzay="çok katmanlı yalıtım (MLI) filmi, esnek devre ve kablo yalıtımı",
     sfpe={"yogunluk": s("A.36", "Polyimide (PI)", "1.40", "10^3 kg/m3", tur="A36", not_="genel poliimid (PI)"),
           "LOI": s("36.5", "Polypromellitimide (PI)", "37", "%", not_="Kapton bir piromellitimiddir")})
ekle(id="peek", ad="PEEK", ad_en="Polyether ether ketone",
     es=["polieter eter keton", "PEEK"], tur="kati", numune="thin_sheet", motor_benzeri="ultem",
     eslesme_gerekce="yüksek sıcaklık termoplastiği; veri setinde PSI noktası olan en yakın polimer Ultem (PEI)",
     desen=r"\bpeek\b|ether ether ketone", uzay="yapısal ve elektrik parçaları, 3B baskı (yüksek sıcaklık)",
     sfpe={"isil_deger_net": s("A.39", "Polyether ether ketone (PEEK-CH0.63O0.16)", "31.3", "MJ/kg", not_="ΔH_T"),
           "yogunluk": s("A.36", "Polyether ether ketone (PEEK)", "570–580 1.31–1.32", "10^3 kg/m3", tur="A36"),
           "LOI": s("36.5", "Polyether ether ketone (PEEK)", "35", "%")})
ekle(id="ultem", ad="Ultem (PEI)", ad_en="Ultem (polyetherimide)",
     es=["polieterimid", "PEI", "Ultem"], tur="kati", numune="thin_sheet", motor_benzeri="ultem",
     eslesme_gerekce="kendisi (veri setinde PSI noktası var)", desen=r"ultem|polyetherimide|\bpei\b",
     uzay="kabin iç parçaları, 3B baskı malzemesi (ISS'te Ultem 9085)",
     sfpe={"isil_deger_net": s("A.39", "Polyetherimide (PEI-CH0.68 N0.05O0.14)", "30.1", "MJ/kg", not_="ΔH_T"),
           "yogunluk": s("A.36", "Polyetherimide (PEI)", "528–540 1.27", "10^3 kg/m3", tur="A36"),
           "LOI": s("36.5", "Polyetherimide (PEI)", "47", "%")})
ekle(id="silicone", ad="Silikon kauçuk", ad_en="Silicone rubber",
     es=["silikon", "silicone", "polidimetilsiloksan", "PDMS", "SIR"], tur="kati", numune="thin_sheet",
     motor_benzeri="silicone", eslesme_gerekce="kendisi (hafif motor kalibrasyon verisinde)", desen=r"silicon",
     uzay="conta, sızdırmazlık halkası ve kablo kılıfı",
     sfpe={"isil_deger_net": s("A.39", "Silicone rubber", "21.7", "MJ/kg", not_="ΔH_T"),
           "yogunluk": s("A.36", "Silicone rubber (SIR)", "407", "10^3 kg/m3", tur="A36")})
ekle(id="viton", ad="Viton (florlu elastomer)", ad_en="Viton (fluoroelastomer, FKM)",
     es=["FKM", "florlu kauçuk", "Fluorel", "Viton A"], tur="kati", numune="thin_sheet", motor_benzeri="silicone",
     eslesme_gerekce="elastomer conta; kalibre elastomer silikon (ZAYIF eşleme)", desen=r"viton|fluoroelastomer|fluorel",
     uzay="O-halka ve contalar (yakıt/oksijen hatları)",
     sfpe={"isil_deger": s("A.32", "—vinylidene", "14.0–15.1", "MJ/kg",
                           not_="A.32'de tek değer; brüt/net sütunu OCR metninde ayırt edilemedi")})
ekle(id="neoprene", ad="Neopren", ad_en="Neoprene (polychloroprene)",
     es=["polikloropren", "CR", "kloropren kauçuk"], tur="kati", numune="thin_sheet", motor_benzeri="silicone",
     eslesme_gerekce="elastomer; kalibre elastomer silikon (ZAYIF eşleme)", desen=r"neoprene|chloroprene",
     uzay="conta, kablo kılıfı",
     sfpe={"isil_deger_net": s("A.38", "Polychloroprene", "25.3c", "MJ/kg"),
           "yogunluk": s("A.36", "Polychloroprene (neoprene, CR)", "406", "10^3 kg/m3", tur="A36")})
ekle(id="pu_foam", ad="Poliüretan köpük (Pyrell)", ad_en="Polyurethane foam (Pyrell)",
     es=["PU köpük", "Pyrell", "esnek poliüretan köpük", "polyurethane foam"], tur="kati", numune="thick_sheet",
     motor_benzeri="pmma", eslesme_gerekce="kalın katı grubu; köpüğe kalibre malzeme yok (ZAYIF eşleme)",
     desen=r"urethane", uzay="saklama kutularında yastıklama köpüğü (Pyrell)",
     sfpe={"isil_deger_net": s("A.38", "GM21", "26.2c", "MJ/kg",
                               not_="esnek PU köpükler GM21–GM27: 23,2–27,2 MJ/kg (A.38); burada GM21")})
ekle(id="melamine_foam", ad="Melamin köpük", ad_en="Melamine foam",
     es=["melamin-formaldehit köpük", "Basotect"], tur="kati", numune="thick_sheet", motor_benzeri="pmma",
     eslesme_gerekce="kalın katı grubu; köpüğe kalibre malzeme yok (ZAYIF eşleme)", desen=r"melamine",
     uzay="akustik yalıtım ve ambalaj köpüğü",
     sfpe={"isil_deger_net": s("A.31", "Melamine formaldehyde", "18.52", "MJ/kg",
                               not_="katı melamin-formaldehit (Formica) değeri; köpüğün kendi değeri değil")})
ekle(id="pvdf_foam", ad="PVDF köpük (Zotek)", ad_en="PVDF foam (Zotek F)",
     es=["Zotek", "Zotek F", "polivinilidin florür köpük", "Kynar köpük"], tur="kati", numune="thick_sheet",
     motor_benzeri="silicone", eslesme_gerekce="zor yanan köpük; ZAYIF eşleme", desen=r"pvdf|zotek|kynar|vinylidene ?fluoride",
     uzay="ISS saklama ambalajında yanmaya dayanıklı köpük",
     sfpe={"isil_deger_net": s("A.38", "Kynar (PVF2)", "13.3c", "MJ/kg", not_="katı PVDF değeri"),
           "LOI": s("36.5", "Polyvinylideneﬂuoride (PVDF)", "44", "%", not_="katı PVDF")})
ekle(id="cotton", ad="Pamuklu kumaş", ad_en="Cotton fabric",
     es=["pamuk", "cotton", "pamuk bez"], tur="kati", numune="fabric", motor_benzeri="cotton",
     eslesme_gerekce="kendisi", desen=r"cotton(?!-fiberglass)(?!.*sibal)(?!.*fiberglass)", uzay="havlu, giysi, temizlik bezi",
     sfpe={"isil_deger": s("A.32", "Cotton", "16.5–20.4", "MJ/kg",
                           not_="A.32'de tek değer; brüt/net sütunu OCR metninde ayırt edilemedi")})
ekle(id="sibal", ad="SIBAL", ad_en="SIBAL (Solid Inflammable Boundary at Low speeds) cotton-fiberglass fabric",
     es=["pamuk-cam elyaf kumaş", "cotton-fiberglass", "SIBAL kumaş"], tur="kati", numune="fabric",
     motor_benzeri="sibal", eslesme_gerekce="kendisi (hafif motor kalibrasyon verisinde)",
     desen=r"sibal|cotton-fiberglass|fiberglass, 50% cotton", uzay="Saffire ve BASS deneylerinin standart kumaş numunesi",
     sfpe={})
ekle(id="beta_cloth", ad="Cam elyaf kumaş (Beta kumaşı)", ad_en="Fiberglass fabric (Beta cloth)",
     es=["Beta cloth", "PTFE kaplı cam elyaf kumaş", "fiberglass fabric"], tur="kati", numune="fabric",
     motor_benzeri="nomex", eslesme_gerekce="yanmaz cam elyaf (yalnız kaplama yanar); ZAYIF eşleme",
     desen=r"beta cloth|fiberglass fabric|glass fabric", uzay="uzay giysisi dış katmanı, MLI dış örtüsü",
     sfpe={})
ekle(id="paper", ad="Kâğıt", ad_en="Paper",
     es=["kağıt", "Kimwipes", "laboratuvar mendili", "filtre kâğıdı", "paper"], tur="kati", numune="thin_sheet",
     motor_benzeri="cotton", eslesme_gerekce="selüloz; kalibre selüloz malzemesi pamuk",
     desen=r"paper|kimwipe|laboratory wip|index card", uzay="belge, etiket, mendil",
     sfpe={"isil_deger": s("A.32", "Paper—brown", "16.3–17.9", "MJ/kg",
                           not_="kahverengi kâğıt; brüt/net sütunu OCR metninde ayırt edilemedi")})
ekle(id="cardboard", ad="Karton", ad_en="Cardboard",
     es=["mukavva", "oluklu karton", "cardboard", "corrugated paper"], tur="kati", numune="thick_sheet",
     motor_benzeri="cotton", eslesme_gerekce="selüloz; kalibre selüloz malzemesi pamuk (kalın: ZAYIF)",
     desen=r"cardboard|corrugated", uzay="kargo ambalajı", sfpe={})
ekle(id="fr4", ad="FR-4 (devre kartı)", ad_en="FR-4 (glass-epoxy laminate)",
     es=["epoksi cam elyaf laminat", "devre kartı", "PCB", "G-10"], tur="kati", numune="thick_sheet",
     motor_benzeri="pmma", eslesme_gerekce="kalın katı grubu; kompozite kalibre malzeme yok (ZAYIF eşleme)",
     desen=r"fr-?4|epoxy/[ﬁf]iberglass|epoxy/fg", uzay="aviyonik ve elektronik kartlar",
     sfpe={}, notlar="Sertleşmiş epoksi reçinenin net yanma ısısı 28,90 MJ/kg (SFPE A.31); cam elyaf oranı bilinmediği "
                     "için kompozite uygulanmadı.")
ekle(id="etfe", ad="ETFE kablo yalıtımı (Tefzel)", ad_en="ETFE wire insulation (Tefzel)",
     es=["Tefzel", "ETFE", "etilen tetrafloroetilen"], tur="kati", numune="wire", motor_benzeri="pmma",
     eslesme_gerekce="tel yalıtımı; tel geometrisine kalibre malzeme yok (ZAYIF eşleme)", desen=r"etfe|tefzel",
     uzay="uzay aracı kablolarının yalıtımı",
     sfpe={"isil_deger_net": s("A.38", "Tefzel ETFE", "12.6c", "MJ/kg"),
           "yogunluk": s("A.36", "(ETFE, Tefzel®)", "540", "10^3 kg/m3", tur="A36")})
ekle(id="abs", ad="ABS (3B yazıcı)", ad_en="ABS (acrylonitrile butadiene styrene)",
     es=["akrilonitril bütadien stiren", "ABS filament"], tur="kati", numune="thick_sheet", motor_benzeri="pmma",
     eslesme_gerekce="eriyen termoplastik (3B baskı parçası: kalın); kalibre malzeme PMMA", desen=r"^abs\b|acrylonitrile[- ]butadiene",
     uzay="ISS'teki 3B yazıcıların filamenti",
     sfpe={"isil_deger_net": s("A.31", "Acrylonitrile-butadiene styrene", "33.75", "MJ/kg", not_="net Δh_c (A.31)"),
           "yogunluk": s("A.36", "(ABS)", "394", "10^3 kg/m3", tur="A36"),
           "LOI": s("36.5", "Acrylonitrile-butadiene-styrene (ABS)", "18", "%")})
ekle(id="pla", ad="PLA (3B yazıcı)", ad_en="PLA (polylactic acid)",
     es=["polilaktik asit", "PLA filament"], tur="kati", numune="thick_sheet", motor_benzeri="pmma",
     eslesme_gerekce="eriyen termoplastik (3B baskı parçası: kalın); kalibre malzeme PMMA", desen=r"\bpla\b|polylactic",
     uzay="3B yazıcı filamenti (yer ve deney)", sfpe={})

# SIVI ---------------------------------------------------------------
ekle(id="ethanol", ad="Etanol", ad_en="Ethanol", es=["etil alkol", "ethyl alcohol", "alkol (temizlik mendili)"],
     tur="sivi", numune="droplet", motor_benzeri="ethanol",
     eslesme_gerekce="damla motoru etanolü tanıyor (kalibre değil; heptan/metanol kalibrasyonundan)",
     desen=r"^ethanol|ethyl alcohol", uzay="temizlik mendilleri (dezenfektan)", nist="ethanol", damla="C2H5OH",
     sfpe={"isil_deger_net": s("A.38", "Ethyl alcohol", "27.7", "MJ/kg"),
           "yogunluk": s("A.24", "Ethyl alcohol", "788.6", "kg/m3", not_="20 °C")})
ekle(id="isopropanol", ad="İzopropanol (IPA)", ad_en="Isopropanol (2-propanol)",
     es=["IPA", "2-propanol", "izopropil alkol", "isopropyl alcohol"], tur="sivi", numune="droplet",
     motor_benzeri="1-propanol", eslesme_gerekce="damla motorunda aynı formüllü 1-propanol var (C3H7OH; izomer)",
     desen=r"isopropanol|2-propanol|isopropyl", uzay="temizlik ve elektronik bakım", nist="isopropanol",
     sfpe={"isil_deger_net": s("A.38", "Isopropyl alcohol", "31.8", "MJ/kg")})
ekle(id="methanol", ad="Metanol", ad_en="Methanol", es=["metil alkol", "methyl alcohol"], tur="sivi",
     numune="droplet", motor_benzeri="methanol", eslesme_gerekce="kendisi (damla motoru FLEX ile kalibre)",
     desen=r"^methanol|^pure methanol|methyl alcohol", uzay="FLEX damla yanma deneyleri (ISS)", nist="methanol",
     damla="CH3OH", sfpe={"isil_deger_net": s("A.38", "Methyl alcohol", "20", "MJ/kg")})
ekle(id="n-heptane", ad="n-Heptan", ad_en="n-Heptane", es=["heptan", "heptane"], tur="sivi", numune="droplet",
     motor_benzeri="n-heptane", eslesme_gerekce="kendisi (damla motoru FLEX ile kalibre)", desen=r"^n-heptane|^heptane",
     uzay="FLEX damla yanma deneyleri (ISS)", nist="n-heptane", damla="NC7H16",
     sfpe={"isil_deger_net": s("A.38", "Heptane", "44.6", "MJ/kg")})
ekle(id="n-decane", ad="n-Dekan", ad_en="n-Decane", es=["dekan", "decane"], tur="sivi", numune="droplet",
     motor_benzeri="n-decane", eslesme_gerekce="damla motoru dekanı tanıyor (kalibre değil)",
     desen=r"^n-decane|^decane", uzay="FLEX-2 damla deneyleri; jet yakıtı vekili", nist="n-decane", damla="NC10H22",
     sfpe={"isil_deger_net": s("A.38", "Decane", "44.4", "MJ/kg")})
ekle(id="acetone", ad="Aseton", ad_en="Acetone", es=["propanon", "dimetil keton"], tur="sivi", numune="droplet",
     motor_benzeri="methanol", eslesme_gerekce="uçucu, suyla karışan çözücü; damla motoru asetonu tanımıyor (ZAYIF eşleme)",
     desen=r"aceton", uzay="çözücü ve temizlik", nist="acetone",
     sfpe={"isil_deger_net": s("A.38", "Acetone", "29.7", "MJ/kg")})
ekle(id="kerosene", ad="Kerosen (RP-1 / jet yakıtı)", ad_en="Kerosene (RP-1 / jet fuel)",
     es=["RP-1", "Jet-A", "JP-8", "gazyağı", "kerosene"], tur="sivi", numune="droplet", motor_benzeri="n-decane",
     eslesme_gerekce="karışım; damla motorundaki en ağır alkan n-dekan (vekil)", desen=r"kerosen|^jp-?8|jet[- ]?a|rp-1",
     uzay="roket itici yakıtı (RP-1); kargo araçlarında", nist=None,
     sfpe={"isil_deger_net": s("A.32", "Kerosene (jet fuel A)", "43.3", "MJ/kg", not_="Jet A; brüt 46,4 (aynı satır)"),
           "yogunluk": s("A.24", "Jet fuel (JP-4)", "773.1", "kg/m3", not_="JP-4, 15,6 °C (kerosen değil, en yakın satır)")})
ekle(id="hydraulic_oil", ad="Hidrolik yağı", ad_en="Hydraulic fluid",
     es=["hidrolik sıvı", "hydraulic oil"], tur="sivi", numune="pool", motor_benzeri="n-decane",
     eslesme_gerekce="ağır hidrokarbon karışımı; yapay zeka sınıflandırması da n-dekan dedi (malzeme_onbellek.json)",
     desen=r"hydraulic", uzay="mekanizma ve robot kol hidroliği", nist=None, sfpe={})
ekle(id="propylene_glycol", ad="Propilen glikol (soğutucu)", ad_en="Propylene glycol",
     es=["1,2-propandiol", "PG", "propylene glycol"], tur="sivi", numune="pool", motor_benzeri="methanol",
     eslesme_gerekce="suyla karışan alkol; damla motoru tanımıyor (ZAYIF eşleme)", desen=r"propylene glycol|propanediol",
     uzay="ısıl kontrol soğutucu döngüleri (su-glikol)", nist="propylene-glycol", sfpe={})
ekle(id="hydrazine", ad="MMH / hidrazin (itici)", ad_en="Monomethylhydrazine / hydrazine",
     es=["MMH", "monometilhidrazin", "hidrazin", "N2H4"], tur="sivi", numune="pool", motor_benzeri=None,
     eslesme_gerekce="tek bileşenli itici; kendiliğinden ayrışır. Motorların hiçbiri uygun değil",
     desen=r"hydrazin|\bmmh\b", uzay="manevra iticileri (hipergolik itici)", nist="mmh", nist_ek="hydrazine", sfpe={})

# GAZ ----------------------------------------------------------------
ekle(id="hydrogen", ad="Hidrojen", ad_en="Hydrogen", es=["H2", "hidrojen gazı"], tur="gaz", numune="gas_jet",
     motor_benzeri="hydrogen", eslesme_gerekce="gaz motoru hidrojeni tanıyor (kalibre değil)",
     desen=r"^hydrogen|^h2$", uzay="yakıt hücresi, oksijen üretimindeki elektroliz yan ürünü", nist="hydrogen", sfpe={})
ekle(id="methane", ad="Metan", ad_en="Methane", es=["CH4", "doğal gaz"], tur="gaz", numune="gas_jet",
     motor_benzeri="methane", eslesme_gerekce="gaz motoru metanı tanıyor (jet geometrisi kalibre değil)",
     desen=r"^methane|^ch4$|stoichiometric ch4", uzay="Sabatier reaktörü ürünü (ISS), SLICE jet deneyleri", nist="methane",
     sfpe={"isil_deger_net": s("A.38", "Methane", "50.1", "MJ/kg")})
ekle(id="ethylene", ad="Etilen", ad_en="Ethylene", es=["eten", "C2H4"], tur="gaz", numune="flat_burner",
     motor_benzeri="ethylene", eslesme_gerekce="kendisi (gaz motoru BRE ile kalibre)",
     desen=r"^ethylene|^c2h4", uzay="ACME BRE ve s-flame deneyleri (ISS)", nist="ethylene",
     sfpe={"isil_deger_net": s("A.38", "Ethylene", "48", "MJ/kg")})
ekle(id="ethane", ad="Etan", ad_en="Ethane", es=["C2H6"], tur="gaz", numune="gas_jet", motor_benzeri="ethane",
     eslesme_gerekce="gaz motoru etanı tanıyor (kalibre değil)", desen=r"^ethane", uzay="yanma deneyleri", nist="ethane",
     sfpe={"isil_deger_net": s("A.38", "Ethane", "47.1", "MJ/kg")})
ekle(id="propane", ad="Propan", ad_en="Propane", es=["C3H8", "LPG"], tur="gaz", numune="gas_jet",
     motor_benzeri="propane", eslesme_gerekce="gaz motoru propanı tanıyor (kalibre değil)", desen=r"^propane",
     uzay="yanma deneyleri", nist="propane", sfpe={"isil_deger_net": s("A.38", "Propane", "46", "MJ/kg")})
ekle(id="carbon_monoxide", ad="Karbon monoksit", ad_en="Carbon monoxide", es=["CO"], tur="gaz", numune="gas_jet",
     motor_benzeri="hydrogen", eslesme_gerekce="gaz motoru CO'yu tanımıyor; hidrokarbon olmayan tek yakıt hidrojen (ZAYIF eşleme)",
     desen=r"carbon monoxide|^co$", uzay="yangın ürünü; kabin gaz izleme", nist="carbon-monoxide", sfpe={})
ekle(id="ammonia", ad="Amonyak", ad_en="Ammonia", es=["NH3"], tur="gaz", numune="gas_jet", motor_benzeri="methane",
     eslesme_gerekce="gaz motoru amonyağı tanımıyor (ZAYIF eşleme)", desen=r"ammonia|^nh3$",
     uzay="ISS dış ısıl kontrol döngüsü soğutucusu", nist="ammonia", sfpe={})
ekle(id="acetylene", ad="Asetilen", ad_en="Acetylene", es=["etin", "C2H2"], tur="gaz", numune="gas_jet",
     motor_benzeri="ethylene", eslesme_gerekce="gaz motoru asetileni tanımıyor; en yakın C2 yakıtı etilen (ZAYIF eşleme)",
     desen=r"acetylen|^c2h2", uzay="kaynak/kesme gazı; yanma deneyleri", nist="acetylene",
     sfpe={"isil_deger_net": s("A.38", "Acetylene", "47.8", "MJ/kg")})

# ===================================================================== 2. GENİŞLETME (2026-11-13)
# kategori: kıyafet/kumaş, plastik, kompozit/yapı, kauçuk/conta, yalıtım/köpük, elektronik/kablo, ambalaj/diğer,
#           yiyecek, pil, akışkan/yağ, yakıt/itici, temizlik/çözücü, gaz
# ozel: yakıt olarak çözülmeyen malzemeler -> tahmin sayı üretmeden uyarı verir (tahmin.py _ozel_durum)
OKS = {"tur": "oksitleyici", "uyari": "yanmaz ama yangını şiddetlendirir (oksitleyici): yakıt olarak tahmin yapılmaz"}
YANMAZ = {"tur": "yanmaz", "uyari": "yanıcı değil: tahmin yapılmaz"}
PIL = {"tur": "pil", "uyari": "termal kaçak modeli yok: motor yok, tahmin yapılmaz"}
PTFE_OZ = {"isil_deger_net": s("A.38", "Teﬂon TFE", "6.2c", "MJ/kg", not_="katı PTFE"),
           "yogunluk": s("A.36", "Polytetraﬂuoroethylene (PTFE)", "630–700 2.15–2.18", "10^3 kg/m3", tur="A36", not_="katı PTFE"),
           "LOI": s("36.5", "Polytetraﬂuoroethylene (PTFE)", "95", "%", not_="katı PTFE")}
PET_OZ = {"isil_deger_net": s("A.38", "Polyethylene-terephthalate", "22c", "MJ/kg"),
          "yogunluk": s("A.36", "Polyethyleneterephthalate (PET)", "1.35", "10^3 kg/m3", tur="A36"),
          "LOI": s("36.5", "Polyethyleneterephthalate (PET)", "21", "%")}
PVC_OZ = {"isil_deger_net": s("A.39", "PVC", "16.4", "MJ/kg", not_="ΔH_T"),
          "yogunluk": s("A.36", "Polyvinylchloride (PVC, ﬂexible)", "1.26–1.95", "10^3 kg/m3", tur="A36", not_="esnek PVC"),
          "LOI": s("36.5", "Polyvinylchloride (PVC)", "50", "%")}
TEL = "tel yalıtımı; tel geometrisine kalibre malzeme yok (ZAYIF eşleme)"

# KATI — kıyafet/kumaş
ekle(id="wool", ad="Yün", ad_en="Wool", es=["yün", "yün kumaş", "wool", "yünlü kumaş"], tur="kati", numune="fabric",
     motor_benzeri="cotton", eslesme_gerekce="doğal lif kumaş; kalibre kumaş pamuk (yün protein lifidir, daha zor yanar: ZAYIF eşleme)",
     desen=r"\bwool\b(?!.*rock)", uzay="giysi katmanları (tarihî uçuşlar), battaniye", sfpe={}, kategori="kıyafet/kumaş",
     notlar="SFPE A.39'da 'Wool 100%' satırı var ama değerleri boş.")
ekle(id="merino", ad="Merinos yünü", ad_en="Merino wool", es=["merinos", "merinos yünü", "merino", "merino wool"], tur="kati",
     numune="fabric", motor_benzeri="cotton", eslesme_gerekce="yün kumaş; kalibre kumaş pamuk (ZAYIF eşleme)",
     desen=r"merino", uzay="ISS mürettebat iç giyimi ve tişörtleri", sfpe={}, kategori="kıyafet/kumaş",
     notlar="Kaynaklarda merinosa özgü değer yok; 'Yün' kaydına bakın.")
ekle(id="polyester_fabric", ad="Polyester kumaş (PET)", ad_en="Polyester (PET) fabric",
     es=["polyester", "polyester kumaş", "PET kumaş", "Dacron", "polyester fabric"], tur="kati", numune="fabric",
     motor_benzeri="cotton", eslesme_gerekce="sentetik kumaş; kalibre kumaş pamuk (polyester erir, damlar: ZAYIF eşleme)",
     desen=r"polyester(?!.*resin)", uzay="giysi, kayış, saklama torbası", sfpe=PET_OZ, kategori="kıyafet/kumaş",
     notlar="Özellikler katı PET'in (SFPE A.38/A.36, Tablo 36.5).")
ekle(id="gore_tex", ad="Gore-Tex (ePTFE membran)", ad_en="Gore-Tex (expanded PTFE membrane)",
     es=["Gore-Tex", "GoreTex", "ePTFE", "genleştirilmiş PTFE", "expanded PTFE"], tur="kati", numune="fabric",
     motor_benzeri="silicone", eslesme_gerekce="PTFE membranlı kumaş; kalibre malzemeler arasında en zor yanan silikon (ZAYIF eşleme)",
     desen=r"gore-?tex|eptfe", uzay="giysi ve eldiven membranı", sfpe=PTFE_OZ, kategori="kıyafet/kumaş",
     notlar="Değerler katı PTFE'nin; Gore-Tex laminatında yüz kumaşı (naylon/polyester) ayrıca yanar.")
ekle(id="spandex", ad="Spandeks (elastan, Lycra)", ad_en="Spandex (elastane)",
     es=["spandeks", "elastan", "Lycra", "spandex", "elastane", "likra"], tur="kati", numune="fabric",
     motor_benzeri="cotton", eslesme_gerekce="sentetik kumaş; kalibre kumaş pamuk (ZAYIF eşleme)", desen=r"spandex|elastane|lycra",
     uzay="egzersiz giysisi, sıkı giysi katmanları", kategori="kıyafet/kumaş",
     sfpe={"isil_deger": s("A.32", "Spandex ﬁber", "31.4", "MJ/kg", not_="A.32'de tek değer; brüt/net ayırt edilemedi")})
ekle(id="acrylic_fabric", ad="Akrilik kumaş (poliakrilonitril)", ad_en="Acrylic fabric (polyacrylonitrile)",
     es=["akrilik kumaş", "akrilik elyaf", "poliakrilonitril", "PAN", "Orlon", "acrylic fiber", "acrylic fabric"], tur="kati",
     numune="fabric", motor_benzeri="cotton", eslesme_gerekce="sentetik kumaş; kalibre kumaş pamuk (ZAYIF eşleme)",
     desen=r"acrylic fiber|acrylic fabric|polyacrylonitrile", uzay="battaniye, örme giysi", kategori="kıyafet/kumaş",
     sfpe={"isil_deger_net": s("A.38", "Polyacrylonitrile (PAN)", "30.8c", "MJ/kg"),
           "yogunluk": s("A.36", "Polyacrylonitrile (PAN)", "1.15", "10^3 kg/m3", tur="A36")})
# KATI — plastik
ekle(id="pvc", ad="PVC", ad_en="PVC (polyvinyl chloride)", es=["PVC", "polivinil klorür", "vinil", "polyvinyl chloride"],
     tur="kati", numune="thin_sheet", motor_benzeri="silicone",
     eslesme_gerekce="halojenli, kendiliğinden sönen levha (LOI 50); kalibre zor yanan malzeme silikon (ZAYIF eşleme)",
     desen=r"^pvc\b|polyvinyl ?chloride", uzay="hortum, kablo kılıfı, torba", sfpe=PVC_OZ, kategori="plastik")
ekle(id="pet", ad="PET (polietilen tereftalat)", ad_en="PET (polyethylene terephthalate)",
     es=["polietilen tereftalat", "PETE", "Mylar", "pet şişe", "polyethylene terephthalate", "PET film"], tur="kati",
     numune="thin_sheet", motor_benzeri="pmma", eslesme_gerekce="eriyen termoplastik levha/film; kalibre levha malzemesi PMMA",
     desen=r"^pet\b|terephthalate|mylar", uzay="şişe, ambalaj filmi, alüminize Mylar (MLI katmanı)", sfpe=PET_OZ,
     kategori="plastik")
ekle(id="polystyrene", ad="Polistiren", ad_en="Polystyrene", es=["polistiren", "PS", "polystyrene"], tur="kati",
     numune="thin_sheet", motor_benzeri="pmma", eslesme_gerekce="eriyen termoplastik levha; kalibre levha malzemesi PMMA",
     desen=r"^polystyrene$|^ps$", uzay="kap, kapak, laboratuvar sarf malzemesi", kategori="plastik",
     sfpe={"isil_deger_net": s("A.38", "Polystyrene", "39.2", "MJ/kg"),
           "yogunluk": s("A.36", "Polystyrene (PS)", "1.05", "10^3 kg/m3", tur="A36"),
           "LOI": s("36.5", "Polystyrene (PS)", "18", "%")})
ekle(id="pom", ad="POM (asetal, Delrin)", ad_en="POM (polyoxymethylene, acetal)",
     es=["POM", "Delrin", "asetal", "polioksimetilen", "acetal", "polyoxymethylene"], tur="kati", numune="thin_sheet",
     motor_benzeri="pmma", eslesme_gerekce="eriyen termoplastik; kalibre levha malzemesi PMMA (POM LOI 15: kolay yanar)",
     desen=r"\bpom\b|delrin|acetal|oxymethylene", uzay="dişli, burç, mekanizma parçaları", kategori="plastik",
     sfpe={"isil_deger_net": s("A.31", "Polyoxymethylene", "15.65", "MJ/kg", not_="net Δh_c (A.31)"),
           "yogunluk": s("A.36", "Polyoxymethylene (POM)", "1.42", "10^3 kg/m3", tur="A36"),
           "LOI": s("36.5", "Polyoxymethylene (POM)", "15", "%")})
ekle(id="fep", ad="FEP", ad_en="FEP (fluorinated ethylene propylene)",
     es=["FEP", "Teflon FEP", "floroetilen propilen", "fluorinated ethylene propylene"], tur="kati", numune="thin_sheet",
     motor_benzeri="silicone", eslesme_gerekce="florlu polimer, havada zor yanar; ZAYIF eşleme", desen=r"\bfep\b",
     uzay="kablo yalıtımı, MLI dış filmi, akışkan hortumu", kategori="plastik",
     sfpe={"isil_deger_net": s("A.38", "Teﬂon FEP", "4.8c", "MJ/kg"),
           "yogunluk": s("A.36", "Fluorinated ethylene propylene (FEP,", "2.15", "10^3 kg/m3")})
ekle(id="pfa", ad="PFA", ad_en="PFA (perfluoroalkoxy)", es=["PFA", "Teflon PFA", "perfloroalkoksi", "perfluoroalkoxy"],
     tur="kati", numune="thin_sheet", motor_benzeri="silicone", eslesme_gerekce="florlu polimer, havada zor yanar; ZAYIF eşleme",
     desen=r"\bpfa\b", uzay="kimyasal hat, kablo yalıtımı", kategori="plastik",
     sfpe={"isil_deger_net": s("A.38", "Teﬂon PFA", "5c", "MJ/kg"),
           "yogunluk": s("A.36", "perﬂuoroether (PFA)", "2.15", "10^3 kg/m3", tur="A36")})
ekle(id="pvdf", ad="PVDF (Kynar)", ad_en="PVDF (polyvinylidene fluoride)",
     es=["PVDF", "Kynar", "polivinilidin florür", "polyvinylidene fluoride"], tur="kati", numune="thin_sheet",
     motor_benzeri="silicone", eslesme_gerekce="florlu polimer (LOI 44); ZAYIF eşleme", desen=r"^pvdf$|^kynar$",
     uzay="boru, kablo kılıfı, kaplama", kategori="plastik",
     sfpe={"isil_deger_net": s("A.38", "Kynar (PVF2)", "13.3c", "MJ/kg"),
           "yogunluk": s("A.36", "Polyvinylideneﬂuoride (PVDF)", "1.76", "10^3 kg/m3", tur="A36"),
           "LOI": s("36.5", "Polyvinylideneﬂuoride (PVDF)", "44", "%")})
ekle(id="phenolic", ad="Fenolik reçine", ad_en="Phenolic resin (phenol formaldehyde)",
     es=["fenolik", "fenolik reçine", "fenol formaldehit", "bakalit", "Bakelite", "phenolic", "phenol formaldehyde"],
     tur="kati", numune="thick_sheet", motor_benzeri="pmma",
     eslesme_gerekce="kömürleşen termoset (kalın parça); kalibre kalın katı yok, PMMA kömürleşmez (ZAYIF eşleme)",
     desen=r"phenolic(?!.*foam)|phenol formaldehyde", uzay="ısı kalkanı matrisi, elektrik parçaları, panel", kategori="plastik",
     sfpe={"isil_deger_net": s("A.31", "Phenol formaldehyde", "26.7–30.4", "MJ/kg", not_="net Δh_c (A.31)"),
           "yogunluk": s("A.36", "Phenol formaldehyde (PF)", "1.30", "10^3 kg/m3", tur="A36")})
ekle(id="epoxy", ad="Epoksi", ad_en="Epoxy resin", es=["epoksi", "epoksi reçine", "epoxy", "epoxy resin", "yapıştırıcı epoksi"],
     tur="kati", numune="thick_sheet", motor_benzeri="pmma", eslesme_gerekce="termoset (kalın parça); kalibre kalın katı yok (ZAYIF eşleme)",
     desen=r"^epoxy$|epoxy resin", uzay="yapıştırıcı, kompozit matrisi, devre kartı", kategori="plastik",
     sfpe={"isil_deger_net": s("A.38", "Epoxy", "28.8c", "MJ/kg"),
           "yogunluk": s("A.36", "Epoxy (EP)", "1.20", "10^3 kg/m3", tur="A36")})
# KATI — kompozit/yapı
ekle(id="cfrp", ad="Karbon elyaf (CFRP)", ad_en="Carbon fiber reinforced polymer (CFRP)",
     es=["CFRP", "karbon elyaf", "karbon fiber", "karbon elyaf takviyeli plastik", "carbon fiber", "carbon fibre"], tur="kati",
     numune="thick_sheet", motor_benzeri="pmma", eslesme_gerekce="kompozit; yalnız reçine matrisi yanar, kalibre kompozit yok (ZAYIF eşleme)",
     desen=r"cfrp|carbon fib|graphite/epoxy", uzay="yapı panelleri, basınç tankı sargısı, robot kol", sfpe={},
     kategori="kompozit/yapı", notlar="Elyaf oranı bilinmediği için matris değeri kompozite uygulanmadı; matris için 'Epoksi' kaydı.")
ekle(id="gfrp", ad="Cam elyaf takviyeli plastik (GFRP)", ad_en="Glass fiber reinforced polymer (GFRP)",
     es=["GFRP", "CTP", "cam elyaf takviyeli plastik", "fiberglas kompozit", "glass fiber reinforced plastic"], tur="kati",
     numune="thick_sheet", motor_benzeri="pmma", eslesme_gerekce="kompozit; yalnız reçine matrisi yanar, kalibre kompozit yok (ZAYIF eşleme)",
     desen=r"gfrp|/fgr|glass fiber reinforced", uzay="panel, kapak, radom", sfpe={}, kategori="kompozit/yapı",
     notlar="Cam elyafın kendisi yanmaz ('Cam elyaf (saf)' kaydı); reçine için 'Epoksi' / 'Fenolik reçine'.")
ekle(id="honeycomb_nomex", ad="Bal peteği panel (Nomex çekirdek)", ad_en="Honeycomb sandwich panel (Nomex core)",
     es=["bal peteği panel", "bal peteği", "Nomex bal peteği", "honeycomb panel", "sandviç panel"], tur="kati",
     numune="thick_sheet", motor_benzeri="nomex", eslesme_gerekce="çekirdek Nomex; panel kalın ve kaplamalı (ZAYIF eşleme)",
     desen=r"honeycomb", uzay="kabin iç panelleri, raf ve zemin panelleri", sfpe={}, kategori="kompozit/yapı",
     notlar="Çekirdek için 'Nomex' kaydı; yüz kaplaması (cam/karbon-fenolik) ayrıca.")
# KATI — kauçuk/conta
ekle(id="epdm", ad="EPDM", ad_en="EPDM (ethylene propylene diene monomer)",
     es=["EPDM", "etilen propilen dien kauçuk", "ethylene propylene diene"], tur="kati", numune="thin_sheet",
     motor_benzeri="silicone", eslesme_gerekce="elastomer conta; kalibre elastomer silikon (ZAYIF eşleme)", desen=r"epdm",
     uzay="conta, hortum, kapı fitili", kategori="kauçuk/conta",
     sfpe={"yogunluk": s("A.36", "Ethylene-propylene diene (EPDM)", "0.93", "10^3 kg/m3", tur="A36")})
ekle(id="natural_rubber", ad="Doğal kauçuk", ad_en="Natural rubber (polyisoprene)",
     es=["doğal kauçuk", "kauçuk", "lateks", "poliizopren", "natural rubber", "NR"], tur="kati", numune="thin_sheet",
     motor_benzeri="silicone", eslesme_gerekce="elastomer; kalibre elastomer silikon (doğal kauçuk çok daha kolay yanar: ZAYIF eşleme)",
     desen=r"natural rubber|polyisoprene", uzay="lastik bant, eldiven, conta", kategori="kauçuk/conta",
     sfpe={"isil_deger_net": s("A.31", "Polyisoprene", "42.30", "MJ/kg", not_="net Δh_c (A.31)"),
           "yogunluk": s("A.36", "Polyisoprene (natural rubber, NR)", "0.92", "10^3 kg/m3", tur="A36")})
ekle(id="nbr", ad="Nitril kauçuk (NBR)", ad_en="Nitrile rubber (NBR, Buna-N)",
     es=["NBR", "nitril", "nitril kauçuk", "Buna-N", "nitrile rubber", "nitril eldiven"], tur="kati", numune="thin_sheet",
     motor_benzeri="silicone", eslesme_gerekce="elastomer; kalibre elastomer silikon (ZAYIF eşleme)", desen=r"nitrile|\bnbr\b|buna",
     uzay="O-halka, eldiven, yakıt hortumu", kategori="kauçuk/conta",
     sfpe={"isil_deger": s("A.32", "Rubber—buna N", "34.7–35.6", "MJ/kg", not_="A.32'de tek değer; brüt/net ayırt edilemedi"),
           "yogunluk": s("A.36", "Nitrile-butadiene (Buna-N, NBR)", "1.35", "10^3 kg/m3", tur="A36")})
ekle(id="fluorosilicone", ad="Florosilikon", ad_en="Fluorosilicone rubber (FVMQ)",
     es=["florosilikon", "FVMQ", "fluorosilicone", "florlu silikon"], tur="kati", numune="thin_sheet",
     motor_benzeri="silicone", eslesme_gerekce="silikon ailesi elastomer; kalibre olan düz silikon (ZAYIF eşleme)",
     desen=r"fluorosilicone", uzay="yakıt ve oksidan hatlarında conta", sfpe={}, kategori="kauçuk/conta")
# KATI — yalıtım/köpük
ekle(id="ps_foam", ad="Polistiren köpük (EPS, strafor)", ad_en="Expanded polystyrene foam (EPS)",
     es=["strafor", "EPS", "polistiren köpük", "köpük polistiren", "Styrofoam", "expanded polystyrene"], tur="kati",
     numune="thick_sheet", motor_benzeri="pmma", eslesme_gerekce="kalın katı grubu; köpüğe kalibre malzeme yok (ZAYIF eşleme)",
     desen=r"polystyrene.?foam|expanded polystyrene|styrofoam|\beps\b", uzay="ambalaj ve yer deneyi yalıtımı", kategori="yalıtım/köpük",
     sfpe={"isil_deger_net": s("A.38", "Expanded polystyrene", "38.1", "MJ/kg", ofset=3, not_="GM47")})
ekle(id="pe_foam", ad="Polietilen köpük", ad_en="Polyethylene foam",
     es=["PE köpük", "polietilen köpük", "polyethylene foam", "Ethafoam", "Plastazote"], tur="kati", numune="thick_sheet",
     motor_benzeri="pmma", eslesme_gerekce="kalın katı grubu; köpüğe kalibre malzeme yok (ZAYIF eşleme)",
     desen=r"polyethylene.?foam|ethafoam|plastazote", uzay="ambalaj ve saklama köpüğü (Plastazote)", kategori="yalıtım/köpük",
     sfpe={"isil_deger_net": s("A.39", "Polyethylene foams", "41.2", "MJ/kg", ofset=2, not_="ΔH_T")})
ekle(id="aerogel", ad="Aerojel (silika)", ad_en="Silica aerogel", es=["aerojel", "aerogel", "silika aerojel", "silica aerogel"],
     tur="kati", numune="thick_sheet", motor_benzeri=None,
     eslesme_gerekce="silika aerojel: inorganik, yanmaz",
     desen=r"aerogel", uzay="yüksek sıcaklık yalıtımı, kriyojenik yalıtım (Mars gezginleri)", sfpe={}, kategori="yalıtım/köpük",
     ozel=YANMAZ, notlar="Silika aerojel; organik katkılı/elyaflı battaniye türleri (Pyrogel, Cryogel vb.) farklı olabilir.")
ekle(id="mli", ad="MLI (çok katmanlı yalıtım)", ad_en="Multilayer insulation (MLI)",
     es=["MLI", "çok katmanlı yalıtım", "multilayer insulation", "termal battaniye", "ısıl battaniye"], tur="kati",
     numune="thin_sheet", motor_benzeri="silicone", eslesme_gerekce="aluminize Kapton/Mylar ince film yığını; ZAYIF eşleme",
     desen=r"\bmli\b|multilayer insulation|multi-layer insulation", uzay="uzay aracı dış ısıl yalıtımı", sfpe={},
     kategori="yalıtım/köpük", notlar="Katmanlar Kapton veya aluminize Mylar (PET), aralarında polyester/naylon ağ; "
                                     "özellik için 'Kapton' ve 'PET' kayıtları.")
# KATI — elektronik/kablo
ekle(id="pvc_cable", ad="PVC kablo", ad_en="PVC-insulated wire", es=["PVC kablo", "PVC yalıtımlı kablo", "PVC wire"],
     tur="kati", numune="wire", motor_benzeri="pmma", eslesme_gerekce=TEL, desen=r"pvc.*(?:wire|cable)|(?:wire|cable).*pvc",
     uzay="yer donanımı ve ticari cihaz kabloları (uçuşta kısıtlı)", sfpe=PVC_OZ, kategori="elektronik/kablo")
ekle(id="xlpe_cable", ad="XLPE kablo", ad_en="XLPE-insulated wire (cross-linked polyethylene)",
     es=["XLPE", "XLPE kablo", "çapraz bağlı polietilen", "PEX", "cross-linked polyethylene"], tur="kati", numune="wire",
     motor_benzeri="pmma", eslesme_gerekce=TEL, desen=r"xlpe|cross-?linked polyethylene", uzay="güç kabloları",
     kategori="elektronik/kablo",
     sfpe={"isil_deger_net": s("A.38", "Polyethylene", "43.6", "MJ/kg", not_="çapraz bağsız PE değeri"),
           "LOI": s("36.5", "Polyethylene (PE)", "18", "%", not_="çapraz bağsız PE değeri")})
ekle(id="silicone_cable", ad="Silikon kablo", ad_en="Silicone-insulated wire",
     es=["silikon kablo", "silikon yalıtımlı kablo", "silicone wire", "silicone cable"], tur="kati", numune="wire",
     motor_benzeri="silicone", eslesme_gerekce=TEL, desen=r"silicone.*(?:wire|cable)", uzay="yüksek sıcaklık ve esnek kablolar",
     kategori="elektronik/kablo",
     sfpe={"isil_deger_net": s("A.39", "Silicone rubber", "21.7", "MJ/kg", not_="ΔH_T"),
           "yogunluk": s("A.36", "Silicone rubber (SIR)", "407", "10^3 kg/m3", tur="A36")})
ekle(id="ptfe_cable", ad="PTFE kablo", ad_en="PTFE-insulated wire",
     es=["PTFE kablo", "teflon kablo", "PTFE wire", "PTFE yalıtımlı kablo"], tur="kati", numune="wire",
     motor_benzeri="silicone", eslesme_gerekce=TEL, desen=r"ptfe.*(?:wire|cable)|teflon.*(?:wire|cable)",
     uzay="uzay aracı sinyal ve güç kabloları", sfpe=PTFE_OZ, kategori="elektronik/kablo")
ekle(id="kapton_tape", ad="Kapton bant", ad_en="Kapton (polyimide) tape",
     es=["Kapton bant", "kapton bandı", "poliimid bant", "Kapton tape", "polyimide tape"], tur="kati", numune="thin_sheet",
     motor_benzeri="silicone", eslesme_gerekce="zor yanan ince film (yapıştırıcı silikon); ZAYIF eşleme", desen=r"kapton tape|polyimide tape",
     uzay="kablo demeti sarma, ısıl maskeleme", kategori="elektronik/kablo",
     sfpe={"yogunluk": s("A.36", "Polyimide (PI)", "1.40", "10^3 kg/m3", tur="A36", not_="genel poliimid film; yapıştırıcı hariç"),
           "LOI": s("36.5", "Polypromellitimide (PI)", "37", "%", not_="film; yapıştırıcı hariç")})
ekle(id="duct_tape", ad="Koli bandı (duct tape)", ad_en="Duct tape",
     es=["duct tape", "koli bandı", "tamir bandı", "gri bant", "gaffer bant", "gaffer tape"], tur="kati", numune="thin_sheet",
     motor_benzeri="pmma", eslesme_gerekce="PE film + pamuk ağ + kauçuk yapıştırıcı; kalibre ince levha PMMA (ZAYIF eşleme)",
     desen=r"duct tape|gaffer", uzay="ISS'te onarım ve sabitleme (her yerde)", sfpe={}, kategori="elektronik/kablo")
# KATI — ambalaj/diğer
ekle(id="foil_pouch", ad="Alüminyum folyo laminat poşet", ad_en="Aluminium foil laminate pouch",
     es=["folyo poşet", "laminat poşet", "alüminyum laminat poşet", "yiyecek poşeti", "foil pouch", "Mylar poşet"], tur="kati",
     numune="thin_sheet", motor_benzeri="pmma", eslesme_gerekce="PET/Al/PE laminat film; Al yanmaz, polimer katmanlar yanar (ZAYIF eşleme)",
     desen=r"foil.*(?:pouch|laminate)|laminate pouch", uzay="uzay yiyeceği ve içecek ambalajı", sfpe={}, kategori="ambalaj/diğer",
     notlar="Polimer katmanlar için 'PET' ve 'Polietilen' kayıtları.")
ekle(id="paper_towel", ad="Kâğıt havlu", ad_en="Paper towel", es=["kağıt havlu", "kâğıt havlu", "peçete", "paper towel"],
     tur="kati", numune="thin_sheet", motor_benzeri="cotton", eslesme_gerekce="selüloz; kalibre selüloz malzemesi pamuk",
     desen=r"paper towel", uzay="temizlik ve hijyen", sfpe={}, kategori="ambalaj/diğer",
     notlar="Kâğıdın yanma ısısı için 'Kâğıt' kaydı (SFPE A.32 kahverengi kâğıt).")
ekle(id="sponge", ad="Sünger", ad_en="Sponge", es=["sünger", "bulaşık süngeri", "banyo süngeri", "sponge"], tur="kati",
     numune="thick_sheet", motor_benzeri="pmma", eslesme_gerekce="çoğunlukla poliüretan köpük; köpüğe kalibre malzeme yok (ZAYIF eşleme)",
     desen=r"sponge", uzay="temizlik, sıvı emme", sfpe={}, kategori="ambalaj/diğer",
     notlar="Poliüretan süngerde 'Poliüretan köpük' kaydı; selüloz süngerde 'Kâğıt'.")
ekle(id="wood", ad="Ahşap (deney kutusu)", ad_en="Wood", es=["ahşap", "tahta", "kontrplak", "wood", "meşe", "çam ağacı"],
     tur="kati", numune="thick_sheet", motor_benzeri="cotton", eslesme_gerekce="selüloz; kalibre selüloz pamuk (kalın, kömürleşen: ZAYIF eşleme)",
     desen=r"\bwood\b|red oak|douglas|pine", uzay="yer deneyi kutuları, kalıp; uçuşta nadiren", kategori="ambalaj/diğer",
     sfpe={"isil_deger_net": s("A.38", "Red oak", "17.1c", "MJ/kg", not_="kırmızı meşe; Douglas köknarı 16,4 (aynı tablo)")})
# KATI — yiyecek
ekle(id="flour", ad="Un", ad_en="Flour", es=["un", "buğday unu", "flour", "wheat flour"], tur="kati", numune="thick_sheet",
     motor_benzeri="cotton", eslesme_gerekce="nişasta/selüloz; kalibre selüloz pamuk (toz bulutu patlaması modellenmiyor: ZAYIF eşleme)",
     desen=r"flour", uzay="yiyecek (uçuşta un yok; tortilla kullanılır)", kategori="yiyecek",
     sfpe={"isil_deger": s("A.32", "Starch", "17.6", "MJ/kg", not_="nişasta satırı (un değil); aynı satırda 16,2 (brüt/net)")},
     notlar="Toz halinde havada asılıysa toz patlaması riski: bu araç modellemiyor.")
ekle(id="sugar", ad="Şeker", ad_en="Sugar (sucrose)", es=["şeker", "toz şeker", "sakkaroz", "sucrose", "sugar"], tur="kati",
     numune="thick_sheet", motor_benzeri="cotton", eslesme_gerekce="karbonhidrat; kalibre selüloz pamuk (ZAYIF eşleme)",
     desen=r"sugar|sucrose", uzay="yiyecek ve içecek tozu", sfpe={}, kategori="yiyecek")
ekle(id="fatty_food", ad="Yağlı yiyecek (genel)", ad_en="Fatty food (generic)",
     es=["yağlı yiyecek", "yağlı yemek", "tereyağı", "fıstık ezmesi", "fatty food"], tur="kati", numune="thick_sheet",
     motor_benzeri="pmma", eslesme_gerekce="eriyen yağ + yiyecek; kalibre malzeme yok (ZAYIF eşleme)", desen=r"fatty food|butter",
     uzay="yiyecek", kategori="yiyecek",
     sfpe={"isil_deger": s("A.32", "Fat, animal", "39.8", "MJ/kg", not_="saf hayvansal yağ; yiyeceğin yağ oranıyla azalır")})
# SIVI — pil elektroliti çözücüleri
ekle(id="dmc", ad="Dimetil karbonat (DMC)", ad_en="Dimethyl carbonate", es=["DMC", "dimetil karbonat", "dimethyl carbonate"],
     tur="sivi", numune="droplet", motor_benzeri="methanol",
     eslesme_gerekce="uçucu karbonat ester; damla motoru tanımıyor, en yakın oksijenli yakıt metanol (ZAYIF eşleme)",
     desen=r"dimethyl carbonate|\bdmc\b", uzay="Li-ion pil elektroliti çözücüsü", nist="dmc", sfpe={}, kategori="pil")
ekle(id="dec", ad="Dietil karbonat (DEC)", ad_en="Diethyl carbonate", es=["DEC", "dietil karbonat", "diethyl carbonate", "etil karbonat"],
     tur="sivi", numune="droplet", motor_benzeri="methanol", eslesme_gerekce="karbonat ester; damla motoru tanımıyor (ZAYIF eşleme)",
     desen=r"diethyl carbonate|\bdec\b", uzay="Li-ion pil elektroliti çözücüsü", nist="dec", kategori="pil",
     sfpe={"isil_deger_net": s("A.38", "Ethyl carbonate", "30.8", "MJ/kg")})
ekle(id="ec", ad="Etilen karbonat (EC)", ad_en="Ethylene carbonate", es=["EC", "etilen karbonat", "ethylene carbonate"],
     tur="sivi", numune="pool", motor_benzeri="methanol", eslesme_gerekce="az uçucu karbonat; damla motoru tanımıyor (ZAYIF eşleme)",
     desen=r"ethylene carbonate", uzay="Li-ion pil elektroliti çözücüsü", nist="ec", sfpe={}, kategori="pil",
     notlar="Oda sıcaklığında katıdır (erime ~36 °C); elektrolitte DMC/DEC ile çözelti halinde.")
# SIVI — yağ/akışkan
ekle(id="mineral_oil", ad="Mineral yağ", ad_en="Mineral oil", es=["mineral yağ", "parafin yağı", "vazelin yağı", "mineral oil"],
     tur="sivi", numune="pool", motor_benzeri="n-decane", eslesme_gerekce="ağır hidrokarbon karışımı; damla motorundaki en ağır alkan n-dekan (ZAYIF eşleme)",
     desen=r"mineral oil", uzay="yağlama, deney akışkanı", kategori="akışkan/yağ",
     sfpe={"isil_deger_net": s("A.39", "Mineral oil", "41.5", "MJ/kg", not_="ΔH_T; aynı tabloda ikinci satır 46,0")})
ekle(id="silicone_oil", ad="Silikon yağı", ad_en="Silicone oil (PDMS fluid)",
     es=["silikon yağı", "silikon sıvı", "PDMS yağı", "silicone oil", "silicone fluid"], tur="sivi", numune="pool",
     motor_benzeri=None, eslesme_gerekce="silikon sıvısı; damla/gaz motorlarında benzer yok: motor çalışmaz",
     desen=r"silicone (?:oil|fluid)", uzay="sönümleyici, ısıl akışkan, deney akışkanı", sfpe={}, kategori="akışkan/yağ")
ekle(id="glycerin", ad="Gliserin", ad_en="Glycerol", es=["gliserin", "gliserol", "glycerol", "glycerin", "glycerine"],
     tur="sivi", numune="pool", motor_benzeri="methanol", eslesme_gerekce="az uçucu poliol; damla motoru tanımıyor (ZAYIF eşleme)",
     desen=r"^glycer", uzay="deney akışkanı, kozmetik", nist="glycerol", kategori="akışkan/yağ",
     sfpe={"yogunluk": s("A.24", "Glycerin", "1,257.6", "kg/m3", not_="20 °C")})
ekle(id="ethylene_glycol", ad="Etilen glikol", ad_en="Ethylene glycol", es=["etilen glikol", "antifriz", "MEG", "ethylene glycol"],
     tur="sivi", numune="pool", motor_benzeri="methanol", eslesme_gerekce="suyla karışan glikol; damla motoru tanımıyor (ZAYIF eşleme)",
     desen=r"ethylene glycol", uzay="ısıl kontrol soğutucusu (su-glikol)", nist="ethylene-glycol", sfpe={}, kategori="akışkan/yağ")
ekle(id="pfpe", ad="PFPE yağı (Krytox)", ad_en="PFPE oil (Krytox, Fomblin)",
     es=["PFPE", "Krytox", "Fomblin", "perflorpolieter", "perfluoropolyether"], tur="sivi", numune="pool", motor_benzeri=None,
     eslesme_gerekce="tamamen florlu yağ: yanmaz", desen=r"pfpe|krytox|fomblin|perfluoropolyether",
     uzay="oksijen uyumlu yağlayıcı (vana, mekanizma)", sfpe={}, kategori="akışkan/yağ", ozel=YANMAZ,
     notlar="Yanmaz; çok yüksek sıcaklıkta bozunup zehirli florlu ürünler verebilir.")
# SIVI — yakıt/itici
ekle(id="udmh", ad="UDMH (itici)", ad_en="UDMH (unsymmetrical dimethylhydrazine)",
     es=["UDMH", "asimetrik dimetilhidrazin", "1,1-dimetilhidrazin", "unsymmetrical dimethylhydrazine"], tur="sivi",
     numune="pool", motor_benzeri=None, eslesme_gerekce="hipergolik itici; motorların hiçbiri uygun değil",
     desen=r"udmh|dimethylhydrazine", uzay="hipergolik itici (Proton, Soyuz/Progress manevra)", nist="udmh", sfpe={},
     kategori="yakıt/itici")
ekle(id="diesel", ad="Dizel", ad_en="Diesel fuel", es=["dizel", "motorin", "diesel", "diesel fuel"], tur="sivi",
     numune="droplet", motor_benzeri="n-decane", eslesme_gerekce="ağır hidrokarbon karışımı; n-dekan dizelden hafif (ZAYIF eşleme)",
     desen=r"diesel", uzay="yer jeneratörleri (uçuşta yok)", sfpe={}, kategori="yakıt/itici")
ekle(id="gasoline", ad="Benzin", ad_en="Gasoline", es=["benzin", "gasoline", "petrol", "gazolin"], tur="sivi",
     numune="droplet", motor_benzeri="n-heptane", eslesme_gerekce="karışım; benzinin standart vekili n-heptan (vekil, kalibre değil)",
     desen=r"gasoline", uzay="yerde (uçuşta yok)", kategori="yakıt/itici",
     sfpe={"isil_deger_net": s("A.32", "Gasoline", "43.7", "MJ/kg", not_="brüt 46,8 (aynı satır)"),
           "yogunluk": s("A.24", "Gasoline", "680.3", "kg/m3", not_="20 °C")})
ekle(id="ethyl_acetate", ad="Etil asetat", ad_en="Ethyl acetate", es=["etil asetat", "ethyl acetate", "EtOAc"], tur="sivi",
     numune="droplet", motor_benzeri="methanol", eslesme_gerekce="uçucu ester çözücü; damla motoru tanımıyor (ZAYIF eşleme)",
     desen=r"ethyl acetate", uzay="çözücü, yapıştırıcı inceltici", nist="ethyl-acetate", kategori="temizlik/çözücü",
     sfpe={"isil_deger_net": s("A.38", "Ethyl acetate", "23.9", "MJ/kg")})
# SIVI — temizlik / oksitleyici
ekle(id="hydrogen_peroxide", ad="Hidrojen peroksit", ad_en="Hydrogen peroxide",
     es=["hidrojen peroksit", "H2O2", "oksijenli su", "HTP", "hydrogen peroxide"], tur="sivi", numune="pool",
     motor_benzeri=None, eslesme_gerekce="oksitleyici; yakıt değil", desen=r"hydrogen peroxide|\bh2o2\b",
     uzay="dezenfektan; yüksek derişimde itici (HTP)", nist="hydrogen-peroxide", sfpe={}, kategori="temizlik/çözücü", ozel=OKS)
# GAZ
ekle(id="butane", ad="Bütan", ad_en="n-Butane", es=["bütan", "n-bütan", "çakmak gazı", "C4H10"], tur="gaz", numune="gas_jet",
     motor_benzeri="propane", eslesme_gerekce="gaz motoru bütanı propan vekiliyle çözüyor (kalibre değil)", desen=r"^n?-?butane",
     uzay="çakmak, kamp ocağı (uçuşta yasak)", nist="n-butane", sfpe={}, kategori="gaz")
ekle(id="isobutane", ad="İzobütan", ad_en="Isobutane", es=["izobütan", "isobutane", "R600a", "2-metilpropan"], tur="gaz",
     numune="gas_jet", motor_benzeri="propane", eslesme_gerekce="gaz motoru izobütanı tanımıyor; en yakın alkan propan (ZAYIF eşleme)",
     desen=r"isobutane", uzay="soğutucu gaz (R600a), aerosol itici", nist="isobutane", sfpe={}, kategori="gaz")
ekle(id="dme", ad="Dimetil eter (DME)", ad_en="Dimethyl ether", es=["dimetil eter", "metoksimetan", "dimethyl ether"],
     tur="gaz", numune="gas_jet", motor_benzeri="ethane", eslesme_gerekce="C2 oksijenli gaz; gaz motoru tanımıyor, en yakın C2 alkan etan (ZAYIF eşleme)",
     desen=r"dimethyl ether|^dme$", uzay="aerosol itici; soğuk alev deneyleri (ISS)", nist="dme", sfpe={}, kategori="gaz")
ekle(id="nitrous_oxide", ad="Nitröz oksit", ad_en="Nitrous oxide",
     es=["nitröz oksit", "diazot monoksit", "güldürücü gaz", "N2O", "nitrous oxide"], tur="gaz", numune="gas_jet",
     motor_benzeri=None, eslesme_gerekce="oksitleyici; yakıt değil", desen=r"nitrous oxide|^n2o$",
     uzay="hibrit roket oksitleyicisi; tıbbi gaz", nist="nitrous-oxide", sfpe={}, kategori="gaz", ozel=OKS)
ekle(id="formaldehyde", ad="Formaldehit", ad_en="Formaldehyde", es=["formaldehit", "metanal", "HCHO", "formaldehyde"],
     tur="gaz", numune="gas_jet", motor_benzeri="methane", eslesme_gerekce="C1 oksijenli gaz; gaz motoru tanımıyor (ZAYIF eşleme)",
     desen=r"formaldehyde", uzay="kabin havasında iz kirletici (malzeme gaz salımı)", nist="formaldehyde", sfpe={}, kategori="gaz")
ekle(id="hydrogen_sulfide", ad="Hidrojen sülfür", ad_en="Hydrogen sulfide", es=["hidrojen sülfür", "kükürtlü hidrojen", "H2S", "hydrogen sulfide"],
     tur="gaz", numune="gas_jet", motor_benzeri=None, eslesme_gerekce="kükürtlü gaz; motorlarda kükürt kimyası yok: motor çalışmaz",
     desen=r"hydrogen sulfide|^h2s$", uzay="atık su / atık işleme gazı", nist="hydrogen-sulfide", sfpe={}, kategori="gaz")
# ÖZEL — oksitleyici / yanmaz / pil
ekle(id="oxygen", ad="Oksijen", ad_en="Oxygen", es=["oksijen", "O2", "saf oksijen", "oxygen", "LOX", "sıvı oksijen"], tur="gaz",
     numune="gas_jet", motor_benzeri=None, eslesme_gerekce="oksitleyici; yakıt değil (ortam oksijeni 'oksijen' girdisiyle verilir)",
     desen=r"^oxygen$|^o2$", uzay="kabin atmosferi, solunum, oksijen tüpleri ve jeneratörleri", nist="oxygen", sfpe={},
     kategori="gaz", ozel=OKS)
ekle(id="fiberglass", ad="Cam elyaf (saf)", ad_en="Glass fiber (bare)",
     es=["cam elyaf", "cam lifi", "cam yünü", "fiberglass", "glass fiber", "glass wool"], tur="kati", numune="fabric",
     motor_benzeri=None, eslesme_gerekce="inorganik cam: yanmaz", desen=r"^fiberglass$|glass wool|^glass fiber$",
     uzay="yalıtım, kompozit takviyesi, Beta kumaşının özü", sfpe={}, kategori="kompozit/yapı", ozel=YANMAZ,
     notlar="Kaplamalı/reçineli hali yanabilir: 'Cam elyaf kumaş (Beta kumaşı)' ve 'GFRP' kayıtları.")
ekle(id="aluminum", ad="Alüminyum", ad_en="Aluminium", es=["alüminyum", "aluminum", "aluminium", "alüminyum folyo", "aluminum foil"],
     tur="kati", numune="thin_sheet", motor_benzeri=None, eslesme_gerekce="metal levha/folyo: bu araçta yanıcı değil",
     desen=r"^alumin(?:um|ium)$", uzay="basınçlı modül gövdesi, raf, folyo", sfpe={}, kategori="kompozit/yapı", ozel=YANMAZ,
     notlar="Levha ve folyo havada yanmaz. İnce toz/talaş yanar (veri setinde alüminyum tozu/parçacığı yanma noktaları var; bu kayda sayılmadı) — bu araç metal yanmasını modellemiyor.")
ekle(id="li_ion_cell", ad="Li-ion pil hücresi", ad_en="Lithium-ion cell",
     es=["Li-ion", "lityum iyon pil", "lityum pil", "pil hücresi", "18650", "batarya", "lithium-ion battery", "li-ion pil"],
     tur="kati", numune="thick_sheet", motor_benzeri=None, eslesme_gerekce="pil hücresi: termal kaçak modeli yok, motor yok",
     desen=r"lithium|li-ion", uzay="dizüstü bilgisayar, kamera, EVA giysi ve araç bataryaları", sfpe={}, kategori="pil",
     ozel=PIL, notlar="Elektrolit çözücüleri için DMC / DEC / EC kayıtları.")


# ilk 44 malzemenin kategorisi (2. genişletmede eklendi; özellikleri değişmedi)
KATEGORI_ESKI = {
    "pmma": "plastik", "polycarbonate": "plastik", "polyethylene": "plastik", "polypropylene": "plastik",
    "nylon": "kıyafet/kumaş", "nomex": "kıyafet/kumaş", "kevlar": "kıyafet/kumaş", "ptfe": "plastik",
    "kapton": "elektronik/kablo", "peek": "plastik", "ultem": "plastik", "silicone": "kauçuk/conta",
    "viton": "kauçuk/conta", "neoprene": "kauçuk/conta", "pu_foam": "yalıtım/köpük", "melamine_foam": "yalıtım/köpük",
    "pvdf_foam": "yalıtım/köpük", "cotton": "kıyafet/kumaş", "sibal": "kıyafet/kumaş", "beta_cloth": "kıyafet/kumaş",
    "paper": "ambalaj/diğer", "cardboard": "ambalaj/diğer", "fr4": "elektronik/kablo", "etfe": "elektronik/kablo",
    "abs": "plastik", "pla": "plastik", "ethanol": "temizlik/çözücü", "isopropanol": "temizlik/çözücü",
    "methanol": "yakıt/itici", "n-heptane": "yakıt/itici", "n-decane": "yakıt/itici", "acetone": "temizlik/çözücü",
    "kerosene": "yakıt/itici", "hydraulic_oil": "akışkan/yağ", "propylene_glycol": "akışkan/yağ",
    "hydrazine": "yakıt/itici", "hydrogen": "gaz", "methane": "gaz", "ethylene": "gaz", "ethane": "gaz", "propane": "gaz",
    "carbon_monoxide": "gaz", "ammonia": "gaz", "acetylene": "gaz",
}

# ------------------------------------------------------------------ kaynak denetimi
_metin_onbellek = {}


def tablo_satirlari(tablo):
    dosya, bas, son, _ = TABLO[tablo]
    if dosya not in _metin_onbellek:
        _metin_onbellek[dosya] = (METIN / dosya).read_text(encoding="utf-8").split("\n")   # sed satır numaralarıyla aynı
    return [x.strip() for x in _metin_onbellek[dosya][bas - 1:son]]


# değerin etiketten kaç hücre sonra geldiği (tablo sütun düzeni); listede olmayan tabloda 8 hücrelik pencere
SUTUN = {"A.38": 2, "A.39": 1, "36.5": 3, "A.24": 2}


def denetle(oz):
    """SFPE değeri: etiket satırı tablo bölgesinde var mı; değer metni doğru sütunda (SUTUN) ya da
    etiketten sonraki 8 satır içinde AYNEN geçiyor mu."""
    L = tablo_satirlari(oz["tablo"])
    for i, x in enumerate(L):
        if x == oz["etiket"] or x.startswith(oz["etiket"]):
            pencere = " | ".join(L[i:i + 9])
            if oz.get("tur") == "A36" or (oz["tablo"] not in SUTUN and not oz.get("ofset")):
                if oz["metin"] in pencere:
                    return pencere
            elif i + (oz.get("ofset") or SUTUN[oz["tablo"]]) < len(L) and L[i + (oz.get("ofset") or SUTUN[oz["tablo"]])] == oz["metin"]:
                return pencere
    raise SystemExit(f"KAYNAK DENETİMİ BAŞARISIZ: Tablo {oz['tablo']} '{oz['etiket']}' -> '{oz['metin']}' bulunamadı")


def sayi_araligi(metin):
    """'0.94–0.96' -> (0.94, 0.96); '25.2c' -> (25.2, 25.2)."""
    xs = [float(v) for v in re.findall(r"\d+(?:\.\d+)?", metin.replace(",", ""))]
    return (min(xs), max(xs)) if xs else (None, None)


def sfpe_deger(ad, oz):
    pencere = denetle(oz)
    if oz.get("tur") == "A36":
        # A.36 sütunları: Tig (°C) | ρ (10^3 kg/m3) | cP | k | TRP. Tig ve ρ bazen aynı OCR satırında ("378–383 1.19").
        L = [p.strip() for p in pencere.split("|")]
        i = next(j for j, x in enumerate(L) if x.startswith(oz["etiket"]))
        hucre = L[i + 1:i + 6]
        if hucre[0] == "–":                      # Tig yok
            rho_metni = hucre[1]
        elif " " in hucre[0]:                     # "Tig ρ" aynı hücrede
            rho_metni = hucre[0].split()[-1]
        elif max(sayi_araligi(hucre[0])) > 50:   # Tig ayrı hücre (°C)
            rho_metni = hucre[1]
        else:
            rho_metni = hucre[0]
        lo, hi = sayi_araligi(rho_metni)
        return {"deger": round(1000 * (lo + hi) / 2, 1), "aralik": [round(1000 * lo, 1), round(1000 * hi, 1)],
                "birim": "kg/m3", "kaynak": TABLO["A.36"][3], "kaynak_metni": oz["etiket"] + " … ρ = " + rho_metni + " ×10³",
                "not": oz.get("not")}
    lo, hi = sayi_araligi(oz["metin"])
    if oz["birim"] == "10^3 kg/m3":
        lo, hi, birim = 1000 * lo, 1000 * hi, "kg/m3"
    else:
        birim = oz["birim"]
    return {"deger": round((lo + hi) / 2, 3), "aralik": [lo, hi] if lo != hi else None, "birim": birim,
            "kaynak": TABLO[oz["tablo"]][3], "kaynak_metni": f"{oz['etiket']} … {oz['metin']}", "not": oz.get("not")}


# ------------------------------------------------------------------ NIST seçimi
def nist_sec(kayit, yogun_faz):
    """Seçim kuralları (değer değiştirilmez):
      Tboil: 'AVG' yöntemli satır, yoksa ilk satır.  ΔvapH°: önce 'ΔvapH°' (298 K) AVG/ilk; yoksa 'ΔvapH' ilk.
      ΔcH°: sıvıda 'ΔcH°liquid', gazda 'ΔcH°gas' — ilk satır (NIST'in ilk sıraladığı)."""
    def bul(tablo, adlar, tercih_avg=True):
        satir = [r for r in kayit.get(tablo, []) if r[0].replace(" ", "") in adlar]   # NIST: "Δ c H° liquid"
        if not satir:
            return None
        avg = [r for r in satir if len(r) > 3 and r[3] == "AVG"]
        return (avg or satir)[0] if tercih_avg else satir[0]

    def deger(r):
        v = re.match(r"\s*(-?[\d.]+)\s*(?:±\s*([\d.]+))?", r[1])
        return (float(v.group(1)), float(v.group(2)) if v.group(2) else None) if v else (None, None)

    sonuc = {}
    M = kayit.get("molar_kutle")
    r = bul("faz_degisimi", ("Tboil",))
    if r:
        v, e = deger(r)
        sonuc["kaynama_K"] = {"deger": v, "belirsizlik": e, "birim": r[2], "yontem": r[3] if len(r) > 3 else None,
                              "nist_kaynak": r[4] if len(r) > 4 else None}
    r = bul("faz_degisimi", ("ΔvapH°",)) or bul("faz_degisimi", ("ΔvapH",))
    if r:
        v, e = deger(r)
        sonuc["buharlasma_isisi"] = {"deger_kJ_mol": v, "belirsizlik": e,
                                     "deger": round(1000 * v / M, 1) if (v and M) else None, "birim": "kJ/kg",
                                     "nicelik": r[0], "yontem": r[3] if len(r) > 3 else None,
                                     "nist_kaynak": r[4] if len(r) > 4 else None,
                                     "not": r[5] if len(r) > 5 else None}
    ad = "ΔcH°liquid" if yogun_faz else "ΔcH°gas"
    r = bul("yogun_termo" if yogun_faz else "gaz_termo", (ad,), tercih_avg=False)
    if r:
        v, e = deger(r)
        sonuc["isil_deger_brut"] = {"deger": round(-v / M, 3) if (v and M) else None, "birim": "MJ/kg",
                                    "deger_kJ_mol": v, "nicelik": ad, "yontem": r[3] if len(r) > 3 else None,
                                    "nist_kaynak": r[4] if len(r) > 4 else None,
                                    "not": "standart yanma entalpisi (ürün su sıvı) = brüt/üst ısıl değer"}
    return sonuc


# ------------------------------------------------------------------ veri seti
def veri_seti_sayimi():
    import pandas as pd
    k = pd.read_csv(KOK / "motor_karsilastirma.csv", low_memory=False, usecols=["malzeme_sade", "etiket_kaynagi", "kalinlik_mm", "numune_tipi"])
    k["ad"] = k.malzeme_sade.astype(str).str.lower().str.strip()
    k["kalibrasyon"] = k.etiket_kaynagi.isin(["psi", "makale_elle"])
    karisim = re.compile(r"/|\+|&|%|–| and | with |mixture|blend|diluted")
    return k, karisim


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--denetle", action="store_true")
    arg = a.parse_args()
    nist = json.loads(NIST_HAM.read_text(encoding="utf-8")) if NIST_HAM.exists() else {"maddeler": {}}
    chem = json.loads(CHEM_HAM.read_text(encoding="utf-8")) if CHEM_HAM.exists() else {"maddeler": {}, "kaynak": ""}
    if not nist["maddeler"]:
        print("UYARI: NIST ham verisi yok; önce deneyler/malzeme_nist_cek.py", file=sys.stderr)
    sys.path.insert(0, str(KOK))
    import damla_motoru as dm
    import gaz_motoru as gm
    k, karisim = veri_seti_sayimi()
    bre = 0
    try:
        import pandas as pd
        bre = len(pd.read_csv(KOK / "gaz_veri" / "bre_dehghani2021_tablo2.csv"))
    except Exception:  # noqa: BLE001
        pass
    import tahmin
    varsay = tahmin.MALZEME_VARSAYILAN

    liste = []
    for m in M:
        oz = {}
        for alan, kaynak in (m.get("sfpe") or {}).items():
            oz[alan] = sfpe_deger(m["id"], kaynak)
        if m.get("damla"):
            y = dm.YAKIT[m["damla"]]
            oz["yogunluk_kaynamaya_yakin"] = {"deger": y["rho"], "birim": "kg/m3", "kaynak": "damla_motoru.py YAKIT tablosu "
                              "(NIST WebBook / Yaws 2003 / Perry's 8. baskı)", "not": "kaynama noktasına yakın sıcaklıkta"}
        for anahtar in [x for x in (m.get("nist"), m.get("nist_ek")) if x]:
            kayit = nist["maddeler"].get(anahtar)
            if not kayit:
                continue
            secim = nist_sec(kayit, m["tur"] != "gaz")
            ek = "" if anahtar == m.get("nist") else f"_{anahtar}"
            for alan, v in secim.items():
                v["kaynak"] = f"NIST Chemistry WebBook (SRD 69), {kayit['adres']}"
                oz[alan + ek] = v
            oz["molar_kutle" + ek] = {"deger": kayit.get("molar_kutle"), "birim": "g/mol",
                                      "kaynak": f"NIST Chemistry WebBook (SRD 69), {kayit['adres']}"}
        # chemicals: boş alanları doldurur; parlama noktası, tutuşma sıcaklığı, Tc, LFL/UFL hep buradan
        for anahtar in [x for x in (m.get("nist"), m.get("nist_ek")) if x]:
            kc = chem["maddeler"].get(anahtar)
            if not kc:
                continue
            ek = "" if anahtar == m.get("nist") else f"_{anahtar}"
            kay = lambda alt: f"{chem['kaynak']}, alt kaynak: {alt}"   # noqa: E731
            mw = kc["MW"]

            def koy(alan, deger, birim, alt, not_=None, zorla=False):
                if deger is None or (not zorla and (alan + ek) in oz):
                    return
                oz[alan + ek] = {"deger": round(deger, 3), "birim": birim, "kaynak": kay(alt), "not": not_}
            if kc.get("Tb") and kc["Tb"][0]:
                koy("kaynama_K", kc["Tb"][0], "K", kc["Tb"][1])
            if kc.get("Tc") and kc["Tc"][0]:
                koy("kritik_sicaklik_K", kc["Tc"][0], "K", kc["Tc"][1])
            hv = kc.get("Hvap_CRC") or {}
            if hv.get("Hvap298_J_mol"):
                koy("buharlasma_isisi", hv["Hvap298_J_mol"] / mw, "kJ/kg", hv["tablo"], "298 K")
            elif hv.get("HvapTb_J_mol"):
                koy("buharlasma_isisi", hv["HvapTb_J_mol"] / mw, "kJ/kg", hv["tablo"], "kaynama noktasında")
            h = kc.get("HHV") or {}
            if h.get("J_mol"):
                koy("isil_deger_brut", -h["J_mol"] / mw / 1000, "MJ/kg", f"combustion_data, Hf: {h['Hf_kaynak']}",
                    "oluşum entalpisinden hesaplanmış (ürün su sıvı)")
                koy("isil_deger_net", -h["LHV_J_mol"] / mw / 1000, "MJ/kg", f"combustion_data, Hf: {h['Hf_kaynak']}",
                    "oluşum entalpisinden hesaplanmış (ürün su buhar)")
            if kc.get("rho_l_298"):
                koy("yogunluk", kc["rho_l_298"][0], "kg/m3", kc["rho_l_298"][1], "sıvı, 298,15 K")
            if kc.get("T_flash") and kc["T_flash"][0]:
                koy("parlama_noktasi_K", kc["T_flash"][0], "K", kc["T_flash"][1])
            if kc.get("T_autoignition") and kc["T_autoignition"][0]:
                koy("kendiliginden_tutusma_K", kc["T_autoignition"][0], "K", kc["T_autoignition"][1])
            if kc.get("LFL") and kc["LFL"][0] is not None:
                koy("LFL", 100 * kc["LFL"][0], "% hacim", kc["LFL"][1], "havada, alt yanma sınırı")
            if kc.get("UFL") and kc["UFL"][0] is not None:
                koy("UFL", 100 * kc["UFL"][0], "% hacim", kc["UFL"][1], "havada, üst yanma sınırı")
        # veri seti
        d = re.compile(m["desen"])
        es = k[k.ad.str.contains(d, regex=True)]
        saf = es[~es.ad.str.contains(karisim, regex=True)]
        adlar = es.ad.value_counts()
        kal = int(saf.kalibrasyon.sum())
        n_saf, n_tum = len(saf), len(es)
        # durum
        if m["tur"] == "sivi" and m.get("damla") in dm.KALIBRE_YAKITLAR:
            durum = "motorda kalibre"
            durum_ayr = "damla motoru FLEX verisiyle kalibre"
        elif m["tur"] == "gaz" and m["id"] == "ethylene":
            durum = "motorda kalibre"
            durum_ayr = f"gaz motoru BRE verisiyle kalibre ({bre} ISS testi, gaz_veri/)"
        elif m["tur"] == "kati" and kal > 0:
            durum = "motorda kalibre"
            durum_ayr = f"hafif motor kalibrasyon verisinde {kal} PSI/elle nokta (geometri grubu kalibrasyonu)"
        elif n_saf > 0:
            durum = f"veri setinde {n_saf} nokta var"
            durum_ayr = "modelin eğitim verisinde; motor bu malzemeye kalibre değil"
        else:
            durum = "veri yok"
            durum_ayr = "veri setinde nokta yok" + (f" (yalnız karışım/kompozit içinde {n_tum} nokta)" if n_tum else "")
        # varsayılan numune ve kalınlık
        num, kal_mm, kal_k = m["numune"], None, None
        if m["tur"] == "gaz":                    # gaz: numune tipi verilmezse sızıntı (küre); debi bilinmez (tahmin.py)
            num, kal_k = "porous_sphere", "bizim seçimimiz: sızıntı (küre); numune tipi verilmezse gaz motoru kullanılmaz"
        elif m["id"] in varsay:
            num, kal_mm = varsay[m["id"]][0], varsay[m["id"]][1]
            kal_k = "tahmin.py MALZEME_VARSAYILAN"
        elif saf.kalinlik_mm.notna().sum() >= 3:
            kal_mm = round(float(saf.kalinlik_mm.median()), 3)
            kal_k = f"veri setindeki {int(saf.kalinlik_mm.notna().sum())} noktanın kalınlık/çap medyanı"
        elif m.get("motor_benzeri") in varsay and varsay[m["motor_benzeri"]][0] == num and m["tur"] != "gaz":
            kal_mm = varsay[m["motor_benzeri"]][1]
            kal_k = f"benzer malzemenin ({m['motor_benzeri']}, aynı numune tipi) varsayılanı — tahmin.py MALZEME_VARSAYILAN"
        motor_tanir = None
        if m["tur"] == "sivi":
            motor_tanir = m["id"] in dm.MALZEME_ADI or (m.get("motor_benzeri") or "") in dm.MALZEME_ADI
        elif m["tur"] == "gaz":
            motor_tanir = any(a == m["id"] for a, _ in gm.YAKIT_ADLARI)
        if (m.get("ozel") or {}).get("tur") == "oksitleyici":   # oksitleyicinin "yanma ısısı" yanıltıcı: gösterilmez
            oz = {k_: v_ for k_, v_ in oz.items() if not k_.startswith("isil_deger")}
        if m.get("ozel"):
            durum_ayr = m["ozel"]["uyari"] + "; " + durum_ayr
        liste.append({
            "id": m["id"], "ad": m["ad"], "ad_en": m["ad_en"], "es_anlamlilar": m["es"], "yakit_turu": m["tur"],
            "kategori": m.get("kategori") or KATEGORI_ESKI[m["id"]], "ozel": m.get("ozel"),
            "varsayilan": {"numune_tipi": num, "kalinlik_veya_cap_mm": kal_mm, "kaynak": kal_k or "bizim seçimimiz (numune tipi)"},
            "motor_benzeri": m.get("motor_benzeri"), "eslesme_gerekce": m["eslesme_gerekce"],
            "motor_kendisini_taniyor": motor_tanir,
            "ozellikler": oz, "durum": durum, "durum_ayrinti": durum_ayr,
            "veri_seti": {"nokta": n_saf, "nokta_karisim_dahil": n_tum, "kalibrasyon_noktasi": kal,
                          "eslesen_adlar": {str(a): int(b) for a, b in adlar.head(12).items()}},
            "uzayda_kullanim": m["uzay"], "notlar": m.get("notlar"),
        })
    cikti = {
        "aciklama": "Yerleşik malzeme kütüphanesi (malzeme_kutuphanesi_uret.py ile üretildi). Özellikler yalnız "
                    "kaynaklı değerlerdir; boş alan = kaynakta bulunamadı. Modele ve motor kalibrasyonuna girmez.",
        "kaynaklar": {"NIST": "NIST Chemistry WebBook, NIST SRD 69 (webbook.nist.gov); çekim "
                              + str(nist.get("cekim")) + "; ham veri deneyler/malzeme_nist_ham.json",
                      "SFPE": {k_: v[3] for k_, v in TABLO.items()},
                      "veri_seti": "motor_karsilastirma.csv (ad eşleşmesi; 'nokta' karışım/kompozit adları hariç)"},
        "alanlar": {"isil_deger_net": "net (alt) ısıl değer, ΔH_T, MJ/kg (SFPE)",
                    "isil_deger_brut": "brüt (üst) ısıl değer = −ΔcH°/M, MJ/kg (NIST)",
                    "isil_deger": "SFPE A.32 tek değer (brüt/net belirsiz)", "yogunluk": "kg/m3",
                    "kaynama_K": "1 atm kaynama noktası (NIST)", "buharlasma_isisi": "ΔvapH (NIST), kJ/kg",
                    "LOI": "sınırlayıcı oksijen indeksi, % (SFPE Tablo 36.5)",
                    "parlama_noktasi_K": "parlama noktası (chemicals: IEC 60079-20-1 / NFPA 497 / DIPPR)",
                    "kendiliginden_tutusma_K": "kendiliğinden tutuşma sıcaklığı (chemicals)",
                    "LFL": "havada alt yanma sınırı, % hacim (chemicals)", "UFL": "havada üst yanma sınırı, % hacim (chemicals)",
                    "kritik_sicaklik_K": "kritik sıcaklık (chemicals)",
                    "yogunluk_kaynamaya_yakin": "sıvı yoğunluğu, kaynamaya yakın sıcaklıkta (damla_motoru.py)",
                    "kategori": "kullanım grubu (arayüz süzgeci)",
                    "ozel": "yakıt olarak çözülmeyen malzeme: tur = oksitleyici | yanmaz | pil; tahmin sayı üretmeden uyarır"},
        "malzemeler": liste,
    }
    # eş anlamlı çakışması: tahmin.py ilk kaydı alır; çakışma varsa dur
    sys.path.insert(0, str(KOK))
    from tahmin import _ad_norm
    gor = {}
    for x in liste:
        for a in {_ad_norm(v) for v in [x["id"], x["ad"], x["ad_en"]] + x["es_anlamlilar"]}:
            if a in gor and gor[a] != x["id"]:
                raise SystemExit(f"EŞ ANLAMLI ÇAKIŞMASI: '{a}' hem {gor[a]} hem {x['id']}")
            gor[a] = x["id"]
    from collections import Counter
    cikti["sayim"] = {"toplam": len(liste), "kategori": dict(Counter(x["kategori"] for x in liste)),
                      "yakit_turu": dict(Counter(x["yakit_turu"] for x in liste)),
                      "ozel": dict(Counter(x["ozel"]["tur"] for x in liste if x["ozel"])),
                      "durum": dict(Counter(x["durum"] if not x["durum"].startswith("veri setinde") else "veri setinde N nokta"
                                            for x in liste))}
    if arg.denetle:
        print(f"denetim tamam: {len(liste)} malzeme, "
              f"{sum(len([o for o in x['ozellikler'].values()]) for x in liste)} kaynaklı özellik")
        return
    CIKTI.write_text(json.dumps(cikti, ensure_ascii=False, indent=1), encoding="utf-8")
    for x in liste:
        print(f"{x['id']:18s} {x['yakit_turu']:5s} {x['durum']:28s} motor≈{str(x['motor_benzeri']):11s} "
              f"özellik: {', '.join(sorted(x['ozellikler'])) or '-'}")
    print(f"yazıldı: {CIKTI.name} ({len(liste)} malzeme)")


if __name__ == "__main__":
    main()
