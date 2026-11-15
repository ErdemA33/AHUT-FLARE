"use strict";
/* AHUT FLARE — uygulama mantığı.
   Ağaç, Ayrıntılar tablosu, çözüm akışı, sonuç görünümleri, kütüphane,
   topluluk ve profil. Model çağrıları core/bridge.py üzerinden yapılır. */

/* ---------------------------------------------------------------- sabitler */
const ONAYARLAR = [
  { ad: "Dünya kabini", en: "Earth cabin", g: 1, o2: 21, p: 101.3 },
  { ad: "ISS", en: "ISS", g: 1e-4, o2: 21, p: 101.3 },
  { ad: "Ay üssü", en: "Lunar habitat", g: 0.165, o2: 21, p: 101.3, not: "O₂ ve basınç verilmedi; Dünya havası varsayıldı" },
  { ad: "Mars üssü", en: "Mars habitat", g: 0.38, o2: 21, p: 101.3, not: "O₂ ve basınç verilmedi; Dünya havası varsayıldı" },
  { ad: "NASA keşif atmosferi", en: "NASA exploration atmosphere", g: null, o2: 34, p: 56.5, not: "Yalnızca O₂ ve basıncı değiştirir" },
  { ad: "Saffire-VI benzeri", en: "Saffire-VI like", g: 1e-4, o2: 31, p: 54 },
  { ad: "Özel", en: "Custom" },
];
const NUMUNE = ["thin_sheet", "thick_sheet", "fabric", "rod", "wire", "sphere", "droplet", "pool",
                "gas_jet", "flat_burner", "porous_sphere"];
const GAZ_NUMUNE = ["gas_jet", "flat_burner", "porous_sphere"];     // gaz yakıt geometrileri (gaz motoru)
const MALZEME_YEDEK = ["pmma", "sibal", "cotton", "nomex", "silicone", "n-heptane", "methanol", "methane"];
const SEYRELTICI = ["n2", "co2", "he", "ar", "xe"];

const BIRIM = {
  basinc: { kPa: { c: 1, b: 1 }, psi: { c: 0.1450377, b: 2 }, atm: { c: 1 / 101.325, b: 3 } },
  akis: { "cm/s": { c: 1, b: 1 }, "m/s": { c: 0.01, b: 3 } },
};
const birimeCevir = (v, tip, birim) => (v == null ? null : v * BIRIM[tip][birim].c);
const birimdenCevir = (v, tip, birim) => (v == null ? null : v / BIRIM[tip][birim].c);
const birimBasamak = (tip, birim) => BIRIM[tip][birim].b;

/* ---------------------------------------------------------------- durum */
const S = {
  surum: "",
  sistem: {},
  ayarlar: { dil: "tr", birimler: { basinc: "kPa", akis: "cm/s" }, gorunum: "acik" },
  profil: {},
  motor: { durum: "yukleniyor" },
  varsay: {},
  malzemeler: MALZEME_YEDEK.slice(),

  onayar: "ISS",
  girdi: {
    malzeme: "pmma", oksijen: 21, basinc: 101.3, g: 1e-4,
    akis: 0, akisBilinmiyor: true, kalinlik: null, numune_tipi: null,
    yakit_turu: null, akis_yonu: "", seyreltici: "n2",
  },
  dokunuldu: { numune_tipi: false, kalinlik: false, yakit_turu: false },
  hatalar: {},

  sonuc: null,          // {kosul, tahmin, oksijen_egrisi, harita, akis_egrisi, yakin}
  cozuluyor: false,
  llm: { durum: "yok", metin: null },
  sohbet: { mesajlar: [], bekle: false, taslak: "", erisim: null, kosul: null },
  vakaId: null, baslik: "", aciklama: "", etiketler: [],
  kirli: false,

  supurme: { parametre: "oksijen", bas: 14, son: 30, adim: 1,
             sonuc: null, calisiyor: false, yuzde: 0 },
  noktaSure: 1.0,          // olculen nokta basina sure (saniye)
  secKarsi: [],            // karsilastirma icin secili vaka kimlikleri
  toplulukBilgi: null,     // {kaynak, zaman, depo, hata}
  mesajlar: [], gunluk: [],
  vakalar: [], topluluk: [], render: [],
  renderSecili: null,
  cozumTuru: "ayrintili", onTahmin: false, ayrintili: null,   // çözüm türü (js/detailed.js); vaka dosyasına kaydedilir
  renderTumu: false,       // true: süzme yok, 37 renderın hepsi
  renderUygun: null,       // {anahtar, mod: tam|benzer|yok, adlar}
  adimDurum: {},
};

/* ---------------------------------------------------------------- yardımcılar */
const zamanMetni = () => new Date().toLocaleTimeString(DIL === "tr" ? "tr-TR" : "en-US");
const gMetni = (g) => (g == null ? "–" : g < 0.001 ? Number(g).toExponential(0).replace("e-", "e−") : nf(g, 4));

function gOku(metin) {
  const t = String(metin == null ? "" : metin).trim().replace(",", ".");
  const v = Number(t);
  return t === "" || !isFinite(v) ? NaN : v;
}

function mesaj(tur, metin) {
  S.mesajlar.unshift({ tur, metin, zaman: zamanMetni() });
  S.mesajlar = S.mesajlar.slice(0, 200);
  mesajCiz();
}

function gunluk(satir) {
  S.gunluk.unshift(Object.assign({ zaman: zamanMetni() }, satir));
  S.gunluk = S.gunluk.slice(0, 200);
  gunlukCiz();
}

function kirlet(k) {
  S.kirli = k !== false;
  Kabuk.durum("dVaka", (S.baslik || T("durum.vakaYok")) + (S.kirli ? " · " + T("durum.kirli") : ""));
}

/* ---------------------------------------------------------------- girdi / koşul */
function kosul() {
  return {
    malzeme: String(S.girdi.malzeme || "").trim(),
    oksijen: S.girdi.oksijen,
    basinc: S.girdi.basinc,
    g: S.girdi.g,
    akis: S.girdi.akisBilinmiyor ? null : S.girdi.akis,
    kalinlik: S.dokunuldu.kalinlik ? S.girdi.kalinlik : null,
    numune_tipi: S.dokunuldu.numune_tipi ? S.girdi.numune_tipi || null : null,
    yakit_turu: S.dokunuldu.yakit_turu && !(malzemeVarsayilani(S.girdi.malzeme) || [])[2] ? S.girdi.yakit_turu || null : null,
    akis_yonu: S.girdi.akis_yonu || null,
    seyreltici: S.girdi.seyreltici || "n2",
  };
}

function dogrula() {
  const h = {};
  const g = S.girdi.g;
  if (!(g > 0)) h.g = DIL === "tr" ? "g sayı ve 0'dan büyük olmalı (örn. 1e-4)" : "g must be a number greater than 0 (e.g. 1e-4)";
  if (!(S.girdi.oksijen > 0 && S.girdi.oksijen <= 100)) h.oksijen = DIL === "tr" ? "Oksijen 0–100 arasında olmalı" : "Oxygen must be between 0 and 100";
  if (!(S.girdi.basinc > 0)) h.basinc = DIL === "tr" ? "Basınç 0'dan büyük olmalı" : "Pressure must be greater than 0";
  if (!String(S.girdi.malzeme || "").trim()) h.malzeme = DIL === "tr" ? "Malzeme seçin ya da yazın" : "Select or type a material";
  if (!S.girdi.akisBilinmiyor && !(S.girdi.akis >= 0)) h.akis = DIL === "tr" ? "Akış 0 ya da daha büyük olmalı" : "Flow must be 0 or greater";
  if (S.dokunuldu.kalinlik && S.girdi.kalinlik != null && !(S.girdi.kalinlik > 0)) {
    h.kalinlik = DIL === "tr" ? "Kalınlık 0'dan büyük olmalı" : "Thickness must be greater than 0";
  }
  S.hatalar = h;
  const ok = Object.keys(h).length === 0;
  const hazirMotor = S.motor.durum === "hazir";
  $("#btnCoz").disabled = !ok || !hazirMotor || S.cozuluyor;
  $("#btnLlm").disabled = S.llm.durum === "bekle";      // yorum motordan ve girdi koşullarından bağımsız: sayfa hep açılır
  return ok;
}

function onayarUygula(o) {
  S.onayar = o.ad;
  if (o.ad !== "Özel") {
    if (o.g != null) S.girdi.g = o.g;
    S.girdi.oksijen = o.o2;
    S.girdi.basinc = o.p;
    S.girdi.seyreltici = "n2";
  }
  kirlet(true);
  ayrintiCiz();
  gorselYenile();
}

function ozelYap() { if (S.onayar !== "Özel") S.onayar = "Özel"; }

/* Ön ayarın ekranda görünen adı (iç kimlik her zaman Türkçe addır) */
function onayarAdi(ad) {
  if (ad === "Özel") return DIL === "tr" ? "" : "";
  const o = ONAYARLAR.find((x) => x.ad === ad);
  return o ? (DIL === "tr" ? o.ad : o.en) : ad;
}

function yakitKilitle() {      // kütüphanede tanımlı malzemede yakıt türü malzemeden gelir; elle değer tutulmaz
  const vd = malzemeVarsayilani(S.girdi.malzeme);
  if (vd && vd[2] && S.dokunuldu.yakit_turu && !S.otoYakit) { S.dokunuldu.yakit_turu = false; S.girdi.yakit_turu = null; }
}
function malzemeDegisti() {
  if (S.otoYakit) { S.dokunuldu.yakit_turu = false; S.otoYakit = false; }   // gaz numunesiyle otomatik konmuştu
  ["numune_tipi", "kalinlik", "yakit_turu"].forEach((a) => {
    if (!S.dokunuldu[a]) S.girdi[a] = null;
  });
}

const malzemeVarsayilani = (ad) => S.varsay[String(ad || "").trim()] || null;

function varsayilanDeger(alan) {
  const v = malzemeVarsayilani(S.girdi.malzeme);
  if (!v) return null;
  return { numune_tipi: v[0], kalinlik: v[1], yakit_turu: v[2] }[alan];
}

/* ---------------------------------------------------------------- AĞAÇ */
/* Düğüm durumları (ANSYS gibi): tamam ✓ güncel · eski ⚡ girdi değişti / çözülmeli ·
   eksik ? girdi eksik · hata ✗ · bekler (çözülüyor). Simgeler shell.js'te SVG olarak çizilir. */
const bosMu = (v) => v == null || v === "" || (typeof v === "number" && isNaN(v));
const GAZ_CAPLI = ["rod", "wire", "sphere", "droplet", "porous_sphere", "gas_jet"];

/* Son çözümün koşulu, şimdiki girdilerle aynı mı? (kayıtlı vakalarda anahtar sırası farklı olabilir) */
function cozumGuncel() {
  if (!S.sonuc || !S.sonuc.kosul) return false;
  const a = kosul(), b = S.sonuc.kosul;
  return Object.keys(a).every((k) => {
    const x = a[k], y = b[k];
    if (bosMu(x) && bosMu(y)) return true;
    return typeof x === "number" || typeof y === "number" ? Number(x) === Number(y) : String(x) === String(y);
  });
}

function girdiDurumu(alanlar) {
  const h = alanlar.filter((a) => S.hatalar[a]);
  if (!h.length) return "tamam";
  return h.some((a) => !bosMu(a === "malzeme" ? String(S.girdi.malzeme || "").trim() : S.girdi[a])) ? "hata" : "eksik";
}

function numuneDurumu() {
  if (S.hatalar.kalinlik) return "hata";
  const vd = malzemeVarsayilani(S.girdi.malzeme);
  if (!vd && !S.girdi.numune_tipi) return "eksik";       // varsayılan yok, numune tipi verilmemiş
  return "tamam";
}

function sonucDurumu(veriVar) {
  if (S.cozuluyor) return "bekler";
  if (S.cozumHata && !S.sonuc) return "hata";
  if (!S.sonuc) return "eski";
  if (veriVar === false) return "hata";
  return cozumGuncel() ? "tamam" : "eski";
}

function agacModeli() {
  const t = S.sonuc && S.sonuc.tahmin;
  const s = S.sonuc || {};
  const vd = malzemeVarsayilani(S.girdi.malzeme);
  const numune = S.girdi.numune_tipi || (vd && vd[0]) || "";
  const kal = S.girdi.kalinlik != null ? S.girdi.kalinlik : vd && vd[1];
  const llmD = { geldi: "tamam", bekle: "bekler", hata: "hata" }[S.llm.durum] || "";
  const sonuclar = [
    { id: "r-ozet", ad: T("agac.ozet"), ikon: "sonuc", durum: sonucDurumu(),
      not: S.ayrintili && S.ayrintili.durum === "bitti" && S.ayrintili.ofm ? (DIL === "tr" ? "Ayrıntılı: " : "Detailed: ") + (S.ayrintili.ofm.yandi === 1 ? (DIL === "tr" ? "yandı" : "ignited") : S.ayrintili.ofm.yandi === 0 ? (DIL === "tr" ? "yanmadı/söndü" : "no burn") : "?")
        : !t ? "" : t.ozel_durum ? ozelKisa(t) : t.yanma_ihtimali == null ? (DIL === "tr" ? "tanınmadı" : "not recognized") : seviyeMetni(t.yanma_birlesik != null ? t.yanma_birlesik : t.yanma_ihtimali) },
    { id: "r-motor", ad: DIL === "tr" ? "Motor Ayrıntıları" : "Engine Details", ikon: "tablo", durum: sonucDurumu(), not: t ? t.motor_kaynagi || "" : "" },
    { id: "r-ofm", ad: T("agac.ofm"), ikon: "tablo", durum: sonucDurumu(), not: t ? (((S.ayrintili && S.ayrintili.ofm) || t.ofm) ? "d=" + nf(((S.ayrintili && S.ayrintili.ofm) || t.ofm).mesafe, 2) : (DIL === "tr" ? "yok" : "none")) : "" },
    { id: "r-3b", ad: T("agac.sonuc3b"), ikon: "render", durum: sonucDurumu(), not: "" },
    { id: "r-guven", ad: T("agac.guven"), ikon: "guven", durum: sonucDurumu(), not: t && guvenSkoru(t) != null ? String(guvenSkoru(t)) : "" },
    { id: "r-oksijen", ad: T("agac.oksijen"), ikon: "grafik", durum: sonucDurumu(t ? !!s.oksijen_egrisi : undefined) },
    { id: "r-harita", ad: T("agac.harita"), ikon: "harita", durum: sonucDurumu(t ? !!s.harita : undefined) },
    { id: "r-akis", ad: T("agac.akisEgrisi"), ikon: "grafik", durum: sonucDurumu(t ? !!s.akis_egrisi : undefined) },
    { id: "r-deney", ad: T("agac.deneyler"), ikon: "tablo", durum: sonucDurumu(), not: t ? String((s.yakin || []).length) : "" },
    { id: "r-adimlar", ad: T("agac.adimlar"), ikon: "tablo", durum: sonucDurumu(),
      not: t && t.adimlar ? String(t.adimlar.length) : "" },
  ].concat(t && t.sinirlama ? [{ id: "r-sinirlama", ad: T("agac.sinirlama"), ikon: "tablo", durum: sonucDurumu() }] : [])
   .concat([
    { id: "r-llm", ad: T("agac.llm"), ikon: "llm", durum: t ? llmD : "" },
    { id: "r-render", ad: T("agac.render"), ikon: "render", not: S.render.length ? String(S.render.length) : "" },
    { id: "supurme", ad: T("agac.supurme"), ikon: "grafik",
      durum: S.supurme.calisiyor ? "bekler" : S.supurme.sonuc ? "tamam" : "",
      not: S.supurme.sonuc ? String((S.supurme.sonuc.noktalar || []).length) : "" },
    { id: "r-dunya", ad: T("agac.dunya"), ikon: "dunya", durum: t ? "tamam" : "" },
  ]);
  /* sonuç düğümleri çözümden önce de görünür (⚡ çözülmeli); içerik gerektirenler pasif */
  sonuclar.forEach((d) => { if (!t && d.id.indexOf("r-") === 0 && d.id !== "r-render") d.pasif = true; });

  const model = {
    id: "vaka", ad: T("agac.model"), ikon: "vaka",
    cocuk: [
      { id: "ortam", ad: T("agac.ortam"), ikon: "ortam", durum: girdiDurumu(["g", "basinc", "oksijen"]), not: onayarAdi(S.onayar) },
      { id: "malzeme", ad: T("agac.malzeme"), ikon: "malzeme", durum: girdiDurumu(["malzeme"]), not: S.girdi.malzeme },
      { id: "numune", ad: T("agac.numune"), ikon: "numune", durum: numuneDurumu(),
        not: numune ? numune + (kal != null ? " · " + nf(kal, 2) + " mm" : "") : "" },
      { id: "akis", ad: T("agac.akis"), ikon: "akis", durum: girdiDurumu(["akis"]),
        not: S.girdi.akisBilinmiyor ? T("genel.bilinmiyor") : nf(S.girdi.akis, 1) },
      { id: "cozumAyar", ad: T("agac.cozumAyar"), ikon: "ayar", durum: "tamam" },
      { id: "cozum", ad: T("agac.cozum"), ikon: "cozum", durum: S.cozumHata && !S.cozuluyor ? "hata" : sonucDurumu(),
        not: S.cozuluyor && S.cozumIlerleme ? (S.cozumIlerleme.adim ? S.cozumIlerleme.adim + " · " : "") + "%" + nf(S.cozumIlerleme.yuzde, 0)
           : S.sonSolveSure ? nf(S.sonSolveSure, 2) + " s" : "", cocuk: sonuclar },
    ],
  };
  return [{ id: "proje", ad: T("agac.proje") + (S.baslik ? " — " + S.baslik : ""), ikon: "proje", cocuk: [model] }];
}

/* Ağaçta bir düğüm var mı (betikler de kullanır) */
function agacDugumVar(id) {
  const ara = (l) => (l || []).some((d) => d.id === id || ara(d.cocuk));
  return ara(agacModeli());
}

function agacYenile() {
  Kabuk.agacCiz(agacModeli());
}

function dugumSecildi(id) {
  ayrintiCiz();
  gorselYenile();
}

/* ---------------------------------------------------------------- AYRINTILAR */
function ayrintiCiz() {
  yakitKilitle();
  const id = Kabuk.agacSecili() || "ortam";
  const b = S.ayarlar.birimler;
  const t = S.sonuc && S.sonuc.tahmin;
  let baslik = T("panel.ayrintilar"), alanlar = [], degerler = {};

  const grupTanim = DIL === "tr" ? "Tanım" : "Definition";
  const basligiYap = (ad) => (DIL === "tr" ? `“${ad}” ayrıntıları` : `Details of “${ad}”`);

  if (id === "proje") {
    baslik = basligiYap(T("agac.proje"));
    alanlar = [
      { grup: DIL === "tr" ? "Vaka bilgileri" : "Case information" },
      { ad: "baslik", etiket: T("alan.baslik"), tip: "metin", yertutucu: DIL === "tr" ? "(çözümden sonra otomatik)" : "(auto after solve)" },
      { ad: "aciklama", etiket: T("alan.aciklama"), tip: "metin", yertutucu: DIL === "tr" ? "kısa not" : "short note" },
      { ad: "etiketler", etiket: T("alan.etiketler"), tip: "metin", yertutucu: "iss, pmma" },
      { grup: DIL === "tr" ? "Durum" : "State" },
      { ad: "kayit", etiket: DIL === "tr" ? "Kayıt" : "Saved", salt: true,
        bicim: () => esc(S.vakaId ? (S.kirli ? (DIL === "tr" ? "kaydedilmemiş değişiklik var" : "unsaved changes") : (DIL === "tr" ? "kayıtlı" : "saved")) : (DIL === "tr" ? "kaydedilmedi" : "not saved")) },
      { ad: "cozDurum", etiket: T("agac.cozum"), salt: true, bicim: () => esc(cozumDurumMetni()) },
    ];
    degerler = { baslik: S.baslik, aciklama: S.aciklama, etiketler: (S.etiketler || []).join(", ") };
  } else if (id === "cozum" || id === "r-adimlar") {
    baslik = basligiYap(T("agac.cozum"));
    alanlar = [
      { grup: DIL === "tr" ? "Çözüm bilgisi" : "Solution information" },
      { ad: "d", etiket: DIL === "tr" ? "Durum" : "State", salt: true, bicim: () => esc(cozumDurumMetni()) },
      { ad: "s", etiket: DIL === "tr" ? "Son çözüm süresi" : "Last solve time", salt: true, birim: "s",
        bicim: () => esc(S.sonSolveSure ? nf(S.sonSolveSure, 2) : "–") },
      { ad: "m", etiket: T("alan.motor"), salt: true, bicim: () => esc(t ? motorAdi(t) : "–") },
      { ad: "n", etiket: T("agac.adimlar"), salt: true, bicim: () => esc(t && t.adimlar ? String(t.adimlar.length) : "–") },
    ];
    if (S.cozumHata) alanlar.push({ ad: "h", etiket: DIL === "tr" ? "Hata" : "Error", salt: true, bicim: () => `<span style="color:var(--hata)">${esc(S.cozumHata)}</span>` });
    if (t && !cozumGuncel()) alanlar.push({ not: esc(DIL === "tr" ? "Girdiler son çözümden sonra değişti; sonuçlar eski. Yeniden çözün (F8)." : "Inputs changed after the last solve; results are stale. Re-solve (F8).") });
  } else if (id === "ortam" || id === "vaka") {
    baslik = basligiYap(T("agac.ortam"));
    alanlar = [
      { grup: grupTanim },
      { ad: "onayar", etiket: T("alan.onayar"), tip: "secim",
        secenekler: ONAYARLAR.map((o) => ({ deger: o.ad, ad: DIL === "tr" ? o.ad : o.en })) },
      { ad: "g", etiket: T("alan.g"), tip: "metin", birim: "g₀", zorunlu: true,
        ipucu: T("ipucu.g"), hata: S.hatalar.g },
      { ad: "basinc", etiket: T("alan.basinc"), tip: "sayi", birim: b.basinc, zorunlu: true,
        adim: b.basinc === "atm" ? 0.01 : 0.1, hata: S.hatalar.basinc },
      { ad: "oksijen", etiket: T("alan.oksijen"), tip: "sayi", birim: "%", zorunlu: true,
        adim: 0.25, min: 0, max: 100, hata: S.hatalar.oksijen },
      { ad: "seyreltici", etiket: T("alan.seyreltici"), tip: "secim", secenekler: SEYRELTICI },
    ];
    degerler = {
      onayar: S.onayar,
      g: typeof S.girdi.g === "number" ? String(S.girdi.g) : S.girdi.g,
      basinc: yuvarla(birimeCevir(S.girdi.basinc, "basinc", b.basinc), birimBasamak("basinc", b.basinc)),
      oksijen: S.girdi.oksijen,
      seyreltici: S.girdi.seyreltici,
    };
  } else if (id === "malzeme") {
    baslik = basligiYap(T("agac.malzeme"));
    const vd = malzemeVarsayilani(S.girdi.malzeme);
    alanlar = [
      { grup: grupTanim },
      { ad: "malzeme", etiket: T("alan.malzeme"), tip: "secim", zorunlu: true,
        secenekler: S.malzemeler.concat(["__diger"]).map((m) => ({ deger: m, ad: m === "__diger" ? (DIL === "tr" ? "diğer…" : "other…") : m })),
        hata: S.hatalar.malzeme },
    ];
    if (!S.malzemeler.includes(S.girdi.malzeme)) {
      alanlar.push({ ad: "malzemeAd", etiket: DIL === "tr" ? "Malzeme adı" : "Material name",
                     tip: "metin", yertutucu: DIL === "tr" ? "İngilizce ad" : "english name" });
    }
    alanlar.push(
      vd && vd[2]
        ? { ad: "yakit_kilitli", etiket: T("alan.yakit"), salt: true, bicim: () => esc(mlzDil(MLZ_TUR[vd[2]] || [vd[2], vd[2]])) }   // kütüphane malzemesinin yakıt türü değiştirilemez
        : { ad: "yakit_turu", etiket: T("alan.yakit"), tip: "secim", varsayilanli: !S.dokunuldu.yakit_turu,
            secenekler: [{ deger: "", ad: "(—)" }, "kati", "sivi", "gaz", "toz"] },
      { grup: DIL === "tr" ? "Kütüphane varsayılanları" : "Library defaults" },
      { ad: "v_numune", etiket: T("alan.numune"), salt: true, bicim: () => esc(vd && vd[0] ? vd[0] : "–") },
      { ad: "v_kal", etiket: DIL === "tr" ? "Kalınlık / çap" : "Thickness / diameter", salt: true, birim: "mm",
        bicim: () => esc(vd && vd[1] != null ? nf(vd[1], 3) : "–") },
    );
    if (!vd) {
      alanlar.push({ not: `<b>${esc(S.girdi.malzeme || "?")}</b> ${esc(DIL === "tr" ? "için varsayılan tanımlı değil. Numune düğümünde tipi ve kalınlığı verirseniz sonuç belirgin biçimde iyileşir." : "has no stored defaults. Entering sample type and thickness under Specimen improves the result markedly.")}` });
    }
    degerler = {
      malzeme: S.malzemeler.includes(S.girdi.malzeme) ? S.girdi.malzeme : "__diger",
      malzemeAd: S.girdi.malzeme,
      yakit_turu: S.dokunuldu.yakit_turu ? S.girdi.yakit_turu : "",
    };
  } else if (id === "numune") {
    baslik = basligiYap(T("agac.numune"));
    const vd = malzemeVarsayilani(S.girdi.malzeme);
    const tip = S.girdi.numune_tipi || (vd && vd[0]) || "";
    const capli = GAZ_CAPLI.indexOf(tip) >= 0;
    const gaz = GAZ_NUMUNE.indexOf(tip) >= 0 || (S.girdi.yakit_turu || (vd && vd[2])) === "gaz";
    const m = t && t.motor;
    alanlar = [
      { grup: DIL === "tr" ? "Geometri" : "Geometry" },
      { ad: "numune_tipi", etiket: T("alan.numune"), tip: "secim", varsayilanli: !S.dokunuldu.numune_tipi,
        ipucu: T("ipucu.varsayilan"),
        secenekler: [{ deger: "", ad: vd && vd[0] ? "(" + vd[0] + ")" : "(—)" }].concat(NUMUNE) },
      { ad: "kalinlik", etiket: capli ? (DIL === "tr" ? "Çap" : "Diameter") : T("alan.kalinlik"), tip: "sayi", birim: "mm", adim: 0.01,
        varsayilanli: !S.dokunuldu.kalinlik, ipucu: T("ipucu.varsayilan"),
        yertutucu: vd && vd[1] != null ? String(vd[1]) : "", hata: S.hatalar.kalinlik },
    ];
    if (gaz) {
      alanlar.push(
        { grup: DIL === "tr" ? "Gaz yakıt" : "Gaseous fuel" },
        { ad: "debi", etiket: DIL === "tr" ? "Yakıt debisi" : "Fuel mass flow", salt: true, birim: "mg/s",
          bicim: () => esc(m && m.debi_mg_s != null ? nf(m.debi_mg_s, 3) : "–") },
        { not: esc(DIL === "tr"
          ? "Debi şimdilik girdi değildir: gaz motoru seçilen geometriye göre kendi debisini kullanır (çözümden sonra burada görünür). Numune tipi verilmezse gaz motoru çalışmaz."
          : "Mass flow is not an input yet: the gas engine uses its own value for the chosen geometry (shown here after solving). Without a sample type the gas engine does not run.") });
    }
    if (!vd && !S.girdi.numune_tipi) {
      alanlar.push({ not: esc(DIL === "tr" ? "Bu malzemenin kütüphane varsayılanı yok: numune tipini seçin." : "This material has no library default: choose a sample type.") });
    }
    degerler = {
      numune_tipi: S.dokunuldu.numune_tipi ? S.girdi.numune_tipi : "",
      kalinlik: S.dokunuldu.kalinlik ? S.girdi.kalinlik : "",
    };
  } else if (id === "akis") {
    baslik = basligiYap(T("agac.akis"));
    alanlar = [
      { grup: grupTanim },
      { ad: "akisBilinmiyor", etiket: T("alan.akisBilinmiyor"), tip: "onay",
        yanMetin: DIL === "tr" ? "en kötü durum" : "worst case", ipucu: T("ipucu.akisBilinmiyor"),
        vurgulu: S.girdi.akisBilinmiyor },
      { ad: "akis", etiket: T("alan.akis"), tip: "sayi", birim: b.akis, adim: 0.1, min: 0,
        ipucu: T("ipucu.akis"), hata: S.hatalar.akis },
      { ad: "akis_yonu", etiket: T("alan.akisYonu"), tip: "secim",
        secenekler: [{ deger: "", ad: "(—)" }, { deger: "ayni", ad: DIL === "tr" ? "ayni (alevle aynı yön)" : "same as flame" },
                     { deger: "ters", ad: DIL === "tr" ? "ters" : "opposed" }, { deger: "yok", ad: DIL === "tr" ? "yok" : "none" }] },
      { not: esc(T("ipucu.akis")) },
    ];
    degerler = {
      akisBilinmiyor: S.girdi.akisBilinmiyor,
      akis: yuvarla(birimeCevir(S.girdi.akis, "akis", b.akis), birimBasamak("akis", b.akis)),
      akis_yonu: S.girdi.akis_yonu,
    };
  } else if (id === "cozumAyar") {
    baslik = basligiYap(T("agac.cozumAyar"));
    alanlar = [
      { grup: DIL === "tr" ? "Çözüm türü" : "Solution type" },
      { ad: "cozumTuru", etiket: DIL === "tr" ? "Çözüm türü" : "Solution type", tip: "secim",
        secenekler: ["ayrintili", "hizli"].map((k) => ({ deger: k, ad: aTurAd(k) })) },
      { ad: "onTahmin", etiket: DIL === "tr" ? "Ön tahmin (hızlı çözüm)" : "Preliminary estimate (fast)", tip: "secim",
        secenekler: [{ deger: "acik", ad: DIL === "tr" ? "açık (ayrıntılı koşu sürerken göster)" : "on (show while detailed run is in progress)" }, { deger: "kapali", ad: DIL === "tr" ? "kapalı" : "off" }] },
      { grup: DIL === "tr" ? "Çözücü" : "Solver" },
      { ad: "motorTuru", etiket: T("alan.motor"), salt: true,
        bicim: () => esc(t ? motorAdi(t) + " · " + motorAucMetni(t) : (DIL === "tr" ? "çözümde belirlenir (yakıt türüne göre)" : "determined at solve (by fuel type)")) },
      { ad: "llmDurum", etiket: T("alan.llmIste"), salt: true,
        bicim: () => esc({ yok: DIL === "tr" ? "istenmedi" : "not requested", bekle: DIL === "tr" ? "bekleniyor" : "pending", geldi: DIL === "tr" ? "alındı" : "received", hata: DIL === "tr" ? "alınamadı" : "failed" }[S.llm.durum]) },
      { ad: "anahtar", etiket: DIL === "tr" ? "SI anahtarı" : "SI key", salt: true,
        bicim: () => (S.sistem.anahtar_var ? `<span style="color:var(--ok)">${esc(DIL === "tr" ? "bulundu" : "found")}</span>` : `<span style="color:var(--uyari)">${esc(DIL === "tr" ? "yok" : "missing")}</span>`) },
      { grup: DIL === "tr" ? "Seyreltici ve akış yönü" : "Diluent and flow direction" },
      { ad: "sey", etiket: T("alan.seyreltici"), salt: true, bicim: () => esc(S.girdi.seyreltici || "n2") },
      { ad: "yon", etiket: T("alan.akisYonu"), salt: true, bicim: () => esc(S.girdi.akis_yonu || "–") },
      { not: esc(DIL === "tr" ? "Vaka başlığı, açıklama ve etiketler Proje düğümündedir." : "Case title, description and tags are on the Project node.") },
    ];
    degerler = { cozumTuru: S.cozumTuru, onTahmin: S.onTahmin ? "acik" : "kapali" };
  } else if (id === "supurme") {
    baslik = basligiYap(T("agac.supurme"));
    const a = supurAlan(S.supurme.parametre);
    const n = supurNokta();
    alanlar = [
      { grup: grupTanim },
      { ad: "sup_parametre", etiket: T("sup.parametre"), tip: "secim",
        secenekler: SUPUR_ALANLAR.map((x) => ({ deger: x.ad, ad: x.etiket() })) },
      { ad: "sup_bas", etiket: T("sup.bas"), tip: "sayi", birim: a.birim, adim: a.adim },
      { ad: "sup_son", etiket: T("sup.son"), tip: "sayi", birim: a.birim, adim: a.adim },
      { ad: "sup_adim", etiket: T("sup.adim"), tip: "sayi", birim: a.birim, adim: a.adim,
        hata: !(S.supurme.adim > 0) ? (DIL === "tr" ? "Adım 0'dan büyük olmalı" : "Step must be greater than 0") : "" },
      { grup: DIL === "tr" ? "Maliyet" : "Cost" },
      { ad: "sup_n", etiket: T("sup.nokta"), salt: true,
        bicim: () => (n > SUPUR_EN_FAZLA
          ? `<span style="color:var(--hata)">${esc(n)} — ${esc(DIL === "tr" ? "en fazla" : "max")} ${SUPUR_EN_FAZLA}</span>`
          : esc(String(n))) },
      { ad: "sup_sure", etiket: T("sup.sure"), salt: true,
        bicim: () => esc("~" + nf(Math.max(1, n * S.noktaSure), 0) + " s") },
      { not: esc(T("sup.uyari")) },
    ];
    degerler = { sup_parametre: S.supurme.parametre, sup_bas: S.supurme.bas,
                 sup_son: S.supurme.son, sup_adim: S.supurme.adim };
  } else if (id.indexOf("r-") === 0 && t) {
    baslik = basligiYap(T("agac.cozum"));
    alanlar = [
      { grup: T("agac.ozet") },
      { ad: "a", etiket: T("sonuc.riskSeviyesi"), salt: true,
        bicim: () => `<span class="rozet ${ROZET_SINIF(t.risk_seviyesi)}">${esc(t.risk_seviyesi)}</span>` },
      { ad: "b0", etiket: DIL === "tr" ? "Birleşik ihtimal" : "Combined probability", salt: true,
        bicim: () => `%${esc(pct(t.yanma_birlesik != null ? t.yanma_birlesik : t.yanma_ihtimali, 1))}` },
      { ad: "b", etiket: T("sonuc.yanmaIhtimali"), salt: true,
        bicim: () => `%${esc(pct(t.yanma_ihtimali, 1))} ± ${esc(pct(t.belirsizlik, 1))}` },
      { ad: "b2", etiket: DIL === "tr" ? "Fizik motoru" : "Physics engine", salt: true,
        bicim: () => esc(motorAdi(t)) + (t.motor && t.motor.yanma != null ? " · %" + esc(pct(t.motor.yanma, 1)) : "") },
      { ad: "c", etiket: T("sonuc.sonmeSiniri"), salt: true, birim: "% O₂",
        bicim: () => (t.sonme_siniri == null ? esc(T("genel.bulunamadi")) : esc(nf(t.sonme_siniri, 2))) },
      { ad: "d", etiket: T("sonuc.guvenlikKatsayisi"), salt: true,
        bicim: () => (t.guvenlik_katsayisi == null ? esc(T("genel.hesaplanamadi")) : esc(nf(t.guvenlik_katsayisi, 2))) },
      { ad: "e", etiket: T("sonuc.guvenSkoru"), salt: true,
        bicim: () => esc(nf(guvenSkoru(t), 0)) + " / 100" + (guvenV2(t) ? ` <span class="etiket" style="color:${BANT_RENK[t.guven_v2.bant]}">${esc(bantMetni(t.guven_v2.bant))}</span>` : "") },
      { grup: DIL === "tr" ? "Kullanılan girdiler" : "Inputs used" },
    ];
    const vk = Object.keys(t.kullanilan_varsayilanlar || {});
    const GIRDI_BIRIM = { oksijen: "%", basinc: "kPa", g: "g₀", akis: "cm/s", kalinlik: "mm" };
    Object.keys(t.girdi || {}).forEach((k) => {
      alanlar.push({
        ad: "g-" + k, etiket: k, salt: true, birim: GIRDI_BIRIM[k] || "",
        bicim: () => (t.girdi[k] == null
          ? `<i class="sonuk">${esc(T("genel.bilinmiyor"))}</i>`
          : esc(typeof t.girdi[k] === "number" ? nf(t.girdi[k], 5) : t.girdi[k]) +
            (vk.indexOf(k) >= 0 ? ` <span class="etiket">${esc(DIL === "tr" ? "varsayılan" : "default")}</span>` : "")),
      });
    });
    degerler = {};
  }

  Kabuk.ozellikCiz(baslik, alanlar, degerler, alanDegisti);
}

