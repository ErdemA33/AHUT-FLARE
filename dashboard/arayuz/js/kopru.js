"use strict";
/* AHUT FLARE — Python köprüsü.
   pywebview, Python tarafındaki Kopru sınıfının her genel metodunu
   window.pywebview.api.<ad>(...) olarak sunar ve Promise döndürür.
   Burada tek yaptığımız: hazır olmasını beklemek, hataları tek biçime sokmak
   ve Python'dan gelen olayları dinleyebilmek. HTTP yok, port yok. */

const API = (function () {
  let hazirSoz = null;
  const dinleyiciler = {};

  function bekle() {
    if (hazirSoz) return hazirSoz;
    hazirSoz = new Promise((coz) => {
      if (window.pywebview && window.pywebview.api) return coz();
      window.addEventListener("pywebviewready", () => coz(), { once: true });
      // pywebview dışında (tarayıcıda) açıldıysa takılmayalım
      setTimeout(() => coz(), 6000);
    });
    return hazirSoz;
  }

  async function cagir(ad, ...args) {
    await bekle();
    const api = window.pywebview && window.pywebview.api;
    if (!api || typeof api[ad] !== "function") {
      throw new Error("Uygulama çekirdeğine ulaşılamadı (" + ad + ").");
    }
    try {
      return await api[ad](...args);
    } catch (e) {
      // pywebview Python istisnasını metin olarak iletir
      const m = (e && (e.message || e.toString())) || "bilinmeyen hata";
      throw new Error(String(m).replace(/^.*?(?:Error|Exception):\s*/, ""));
    }
  }

  return {
    bekle,
    cagir,
    /* Python -> ekran olayları (ilerleme, motor durumu) */
    dinle(ad, f) {
      (dinleyiciler[ad] || (dinleyiciler[ad] = [])).push(f);
    },
    _olay(ad, veri) {
      (dinleyiciler[ad] || []).forEach((f) => {
        try { f(veri); } catch (e) { console.error(e); }
      });
    },

    hazir: () => cagir("hazir"),
    motorDurumu: () => cagir("motor_durumu"),
    malzemeVarsayilanlari: () => cagir("malzeme_varsayilanlari"),
    malzemeKutuphanesi: () => cagir("malzeme_kutuphanesi"),
    malzemeTani: (ad) => cagir("malzeme_tani", ad),
    malzemeOner: (ad) => cagir("malzeme_oner", ad),
    kullaniciMalzemeKaydet: (k, onay) => cagir("kullanici_malzeme_kaydet", k, onay),
    kullaniciMalzemeOnayla: (id) => cagir("kullanici_malzeme_onayla", id),
    kullaniciMalzemeSil: (id) => cagir("kullanici_malzeme_sil", id),
    kullaniciMalzemeDisaAktar: (y) => cagir("kullanici_malzeme_disa_aktar", y || null),
    kullaniciMalzemeIceAktar: (y) => cagir("kullanici_malzeme_ice_aktar", y || null),
    tvEkle: (k) => cagir("tv_ekle", k),
    tvListele: (f) => cagir("tv_listele", f || null),
    tvOnayla: (id, m) => cagir("tv_onayla", id, m),
    tvReddet: (id, m, g) => cagir("tv_reddet", id, m, g || ""),
    tvCsvYukle: (y, e) => cagir("tv_csv_yukle", y || null, e || null),
    tvSablon: (y) => cagir("tv_sablon", y || null),
    tvDisaAktar: (y) => cagir("tv_disa_aktar", y || null),
    tvIceAktar: (y) => cagir("tv_ice_aktar", y || null),
    coz: (k) => cagir("coz", k),
    llm: (k) => cagir("llm", k),
    llmDurumu: () => cagir("llm_durumu"),
    sohbet: (k, gecmis, soru) => cagir("sohbet", k, gecmis, soru),
    supur: (k, p, a, b, s) => cagir("supur", k, p, a, b, s),
    islemci: () => cagir("islemci"),
    renderListesi: () => cagir("render_listesi"),
    ofmKosular: () => cagir("ofm_kosular"),
    ofmDestek: (k) => cagir("ofm_destek", k),
    ofmSureTahmini: (c, b) => cagir("ofm_sure_tahmini", c, b),
    ofmKosKontrol: (t, c, b) => cagir("ofm_kos_kontrol", t || "kati", c || null, b || 10),
    ofmAyrintiliBaslat: (k, c, b, v) => cagir("ofm_ayrintili_baslat", k, c || null, b || 10, !!v),
    ofmAyrintiliDurum: (id) => cagir("ofm_ayrintili_durum", id),
    ofmKosuSonuc: (ad) => cagir("ofm_kosu_sonuc", ad),
    sahneVaka: (k) => cagir("sahne_vaka", k),
    sahneIzgara: () => cagir("sahne_izgara"),
    sonuc3bListe: () => cagir("sonuc3b_liste"),
    sonuc3bMeta: (y) => cagir("sonuc3b_meta", y),
    sonuc3bKare: (y, i) => cagir("sonuc3b_kare", y, i),
    sonuc3bAktar: (d) => cagir("sonuc3b_aktar", d),
    sonuc3bDurum: () => cagir("sonuc3b_durum"),
    paraviewAc: (d) => cagir("paraview_ac", d),
    ofmKosBaslat: (t) => cagir("ofm_kos_baslat", t || "kati"),
    ofmIceAktar: (y) => cagir("ofm_ice_aktar", y),
    sistemEk: () => cagir("sistem_ek"),
    kosular: () => cagir("kosular"),
    kosuKaynaklari: () => cagir("kosu_kaynaklari"),
    izle: (k, o, s) => cagir("izle", k, o, s),
    kosuEkle: (ad, dizin, komut, log, cekirdek) => cagir("kosu_ekle", ad, dizin, komut, log || "log.kosu", cekirdek || 1),
    kosuIptal: (id) => cagir("kosu_iptal", id),
    kosuDuraklat: (id) => cagir("kosu_duraklat", id),
    kosuDevam: (id) => cagir("kosu_devam", id),
    dogrulamaSivi: () => cagir("dogrulama_sivi"),
    dogrulamaSiviKur: (adlar) => cagir("dogrulama_sivi_kur", adlar || null),
    kosuLogAc: (k) => cagir("kosu_log_ac", k),
    renderUygun: (m, y, g, dil) => cagir("render_uygun", m, y, g, dil),

    ayarlar: () => cagir("ayarlar"),
    ayarYaz: (a) => cagir("ayar_yaz", a),
    profil: () => cagir("profil"),
    profilYaz: (p) => cagir("profil_yaz", p),

    vakaKaydet: (a) => cagir("vaka_kaydet", a),
    vakaGuncelle: (id, a) => cagir("vaka_guncelle", id, a),
    vakaListesi: () => cagir("vaka_listesi"),
    vakaOku: (id) => cagir("vaka_oku", id),
    vakaSil: (id) => cagir("vaka_sil", id),
    yorumEkle: (id, m) => cagir("yorum_ekle", id, m),
    vakaDisaAktar: (id) => cagir("vaka_disa_aktar", id),
    vakaIceAktar: () => cagir("vaka_ice_aktar"),
    dosyaAc: (y) => cagir("dosya_ac", y),
    raporKaydet: (h, ad) => cagir("rapor_kaydet", h, ad),
    csvKaydet: (m, ad) => cagir("csv_kaydet", m, ad),

    githubAyar: () => cagir("github_ayar"),
    githubSina: () => cagir("github_sina"),
    githubSiteKur: () => cagir("github_site_kur"),
    githubPaylas: (id) => cagir("github_paylas", id),
    githubListe: (t) => cagir("github_liste", t),
    githubVaka: (d) => cagir("github_vaka", d),
    githubAl: (d) => cagir("github_al", d),

    topluluk: () => cagir("topluluk"),
    toplulukOku: (id) => cagir("topluluk_oku", id),
    toplulukta: (id) => cagir("topluluktan_al", id),

    klasorGoster: (h) => cagir("klasor_goster", h),
    baglantiAc: (u) => cagir("baglanti_ac", u),
    tamEkran: () => cagir("tam_ekran"),
    cikis: () => cagir("cikis"),
  };
})();

/* Python tarafı buraya seslenir: window.AHUT.olay(ad, veri) */
window.AHUT = window.AHUT || {};
window.AHUT.olay = (ad, veri) => API._olay(ad, veri);
