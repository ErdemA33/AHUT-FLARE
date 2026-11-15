"use strict";
/* AHUT FLARE — dil katmanı (TR / EN).
   Ekrandaki her metin buradan gelir:
     - HTML'de  data-d="anahtar"        (textContent)
     - HTML'de  data-d-ph="anahtar"     (placeholder)
     - HTML'de  data-d-t="anahtar"      (title)
     - JS'te    T("anahtar", {ad: deger})
   Backend'den gelen uyarı metinleri Türkçedir; İngilizce modda oldukları gibi
   gösterilir ve başlarına "model warning" etiketi konur (uydurma çeviri yapılmaz). */

const SOZLUK = {
  tr: {
    "menu.dosya": "Dosya", "menu.duzen": "Düzen", "menu.gorunum": "Görünüm",
    "menu.birimler": "Birimler", "menu.araclar": "Araçlar", "menu.profil": "Profil", "menu.yardim": "Yardım",

    "komut.yeni": "Yeni Vaka", "komut.yeniK": "Yeni",
    "komut.ac": "Vaka Aç…", "komut.acK": "Aç",
    "komut.kaydet": "Kütüphaneye Kaydet", "komut.kaydetK": "Kaydet",
    "komut.ice": "İçe Aktar (.ahut)…", "komut.disa": "Dışa Aktar (.ahut)…",
    "komut.rapor": "Rapor Oluştur…", "komut.raporK": "Rapor", "komut.paylasK": "Paylaş",
    "komut.klasorVeri": "Veri Klasörünü Aç", "komut.klasorRender": "Render Klasörünü Aç",
    "komut.cikis": "Çıkış", "komut.sifirla": "Girdileri Varsayılana Döndür",
    "komut.onayarIss": "Ön Ayar: ISS", "komut.onayarMars": "Ön Ayar: Mars Üssü", "komut.onayarAy": "Ön Ayar: Ay Üssü",
    "komut.tema": "Koyu Tema", "komut.temaAcik": "Açık Tema", "komut.temaKoyu": "Koyu Tema",
    "komut.sunum": "Sunum Modu", "komut.sunumK": "Sunum", "komut.tamekran": "Tam Ekran",
    "komut.panelSifirla": "Panel Düzenini Sıfırla",
    "komut.coz": "Çöz", "komut.cozK": "ÇÖZ",
    "komut.llm": "Yapay Zeka Yorumu İste", "komut.llmK": "Yorum",
    "komut.karsilastir": "Vaka Karşılaştır…", "komut.supur": "Parametre Süpürmesi…",
    "gh.baslik": "Paylaşım deposu (GitHub)",
    "gh.depo": "Depo", "gh.jeton": "Erişim jetonu",
    "gh.depoIpucu": "kullanici/depo — örn. Nikire55/ahut-flare",
    "gh.jetonIpucu": "Yalnızca bu bilgisayarda saklanır, paylaşılan dosyaya girmez. Silmek için tek tire (-) yazın.",
    "gh.jetonVar": "jeton kayıtlı — değiştirmek için yeni jetonu yapıştırın",
    "gh.sina": "Bağlantıyı Sına", "gh.siteKur": "Siteyi Kur",
    "gh.sinaniyor": "Sınanıyor…", "gh.kuruluyor": "Site kuruluyor…",
    "gh.baglandi": "Bağlandı", "gh.siteAdresi": "Site adresi",
    "gh.paylas": "GitHub'da Paylaş", "gh.paylasiliyor": "Paylaşılıyor…",
    "gh.paylasildi": "Vaka paylaşıldı", "gh.guncellendi": "Vaka güncellendi",
    "gh.siteAc": "Sitede aç", "gh.githubAc": "GitHub'da aç", "gh.panoyaKopyala": "Bağlantıyı kopyala",
    "gh.canli": "canlı", "gh.cevrimdisi": "çevrimdışı", "gh.yerelKaynak": "yalnızca yerel örnekler",
    "gh.tazele": "Yenile", "gh.sonGuncelleme": "son güncelleme",
    "gh.kurulumYok": "Paylaşım deposu tanımlı değil",
    "gh.kurulumYokAlt": "Profil ekranından GitHub deposunu ve jetonunu girin; vakalarınız o depoya yüklenir ve GitHub Pages sitesinde yayımlanır.",
    "gh.al": "Kütüphaneme al", "gh.alindi": "Vaka kütüphaneye eklendi",
    "gh.siteKuruldu": "Site kuruldu", "gh.siteDegismedi": "Site zaten güncel",
 "komut.json": "Ham Sonucu JSON Olarak Göster",
    "komut.profilDuzenle": "Profili Düzenle…", "komut.gitKutuphane": "Vaka Kütüphanem",
    "komut.gitTopluluk": "Topluluk", "komut.gitBaslangic": "Başlangıç Ekranı",
    "komut.kisayollar": "Klavye Kısayolları", "komut.hakkinda": "Hakkında",

    "sekme.baslangic": "Başlangıç", "sekme.calisma": "Model",
    "sekme.kutuphane": "Kütüphane", "sekme.topluluk": "Topluluk",

    "panel.anahat": "Anahat", "panel.ayrintilar": "Ayrıntılar", "panel.mesajlar": "Mesajlar",
    "panel.tablo": "Tablo Verisi", "panel.grafik": "Grafik", "panel.gunluk": "Günlük", "panel.sistem": "Sistem",

    "birim.basinc": "Basınç", "birim.akis": "Hava akışı",

    "agac.ortam": "Ortam", "agac.malzeme": "Malzeme", "agac.akis": "Akış",
    "agac.cozumAyar": "Analiz Ayarları", "agac.ofm": "Ayrıntılı Motor (OpenFOAM)", "agac.sonuc3b": "3B Alan Sonucu",
    "agac.proje": "Proje", "agac.model": "Model", "agac.numune": "Numune / Geometri", "agac.cozum": "Çözüm İzleyici",
    "agac.adimlar": "Analiz Adımları",
    "agac.ozet": "Risk Özeti", "agac.oksijen": "Oksijen Eğrisi", "agac.harita": "Yanabilirlik Haritası",
    "agac.akisEgrisi": "Akış Eğrisi", "agac.deneyler": "Yakın Deneyler", "agac.guven": "Güven Analizi",
    "agac.sinirlama": "Yerçekimi Sınırlaması", "agac.llm": "Yapay Zeka Yorumu", "agac.render": "Render Görüntüsü",
    "agac.dunya": "Dünya Uygulamaları",

    "alan.onayar": "Ortam ön ayarı", "alan.g": "Yerçekimi", "alan.basinc": "Basınç",
    "alan.oksijen": "Oksijen", "alan.seyreltici": "Ortam gazı (seyreltici)",
    "alan.malzeme": "Malzeme", "alan.numune": "Numune tipi", "alan.kalinlik": "Kalınlık",
    "alan.yakit": "Yakıt türü", "alan.akisBilinmiyor": "Akış bilinmiyor", "alan.akis": "Hava akışı",
    "alan.akisYonu": "Akış yönü", "alan.motor": "Fizik motoru", "alan.llmIste": "Yapay zeka yorumu",
    "alan.baslik": "Başlık", "alan.aciklama": "Açıklama", "alan.etiketler": "Etiketler",

    "ipucu.g": "Dünya = 1 · ISS ≈ 1e-4 · Ay = 0,165 · Mars = 0,38",
    "ipucu.akis": "0 = durgun ortam. “Bilinmiyor” ile aynı şey değildir.",
    "ipucu.akisBilinmiyor": "İşaretliyken en kötü durum (akış var) varsayılır.",
    "ipucu.varsayilan": "Boş bırakılırsa malzeme varsayılanı kullanılır.",

    "durum.motorYukleniyor": "Model yükleniyor…", "durum.motorHazir": "Model hazır",
    "durum.motorHata": "Model yüklenemedi", "durum.motorMock": "SAHTE VERİ modu",
    "durum.cozuluyor": "Çözülüyor…", "durum.bosta": "Boşta",
    "durum.vakaYok": "Kaydedilmemiş vaka", "durum.kirli": "kaydedilmedi",

    "genel.profilYok": "Profil tanımlı değil", "genel.kapat": "Kapat", "genel.iptal": "İptal",
    "genel.tamam": "Tamam", "genel.kaydet": "Kaydet", "genel.sil": "Sil", "genel.ac": "Aç",
    "genel.hepsi": "Hepsi", "genel.ara": "Ara…", "genel.yok": "yok", "genel.hesaplanamadi": "hesaplanamadı",
    "genel.bulunamadi": "bulunamadı", "genel.bilinmiyor": "bilinmiyor",

    "bas.slogan": "Mikro yerçekiminde yangın güvenliği analiz ortamı",
    "bas.ozet": "NASA PSI mikro yerçekimi yanma deneylerinden öğrenilmiş bir risk modelini, yarı-ampirik bir fizik motoruyla birlikte çalıştırır; uzay aracı kabinleri ile Ay ve Mars üsleri için malzeme yanabilirlik kararı üretir.",
    "bas.hizli": "Hızlı başlangıç", "bas.nasil": "Nasıl çalışır", "bas.sonVakalar": "Son vakalar",
    "bas.sistem": "Sistem", "bas.veri": "Veri ve yöntem",
    "bas.yeniVaka": "Yeni vaka kur", "bas.yeniVakaAlt": "Ortam ve malzeme değerlerini kendin gir",
    "bas.ornekIss": "Örnek: ISS kabini", "bas.ornekIssAlt": "Mikro yerçekimi, %21 O₂, 101,3 kPa, PMMA",
    "bas.ornekMars": "Örnek: Mars üssü", "bas.ornekMarsAlt": "g = 0,38 · kısmi yerçekimi sınırlaması",
    "bas.kutuphane": "Kütüphaneyi aç", "bas.kutuphaneAlt": "Kayıtlı vakaların ve paylaşıma hazır dosyalar",
    "bas.adim1": "Vakayı kur", "bas.adim1Alt": "Yerçekimi, basınç, oksijen, malzeme ve akış değerlerini ağaçtaki Ayrıntılar tablosuna gir.",
    "bas.adim2": "Çöz", "bas.adim2Alt": "Risk modeli ve fizik motoru aynı koşulu bağımsız olarak değerlendirir.",
    "bas.adim3": "Sonucu oku", "bas.adim3Alt": "Risk seviyesi, güvenlik katsayısı ve güven skoru; eksik girdiler açıkça işaretlenir.",
    "bas.adim4": "Kaydet ve paylaş", "bas.adim4Alt": "Vaka tek dosyada toplanır (.ahut); yorumlarıyla birlikte paylaşılabilir.",

    "coz.basligi": "Analiz çalışıyor", "coz.alt": "Risk modeli ve fizik motoru sırayla çağrılıyor. Bu sırada diğer sekmeleri kullanabilirsiniz.",
    "coz.adimTahmin": "Risk modeli tahmini", "coz.adimOksijen": "Oksijen eğrisi (221 nokta)",
    "coz.adimHarita": "Yanabilirlik haritası (40 × 40)", "coz.adimAkis": "Akış eğrisi (40 nokta)",
    "coz.adimYakin": "Yakın deneylerin taranması", "coz.adimLlm": "Yapay zeka yorumu",
    "coz.bitti": "Çözüm tamamlandı", "coz.hata": "Çözüm başarısız",

    "sonuc.riskSeviyesi": "Risk seviyesi", "sonuc.guvenlikKatsayisi": "Güvenlik katsayısı",
    "sonuc.guvenSkoru": "Güven skoru", "sonuc.yanmaIhtimali": "Yanma ihtimali",
    "sonuc.sonmeSiniri": "Sönme sınırı", "sonuc.uyarilar": "Uyarılar",
    "sonuc.varsayilanlar": "Kullanılan varsayılanlar", "sonuc.modelMotor": "Risk modeli ile fizik motoru",
    "sonuc.celiski": "Risk modeli ile fizik motoru çelişiyor",
    "sonuc.dogrulanmamis": "doğrulanmamış", "sonuc.bilinmeyenMalzeme": "bilinmeyen malzeme",
    "sonuc.yokHenuz": "Henüz çözüm yok", "sonuc.yokHenuzAlt": "Soldaki ağaçtan girdileri ayarlayıp ÇÖZ'e basın.",

    "ktp.basligi": "Vaka kütüphanem", "ktp.bos": "Kütüphane boş",
    "ktp.bosAlt": "Çözdüğünüz her vakayı Ctrl+S ile buraya kaydedebilirsiniz.",
    "top.basligi": "Topluluk", "top.alt": "Paylaşılmış vaka ve deney sonuçları.",
    "top.yerel": "Bu sürümde topluluk içeriği uygulamayla gelen örneklerden okunur. Çevrimiçi yayın bir sonraki sürümde açılacak.",

    "agac.supurme": "Parametre Süpürmesi",
    "sup.parametre": "Süpürülecek girdi", "sup.bas": "Başlangıç", "sup.son": "Bitiş", "sup.adim": "Adım",
    "sup.nokta": "Nokta sayısı", "sup.sure": "Tahmini süre", "sup.calistir": "Süpürmeyi Çalıştır",
    "sup.calisiyor": "Süpürülüyor", "sup.durdu": "Süpürme tamamlandı",
    "sup.yok": "Henüz süpürme yapılmadı",
    "sup.yokAlt": "Bir girdiyi aralık boyunca değiştirip her noktada riski hesaplar. Hangi oksijen yüzdesinde güvenliğin kaybolduğunu tek bakışta gösterir.",
    "sup.esik": "Güvenlik eşiği", "sup.esikYok": "Bu aralıkta güvenlik eşiği yok",
    "sup.esikAciklama": "Güvenlik katsayısının 1'in altına düştüğü değer; bunun ötesinde alev yanabilir.",
    "sup.tablo": "Süpürme tablosu", "sup.uyari": "Nokta başına yaklaşık 1 saniye sürer.",
    "sup.hataNokta": "hesaplanamayan nokta",
    "krs.ad": "Vaka Karşılaştırma", "krs.sec": "Karşılaştırmak için iki vaka seçin",
    "krs.secAlt": "Kütüphanedeki kartların köşesindeki kutuları işaretleyin; iki vaka seçince bu düğme etkinleşir.",
    "krs.mevcut": "Ekrandaki vaka", "krs.fark": "Farklı alanlar sarı ile işaretlidir.",
    "krs.girdiler": "Girdiler", "krs.sonuclar": "Sonuçlar", "krs.egriler": "Oksijen eğrileri",
    "krs.egriNot": "Mavi = A, turuncu = B. Kısmi yerçekiminde eğri en kötü durumdur.",
    "krs.egriYok": "Bu vakalarda saklı eğri verisi yok.", "krs.karsilastir": "Karşılaştır",
  },

  en: {
    "menu.dosya": "File", "menu.duzen": "Edit", "menu.gorunum": "View",
    "menu.birimler": "Units", "menu.araclar": "Tools", "menu.profil": "Profile", "menu.yardim": "Help",

    "komut.yeni": "New Case", "komut.yeniK": "New",
    "komut.ac": "Open Case…", "komut.acK": "Open",
    "komut.kaydet": "Save to Library", "komut.kaydetK": "Save",
    "komut.ice": "Import (.ahut)…", "komut.disa": "Export (.ahut)…",
    "komut.rapor": "Generate Report…", "komut.raporK": "Report", "komut.paylasK": "Share",
    "komut.klasorVeri": "Open Data Folder", "komut.klasorRender": "Open Render Folder",
    "komut.cikis": "Exit", "komut.sifirla": "Reset Inputs to Defaults",
    "komut.onayarIss": "Preset: ISS", "komut.onayarMars": "Preset: Mars Habitat", "komut.onayarAy": "Preset: Lunar Habitat",
    "komut.tema": "Dark Theme", "komut.temaAcik": "Light Theme", "komut.temaKoyu": "Dark Theme",
    "komut.sunum": "Presentation Mode", "komut.sunumK": "Present", "komut.tamekran": "Full Screen",
    "komut.panelSifirla": "Reset Panel Layout",
    "komut.coz": "Solve", "komut.cozK": "SOLVE",
    "komut.llm": "Request AI Commentary", "komut.llmK": "AI",
    "komut.karsilastir": "Compare Cases…", "komut.supur": "Parameter Sweep…",
    "gh.baslik": "Sharing repository (GitHub)",
    "gh.depo": "Repository", "gh.jeton": "Access token",
    "gh.depoIpucu": "owner/repo — e.g. Nikire55/ahut-flare",
    "gh.jetonIpucu": "Stored on this computer only; never written into a shared case file. Type a single dash (-) to clear it.",
    "gh.jetonVar": "token saved — paste a new one to replace it",
    "gh.sina": "Test Connection", "gh.siteKur": "Publish Site",
    "gh.sinaniyor": "Testing…", "gh.kuruluyor": "Publishing site…",
    "gh.baglandi": "Connected", "gh.siteAdresi": "Site address",
    "gh.paylas": "Share on GitHub", "gh.paylasiliyor": "Sharing…",
    "gh.paylasildi": "Case shared", "gh.guncellendi": "Case updated",
    "gh.siteAc": "Open on site", "gh.githubAc": "Open on GitHub", "gh.panoyaKopyala": "Copy link",
    "gh.canli": "live", "gh.cevrimdisi": "offline", "gh.yerelKaynak": "local examples only",
    "gh.tazele": "Refresh", "gh.sonGuncelleme": "last updated",
    "gh.kurulumYok": "No sharing repository configured",
    "gh.kurulumYokAlt": "Enter your GitHub repository and token in the Profile screen; your cases are uploaded there and published on the GitHub Pages site.",
    "gh.al": "Add to library", "gh.alindi": "Case added to the library",
    "gh.siteKuruldu": "Site published", "gh.siteDegismedi": "Site already up to date",
 "komut.json": "Show Raw Result as JSON",
    "komut.profilDuzenle": "Edit Profile…", "komut.gitKutuphane": "My Case Library",
    "komut.gitTopluluk": "Community", "komut.gitBaslangic": "Start Screen",
    "komut.kisayollar": "Keyboard Shortcuts", "komut.hakkinda": "About",

    "sekme.baslangic": "Start", "sekme.calisma": "Model",
    "sekme.kutuphane": "Library", "sekme.topluluk": "Community",

    "panel.anahat": "Outline", "panel.ayrintilar": "Details", "panel.mesajlar": "Messages",
    "panel.tablo": "Tabular Data", "panel.grafik": "Graph", "panel.gunluk": "Log", "panel.sistem": "System",

    "birim.basinc": "Pressure", "birim.akis": "Air flow",

    "agac.ortam": "Environment", "agac.malzeme": "Material", "agac.akis": "Flow",
    "agac.cozumAyar": "Analysis Settings", "agac.ofm": "Detailed Engine (OpenFOAM)", "agac.sonuc3b": "3D Field Result",
    "agac.proje": "Project", "agac.model": "Model", "agac.numune": "Specimen / Geometry", "agac.cozum": "Solution Monitor",
    "agac.adimlar": "Analysis Steps",
    "agac.ozet": "Risk Summary", "agac.oksijen": "Oxygen Curve", "agac.harita": "Flammability Map",
    "agac.akisEgrisi": "Flow Curve", "agac.deneyler": "Nearby Experiments", "agac.guven": "Confidence Analysis",
    "agac.sinirlama": "Gravity Bounding", "agac.llm": "AI Commentary", "agac.render": "Render View",
    "agac.dunya": "Earth Applications",

    "alan.onayar": "Environment preset", "alan.g": "Gravity", "alan.basinc": "Pressure",
    "alan.oksijen": "Oxygen", "alan.seyreltici": "Diluent gas",
    "alan.malzeme": "Material", "alan.numune": "Sample type", "alan.kalinlik": "Thickness",
    "alan.yakit": "Fuel type", "alan.akisBilinmiyor": "Flow unknown", "alan.akis": "Air flow",
    "alan.akisYonu": "Flow direction", "alan.motor": "Physics engine", "alan.llmIste": "AI commentary",
    "alan.baslik": "Title", "alan.aciklama": "Description", "alan.etiketler": "Tags",

    "ipucu.g": "Earth = 1 · ISS ≈ 1e-4 · Moon = 0.165 · Mars = 0.38",
    "ipucu.akis": "0 = quiescent. Not the same as “unknown”.",
    "ipucu.akisBilinmiyor": "When checked, the worst case (flow present) is assumed.",
    "ipucu.varsayilan": "Left empty, the material default is used.",

    "durum.motorYukleniyor": "Loading model…", "durum.motorHazir": "Model ready",
    "durum.motorHata": "Model failed to load", "durum.motorMock": "MOCK DATA mode",
    "durum.cozuluyor": "Solving…", "durum.bosta": "Idle",
    "durum.vakaYok": "Unsaved case", "durum.kirli": "unsaved",

    "genel.profilYok": "No profile set", "genel.kapat": "Close", "genel.iptal": "Cancel",
    "genel.tamam": "OK", "genel.kaydet": "Save", "genel.sil": "Delete", "genel.ac": "Open",
    "genel.hepsi": "All", "genel.ara": "Search…", "genel.yok": "none", "genel.hesaplanamadi": "not computable",
    "genel.bulunamadi": "not found", "genel.bilinmiyor": "unknown",

    "bas.slogan": "Fire safety analysis environment for microgravity",
    "bas.ozet": "Runs a risk model learned from NASA PSI microgravity combustion experiments alongside a semi-empirical physics engine, producing material flammability decisions for spacecraft cabins and lunar or Martian habitats.",
    "bas.hizli": "Quick start", "bas.nasil": "How it works", "bas.sonVakalar": "Recent cases",
    "bas.sistem": "System", "bas.veri": "Data and method",
    "bas.yeniVaka": "Set up a new case", "bas.yeniVakaAlt": "Enter environment and material values yourself",
    "bas.ornekIss": "Example: ISS cabin", "bas.ornekIssAlt": "Microgravity, 21% O₂, 101.3 kPa, PMMA",
    "bas.ornekMars": "Example: Mars habitat", "bas.ornekMarsAlt": "g = 0.38 · partial-gravity bounding",
    "bas.kutuphane": "Open library", "bas.kutuphaneAlt": "Saved cases and shareable files",
    "bas.adim1": "Set up the case", "bas.adim1Alt": "Enter gravity, pressure, oxygen, material and flow in the Details grid.",
    "bas.adim2": "Solve", "bas.adim2Alt": "The risk model and the physics engine evaluate the same condition independently.",
    "bas.adim3": "Read the result", "bas.adim3Alt": "Risk level, safety factor and confidence score; missing inputs are flagged explicitly.",
    "bas.adim4": "Save and share", "bas.adim4Alt": "The case is packed into a single file (.ahut) and can be shared with its comments.",

    "coz.basligi": "Analysis running", "coz.alt": "The risk model and the physics engine are being called in turn. You can use the other tabs meanwhile.",
    "coz.adimTahmin": "Risk model prediction", "coz.adimOksijen": "Oxygen curve (221 points)",
    "coz.adimHarita": "Flammability map (40 × 40)", "coz.adimAkis": "Flow curve (40 points)",
    "coz.adimYakin": "Scanning nearby experiments", "coz.adimLlm": "AI commentary",
    "coz.bitti": "Solution complete", "coz.hata": "Solution failed",

    "sonuc.riskSeviyesi": "Risk level", "sonuc.guvenlikKatsayisi": "Safety factor",
    "sonuc.guvenSkoru": "Confidence score", "sonuc.yanmaIhtimali": "Burning probability",
    "sonuc.sonmeSiniri": "Extinction limit", "sonuc.uyarilar": "Warnings",
    "sonuc.varsayilanlar": "Defaults applied", "sonuc.modelMotor": "Risk model vs physics engine",
    "sonuc.celiski": "Risk model and physics engine disagree",
    "sonuc.dogrulanmamis": "unvalidated", "sonuc.bilinmeyenMalzeme": "unknown material",
    "sonuc.yokHenuz": "No solution yet", "sonuc.yokHenuzAlt": "Set the inputs in the tree on the left, then press SOLVE.",

    "ktp.basligi": "My case library", "ktp.bos": "Library is empty",
    "ktp.bosAlt": "Save any solved case here with Ctrl+S.",
    "top.basligi": "Community", "top.alt": "Shared cases and experiment results.",
    "top.yerel": "In this release community content is read from the examples shipped with the application. Online publishing arrives in the next version.",

    "agac.supurme": "Parameter Sweep",
    "sup.parametre": "Swept input", "sup.bas": "Start", "sup.son": "End", "sup.adim": "Step",
    "sup.nokta": "Points", "sup.sure": "Estimated time", "sup.calistir": "Run Sweep",
    "sup.calisiyor": "Sweeping", "sup.durdu": "Sweep complete",
    "sup.yok": "No sweep yet",
    "sup.yokAlt": "Varies one input across a range and evaluates the risk at every point, showing at a glance where safety is lost.",
    "sup.esik": "Safety threshold", "sup.esikYok": "No safety threshold in this range",
    "sup.esikAciklama": "The value at which the safety factor drops below 1; beyond it a flame can sustain.",
    "sup.tablo": "Sweep table", "sup.uyari": "Takes about one second per point.",
    "sup.hataNokta": "point(s) could not be evaluated",
    "krs.ad": "Case Comparison", "krs.sec": "Select two cases to compare",
    "krs.secAlt": "Tick the boxes on the library cards; the button activates once two cases are selected.",
    "krs.mevcut": "Current case", "krs.fark": "Differing fields are highlighted.",
    "krs.girdiler": "Inputs", "krs.sonuclar": "Results", "krs.egriler": "Oxygen curves",
    "krs.egriNot": "Blue = A, orange = B. In partial gravity the curve is the worst case.",
    "krs.egriYok": "These cases carry no stored curve data.", "krs.karsilastir": "Compare",
  },
};