function cozumDurumMetni() {
  if (S.cozuluyor) return T("durum.cozuluyor");
  if (S.cozumHata && !S.sonuc) return DIL === "tr" ? "hata" : "error";
  if (!S.sonuc) return DIL === "tr" ? "çözülmedi" : "not solved";
  return cozumGuncel() ? (DIL === "tr" ? "güncel" : "up to date") : (DIL === "tr" ? "girdi değişti — yeniden çözülmeli" : "inputs changed — re-solve needed");
}

const yuvarla = (v, b) => (v == null ? null : Math.round(v * Math.pow(10, b)) / Math.pow(10, b));

function alanDegisti(ad, deger) {
  const b = S.ayarlar.birimler;
  switch (ad) {
    case "cozumTuru": cozumTuruDegisti(deger); return;
    case "onTahmin": S.onTahmin = deger !== "kapali"; kirlet(true); return;
    case "onayar": {
      const o = ONAYARLAR.find((x) => x.ad === deger);
      if (o) onayarUygula(o);
      return;
    }
    case "g": {
      const v = gOku(deger);
      S.girdi.g = isNaN(v) ? NaN : v;
      ozelYap();
      break;
    }
    case "basinc":
      S.girdi.basinc = deger === "" ? NaN : birimdenCevir(Number(deger), "basinc", b.basinc);
      ozelYap();
      break;
    case "oksijen":
      S.girdi.oksijen = deger === "" ? NaN : Number(deger);
      ozelYap();
      break;
    case "seyreltici": S.girdi.seyreltici = deger; ozelYap(); break;
    case "malzeme":
      S.girdi.malzeme = deger === "__diger" ? "" : deger;
      // yakıt türü malzemenin özelliğidir: önceki malzemede elle seçilmiş (örn. sıvı) değer yeni malzemeye taşınmaz
      S.dokunuldu.yakit_turu = false; S.otoYakit = false;
      malzemeDegisti();
      kirlet(true); ayrintiCiz(); agacYenile(); gorselYenile(); dogrula();
      return;
    case "malzemeAd":
      S.girdi.malzeme = deger;
      malzemeDegisti();
      break;
    case "numune_tipi":
      S.dokunuldu.numune_tipi = deger !== "";
      S.girdi.numune_tipi = deger || null;
      if (GAZ_NUMUNE.indexOf(deger) >= 0 && !S.dokunuldu.yakit_turu) {   // gaz geometrisi -> yakıt türü gaz
        S.dokunuldu.yakit_turu = true;
        S.girdi.yakit_turu = "gaz";
        S.otoYakit = true;
      }
      setTimeout(ayrintiCiz, 0);      // etiket (kalınlık / çap) ve gaz grubu numune tipine bağlı
      break;
    case "kalinlik":
      S.dokunuldu.kalinlik = deger !== "";
      S.girdi.kalinlik = deger === "" ? null : Number(deger);
      break;
    case "yakit_turu":
      S.dokunuldu.yakit_turu = deger !== "";
      S.girdi.yakit_turu = deger || null;
      break;
    case "akisBilinmiyor":
      S.girdi.akisBilinmiyor = !!deger;
      kirlet(true); ayrintiCiz(); agacYenile(); dogrula();
      return;
    case "akis":
      S.girdi.akis = deger === "" ? NaN : birimdenCevir(Number(deger), "akis", b.akis);
      break;
    case "akis_yonu": S.girdi.akis_yonu = deger; break;
    case "sup_parametre": {
      S.supurme.parametre = deger;
      const v = supurAlan(deger).varsayilan;
      S.supurme.bas = v[0]; S.supurme.son = v[1]; S.supurme.adim = v[2];
      S.supurme.sonuc = null;
      ayrintiCiz(); agacYenile(); gorselYenile();
      return;
    }
    case "sup_bas": S.supurme.bas = Number(deger); ayrintiCiz(); gorselYenile(); return;
    case "sup_son": S.supurme.son = Number(deger); ayrintiCiz(); gorselYenile(); return;
    case "sup_adim": S.supurme.adim = Number(deger); ayrintiCiz(); gorselYenile(); return;
    case "baslik": S.baslik = deger; S.baslikOto = !deger; break;
    case "aciklama": S.aciklama = deger; break;
    case "etiketler": S.etiketler = String(deger).split(",").map((x) => x.trim()).filter(Boolean); break;
    default: return;
  }
  kirlet(true);
  dogrula();
  agacYenile();
  if (Kabuk.aktif() === "calisma" && (Kabuk.agacSecili() || "").indexOf("r-") !== 0) gorselYenile();
  else if (Kabuk.aktif() === "calisma" && Kabuk.agacSecili() === "r-llm" && S.sonuc) llmGorseli();   // yorum + sohbet "girdiler değişti" durumu
  hataGoster();
}

let hataZaman = null;
function hataGoster() {
  clearTimeout(hataZaman);
  hataZaman = setTimeout(() => {
    const kap = $("#ayrintilar");
    if (!kap) return;
    kap.querySelectorAll("[data-alan]").forEach((el) => {
      el.classList.toggle("hatali", !!S.hatalar[el.dataset.alan]);
    });
  }, 150);
}

/* ---------------------------------------------------------------- GÖRSEL ALAN */
/* Sonuç düğümleri için sol üst başlık bloğu: sonuç adı, tür, birim, koşul ve zaman */
const SONUC_META = {
  "r-ozet":      [["Risk değerlendirmesi (birleşik yanma ihtimali)", "Risk assessment (combined burning probability)"], "%"],
  "r-motor":     [["Fizik motoru çıktıları", "Physics engine outputs"], ["karışık", "mixed"]],
  "r-ofm":     [["Ayrıntılı motor (OpenFOAM)", "Detailed engine (OpenFOAM)"], ["karışık", "mixed"]],
  "r-3b":        [["3B alan sonucu (OpenFOAM)", "3D field result (OpenFOAM)"], ["K · kütle kesri · m/s", "K · mass fraction · m/s"]],
  "r-guven":     [["Güven skoru", "Confidence score"], ["puan / 100", "points / 100"]],
  "r-oksijen":   [["Yanma ihtimali — oksijen taraması", "Burning probability — oxygen sweep"], ["olasılık (0–1) · x: % O₂", "probability (0–1) · x: % O₂"]],
  "r-harita":    [["Yanabilirlik haritası (g × O₂)", "Flammability map (g × O₂)"], ["olasılık (0–1)", "probability (0–1)"]],
  "r-akis":      [["Motor yanma ihtimali — akış taraması", "Engine burning probability — flow sweep"], ["olasılık (0–1) · x: cm/s", "probability (0–1) · x: cm/s"]],
  "r-deney":     [["Yakın deneyler (NASA PSI)", "Nearby experiments (NASA PSI)"], ["tablo", "table"]],
  "r-adimlar":   [["Analiz adımları", "Analysis steps"], "ms"],
  "r-sinirlama": [["Kısmi yerçekimi sınırlaması", "Partial-gravity bounding"], "%"],
  "r-llm":       [["Yapay zeka yorumu", "AI commentary"], ["metin", "text"]],
  "r-render":    [["CFD render (OpenFOAM)", "CFD render (OpenFOAM)"], ["video", "video"]],
  "r-dunya":     [["Dünya uygulamaları", "Earth applications"], ["metin", "text"]],
};
function sonucBlogu(id, ad) {
  const m = SONUC_META[id];
  const s = S.sonuc;
  if (!m || !s || !s.tahmin) return "";
  const i = DIL === "tr" ? 0 : 1;
  const k = s.tahmin.girdi || s.kosul || {};
  const kosulMetni = [k.malzeme, "g = " + gMetni(k.g) + " g₀", "%" + nf(k.oksijen, 1) + " O₂", nf(k.basinc, 1) + " kPa",
    k.akis == null ? (DIL === "tr" ? "akış bilinmiyor" : "flow unknown") : nf(k.akis, 1) + " cm/s"].join(" · ");
  const birim = Array.isArray(m[1]) ? m[1][i] : m[1];
  return ayrintiliBannerHtml() + `<div class="sonuc-blok"><b>${esc(ad)}</b>` +
    (S.ayrintili && S.ayrintili.durum === "bitti" && ["r-ozet", "r-ofm", "r-motor"].indexOf(id) >= 0 ? `<span style="color:var(--vurgu)">${esc(DIL === "tr" ? "Kaynak: Ayrıntılı (OpenFOAM)" : "Source: Detailed (OpenFOAM)")}</span>` : "") +
    `<span>${esc(DIL === "tr" ? "Tür" : "Type")}: ${esc(m[0][i])}</span>` +
    `<span>${esc(DIL === "tr" ? "Birim" : "Unit")}: ${esc(birim)}</span>` +
    `<span>${esc(DIL === "tr" ? "Koşul" : "Condition")}: ${esc(kosulMetni)}</span>` +
    `<span>${esc(DIL === "tr" ? "Zaman" : "Time")}: ${esc(s.zaman || (DIL === "tr" ? "kayıtlı vaka" : "stored case"))}</span>` +
    (cozumGuncel() ? "" : `<span class="eski">${esc(DIL === "tr" ? "Girdiler değişti — sonuç eski, yeniden çözün (F8)" : "Inputs changed — result is stale, re-solve (F8)")}</span>`) +
    `</div>`;
}

function gorselYenile() {
  const id = Kabuk.agacSecili() || "ortam";
  const t = S.sonuc && S.sonuc.tahmin;

  if (id === "supurme") return supurmeGorseli();
  if (id === "proje" || id === "vaka") return kurulumGorseli();
  if (["ortam", "malzeme", "numune", "akis", "cozumAyar"].indexOf(id) >= 0) return girdiGorseli(id);
  if (id === "cozum") return cozumBilgisiGoster();
  if (id === "r-llm") return llmGorseli();      // yorum sayfası sonuç/motor olmadan da açılır
  if (ayrintiliBekleGorseli(id)) return;
  if (!t) return Kabuk.gorselYaz(T("sonuc.yokHenuz"),
    `<div class="gorunum ortala"><div class="bos"><b>${esc(T("sonuc.yokHenuz"))}</b>${esc(T("sonuc.yokHenuzAlt"))}</div></div>`);

  switch (id) {
    case "r-ozet": ozetGorseli(); return ayrintiliOzetEkle();
    case "r-oksijen": return egriGorseli();
    case "r-harita": return haritaGorseli();
    case "r-akis": return akisGorseli();
    case "r-deney": return deneyGorseli();
    case "r-guven": return guvenGorseli();
    case "r-motor": return motorGorseli();
    case "r-ofm": return ofmGorseli();
    case "r-3b": return s3Goster("sonuc", T("agac.sonuc3b"), null, "");
    case "r-adimlar": return Kabuk.gorselYaz(T("agac.adimlar"), `<div class="gorunum">` +
      (t.adimlar && t.adimlar.length ? adimTablosu(t.adimlar) : `<div class="bos">—</div>`) + `</div>`);
    case "r-sinirlama": return sinirlamaGorseli();
    case "r-llm": return llmGorseli();
    case "r-render": return renderGorseli();
    case "r-dunya": return dunyaGorseli();
    default: return ozetGorseli();
  }
}

function gBandi() {
  const g = S.sonuc ? S.sonuc.tahmin.girdi.g : S.girdi.g;
  if (!(g >= 0.01 && g < 0.9)) return "";
  const yer = g < 0.25 ? (DIL === "tr" ? "Ay" : "the Moon") : (DIL === "tr" ? "Mars" : "Mars");
  return `<div class="g-band"><b>${esc(DIL === "tr" ? "Kısmi yerçekimi" : "Partial gravity")}</b>` +
    esc(DIL === "tr"
      ? `g = ${nf(g, 3)} (${yer}) için doğrudan deney verisi azdır. Sonuç; uzay, gerçek g ve Dünya hesaplarının en kötüsü alınarak sınırlanmıştır.`
      : `There is little direct experimental data at g = ${nf(g, 3)} (${yer}). The result is bounded by the worst of the space, actual-g and Earth cases.`) +
    `</div>`;
}

/* Seçili girdi düğümünün kısa özeti (düzenleme Ayrıntılar panelinde) */
let S3_KULLAN = true;          // WebGL açılamazsa false: eski tablo görünümüne düşülür
function girdiGorseli(id) {
  yakitKilitle();
  const b = S.ayarlar.birimler;
  const vd = malzemeVarsayilani(S.girdi.malzeme);
  const tr = DIL === "tr";
  const satir = (ad, deger, ek) =>
    `<div class="bilgi-satir"><span class="etiket-ad">${esc(ad)}</span><span class="deger">${deger}</span>` +
    (ek ? `<span class="sonuk" style="margin-left:auto">${esc(ek)}</span>` : "") + `</div>`;
  const kart = (baslik, ic) => `<div class="kart" style="max-width:640px"><h3>${esc(baslik)}</h3>${ic}</div>`;
  const varsay = (dokundu) => (dokundu ? "" : (tr ? "kütüphane varsayılanı" : "library default"));
  const hatalar = { ortam: ["g", "basinc", "oksijen"], malzeme: ["malzeme"], numune: ["kalinlik"], akis: ["akis"], cozumAyar: [] }[id]
    .filter((a) => S.hatalar[a]).map((a) => S.hatalar[a]);
  let ic = "", ek = "";

  if (id === "ortam") {
    const o = ONAYARLAR.find((x) => x.ad === S.onayar);
    ic = kart(tr ? "Ortam" : "Environment",
      satir(T("alan.onayar"), esc(onayarAdi(S.onayar) || (tr ? "özel" : "custom")), o && o.not ? o.not : "") +
      satir(T("alan.g"), `<span class="sayi">${esc(gMetni(S.girdi.g))}</span> g₀`,
            S.girdi.g < 0.01 ? (tr ? "mikro yerçekimi" : "microgravity") : S.girdi.g < 0.9 ? (tr ? "kısmi" : "partial") : (tr ? "Dünya" : "Earth")) +
      satir(T("alan.basinc"), `<span class="sayi">${esc(nf(birimeCevir(S.girdi.basinc, "basinc", b.basinc), birimBasamak("basinc", b.basinc)))}</span> ${esc(b.basinc)}`) +
      satir(T("alan.oksijen"), `<span class="sayi">%${esc(nf(S.girdi.oksijen, 2))}</span>`, S.girdi.oksijen > 23 ? (tr ? "zenginleştirilmiş" : "enriched") : "") +
      satir(T("alan.seyreltici"), esc(S.girdi.seyreltici)));
    ek = `<div class="gorunum-bas"><h3>${esc(tr ? "Ön ayarlar" : "Presets")}</h3></div>` +
      `<div class="suzgec" id="onayarlar">` + ONAYARLAR.map((x) =>
        `<button class="dugme${x.ad === S.onayar ? " birincil" : ""}" data-onayar="${esc(x.ad)}" title="${esc(x.not || "")}">${esc(tr ? x.ad : x.en)}</button>`).join("") + `</div>`;
  } else if (id === "malzeme") {
    ic = kart(T("agac.malzeme"),
      satir(T("alan.malzeme"), `<b>${esc(S.girdi.malzeme || "—")}</b>`, vd ? "" : (tr ? "kütüphanede varsayılan yok" : "no library defaults")) +
      satir(T("alan.yakit"), esc(S.dokunuldu.yakit_turu ? S.girdi.yakit_turu : (vd && vd[2]) || "—"), varsay(S.dokunuldu.yakit_turu)) +
      satir(tr ? "Varsayılan numune" : "Default sample", esc(vd && vd[0] ? vd[0] : "—")) +
      satir(tr ? "Varsayılan kalınlık / çap" : "Default thickness / diameter", esc(vd && vd[1] != null ? nf(vd[1], 3) + " mm" : "—")));
  } else if (id === "numune") {
    const tip = S.girdi.numune_tipi || (vd && vd[0]) || "";
    const capli = GAZ_CAPLI.indexOf(tip) >= 0;
    const kal = S.dokunuldu.kalinlik ? S.girdi.kalinlik : vd && vd[1];
    ic = kart(T("agac.numune"),
      satir(T("alan.numune"), esc(tip || "—"), varsay(S.dokunuldu.numune_tipi)) +
      satir(capli ? (tr ? "Çap" : "Diameter") : T("alan.kalinlik"), esc(kal != null ? nf(kal, 3) + " mm" : "—"), varsay(S.dokunuldu.kalinlik)) +
      (GAZ_NUMUNE.indexOf(tip) >= 0 ? satir(tr ? "Yakıt debisi" : "Fuel mass flow",
        esc(S.sonuc && S.sonuc.tahmin.motor && S.sonuc.tahmin.motor.debi_mg_s != null ? nf(S.sonuc.tahmin.motor.debi_mg_s, 3) + " mg/s" : "—"),
        tr ? "gaz motorundan" : "from gas engine") : ""));
    if (!tip) ek = `<div class="uyari-satir" style="max-width:640px;margin-top:12px"><span>${esc(tr ? "Numune tipi yok: bu malzemenin kütüphane varsayılanı da olmadığından model en genel durumu kullanır. Ayrıntılar panelinden seçin." : "No sample type and no library default: the model uses the most generic case. Choose one in the Details panel.")}</span></div>`;
  } else if (id === "akis") {
    ic = kart(T("agac.akis"),
      satir(T("alan.akis"), S.girdi.akisBilinmiyor ? `<i class="sonuk">${esc(T("genel.bilinmiyor"))}</i>`
        : `<span class="sayi">${esc(nf(birimeCevir(S.girdi.akis, "akis", b.akis), birimBasamak("akis", b.akis)))}</span> ${esc(b.akis)}`,
        S.girdi.akisBilinmiyor ? (tr ? "en kötü durum varsayılır" : "worst case assumed") : S.girdi.akis === 0 ? (tr ? "durgun ortam" : "quiescent") : "") +
      satir(T("alan.akisYonu"), esc(S.girdi.akis_yonu || "—")));
    ek = `<div class="grafik-not" style="max-width:640px">${esc(T("ipucu.akis"))}</div>`;
  } else {
    const t = S.sonuc && S.sonuc.tahmin;
    ic = kart(T("agac.cozumAyar"),
      satir(T("alan.motor"), esc(t ? motorAdi(t) : (tr ? "çözümde yakıt türüne göre seçilir" : "chosen at solve by fuel type"))) +
      satir(T("alan.llmIste"), esc({ yok: tr ? "istenmedi" : "not requested", bekle: tr ? "bekleniyor" : "pending", geldi: tr ? "alındı" : "received", hata: tr ? "alınamadı" : "failed" }[S.llm.durum])) +
      satir(tr ? "SI anahtarı" : "SI key", esc(S.sistem.anahtar_var ? (tr ? "bulundu" : "found") : (tr ? "yok" : "missing"))));
  }
  const hata = hatalar.length ? `<div class="uyari-satir kritik" style="max-width:640px">${hatalar.map(esc).join(" · ")}</div>` : "";
  // 3B sahne: girdi düğümlerinde ortadaki tablo (Ayrıntılar'ın kopyası) yerine geometri (js/scene3d.js); WebGL yoksa eski görünüm
  if (id !== "cozumAyar" && window.THREE && S3_KULLAN) {
    const ad3 = ({ ortam: T("agac.ortam"), malzeme: T("agac.malzeme"), numune: T("agac.numune"), akis: T("agac.akis") })[id];
    s3Goster("girdi", ad3, id, (id === "ortam" ? ek : "") + hata + (id === "ortam" ? gBandi() : "")).then((ok) => { if (!ok) { S3_KULLAN = false; girdiGorseli(id); } });
    return;
  }
  Kabuk.gorselYaz(({ ortam: T("agac.ortam"), malzeme: T("agac.malzeme"), numune: T("agac.numune"), akis: T("agac.akis"), cozumAyar: T("agac.cozumAyar") })[id],
    `<div class="gorunum">` + (id === "ortam" ? gBandi() : "") + hata + ic + ek + `</div>`,
    `<button class="dugme kucuk" data-komut="coz">${esc(T("komut.coz"))} · F8</button>`);
}

function kurulumGorseli() {
  const b = S.ayarlar.birimler;
  const vd = malzemeVarsayilani(S.girdi.malzeme);
  const onayarlar = ONAYARLAR.map((o) =>
    `<button class="dugme${o.ad === S.onayar ? " birincil" : ""}" data-onayar="${esc(o.ad)}" title="${esc(o.not || "")}">${esc(DIL === "tr" ? o.ad : o.en)}</button>`).join("");

  const satir = (ad, deger, ek) =>
    `<div class="bilgi-satir"><span class="etiket-ad">${esc(ad)}</span><span class="deger">${deger}</span>` +
    (ek ? `<span class="sonuk" style="margin-left:auto">${esc(ek)}</span>` : "") + `</div>`;

  const hata = Object.keys(S.hatalar).length
    ? `<div class="uyari-satir kritik">${Object.keys(S.hatalar).map((k) => esc(S.hatalar[k])).join(" · ")}</div>` : "";

  const ic =
    `<div class="gorunum">` +
    gBandi() + hata +
    `<div class="gorunum-bas"><h3>${esc(DIL === "tr" ? "Ortam ön ayarları" : "Environment presets")}</h3></div>` +
    `<div class="suzgec" id="onayarlar">${onayarlar}</div>` +
    `<div class="kutular k2" style="margin-top:18px">` +
      `<div class="kart"><h3>${esc(DIL === "tr" ? "Vaka özeti" : "Case summary")}</h3>` +
        satir(T("alan.g"), `<span class="sayi">${esc(gMetni(S.girdi.g))}</span>`,
              S.girdi.g < 0.01 ? (DIL === "tr" ? "mikro yerçekimi" : "microgravity") : S.girdi.g < 0.9 ? (DIL === "tr" ? "kısmi" : "partial") : (DIL === "tr" ? "Dünya" : "Earth")) +
        satir(T("alan.basinc"), `<span class="sayi">${esc(nf(birimeCevir(S.girdi.basinc, "basinc", b.basinc), birimBasamak("basinc", b.basinc)))}</span> ${esc(b.basinc)}`) +
        satir(T("alan.oksijen"), `<span class="sayi">%${esc(nf(S.girdi.oksijen, 2))}</span>`,
              S.girdi.oksijen > 23 ? (DIL === "tr" ? "zenginleştirilmiş" : "enriched") : "") +
        satir(T("alan.seyreltici"), esc(S.girdi.seyreltici)) +
        satir(T("alan.malzeme"), `<b>${esc(S.girdi.malzeme || "—")}</b>`, vd ? "" : (DIL === "tr" ? "varsayılan yok" : "no defaults")) +
        satir(T("alan.numune"), esc(S.dokunuldu.numune_tipi ? S.girdi.numune_tipi : (vd ? vd[0] : "—")),
              S.dokunuldu.numune_tipi ? "" : (DIL === "tr" ? "varsayılan" : "default")) +
        satir(T("alan.kalinlik"), esc(S.dokunuldu.kalinlik ? nf(S.girdi.kalinlik, 2) : (vd && vd[1] != null ? nf(vd[1], 2) : "—")) + " mm",
              S.dokunuldu.kalinlik ? "" : (DIL === "tr" ? "varsayılan" : "default")) +
        satir(T("alan.akis"), S.girdi.akisBilinmiyor
          ? `<i class="sonuk">${esc(T("genel.bilinmiyor"))}</i>`
          : `<span class="sayi">${esc(nf(birimeCevir(S.girdi.akis, "akis", b.akis), birimBasamak("akis", b.akis)))}</span> ${esc(b.akis)}`,
          S.girdi.akisBilinmiyor ? (DIL === "tr" ? "en kötü durum" : "worst case") : "") +
      `</div>` +
      `<div class="kart"><h3>${esc(DIL === "tr" ? "Çözümde ne olacak" : "What solving does")}</h3>` +
        `<div class="akis" style="grid-template-columns:1fr;margin:0">` +
        [[T("coz.adimTahmin"), DIL === "tr" ? "Eğitilmiş risk modeli yanma ihtimalini ve belirsizliğini verir." : "The trained risk model returns burning probability and uncertainty."],
         [T("coz.adimOksijen"), DIL === "tr" ? "%5–60 arasında oksijene göre ihtimal eğrisi ve sönme sınırı." : "Probability curve and extinction limit over 5–60% oxygen."],
         [T("coz.adimHarita"), DIL === "tr" ? "Yerçekimi × oksijen düzleminde yanabilirlik haritası." : "Flammability map over the gravity × oxygen plane."],
         [T("coz.adimYakin"), DIL === "tr" ? "Bu koşula yakın gerçek NASA deneyleri taranır." : "Real NASA experiments close to this condition are scanned."]]
          .map((p, i) => `<div class="akis-adim"><div class="no">${i + 1}</div><b>${esc(p[0])}</b><span>${esc(p[1])}</span></div>`).join("") +
        `</div></div>` +
    `</div></div>`;

  Kabuk.gorselYaz(DIL === "tr" ? "Vaka kurulumu" : "Case setup", ic,
    `<button class="dugme kucuk" data-komut="coz">${esc(T("komut.coz"))} · F8</button>`);

  const k = $("#onayarlar");
  if (k) k.addEventListener("click", (e) => {
    const d = e.target.closest("[data-onayar]");
    if (!d) return;
    const o = ONAYARLAR.find((x) => x.ad === d.dataset.onayar);
    if (o) onayarUygula(o);
  });
}

/* ------------------------------------------------- sonuç görünümleri */
/* motorun asıl kaynağı (tahmin.motor_kaynagi) ve dürüst test AUC'si; "yonlendirici" yalnız seçicinin adı */
const MOTOR_ADI = {
  hafif: ["hafif motor (katı)", "light engine (solid)"], damla: ["damla motoru (sıvı)", "droplet engine (liquid)"],
  gaz: ["gaz motoru", "gas engine"], ofm_tablo: ["OpenFOAM tablosu", "OpenFOAM table"],
  "ofm+hafif": ["OpenFOAM tablosu + hafif motor", "OpenFOAM table + light engine"],
};
function motorAdi(t) {
  const k = t && t.motor_kaynagi;
  return k ? (MOTOR_ADI[k] ? mlzDil(MOTOR_ADI[k]) : k) : (DIL === "tr" ? "motor yok" : "no engine");
}
function motorAucMetni(t) {
  const a = t && t.motor ? t.motor.motor_auc : null;
  return a == null ? (DIL === "tr" ? "AUC yok (kalibre değil)" : "no AUC (not calibrated)") : "AUC " + nf(a, 2);
}
/* risk seviyesi eşikleri risk_model.RISK ile aynı: <%20 DÜŞÜK, <%50 ORTA, <%80 YÜKSEK, üstü ÇOK YÜKSEK */
function seviyeMetni(p) {
  if (p == null) return "—";
  const y = 100 * p;
  return DIL === "tr" ? (y < 20 ? "DÜŞÜK" : y < 50 ? "ORTA" : y < 80 ? "YÜKSEK" : "ÇOK YÜKSEK")
                      : (y < 20 ? "LOW" : y < 50 ? "MEDIUM" : y < 80 ? "HIGH" : "VERY HIGH");
}
/* model / motor ağırlık çubuğu (tahmin.agirliklar); motor 0 ise motor kısmı boş + "kalibre değil" */
function agirlikCubugu(t) {
  const w = t.agirliklar || { model: 1, motor: 0 };
  const wm = Math.max(0, Math.min(1, w.model || 0)), wo = Math.max(0, Math.min(1, w.motor || 0));
  return `<div class="cubuk-bas" style="margin-top:12px"><span>${esc(DIL === "tr" ? "Birleşik ihtimalde ağırlıklar" : "Weights in the combined probability")}</span>` +
      `<span>${esc(DIL === "tr" ? "model" : "model")} %${esc(pct(wm, 0))} · ${esc(DIL === "tr" ? "motor" : "engine")} %${esc(pct(wo, 0))}</span></div>` +
    `<div class="cubuk"><i style="left:0;width:${wm * 100}%;background:var(--vurgu)"></i>` +
      (wo > 0 ? `<i style="left:${wm * 100}%;width:${wo * 100}%;background:var(--g-seri2)"></i>` : "") + `</div>` +
    `<div class="cubuk-alt"><span>${esc(DIL === "tr" ? "risk modeli" : "risk model")}</span>` +
      (wo > 0 ? `<span>${esc(motorAdi(t))}</span>`
              : `<span class="etiket uyari">${esc(DIL === "tr" ? "motor kalibre değil — ağırlık 0" : "engine not calibrated — weight 0")}</span>`) + `</div>`;
}

/* ---------------------------------------------------------------- güven v2 (tahmin.guven_v2) */
const BANT_RENK = { "yüksek": "var(--ok)", "orta": "var(--uyari)", "düşük": "var(--hata)" };
const BANT_EN = { "yüksek": "high", "orta": "medium", "düşük": "low" };
function guvenV2(t) { return t && t.guven_v2 && t.guven_v2.skor != null ? t.guven_v2 : null; }
function guvenSkoru(t) { const v = guvenV2(t); return v ? v.skor : (t && t.guven ? t.guven.skor : null); }
/* skorun tek cümlelik sebebi: NASA deneyi yok/az, kapsam dışı, eşleme ... */
function guvenSebebi(t) {
  const v = guvenV2(t);
  if (!v) return "";
  const nasa = (v.yakin_deney_kaynaklari || {})["NASA PSI"] || 0;
  const ceza = (v.cezalar || []).map((c) => c.ad);
  const motorYok = !t.motor || !(t.agirliklar && t.agirliklar.motor > 0);
  if (v.bant !== "düşük") {
    if (nasa === 0) return DIL === "tr" ? "Bu koşulda NASA deneyi yok." : "No NASA experiment at this condition.";
    if (ceza.length) return (DIL === "tr" ? "Ceza: " : "Penalty: ") + ceza.join(", ") + ".";
    return DIL === "tr" ? `Yakında ${nasa} NASA deneyi var.` : `${nasa} NASA experiments nearby.`;
  }
  // düşük güven: bütün somut sebepler tek cümlede (arka uçtaki _guven_dusuk_cumlesi ile aynı sıra)
  const s = [];
  if (nasa === 0) s.push(DIL === "tr" ? "bu koşula yakın NASA deneyi yok" : "no NASA experiment near this condition");
  else if (nasa < 5) s.push(DIL === "tr" ? `yakın NASA deneyi az (${nasa})` : `few nearby NASA experiments (${nasa})`);
  ceza.forEach((c) => s.push(c));
  if (motorYok) s.push(DIL === "tr" ? "fizik motoru kullanılmadı (ağırlık 0)" : "physics engine not used (weight 0)");
  else if ((v.bilesenler || {}).motor < 0.3) s.push(DIL === "tr" ? "motor bu koşulda zayıf" : "engine weak at this condition");
  const c = s.length ? s.join("; ") : (DIL === "tr" ? "bileşenlerin toplamı eşiğin altında" : "components sum below threshold");
  return c.charAt(0).toLocaleUpperCase(DIL === "tr" ? "tr-TR" : "en-US") + c.slice(1) + ".";
}
function bantMetni(b) { return DIL === "tr" ? b : (BANT_EN[b] || b); }

function taninmadiGorseli(t) {
  const l = t.llm_siniflandirma || {}, ad = l.girilen || (t.girdi || {}).malzeme || "";
  const neden = l.durum === "baglanti_yok"
    ? (DIL === "tr" ? "Liste ve kütüphanede yok; LLM'e de ulaşılamadı (internet / SI yok)." : "Not in the list or library; the LLM could not be reached (no internet / SI).")
    : (DIL === "tr" ? "Liste ve kütüphanede yok; LLM bunu bir malzeme olarak tanımadı." : "Not in the list or library; the LLM did not recognize it as a material.");
  Kabuk.gorselYaz(T("agac.ozet"),
    `<div class="gorunum"><div class="kart" style="max-width:760px">` +
      `<h3>${esc(DIL === "tr" ? "Malzeme tanınmadı" : "Material not recognized")}</h3>` +
      `<div style="font-size:20px;font-weight:700;margin:6px 0 10px">“${esc(ad)}”</div>` +
      `<div class="uyari-satir"><span>${esc(neden)}${l.sebep ? `<br><span class="sonuk" style="font-size:11.5px">${esc(l.sebep)}</span>` : ""}</span></div>` +
      `<p class="sonuk" style="margin:10px 0">${esc(DIL === "tr" ? "Uydurma sonuç üretilmedi: risk, sönme sınırı ve güven hesaplanmadı." : "No made-up result: risk, extinction limit and confidence were not computed.")}</p>` +
      `<div style="display:flex;gap:9px"><button class="dugme birincil" data-komut="git-malzeme">${esc(DIL === "tr" ? "Listeden malzeme seç" : "Pick a material")}</button>` +
      `<button class="dugme" data-mlzekle="${esc(ad)}">${esc(DIL === "tr" ? "Kütüphaneye malzeme olarak ekle" : "Add to the library as a material")}</button></div>` +
    `</div></div>`);
}

function ozelDurumGorseli(t) {
  const o = t.ozel_durum, ad = (t.girdi || {}).malzeme || o.ad;
  const baslik = { oksitleyici: ["Oksitleyici: yanmaz ama yangını şiddetlendirir", "Oxidizer: does not burn but intensifies fire"],
                   yanmaz: ["Yanıcı değil", "Not flammable"], pil: ["Pil: termal kaçak modeli yok", "Battery: no thermal-runaway model"] }[o.tur];
  Kabuk.gorselYaz(T("agac.ozet"),
    `<div class="gorunum"><div class="kart" style="max-width:760px">` +
      `<h3>${esc(baslik ? mlzDil(baslik) : o.baslik)}</h3>` +
      `<div style="font-size:20px;font-weight:700;margin:6px 0 10px">“${esc(ad)}” <span class="sonuk" style="font-size:13px;font-weight:400">= ${esc(o.ad)}${o.kategori ? " · " + esc(katAdi(o.kategori)) : ""}</span></div>` +
      (t.uyarilar || []).map((u) => `<div class="uyari-satir"><span>${esc(u)}</span></div>`).join("") +
      `<p class="sonuk" style="margin:10px 0">${esc(DIL === "tr" ? "Yakıt olarak çözülmedi: yanma ihtimali, sönme sınırı, grafikler ve güven hesaplanmadı." : "Not solved as a fuel: burn probability, extinction limit, charts and confidence were not computed.")}</p>` +
      `<div style="display:flex;gap:9px"><button class="dugme birincil" data-komut="git-malzeme">${esc(DIL === "tr" ? "Başka malzeme seç" : "Pick another material")}</button>` +
      `<button class="dugme" data-malzeme="${esc(o.id)}" data-mlzkaynak="kutuphane">${esc(DIL === "tr" ? "Kütüphane kaydını aç" : "Open library entry")}</button></div>` +
    `</div></div>`);
}

function ozetGorseli() {
  const t = S.sonuc.tahmin, g = t.guven || {}, p = t.yanma_ihtimali;
  if (t.ozel_durum) return ozelDurumGorseli(t);
  if (p == null) return taninmadiGorseli(t);
  const pb = t.yanma_birlesik != null ? t.yanma_birlesik : p;      // ana sayı: birleşik ihtimal
  const w = t.agirliklar || { model: 1, motor: 0 };
  const gk = t.guvenlik_katsayisi;
  const dogrulanmamis = guvenV2(t) ? !((t.guven_v2.yakin_deney_kaynaklari || {})["NASA PSI"] > 0) : g.skor === 0;
  const bilinmeyen = (t.uyarilar || []).some((u) => u.indexOf("için varsayılan yok") >= 0);
  const celiski = t.motor && t.motor.yanma != null && (p >= 0.5) !== (t.motor.yanma >= 0.5);

  const gkRenk = gk == null ? "var(--cok-sonuk)" : gk < 1 ? "var(--hata)" : "var(--ok)";
  const skRenk = g.skor === 0 ? "var(--hata)" : g.skor < 60 ? "var(--uyari)" : "var(--ok)";

  let ic = `<div class="gorunum">` + gBandi() +
    `<div class="risk-ust">` +
      `<div class="risk-levha" style="border-color:${SEVIYE_RENK(pb)}">` +
        `<div class="seviye" style="color:${SEVIYE_YAZI(pb)}">${esc(seviyeMetni(pb))}</div>` +
        `<div class="oran">${esc(DIL === "tr" ? "Birleşik yanma ihtimali" : "Combined burn probability")}: <b>%${esc(pct(pb, 0))}</b></div>` +
        `<div class="sonuk" style="font-size:12px">${esc(DIL === "tr" ? "risk modeli" : "risk model")} <b style="color:var(--yazi)">%${esc(pct(p, 0))}</b> ± ${esc(pct(t.belirsizlik, 0))}` +
          ` <span style="color:var(--cok-sonuk)">(${esc(DIL === "tr" ? "ağırlık" : "weight")} %${esc(pct(w.model, 0))})</span> · ` +
          `${esc(motorAdi(t))} <b style="color:var(--yazi)">${t.motor && t.motor.yanma != null ? "%" + esc(pct(t.motor.yanma, 0)) : "–"}</b>` +
          ` <span style="color:var(--cok-sonuk)">(${esc(DIL === "tr" ? "ağırlık" : "weight")} %${esc(pct(w.motor, 0))})</span></div>` +
        `<div class="risk-serit"><u style="left:${Math.max(0, Math.min(100, pb * 100))}%"></u></div>` +
        `<div class="etiketler">` +
          (seviyeMetni(p) !== seviyeMetni(pb) ? `<span class="etiket">${esc((DIL === "tr" ? "model seviyesi: " : "model level: ") + t.risk_seviyesi)}</span>` : "") +
          (dogrulanmamis ? `<span class="etiket uyari">${esc(T("sonuc.dogrulanmamis"))}</span>` : "") +
          (bilinmeyen ? `<span class="etiket uyari">${esc(T("sonuc.bilinmeyenMalzeme"))}</span>` : "") +
          (t.belirsizlik > 0.3 ? `<span class="etiket uyari">${esc(DIL === "tr" ? "yüksek belirsizlik" : "high uncertainty")}</span>` : "") +
        `</div></div>` +

      `<div class="kart olcu"><span class="ad">${esc(T("sonuc.guvenlikKatsayisi"))}</span>` +
        `<span class="buyuk" style="color:${gkRenk}">${gk == null ? esc(T("genel.hesaplanamadi")) : esc(nf(gk, 2))}</span>` +
        (gk == null ? "" :
          `<div class="cubuk"><i style="width:${Math.min(100, (gk / 2) * 100)}%;background:${gkRenk}"></i><u style="left:50%"></u></div>` +
          `<div class="cubuk-alt"><span>0</span><span>1</span><span>2</span></div>`) +
        `<span class="aciklama">` + esc(
          gk == null ? (DIL === "tr" ? "Model %5–60 aralığında sönme sınırı bulamadı." : "No extinction limit found in the 5–60% range.")
          : gk < 1 ? (DIL === "tr" ? "Ortam oksijeni sönme sınırının üstünde — alev yanabilir." : "Ambient oxygen exceeds the extinction limit — a flame can sustain.")
          : (DIL === "tr" ? "Ortam oksijeni sönme sınırının altında." : "Ambient oxygen is below the extinction limit.")) +
        `</span>` +
        (t.sonme_siniri == null ? "" :
          `<span class="aciklama">${esc(DIL === "tr" ? "Bu malzeme için oksijen en fazla" : "Oxygen should not exceed")} <b style="color:var(--yazi);font-size:15px">%${esc(nf(t.sonme_siniri, 1))}</b> ${esc(DIL === "tr" ? "olmalı (güvenlik payı eklenmemiştir)." : "(no safety margin added).")}</span>`) +
      `</div>` +

      (guvenV2(t)
        ? `<div class="kart olcu"><span class="ad">${esc(T("sonuc.guvenSkoru"))} <span class="etiket" style="color:${BANT_RENK[t.guven_v2.bant] || "var(--sonuk)"};border-color:${BANT_RENK[t.guven_v2.bant] || "var(--cizgi)"}">${esc(bantMetni(t.guven_v2.bant))}</span></span>` +
            yariDaire(t.guven_v2.skor, BANT_RENK[t.guven_v2.bant] || skRenk) +
            `<span class="aciklama" style="color:${t.guven_v2.bant === "yüksek" ? "var(--sonuk)" : BANT_RENK[t.guven_v2.bant]}">${esc(guvenSebebi(t))}</span>` +
            `<span class="aciklama" style="color:var(--cok-sonuk)">${esc(DIL === "tr" ? "eski skor (v1): " : "old score (v1): ")}${esc(nf(g.skor, 0))}</span>` +
          `</div>`
        : `<div class="kart olcu"><span class="ad">${esc(T("sonuc.guvenSkoru"))}</span>` +
        yariDaire(g.skor || 0, skRenk) +
        `<span class="aciklama" style="color:${g.skor < 60 ? skRenk : "var(--sonuk)"}">` + esc(
          g.skor === 0 ? (DIL === "tr" ? "Bu koşulda benzer deney yok; sonuç tamamen modelin dış değerlendirmesi." : "No similar experiment at this condition; the result is pure extrapolation.")
          : g.skor < 60 ? (DIL === "tr" ? "Düşük güven: yakın deney az ya da fizik motoru burada zayıf." : "Low confidence: few nearby experiments or a weak physics engine here.")
          : (DIL === "tr" ? "Yeterli güven." : "Adequate confidence.")) + `</span>` +
      `</div>`) +
    `</div>`;

  ic += `<div class="kutular k2" style="margin-top:14px">` +
    `<div class="kart"><h3>${esc(T("sonuc.uyarilar"))}</h3>` +
      (uyarilarGoster(t).length
        ? uyarilarGoster(t).map((u) => `<div class="uyari-satir">${esc(u)}</div>`).join("")
        : `<div class="sonuk">${esc(DIL === "tr" ? "Uyarı yok." : "No warnings.")}</div>`) +
      varsayilanKutusu(t) +
      (t.llm_siniflandirma ? `<div style="margin-top:10px"><button class="dugme kucuk birincil" data-mlzekle="${esc(t.llm_siniflandirma.girilen || "")}">` +
        `${esc(DIL === "tr" ? "Bu malzemeyi kütüphaneye ekle (LLM önerisiyle)" : "Add this material to the library (with LLM suggestion)")}</button></div>` : "") +
    `</div>` +
    `<div class="kart"><h3>${esc(T("sonuc.modelMotor"))}</h3>` +
      cubukCiz(DIL === "tr" ? "Risk modeli" : "Risk model", p, false) +
      (celiski ? `<div class="celiski">${esc(T("sonuc.celiski"))}</div>` : "") +
      cubukCiz((DIL === "tr" ? "Fizik motoru — " : "Physics engine — ") + motorAdi(t) + " · " + motorAucMetni(t),
               t.motor ? t.motor.yanma : null, !t.motor,
               t.kutuphane_eslesme && !t.kutuphane_eslesme.motor_benzeri
                 ? (DIL === "tr" ? "uygun motor yok" : "no suitable engine")
                 : (DIL === "tr" ? "motor bu koşulu bilmiyor" : "engine does not cover this")) +
      (t.motor && t.motor.benzer_malzeme ? `<div class="sonuk" style="font-size:11.5px;margin-top:4px">${esc(DIL === "tr" ? "motor benzer malzemeyle çalıştı: " : "engine ran with surrogate: ")}<b>${esc(t.motor.benzer_malzeme)}</b></div>` : "") +
      agirlikCubugu(t) +
      `<div class="sonuk" style="margin-top:11px">${esc(T("sonuc.sonmeSiniri"))} — ` +
        `${esc(DIL === "tr" ? "model" : "model")}: <b style="color:var(--yazi)">${t.sonme_siniri == null ? esc(T("genel.bulunamadi")) : "%" + esc(nf(t.sonme_siniri, 2))}</b> · ` +
        `${esc(DIL === "tr" ? "motor" : "engine")}: <b style="color:var(--yazi)">${!t.motor || t.motor.min_oksijen == null ? esc(T("genel.yok")) : "%" + esc(nf(t.motor.min_oksijen, 2))}</b></div>` +
    `</div></div></div>`;

  Kabuk.gorselYaz(T("agac.ozet"), ic,
    `<button class="dugme kucuk" data-komut="rapor">${esc(T("komut.raporK"))}</button>` +
    `<button class="dugme kucuk" data-komut="kaydet">${esc(T("komut.kaydetK"))}</button>`);
}

function varsayilanKutusu(t) {
  const ad = { kalinlik: DIL === "tr" ? "kalınlık" : "thickness", numune_tipi: DIL === "tr" ? "numune tipi" : "sample type", yakit_turu: DIL === "tr" ? "yakıt türü" : "fuel type" };
  const v = Object.keys(t.kullanilan_varsayilanlar || {}).map((a) =>
    `${esc(ad[a] || a)} = ${esc(t.kullanilan_varsayilanlar[a])}${a === "kalinlik" ? " mm" : ""}`);
  if (t.girdi && t.girdi.akis == null) v.push(esc(DIL === "tr" ? "hava akışı = bilinmiyor (en kötü durum)" : "air flow = unknown (worst case)"));
  return `<div class="uyari-satir bilgi" style="margin-top:10px"><span><b>${esc(T("sonuc.varsayilanlar"))}:</b> ${v.length ? v.join(" · ") : esc(T("genel.yok"))}</span></div>`;
}

function egriGorseli() {
  const s = S.sonuc;
  if (!s.oksijen_egrisi) return Kabuk.gorselYaz(T("agac.oksijen"), `<div class="gorunum"><div class="bos">${esc(DIL === "tr" ? "Eğri çizilemedi." : "Curve unavailable.")}</div></div>`);
  const not = (s.tahmin.sinirlama ? (DIL === "tr" ? "Kısmi yerçekiminde eğri; uzay, gerçek g ve Dünya eğrilerinin en kötüsüdür. " : "In partial gravity the curve is the worst of the space, actual-g and Earth curves. ") : "") +
    (DIL === "tr"
      ? "Noktalar yakın gerçek deneylerdir (kırmızı = yandı, yeşil = söndü; soluk olanlar dil modeliyle makalelerden otomatik çıkarılmıştır). Mevcut oksijenin ±3 puanı içindedir."
      : "The dots are real nearby experiments (red = burned, green = extinguished; faded ones were extracted automatically from papers by a language model), within ±3 points of the current oxygen.");
  const e = s.oksijen_egrisi, tr = DIL === "tr";
  Kabuk.gorselYaz(T("agac.oksijen"),
    `<div class="gorunum">` + oksijenCiz(e, { yakin: s.yakin, ortam: [s.tahmin.girdi.oksijen] }) +
    `<div class="grafik-not">${esc(not)}</div></div>`, "",
    { ad: "oksijen_egrisi", sutunlar: [{ ad: "O₂", birim: "%", d: 1 }, { ad: tr ? "Yanma ihtimali" : "Burning probability", birim: "0–1", d: 3 },
      { ad: tr ? "Alt sınır" : "Lower bound", birim: "0–1", d: 3 }, { ad: tr ? "Üst sınır" : "Upper bound", birim: "0–1", d: 3 }],
      satirlar: e.oksijen.map((x, i) => [x, e.ihtimal[i], e.alt ? e.alt[i] : null, e.ust ? e.ust[i] : null]) });
}

function haritaGorseli() {
  const s = S.sonuc;
  if (!s.harita) return Kabuk.gorselYaz(T("agac.harita"), `<div class="gorunum"><div class="bos">${esc(DIL === "tr" ? "Harita çizilemedi." : "Map unavailable.")}</div></div>`);
  const not = DIL === "tr"
    ? "Basınç, malzeme, akış ve diğer girdiler mevcut vakadan alınır. Haritada en kötü durum alınmaz; her yerçekimi kendi değeriyle hesaplanır. Bu yüzden Ay/Mars sütunu ana sonuçtan daha iyimser görünebilir."
    : "Pressure, material, flow and the other inputs come from the current case. The map is not bounded; each gravity is computed at its own value, so the Moon/Mars columns can look more optimistic than the headline result.";
  const h = s.harita, satir = [];
  h.g.forEach((g, i) => h.oksijen.forEach((o, j) => satir.push([g, o, h.ihtimal[i][j]])));
  Kabuk.gorselYaz(T("agac.harita"),
    `<div class="gorunum">` + haritaCiz(h, s.tahmin.girdi) + `<div class="grafik-not">${esc(not)}</div></div>`, "",
    { ad: "yanabilirlik_haritasi", sutunlar: [{ ad: "g", birim: "g₀", d: null }, { ad: "O₂", birim: "%", d: 1 },
      { ad: DIL === "tr" ? "Yanma ihtimali" : "Burning probability", birim: "0–1", d: 3 }], satirlar: satir });
}

function akisGorseli() {
  const s = S.sonuc;
  const not = DIL === "tr"
    ? "Bu eğri fizik motorundan gelir, risk modelinden değil. Yüksek akıştaki düşüş üfleyerek söndürmedir."
    : "This curve comes from the physics engine, not the risk model. The fall-off at high flow is blow-off extinction.";
  const a = s.akis_egrisi;
  Kabuk.gorselYaz(T("agac.akisEgrisi") + " — " + (s.tahmin.motor_turu || "?"),
    `<div class="gorunum">` + akisCiz(a, s.tahmin) + `<div class="grafik-not">${esc(not)}</div></div>`, "",
    a && a.akis ? { ad: "akis_egrisi", sutunlar: [{ ad: DIL === "tr" ? "Hava akışı" : "Air flow", birim: "cm/s", d: 2 },
      { ad: DIL === "tr" ? "Motor yanma ihtimali" : "Engine burning probability", birim: "0–1", d: 3 }],
      satirlar: a.akis.map((x, i) => [x, a.motor_yanma[i]]) } : null);
}