let DIL = "tr";

function T(anahtar, degerler) {
  const s = (SOZLUK[DIL] && SOZLUK[DIL][anahtar]) || (SOZLUK.tr[anahtar]) || anahtar;
  if (!degerler) return s;
  return s.replace(/\{(\w+)\}/g, (_, a) => (degerler[a] == null ? "" : degerler[a]));
}

function dilSec(kod) {
  DIL = SOZLUK[kod] ? kod : "tr";
  document.documentElement.lang = DIL;
  document.querySelectorAll("[data-d]").forEach((e) => (e.textContent = T(e.dataset.d)));
  document.querySelectorAll("[data-d-ph]").forEach((e) => (e.placeholder = T(e.dataset.dPh)));
  document.querySelectorAll("[data-d-t]").forEach((e) => (e.title = T(e.dataset.dT)));
  const d = document.getElementById("dilDugme");
  if (d) d.textContent = DIL === "tr" ? "EN" : "TR";
}

/* Sayı biçimleri dile göre: 0,79 (tr) / 0.79 (en) */
const yerel = () => (DIL === "tr" ? "tr-TR" : "en-US");
const nf = (x, d = 1) =>
  x == null || x === "" || Number.isNaN(Number(x)) ? "–" : Number(x).toLocaleString(yerel(), { maximumFractionDigits: d });
const pct = (x, d = 0) => (x == null ? "–" : nf(x * 100, d));