function deneyGorseli() {
  const s = S.sonuc, tum = s.yakin || [];
  const toplam = (s.tahmin.guven && s.tahmin.guven.yakin_deney) != null ? s.tahmin.guven.yakin_deney : tum.length;
  if (!tum.length) {
    return Kabuk.gorselYaz(T("agac.deneyler"),
      `<div class="gorunum"><div class="bos"><b>${esc(DIL === "tr" ? "Yakın gerçek deney yok" : "No nearby experiments")}</b>` +
      esc(DIL === "tr" ? "Sonuç tamamen modele dayanıyor." : "The result relies entirely on the model.") + `</div></div>`);
  }
  const bag = (x) => (/^https?:\/\//.test(x || "") ? `<a href="#" data-dis="${esc(x)}">${esc(DIL === "tr" ? "aç" : "open")} ↗</a>` : "");
  const satirlar = tum.map((d) => {
    const soluk = d.kaynak && d.kaynak.indexOf("Gemma") >= 0;
    const son = d.yanar === 1 ? `<span class="yandi">${esc(DIL === "tr" ? "yandı" : "burned")}</span>`
      : d.yanar === 0 ? `<span class="sondu">${esc(DIL === "tr" ? "söndü" : "extinguished")}</span>` : "–";
    return `<tr class="${soluk ? "soluk" : ""}"><td>${esc(d.kaynak)}</td><td title="${esc(d.aciklama || "")}">${esc(d.makale_id)}</td>` +
      `<td class="s">${esc(gMetni(d.g))}</td><td class="s">${esc(nf(d.oksijen, 1))}</td><td class="s">${esc(nf(d.basinc, 1))}</td>` +
      `<td class="s">${d.akis == null ? "–" : esc(nf(d.akis, 1))}</td><td>${esc(d.malzeme)}</td><td>${son}</td><td>${bag(d.link)}</td></tr>`;
  }).join("");
  const ic = `<div class="gorunum"><div class="gorunum-bas"><h3>${esc(T("agac.deneyler"))}</h3>` +
    `<span class="sonuk">${esc(DIL === "tr" ? "toplam" : "total")} ${esc(toplam)}</span></div>` +
    `<div class="tablo-kap" style="max-height:calc(100vh - 290px)"><table class="veri"><thead><tr>` +
    [DIL === "tr" ? "Kaynak" : "Source", DIL === "tr" ? "Deney" : "Experiment", "g", "O₂ %", "kPa",
     DIL === "tr" ? "akış" : "flow", DIL === "tr" ? "Malzeme" : "Material", DIL === "tr" ? "Sonuç" : "Result", ""]
      .map((h, i) => `<th class="${i >= 2 && i <= 5 ? "s" : ""}">${esc(h)}</th>`).join("") +
    `</tr></thead><tbody>${satirlar}</tbody></table></div>` +
    `<div class="grafik-not">${esc(DIL === "tr"
      ? "Soluk satırlar dil modeliyle makalelerden otomatik çıkarılmıştır; daha az güvenilirdir. Sıralama yakınlığa göredir."
      : "Faded rows were extracted automatically from papers by a language model and are less reliable. Ordering is by proximity.")}</div></div>`;
  const tr = DIL === "tr";
  Kabuk.gorselYaz(T("agac.deneyler"), ic.replace(`<div class="tablo-kap"`, deneyCiz(tum, s.tahmin.girdi) + `<div class="tablo-kap"`), "",
    { ad: "yakin_deneyler", sutunlar: [{ ad: tr ? "Kaynak" : "Source", birim: "", d: null }, { ad: tr ? "Deney" : "Experiment", birim: "", d: null },
      { ad: "g", birim: "g₀", d: null }, { ad: "O₂", birim: "%", d: 1 }, { ad: tr ? "Basınç" : "Pressure", birim: "kPa", d: 1 },
      { ad: tr ? "Akış" : "Flow", birim: "cm/s", d: 1 }, { ad: tr ? "Malzeme" : "Material", birim: "", d: null },
      { ad: tr ? "Sonuç" : "Result", birim: tr ? "1 = yandı, 0 = söndü" : "1 = burned, 0 = extinguished", d: 0 }, { ad: tr ? "Bağlantı" : "Link", birim: "", d: null }],
      satirlar: tum.map((d) => [d.kaynak, d.makale_id, d.g, d.oksijen, d.basinc, d.akis, d.malzeme, d.yanar, d.link || null]) });
}

/* ---------------------------------------------------------------- motor ayrıntıları (10. madde) */
async function motorGorseli() {
  const t = S.sonuc.tahmin, m = t.motor || {}, b = t.motor_belirsizlik || {};
  const satir = (ad, deger, alt) => `<div class="bilgi-satir"><span class="etiket-ad" style="min-width:190px">${esc(ad)}</span>` +
    `<span class="deger sayi">${deger}</span>${alt ? `<span class="sonuk" style="margin-left:auto">${esc(alt)}</span>` : ""}</div>`;
  // ± yalnız motorun kalibre olduğu yakıtta (kalibre edilmemiş yakıtta bootstrap bandı yanıltıcı: gösterilmez)
  const kalibre = t.motor_kaynagi === "damla" ? !!m.motor_kalibre : t.motor_kaynagi === "gaz" ? !m.kalibre_degil
    : !(t.kutuphane_eslesme && t.kutuphane_eslesme.motor_agirligi_sifir);
  const pm = (k, n, birim) => m[k] == null ? esc(T("genel.yok")) :
    esc(nf(m[k], n)) + (birim ? " " + esc(birim) : "") + (kalibre && b[k] != null ? ` <span class="sonuk">± ${esc(nf(b[k], n + 1))}</span>` : "");
  const evet = (x) => x == null ? "–" : x ? (DIL === "tr" ? "evet" : "yes") : (DIL === "tr" ? "hayır" : "no");
  const SONME = { kimyasal: ["kimyasal (Damköhler)", "chemical (Damköhler)"], isinim: ["ışınım", "radiative"], yok: ["sönmedi", "none"],
                  "üflenme": ["üflenme", "blow-off"], ufleme: ["üflenme", "blow-off"],
                  su_emme: ["su emme (damla suyu emip söner)", "water absorption (droplet absorbs water and extinguishes)"] };
  let ic = `<div class="gorunum"><div class="kutular k2">` +
    `<div class="kart"><h3>${esc(DIL === "tr" ? "Fizik motoru" : "Physics engine")}</h3>` +
      satir(DIL === "tr" ? "Motor" : "Engine", `<b>${esc(motorAdi(t))}</b>`, motorAucMetni(t)) +
      (m.benzer_malzeme ? satir(DIL === "tr" ? "Benzer malzeme" : "Surrogate", esc(m.benzer_malzeme)) : "") +
      satir(DIL === "tr" ? "Yanma ihtimali" : "Burn probability", m.yanma == null ? esc(T("genel.yok")) : "%" + esc(pct(m.yanma, 1)) + (kalibre && b.yanma != null ? ` <span class="sonuk">± ${esc(pct(b.yanma, 1))}</span>` : "")) +
      satir(DIL === "tr" ? "Sönme sınırı (motor)" : "Extinction limit (engine)", m.min_oksijen == null ? esc(T("genel.yok")) : "%" + pm("min_oksijen", 2, "O₂")) +
      satir(DIL === "tr" ? "Alev sıcaklığı" : "Flame temperature", pm("sicaklik", 0, "K"),
            m.sicaklik_adyabatik != null ? (DIL === "tr" ? "adyabatik " : "adiabatic ") + nf(m.sicaklik_adyabatik, 0) + " K" : "") +
      satir(DIL === "tr" ? "Motorun kullandığı akış" : "Flow used", t.motor_akis == null ? "–" : esc(nf(t.motor_akis, 1)) + " cm/s") +
      (m.yayilma_hizi != null ? satir(DIL === "tr" ? "Alev yayılma hızı" : "Flame spread rate", pm("yayilma_hizi", 2, "mm/s")) : "") +
      (b.yontem && kalibre ? `<div class="grafik-not">${esc((DIL === "tr" ? "Belirsizlik: " : "Uncertainty: ") + b.yontem)}</div>` : "") +
      (b.yontem && !kalibre ? `<div class="grafik-not">${esc(DIL === "tr" ? "Yakıt motorda kalibre değil: ± belirsizlik gösterilmiyor (kalibre yakıtlardan türetilmiş bant bu yakıtı temsil etmez)." : "Fuel not calibrated in the engine: ± not shown (the band from calibrated fuels does not represent this fuel).")}</div>` : "") +
      (t.motor_kaynagi ? "" : `<div class="uyari-satir"><span>${esc(t.gas_engine_kullanilmadi ? (DIL === "tr" ? "Debi bilinmiyor; gaz motoru kullanılmadı (numune tipi seçilirse çalışır)." : "Flow rate unknown; gas engine not used (runs if a sample type is chosen).")
        : t.kutuphane_eslesme && !t.kutuphane_eslesme.motor_benzeri ? (DIL === "tr" ? "Motor yok, model bu malzemeyi tanımıyor: yalnız risk modeli." : "No engine and the model does not know this material: risk model only.") : (DIL === "tr" ? "Motor bu koşulu bilmiyor." : "The engine does not cover this condition."))}</span></div>`) +
    `</div>`;
  if (t.motor_kaynagi === "damla") {
    ic += `<div class="kart"><h3>${esc(DIL === "tr" ? "Damla motoru" : "Droplet engine")}</h3>` +
      satir(DIL === "tr" ? "Yanma hızı sabiti K" : "Burning rate constant K", pm("yanma_hizi_K", 3, "mm²/s")) +
      satir(DIL === "tr" ? "Sönme çapı" : "Extinction diameter", pm("sonme_capi", 3, "mm")) +
      satir(DIL === "tr" ? "Sönme türü" : "Extinction type", esc(SONME[m.sonme_turu] ? mlzDil(SONME[m.sonme_turu]) : (m.sonme_turu || "–"))) +
      satir(DIL === "tr" ? "Soğuk alev" : "Cool flame", esc(evet(m.soguk_alev)) + (m.soguk_alev_suresi_s != null ? " · " + esc(nf(m.soguk_alev_suresi_s, 2)) + " s" : "")) +
      satir(DIL === "tr" ? "Yakıt motorda kalibre" : "Fuel calibrated", esc(evet(m.motor_kalibre))) +
      (m.tasinim_dogrulanmadi ? `<div class="uyari-satir"><span>${esc(DIL === "tr" ? "Zorlanmış akış taşınım düzeltmesi doğrulanmadı (FLEX'te akış yoktu)." : "Forced-flow convection correction not validated (FLEX had no flow).")}</span></div>` : "") +
      (m.kismi_g_dogrulanmadi ? `<div class="uyari-satir"><span>${esc(DIL === "tr" ? "Kısmi g davranışı doğrulanmadı." : "Partial-g behaviour not validated.")}</span></div>` : "") +
      (m.isinim_temsili ? `<div class="grafik-not">${esc(m.isinim_temsili)}</div>` : "") +
    `</div>`;
  } else if (t.motor_kaynagi === "gaz") {
    ic += `<div class="kart"><h3>${esc(DIL === "tr" ? "Gaz motoru" : "Gas engine")}</h3>` +
      (m.kalibre_degil ? `<div class="uyari-satir"><span>${esc(DIL === "tr" ? "Bu geometri kalibre değil (etiketli PSI verisi yok): motor ağırlığı 0." : "This geometry is not calibrated (no labelled PSI data): engine weight 0.")}</span></div>` : "") +
      satir(DIL === "tr" ? "Geometri" : "Geometry", esc({ kure: DIL === "tr" ? "küre" : "sphere", duz: DIL === "tr" ? "düz brülör" : "flat burner", jet: "jet" }[m.geometri] || m.geometri || "–")) +
      satir(DIL === "tr" ? "Alev boyu" : "Flame length", pm("alev_boyu", 1, "mm")) +
      satir(DIL === "tr" ? "Alev yarıçapı" : "Flame radius", pm("alev_yaricapi", 1, "mm")) +
      satir(DIL === "tr" ? "Sönme türü" : "Extinction type", esc(SONME[m.sonme_turu] ? mlzDil(SONME[m.sonme_turu]) : (m.sonme_turu || "–"))) +
      satir(DIL === "tr" ? "Işınım oranı" : "Radiant fraction", pm("isinim_orani", 3)) +
      satir(DIL === "tr" ? "Debi" : "Mass flow", pm("debi_mg_s", 3, "mg/s")) +
      (m.kopma != null ? satir(DIL === "tr" ? "Alev kopması" : "Lift-off", esc(evet(m.kopma))) : "") +
    `</div>`;
  }
  ic += ofmYanYana(t);       // hızlı motor ↔ OpenFOAM motoru ↔ deney (js/ofm.js)
  // kütüphaneden yanıcılık bilgisi
  if (MLZ === null) { try { MLZ = await API.malzemeKutuphanesi(); } catch (e) { MLZ = { malzemeler: [] }; } }
  const id = (t.kutuphane_eslesme && t.kutuphane_eslesme.id) || (t.girdi && t.girdi.malzeme);
  const k = (MLZ.malzemeler || []).find((x) => x.id === id);
  const o = (k && k.ozellikler) || {};
  const kel = (a, n, birim, c) => o[a] && o[a].deger != null
    ? `<tr><td>${esc(n)}</td><td class="s">${esc(nf(o[a].deger, 1))} ${esc(birim)}${c ? ` <span class="sonuk">(${esc(nf(o[a].deger - 273.15, 0))} °C)</span>` : ""}</td><td class="sonuk" style="font-size:11px">${esc(String(o[a].kaynak || "").replace(/^chemicals [^,]*, /, "chemicals · "))}</td></tr>` : "";
  const kut = k ? kel("LFL", DIL === "tr" ? "Alt yanma sınırı (LFL)" : "LFL", "% hacim") + kel("UFL", DIL === "tr" ? "Üst yanma sınırı (UFL)" : "UFL", "% hacim") +
    kel("parlama_noktasi_K", DIL === "tr" ? "Parlama noktası" : "Flash point", "K", true) +
    kel("kendiliginden_tutusma_K", DIL === "tr" ? "Kendiliğinden tutuşma" : "Autoignition", "K", true) +
    kel("LOI", "LOI", "%") : "";
  ic += `<div class="kart"><h3>${esc(DIL === "tr" ? "Yanıcılık (malzeme kütüphanesi)" : "Flammability (material library)")}</h3>` +
    (kut ? `<div class="tablo-kap" style="border:0"><table class="veri"><tbody>${kut}</tbody></table></div>`
         : `<div class="sonuk">${esc(k ? (DIL === "tr" ? "Kütüphanede bu malzeme için yanıcılık verisi yok." : "No flammability data in the library for this material.")
                                         : (DIL === "tr" ? "Malzeme kütüphanede yok." : "Material not in the library."))}</div>`) +
    `<div class="grafik-not">${esc(DIL === "tr" ? "Bilgi amaçlı; hesaba girmez." : "For information; not used in the calculation.")}</div></div>`;
  ic += `</div></div>`;
  Kabuk.gorselYaz(DIL === "tr" ? "Motor Ayrıntıları" : "Engine Details", ic);
}

function guvenGorseli() {
  const t = S.sonuc.tahmin, g = t.guven || {}, w = g.agirliklar || {};
  const satir = (ad, deger, alt) =>
    `<div class="bilgi-satir"><span class="etiket-ad" style="min-width:150px">${esc(ad)}</span>` +
    `<span class="deger sayi">${deger}</span>${alt ? `<span class="sonuk" style="margin-left:auto">${esc(alt)}</span>` : ""}</div>`;
  const v = guvenV2(t);
  const BIL = { veri: ["Veri", "Data"], uyum: ["Uyum", "Agreement"], motor: ["Motor", "Engine"], kesinlik: ["Kesinlik", "Certainty"] };
  const bilesenCubugu = (k) => {
    const x = v.bilesenler[k], a = (v.agirliklar || {})[k];
    return `<div class="cubuk-bas" style="margin-top:9px"><span>${esc(mlzDil(BIL[k]))} <span style="color:var(--cok-sonuk)">· ${esc(DIL === "tr" ? "ağırlık" : "weight")} ${esc(nf(a, 2))}</span></span>` +
      `<span>${x == null ? esc(DIL === "tr" ? "hesaplanmadı" : "not computed") : esc(nf(x, 2))}</span></div>` +
      `<div class="cubuk"${x == null ? ' style="opacity:.4"' : ""}>${x == null ? "" : `<i style="width:${Math.max(0, Math.min(1, x)) * 100}%;background:var(--vurgu)"></i>`}</div>`;
  };
  const v2kart = !v ? "" :
    `<div class="kart"><h3>${esc(DIL === "tr" ? "Güven skoru (v2)" : "Confidence score (v2)")}</h3>` +
      `<div style="display:flex;align-items:baseline;gap:12px"><b style="font-size:30px;color:${BANT_RENK[v.bant]}">${esc(nf(v.skor, 0))}</b>` +
        `<span class="etiket" style="color:${BANT_RENK[v.bant]};border-color:${BANT_RENK[v.bant]}">${esc(bantMetni(v.bant))}</span>` +
        `<span class="sonuk" style="margin-left:auto">${esc(DIL === "tr" ? "ham skor" : "raw score")} ${esc(nf(v.ham_skor, 1))}</span></div>` +
      `<div class="sonuk" style="margin-top:4px">${esc(guvenSebebi(t))}</div>` +
      ["veri", "uyum", "motor", "kesinlik"].map(bilesenCubugu).join("") +
      `<h3 style="margin-top:16px">${esc(DIL === "tr" ? "Cezalar" : "Penalties")}</h3>` +
      ((v.cezalar || []).length
        ? v.cezalar.map((c) => `<div class="uyari-satir"><span><b>× ${esc(nf(c.carpan, 2))}</b> ${esc(c.ad)}` +
            (c.ayrinti || c.esik ? `<br><span class="sonuk" style="font-size:11px">${esc(c.ayrinti || c.esik)}</span>` : "") + `</span></div>`).join("")
        : `<div class="sonuk">${esc(DIL === "tr" ? "Ceza yok." : "No penalty.")}</div>`) +
      `<h3 style="margin-top:16px">${esc(DIL === "tr" ? "Yakın deney kaynakları" : "Nearby experiment sources")}</h3>` +
      `<div class="tablo-kap" style="border:0"><table class="veri"><tbody>` +
        Object.entries(v.yakin_deney_kaynaklari || {}).map(([k, n]) => `<tr><td>${esc(k)}</td><td class="s">${esc(n)}</td></tr>`).join("") +
        `<tr><td>${esc(DIL === "tr" ? "ağırlıklı toplam" : "weighted total")}</td><td class="s">${esc(nf(v.agirlikli_yakin_deney, 1))}</td></tr>` +
      `</tbody></table></div>` +
      (v.kalibrasyon_mesafesi != null ? `<div class="grafik-not">${esc(DIL === "tr" ? "Kalibrasyon noktasına mesafe: " : "Distance to calibration point: ")}${esc(nf(v.kalibrasyon_mesafesi, 2))} ${esc(DIL === "tr" ? "(1'in üstü kapsam dışı)" : "(above 1 = out of range)")}</div>` : "") +
      `<div class="grafik-not">${esc("skor = 100 × (0,35 veri + 0,25 uyum + 0,25 motor + 0,15 kesinlik) × cezalar")}</div>` +
    `</div>`;
  const ic = `<div class="gorunum"><div class="kutular k2">` + v2kart +
    `<div class="kart"><h3>${esc(v ? (DIL === "tr" ? "Eski güven skoru (v1)" : "Old confidence score (v1)") : T("sonuc.guvenSkoru"))}</h3>` +
      satir(DIL === "tr" ? "Skor (0–100)" : "Score (0–100)", `<b style="font-size:17px">${esc(nf(g.skor, 0))}</b>`) +
      satir(DIL === "tr" ? "Veri bileşeni" : "Data component", esc(nf(g.veri_bileseni, 2)),
            (DIL === "tr" ? "yakın deney: " : "nearby: ") + (g.yakin_deney == null ? "–" : g.yakin_deney)) +
      satir(DIL === "tr" ? "Uyum bileşeni" : "Agreement component",
            g.uyum_bileseni == null ? `<i class="sonuk">${esc(DIL === "tr" ? "hesaplanmadı" : "not computed")}</i>` : esc(nf(g.uyum_bileseni, 2)),
            g.yakin_deney_yanma_orani == null ? "" : (DIL === "tr" ? "yanma oranı " : "burn ratio ") + nf(g.yakin_deney_yanma_orani, 2)) +
      satir(DIL === "tr" ? "Motor bileşeni" : "Engine component", esc(nf(g.motor_bileseni, 2)),
            (DIL === "tr" ? "yanan " : "burned ") + (g.yanan == null ? "–" : g.yanan) + " / " + (DIL === "tr" ? "sönen " : "ext. ") + (g.sonen == null ? "–" : g.sonen)) +
      satir(DIL === "tr" ? "Ağırlıklar" : "Weights",
            `${esc(nf(w.veri, 2))} · ${esc(nf(w.uyum, 2))} · ${esc(nf(w.motor, 2))}`,
            DIL === "tr" ? "veri · uyum · motor" : "data · agreement · engine") +
      `<div class="grafik-not">${esc(DIL === "tr"
        ? "skor = 100 × (veri·ağırlık + uyum·ağırlık + motor·ağırlık)"
        : "score = 100 × (data·w + agreement·w + engine·w)")}</div>` +
      (g.motor_yontemi ? `<div class="grafik-not">${esc(DIL === "tr" ? "Motor yöntemi: " : "Engine method: ")}${esc(g.motor_yontemi)}</div>` : "") +
    `</div>` +
    `<div class="kart"><h3>${esc(DIL === "tr" ? "Ham model çıktısı" : "Raw model output")}</h3>` +
      satir(T("sonuc.yanmaIhtimali"), `%${esc(pct(t.yanma_ihtimali, 1))} ± ${esc(pct(t.belirsizlik, 1))}`) +
      satir(T("sonuc.sonmeSiniri"), t.sonme_siniri == null ? esc(T("genel.bulunamadi")) : `%${esc(nf(t.sonme_siniri, 2))}`) +
      satir(T("sonuc.guvenlikKatsayisi"), t.guvenlik_katsayisi == null ? esc(T("genel.hesaplanamadi")) : esc(nf(t.guvenlik_katsayisi, 2))) +
      satir(DIL === "tr" ? "Fizik motoru" : "Physics engine", esc(motorAdi(t)), motorAucMetni(t)) +
      satir(DIL === "tr" ? "Motorun kullandığı akış" : "Flow used by engine", esc(nf(t.motor_akis, 1)) + " cm/s") +
      (t.motor ? satir(DIL === "tr" ? "Yayılma hızı" : "Spread rate", t.motor.yayilma_hizi == null ? esc(T("genel.yok")) : esc(nf(t.motor.yayilma_hizi, 2)) + " mm/s") : "") +
      (t.motor ? satir(DIL === "tr" ? "Alev sıcaklığı" : "Flame temperature", t.motor.sicaklik == null ? esc(T("genel.yok")) : esc(nf(t.motor.sicaklik, 0)) + " K") : "") +
      satir(DIL === "tr" ? "Çözüm süresi" : "Solve time", esc(nf(t.sure_sn, 2)) + " s") +
    `</div></div></div>`;
  Kabuk.gorselYaz(T("agac.guven"), ic,
    `<button class="dugme kucuk" data-komut="json">JSON</button>`);
}

function sinirlamaGorseli() {
  const sn = S.sonuc.tahmin.sinirlama;
  if (!sn) return Kabuk.gorselYaz(T("agac.sinirlama"), `<div class="gorunum"><div class="bos">${esc(DIL === "tr" ? "Bu yerçekiminde sınırlama yapılmadı." : "No bounding applied at this gravity.")}</div></div>`);
  const adlar = { uzay: DIL === "tr" ? "Uzay" : "Space", gercek_g: DIL === "tr" ? "Gerçek g" : "Actual g", dunya: DIL === "tr" ? "Dünya" : "Earth" };
  const satirlar = ["uzay", "gercek_g", "dunya"].map((k) => {
    const x = sn[k] || {};
    return `<tr><td>${esc(adlar[k])}</td><td class="s">${esc(gMetni(x.g))}</td><td class="s">%${esc(pct(x.yanma_ihtimali, 1))}</td>` +
      `<td class="s">${esc(pct(x.belirsizlik, 1))}</td><td class="s">${x.sonme_siniri == null ? "–" : "%" + esc(nf(x.sonme_siniri, 2))}</td>` +
      `<td class="s">${x.guvenlik_katsayisi == null ? "–" : esc(nf(x.guvenlik_katsayisi, 2))}</td>` +
      `<td><span class="rozet ${ROZET_SINIF(x.risk_seviyesi)}">${esc(x.risk_seviyesi)}</span></td></tr>`;
  }).join("");
  const ic = `<div class="gorunum">` + gBandi() +
    `<div class="tablo-kap"><table class="veri"><thead><tr>` +
    [DIL === "tr" ? "Satır" : "Row", "g", DIL === "tr" ? "Yanma" : "Burn", DIL === "tr" ? "Belirsizlik" : "Uncertainty",
     DIL === "tr" ? "Sönme sınırı" : "Ext. limit", DIL === "tr" ? "Güv. kats." : "Safety f.", "Risk"]
      .map((h, i) => `<th class="${i >= 1 && i <= 5 ? "s" : ""}">${esc(h)}</th>`).join("") +
    `</tr></thead><tbody>${satirlar}</tbody></table></div>` +
    `<div class="grafik-not">${esc(DIL === "tr"
      ? "Ana sonuç en kötü satırdır: en yüksek yanma ihtimali ve en düşük sönme sınırı."
      : "The headline result is the worst row: highest burning probability and lowest extinction limit.")}</div></div>`;
  Kabuk.gorselYaz(T("agac.sinirlama"), ic);
}

function llmGorseli() {
  const l = S.llm;
  const alt = "";
  let ic;
  const degisti = !!l.kosul && JSON.stringify(kosul()) !== l.kosul;     // ekrandaki girdiler yorumun girdilerinden farklı
  if (l.durum === "eski" || (l.durum === "geldi" && degisti)) {
    ic = `<div class="bos"><b>${esc(DIL === "tr" ? "Girdiler değişti" : "Inputs changed")}</b>` +
      esc(DIL === "tr" ? "Eldeki yorum önceki girdiler içindi ve gösterilmiyor. Yeni girdiler için yeniden isteyin."
                       : "The available commentary was for previous inputs and is hidden. Request it again for the new inputs.") +
      `<button class="dugme" data-komut="llm" style="margin-top:10px">${esc(T("komut.llm"))}</button></div>`;
  } else if (l.durum === "yok") {
    const sonucYok = "";
    ic = `<div class="bos"><b>${esc(DIL === "tr" ? "Henüz istenmedi" : "Not requested yet")}</b>${esc(sonucYok)}` +
      `<button class="dugme" data-komut="llm" style="margin-top:10px">${esc(T("komut.llm"))}</button></div>`;
  } else if (l.durum === "bekle") {
    ic = `<div class="llm donen">${esc(DIL === "tr" ? "Yapay zeka yorumu hazırlanıyor…" : "Preparing AI commentary…")}</div>`;
  } else if (l.durum === "hata") {
    ic = `<div class="llm sonuk">${esc(l.metin)}</div><div style="margin-top:10px"><button class="dugme" data-komut="llm">${esc(DIL === "tr" ? "Tekrar dene" : "Try again")}</button></div>`;
  } else {
    const satir = String(l.metin).split("\n");
    const sariSatir = satir.filter((x) => x.indexOf("Doğrulanamayan sayılar") >= 0);
    const govde = satir.filter((x) => x.indexOf("Doğrulanamayan sayılar") < 0).map((x, i) => {
      const h = esc(x);
      return (i === 0 || x.indexOf("KARAR:") === 0) ? `<b style="font-size:14px">${h}</b>` : h;
    }).join("\n");
    ic = (sariSatir.length
      ? `<div class="llm sari" style="margin-bottom:10px"><span class="dogrulanmayan">${esc(sariSatir.join(" "))}</span>` +
        `<div class="sonuk" style="font-size:11.5px;margin-top:6px">${esc(DIL === "tr" ? "Dil modeli giriş verisinde olmayan sayı yazdı; bu sayılara güvenmeyin." : "The language model wrote numbers that are not in the input data; do not rely on them.")}</div></div>`
      : "") + `<div class="llm">${govde}</div>`;
  }
  Kabuk.gorselYaz(T("agac.llm"), `<div class="gorunum">${ic}${alt}${sohbetHtml()}</div>`);
  // Erişim yoklaması açılışta yapılmaz (sayfa doğrudan açılsın); bağlantı yoksa ilk soruda ya da "Yeniden dene" ile anlaşılır.
}

/* ---------------------------------------------------- SOHBET (yorumun altında)
   Sayıları kod üretir: "ne olur eğer" sorusunda dil modeli yalnız bir hesap isteği döndürür, köprü tahmin()'i
   çalıştırır (en fazla 3), sonuç tabloda gösterilir. Girdiler değişince eski mesajlar "eski vaka" olur ve
   dil modeline gönderilmez. */
const SOHBET_ALAN = () => ({ oksijen: ["O₂", "%"], basinc: ["p", "kPa"], g: ["g", ""], akis: [DIL === "tr" ? "akış" : "flow", "cm/s"],
  kalinlik: [DIL === "tr" ? "kalınlık" : "thickness", "mm"], seyreltici: [DIL === "tr" ? "seyreltici" : "diluent", ""],
  malzeme: [DIL === "tr" ? "malzeme" : "material", ""] });
function sohbetIstekMetni(i) {
  if (!i || typeof i !== "object") return String(i);
  return Object.keys(i).map((k) => {
    const a = SOHBET_ALAN()[k] || [k, ""];
    const v = typeof i[k] === "number" ? (k === "g" ? gMetni(i[k]) : nf(i[k], 2).replace(/([.,]\d*?)0+$/, "$1").replace(/[.,]$/, "")) : i[k];
    return a[0] + " = " + v + (a[1] ? " " + a[1] : "");
  }).join(", ");
}
function sohbetEskiIsaretle() {            // yeni çözüm / yeni vaka: eldeki mesajlar artık eski vakaya ait
  S.sohbet.mesajlar.forEach((m) => (m.eski = true));
  S.sohbet.kosul = null;
}
function sohbetTablo(m) {
  const tr = DIL === "tr";
  const hucre = (o) => `<td class="s">%${pct(o.yanma_birlesik, 1)}</td><td>${esc(o.risk_seviyesi || "–")}</td>` +
    `<td class="s">${o.sonme_siniri == null ? "–" : "%" + nf(o.sonme_siniri, 2)}</td><td class="s">${nf(o.guvenlik_katsayisi, 3)}</td>` +
    `<td class="s">${o.guven == null ? "–" : nf(o.guven, 0) + "/100"}</td>`;
  const satirlar = (m.mevcut ? `<tr class="soluk"><td>${esc(tr ? "mevcut vaka" : "current case")}</td>${hucre(m.mevcut)}</tr>` : "") +
    m.hesaplar.map((h) => h.durum === "tamam"
      ? `<tr><td>${esc(sohbetIstekMetni(h.istek))}</td>${hucre(h.ozet)}</tr>`
      : `<tr><td>${esc(sohbetIstekMetni(h.istek))}</td><td colspan="5" class="sohbet-red">${esc((h.durum === "reddedildi" ? (tr ? "istek reddedildi: " : "request rejected: ") : (tr ? "hesaplanamadı: " : "failed: ")) + (h.sebep || ""))}</td></tr>`).join("");
  return `<div class="sohbet-hesap"><div class="sohbet-hesap-bas">${esc(tr ? "Ek hesaplar (kod çalıştırdı, tahmin())" : "Extra runs (computed by code, tahmin())")}</div>` +
    `<table class="veri"><thead><tr><th>${esc(tr ? "Değişen girdi" : "Changed input")}</th><th class="s">${esc(tr ? "Birleşik ihtimal" : "Combined prob.")}</th>` +
    `<th>${esc(tr ? "Risk" : "Risk")}</th><th class="s">${esc(tr ? "Sönme sınırı (O₂)" : "Extinction limit (O₂)")}</th>` +
    `<th class="s">${esc(tr ? "Güvenlik kats." : "Safety factor")}</th><th class="s">${esc(tr ? "Güven" : "Confidence")}</th></tr></thead><tbody>${satirlar}</tbody></table></div>`;
}
function sohbetHtml() {
  const t = S.sonuc && S.sonuc.tahmin, tr = DIL === "tr", so = S.sohbet;
  // Çözüm GEREKMEZ: çözüm yoksa ya da girdiler değiştiyse sohbet "genel" kipte, uygulama hakkında konuşur
  const sonucVar = !!(t && t.yanma_ihtimali != null);
  const genel = !sonucVar || JSON.stringify(kosul()) !== JSON.stringify(S.sonuc.kosul);
  const eskiVar = so.mesajlar.some((m) => m.eski);
  const satirlar = so.mesajlar.map((m) => {
    const eski = m.eski;
    const etiket = m.rol === "kullanici" ? (tr ? "Siz" : "You") : (tr ? "Asistan" : "Assistant");
    let govde = `<div class="sohbet-metin">${esc(String(m.metin).replace(/\*\*/g, ""))}</div>`;
    if (m.rol === "asistan") {
      if (m.dogrulanamayan && m.dogrulanamayan.length)
        govde += `<div class="sohbet-sari"><span class="dogrulanmayan">${esc("⚠️ " + (tr ? "Doğrulanamayan sayılar: " : "Unverifiable numbers: ") + m.dogrulanamayan.join(", "))}</span> ` +
          `<span class="sonuk">${esc(tr ? "Dil modeli veride olmayan sayı yazdı; bu sayılara güvenmeyin." : "The language model wrote numbers that are not in the data; do not rely on them.")}</span></div>`;
      if (m.hesaplar && m.hesaplar.length) govde += sohbetTablo(m);
    }
    return `<div class="sohbet-satir ${m.rol}${eski ? " eski" : ""}${m.hata ? " hata" : ""}"><div class="sohbet-kim">${esc(etiket)}` +
      (eski ? `<span class="etiket">${esc(tr ? "eski vaka" : "previous case")}</span>` : "") + `</div><div class="sohbet-govde">${govde}</div></div>`;
  }).join("");
  const bekle = so.bekle ? `<div class="sohbet-satir asistan"><div class="sohbet-kim">${esc(tr ? "Asistan" : "Assistant")}</div>` +
    `<div class="sohbet-govde"><span class="sohbet-bekle"><i></i><i></i><i></i></span> <span class="sonuk">${esc(tr ? "yanıt bekleniyor…" : "waiting for the answer… (5–25 s; one request at a time)")}</span></div></div>` : "";
  const kapali = so.erisim === false;
  const yorumBekliyor = S.llm.durum === "bekle";
  const pasif = kapali || so.bekle || yorumBekliyor;
  const ipucu = kapali ? (tr ? "LLM'e ulaşılamıyor" : "LLM unreachable")
    : genel ? (tr ? "Sorunuzu yazın" : "Type your question")
    : yorumBekliyor ? (tr ? "Yorum hazırlanıyor…" : "Preparing commentary…")
    : (tr ? "Sorunuzu yazın" : "Type your question");
  const uyari = kapali
    ? `<div class="uyari-satir"><span>${esc((tr ? "LLM'e ulaşılamıyor" : "The LLM cannot be reached") + (so.erisimSebep ? " (" + so.erisimSebep + ")" : "") + (tr ? ". Sohbet kapalı; hesaplar ve diğer sonuçlar çevrimdışı çalışır." : ". Chat is closed; calculations and other results work offline."))} ` +
      `<a href="#" data-komut="sohbet-sina">${esc(tr ? "Yeniden dene" : "Retry")}</a></span></div>`
    : eskiVar ? `<div class="uyari-satir bilgi"><span>${esc(tr ? "Girdiler değişti: “eski vaka” işaretli mesajlar önceki girdilere aittir ve dil modeline gönderilmez." : "Inputs changed: messages marked “previous case” belong to earlier inputs and are not sent to the language model.")} ` +
      `<a href="#" data-komut="sohbet-temizle">${esc(tr ? "Temizle" : "Clear")}</a></span></div>` : "";
  return `<div class="sohbet"><div class="sohbet-bas"><b>${esc(tr ? "Sohbet" : "Chat")}</b>` +
    (so.mesajlar.length && !so.bekle ? `<a href="#" class="sag" data-komut="sohbet-temizle">${esc(tr ? "Temizle" : "Clear")}</a>` : "") + `</div>` +
    uyari + (satirlar || bekle ? `<div class="sohbet-liste">${satirlar}${bekle}</div>` : "") +
    `<div class="sohbet-giris"><input class="giris" id="sohbetGiris" maxlength="400" autocomplete="off" placeholder="${esc(ipucu)}" value="${esc(so.taslak || "")}"${pasif ? " disabled" : ""}>` +
    `<button class="dugme birincil" data-komut="sohbet-gonder"${pasif ? " disabled" : ""}>${esc(tr ? "Gönder" : "Send")}</button></div></div>`;
}
function sohbetYenile(odak) {
  if ((Kabuk.agacSecili() || "") !== "r-llm" || Kabuk.aktif() !== "calisma") return;
  llmGorseli();
  const g = $("#sohbetGiris");
  if (!g) return;
  g.scrollIntoView({ block: "end" });
  if (odak && !g.disabled) { g.focus(); g.setSelectionRange(g.value.length, g.value.length); }
}
async function sohbetErisimSina(zorla) {
  const so = S.sohbet;
  if (so.sinaniyor || (!zorla && so.erisim !== null && Date.now() - (so.erisimZaman || 0) < 60000)) return;
  if (!S.sonuc || !S.sonuc.tahmin || S.sonuc.tahmin.yanma_ihtimali == null) return;
  so.sinaniyor = true;
  let r;
  try { r = await API.llmDurumu(); } catch (e) { r = { ulasilabilir: false, sebep: e.message }; }
  so.sinaniyor = false;
  const once = so.erisim;
  so.erisim = !!r.ulasilabilir; so.erisimSebep = r.sebep || ""; so.erisimZaman = Date.now();
  if (once !== so.erisim) sohbetYenile(false);
}
async function sohbetGenelGonder(soru) {
  const so = S.sohbet, tr = DIL === "tr";
  const gecmis = so.mesajlar.filter((m) => !m.eski && !m.hata).map((m) => ({ rol: m.rol, metin: m.metin }));
  so.mesajlar.push({ rol: "kullanici", metin: soru });
  so.taslak = ""; so.bekle = true;
  sohbetYenile(false); dogrula();
  const bas = performance.now();
  let r;
  try { r = await API.sohbetGenel(gecmis, soru, kosul()); } catch (e) { r = { durum: "hata", sebep: e.message }; }
  const sure = (performance.now() - bas) / 1000;
  so.bekle = false;
  if (r.durum === "tamam") {
    so.mesajlar.push({ rol: "asistan", metin: r.cevap, hesaplar: [], dogrulanamayan: r.dogrulanamayan || [] });
    so.erisim = true; so.erisimZaman = Date.now();
  } else {
    if (r.durum === "baglanti_yok") { so.erisim = false; so.erisimSebep = r.sebep || ""; so.erisimZaman = Date.now(); }
    const m = r.durum === "baglanti_yok" ? (tr ? "LLM'e ulaşılamıyor" : "The LLM cannot be reached") + (r.sebep ? " (" + r.sebep + ")" : "")
      : r.durum === "mesgul" ? (tr ? "Başka bir yapay zeka isteği sürüyor; bitince yeniden sorun." : "Another AI request is running; ask again when it finishes.")
      : (tr ? "Cevap alınamadı (" : "No answer (") + (r.sebep || "?") + ")";
    so.mesajlar.push({ rol: "asistan", metin: m, hata: true, hesaplar: [] });
    mesaj(r.durum === "mesgul" ? "uyari" : "hata", m);
  }
  gunluk({ tur: tr ? "Sohbet (genel)" : "Chat (general)", sure, girdi: soru.slice(0, 60), hata: r.durum === "tamam" ? "" : (r.sebep || r.durum), sonuc: r.durum === "tamam" ? (tr ? "cevap geldi" : "answered") : "" });
  dogrula();
  if ((Kabuk.agacSecili() || "") === "r-llm" && Kabuk.aktif() === "calisma") sohbetYenile(true);
}
async function sohbetGonder() {
  const so = S.sohbet, tr = DIL === "tr";
  const g = $("#sohbetGiris");
  const soru = ((g && g.value) || so.taslak || "").trim();
  if (!soru || so.bekle || so.erisim === false || S.llm.durum === "bekle") return;
  const sonucVar = !!(S.sonuc && S.sonuc.tahmin && S.sonuc.tahmin.yanma_ihtimali != null);
  if (!sonucVar || JSON.stringify(kosul()) !== JSON.stringify(S.sonuc.kosul)) return sohbetGenelGonder(soru, g);   // çözümsüz genel sohbet
  const istenen = JSON.stringify(S.sonuc.kosul);
  if (so.kosul !== istenen) { so.mesajlar.forEach((m) => (m.eski = true)); so.kosul = istenen; }
  const gecmis = so.mesajlar.filter((m) => !m.eski && !m.hata)
    .map((m) => ({ rol: m.rol, metin: m.metin, hesaplar: (m.hesaplar || []).filter((h) => h.durum === "tamam").map((h) => ({ istek: h.istek, ozet: h.ozet })) }));
  so.mesajlar.push({ rol: "kullanici", metin: soru });
  so.taslak = ""; so.bekle = true;
  sohbetYenile(false); dogrula();
  const bas = performance.now();
  let r;
  try { r = await API.sohbet(S.sonuc.kosul, gecmis, soru); } catch (e) { r = { durum: "hata", sebep: e.message, hesaplar: [] }; }
  const sure = (performance.now() - bas) / 1000;
  so.bekle = false;
  const eski = !S.sonuc || JSON.stringify(S.sonuc.kosul) !== istenen;      // bu sırada yeniden çözüldü
  if (r.durum === "tamam") {
    so.mesajlar.push({ rol: "asistan", metin: r.cevap, hesaplar: r.hesaplar || [], mevcut: r.mevcut, dogrulanamayan: r.dogrulanamayan || [], eski });
    so.erisim = true; so.erisimZaman = Date.now();
  } else {
    if (r.durum === "baglanti_yok") { so.erisim = false; so.erisimSebep = r.sebep || ""; so.erisimZaman = Date.now(); }
    const m = r.durum === "baglanti_yok" ? (tr ? "LLM'e ulaşılamıyor" : "The LLM cannot be reached") + (r.sebep ? " (" + r.sebep + ")" : "")
      : r.durum === "mesgul" ? (tr ? "Başka bir yapay zeka isteği sürüyor; bitince yeniden sorun." : "Another AI request is running; ask again when it finishes.")
      : (tr ? "Cevap alınamadı (" : "No answer (") + (r.sebep || "?") + ")";
    so.mesajlar.push({ rol: "asistan", metin: m, hata: true, hesaplar: r.hesaplar || [], mevcut: r.mevcut, eski });
    mesaj(r.durum === "mesgul" ? "uyari" : "hata", m);
  }
  gunluk({ tur: tr ? "Sohbet" : "Chat", sure, girdi: soru.slice(0, 60), hata: r.durum === "tamam" ? "" : (r.sebep || r.durum),
           sonuc: r.durum === "tamam" ? ((r.hesaplar || []).length ? (r.hesaplar.length + (tr ? " ek hesap" : " extra runs")) : (tr ? "cevap geldi" : "answered")) : "" });
  dogrula();
  if ((Kabuk.agacSecili() || "") === "r-llm" && Kabuk.aktif() === "calisma") sohbetYenile(true);
  else Kabuk.bildir(tr ? "Sohbet cevabı hazır." : "Chat answer ready.", "basari");
}

function renderGorseli() {
  const liste = S.render;
  if (!liste.length) {
    return Kabuk.gorselYaz(T("agac.render"),
      `<div class="gorunum"><div class="bos"><b>${esc(DIL === "tr" ? "Render klasörü boş" : "Render folder is empty")}</b>` +
      esc(DIL === "tr"
        ? "OpenFOAM çıktıları (mp4, webm, png) render klasörüne konulduğunda burada görünür ve dosya adındaki vaka bilgisiyle eşleştirilir."
        : "OpenFOAM outputs (mp4, webm, png) placed in the render folder appear here and are matched to the case by their file name.") +
      `<div style="margin-top:12px"><button class="dugme" data-komut="klasor-render">${esc(T("komut.klasorRender"))}</button></div>` +
      `<div class="grafik-not" style="margin-top:12px">${esc(DIL === "tr" ? "Dosya adı sözleşmesi:" : "File name convention:")} <code class="tek">pmma_g1e-4_o21_p101.3_a10.mp4</code></div></div></div>`);
  }
  const tr = DIL === "tr";
  const girdi = S.sonuc && S.sonuc.tahmin && S.sonuc.tahmin.girdi;
  // Çözülen vakaya göre süz: tam (aynı malzeme + yerçekimi bandı) → benzer (aynı yakıt türü) → yok
  let uyg = null;
  if (girdi && !S.renderTumu) {
    const kosuAd = (S.ayrintili && S.ayrintili.kosu) || null;
    const anahtar = [girdi.malzeme, girdi.yakit_turu, girdi.g, DIL, kosuAd, liste.map((x) => x.ad).join("|")].join("#");
    if (S.renderUygun && S.renderUygun.anahtar === anahtar) uyg = S.renderUygun;
    else {
      if (!S.renderUygun || S.renderUygun.anahtar !== anahtar || !S.renderUygun.bekle) {
        S.renderUygun = { anahtar, bekle: true };
        API.renderUygun(girdi.malzeme, girdi.yakit_turu || null, girdi.g, DIL, kosuAd).then((r) => {
          if (S.renderUygun && S.renderUygun.anahtar === anahtar) {
            S.renderUygun = { anahtar, mod: r.mod, adlar: r.adlar || [] };
            renderYokla();   // uyumsuz renderlar archive/ altına taşınmış olabilir: listeyi yenile
            if ((Kabuk.agacSecili() || "") === "r-render") renderGorseli();
          }
        }).catch(() => { S.renderUygun = { anahtar, mod: "tum", adlar: [] }; if ((Kabuk.agacSecili() || "") === "r-render") renderGorseli(); });
      }
      uyg = { bekle: true };
    }
  }
  if (uyg && uyg.bekle) return Kabuk.gorselYaz(T("agac.render"), `<div class="gorunum"><div class="bos">${esc(tr ? "Uygun render aranıyor…" : "Looking for a matching render…")}</div></div>`);
  const sogus = uyg && uyg.mod && uyg.mod !== "tum";
  const gor = !sogus ? liste : uyg.adlar.map((ad) => liste.find((x) => x.ad === ad)).filter(Boolean);
  const bantAd = (b) => ({ uzay: tr ? "uzay" : "space", ay: tr ? "Ay" : "Moon", mars: "Mars", dunya: tr ? "Dünya" : "Earth" }[b] || b);
  const kosulMetni = (x) => x.vaka
    ? `${x.vaka.malzeme} · g=${(x.paneller && x.paneller.length ? x.paneller.map(bantAd).join(" | ") : gMetni(x.vaka.g))} · %${nf(x.vaka.oksijen, 1)} O₂ · ${nf(x.vaka.basinc, 1)} kPa`
    : (tr ? "koşul dosya adından okunamadı" : "condition not readable from file name");
  const tumuKutu = girdi
    ? `<label class="grafik-not" style="display:inline-flex;gap:6px;align-items:center;margin-left:10px"><input type="checkbox" id="renderTumu"${S.renderTumu ? " checked" : ""}> ${esc(tr ? "Tümünü göster" : "Show all")} (${liste.length})</label>`
    : "";
  let etiket = "";
  if (sogus && uyg.mod === "kosu" && gor.length) {
    etiket = `<div class="uyari-satir" role="note"><b>${esc(tr ? "Yalnız bu koşunun renderları gösteriliyor." : "Showing only this run's renders.")}</b> ${esc(tr ? "Diğer renderlar render/archive/ klasöründe; 'Tümünü göster' ile geri gelir." : "Other renders are in render/archive/; 'Show all' brings them back.")}</div>`;
  }
  if (sogus && uyg.mod === "benzer" && gor.length) {
    const kos = [...new Set(gor.map(kosulMetni))].slice(0, 3).join("; ");
    etiket = `<div class="uyari-satir" role="note"><b>${esc(tr ? "Bu vaka için hazır render yok; benzer koşuldan gösterim:" : "No ready render for this case; showing a similar condition:")}</b> ${esc(kos)}</div>`;
  }
  if (sogus && uyg.mod === "yok") {
    return Kabuk.gorselYaz(T("agac.render"),
      `<div class="gorunum"><div class="bos"><b>${esc(tr ? "Bu vaka için render yok" : "No render for this case")}</b>` +
      esc(tr ? `${girdi.malzeme} (${girdi.yakit_turu || "?"}) için ne aynı malzemeden ne de aynı yakıt türünden render var.` : `No render exists for ${girdi.malzeme} or for the same fuel type.`) +
      `<div style="margin-top:12px">${tumuKutu}</div></div></div>`) || kutuBagla();
  }
  const s = S.renderSecili || (gor[0] && gor[0].ad);
  const v = gor.find((x) => x.ad === s) || gor[0];
  if (!v) return Kabuk.gorselYaz(T("agac.render"), `<div class="gorunum"><div class="bos">${esc(tr ? "Uygun render aranıyor…" : "Looking for a matching render…")}</div></div>`);
  const sec = gor.map((x) => `<option value="${esc(x.ad)}"${x.ad === v.ad ? " selected" : ""}>${esc(x.ad)}</option>`).join("");
  const oynatici = v.tur === "video"
    ? `<video src="${esc(v.yol)}" controls autoplay muted loop playsinline></video>`
    : `<img src="${esc(v.yol)}" alt="${esc(v.ad)}">`;
  Kabuk.gorselYaz(T("agac.render"),
    `<div class="gorunum"><div class="render-kap">` + etiket +
    `<div class="suzgec"><select class="giris" id="renderSec" style="max-width:420px">${sec}</select>` +
    `<button class="dugme kucuk" data-komut="klasor-render">${esc(T("komut.klasorRender"))}</button>${tumuKutu}</div>` +
    oynatici +
    `<div class="render-bilgi"><span>${esc(new Date(v.zaman * 1000).toLocaleString(tr ? "tr-TR" : "en-US"))}</span>` +
    `<span>${esc(nf(v.boyut / 1048576, 1))} MB</span></div>` +
    `<div class="grafik-not">${esc(tr ? "Render koşulu:" : "Render condition:")} ${esc(kosulMetni(v))}${v.ad.indexOf("_kosu-") >= 0 ? " · " + esc(tr ? "ayrıntılı OpenFOAM koşusu" : "detailed OpenFOAM run") : ""}</div>` +
    `<div class="grafik-not"><b>${esc(tr ? "GÖSTERİM — deney verisiyle doğrulanmadı" : "ILLUSTRATION — not validated against experimental data")}</b></div></div></div>`);
  kutuBagla();
  function kutuBagla() {
    const k = $("#renderTumu");
    if (k) k.addEventListener("change", async () => {
      S.renderTumu = k.checked; S.renderSecili = null;
      if (k.checked) { try { await API.renderArsiviGeriYukle(); await renderYokla(); } catch (e) { /* liste yenilenemedi */ } }
      renderGorseli();
    });
  }
  const sel = $("#renderSec");
  if (sel) sel.addEventListener("change", () => { S.renderSecili = sel.value; renderGorseli(); });
}

function dunyaGorseli() {
  const veri = DIL === "tr" ? [
    ["Hiperbarik oksijen odaları", "Hastane odalarında oksijen %21'in çok üstüne çıkar. Sönme sınırı hesabı, odada hangi tekstil ve plastiklerin bulunabileceğini doğrudan belirler."],
    ["Denizaltılar ve dalış sistemleri", "Kapalı ortam, değişken basınç ve zenginleştirilmiş oksijen; uzay kabinine en çok benzeyen Dünya ortamı budur."],
    ["Yeraltı madenleri ve sığınaklar", "Düşük akışlı, kapalı hacimlerde yangının nasıl yayılacağı akış eğrisindeki düşük akış bölgesiyle aynı fiziktir."],
    ["Uçak kargo bölmeleri", "Düşük basınç (~75 kPa) ve sınırlı hava akışı; basınç ekseni bu durum için doğrudan kullanılabilir."],
    ["Yangın güvenliği standartları", "NASA STD-6001 benzeri malzeme kabul testlerinin hangi oksijen düzeyinde yapılması gerektiğine dair ön eleme."],
  ] : [
    ["Hyperbaric oxygen chambers", "Hospital chambers run well above 21% oxygen. The extinction-limit calculation directly governs which textiles and plastics may be present."],
    ["Submarines and diving systems", "Closed environment, variable pressure and enriched oxygen — the closest terrestrial analogue to a spacecraft cabin."],
    ["Underground mines and shelters", "Fire spread in low-flow enclosed volumes is the same physics as the low-flow region of the flow curve."],
    ["Aircraft cargo bays", "Low pressure (~75 kPa) and limited air flow; the pressure axis applies directly."],
    ["Fire safety standards", "Pre-screening for the oxygen level at which NASA STD-6001 style material acceptance tests should be run."],
  ];
  const ic = `<div class="gorunum"><div class="gorunum-bas"><h3>${esc(T("agac.dunya"))}</h3></div>` +
    `<div class="kutular k2">` + veri.map((p) =>
      `<div class="kart"><h3>${esc(p[0])}</h3><div style="font-size:12.5px;line-height:1.6">${esc(p[1])}</div></div>`).join("") +
    `</div></div>`;
  Kabuk.gorselYaz(T("agac.dunya"), ic);
}

/* ---------------------------------------------------------------- ALT PANEL */
function mesajCiz() {
  const h = !S.mesajlar.length
    ? `<div class="bos" style="margin:14px">${esc(DIL === "tr" ? "Mesaj yok." : "No messages.")}</div>`
    : `<div class="alt-liste">` + S.mesajlar.map((m) =>
        `<div class="alt-satir ${esc(m.tur)}"><span class="zaman">${esc(m.zaman)}</span>` +
        `<span class="tur">${esc({ uyari: DIL === "tr" ? "uyarı" : "warning", hata: DIL === "tr" ? "hata" : "error", bilgi: DIL === "tr" ? "bilgi" : "info" }[m.tur] || m.tur)}</span>` +
        `<span class="metin">${esc(m.metin)}</span></div>`).join("") + `</div>`;
  Kabuk.altYaz("mesaj", h);
  const uyariSayi = S.mesajlar.filter((m) => m.tur !== "bilgi").length;
  const d = $("#dMesaj");
  if (d) {
    d.textContent = (DIL === "tr" ? "Mesajlar: " : "Messages: ") + S.mesajlar.length +
      (uyariSayi ? (DIL === "tr" ? ` (${uyariSayi} uyarı/hata)` : ` (${uyariSayi} warning/error)`) : "");
    d.classList.toggle("var", uyariSayi > 0);
  }
}

/* Durum çubuğu: bağlantı (topluluk deposu + yapay zeka anahtarı) */
function baglantiGoster() {
  const b = S.toplulukBilgi || {};
  const gh = b.yukleniyor ? (DIL === "tr" ? "bağlanıyor…" : "connecting…")
    : b.kaynak === "canli" ? (DIL === "tr" ? "çevrimiçi" : "online")
    : b.kaynak === "onbellek" ? (DIL === "tr" ? "çevrimdışı (önbellek)" : "offline (cache)")
    : (DIL === "tr" ? "yerel" : "local");
  const llm = S.sistem && S.sistem.anahtar_var ? (DIL === "tr" ? "anahtar var" : "key set") : (DIL === "tr" ? "anahtar yok" : "no key");
  Kabuk.durum("dBaglanti", (DIL === "tr" ? "Bağlantı: GitHub " : "Connection: GitHub ") + gh + " · LLM " + llm);
}

function gunlukCiz() {
  const t = S.sonuc && S.sonuc.tahmin;
  const ust = t && t.adimlar ? `<div style="margin:10px 14px 0"><b>${esc(DIL === "tr" ? "Son çözümün analiz adımları" : "Analysis steps of the last solve")}</b>` +
    ` <span class="sonuk">${esc(t.girdi ? t.girdi.malzeme + " · %" + nf(t.girdi.oksijen, 1) + " O₂" : "")}</span>` + adimTablosu(t.adimlar) + `</div>` : "";
  const h = ust + (!S.gunluk.length
    ? `<div class="bos" style="margin:14px">${esc(DIL === "tr" ? "Bu oturumda kayıt yok." : "No entries in this session.")}</div>`
    : `<div class="tablo-kap" style="border:0"><table class="veri"><thead><tr>` +
      [DIL === "tr" ? "Zaman" : "Time", DIL === "tr" ? "İşlem" : "Action", DIL === "tr" ? "Süre" : "Duration",
       DIL === "tr" ? "Girdiler" : "Inputs", DIL === "tr" ? "Sonuç" : "Result"].map((x) => `<th>${esc(x)}</th>`).join("") +
      `</tr></thead><tbody>` + S.gunluk.map((l) =>
        `<tr><td class="tek">${esc(l.zaman)}</td><td>${esc(l.tur)}</td><td class="s">${l.sure == null ? "–" : esc(nf(l.sure, 2)) + " s"}</td>` +
        `<td class="tek">${esc(l.girdi || "")}</td><td style="${l.hata ? "color:var(--hata)" : ""}">${esc(l.hata || l.sonuc || "")}</td></tr>`).join("") +
      `</tbody></table></div>`);
  Kabuk.altYaz("gunluk", h);
}

/* ---------------------------------------------------------------- ÇÖZÜM */
/* ---------------------------------------------------------------- analiz adımları (tahmin.adimlar, 12 adım) */
function ayrintiMetni(a) {
  if (!a || typeof a !== "object" || !Object.keys(a).length) return "";
  const m = Object.entries(a).map(([k, v]) => k + ": " + (typeof v === "object" ? JSON.stringify(v) : String(v))).join(" · ");
  return m.length > 260 ? m.slice(0, 257) + "…" : m;
}
function adimTablosu(adimlar, baslik) {
  if (!adimlar || !adimlar.length) return "";
  const sirali = adimlar.slice().sort((x, y) => x.no - y.no);
  const toplam = sirali.reduce((a, x) => a + (x.sure_ms || 0), 0);
  return `<div class="tablo-kap" style="margin-top:14px"><table class="veri"><thead><tr>` +
    `<th class="s">#</th><th>${esc(baslik || (DIL === "tr" ? "Analiz adımı" : "Analysis step"))}</th><th class="s">${esc(DIL === "tr" ? "Süre" : "Time")}</th><th>${esc(DIL === "tr" ? "Karar" : "Decision")}</th></tr></thead><tbody>` +
    sirali.map((x) => `<tr><td class="s">${esc(x.no)}</td><td>${esc(x.ad)}</td><td class="s" style="white-space:nowrap">${esc(nf(x.sure_ms, 1))} ms</td>` +
      `<td style="overflow-wrap:anywhere">${esc(x.karar)}${ayrintiMetni(x.ayrinti) ? `<div class="sonuk" style="font-size:11px;margin-top:2px;overflow-wrap:anywhere">${esc(ayrintiMetni(x.ayrinti))}</div>` : ""}</td></tr>`).join("") +
    `<tr><td></td><td><b>${esc(DIL === "tr" ? "toplam" : "total")}</b></td><td class="s"><b>${esc(nf(toplam, 1))} ms</b></td><td></td></tr>` +
    `</tbody></table></div>`;
}
/* arka ucun "Güven düşük (x/100)" uyarısı v1 skorunu kullanır; v2 varsa arayüzde v2'ye göre yazılır */
function uyarilarGoster(t) {
  const v = guvenV2(t);
  let u = (t.uyarilar || []).slice();
  if (v) {
    u = u.filter((x) => !/^Güven düşük \(\d+\/100\)/.test(x));
    if (v.bant === "düşük") { const g = guvenSebebi(t); u.push((DIL === "tr" ? `Güven düşük (${v.skor}/100): ` : `Low confidence (${v.skor}/100): `) + g.charAt(0).toLocaleLowerCase(DIL === "tr" ? "tr-TR" : "en-US") + g.slice(1)); }
  }
  return u;
}

const COZUM_ADIMLARI = [
  ["tahmin", "coz.adimTahmin"], ["oksijen_egrisi", "coz.adimOksijen"],
  ["harita", "coz.adimHarita"], ["akis_egrisi", "coz.adimAkis"], ["yakin", "coz.adimYakin"],
];

function cozumEkraniCiz(yuzde, aktifAdim, bitti, hata) {
  const adimlar = COZUM_ADIMLARI.map((p) => {
    const d = S.adimDurum[p[0]] || (bitti ? "bitti" : "bekliyor");
    return `<div class="adim ${esc(d)}"><span class="ikon"></span><span>${esc(T(p[1]))}</span>` +
      `<span class="sure">${esc(S.adimSure && S.adimSure[p[0]] ? nf(S.adimSure[p[0]], 2) + " s" : "")}</span></div>`;
  }).join("");
  S.cozumHtml =
    `<div class="cozum-kap"><div class="cozum-ic">` +
    `<h2>${esc(hata ? T("coz.hata") : bitti ? T("coz.bitti") : T("coz.basligi"))}</h2>` +
    `<div class="alt">${esc(hata || T("coz.alt"))}</div>` +
    `<div class="ilerleme-bas"><span>${esc(aktifAdim || "")}</span><span class="sayi">%${esc(nf(yuzde, 0))}</span></div>` +
    `<div class="ilerleme"><i style="width:${yuzde}%" class="${yuzde > 0 && yuzde < 100 && !bitti ? "" : ""}"></i></div>` +
    `<div class="adimlar">${adimlar}</div>` +
    (bitti && !hata ? `<div style="margin-top:20px;display:flex;gap:9px"><button class="dugme birincil" data-komut="git-sonuclar">${esc(DIL === "tr" ? "Sonuçları aç" : "Open results")}</button>` +
      `<button class="dugme" data-komut="kaydet">${esc(T("komut.kaydet"))}</button></div>` : "") +
    (bitti && !hata && S.sonuc && S.sonuc.tahmin && S.sonuc.tahmin.adimlar
      ? `<h3 style="margin-top:22px">${esc(DIL === "tr" ? "Analiz adımları (tahmin.adimlar)" : "Analysis steps (tahmin.adimlar)")}</h3>` + adimTablosu(S.sonuc.tahmin.adimlar)
      : "") +
    `</div></div>`;
  /* Ayrı çözüm ekranı yok: ilerleme (adım adı, yüzde) Çözüm düğümünün notunda ve durum çubuğunda.
     Ayrıntılı adım listesi Çözüm düğümü seçilince görüntü alanında görünür. */
  if (S.cozuluyor) {
    S.cozumIlerleme = { adim: aktifAdim || "", yuzde };
    Kabuk.durum("dMotor", T("durum.cozuluyor") + " " + (aktifAdim ? aktifAdim + " · " : "") + "%" + nf(yuzde, 0), "bekle");
    agacYenile();
  } else S.cozumIlerleme = null;
  if (Kabuk.agacSecili() === "cozum") cozumBilgisiGoster();
}

function cozumBilgisiGoster() {
  izleyiciGoster();     // Çözüm İzleyici: canlı günlük, izleme grafikleri, koşu kuyruğu (js/monitor.js)
}

async function cozHizli(onTahmin) {
  if (!dogrula() || S.cozuluyor) return null;
  if (S.motor.durum !== "hazir") { Kabuk.bildir(T("durum.motorYukleniyor"), "hata"); return null; }

  S.cozuluyor = true;
  S.cozumHata = null;
  agacYenile();
  S.adimDurum = {}; S.adimSure = {};
  COZUM_ADIMLARI.forEach((p) => (S.adimDurum[p[0]] = "bekliyor"));
  $("#btnCoz").disabled = true;
  $("#btnCoz").classList.add("calisiyor");
  Kabuk.durum("dMotor", T("durum.cozuluyor"), "bekle");
  Kabuk.sekmeAc("calisma");
  cozumEkraniCiz(3, T("coz.adimTahmin"));

  const k = kosul();
  izHizliBaslat(k);
  let tani = null;
  try { tani = await API.malzemeTani(k.malzeme); } catch (e) { tani = null; }
  S.sonTani = tani;
  if (tani && tani.kaynak === "llm_gerekli") {
    const m = DIL === "tr" ? `'${k.malzeme}' listede ve kütüphanede yok: LLM malzemeyi tanıyor (~30 s)…`
                           : `'${k.malzeme}' is not in the list or library: the LLM is identifying it (~30 s)…`;
    cozumEkraniCiz(3, m);
    mesaj("bilgi", m);
  }
  const bas = performance.now();
  let r;
  try {
    r = await API.coz(k);
  } catch (e) {
    r = { hata: e.message };
  }
  const sure = (performance.now() - bas) / 1000;

  S.cozuluyor = false;
  $("#btnCoz").classList.remove("calisiyor");
  Kabuk.durum("dMotor", T("durum.motorHazir"), "ok");
  dogrula();

  const girdiMetni = `${k.malzeme} g=${gMetni(k.g)} O₂=${nf(k.oksijen, 2)} p=${nf(k.basinc, 1)}`;

  if (r.hata || !r.tahmin || r.tahmin.hata) {
    const m = r.hata || r.tahmin.hata;
    S.adimDurum.tahmin = "hata";
    S.cozumHata = m;
    cozumEkraniCiz(100, "", true, m);
    Kabuk.agacSec("cozum");
    mesaj("hata", m);
    izHizliAkit(null, m);
    gunluk({ tur: DIL === "tr" ? "Çöz" : "Solve", sure, girdi: girdiMetni, hata: m });
    Kabuk.bildir(m, "hata", 8000);
    agacYenile();
    return null;
  }

  COZUM_ADIMLARI.forEach((p) => {
    const a = r[p[0]];
    S.adimDurum[p[0]] = a && a.hata ? "hata" : "bitti";
    if (a && a.sure_sn != null) S.adimSure[p[0]] = a.sure_sn;
  });

  const t = r.tahmin.veri;
  S.sonuc = {
    kosul: k, tahmin: t, zaman: new Date().toLocaleString(DIL === "tr" ? "tr-TR" : "en-US"),
    oksijen_egrisi: r.oksijen_egrisi && r.oksijen_egrisi.veri || null,
    harita: r.harita && r.harita.veri || null,
    akis_egrisi: r.akis_egrisi && r.akis_egrisi.veri || null,
    yakin: (r.yakin && r.yakin.veri) || [],
  };
  S.llm = { durum: "yok", metin: null };
  izHizliAkit(t);
  if (S.sohbet.kosul !== JSON.stringify(k)) sohbetEskiIsaretle();

  if (!S.baslik || S.baslikOto) { S.baslik = otomatikBaslik(k, t); S.baslikOto = true; }
  kirlet(true);

  uyarilarGoster(t).forEach((u) => mesaj("uyari", u));
  ["oksijen_egrisi", "harita", "akis_egrisi", "yakin"].forEach((a) => {
    if (r[a] && r[a].hata) mesaj("hata", a + ": " + r[a].hata);
  });
  mesaj(t.yanma_ihtimali == null ? "uyari" : "bilgi", t.ozel_durum
    ? (DIL === "tr" ? `Yakıt olarak çözülmedi: '${k.malzeme}' = ${t.ozel_durum.ad} (${ozelKisa(t)}).` : `Not solved as a fuel: '${k.malzeme}' = ${t.ozel_durum.ad} (${ozelKisa(t)}).`)
    : t.yanma_ihtimali == null
    ? (DIL === "tr" ? `Malzeme tanınmadı: '${k.malzeme}'. Listeden seçin ya da kütüphaneye ekleyin.` : `Material not recognized: '${k.malzeme}'. Pick from the list or add it to the library.`)
    : (DIL === "tr" ? "Çözüm tamamlandı: " : "Solution complete: ") +
      t.risk_seviyesi + " · " + (DIL === "tr" ? "güven " : "confidence ") + nf(guvenSkoru(t), 0) + "/100");
  gunluk({ tur: DIL === "tr" ? "Çöz" : "Solve", sure: t.sure_sn, girdi: girdiMetni,
           sonuc: t.ozel_durum ? ozelKisa(t) : t.risk_seviyesi + " · %" + pct(t.yanma_ihtimali, 0) });

  S.sonSolveSure = t.sure_sn;
  cozumEkraniCiz(100, "", true);
  agacYenile();
  if (!onTahmin) { Kabuk.agacSec("r-ozet"); Kabuk.sekmeAc("sonuclar"); }
  Kabuk.durum("dSure", (DIL === "tr" ? "son çözüm " : "last solve ") + nf(t.sure_sn, 2) + " s");
  return S.sonuc;
}

function otomatikBaslik(k, t) {
  const ortam = k.g < 0.01 ? "ISS" : k.g < 0.9 ? (k.g < 0.25 ? (DIL === "tr" ? "Ay" : "Moon") : "Mars") : (DIL === "tr" ? "Dünya" : "Earth");
  const sev = t ? (t.risk_seviyesi || (t.ozel_durum ? ozelKisa(t) : (DIL === "tr" ? "tanınmadı" : "not recognized"))) : "";
  return `${k.malzeme} · ${ortam} · %${nf(k.oksijen, 1)} O₂` + (t ? ` · ${sev}` : "");
}

async function llmIste() {
  if (S.llm.durum === "bekle") return;
  Kabuk.sekmeAc("calisma");
  Kabuk.agacSec("r-llm");          // sayfa HEMEN açılır: motor yüklenmesini ya da çözümü beklemez
  // Çözüm GEREKMEZ: ekrandaki girdilerle uyumlu bir çözüm varsa sayılarıyla, yoksa yalnız girdilerden yorumlanır.
  const girdiler = kosul();
  const istenen = JSON.stringify(girdiler);
  const sonucta = !!S.sonuc && JSON.stringify(S.sonuc.kosul) === istenen;
  S.llm = { durum: "bekle", metin: null, kosul: istenen };
  agacYenile();
  llmGorseli();
  dogrula();
  mesaj("bilgi", DIL === "tr" ? "Yapay zeka yorumu istendi." : "AI commentary requested.");

  const bas = performance.now();
  let r;
  try { r = await API.llmYorum(sonucta ? S.sonuc.tahmin : null, girdiler); } catch (e) { r = { hata: e.message }; }
  const sure = (performance.now() - bas) / 1000;

  if (JSON.stringify(kosul()) !== istenen) {      // bu sırada girdiler değişti
    S.llm = { durum: "eski", metin: null, kosul: istenen };
    mesaj("uyari", DIL === "tr" ? "Yapay zeka yorumu önceki girdiler için geldi; gösterilmedi." : "AI commentary arrived for previous inputs; not shown.");
    agacYenile(); dogrula();
    if ((Kabuk.agacSecili() || "") === "r-llm") llmGorseli();
    return;
  }
  let metin;
  if (r.hata) {
    metin = (DIL === "tr" ? "Yapay zeka yorumu alınamadı (" : "AI commentary unavailable (") + r.hata + ")";
    S.llm = { durum: "hata", metin };
    mesaj("hata", metin);
  } else {
    metin = r.yorum ||
      (DIL === "tr" ? "Yapay zeka yorumu alınamadı (boş yanıt)" : "AI commentary unavailable (empty response)");
    const basarisiz = metin.indexOf("alınamadı") === 0 || metin.indexOf("LLM yorumu alınamadı") === 0;
    S.llm = { durum: basarisiz ? "hata" : "geldi", metin, kosul: istenen };
    mesaj(basarisiz ? "hata" : "bilgi", basarisiz ? metin : (DIL === "tr" ? "Yapay zeka yorumu alındı." : "AI commentary received."));
    if (!basarisiz) kirlet(true);
  }
  gunluk({ tur: DIL === "tr" ? "Yapay zeka" : "AI", sure, girdi: girdiler.malzeme,
           hata: S.llm.durum === "hata" ? metin : "", sonuc: S.llm.durum === "geldi" ? (DIL === "tr" ? "yorum geldi" : "received") : "" });
  agacYenile();
  dogrula();
  if ((Kabuk.agacSecili() || "") === "r-llm") llmGorseli();
  else Kabuk.bildir(DIL === "tr" ? "Yapay zeka yorumu hazır." : "AI commentary ready.", "basari");
}

/* ---------------------------------------------------------------- BAŞLANGIÇ EKRANI */
function baslangicCiz() {
  const sis = S.sistem || {};
  const motorMetni = { yukleniyor: T("durum.motorYukleniyor"), hazir: T("durum.motorHazir"), hata: T("durum.motorHata") }[S.motor.durum];
  const sonVakalar = S.vakalar.slice(0, 7);

  const hizli = [
    ["yeni", '<path d="M10.5 2v17M2 10.5h17"/>', T("bas.yeniVaka"), T("bas.yeniVakaAlt")],
    ["ornek-iss", '<circle cx="10.5" cy="10.5" r="8"/><path d="M2.5 10.5h16M10.5 2.5c3.5 4 3.5 12 0 16M10.5 2.5c-3.5 4-3.5 12 0 16"/>', T("bas.ornekIss"), T("bas.ornekIssAlt")],
    ["ornek-mars", '<circle cx="10.5" cy="10.5" r="7"/><path d="M7 8.5c2 1.5 5 1.5 7 0M6.5 13c2.5-1.5 5.5-1 7.5.5"/>', T("bas.ornekMars"), T("bas.ornekMarsAlt")],
    ["git-kutuphane", '<path d="M3 3.5h6l1.5 2H18v12H3z"/>', T("bas.kutuphane"), T("bas.kutuphaneAlt")],
  ].map((p) => `<button data-komut="${esc(p[0])}"><svg viewBox="0 0 21 21">${p[1]}</svg><b>${esc(p[2])}</b><span>${esc(p[3])}</span></button>`).join("");

  const adimlar = [["bas.adim1", "bas.adim1Alt"], ["bas.adim2", "bas.adim2Alt"],
                   ["bas.adim3", "bas.adim3Alt"], ["bas.adim4", "bas.adim4Alt"]]
    .map((p, i) => `<div class="akis-adim"><div class="no">${i + 1}</div><b>${esc(T(p[0]))}</b><span>${esc(T(p[1]))}</span></div>`).join("");

  const bilgi = (a, d) => `<div class="bilgi-satir"><span class="etiket-ad">${esc(a)}</span><span class="deger">${d}</span></div>`;

  const ic =
    `<div class="sayfa">` +
      `<div class="bas-ust">` +
        `<img class="bas-logo" src="brand/logo-round.png" alt="AHUT">` +
        `<div><h1>AHUT <span class="flare">FLARE</span></h1>` +
          `<div class="acilim">Fire Learning, Analysis &amp; Research Engine</div>` +
          `<div class="alt"><b>${esc(T("bas.slogan"))}</b><br>${esc(T("bas.ozet"))}</div>` +
          `<div class="surum"><span class="etiket">v${esc(S.surum)}</span>` +
            `<span class="etiket">${esc(DIL === "tr" ? "açık kaynak" : "open source")} · MIT</span>` +
            `<span class="etiket">${esc(DIL === "tr" ? "çevrimdışı çalışır" : "works offline")}</span>` +
            `<span class="etiket ${S.motor.durum === "hata" ? "uyari" : ""}">${esc(motorMetni)}</span>` +
          `</div></div></div>` +

      `<div class="bas-orta"><div class="bas-sol">` +
        `<h3 style="font-size:11px;letter-spacing:.9px;text-transform:uppercase;color:var(--sonuk);margin-bottom:11px">${esc(T("bas.hizli"))}</h3>` +
        `<div class="hizli">${hizli}</div>` +
        `<h3 style="font-size:11px;letter-spacing:.9px;text-transform:uppercase;color:var(--sonuk);margin-bottom:11px">${esc(T("bas.nasil"))}</h3>` +
        `<div class="akis">${adimlar}</div>` +
        `<h3 style="font-size:11px;letter-spacing:.9px;text-transform:uppercase;color:var(--sonuk);margin-bottom:11px">${esc(T("bas.veri"))}</h3>` +
        `<div class="kutular k2">` +
          `<div class="kart"><h3>${esc(DIL === "tr" ? "Veri kaynakları" : "Data sources")}</h3>` +
            bilgi("NASA PSI", esc(DIL === "tr" ? "mikro yerçekimi yanma deneyleri (BASS, FLEX, Saffire)" : "microgravity combustion experiments (BASS, FLEX, Saffire)")) +
            bilgi(DIL === "tr" ? "Makaleler" : "Papers", esc(DIL === "tr" ? "elle ve dil modeliyle çıkarılmış deney satırları" : "rows extracted manually and by a language model")) +
            bilgi(DIL === "tr" ? "Doğrulama" : "Validation", esc(DIL === "tr" ? "OpenFOAM karşı akış alevi koşuları" : "OpenFOAM counterflow flame runs")) +
          `</div>` +
          `<div class="kart"><h3>${esc(DIL === "tr" ? "Yöntem" : "Method")}</h3>` +
            bilgi(DIL === "tr" ? "Risk modeli" : "Risk model", esc(DIL === "tr" ? "scikit-learn topluluk modeli, belirsizlik tahminiyle" : "scikit-learn ensemble with uncertainty estimate")) +
            bilgi(DIL === "tr" ? "Fizik motoru" : "Physics engine", esc(DIL === "tr" ? "yarı-ampirik alev modeli (bağımsız ikinci görüş)" : "semi-empirical flame model (independent second opinion)")) +
            bilgi(DIL === "tr" ? "Güven skoru" : "Confidence", esc(DIL === "tr" ? "veri yoğunluğu + uyum + motor doğruluğu" : "data density + agreement + engine accuracy")) +
          `</div></div>` +
      `</div>` +

      `<div class="bas-sag">` +
        `<h3>${esc(T("bas.sonVakalar"))}</h3>` +
        (sonVakalar.length ? sonVakalar.map((v) =>
          `<div class="son-vaka" data-vaka="${esc(v.id)}"><span class="rozet ${ROZET_SINIF(v.risk_seviyesi)}">${esc(v.risk_seviyesi || "—")}</span>` +
          `<div class="ozet"><b>${esc(v.baslik)}</b><span>${esc((v.guncelleme || "").replace("T", " ").slice(0, 16))}</span></div></div>`).join("")
          : `<div class="sonuk" style="font-size:12px">${esc(DIL === "tr" ? "Henüz kayıtlı vaka yok." : "No saved cases yet.")}</div>`) +
        `<h3 style="margin-top:20px">${esc(T("bas.sistem"))}</h3>` +
        bilgi("Python", esc(sis.python || "–")) +
        bilgi(DIL === "tr" ? "Çekirdek" : "Cores", esc(sis.cekirdek_sayisi || "–")) +
        bilgi(DIL === "tr" ? "SI anahtarı" : "SI key",
          sis.anahtar_var ? `<span style="color:var(--ok)">${esc(DIL === "tr" ? "bulundu" : "found")}</span>`
                          : `<span style="color:var(--uyari)">${esc(DIL === "tr" ? "yok" : "missing")}</span>`) +
        bilgi(DIL === "tr" ? "Veri klasörü" : "Data folder",
          `<a href="#" data-komut="klasor-veri">${esc(DIL === "tr" ? "aç" : "open")}</a>`) +
      `</div></div>` +

      `<div class="bas-alt"><span>AHUT — ${esc(DIL === "tr" ? "Ankara Havacılık ve Uzay Teknolojileri Hackathon Takımı" : "Ankara Aerospace Technologies Hackathon Team")}</span>` +
        `<span class="sag"><button class="dugme kucuk" data-komut="hakkinda">${esc(T("komut.hakkinda"))}</button>` +
        `<button class="dugme kucuk" data-komut="kisayollar">${esc(T("komut.kisayollar"))}</button></span></div>` +
    `</div>`;

  Kabuk.ekranYaz("ek-baslangic", ic);
  // Tıklama dinleyicisi baslat() içinde bir kez kurulur (her çizimde eklenirse birikir).
}

/* ---------------------------------------------------------------- KÜTÜPHANE / TOPLULUK */
let ktpAra = "";
let ktpGorunum = "vakalar";          // "vakalar" | "malzemeler"
let mlzTur = "";                     // malzeme süzgeci: "" | kati | sivi | gaz
let mlzKat = "";                     // kategori süzgeci: "" | kütüphanedeki "kategori" değerleri
let MLZ = null;                      // material_library.json (ilk açılışta yüklenir)

/* ---------------------------------------------------------------- KÜTÜPHANE > MALZEMELER */
const MLZ_TUR = { kati: ["Katı", "Solid"], sivi: ["Sıvı", "Liquid"], gaz: ["Gaz", "Gas"] };
const MLZ_KAT_EN = { "kıyafet/kumaş": "clothing/fabric", "plastik": "plastic", "kompozit/yapı": "composite/structure",
  "kauçuk/conta": "rubber/seal", "yalıtım/köpük": "insulation/foam", "elektronik/kablo": "electronics/cable",
  "ambalaj/diğer": "packaging/other", "yiyecek": "food", "pil": "battery", "akışkan/yağ": "fluid/oil",
  "yakıt/itici": "fuel/propellant", "temizlik/çözücü": "cleaning/solvent", "gaz": "gas" };
const MLZ_OZEL = { oksitleyici: ["oksitleyici", "oxidizer"], yanmaz: ["yanmaz", "non-flammable"], pil: ["pil · motor yok", "battery · no engine"] };
function ozelKisa(t) { const o = t.ozel_durum || {}; return mlzDil(MLZ_OZEL[o.tur] || [o.tur || "", o.tur || ""]); }
function katAdi(k) { return DIL === "tr" ? k : (MLZ_KAT_EN[k] || k); }
const MLZ_ALAN = [   // [anahtar, TR, EN, ondalık]
  ["yogunluk", "Yoğunluk", "Density", 0],
  ["isil_deger_net", "Isıl değer (net)", "Heat of combustion (net)", 1],
  ["isil_deger_brut", "Isıl değer (brüt)", "Heat of combustion (gross)", 1],
  ["isil_deger", "Isıl değer (brüt/net belirsiz)", "Heat of combustion (gross/net unclear)", 1],
  ["kaynama_K", "Kaynama noktası", "Boiling point", 1],
  ["buharlasma_isisi", "Buharlaşma ısısı", "Heat of vaporization", 0],
  ["LOI", "LOI", "LOI", 0],
  ["parlama_noktasi_K", "Parlama noktası", "Flash point", 1],
  ["kendiliginden_tutusma_K", "Kendiliğinden tutuşma", "Autoignition temperature", 1],
  ["LFL", "Alt yanma sınırı (LFL)", "Lower flammability limit (LFL)", 2],
  ["UFL", "Üst yanma sınırı (UFL)", "Upper flammability limit (UFL)", 2],
  ["kritik_sicaklik_K", "Kritik sıcaklık", "Critical temperature", 1],
  ["yogunluk_kaynamaya_yakin", "Yoğunluk (kaynamaya yakın)", "Density (near boiling)", 0],
  ["molar_kutle", "Molar kütle", "Molar mass", 2],
];
const mlzDil = (a) => (DIL === "tr" ? a[0] : a[1]);

function mlzDurumSinif(d) {
  return d === "motorda kalibre" ? "" : d === "veri yok" ? " uyari" : "";
}

function mlzOzet(m) {
  const o = m.ozellikler || {}, p = [];
  const ek = (k, ad, birim, n) => { if (o[k] && o[k].deger != null) p.push(`<span>${esc(ad)} <b>${esc(nf(o[k].deger, n))}</b> ${esc(birim)}</span>`); };
  ek("yogunluk", "ρ", "kg/m³", 0);
  if (o.isil_deger_net) ek("isil_deger_net", "Hc", "MJ/kg", 1);
  else if (o.isil_deger_brut) ek("isil_deger_brut", "Hc", "MJ/kg", 1);
  else ek("isil_deger", "Hc", "MJ/kg", 1);
  ek("kaynama_K", "Tb", "K", 0);
  ek("LOI", "LOI", "%", 0);
  if (o.LFL && o.UFL && o.LFL.deger != null && o.UFL.deger != null)
    p.push(`<span>${esc(DIL === "tr" ? "yanma aralığı" : "flam. range")} <b>%${esc(nf(o.LFL.deger, 1))}–${esc(nf(o.UFL.deger, 0))}</b></span>`);
  if (o.parlama_noktasi_K && o.parlama_noktasi_K.deger != null)
    p.push(`<span>${esc(DIL === "tr" ? "parlama" : "flash")} <b>${esc(nf(o.parlama_noktasi_K.deger - 273.15, 0))}</b> °C</span>`);
  return p.length ? p.join("") : `<span>${esc(DIL === "tr" ? "kaynaklı özellik yok" : "no sourced property")}</span>`;
}

function mlzEtiket(m) {
  if (m._kaynak === "kullanici") {
    return `<span class="etiket${m.onay === "onayli" ? "" : " uyari"}">${esc(DIL === "tr" ? "kullanıcı · " : "user · ")}` +
      `${esc(m.onay === "onayli" ? (DIL === "tr" ? "onaylı" : "approved") : (DIL === "tr" ? "onaysız" : "unapproved"))}</span>`;
  }
  if (m.ozel) return `<span class="etiket uyari">${esc(mlzDil(MLZ_OZEL[m.ozel.tur] || [m.ozel.tur, m.ozel.tur]))}</span>`;
  return `<span class="etiket${mlzDurumSinif(m.durum)}">${esc(m.durum)}</span>`;
}

function mlzKarti(m) {
  return `<div class="vaka-kart" data-malzeme="${esc(m.id)}" data-mlzkaynak="${esc(m._kaynak || "kutuphane")}">` +
    `<div class="ust"><h4>${esc(m.ad)}</h4>${mlzEtiket(m)}</div>` +
    `<div class="aciklama">${esc((m.es_anlamlilar || []).join(" · "))}</div>` +
    `<div class="olcumler">${mlzOzet(m)}</div>` +
    `<div class="ayak"><span>${esc(mlzDil(MLZ_TUR[m.yakit_turu] || ["", ""]))}${m.kategori ? " · " + esc(katAdi(m.kategori)) : ""}</span>` +
      `<span>${esc(DIL === "tr" ? "motor ≈ " : "engine ≈ ")}<b>${esc(m.motor_benzeri || "—")}</b></span>` +
      `<span class="sag">${esc(m.varsayilan.numune_tipi || "")}</span></div></div>`;
}

function mlzAyrinti(id, kaynak) {
  if (MLZ === null) {   // Risk Özeti'nden açıldı (kütüphane henüz yüklenmedi)
    API.malzemeKutuphanesi().then((r) => { MLZ = r; mlzAyrinti(id, kaynak); }).catch(() => {});
    return;
  }
  const m = ((MLZ && MLZ.malzemeler) || []).find((x) => x.id === id && (!kaynak || (x._kaynak || "kutuphane") === kaynak));
  if (!m) return;
  const o = m.ozellikler || {};
  const satir = (ad, deger) => `<tr><th style="width:34%">${esc(ad)}</th><td>${deger}</td></tr>`;
  const ozSatir = MLZ_ALAN.flatMap(([k, tr, en, n]) =>
    Object.keys(o).filter((a) => a === k || a.indexOf(k + "_") === 0 && k !== "isil_deger").map((a) => {
      const v = o[a];
      const ad = (DIL === "tr" ? tr : en) + (a !== k ? " (" + a.slice(k.length + 1) + ")" : "");
      const deger = v.deger == null ? "–" : nf(v.deger, n) + " " + (v.birim || "") +
        (v.birim === "K" ? ` <span class="sonuk">(${esc(nf(v.deger - 273.15, 1))} °C)</span>` : "") +
        (v.aralik ? ` <span class="sonuk">(${esc(nf(v.aralik[0], n))}–${esc(nf(v.aralik[1], n))})</span>` : "") +
        (v.deger_kJ_mol != null ? ` <span class="sonuk">(${esc(nf(v.deger_kJ_mol, 1))} kJ/mol)</span>` : "");
      const kaynak = `<div class="sonuk" style="font-size:11px;margin-top:2px">${esc(v.kaynak || "")}` +
        (v.kaynak_metni ? ` — “${esc(v.kaynak_metni)}”` : "") + (v.not ? ` · ${esc(v.not)}` : "") + `</div>`;
      return `<tr><th>${esc(ad)}</th><td>${deger}${kaynak}</td></tr>`;
    }));
  const vs = m.veri_seti || {};
  const adlar = Object.entries(vs.eslesen_adlar || {}).map(([a, n]) => `${esc(a)} (${esc(n)})`).join(", ");
  const ic =
    `<div class="tablo-kap" style="border:0"><table class="veri"><tbody>` +
    satir(DIL === "tr" ? "Eş anlamlılar" : "Synonyms", esc((m.es_anlamlilar || []).join(", "))) +
    satir(DIL === "tr" ? "Yakıt türü" : "Fuel type", esc(mlzDil(MLZ_TUR[m.yakit_turu] || ["", ""]))) +
    (m.kategori ? satir(DIL === "tr" ? "Kategori" : "Category", esc(katAdi(m.kategori))) : "") +
    (m.ozel ? satir(DIL === "tr" ? "Özel durum" : "Special case",
      `<b>${esc(mlzDil(MLZ_OZEL[m.ozel.tur] || [m.ozel.tur, m.ozel.tur]))}</b><div class="sonuk" style="font-size:11px">${esc(m.ozel.uyari || "")}</div>`) : "") +
    satir(DIL === "tr" ? "Varsayılan numune" : "Default sample",
          esc(m.varsayilan.numune_tipi || "–") + (m.varsayilan.kalinlik_veya_cap_mm != null ? " · " + esc(nf(m.varsayilan.kalinlik_veya_cap_mm, 2)) + " mm" : "") +
          `<div class="sonuk" style="font-size:11px">${esc(m.varsayilan.kaynak || "")}</div>`) +
    satir(DIL === "tr" ? "Motorda benzeri" : "Engine surrogate",
          `<b>${esc(m.motor_benzeri || "—")}</b><div class="sonuk" style="font-size:11px">${esc(m.eslesme_gerekce || "")}</div>`) +
    satir(DIL === "tr" ? "Durum" : "Status", esc(m.durum) + `<div class="sonuk" style="font-size:11px">${esc(m.durum_ayrinti || "")}</div>`) +
    satir(DIL === "tr" ? "Veri seti" : "Dataset",
          `${esc(vs.nokta)} ${esc(DIL === "tr" ? "nokta" : "points")}` +
          (vs.nokta_karisim_dahil !== vs.nokta ? ` · ${esc(vs.nokta_karisim_dahil)} ${esc(DIL === "tr" ? "karışım dahil" : "incl. mixtures")}` : "") +
          (adlar ? `<div class="sonuk" style="font-size:11px">${adlar}</div>` : "")) +
    satir(DIL === "tr" ? "Uzayda kullanım" : "Use in space", esc(m.uzayda_kullanim || "–")) +
    (m._kaynak === "kullanici" ? satir(DIL === "tr" ? "Ekleyen" : "Added by", esc((m.ekleyen || "–") + " · " + String(m.zaman || "").replace("T", " ")) +
      `<div class="sonuk" style="font-size:11px">${esc(m.onay === "onayli"
        ? (DIL === "tr" ? "Onaylı: tahminde tanınır; yalnız yakıt türü, numune, kalınlık ve benzer malzeme kullanılır; motor ağırlığı 0." : "Approved: recognized; only fuel type, sample, thickness and surrogate are used; engine weight 0.")
        : (DIL === "tr" ? "Onaysız: hiçbir hesaba girmez." : "Unapproved: enters no calculation."))}</div>`) : "") +
    ozSatir.join("") +
    (m.notlar ? satir(DIL === "tr" ? "Not" : "Note", esc(m.notlar)) : "") +
    `</tbody></table></div>` +
    `<p class="sonuk" style="font-size:11px;margin-top:10px">${esc(DIL === "tr"
      ? "Boş alan: kaynakta (NIST WebBook, SFPE El Kitabı, veri seti) bulunamadı. Kütüphane modele ve motor kalibrasyonuna girmez."
      : "Empty field: not found in the sources (NIST WebBook, SFPE Handbook, dataset). The library does not enter the model or engine calibration.")}</p>`;
  const kul = m._kaynak === "kullanici";
  const dugmeler = [{ ad: T("genel.kapat"), sinif: "birincil" }];
  if (kul) {
    dugmeler.unshift({ ad: T("genel.sil"), sinif: "tehlike", islev: async () => {
      await API.kullaniciMalzemeSil(m.id); MLZ = null; kutuphaneCiz(); Kabuk.bildir(DIL === "tr" ? "Kullanıcı malzemesi silindi." : "User material deleted."); } });
    dugmeler.unshift({ ad: DIL === "tr" ? "Düzenle" : "Edit", islev: () => { setTimeout(() => kullaniciMalzemeFormu(m.ad, null, m), 30); } });
    if (m.onay !== "onayli") dugmeler.unshift({ ad: DIL === "tr" ? "Onayla" : "Approve", sinif: "birincil", islev: async () => {
      await API.kullaniciMalzemeOnayla(m.id); MLZ = null; kutuphaneCiz();
      Kabuk.bildir(DIL === "tr" ? "Onaylandı: artık tahminde tanınır (motor ağırlığı 0)." : "Approved: now recognized in predictions (engine weight 0).", "basari"); } });
  }
  Kabuk.pencereAc({ baslik: m.ad + (m.ad_en && m.ad_en !== m.ad ? " — " + m.ad_en : "") +
                    (kul ? (DIL === "tr" ? " (kullanıcı malzemesi)" : " (user material)") : ""), ic, dugmeler });
}

/* ---------------------------------------------------------------- kullanıcı malzemesi formu (9. madde) */
const MLZ_FORM_OZ = [   // [alan, TR, EN, birim, LLM öneri anahtarı]
  ["yogunluk", "Yoğunluk", "Density", "kg/m³", "yogunluk_kg_m3"],
  ["isil_deger", "Isıl değer", "Heat of combustion", "MJ/kg", "isil_deger_MJ_kg"],
  ["kaynama_K", "Kaynama noktası", "Boiling point", "K", "kaynama_K"],
  ["LOI", "LOI", "LOI", "%", "LOI_yuzde"],
  ["parlama_noktasi_K", "Parlama noktası", "Flash point", "K", "parlama_noktasi_K"],
  ["LFL", "Alt yanma sınırı (LFL)", "LFL", "% hacim", "LFL_yuzde"],
  ["UFL", "Üst yanma sınırı (UFL)", "UFL", "% hacim", "UFL_yuzde"],
];
const LLM_ETIKET = () => `<span class="etiket uyari" style="margin-left:6px">${esc(DIL === "tr" ? "LLM önerisi, doğrulanmadı" : "LLM suggestion, unverified")}</span>`;

function kullaniciMalzemeFormu(ad, oneri, mevcut) {
  const o = oneri || {}, sn = o.siniflandirma || {}, oz = o.ozellikler || {}, m = mevcut || {};
  const llm = (v) => (v != null && v !== "" ? LLM_ETIKET() : "");
  const v0 = m.varsayilan || {};
  const deger = {
    ad: m.ad || o.ad_tr || ad || "", ad_en: m.ad_en || o.ad_en || "",
    es: (m.es_anlamlilar || o.es_anlamlilar || []).join(", "),
    yakit: m.yakit_turu || sn.yakit_turu || "", numune: v0.numune_tipi || sn.numune_tipi || "",
    kal: v0.kalinlik_veya_cap_mm != null ? v0.kalinlik_veya_cap_mm : "",
    benzer: m.motor_benzeri || sn.benzer_malzeme || "", gerekce: m.eslesme_gerekce || sn.gerekce || "",
    uzay: m.uzayda_kullanim || o.uzayda_kullanim || "",
  };
  const secim = (id, liste, sec) => `<select class="giris" id="${id}">` +
    liste.map((x) => { const [v, a] = Array.isArray(x) ? x : [x, x]; return `<option value="${esc(v)}"${String(v) === String(sec) ? " selected" : ""}>${esc(a)}</option>`; }).join("") + `</select>`;
  const adlar = (S.malzemeler || []).slice();
  if (deger.benzer && adlar.indexOf(deger.benzer) < 0) adlar.push(deger.benzer);    // LLM'in önerdiği (risk modelinin bildiği) ad
  const benzerler = [["", DIL === "tr" ? "(motor yok — yalnız risk modeli)" : "(no engine — risk model only)"]].concat(
    adlar.sort().map((x) => [x, x]));
  const satir = (et, girdi, ek) => `<tr><th style="width:30%">${esc(et)}</th><td>${girdi}${ek || ""}</td></tr>`;
  const durumNotu = !oneri ? "" :
    o.durum === "baglanti_yok" ? `<div class="uyari-satir"><span>${esc(DIL === "tr" ? "İnternet / SI'e ulaşılamadı; form boş açıldı, elle doldurun." : "Internet / SI not reachable; the form is empty, fill it in manually.")}` + (o.sebep ? ` <span class="sonuk">(${esc(o.sebep)})</span>` : "") + `</span></div>`
    : o.durum === "reddedildi" ? `<div class="uyari-satir"><span>${esc(DIL === "tr" ? "LLM bunu bir malzeme olarak tanımadı; adı kontrol edin ya da formu elle doldurun." : "The LLM did not recognize this as a material; check the name or fill in the form manually.")}` + (o.sebep ? ` <span class="sonuk">(${esc(o.sebep)})</span>` : "") + `</span></div>`
    : o.durum === "kabul" ? `<div class="uyari-satir bilgi"><span>${esc(DIL === "tr" ? "Form LLM önerisiyle dolduruldu. İşaretli alanlar doğrulanmadı; düzeltin, sonra onaylayın. Onaysız kayıt hiçbir hesaba girmez." : "The form was filled with an LLM suggestion. Marked fields are unverified; correct them, then approve. Unapproved records enter no calculation.")}</span></div>`
    : o.durum === "mesgul" ? `<div class="uyari-satir"><span>${esc(o.sebep || "")}</span></div>`
    : o.durum === "hata" ? `<div class="uyari-satir"><span>${esc(DIL === "tr" ? "Öneri alınırken uygulama hatası; form boş açıldı." : "Application error while fetching the suggestion; the form is empty.")} <span class="sonuk">(${esc(o.sebep || "")})</span></span></div>` : "";
  const ic = durumNotu +
    `<div class="tablo-kap" style="border:0;margin-top:8px"><table class="veri"><tbody>` +
    satir(DIL === "tr" ? "Ad *" : "Name *", `<input class="giris" id="kmAd" value="${esc(deger.ad)}" style="width:60%">` +
      ` <button class="dugme kucuk" id="kmOner">${esc(DIL === "tr" ? "LLM'den öner (~30 s)" : "Ask LLM (~30 s)")}</button>`) +
    satir(DIL === "tr" ? "İngilizce ad" : "English name", `<input class="giris" id="kmAdEn" value="${esc(deger.ad_en)}">`, llm(o.ad_en && !m.ad_en ? 1 : null)) +
    satir(DIL === "tr" ? "Eş anlamlılar (virgülle)" : "Synonyms (comma)", `<input class="giris" id="kmEs" value="${esc(deger.es)}" style="width:90%">`, llm(o.es_anlamlilar && !m.es_anlamlilar ? 1 : null)) +
    satir(DIL === "tr" ? "Yakıt türü *" : "Fuel type *", secim("kmYakit", [["", "—"], "kati", "sivi", "gaz"], deger.yakit), llm(!m.yakit_turu ? sn.yakit_turu : null)) +
    satir(DIL === "tr" ? "Numune tipi" : "Sample type", secim("kmNumune", [["", "—"]].concat(NUMUNE), deger.numune), llm(!v0.numune_tipi ? sn.numune_tipi : null)) +
    satir(DIL === "tr" ? "Kalınlık / çap (mm)" : "Thickness / diameter (mm)", `<input class="giris" id="kmKal" type="number" step="0.01" value="${esc(deger.kal)}">`) +
    satir(DIL === "tr" ? "Motorda benzer malzeme" : "Engine surrogate", secim("kmBenzer", benzerler, deger.benzer), llm(!m.motor_benzeri ? sn.benzer_malzeme : null)) +
    satir(DIL === "tr" ? "Eşleme gerekçesi" : "Mapping rationale", `<input class="giris" id="kmGerekce" value="${esc(deger.gerekce)}" style="width:90%">`) +
    satir(DIL === "tr" ? "Uzayda kullanım" : "Use in space", `<input class="giris" id="kmUzay" value="${esc(deger.uzay)}" style="width:90%">`) +
    MLZ_FORM_OZ.map(([k, tr, en, birim, ok]) => {
      const mv = (m.ozellikler || {})[k], ov = oz[ok];
      const v = mv ? mv.deger : ov != null ? ov : "";
      const kay = mv ? mv.kaynak : ov != null ? (DIL === "tr" ? "LLM önerisi, doğrulanmadı" : "LLM suggestion, unverified") : "";
      return satir((DIL === "tr" ? tr : en) + " (" + birim + ")",
        `<input class="giris" data-kmoz="${k}" data-kmllm="${mv ? (mv.llm_onerisi ? 1 : 0) : ov != null ? 1 : 0}" type="number" step="any" value="${esc(v)}" style="width:28%"> ` +
        `<input class="giris" data-kmkay="${k}" placeholder="${esc(DIL === "tr" ? "kaynak (zorunlu)" : "source (required)")}" value="${esc(kay)}" style="width:62%">`,
        llm(!mv && ov != null ? 1 : mv && mv.llm_onerisi ? 1 : null));
    }).join("") +
    `</tbody></table></div><div id="kmHata"></div>` +
    `<p class="sonuk" style="font-size:11px;margin-top:8px">${esc(DIL === "tr"
      ? "Onaysız kayıt hiçbir hesaba girmez. Onaylı kayıt tahminde tanınır ama yalnız yakıt türü, numune, kalınlık ve benzer malzeme kullanılır; motor ağırlığı 0 olur ve uyarı yazılır. Özellik sayıları yalnız gösterilir."
      : "Unapproved records enter no calculation. Approved records are recognized, but only fuel type, sample, thickness and surrogate are used; engine weight is 0 with a warning. Property numbers are display-only.")}</p>`;
  const topla = (ic) => {
    const al = (sel) => (ic.querySelector(sel) || {}).value || "";
    const ozellikler = {};
    ic.querySelectorAll("[data-kmoz]").forEach((el) => {
      const k = el.dataset.kmoz;
      if (el.value !== "") ozellikler[k] = { deger: el.value, kaynak: (ic.querySelector(`[data-kmkay="${k}"]`) || {}).value || "", llm_onerisi: el.dataset.kmllm === "1" };
    });
    return { id: m.id, ad: al("#kmAd").trim(), ad_en: al("#kmAdEn").trim(), es_anlamlilar: al("#kmEs").split(",").map((x) => x.trim()).filter(Boolean),
             yakit_turu: al("#kmYakit"), numune_tipi: al("#kmNumune"), kalinlik_veya_cap_mm: al("#kmKal"),
             motor_benzeri: al("#kmBenzer"), eslesme_gerekce: al("#kmGerekce"), uzayda_kullanim: al("#kmUzay"),
             benzer_llm: !m.motor_benzeri && !!sn.benzer_malzeme && al("#kmBenzer") === sn.benzer_malzeme,
             llm_onerisi_kullanildi: !!(oneri && oneri.durum === "kabul"), ozellikler };
  };
  const kaydet = (onay) => async (ic) => {
    const r = await API.kullaniciMalzemeKaydet(topla(ic), onay);
    if (r.hatalar) { ic.querySelector("#kmHata").innerHTML = r.hatalar.map((x) => `<div class="uyari-satir"><span>${esc(x)}</span></div>`).join(""); return false; }
    MLZ = null; ktpGorunum = "malzemeler"; Kabuk.sekmeAc("kutuphane"); kutuphaneCiz();
    Kabuk.bildir(onay === "onayli" ? (DIL === "tr" ? "Kaydedildi ve onaylandı." : "Saved and approved.") : (DIL === "tr" ? "Taslak kaydedildi (onaysız)." : "Draft saved (unapproved)."), "basari");
    return true;
  };
  Kabuk.pencereAc({
    baslik: m.id ? (DIL === "tr" ? "Kullanıcı malzemesini düzenle" : "Edit user material") : (DIL === "tr" ? "Kullanıcı malzemesi ekle" : "Add user material"),
    ic,
    dugmeler: [{ ad: T("genel.iptal") },
               { ad: DIL === "tr" ? "Taslak kaydet (onaysız)" : "Save draft (unapproved)", islev: kaydet("onaysiz") },
               { ad: DIL === "tr" ? "Onayla ve kaydet" : "Approve and save", sinif: "birincil", islev: kaydet("onayli") }],
    hazir: (ic) => {
      const b = ic.querySelector("#kmOner");
      if (b) b.addEventListener("click", async () => {
        const a = ic.querySelector("#kmAd").value.trim();
        if (!a) return;
        b.disabled = true; b.textContent = DIL === "tr" ? "LLM düşünüyor… (~30 s)" : "LLM thinking… (~30 s)";
        let r; try { r = await API.malzemeOner(a); } catch (e) { r = { durum: "hata", sebep: e.message }; }
        kullaniciMalzemeFormu(a, r, null);
      });
    },
  });
}

async function malzemelerCiz() {
  if (MLZ === null) {
    try { MLZ = await API.malzemeKutuphanesi(); } catch (e) { MLZ = { malzemeler: [], hata: e.message }; }
  }
  const ara = ktpAra.toLocaleLowerCase(DIL === "tr" ? "tr-TR" : "en-US");
  const tum = MLZ.malzemeler || [];
  const liste = tum.filter((m) => (!mlzTur || m.yakit_turu === mlzTur) && (!mlzKat || m.kategori === mlzKat) && (!ara ||
    [m.id, m.ad, m.ad_en, (m.es_anlamlilar || []).join(" "), m.durum, m.motor_benzeri, m.uzayda_kullanim, m.kategori].join(" ")
      .toLocaleLowerCase(DIL === "tr" ? "tr-TR" : "en-US").indexOf(ara) >= 0));
  const turDugme = (t, ad) => `<button class="dugme kucuk${mlzTur === t ? " birincil" : ""}" data-mlztur="${t}">${esc(ad)}</button>`;
  const kulSay = tum.filter((m) => m._kaynak === "kullanici").length;
  const katSay = {};
  tum.forEach((m) => { if (m.kategori) katSay[m.kategori] = (katSay[m.kategori] || 0) + 1; });
  const kategoriler = Object.entries(katSay).sort((a, b) => a[0].localeCompare(b[0], "tr"));
  return `<div class="sayfa-bas" style="margin-top:-4px"><span class="sonuk">${esc(liste.length)} / ${esc(tum.length)} ${esc(DIL === "tr" ? "malzeme" : "materials")}` +
    (kulSay ? ` · ${esc(kulSay)} ${esc(DIL === "tr" ? "kullanıcı" : "user")}` : "") + `</span>` +
    `<button class="dugme kucuk birincil" data-mlzekle="">${esc(DIL === "tr" ? "+ Malzeme ekle" : "+ Add material")}</button>` +
    `<span class="sag"><select class="giris" id="mlzKatSec"><option value="">${esc(DIL === "tr" ? "tüm kategoriler" : "all categories")}</option>` +
      kategoriler.map(([k, n]) => `<option value="${esc(k)}"${mlzKat === k ? " selected" : ""}>${esc(katAdi(k))} (${esc(n)})</option>`).join("") + `</select>` +
      `${turDugme("", DIL === "tr" ? "Tümü" : "All")}` +
    Object.entries(MLZ_TUR).map(([t, a]) => turDugme(t, mlzDil(a))).join("") + `</span></div>` +
    (MLZ.hata ? `<div class="bos">${esc(MLZ.hata)}</div>`
      : !liste.length ? `<div class="bos">${esc(DIL === "tr" ? "Eşleşen malzeme yok." : "No matching material.")}</div>`
      : `<div class="vaka-izgara">${liste.map(mlzKarti).join("")}</div>`);
}

function vakaKarti(v, topluluk) {
  return `<div class="vaka-kart" data-ac="${esc(v.id)}" data-kaynak="${topluluk ? "topluluk" : "yerel"}">` +
    `<div class="ust">` +
      (topluluk ? "" : `<input type="checkbox" class="krs-kutu" data-krs="${esc(v.id)}"${S.secKarsi.indexOf(v.id) >= 0 ? " checked" : ""} title="${esc(T("krs.karsilastir"))}">`) +
      `<h4>${esc(v.baslik)}</h4><span class="rozet ${ROZET_SINIF(v.risk_seviyesi)}">${esc(v.risk_seviyesi || "—")}</span></div>` +
    (v.aciklama ? `<div class="aciklama">${esc(v.aciklama)}</div>` : "") +
    `<div class="olcumler">` +
      `<span>g <b>${esc(gMetni(v.g))}</b></span>` +
      `<span>O₂ <b>%${esc(nf(v.oksijen, 1))}</b></span>` +
      `<span>p <b>${esc(nf(v.basinc, 1))}</b> kPa</span>` +
      `<span>${esc(DIL === "tr" ? "güven" : "conf.")} <b>${esc(nf(v.guven, 0))}</b></span>` +
    `</div>` +
    (v.etiketler && v.etiketler.length ? `<div class="etiketler">${v.etiketler.slice(0, 5).map((e) => `<span class="etiket">${esc(e)}</span>`).join("")}</div>` : "") +
    `<div class="ayak"><span>${esc(v.yazar || (DIL === "tr" ? "isimsiz" : "anonymous"))}</span>` +
      `<span>${esc((v.guncelleme || "").replace("T", " ").slice(0, 16))}</span>` +
      (v.yorum_sayisi ? `<span>${esc(v.yorum_sayisi)} ${esc(DIL === "tr" ? "yorum" : "comments")}</span>` : "") +
      `<span class="sag">` +
        (topluluk
          ? (v.kaynak === "github"
              ? `<button class="dugme kucuk" data-ghal="${esc(v.dosya)}">${esc(T("gh.al"))}</button>` +
                (v.adres ? `<button class="dugme kucuk" data-ghac="${esc(v.adres)}">${esc(T("gh.siteAc"))}</button>` : "")
              : `<button class="dugme kucuk" data-al="${esc(v.id)}">${esc(T("gh.al"))}</button>`)
          : `<button class="dugme kucuk" data-paylas="${esc(v.id)}">${esc(T("komut.paylasK"))}</button>` +
            `<button class="dugme kucuk tehlike" data-sil="${esc(v.id)}">${esc(T("genel.sil"))}</button>`) +
      `</span></div></div>`;
}

async function kutuphaneCiz() {
  const gorunumDugme = (g, ad) => `<button class="dugme kucuk${ktpGorunum === g ? " birincil" : ""}" data-ktpgor="${g}">${esc(ad)}</button>`;
  const gecis = `<span style="display:flex;gap:6px">${gorunumDugme("vakalar", DIL === "tr" ? "Vakalar" : "Cases")}` +
    `${gorunumDugme("malzemeler", DIL === "tr" ? "Malzemeler" : "Materials")}${gorunumDugme("ofm", DIL === "tr" ? "Ayrıntılı koşular" : "Detailed runs")}</span>`;
  if (ktpGorunum === "ofm") {
    const govde = await ofmKutuphaneCiz();
    Kabuk.ekranYaz("ek-kutuphane", `<div class="sayfa"><div class="sayfa-bas"><h2>${esc(DIL === "tr" ? "Ayrıntılı koşular (OpenFOAM)" : "Detailed runs (OpenFOAM)")}</h2>` + gecis + `</div>` + govde + `</div>`);
    return;
  }
  if (ktpGorunum === "malzemeler") {
    const govde = await malzemelerCiz();
    Kabuk.ekranYaz("ek-kutuphane", `<div class="sayfa"><div class="sayfa-bas"><h2>${esc(DIL === "tr" ? "Malzeme kütüphanesi" : "Material library")}</h2>` +
      gecis + `<span class="sag"><input class="giris" id="ktpAra" placeholder="${esc(T("genel.ara"))}" value="${esc(ktpAra)}"></span></div>` +
      govde + `</div>`);
    const a = $("#ktpAra");
    if (a) a.addEventListener("input", async () => { ktpAra = a.value; const p = a.selectionStart; await kutuphaneCiz(); const b = $("#ktpAra"); b.focus(); b.setSelectionRange(p, p); });
    const ks = $("#mlzKatSec");
    if (ks) ks.addEventListener("change", () => { mlzKat = ks.value; kutuphaneCiz(); });
    return;
  }
  const ara = ktpAra.toLocaleLowerCase(DIL === "tr" ? "tr-TR" : "en-US");
  const liste = S.vakalar.filter((v) => !ara ||
    [v.baslik, v.aciklama, v.malzeme, v.risk_seviyesi, (v.etiketler || []).join(" ")].join(" ")
      .toLocaleLowerCase(DIL === "tr" ? "tr-TR" : "en-US").indexOf(ara) >= 0);
  const ic = `<div class="sayfa"><div class="sayfa-bas"><h2>${esc(T("ktp.basligi"))}</h2>` + gecis +
    `<span class="sonuk">${esc(S.vakalar.length)} ${esc(DIL === "tr" ? "vaka" : "cases")}</span>` +
    `<span class="sag"><input class="giris" id="ktpAra" placeholder="${esc(T("genel.ara"))}" value="${esc(ktpAra)}">` +
    `<button class="dugme${S.secKarsi.length === 2 ? " birincil" : ""}" data-komut="karsilastir"${S.secKarsi.length < 1 ? " disabled" : ""}>` +
    `${esc(T("krs.karsilastir"))}${S.secKarsi.length ? " (" + S.secKarsi.length + ")" : ""}</button>` +
    `<button class="dugme" data-komut="ice">${esc(T("komut.ice"))}</button>` +
    `<button class="dugme" data-komut="klasor-vakalar">${esc(DIL === "tr" ? "Klasörü aç" : "Open folder")}</button></span></div>` +
    (!S.vakalar.length
      ? `<div class="bos"><b>${esc(T("ktp.bos"))}</b>${esc(T("ktp.bosAlt"))}</div>`
      : !liste.length ? `<div class="bos">${esc(DIL === "tr" ? "Eşleşen vaka yok." : "No matching case.")}</div>`
      : `<div class="vaka-izgara">${liste.map((v) => vakaKarti(v, false)).join("")}</div>`) +
    `</div>`;
  Kabuk.ekranYaz("ek-kutuphane", ic);
  const a = $("#ktpAra");
  if (a) a.addEventListener("input", () => { ktpAra = a.value; const p = a.selectionStart; kutuphaneCiz(); const b = $("#ktpAra"); b.focus(); b.setSelectionRange(p, p); });
}

async function vakaYukle(id, topluluk) {
  let paket;
  try {
    paket = topluluk ? await API.toplulukOku(id) : await API.vakaOku(id);
  } catch (e) { Kabuk.bildir(e.message, "hata"); return; }
  if (!paket) { Kabuk.bildir(DIL === "tr" ? "Vaka bulunamadı." : "Case not found.", "hata"); return; }

  const g = paket.girdi || {};
  S.girdi = {
    malzeme: g.malzeme, oksijen: g.oksijen, basinc: g.basinc, g: g.g,
    akis: g.akis == null ? 0 : g.akis, akisBilinmiyor: g.akis == null,
    kalinlik: g.kalinlik, numune_tipi: g.numune_tipi, yakit_turu: g.yakit_turu,
    akis_yonu: g.akis_yonu || "", seyreltici: g.seyreltici || "n2",
  };
  S.dokunuldu = { numune_tipi: g.numune_tipi != null, kalinlik: g.kalinlik != null, yakit_turu: g.yakit_turu != null };
  S.onayar = paket.onayar || "Özel";
  S.cozumHata = null; S.cozumHtml = null;
  S.sonuc = paket.sonuc && paket.sonuc.tahmin
    ? { kosul: g, tahmin: paket.sonuc.tahmin, oksijen_egrisi: paket.sonuc.oksijen_egrisi,
        harita: paket.sonuc.harita, akis_egrisi: paket.sonuc.akis_egrisi, yakin: paket.sonuc.yakin || [] }
    : null;
  S.llm = paket.llm_yorum ? { durum: "geldi", metin: paket.llm_yorum } : { durum: "yok", metin: null };
  S.sohbet.mesajlar = []; S.sohbet.kosul = null; S.sohbet.taslak = "";
  S.supurme = Object.assign({ parametre: "oksijen", bas: 14, son: 30, adim: 1, calisiyor: false, yuzde: 0 },
    paket.supurme ? { parametre: paket.supurme.parametre, bas: paket.supurme.bas,
                      son: paket.supurme.son, adim: paket.supurme.adim, sonuc: paket.supurme } : { sonuc: null });
  S.vakaId = topluluk ? null : paket.id;
  if (paket.sonuc && paket.sonuc.cozum_turu) { S.cozumTuru = paket.sonuc.cozum_turu; S.onTahmin = paket.sonuc.on_tahmin === true; }
  S.ayrintili = null; cozumTuruYaz();
  if (paket.sonuc && paket.sonuc.ayrintili && paket.sonuc.ayrintili.kosu) ayrintiliGeriYukle(paket.sonuc.ayrintili);
  S.baslik = paket.baslik || "";
  S.baslikOto = false;
  S.aciklama = paket.aciklama || "";
  S.etiketler = paket.etiketler || [];
  kirlet(false);
  S.mesajlar = [];
  if (S.sonuc) (S.sonuc.tahmin.uyarilar || []).forEach((u) => mesaj("uyari", u));
  mesaj("bilgi", (DIL === "tr" ? "Vaka açıldı: " : "Case opened: ") + S.baslik);

  dogrula();
  agacYenile();
  Kabuk.agacSec(S.sonuc ? "r-ozet" : "ortam");
  Kabuk.sekmeAc(S.sonuc ? "sonuclar" : "kurulum");
  if (S.sonuc) Kabuk.bildir(DIL === "tr" ? "Kayıtlı sonuç gösteriliyor. Güncel model için yeniden çözün." : "Showing a stored result. Re-solve for the current model.", "", 6000);
}

async function vakaKaydet() {
  if (!S.sonuc) { Kabuk.bildir(DIL === "tr" ? "Önce çözün." : "Solve first.", "hata"); return; }
  try {
    const ozet = await API.vakaKaydet({
      id: S.vakaId, girdi: S.sonuc.kosul,
      sonuc: { cozum_turu: S.cozumTuru, on_tahmin: S.onTahmin, ayrintili: S.ayrintili ? { id: S.ayrintili.id, kosu: S.ayrintili.kosu, durum: S.ayrintili.durum } : null,
               tahmin: S.sonuc.tahmin, oksijen_egrisi: S.sonuc.oksijen_egrisi,
               harita: S.sonuc.harita, akis_egrisi: S.sonuc.akis_egrisi, yakin: S.sonuc.yakin },
      baslik: S.baslik, aciklama: S.aciklama, etiketler: S.etiketler,
      onayar: S.onayar, llm_yorum: S.llm.durum === "geldi" ? S.llm.metin : null,
      render: S.renderSecili, supurme: S.supurme.sonuc,
    });
    S.vakaId = ozet.id;
    S.baslik = ozet.baslik;
    S.etiketler = ozet.etiketler;
    kirlet(false);
    await vakalariTazele();
    Kabuk.bildir(DIL === "tr" ? "Vaka kütüphaneye kaydedildi." : "Case saved to the library.", "basari");
    mesaj("bilgi", (DIL === "tr" ? "Kaydedildi: " : "Saved: ") + ozet.baslik);
  } catch (e) {
    Kabuk.bildir(e.message, "hata");
  }
}

async function vakalariTazele() {
  try {
    S.vakalar = await API.vakaListesi();
  } catch (e) {}
  if (Kabuk.aktif() === "kutuphane") kutuphaneCiz();
  if (Kabuk.aktif() === "topluluk") toplulukCiz();
  if (Kabuk.aktif() === "baslangic") baslangicCiz();
}

/* ---------------------------------------------------------------- PENCERELER */
function profilGoster() {
  const p = S.profil || {};
  $("#profilAd").textContent = p.ad || T("genel.profilYok");
  $("#avatar").textContent = (p.ad || "?").trim().charAt(0).toLocaleUpperCase(DIL === "tr" ? "tr-TR" : "en-US") || "?";
  Kabuk.durum("dSurum", "v" + S.surum + (p.ad ? " · " + p.ad : ""));
}

function hakkindaPenceresi() {
  Kabuk.pencereAc({
    baslik: T("komut.hakkinda"),
    ic: `<div style="display:flex;gap:18px;align-items:flex-start">` +
      `<img src="brand/logo-round-128.png" width="72" height="72" style="border-radius:50%">` +
      `<div><h3 style="font-size:18px">AHUT <span class="flare">FLARE</span> <span class="sonuk" style="font-size:12px">v${esc(S.surum)}</span></h3>` +
      `<div class="acilim" style="margin:3px 0 9px">Fire Learning, Analysis &amp; Research Engine</div>` +
      `<p style="line-height:1.65;font-size:12.5px;max-width:560px">${esc(T("bas.ozet"))}</p>` +
      `<p style="line-height:1.65;font-size:12.5px">${esc(DIL === "tr" ? "AHUT — Ankara Havacılık ve Uzay Teknolojileri Hackathon Takımı" : "AHUT — Ankara Aerospace Technologies Hackathon Team")}<br>` +
      `NASA Space Apps Challenge 2026<br>${esc(DIL === "tr" ? "Lisans" : "License")}: MIT</p>` +
      `<p class="sonuk" style="font-size:11.5px;line-height:1.6">Python ${esc((S.sistem || {}).python || "")} · scikit-learn · pywebview<br>` +
      `${esc(DIL === "tr" ? "Çevrimdışı çalışır; yapay zeka yorumu dışında internet kullanmaz." : "Works offline; uses the internet only for AI commentary.")}</p>` +
      `</div></div>`,
    dugmeler: [{ ad: T("genel.kapat"), sinif: "birincil" }],
  });
}

function kisayolPenceresi() {
  const k = [["F8", T("komut.coz")], ["F5", T("komut.sunum")], ["F11", T("komut.tamekran")],
             ["Ctrl + N", T("komut.yeni")], ["Ctrl + S", T("komut.kaydet")], ["Ctrl + O", T("komut.ice")],
             ["Ctrl + 1…4", DIL === "tr" ? "Sekmeler" : "Tabs"], ["Esc", DIL === "tr" ? "Pencereyi kapat" : "Close dialog"]];
  Kabuk.pencereAc({
    baslik: T("komut.kisayollar"),
    ic: `<table class="veri">${k.map((p) => `<tr><td style="width:130px"><kbd class="tek">${esc(p[0])}</kbd></td><td>${esc(p[1])}</td></tr>`).join("")}</table>`,
    dugmeler: [{ ad: T("genel.kapat"), sinif: "birincil" }],
  });
}

function jsonPenceresi() {
  if (!S.sonuc) return Kabuk.bildir(DIL === "tr" ? "Önce çözün." : "Solve first.", "hata");
  const metin = JSON.stringify({ girdi: S.sonuc.kosul, tahmin: S.sonuc.tahmin }, null, 2);
  Kabuk.pencereAc({
    baslik: "JSON",
    ic: `<pre class="tek" style="margin:0;white-space:pre-wrap;line-height:1.5;font-size:11.5px">${esc(metin)}</pre>`,
    dugmeler: [{ ad: T("genel.kapat"), sinif: "birincil" }],
  });
}

/* ---------------------------------------------------------------- RAPOR */
/* Rapor ayrı bir HTML belgesidir (tema değişkenleri yok, beyaz kağıt): grafikteki var(--x) renkleri
   açık temanın sabit değerleriyle değiştirilir. Bilinmeyen değişken siyaha düşer. */
const RAPOR_RENK = { vurgu: "#0066cc", sonuk: "#505050", yazi: "#1e1e1e", cizgi: "#c8c8c8", "cizgi-acik": "#a8a8a8",
  yesil: "#2e9e4f", sari: "#e0b000", turuncu: "#e46c0a", kirmizi: "#c00000", gri: "#8c8c8c",
  "g-seri2": "#c05000", "g-yanar": "#c00000", "g-sondu": "#2e7d32", "g-isaret": "#ffffff", "g-hale": "#000000",
  "panel-ic": "#ffffff", panel: "#f0f0f0" };
const raporRenkleri = (svg) => svg.replace(/var\(--([a-z0-9-]+)\)/g, (m, ad) => RAPOR_RENK[ad] || "#000");
function raporHtml() {
  if (!S.sonuc) return null;
  const t = S.sonuc.tahmin, k = S.sonuc.kosul, g = t.guven || {};
  const satir = (a, b) => `<tr><th>${esc(a)}</th><td>${b}</td></tr>`;
  return `<!doctype html><html lang="${DIL}"><head><meta charset="utf-8"><title>${esc(S.baslik || "AHUT")}</title>
<style>
body{font:14px/1.6 "Segoe UI",system-ui,sans-serif;color:#10203f;background:#fff;margin:0;padding:34px}
.kap{max-width:980px;margin:0 auto}h1{font-size:23px;margin:0 0 4px}h2{font-size:15px;margin:26px 0 9px;
text-transform:uppercase;letter-spacing:1px;color:#55668d;border-bottom:1px solid #d7e0f0;padding-bottom:5px}
table{border-collapse:collapse;width:100%;margin-bottom:10px}th,td{text-align:left;padding:6px 9px;border-bottom:1px solid #e6ecf7}
th{width:230px;color:#55668d;font-weight:600}.rozet{display:inline-block;padding:2px 11px;border-radius:4px;font-weight:700;color:#fff}
.u{background:#fff8e6;border:1px solid #f0c75a;padding:7px 11px;border-radius:5px;margin-bottom:6px}
.ust{display:flex;gap:16px;align-items:center;border-bottom:2px solid #0a378d;padding-bottom:14px}
.ayak{margin-top:30px;border-top:1px solid #d7e0f0;padding-top:11px;font-size:11.5px;color:#7a88a8}
svg{max-width:100%;height:auto}.g{margin:12px 0}
</style></head><body><div class="kap">
<div class="ust"><img src="brand/logo-round-128.png" width="58" height="58" style="border-radius:50%">
<div><h1>${esc(S.baslik || "AHUT FLARE")}</h1>
<div style="color:#55668d">AHUT FLARE v${esc(S.surum)} · ${esc(new Date().toLocaleString(DIL === "tr" ? "tr-TR" : "en-US"))}${S.profil.ad ? " · " + esc(S.profil.ad) : ""}</div></div></div>
${S.aciklama ? `<p>${esc(S.aciklama)}</p>` : ""}
<h2>${esc(DIL === "tr" ? "Sonuç" : "Result")}</h2><table>
${satir(T("sonuc.riskSeviyesi"), `<span class="rozet" style="background:${t.risk_seviyesi === "DÜŞÜK" ? "#108b61" : t.risk_seviyesi === "ORTA" ? "#a97a00" : t.risk_seviyesi === "YÜKSEK" ? "#c25f07" : "#cc1b29"}">${esc(t.risk_seviyesi)}</span>`)}
${satir(T("sonuc.yanmaIhtimali"), `%${esc(pct(t.yanma_ihtimali, 1))} ± ${esc(pct(t.belirsizlik, 1))}`)}
${satir(T("sonuc.sonmeSiniri"), t.sonme_siniri == null ? esc(T("genel.bulunamadi")) : "%" + esc(nf(t.sonme_siniri, 2)) + " O₂")}
${satir(T("sonuc.guvenlikKatsayisi"), t.guvenlik_katsayisi == null ? esc(T("genel.hesaplanamadi")) : esc(nf(t.guvenlik_katsayisi, 2)))}
${satir(T("sonuc.guvenSkoru"), esc(nf(g.skor, 0)) + " / 100")}
</table>
<h2>${esc(DIL === "tr" ? "Girdiler" : "Inputs")}</h2><table>
${Object.keys(k).map((a) => satir(a, k[a] == null ? `<i>${esc(T("genel.bilinmiyor"))}</i>` : esc(String(k[a])))).join("")}
</table>
<h2>${esc(T("sonuc.uyarilar"))}</h2>
${(t.uyarilar || []).length ? t.uyarilar.map((u) => `<div class="u">${esc(u)}</div>`).join("") : `<p>${esc(DIL === "tr" ? "Uyarı yok." : "No warnings.")}</p>`}
${S.sonuc.oksijen_egrisi ? `<h2>${esc(T("agac.oksijen"))}</h2><div class="g">${raporRenkleri(oksijenCiz(S.sonuc.oksijen_egrisi, { ortam: [k.oksijen] }))}</div>` : ""}
${S.llm.durum === "geldi" ? `<h2>${esc(T("agac.llm"))}</h2><pre style="white-space:pre-wrap;font:inherit;background:#f6f9fe;padding:13px;border-radius:6px">${esc(S.llm.metin)}</pre>` : ""}
<div class="ayak">${esc(DIL === "tr"
  ? "Bu rapor AHUT FLARE tarafından üretilmiştir. Sonuçlar model tahminidir; güvenlik payı eklenmemiştir ve resmî bir malzeme kabul belgesi yerine geçmez."
  : "Generated by AHUT FLARE. The results are model estimates; no safety margin is applied and this does not replace a formal material acceptance certificate.")}</div>
</div></body></html>`;
}

/* ---------------------------------------------------------------- KOMUTLAR */
async function komut(ad, el) {
  switch (ad) {
    case "yeni": yeniVaka(); break;
    case "coz": await coz(); break;
    case "llm": await llmIste(); break;
    case "sohbet-gonder": await sohbetGonder(); break;
    case "sohbet-temizle": S.sohbet.mesajlar = []; S.sohbet.kosul = null; sohbetYenile(true); break;
    case "sohbet-sina": await sohbetErisimSina(true); sohbetYenile(true); break;
    case "kaydet": await vakaKaydet(); break;
    case "ac": case "git-kutuphane": Kabuk.sekmeAc("kutuphane"); kutuphaneCiz(); break;
    case "git-topluluk": Kabuk.sekmeAc("topluluk"); toplulukTazele(true); break;
    case "git-baslangic": Kabuk.sekmeAc("baslangic"); baslangicCiz(); break;
    case "git-sonuclar": Kabuk.agacSec("r-ozet"); Kabuk.sekmeAc("sonuclar"); break;
    case "git-malzeme": Kabuk.sekmeAc("kurulum"); Kabuk.agacSec("malzeme"); break;
    case "ice":
      try {
        const r = await API.vakaIceAktar();
        if (!r.iptal) {
          await vakalariTazele();
          Kabuk.bildir((r.eklenen || []).length + (DIL === "tr" ? " vaka içe aktarıldı." : " case(s) imported."), "basari");
          (r.hatalar || []).forEach((h) => mesaj("hata", h));
          Kabuk.sekmeAc("kutuphane"); kutuphaneCiz();
        }
      } catch (e) { Kabuk.bildir(e.message, "hata"); }
      break;
    case "disa":
      if (!S.vakaId) { await vakaKaydet(); }
      if (!S.vakaId) break;
      try {
        const r = await API.vakaDisaAktar(S.vakaId);
        if (!r.iptal) Kabuk.bildir((DIL === "tr" ? "Kaydedildi: " : "Saved: ") + r.yol, "basari", 7000);
      } catch (e) { Kabuk.bildir(e.message, "hata"); }
      break;
    case "rapor": {
      const h = raporHtml();
      if (!h) return Kabuk.bildir(DIL === "tr" ? "Önce çözün." : "Solve first.", "hata");
      try {
        const r = await API.raporKaydet(h, S.baslik || "ahut_rapor");
        if (!r.iptal) Kabuk.bildir((DIL === "tr" ? "Rapor kaydedildi: " : "Report saved: ") + r.yol, "basari", 7000);
      } catch (e) { Kabuk.bildir(e.message, "hata"); }
      break;
    }
    case "paylas": await paylas(); break;
    case "gh-tazele": await toplulukTazele(true); break;
    case "gh-site": {
      const a = await ghAyarAl();
      if (a.site) API.baglantiAc(a.site); else ghKurulumPenceresi();
      break;
    }
    case "json": jsonPenceresi(); break;
    case "karsilastir": await karsilastir(); break;
    case "supur": await supur(); break;
    case "klasor-veri": API.klasorGoster("veri"); break;
    case "klasor-render": API.klasorGoster("render"); break;
    case "ofm-kos": ofmKosDialog(); break;
    case "klasor-vakalar": API.klasorGoster("vakalar"); break;
    case "profil-duzenle": profilPenceresi(); break;
    case "hakkinda": hakkindaPenceresi(); break;
    case "kisayollar": kisayolPenceresi(); break;
    case "tema": temaDegistir(); break;
    case "tema-acik": temaDegistir("acik"); break;
    case "tema-koyu": temaDegistir("koyu"); break;
    case "sunum": sunumDegistir(); break;
    case "tamekran": API.tamEkran(); break;
    case "panel-sifirla": Kabuk.duzenSifirla(); break;
    case "sifirla": yeniVaka(); break;
    case "onayar-iss": onayarUygula(ONAYARLAR[1]); Kabuk.sekmeAc("kurulum"); break;
    case "onayar-mars": onayarUygula(ONAYARLAR[3]); Kabuk.sekmeAc("kurulum"); break;
    case "onayar-ay": onayarUygula(ONAYARLAR[2]); Kabuk.sekmeAc("kurulum"); break;
    case "ornek-iss": onayarUygula(ONAYARLAR[1]); S.girdi.malzeme = "pmma"; Kabuk.sekmeAc("kurulum"); await cozHizli(); break;
    case "ornek-mars": onayarUygula(ONAYARLAR[3]); S.girdi.malzeme = "pmma"; Kabuk.sekmeAc("kurulum"); await cozHizli(); break;
    case "birim": {
      const p = el.dataset.birim.split(":");
      S.ayarlar.birimler[p[0]] = p[1];
      await API.ayarYaz({ birimler: S.ayarlar.birimler });
      birimIsaretle();
      ayrintiCiz();
      gorselYenile();
      break;
    }
    case "cikis": API.cikis(); break;
    default: break;
  }
}

function yeniVaka() {
  S.girdi = { malzeme: "pmma", oksijen: 21, basinc: 101.3, g: 1e-4, akis: 0, akisBilinmiyor: true,
              kalinlik: null, numune_tipi: null, yakit_turu: null, akis_yonu: "", seyreltici: "n2" };
  S.dokunuldu = { numune_tipi: false, kalinlik: false, yakit_turu: false };
  S.onayar = "ISS";
  S.sonuc = null; S.llm = { durum: "yok", metin: null }; S.ayrintili = null;
  S.sohbet.mesajlar = []; S.sohbet.kosul = null; S.sohbet.taslak = "";
  S.cozumHata = null; S.cozumHtml = null; S.sonSolveSure = null;
  S.vakaId = null; S.baslik = ""; S.aciklama = ""; S.etiketler = [];
  S.supurme = { parametre: "oksijen", bas: 14, son: 30, adim: 1, sonuc: null, calisiyor: false, yuzde: 0 };
  S.mesajlar = []; mesajCiz();
  kirlet(false);
  dogrula();
  agacYenile();
  Kabuk.agacSec("ortam");
  Kabuk.sekmeAc("kurulum");
  Kabuk.durum("dSure", "");
}

/* Görünüm: "acik" (varsayılan, ANSYS klasik) | "koyu" (eski lacivert palet) */
function temaUygula() {
  const koyu = S.ayarlar.gorunum === "koyu";
  document.documentElement.dataset.tema = koyu ? "koyu" : "acik";
  $("#isKoyu").textContent = koyu ? "✓" : "";
  if ($("#isAcik")) $("#isAcik").textContent = koyu ? "" : "✓";
}

function temaDegistir(hedef) {
  S.ayarlar.gorunum = hedef || (S.ayarlar.gorunum === "koyu" ? "acik" : "koyu");
  temaUygula();
  API.ayarYaz({ gorunum: S.ayarlar.gorunum });
  gorselYenile();
}

function sunumDegistir() {
  document.body.classList.toggle("sunum");
  gorselYenile();
}

function birimIsaretle() {
  $$("[data-birim]").forEach((b) => {
    const p = b.dataset.birim.split(":");
    const i = b.querySelector(".isaret");
    if (i) i.textContent = S.ayarlar.birimler[p[0]] === p[1] ? "✓" : "";
  });
  Kabuk.durum("dBirim", (DIL === "tr" ? "Birimler: " : "Units: ") + S.ayarlar.birimler.basinc + " · " + S.ayarlar.birimler.akis + " · %O₂");
}

/* ---------------------------------------------------------------- AÇILIŞ */
async function baslat() {
  Kabuk.menuleriKur(komut);
  /* istenen: eski sekme adı (kurulum / cozum / sonuclar) — hepsi tek çalışma ekranına yönlenir */
  Kabuk.sekmeKur((ad, istenen) => {
    if (ad === "baslangic") baslangicCiz();
    if (ad === "kutuphane") kutuphaneCiz();
    if (ad === "topluluk") toplulukTazele(S.toplulukBilgi ? false : true);
    if (ad === "calisma") {
      const s = Kabuk.agacSecili() || "";
      const sonucta = s.indexOf("r-") === 0;
      if (istenen === "cozum") Kabuk.agacSec("cozum");
      else if (istenen === "kurulum" && sonucta) Kabuk.agacSec("ortam");
      else if (istenen === "sonuclar" && !sonucta && S.sonuc) Kabuk.agacSec("r-ozet");
      else gorselYenile();
    }
  });
  Kabuk.agacKur(dugumSecildi);
  Kabuk.gorselOnekKur((baslik) => sonucBlogu(Kabuk.agacSecili() || "", baslik));
  Kabuk.bolucuKur();
  Kabuk.altKur();
  Kabuk.pencereKur();
  Kabuk.altSec("sistem");

  document.addEventListener("click", (e) => {
    const d = e.target.closest("[data-dis]");
    if (d) { e.preventDefault(); API.baglantiAc(d.dataset.dis); return; }
    const sv = e.target.closest("[data-vaka]");
    if (sv) { vakaYukle(sv.dataset.vaka); return; }
    const krs = e.target.closest("[data-krs]");
    if (krs) {
      e.stopPropagation();
      const id = krs.dataset.krs, i = S.secKarsi.indexOf(id);
      if (i >= 0) S.secKarsi.splice(i, 1);
      else { S.secKarsi.push(id); if (S.secKarsi.length > 2) S.secKarsi.shift(); }
      kutuphaneCiz();
      return;
    }
    const tg = e.target.closest("[data-topgor]");
    if (tg) { topGorunum = tg.dataset.topgor; toplulukCiz(); return; }
    const tk = e.target.closest("[data-tvkomut]");
    if (tk) { tvKomut(tk.dataset.tvkomut); return; }
    const tvon = e.target.closest("[data-tvonay]"), tvre = e.target.closest("[data-tvred]");
    if (tvon || tvre) {
      e.stopPropagation();
      if (!TV.moderatorAd.trim()) { Kabuk.bildir(DIL === "tr" ? "Moderatör adı zorunlu." : "Moderator name required.", "hata"); return; }
      (tvon ? API.tvOnayla(tvon.dataset.tvonay, TV.moderatorAd) : API.tvReddet(tvre.dataset.tvred, TV.moderatorAd, DIL === "tr" ? "moderatör kararı" : "moderator decision"))
        .then((r) => { if (r && r.hata) Kabuk.bildir(r.hata, "hata"); tvTazele(); });
      return;
    }
    const tvs = e.target.closest("[data-tvsatir]");
    if (tvs) { tvAyrinti(tvs.dataset.tvsatir); return; }
    const kgor = e.target.closest("[data-ktpgor]");
    if (kgor) { ktpGorunum = kgor.dataset.ktpgor; kutuphaneCiz(); return; }
    const mtur = e.target.closest("[data-mlztur]");
    if (mtur) { mlzTur = mtur.dataset.mlztur; kutuphaneCiz(); return; }
    const mekle = e.target.closest("[data-mlzekle]");
    if (mekle) {
      e.stopPropagation();
      const ad = mekle.dataset.mlzekle || "";
      kullaniciMalzemeFormu(ad, null, null);
      if (ad) setTimeout(() => { const b = document.querySelector("#kmOner"); if (b) b.click(); }, 60);   // çözümden geldi: öneriyi hemen iste
      return;
    }
    const mlz = e.target.closest("[data-malzeme]");
    if (mlz) { mlzAyrinti(mlz.dataset.malzeme, mlz.dataset.mlzkaynak); return; }
    const kart = e.target.closest("[data-ac]");
    const al = e.target.closest("[data-al]");
    const sil = e.target.closest("[data-sil]");
    const pay = e.target.closest("[data-paylas]");
    if (al) { e.stopPropagation(); API.toplulukta(al.dataset.al).then(() => { vakalariTazele(); Kabuk.bildir(T("gh.alindi"), "basari"); }); return; }
    const ghal = e.target.closest("[data-ghal]");
    if (ghal) {
      e.stopPropagation();
      API.githubAl(ghal.dataset.ghal).then((r) => {
        if (r.hata) return Kabuk.bildir(r.hata, "hata");
        vakalariTazele();
        Kabuk.bildir(T("gh.alindi"), "basari");
      });
      return;
    }
    const ghac = e.target.closest("[data-ghac]");
    if (ghac) { e.stopPropagation(); API.baglantiAc(ghac.dataset.ghac); return; }
    if (sil) {
      e.stopPropagation();
      Kabuk.pencereAc({
        baslik: T("genel.sil"),
        ic: `<p>${esc(DIL === "tr" ? "Bu vaka kalıcı olarak silinecek. Geri alınamaz." : "This case will be permanently deleted. This cannot be undone.")}</p>`,
        dugmeler: [{ ad: T("genel.iptal") }, { ad: T("genel.sil"), sinif: "tehlike", islev: async () => {
          await API.vakaSil(sil.dataset.sil);
          if (S.vakaId === sil.dataset.sil) S.vakaId = null;
          await vakalariTazele();
          Kabuk.bildir(DIL === "tr" ? "Vaka silindi." : "Case deleted.");
        } }],
      });
      return;
    }
    if (pay) { e.stopPropagation(); API.vakaDisaAktar(pay.dataset.paylas).then((r) => { if (!r.iptal) Kabuk.bildir((DIL === "tr" ? "Kaydedildi: " : "Saved: ") + r.yol, "basari", 7000); }); return; }
    if (kart) vakaYukle(kart.dataset.ac, kart.dataset.kaynak === "topluluk");
  });

  document.addEventListener("input", (e) => { if (e.target && e.target.id === "sohbetGiris") S.sohbet.taslak = e.target.value; });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target && e.target.id === "sohbetGiris") { e.preventDefault(); komut("sohbet-gonder"); return; }
    if (e.key === "F8") { e.preventDefault(); komut("coz"); }
    else if (e.key === "F5") { e.preventDefault(); sunumDegistir(); }
    else if (e.key === "F11") { e.preventDefault(); API.tamEkran(); }
    else if (e.ctrlKey && !e.shiftKey && e.key.toLowerCase() === "n") { e.preventDefault(); yeniVaka(); }
    else if (e.ctrlKey && e.key.toLowerCase() === "s") { e.preventDefault(); vakaKaydet(); }
    else if (e.ctrlKey && e.key.toLowerCase() === "o") { e.preventDefault(); komut("ice"); }
    else if (e.ctrlKey && e.key >= "1" && e.key <= "4") {
      e.preventDefault();
      const s = ["baslangic", "calisma", "kutuphane", "topluluk"][Number(e.key) - 1];
      Kabuk.sekmeAc(s);
    } else if (e.key === "Escape" && document.body.classList.contains("sunum")) sunumDegistir();
  });

  // malzeme varsayılanları (katı/sıvı/gaz dahil) motoru beklemeden yüklenir
  API.malzemeVarsayilanlari().then((v) => {
    if (v && Object.keys(v).length) { S.varsay = v; S.malzemeler = Object.keys(v); ayrintiCiz(); }
  }).catch(() => {});

  API.dinle("motor", (d) => {
    S.motor = d && d.durum ? d : S.motor;
    motorDurumGoster();
    dogrula();
    if (S.motor.durum === "hazir") {
      API.malzemeVarsayilanlari().then((v) => {
        S.varsay = v || {};
        S.malzemeler = Object.keys(S.varsay);
        if (!S.malzemeler.length) S.malzemeler = MALZEME_YEDEK.slice();
        ayrintiCiz();
      }).catch(() => {});
    }
    if (Kabuk.aktif() === "baslangic") baslangicCiz();
  });

  API.dinle("supurme", (d) => {
    if (!d || !S.supurme.calisiyor) return;
    S.supurme.yuzde = d.yuzde || 0;
    if ((Kabuk.agacSecili() || "") === "supurme") supurmeGorseli();
  });

  API.dinle("cozum", (d) => {
    if (!d) return;
    if (d.adim && d.adim !== "bitti") {
      Object.keys(S.adimDurum).forEach((a) => { if (S.adimDurum[a] === "calisiyor") S.adimDurum[a] = "bitti"; });
      if (S.adimDurum[d.adim] !== undefined) S.adimDurum[d.adim] = "calisiyor";
      const ad = (COZUM_ADIMLARI.find((p) => p[0] === d.adim) || [])[1];
      cozumEkraniCiz(d.yuzde || 0, ad ? T(ad) : "");
    }
  });

  /* Açılış verisi */
  let h = {};
  try { h = await API.hazir(); } catch (e) { console.error(e); }
  S.surum = h.surum || "1.0.0";
  S.sistem = h.sistem || {};
  S.ayarlar = Object.assign(S.ayarlar, h.ayarlar || {});
  S.profil = h.profil || {};
  S.motor = h.motor || S.motor;
  S.vakalar = h.vakalar || [];
  S.topluluk = h.topluluk || [];
  S.toplulukBilgi = { kaynak: "yerel", liste: S.topluluk };
  S.render = h.render || [];

  dilSec(S.ayarlar.dil || "tr");
  temaUygula();
  birimIsaretle();
  profilGoster();
  motorDurumGoster();

  $("#dilDugme").addEventListener("click", async () => {
    const yeni = DIL === "tr" ? "en" : "tr";
    S.ayarlar.dil = yeni;
    await API.ayarYaz({ dil: yeni });
    dilSec(yeni);
    yenidenCiz();
  });

  dogrula();
  agacYenile();
  Kabuk.agacSec("ortam");
  mesajCiz(); gunlukCiz();
  baslangicCiz();
  Kabuk.sekmeAc("baslangic");
  kirlet(false);

  if (h.acilis_dosyasi) {
    try { const r = await API.dosyaAc(h.acilis_dosyasi); await vakalariTazele(); if (r.ozet) vakaYukle(r.ozet.id); } catch (e) {}
  }

  tiklamaDenetimi();          // gizli bir katman tiklamalari yutuyor mu
  setInterval(islemciYokla, 1500);
  cozumTuruYaz();
  document.getElementById("cozumTuru").addEventListener("change", (e) => cozumTuruDegisti(e.target.value));
  setInterval(izPoll, 1500);
  setInterval(sistemEkYokla, 2000);
  sistemEkYokla();
  setInterval(renderYokla, 5000);
  islemciYokla();
}

function yenidenCiz() {
  agacYenile();
  ayrintiCiz();
  gorselYenile();
  mesajCiz(); gunlukCiz();
  motorDurumGoster();
  profilGoster();
  kirlet(S.kirli);
  const a = Kabuk.aktif();
  if (a === "baslangic") baslangicCiz();
  if (a === "kutuphane") kutuphaneCiz();
  if (a === "topluluk") toplulukCiz();
}

function motorDurumGoster() {
  const d = S.motor.durum;
  const metin = d === "hazir" ? (S.motor.mock ? T("durum.motorMock") : T("durum.motorHazir"))
    : d === "hata" ? T("durum.motorHata") : T("durum.motorYukleniyor");
  Kabuk.durum("dMotor", metin, d === "hazir" ? "ok" : d === "hata" ? "kotu" : "bekle");
  baglantiGoster();
  birimIsaretle();
  if (d === "hata" && S.motor.mesaj && !S.motorHataBildirildi) {
    S.motorHataBildirildi = true;
    mesaj("hata", S.motor.mesaj);
    Kabuk.bildir(T("durum.motorHata") + ": " + S.motor.mesaj, "hata", 12000);
  }
}

async function islemciYokla() {
  try {
    const s = await API.islemci();
    const t = s.toplam;
    Kabuk.durum("dCpu", (DIL === "tr" ? "İşlemci" : "CPU") + ": " +
      (t == null ? "–" : "%" + nf(t, 0)) + " · " + (s.cekirdek_sayisi || "?") +
      " " + (DIL === "tr" ? "çekirdek" : "cores"));
    S.sisSon = s;
    sistemCiz(s);
  } catch (e) {}
}

let renderImza = "";
async function renderYokla() {
  try {
    const l = await API.renderListesi();
    const imza = l.map((x) => x.ad + ":" + x.zaman).join("|");
    if (imza === renderImza) return;
    const ilkti = renderImza === "";
    renderImza = imza;
    S.render = l;
    if (!ilkti && l.length) {
      Kabuk.bildir((DIL === "tr" ? "Yeni render dosyası: " : "New render file: ") + l[0].ad, "basari", 7000);
      mesaj("bilgi", (DIL === "tr" ? "Render klasörü güncellendi: " : "Render folder updated: ") + l[0].ad);
      S.renderSecili = l[0].ad;
    }
    agacYenile();
    if ((Kabuk.agacSecili() || "") === "r-render") renderGorseli();
  } catch (e) {}
}

document.addEventListener("DOMContentLoaded", baslat);

/* ================================================================
   PARAMETRE SÜPÜRMESİ
   Bir girdiyi aralık boyunca değiştirip her noktada riski hesaplar.
   Süpürme her zaman temel birimlerle çalışır (%, kPa, g, cm/s, mm);
   birim menüsü yalnızca vaka kurulumunu etkiler, süpürmeyi değil.
   ================================================================ */
const SUPUR_EN_FAZLA = 120;

const SUPUR_ALANLAR = [
  { ad: "oksijen", etiket: () => T("alan.oksijen"), birim: "%", adim: 0.25, varsayilan: [14, 30, 1] },
  { ad: "basinc", etiket: () => T("alan.basinc"), birim: "kPa", adim: 1, varsayilan: [20, 120, 10] },
  { ad: "g", etiket: () => T("alan.g"), birim: "g", adim: 0.01, varsayilan: [0.0001, 1, 0.1] },
  { ad: "akis", etiket: () => T("alan.akis"), birim: "cm/s", adim: 0.5, varsayilan: [0, 20, 2] },
  { ad: "kalinlik", etiket: () => T("alan.kalinlik"), birim: "mm", adim: 0.01, varsayilan: [0.05, 1, 0.05] },
];

const supurAlan = (ad) => SUPUR_ALANLAR.find((x) => x.ad === ad) || SUPUR_ALANLAR[0];

function supurNokta() {
  const d = S.supurme;
  if (!(d.adim > 0)) return 0;
  const a = Math.min(d.bas, d.son), b = Math.max(d.bas, d.son);
  return Math.floor((b - a) / d.adim + 1e-9) + 1;
}

async function supur() {
  if (S.supurme.calisiyor) return;
  if (S.motor.durum !== "hazir") { Kabuk.bildir(T("durum.motorYukleniyor"), "hata"); return; }
  if (!dogrula()) { Kabuk.bildir(DIL === "tr" ? "Önce vaka girdilerini düzeltin." : "Fix the case inputs first.", "hata"); return; }
  const n = supurNokta();
  if (n < 2) { Kabuk.bildir(DIL === "tr" ? "Aralık en az iki nokta vermeli." : "The range must give at least two points.", "hata"); return; }
  if (n > SUPUR_EN_FAZLA) {
    Kabuk.bildir((DIL === "tr" ? "Çok fazla nokta: " : "Too many points: ") + n + " > " + SUPUR_EN_FAZLA, "hata");
    return;
  }

  S.supurme.calisiyor = true;
  S.supurme.yuzde = 0;
  agacYenile(); supurmeGorseli();
  Kabuk.durum("dMotor", T("sup.calisiyor") + "…", "bekle");
  mesaj("bilgi", T("sup.calisiyor") + ": " + supurAlan(S.supurme.parametre).etiket() + " · " + n + " " + (DIL === "tr" ? "nokta" : "points"));

  const bas = performance.now();
  let r;
  try {
    r = await API.supur(kosul(), S.supurme.parametre, S.supurme.bas, S.supurme.son, S.supurme.adim);
  } catch (e) {
    r = { hata: e.message };
  }
  const sure = (performance.now() - bas) / 1000;

  S.supurme.calisiyor = false;
  Kabuk.durum("dMotor", T("durum.motorHazir"), "ok");

  if (r.hata) {
    mesaj("hata", r.hata);
    Kabuk.bildir(r.hata, "hata", 8000);
    gunluk({ tur: T("agac.supurme"), sure, girdi: S.supurme.parametre, hata: r.hata });
    agacYenile(); supurmeGorseli();
    return;
  }

  S.supurme.sonuc = r;
  S.noktaSure = Math.max(0.1, sure / Math.max(1, (r.noktalar || []).length));
  kirlet(true);

  const esik = esikBul((r.noktalar || []).filter((x) => x.yanma_ihtimali != null));
  mesaj("bilgi", T("sup.durdu") + ": " + (r.noktalar || []).length + " " + (DIL === "tr" ? "nokta" : "points") +
    (esik != null ? " · " + T("sup.esik") + " " + nf(esik, 2) + " " + supurAlan(r.parametre).birim : " · " + T("sup.esikYok")));
  if (r.hata_sayisi) mesaj("uyari", r.hata_sayisi + " " + T("sup.hataNokta"));
  gunluk({ tur: T("agac.supurme"), sure, girdi: r.parametre + " " + nf(r.bas, 3) + "→" + nf(r.son, 3),
           sonuc: (r.noktalar || []).length + (DIL === "tr" ? " nokta" : " points") });

  agacYenile();
  Kabuk.agacSec("supurme");
  Kabuk.bildir(T("sup.durdu"), "basari");
}

function supurmeGorseli() {
  const d = S.supurme, a = supurAlan(d.parametre);
  const n = supurNokta();
  const yuzde = d.yuzde || 0;

  let ic = `<div class="gorunum"><div class="gorunum-bas"><h3>${esc(T("agac.supurme"))}</h3>` +
    `<span class="sonuk">${esc(a.etiket())} · ${esc(nf(d.bas, 4))} → ${esc(nf(d.son, 4))} ${esc(a.birim)}</span>` +
    `<span class="sag">` +
    `<button class="dugme birincil" data-komut="supur"${d.calisiyor || n < 2 || n > SUPUR_EN_FAZLA ? " disabled" : ""}>` +
    `${esc(d.calisiyor ? T("sup.calisiyor") + "…" : T("sup.calistir"))}</button></span></div>`;

  if (d.calisiyor) {
    ic += `<div class="kart"><div class="ilerleme-bas"><span class="donen">${esc(T("sup.calisiyor"))}</span>` +
      `<span class="sayi">%${esc(nf(yuzde, 0))}</span></div>` +
      `<div class="ilerleme"><i style="width:${yuzde}%"></i></div>` +
      `<div class="grafik-not">${esc(T("sup.uyari"))}</div></div>`;
  }

  if (!d.sonuc) {
    if (!d.calisiyor) {
      ic += `<div class="bos"><b>${esc(T("sup.yok"))}</b>${esc(T("sup.yokAlt"))}` +
        `<div style="margin-top:12px"><button class="dugme birincil" data-komut="supur"${n < 2 || n > SUPUR_EN_FAZLA ? " disabled" : ""}>` +
        `${esc(T("sup.calistir"))} · ${esc(n)} ${esc(DIL === "tr" ? "nokta" : "points")}</button></div></div>`;
    }
    return Kabuk.gorselYaz(T("agac.supurme"), ic + `</div>`);
  }

  const r = d.sonuc;
  const nk = (r.noktalar || []).filter((x) => x.yanma_ihtimali != null);
  const esik = esikBul(nk);
  const mevcut = kosul()[r.parametre];

  ic += `<div class="kutular k3" style="margin-bottom:14px">` +
    `<div class="kart olcu"><span class="ad">${esc(T("sup.esik"))}</span>` +
      (esik == null
        ? `<span class="buyuk" style="font-size:18px;color:var(--cok-sonuk)">${esc(T("sup.esikYok"))}</span>`
        : `<span class="buyuk" style="color:var(--ok)">${esc(nf(esik, 2))} <span style="font-size:15px">${esc(a.birim)}</span></span>`) +
      `<span class="aciklama">${esc(T("sup.esikAciklama"))}</span></div>` +
    `<div class="kart olcu"><span class="ad">${esc(T("sup.nokta"))}</span>` +
      `<span class="buyuk">${esc((r.noktalar || []).length)}</span>` +
      `<span class="aciklama">${esc(nf(r.sure_sn, 1))} s` +
      (r.hata_sayisi ? ` · <span style="color:var(--uyari)">${esc(r.hata_sayisi)} ${esc(T("sup.hataNokta"))}</span>` : "") +
      `</span></div>` +
    `<div class="kart olcu"><span class="ad">${esc(DIL === "tr" ? "Risk aralığı" : "Risk range")}</span>` +
      `<span class="buyuk" style="font-size:19px">%${esc(pct(Math.min.apply(null, nk.map((x) => x.yanma_ihtimali)), 0))}` +
      ` → %${esc(pct(Math.max.apply(null, nk.map((x) => x.yanma_ihtimali)), 0))}</span>` +
      `<span class="aciklama">${esc(DIL === "tr" ? "aralık boyunca yanma ihtimali" : "burning probability across the range")}</span></div>` +
  `</div>`;

  ic += supurmeCiz(r, { etiket: a.etiket(), birim: a.birim, mevcut: mevcut });

  const tr = DIL === "tr";
  const tablo = { ad: "parametre_supurmesi", sutunlar: [{ ad: a.etiket(), birim: a.birim, d: 4 },
      { ad: T("sonuc.yanmaIhtimali"), birim: "0–1", d: 3 }, { ad: tr ? "Belirsizlik" : "Uncertainty", birim: "0–1", d: 3 },
      { ad: T("sonuc.sonmeSiniri"), birim: "% O₂", d: 2 }, { ad: tr ? "Güvenlik katsayısı" : "Safety factor", birim: "–", d: 2 },
      { ad: "Risk", birim: "", d: null }, { ad: tr ? "Güven" : "Confidence", birim: "/100", d: 0 }, { ad: tr ? "Hata" : "Error", birim: "", d: null }],
    satirlar: (r.noktalar || []).map((x) => x.hata ? [x.deger, null, null, null, null, null, null, x.hata]
      : [x.deger, x.yanma_ihtimali, x.belirsizlik, x.sonme_siniri, x.guvenlik_katsayisi, x.risk_seviyesi, x.guven, null]) };
  if (!tablo.satirlar.some((x) => x[7])) { tablo.sutunlar.pop(); tablo.satirlar.forEach((x) => x.pop()); }

  Kabuk.gorselYaz(T("agac.supurme"), ic + `</div>`,
    `<button class="dugme kucuk" data-komut="kaydet">${esc(T("komut.kaydetK"))}</button>`, tablo);
}

/* ================================================================
   VAKA KARŞILAŞTIRMA
   Kütüphanedeki iki vaka (ya da ekrandaki vaka + bir kayıt) yan yana.
   ================================================================ */
async function karsilastir() {
  let paketler = [];
  try {
    for (const id of S.secKarsi.slice(0, 2)) {
      const p = await API.vakaOku(id);
      if (p) paketler.push(p);
    }
  } catch (e) {
    return Kabuk.bildir(e.message, "hata");
  }

  // Tek vaka seçiliyse ekrandaki çözümle karşılaştır
  if (paketler.length === 1 && S.sonuc) {
    paketler.unshift({
      baslik: (S.baslik || T("krs.mevcut")) + " (" + T("krs.mevcut") + ")",
      girdi: S.sonuc.kosul,
      sonuc: { tahmin: S.sonuc.tahmin, oksijen_egrisi: S.sonuc.oksijen_egrisi },
    });
  }
  if (paketler.length < 2) {
    Kabuk.sekmeAc("kutuphane"); kutuphaneCiz();
    return Kabuk.pencereAc({
      baslik: T("krs.ad"),
      ic: `<div class="bos"><b>${esc(T("krs.sec"))}</b>${esc(T("krs.secAlt"))}</div>`,
      dugmeler: [{ ad: T("genel.kapat"), sinif: "birincil" }],
    });
  }

  const A = paketler[0], B = paketler[1];
  const ta = (A.sonuc || {}).tahmin || {}, tb = (B.sonuc || {}).tahmin || {};
  // Modelin gerçekten kullandığı girdiler (varsayılanlar doldurulmuş hali);
  // ham koşulu göstermek boş alanlara "bilinmiyor" yazıp karşılaştırmayı yanıltır.
  const ga = ta.girdi || A.girdi || {}, gb = tb.girdi || B.girdi || {};

  const bicimle = (v, ad) => {
    if (v == null) return `<i class="sonuk">${esc(T("genel.bilinmiyor"))}</i>`;
    if (ad === "g") return esc(gMetni(v));
    return esc(typeof v === "number" ? nf(v, 4) : v);
  };
  const satir = (ad, x, y, f) => {
    const fark = String(x) !== String(y);
    const h = f || ((v) => esc(v == null ? "–" : v));
    return `<tr><td>${esc(ad)}</td><td class="${fark ? "fark" : ""}">${h(x)}</td><td class="${fark ? "fark" : ""}">${h(y)}</td></tr>`;
  };

  const girdiAlanlari = [
    ["malzeme", T("alan.malzeme")], ["g", T("alan.g")], ["oksijen", T("alan.oksijen") + " (%)"],
    ["basinc", T("alan.basinc") + " (kPa)"], ["akis", T("alan.akis") + " (cm/s)"],
    ["kalinlik", T("alan.kalinlik") + " (mm)"], ["numune_tipi", T("alan.numune")],
    ["yakit_turu", T("alan.yakit")], ["akis_yonu", T("alan.akisYonu")], ["seyreltici", T("alan.seyreltici")],
  ];

  let h = `<div class="suzgec" style="margin-bottom:12px">` +
    `<span class="etiket">A</span><b>${esc(A.baslik || "—")}</b>` +
    `<span style="width:16px;display:inline-block"></span>` +
    `<span class="etiket">B</span><b>${esc(B.baslik || "—")}</b></div>`;

  h += `<h3 style="font-size:11px;letter-spacing:.9px;text-transform:uppercase;color:var(--sonuk);margin:0 0 8px">${esc(T("krs.girdiler"))}</h3>`;
  h += `<div class="tablo-kap"><table class="veri"><thead><tr><th></th><th>A</th><th>B</th></tr></thead><tbody>` +
    girdiAlanlari.map((p) => satir(p[1], ga[p[0]], gb[p[0]], (v) => bicimle(v, p[0]))).join("") +
    `</tbody></table></div>`;

  h += `<h3 style="font-size:11px;letter-spacing:.9px;text-transform:uppercase;color:var(--sonuk);margin:16px 0 8px">${esc(T("krs.sonuclar"))}</h3>`;
  h += `<div class="tablo-kap"><table class="veri"><tbody>` +
    satir(T("sonuc.riskSeviyesi"), ta.risk_seviyesi, tb.risk_seviyesi,
          (v) => `<span class="rozet ${ROZET_SINIF(v)}">${esc(v || "—")}</span>`) +
    satir(T("sonuc.yanmaIhtimali"), ta.yanma_ihtimali, tb.yanma_ihtimali,
          (v) => (v == null ? "–" : "%" + esc(pct(v, 1)))) +
    satir(DIL === "tr" ? "Belirsizlik" : "Uncertainty", ta.belirsizlik, tb.belirsizlik,
          (v) => (v == null ? "–" : "±" + esc(pct(v, 1)))) +
    satir(T("sonuc.sonmeSiniri"), ta.sonme_siniri, tb.sonme_siniri,
          (v) => (v == null ? esc(T("genel.bulunamadi")) : "%" + esc(nf(v, 2)))) +
    satir(T("sonuc.guvenlikKatsayisi"), ta.guvenlik_katsayisi, tb.guvenlik_katsayisi,
          (v) => (v == null ? esc(T("genel.hesaplanamadi"))
                 : `<span style="${v < 1 ? "color:var(--hata);font-weight:700" : "color:var(--ok)"}">${esc(nf(v, 2))}</span>`)) +
    satir(T("sonuc.guvenSkoru"), (ta.guven || {}).skor, (tb.guven || {}).skor, (v) => esc(nf(v, 0)) + " / 100") +
    satir(DIL === "tr" ? "Fizik motoru" : "Physics engine", (ta.motor || {}).yanma, (tb.motor || {}).yanma,
          (v) => (v == null ? esc(T("genel.yok")) : "%" + esc(pct(v, 0)))) +
    satir(DIL === "tr" ? "Uyarı sayısı" : "Warning count", (ta.uyarilar || []).length, (tb.uyarilar || []).length) +
    `</tbody></table></div>`;

  const ea = (A.sonuc || {}).oksijen_egrisi, eb = (B.sonuc || {}).oksijen_egrisi;
  h += `<h3 style="font-size:11px;letter-spacing:.9px;text-transform:uppercase;color:var(--sonuk);margin:16px 0 8px">${esc(T("krs.egriler"))}</h3>`;
  h += ea && eb
    ? oksijenCiz(ea, { ekler: [{ e: eb, renk: "var(--g-seri2)" }], ortam: [ga.oksijen, gb.oksijen] }) +
      `<div class="grafik-not">${esc(T("krs.egriNot"))}</div>`
    : `<div class="bos">${esc(T("krs.egriYok"))}</div>`;

  h += `<div class="grafik-not">${esc(T("krs.fark"))}</div>`;

  Kabuk.pencereAc({ baslik: T("krs.ad"), ic: h, dugmeler: [{ ad: T("genel.kapat"), sinif: "birincil" }] });
}

/* ================================================================
   TIKLAMA DENETİMİ
   Gizli olması gereken bir katman (pencere örtüsü) ekranı kaplarsa
   bütün tıklamalar o katmana gider ve arayüz ölü görünür — ama hiçbir
   hata mesajı çıkmaz. Sessiz olduğu için açılışta bir kez denetliyoruz:
   sorun varsa katmanı zorla kapatıp Mesajlar panelinde bildiriyoruz.
   ================================================================ */
function tiklamaDenetimi() {
  try {
    const noktalar = [[innerWidth / 2, innerHeight / 2], [innerWidth / 2, 120], [200, innerHeight / 2]];
    const engelleyenler = [];
    noktalar.forEach((p) => {
      const ust = document.elementFromPoint(p[0], p[1]);
      if (!ust) return;
      const ortu = ust.id === "ortu" || (ust.closest && ust.closest("#ortu"));
      if (ortu) engelleyenler.push(ust.id || ust.className);
    });
    if (!engelleyenler.length) return;

    const o = $("#ortu");
    if (o && o.hidden) o.style.setProperty("display", "none", "important");

    const m = DIL === "tr"
      ? "Arayüz katmanı hatası: görünmez bir katman ekranı kaplıyordu ve tıklamaları engelliyordu (" +
        engelleyenler.join(", ") + "). Katman kapatıldı. Sorun sürerse troubleshoot.bat ile açın."
      : "Overlay fault: an invisible layer was covering the screen and swallowing clicks (" +
        engelleyenler.join(", ") + "). It has been disabled. If it persists, launch via troubleshoot.bat.";
    mesaj("hata", m);
    Kabuk.bildir(m, "hata", 12000);
  } catch (e) {
    /* denetimin kendisi uygulamayı düşürmemeli */
  }
}

/* ================================================================
   GITHUB PAYLAŞIMI
   Sunucu yok: her vaka, GitHub deposundaki vakalar/ klasörüne düşen bir
   .ahut dosyası. GitHub Pages o depoyu site olarak yayımlıyor.
   Jeton yalnızca bu bilgisayarda durur; buraya hiç gelmez (Python tarafı
   yalnızca "var/yok" bilgisini gönderir).
   ================================================================ */

async function ghAyarAl() {
  try { return await API.githubAyar(); } catch (e) { return { depo: "", jeton_var: false }; }
}

function ghKurulumPenceresi() {
  Kabuk.pencereAc({
    baslik: T("gh.kurulumYok"),
    ic: `<div class="bos"><b>${esc(T("gh.kurulumYok"))}</b>${esc(T("gh.kurulumYokAlt"))}</div>`,
    dugmeler: [
      { ad: T("genel.iptal") },
      { ad: T("komut.profilDuzenle"), sinif: "birincil", islev: () => setTimeout(profilPenceresi, 60) },
    ],
  });
}

async function paylas() {
  if (!S.sonuc) return Kabuk.bildir(DIL === "tr" ? "Önce çözün." : "Solve first.", "hata");

  const ayar = await ghAyarAl();
  if (!ayar.depo || !ayar.jeton_var) return ghKurulumPenceresi();

  if (!S.vakaId || S.kirli) await vakaKaydet();
  if (!S.vakaId) return;

  Kabuk.bildir(T("gh.paylasiliyor"));
  Kabuk.durum("dMotor", T("gh.paylasiliyor"), "bekle");
  let r;
  try { r = await API.githubPaylas(S.vakaId); } catch (e) { r = { hata: e.message }; }
  Kabuk.durum("dMotor", T("durum.motorHazir"), "ok");

  if (r.hata) {
    mesaj("hata", r.hata);
    return Kabuk.pencereAc({
      baslik: T("gh.paylas"),
      ic: `<div class="uyari-satir kritik">${esc(r.hata)}</div>`,
      dugmeler: [{ ad: T("genel.kapat") }, { ad: T("komut.profilDuzenle"), sinif: "birincil",
                   islev: () => setTimeout(profilPenceresi, 60) }],
    });
  }

  mesaj("bilgi", (r.guncelleme ? T("gh.guncellendi") : T("gh.paylasildi")) + ": " + r.dosya);
  Kabuk.pencereAc({
    baslik: r.guncelleme ? T("gh.guncellendi") : T("gh.paylasildi"),
    ic: `<div class="uyari-satir bilgi"><span><b>${esc(r.dosya)}</b> → ${esc(r.depo)}</span></div>
      <div class="form-izgara" style="margin-top:14px">
        <label>${esc(T("gh.siteAdresi"))}</label>
        <input class="giris" id="ghAdres" readonly value="${esc(r.site)}">
      </div>
      <p class="form-not">${esc(DIL === "tr"
        ? "GitHub Pages ilk yayında birkaç dakika gecikebilir. Bağlantı aynı kalır, sonradan da açılır."
        : "GitHub Pages can take a few minutes on first publish. The link stays the same and will work later.")}</p>`,
    dugmeler: [
      { ad: T("genel.kapat") },
      { ad: T("gh.panoyaKopyala"), islev: (ic) => {
          const g = $("#ghAdres", ic); g.select();
          try { document.execCommand("copy"); } catch (e) {}
          Kabuk.bildir(T("gh.panoyaKopyala") + " ✓", "basari");
          return false;
        } },
      { ad: T("gh.githubAc"), islev: () => API.baglantiAc(r.github) },
      { ad: T("gh.siteAc"), sinif: "birincil", islev: () => API.baglantiAc(r.site) },
    ],
  });
  toplulukTazele(true);
}

/* ---------------------------------------------------------------- topluluk */
async function toplulukTazele(tazele) {
  S.toplulukBilgi = Object.assign({}, S.toplulukBilgi, { yukleniyor: true });
  if (Kabuk.aktif() === "topluluk") toplulukCiz();
  let r;
  try { r = await API.githubListe(!!tazele); } catch (e) { r = { kaynak: "yerel", liste: [], hata: e.message }; }
  r.yukleniyor = false;
  S.toplulukBilgi = r;
  S.topluluk = r.liste || [];
  baglantiGoster();
  if (Kabuk.aktif() === "topluluk") toplulukCiz();
}

/* ---------------------------------------------------------------- Topluluk > Deney verisi (11. madde) */
let topGorunum = "vakalar";            // "vakalar" | "deney"
let TV = { liste: null, durum: "", moderator: false, moderatorAd: "", ozet: null, hata: null };
const TV_DURUM = { onaysiz: ["onaysız", "unapproved", "var(--cok-sonuk)", ""], onayli: ["onaylı", "approved", "var(--ok)", ""],
                   reddedildi: ["reddedildi", "rejected", "var(--hata)", "line-through"] };
const TV_ETIKET = { celiski: "var(--uyari)", birim_supheli: "var(--uyari)", llm_cikardi: "var(--vurgu)", ice_aktarildi: "var(--cok-sonuk)" };
const TV_ALAN = [   // [anahtar, TR, EN, tür, zorunlu]
  ["malzeme", "Malzeme", "Material", "metin", true], ["yakit_turu", "Yakıt türü", "Fuel type", ["", "kati", "sivi", "gaz"], false],
  ["numune_tipi", "Numune tipi", "Sample type", ["", ...NUMUNE], false], ["kalinlik_mm", "Kalınlık / çap (mm)", "Thickness / diameter (mm)", "sayi", false],
  ["g", "Yerçekimi (g₀)", "Gravity (g₀)", "sayi", true], ["oksijen_yuzde", "Oksijen (%)", "Oxygen (%)", "sayi", true],
  ["basinc_kpa", "Basınç (kPa)", "Pressure (kPa)", "sayi", true], ["akis_cm_s", "Akış (cm/s)", "Flow (cm/s)", "sayi", false],
  ["seyreltici", "Seyreltici", "Diluent", ["", "n2", "he", "co2", "ar"], false], ["sonuc", "Sonuç", "Result", ["", "yandi", "sondu"], true],
  ["yayilma_hizi_mm_s", "Yayılma hızı (mm/s)", "Spread rate (mm/s)", "sayi", false], ["K_mm2_s", "Yanma hızı K (mm²/s)", "Burning rate K (mm²/s)", "sayi", false],
  ["sonme_capi_mm", "Sönme çapı (mm)", "Extinction diameter (mm)", "sayi", false],
  ["kaynak_turu", "Kaynak türü", "Source type", ["", "doi", "rapor", "kendi_deney", "makale_pdf"], true], ["kaynak", "Kaynak", "Source", "metin", true],
  ["yontem", "Yöntem", "Method", "metin", false], ["ekleyen", "Ekleyen", "Added by", "metin", true], ["tarih", "Tarih", "Date", "metin", false],
];

async function tvTazele() {
  const r = await API.tvListele(TV.durum ? { durum: TV.durum } : null);
  TV.liste = r.liste || []; TV.hata = r.hata || null; TV.depo = r.depo;
  if (Kabuk.aktif() === "topluluk") toplulukCiz();
}

function tvDurum(dr) {
  const x = TV_DURUM[dr] || [dr, dr, "var(--cok-sonuk)", ""];
  return `<span class="etiket" style="color:${x[2]};border-color:${x[2]};text-decoration:${x[3]}">${esc(DIL === "tr" ? x[0] : x[1])}</span>`;
}

function tvFormu() {
  const p = S.profil || {};
  const ic = `<div class="tablo-kap" style="border:0"><table class="veri"><tbody>` + TV_ALAN.map(([k, tr, en, tur, z]) => {
      const v = k === "ekleyen" ? (p.ad || "") : k === "malzeme" ? (S.girdi.malzeme || "") : "";
      const girdi = Array.isArray(tur)
        ? `<select class="giris" data-tv="${k}">${tur.map((x) => `<option value="${esc(x)}">${esc(x || "—")}</option>`).join("")}</select>`
        : `<input class="giris" data-tv="${k}" ${tur === "sayi" ? 'type="number" step="any"' : ""} value="${esc(v)}" style="width:90%">`;
      return `<tr><th style="width:36%">${esc(DIL === "tr" ? tr : en)}${z ? " *" : ""}</th><td>${girdi}</td></tr>`;
    }).join("") + `</tbody></table></div><div id="tvHata"></div>` +
    `<p class="sonuk" style="font-size:11px">${esc(DIL === "tr" ? "Kayıt onaysız girer; risk modeline ve motor kalibrasyonuna girmez." : "Records enter as unapproved; they do not enter the risk model or engine calibration.")}</p>`;
  Kabuk.pencereAc({ baslik: DIL === "tr" ? "Deney kaydı ekle" : "Add experiment record", ic,
    dugmeler: [{ ad: T("genel.iptal") }, { ad: DIL === "tr" ? "Ekle" : "Add", sinif: "birincil", islev: async (pic) => {
      const k = {};
      pic.querySelectorAll("[data-tv]").forEach((el) => { k[el.dataset.tv] = el.value; });
      const r = await API.tvEkle(k);
      if (r.hata) { pic.querySelector("#tvHata").innerHTML = `<div class="uyari-satir" style="color:var(--hata)"><span>${esc(r.hata)}</span></div>`; return false; }
      Kabuk.bildir(r.mukerrer ? (DIL === "tr" ? `Bu kayıt zaten var (id ${r.id}).` : `This record already exists (id ${r.id}).`)
                              : (DIL === "tr" ? `Eklendi (id ${r.id}, ${r.durum})` : `Added (id ${r.id}, ${r.durum})`) + ((r.etiketler || []).length ? " · " + r.etiketler.join(", ") : ""), r.mukerrer ? "hata" : "basari", 6000);
      await tvTazele();
      return true;
    } }] });
}

function tvAyrinti(id) {
  const k = (TV.liste || []).find((x) => String(x.id) === String(id));
  if (!k) return;
  const satir = (a, v) => `<tr><th style="width:34%">${esc(a)}</th><td>${v}</td></tr>`;
  const ic = `<div class="tablo-kap" style="border:0"><table class="veri"><tbody>` +
    TV_ALAN.map(([a, tr, en]) => k[a] == null ? "" : satir(DIL === "tr" ? tr : en, esc(k[a]))).join("") +
    satir(DIL === "tr" ? "Durum" : "Status", tvDurum(k.durum)) +
    satir(DIL === "tr" ? "Kontrol notları" : "Check notes", (k.kontrol_notlari || []).map((x) => `<div>${esc(x)}</div>`).join("") || "–") +
    (k.moderator ? satir(DIL === "tr" ? "Moderatör" : "Moderator", esc(k.moderator + " · " + (k.karar_tarihi || "") + (k.gerekce ? " · " + k.gerekce : ""))) : "") +
    `</tbody></table></div>`;
  Kabuk.pencereAc({ baslik: (DIL === "tr" ? "Kayıt " : "Record ") + k.id + " — " + k.malzeme, ic, dugmeler: [{ ad: T("genel.kapat"), sinif: "birincil" }] });
}

function deneyVerisiCiz() {
  if (TV.liste === null) { tvTazele(); return `<div class="bos">${esc(DIL === "tr" ? "Yükleniyor…" : "Loading…")}</div>`; }
  const ust = `<div class="uyari-satir bilgi"><span><b>${esc(DIL === "tr" ? "Bu veri risk modeline ve fizik motorlarının kalibrasyonuna girmez." : "This data does not enter the risk model or the calibration of the physics engines.")}</b> ` +
    esc(DIL === "tr" ? "Yalnız güven skorunda (v2) yakın kayıt olarak sayılır: onaylı kayıt 0,6, onaysız kayıt 0,2 ağırlıkla." : "It only counts as a nearby record in the confidence score (v2): approved 0.6, unapproved 0.2 weight.") + `</span></div>`;
  const dg = (k, a, sinif) => `<button class="dugme kucuk${sinif ? " " + sinif : ""}" data-tvkomut="${k}">${esc(a)}</button>`;
  const arac = `<div class="sayfa-bas" style="margin-top:12px;flex-wrap:wrap">` +
    dg("ekle", DIL === "tr" ? "+ Kayıt ekle" : "+ Add record", "birincil") + dg("csv", DIL === "tr" ? "CSV yükle" : "Upload CSV") +
    dg("sablon", DIL === "tr" ? "Şablonu indir" : "Download template") + dg("disa", DIL === "tr" ? "Dışa aktar" : "Export") +
    dg("ice", DIL === "tr" ? "İçe aktar" : "Import") +
    dg("mlzdisa", DIL === "tr" ? "Kullanıcı malzemelerini paylaş" : "Share user materials") + dg("mlzice", DIL === "tr" ? "Malzeme paketi al" : "Import material pack") +
    `<span class="sag"><select class="giris" id="tvDurumSec"><option value="">${esc(DIL === "tr" ? "tüm durumlar" : "all statuses")}</option>` +
      Object.keys(TV_DURUM).map((x) => `<option value="${x}"${TV.durum === x ? " selected" : ""}>${esc(DIL === "tr" ? TV_DURUM[x][0] : TV_DURUM[x][1])}</option>`).join("") + `</select>` +
      `<label class="sonuk" style="display:flex;gap:5px;align-items:center"><input type="checkbox" id="tvMod"${TV.moderator ? " checked" : ""}>${esc(DIL === "tr" ? "moderatör kipi" : "moderator mode")}</label>` +
      (TV.moderator ? `<input class="giris" id="tvModAd" placeholder="${esc(DIL === "tr" ? "moderatör adı" : "moderator name")}" value="${esc(TV.moderatorAd)}" style="width:140px">` : "") +
    `</span></div>`;
  const ozet = TV.ozet ? `<div class="uyari-satir bilgi"><span>${TV.ozet}</span></div>` : "";
  const tablo = TV.hata ? `<div class="uyari-satir">${esc(TV.hata)}</div>` : !TV.liste.length
    ? `<div class="bos">${esc(DIL === "tr" ? "Kayıt yok. Form ya da CSV ile ekleyin." : "No records. Add via form or CSV.")}</div>`
    : `<div class="tablo-kap" style="margin-top:10px"><table class="veri"><thead><tr>` +
      ["id", DIL === "tr" ? "malzeme" : "material", "g", "O₂ %", "kPa", DIL === "tr" ? "sonuç" : "result", DIL === "tr" ? "kaynak" : "source",
       DIL === "tr" ? "ekleyen" : "added by", DIL === "tr" ? "tarih" : "date", DIL === "tr" ? "durum" : "status", DIL === "tr" ? "etiketler" : "tags", ""]
        .map((x) => `<th>${esc(x)}</th>`).join("") + `</tr></thead><tbody>` +
      TV.liste.map((k) => `<tr data-tvsatir="${esc(k.id)}" style="cursor:pointer">` +
        `<td class="s">${esc(k.id)}</td><td>${esc(k.malzeme)}</td><td class="s">${esc(gMetni(k.g))}</td><td class="s">${esc(nf(k.oksijen_yuzde, 1))}</td>` +
        `<td class="s">${esc(nf(k.basinc_kpa, 1))}</td><td>${esc(k.sonuc)}</td><td style="overflow-wrap:anywhere">${esc((k.kaynak_turu || "") + ": " + (k.kaynak || ""))}</td>` +
        `<td>${esc(k.ekleyen || "")}</td><td>${esc(k.tarih || "")}</td><td>${tvDurum(k.durum)}</td>` +
        `<td>${(k.etiketler || []).map((e) => `<span class="etiket" style="color:${TV_ETIKET[e] || "var(--sonuk)"};border-color:${TV_ETIKET[e] || "var(--cizgi)"}">${esc(e)}</span>`).join(" ")}</td>` +
        `<td>${TV.moderator && k.durum !== "onayli" ? `<button class="dugme kucuk" data-tvonay="${esc(k.id)}">${esc(DIL === "tr" ? "Onayla" : "Approve")}</button>` : ""}` +
          `${TV.moderator && k.durum !== "reddedildi" ? ` <button class="dugme kucuk tehlike" data-tvred="${esc(k.id)}">${esc(DIL === "tr" ? "Reddet" : "Reject")}</button>` : ""}</td></tr>`).join("") +
      `</tbody></table></div>`;
  return ust + arac + ozet + tablo + (TV.depo ? `<div class="grafik-not">${esc(DIL === "tr" ? "Depo: " : "Store: ")}${esc(TV.depo)}</div>` : "");
}

async function tvKomut(k) {
  const ozet = (r, ad) => r.iptal ? null : r.hata ? `<b style="color:var(--hata)">${esc(r.hata)}</b>` : ad(r);
  let o = null;
  if (k === "ekle") return tvFormu();
  if (k === "csv") o = ozet(await API.tvCsvYukle(null, (S.profil || {}).ad || null), (r) =>
    esc(`${r.eklenen} ${DIL === "tr" ? "eklendi" : "added"}, ${r.mukerrer} ${DIL === "tr" ? "mükerrer" : "duplicate"}, ${(r.reddedilen || []).length} ${DIL === "tr" ? "reddedildi" : "rejected"}`) +
      (r.reddedilen || []).map((x) => `<div class="sonuk">${esc((DIL === "tr" ? "satır " : "row ") + x.satir + ": " + x.sebep)}</div>`).join(""));
  if (k === "sablon") o = ozet(await API.tvSablon(), (r) => esc((DIL === "tr" ? "Şablon kaydedildi: " : "Template saved: ") + r.yol));
  if (k === "disa") o = ozet(await API.tvDisaAktar(), (r) => esc((DIL === "tr" ? "Paket yazıldı: " : "Pack written: ") + r.yol));
  if (k === "ice") o = ozet(await API.tvIceAktar(), (r) => esc(`${DIL === "tr" ? "İçe aktarıldı (hepsi onaysız)" : "Imported (all unapproved)"}: ${r.eklenen} / ${r.mukerrer} ${DIL === "tr" ? "mükerrer" : "duplicate"} / ${(r.reddedilen || []).length} ${DIL === "tr" ? "reddedildi" : "rejected"}`));
  if (k === "mlzdisa") o = ozet(await API.kullaniciMalzemeDisaAktar(), (r) => esc((DIL === "tr" ? `${r.sayi} kullanıcı malzemesi yazıldı: ` : `${r.sayi} user materials written: `) + r.yol));
  if (k === "mlzice") { o = ozet(await API.kullaniciMalzemeIceAktar(), (r) => esc(`${r.eklenen} ${DIL === "tr" ? "malzeme alındı (onaysız)" : "materials imported (unapproved)"}`) +
      (r.reddedilen || []).map((x) => `<div class="sonuk">${esc(x.ad + ": " + x.sebep)}</div>`).join("")); MLZ = null; }
  if (o !== null) TV.ozet = o;
  await tvTazele();
}

function toplulukCiz() {
  const gecis = `<span style="display:flex;gap:6px">` +
    [["vakalar", DIL === "tr" ? "Paylaşılan vakalar" : "Shared cases"], ["deney", DIL === "tr" ? "Deney verisi" : "Experiment data"]]
      .map(([g, a]) => `<button class="dugme kucuk${topGorunum === g ? " birincil" : ""}" data-topgor="${g}">${esc(a)}</button>`).join("") + `</span>`;
  if (topGorunum === "deney") {
    Kabuk.ekranYaz("ek-topluluk", `<div class="sayfa"><div class="sayfa-bas"><h2>${esc(T("top.basligi"))}</h2>${gecis}</div>${deneyVerisiCiz()}</div>`);
    const sec = $("#tvDurumSec");
    if (sec) sec.addEventListener("change", () => { TV.durum = sec.value; tvTazele(); });
    const mod = $("#tvMod");
    if (mod) mod.addEventListener("change", () => { TV.moderator = mod.checked; toplulukCiz(); });
    const mad = $("#tvModAd");
    if (mad) mad.addEventListener("input", () => { TV.moderatorAd = mad.value; });
    return;
  }
  const b = S.toplulukBilgi || { kaynak: "yerel", liste: S.topluluk || [] };
  const liste = S.topluluk || [];

  const rozet = b.yukleniyor
    ? `<span class="etiket donen">${esc(T("gh.tazele"))}…</span>`
    : b.kaynak === "canli"
      ? `<span class="etiket" style="border-color:var(--ok);color:var(--ok)">${esc(T("gh.canli"))}</span>`
      : b.kaynak === "onbellek"
        ? `<span class="etiket uyari">${esc(T("gh.cevrimdisi"))}</span>`
        : `<span class="etiket">${esc(T("gh.yerelKaynak"))}</span>`;

  const zaman = b.zaman ? ` · ${esc(T("gh.sonGuncelleme"))} ${esc(String(b.zaman).replace("T", " ").slice(0, 16))}` : "";

  let ic = `<div class="sayfa"><div class="sayfa-bas">` +
    `<h2>${esc(T("top.basligi"))}</h2>` + gecis +
    `<span class="sonuk">${rozet}${b.depo ? " · " + esc(b.depo) : ""}${zaman}</span>` +
    `<span class="sag">` +
    `<button class="dugme" data-komut="gh-tazele"${b.yukleniyor ? " disabled" : ""}>${esc(T("gh.tazele"))}</button>` +
    (b.depo ? `<button class="dugme" data-komut="gh-site">${esc(T("gh.siteAc"))}</button>` : "") +
    `<button class="dugme" data-komut="profil-duzenle">${esc(T("komut.profilDuzenle"))}</button>` +
    `</span></div>`;

  if (b.hata) {
    ic += `<div class="uyari-satir">${esc(b.hata)}</div>`;
  }
  if (!b.depo && !b.hata) {
    ic += `<div class="uyari-satir bilgi"><span>${esc(T("gh.kurulumYokAlt"))}</span></div>`;
  }

  ic += liste.length
    ? `<div class="vaka-izgara" style="margin-top:14px">${liste.map((v) => vakaKarti(v, true)).join("")}</div>`
    : `<div class="bos" style="margin-top:14px"><b>${esc(DIL === "tr" ? "Paylaşılmış vaka yok" : "No shared cases")}</b>` +
      esc(DIL === "tr" ? "Bir vakayı çözüp Paylaş düğmesine basın." : "Solve a case and press Share.") + `</div>`;

  Kabuk.ekranYaz("ek-topluluk", ic + `</div>`);
}

/* ---------------------------------------------------------------- profil penceresi (GitHub bölümüyle) */
function profilPenceresi() {
  const p = S.profil || {};
  Kabuk.pencereAc({
    baslik: T("komut.profilDuzenle"),
    ic: `<div class="form-izgara">` +
      `<label for="pAd">${esc(DIL === "tr" ? "Ad soyad" : "Full name")}</label><input class="giris" id="pAd" value="${esc(p.ad || "")}">` +
      `<label for="pKurum">${esc(DIL === "tr" ? "Kurum / okul" : "Institution")}</label><input class="giris" id="pKurum" value="${esc(p.kurum || "")}">` +
      `<label for="pRol">${esc(DIL === "tr" ? "Rol" : "Role")}</label><input class="giris" id="pRol" value="${esc(p.rol || "")}" placeholder="${esc(DIL === "tr" ? "örn. yangın güvenliği analisti" : "e.g. fire safety analyst")}">` +
      `<label for="pBag">${esc(DIL === "tr" ? "Bağlantı" : "Link")}</label><input class="giris" id="pBag" value="${esc(p.baglanti || "")}" placeholder="https://github.com/...">` +
      `<div class="genis form-not">${esc(DIL === "tr"
        ? "Profil yalnızca bu bilgisayarda tutulur. Kaydettiğiniz her vaka dosyasına yazar bilgisi olarak eklenir."
        : "The profile is stored on this computer only and is attached as author information to every case you save.")}</div>` +

      `<div class="genis" style="border-top:1px solid var(--cizgi);margin-top:6px;padding-top:12px">` +
        `<h3 style="font-size:11px;letter-spacing:.9px;text-transform:uppercase;color:var(--sonuk)">${esc(T("gh.baslik"))}</h3></div>` +
      `<label for="pDepo">${esc(T("gh.depo"))}</label>` +
        `<input class="giris" id="pDepo" value="${esc(p.github_depo || "")}" placeholder="${esc(T("gh.depoIpucu"))}">` +
      `<label for="pJeton">${esc(T("gh.jeton"))}</label>` +
        `<input class="giris" id="pJeton" type="password" autocomplete="off" placeholder="${esc(p.github_jeton_var ? T("gh.jetonVar") : "github_pat_…")}">` +
      `<div class="genis form-not">${esc(T("gh.jetonIpucu"))}</div>` +
      `<div class="genis" id="ghDurum"></div>` +
      `<div class="genis" style="display:flex;gap:9px;flex-wrap:wrap">` +
        `<button class="dugme" id="ghSina">${esc(T("gh.sina"))}</button>` +
        `<button class="dugme" id="ghSite">${esc(T("gh.siteKur"))}</button>` +
      `</div>` +
      `</div>`,
    hazir: (ic) => {
      const kaydet = async () => {
        const yeni = {
          ad: $("#pAd", ic).value.trim(), kurum: $("#pKurum", ic).value.trim(),
          rol: $("#pRol", ic).value.trim(), baglanti: $("#pBag", ic).value.trim(),
          github_depo: $("#pDepo", ic).value.trim(), github_jeton: $("#pJeton", ic).value,
        };
        S.profil = await API.profilYaz(yeni);
        $("#pJeton", ic).value = "";
        profilGoster();
        return S.profil;
      };
      const durum = (metin, sinif) => ($("#ghDurum", ic).innerHTML =
        metin ? `<div class="uyari-satir ${sinif || "bilgi"}"><span>${metin}</span></div>` : "");

      $("#ghSina", ic).addEventListener("click", async () => {
        durum(esc(T("gh.sinaniyor")));
        await kaydet();
        const r = await API.githubSina();
        if (!r.tamam) return durum(esc(r.hata), "kritik");
        durum(`<b>${esc(T("gh.baglandi"))}:</b> ${esc(r.tam_ad)} · ${esc(r.acik ? (DIL === "tr" ? "açık depo" : "public") : (DIL === "tr" ? "GİZLİ DEPO — Pages çalışmaz" : "PRIVATE — Pages will not work"))}` +
          `<br>${esc(T("gh.siteAdresi"))}: ${esc(r.site)}`, r.acik ? "bilgi" : "");
      });
      $("#ghSite", ic).addEventListener("click", async () => {
        durum(esc(T("gh.kuruluyor")));
        await kaydet();
        const r = await API.githubSiteKur();
        if (r.hata) return durum(esc(r.hata), "kritik");
        const y = (r.yazilan || []).length;
        durum(`<b>${esc(y ? T("gh.siteKuruldu") : T("gh.siteDegismedi"))}</b>` +
          (y ? ` · ${esc(y)} ${esc(DIL === "tr" ? "dosya yüklendi" : "files uploaded")}` : "") +
          `<br>${esc(r.site)}`, "bilgi");
        toplulukTazele(true);
      });
    },
    dugmeler: [
      { ad: T("genel.iptal") },
      { ad: T("genel.kaydet"), sinif: "birincil", islev: async (ic) => {
          try {
            S.profil = await API.profilYaz({
              ad: $("#pAd", ic).value.trim(), kurum: $("#pKurum", ic).value.trim(),
              rol: $("#pRol", ic).value.trim(), baglanti: $("#pBag", ic).value.trim(),
              github_depo: $("#pDepo", ic).value.trim(), github_jeton: $("#pJeton", ic).value,
            });
            profilGoster();
            Kabuk.bildir(DIL === "tr" ? "Profil kaydedildi." : "Profile saved.", "basari");
            toplulukTazele(true);
          } catch (e) { Kabuk.bildir(e.message, "hata"); }
        } },
    ],
  });
}

/* ================================================================
   SİSTEM PANELİ (alt panel, htop benzeri)
   Çekirdek başına işlemci kullanımı, bellek, takas, süreç sayısı.
   Değerler gerçekten ölçülür; ölçülemeyen alan gösterilmez.
   ================================================================ */
const SIS_RENK = (y) => (y < 50 ? "var(--ok)" : y < 80 ? "var(--uyari)" : "var(--hata)");
const GB = (b) => (b == null ? "–" : nf(b / 1073741824, 1));

function sureMetni(sn) {
  if (sn == null) return "–";
  const g = Math.floor(sn / 86400), s = Math.floor((sn % 86400) / 3600), d = Math.floor((sn % 3600) / 60);
  if (DIL === "tr") return (g ? g + " gün " : "") + (s ? s + " sa " : "") + d + " dk";
  return (g ? g + "d " : "") + (s ? s + "h " : "") + d + "m";
}

function sisCubuk(yuzde, etiket, renk) {
  const y = Math.max(0, Math.min(100, yuzde || 0));
  return `<div class="sis-cubuk"><i style="width:${y}%;background:${renk || SIS_RENK(y)}"></i>` +
         `<u>${esc(etiket)}</u></div>`;
}

function sistemCiz(s) {
  if (!s) return;
  const cek = s.cekirdek;
  let h = `<div class="sis">`;

  h += `<div class="sis-bas"><b>${esc(DIL === "tr" ? "İŞLEMCİ" : "CPU")}</b>` +
    `<span>${esc(s.cekirdek_sayisi ?? "?")} ${esc(DIL === "tr" ? "çekirdek" : "cores")}</span>` +
    `<span class="sag sayi" style="color:${SIS_RENK(s.toplam || 0)}">${s.toplam == null ? "–" : "%" + esc(nf(s.toplam, 0))}</span></div>`;

  if (cek && cek.length) {
    h += `<div class="sis-cekirdekler">` + cek.map((y, i) =>
      `<div class="sis-cek"><span class="no">${i}</span>${sisCubuk(y, "%" + nf(y, 0))}</div>`).join("") + `</div>`;
  } else {
    h += sisCubuk(s.toplam || 0, s.toplam == null ? "–" : "%" + nf(s.toplam, 0));
    h += `<div class="sis-not">${esc(DIL === "tr"
      ? "Çekirdek başına ölçüm için psutil gerekir; şu an yalnızca toplam gösteriliyor."
      : "Per-core measurement needs psutil; only the total is shown.")}</div>`;
  }

  if (s.bellek) {
    h += `<div class="sis-bas" style="margin-top:12px"><b>${esc(DIL === "tr" ? "BELLEK" : "MEMORY")}</b>` +
      `<span>${esc(GB(s.bellek.kullanilan))} / ${esc(GB(s.bellek.toplam))} GB</span>` +
      `<span class="sag sayi" style="color:${SIS_RENK(s.bellek.yuzde)}">%${esc(nf(s.bellek.yuzde, 0))}</span></div>` +
      sisCubuk(s.bellek.yuzde, "");
  }
  if (s.takas) {
    h += `<div class="sis-bas" style="margin-top:10px"><b>${esc(DIL === "tr" ? "TAKAS" : "SWAP")}</b>` +
      `<span>${esc(GB(s.takas.kullanilan))} / ${esc(GB(s.takas.toplam))} GB</span>` +
      `<span class="sag sayi">%${esc(nf(s.takas.yuzde, 0))}</span></div>` +
      sisCubuk(s.takas.yuzde, "", "var(--vurgu)");
  }

  h += sistemEkHtml(S.sisEk);
  const ayak = [];
  if (s.surec != null) ayak.push((DIL === "tr" ? "süreç " : "processes ") + s.surec);
  if (s.calisma_sn != null) ayak.push((DIL === "tr" ? "çalışma süresi " : "uptime ") + sureMetni(s.calisma_sn));
  if (s.yuk) ayak.push((DIL === "tr" ? "yük " : "load ") + s.yuk.map((x) => nf(x, 2)).join(" "));
  if (S.sonSolveSure) ayak.push((DIL === "tr" ? "son çözüm " : "last solve ") + nf(S.sonSolveSure, 2) + " s");
  ayak.push((DIL === "tr" ? "kaynak " : "source ") + (s.kaynak || "–"));
  h += `<div class="sis-ayak">${ayak.map(esc).join(" · ")}</div>`;

  Kabuk.altYaz("sistem", h + `</div>`);
}
