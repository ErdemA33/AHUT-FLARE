"use strict";
/* AHUT FLARE — Çözüm türü: Ayrıntılı (OpenFOAM; varsayılan) | Hızlı (yarı-ampirik motorlar + risk modeli).
   ÇÖZ, Ayrıntılı'da: koşu doğrudan başlar (malzeme uymuyorsa SIBAL vekil) → bilgi penceresi (süre, uyarılar, isteğe bağlı
   hızlı test) → Çözüm İzleyici kuyruğu (duraklat / devam / kes) → bitince otomatik analiz → sonuç düğümlerinde
   "Ayrıntılı (OpenFOAM)". Hızlı test seçilirse "ön tahmin" olarak gösterilir. Hızlı'da mevcut davranış aynen (cozHizli). Ayrıntılı sonuç varken ana sonuç OpenFOAM motorundan. */

const aTr = () => DIL === "tr";
const A_TUR = { ayrintili: ["Ayrıntılı (OpenFOAM)", "Detailed (OpenFOAM)"],
                hizli: ["Hızlı (yarı-ampirik motorlar + risk modeli)", "Fast (semi-empirical engines + risk model)"] };
const A_TUR_KISA = { ayrintili: ["Ayrıntılı (OpenFOAM)", "Detailed (OpenFOAM)"], hizli: ["Hızlı", "Fast"] };
const aTurAd = (t, kisa) => (kisa ? A_TUR_KISA : A_TUR)[t][aTr() ? 0 : 1];
const aSure = (sn) => (sn == null ? "–" : sn < 90 ? nf(sn, 0) + " s" : sn < 5400 ? nf(sn / 60, 0) + (aTr() ? " dk" : " min") : nf(sn / 3600, 1) + (aTr() ? " sa" : " h"));
const aAktif = () => S.ayrintili && (S.ayrintili.durum === "calisiyor" || S.ayrintili.durum === "iceAktariliyor");

/* ---- araç çubuğu seçici + ayar */
function cozumTuruYaz() {
  const s = document.getElementById("cozumTuru");
  if (!s) return;
  s.innerHTML = ["ayrintili", "hizli"].map((k) => `<option value="${k}">${esc(aTurAd(k, true))}</option>`).join("");
  s.value = S.cozumTuru;
  s.title = (aTr() ? "Çözüm türü: " : "Solution type: ") + aTurAd(S.cozumTuru);
}
function cozumTuruDegisti(t, kirli) {
  S.cozumTuru = t === "hizli" ? "hizli" : "ayrintili";
  cozumTuruYaz();
  if (kirli !== false) kirlet(true);
  agacYenile();
}

/* ---- ÇÖZ giriş noktası */
async function coz() {
  if (S.cozuluyor) return null;
  if (S.cozumTuru !== "ayrintili") return cozHizli();
  return cozAyrintili();
}

async function cozAyrintili() {
  if (!dogrula()) return null;
  if (S.motor.durum !== "hazir") { Kabuk.bildir(T("durum.motorYukleniyor"), "hata"); return null; }
  if (aAktif()) {
    Kabuk.bildir(aTr() ? "Bir ayrıntılı koşu sürüyor; Çözüm İzleyici'den duraklatabilir ya da kesebilirsiniz." : "A detailed run is in progress; pause or stop it from the Solution Monitor.", "hata", 7000);
    Kabuk.sekmeAc("calisma"); Kabuk.agacSec("cozum");
    return null;
  }
  /* ÇÖZ doğrudan OpenFOAM motorunu başlatır (varsayılan çekirdek nproc−2, 10 s benzetim). Malzeme/kalınlık OpenFOAM vakasına
     uymuyorsa koşu SIBAL ağıyla "vekil" olarak yapılır ve bu açıkça yazılır. Yalnız koşu hiç yapılamıyorsa
     (OpenFOAM/paket yok, basınç aralık dışı) hızlı teste yönlendiren pencere çıkar. */
  const k = kosul();
  const d = await API.ofmDestek(k).catch((e) => ({ destekli: false, neden: e.message }));
  const vekil = !d.destekli && (d.kod === "malzeme" || d.kod === "kalinlik");
  if (!d.destekli && !vekil) return ayrintiliDesteklenmiyor(d, k);
  let kon;
  try { kon = await API.ofmKosKontrol("kati", null, 10); } catch (e) { Kabuk.bildir(e.message, "hata"); return null; }
  if (!kon.hazir) return ayrintiliDesteklenmiyor({ neden: kon.neden }, k);
  return ayrintiliBaslat(k, kon.cekirdek, 10, vekil);
}

function ayrintiliDesteklenmiyor(d, k) {
  const tr = aTr();
  const baslik = tr ? "Ayrıntılı (OpenFOAM) koşu bu bilgisayarda/koşulda yapılamıyor" : "A detailed (OpenFOAM) run is not possible here / for this condition";
  mesaj("uyari", baslik + (d.neden ? ": " + d.neden : ""));
  Kabuk.pencereAc({
    baslik: tr ? "Ayrıntılı çözüm yapılamıyor" : "Detailed solve not possible",
    ic: `<p><b>${esc(baslik)}</b></p><p class="sonuk">${esc(d.neden || "")}</p>` +
      `<p class="sonuk">${esc(tr ? "Hızlı test yapabilirsiniz (yarı-ampirik motorlar + risk modeli, birkaç saniye). Çözüm türü ayarınız değişmez." : "You can run a fast test instead (semi-empirical engines + risk model, a few seconds). Your solution-type setting is unchanged.")}</p>`,
    dugmeler: [{ ad: tr ? "Hızlı test yap" : "Run fast test", sinif: "birincil", islev: () => { cozHizli(); } }, { ad: tr ? "Kapat" : "Close" }],
  });
  return null;
}

/* OpenFOAM koşusu başladıktan sonra çıkan uyarı/bilgi penceresi: süre, uyarılar, isteğe bağlı hızlı test */
function ayrintiliBasladiPenceresi(r, k) {
  const tr = aTr();
  const uyar = (u) => `<div class="uyari-satir"><span>${esc(u)}</span></div>`;
  Kabuk.pencereAc({
    baslik: tr ? "Ayrıntılı test başladı (OpenFOAM)" : "Detailed test started (OpenFOAM)",
    ic: `<p class="sonuk">${esc(`${k.malzeme} · g=${gMetni(k.g)} · %${nf(k.oksijen, 1)} O₂ · ${nf(k.basinc, 1)} kPa · ` + (k.akis == null ? (tr ? "akış bilinmiyor (Saffire değeri)" : "flow unknown (Saffire value)") : nf(k.akis, 1) + " cm/s"))}</p>` +
      `<div class="bilgi-satir"><span class="etiket-ad" style="min-width:150px">${esc(tr ? "Koşu" : "Run")}</span><span class="deger"><b>${esc(r.kosu)}</b> · ${esc(r.cekirdek)} ${esc(tr ? "çekirdek" : "cores")} · 10 s ${esc(tr ? "benzetim" : "simulated")}</span></div>` +
      `<div class="bilgi-satir"><span class="etiket-ad" style="min-width:150px">${esc(tr ? "Tahmini süre" : "Estimated time")}</span><span class="deger">${esc(r.sure_saat == null ? "–" : "≈ " + nf(r.sure_saat, 1) + (tr ? " saat" : " h"))}</span></div>` +
      (r.uyarilar || []).map(uyar).join("") +
      `<div class="grafik-not">${esc(tr ? "Koşu Çözüm İzleyici'den izlenir; oradan duraklatılabilir, devam ettirilebilir ya da kesilebilir. Bitince analiz otomatik çalışır." : "Monitor the run in the Solution Monitor, where it can be paused, resumed or stopped. Analysis runs automatically when it finishes.")}</div>` +
      `<p style="margin-top:10px"><b>${esc(tr ? "Hızlı testten devam edebilirsiniz." : "You can continue with the fast test.")}</b> ` +
      `<span class="sonuk">${esc(tr ? "Yarı-ampirik motorlar + risk modeli, birkaç saniye. Seçerseniz OpenFOAM koşusu kesilir ve sonuçlar yalnız hızlı testten gelir." : "Semi-empirical engines + risk model, a few seconds. If chosen, the OpenFOAM run is stopped and results come from the fast test only.")}</span></p>`,
    dugmeler: [{ ad: tr ? "Hızlı testten devam et" : "Continue with fast test", islev: () => { hizliyaGec(r.id); } },
               { ad: tr ? "Yalnız OpenFOAM (tamam)" : "OpenFOAM only (OK)", sinif: "birincil" }],
  });
}

async function ayrintiliBaslat(k, cek, bitis, vekil) {
  const tr = aTr();
  const r = await API.ofmAyrintiliBaslat(k, cek, bitis, vekil).catch((e) => ({ hata: e.message }));
  if (r.hata) { Kabuk.bildir(r.hata, "hata", 9000); mesaj("hata", r.hata); return; }
  S.ayrintili = { id: r.id, kosu: r.kosu, dizin: r.dizin, durum: "calisiyor", kosul: k, cekirdek: r.cekirdek, bitis_s: bitis, deney: r.deney,
                  vekil: !!r.vekil, duraklatildi: false, baslangic: Date.now(), ilerleme: null, kontrol: null, kayit: null, ofm: null };
  mesaj("bilgi", (tr ? "Ayrıntılı koşu kuyruğa eklendi: " : "Detailed run queued: ") + r.kosu + " · " + (r.notlar || []).join("; "));
  (r.uyarilar || []).forEach((u) => mesaj("uyari", u));
  gunluk({ tur: tr ? "Çöz (ayrıntılı)" : "Solve (detailed)", sure: null, girdi: `${k.malzeme} g=${gMetni(k.g)} O₂=${nf(k.oksijen, 2)} p=${nf(k.basinc, 1)}`, sonuc: (tr ? "kuyrukta · " : "queued · ") + r.cekirdek + (tr ? " çekirdek" : " cores") + (r.vekil ? (tr ? " · vekil SIBAL" : " · SIBAL surrogate") : "") });
  IZ.kaynak = r.id; IZ.elle = true; IZ.log[r.id] = []; IZ.ofset[r.id] = null;
  S.cozumTuru = "ayrintili"; cozumTuruYaz();
  kirlet(true); agacYenile();
  Kabuk.sekmeAc("calisma"); Kabuk.agacSec("cozum");
  izPoll(true);
  if (S.onTahmin) cozHizli(true);          // Analiz Ayarları'nda ön tahmin açıksa hızlı test kendiliğinden
  ayrintiliBasladiPenceresi(r, k);
}

/* "Hızlı testten devam et": OpenFOAM koşusu kesilir (arkada sürmez), hızlı test yapılır ve Risk Özeti açılır */
async function hizliyaGec(id) {
  const tr = aTr();
  const r = await API.kosuIptal(id).catch((e) => ({ hata: e.message }));
  if (r && r.hata) mesaj("uyari", (tr ? "Ayrıntılı koşu kesilemedi: " : "Detailed run could not be stopped: ") + r.hata);
  else mesaj("bilgi", tr ? "Ayrıntılı (OpenFOAM) koşu kesildi; hızlı testle devam ediliyor." : "Detailed (OpenFOAM) run stopped; continuing with the fast test.");
  S.ayrintili = null;
  IZ.kaynak = "hizli"; IZ.elle = false;
  agacYenile();
  await cozHizli();
}

/* Çözüm İzleyici / kuyruk: duraklat, devam, kes (onaylı) */
async function kosuKontrol(ne, id) {
  const tr = aTr();
  id = id || (S.ayrintili && S.ayrintili.id);
  if (!id) return;
  const bitti = (r) => { if (r && r.hata) Kabuk.bildir(r.hata, "hata"); izPoll(true); };
  if (ne === "duraklat") {
    const r = await API.kosuDuraklat(id).catch((e) => ({ hata: e.message }));
    if (!r.hata) { mesaj("bilgi", tr ? "Koşu duraklatıldı; çekirdekler boşaldı (bellek tutuluyor)." : "Run paused; cores released (memory kept)."); if (S.ayrintili && S.ayrintili.id === id) S.ayrintili.duraklatildi = true; }
    return bitti(r);
  }
  if (ne === "devam") {
    const r = await API.kosuDevam(id).catch((e) => ({ hata: e.message }));
    if (!r.hata) { mesaj("bilgi", tr ? "Koşu kaldığı yerden devam ediyor." : "Run resumed."); if (S.ayrintili && S.ayrintili.id === id) S.ayrintili.duraklatildi = false; }
    return bitti(r);
  }
  if (ne === "kes") {
    Kabuk.pencereAc({
      baslik: tr ? "Çözümü kes" : "Stop solve",
      ic: `<p>${esc(tr ? "Koşu sonlandırılacak; o ana kadar yazılan zaman adımları klasörde kalır ama analiz yapılmaz. Emin misiniz?" : "The run will be terminated; time steps written so far stay in the folder but no analysis is done. Are you sure?")}</p>`,
      dugmeler: [{ ad: tr ? "Kes" : "Stop", sinif: "tehlike", islev: async () => bitti(await API.kosuIptal(id).catch((e) => ({ hata: e.message }))) },
                 { ad: tr ? "Vazgeç" : "Cancel", sinif: "birincil" }],
    });
  }
}

/* ---- koşu takibi (izPoll'dan her turda) */
async function ayrintiliTakip(k) {
  (k.olaylar || []).forEach((o) => {
    if (o.tur !== "kaldirma") return;
    const m = (aTr() ? "Kaldırma denetimi (" : "Buoyancy check (") + o.ad + "): " + o.mesaj;
    mesaj(o.tamam === false ? "hata" : o.tamam ? "bilgi" : "uyari", m);
    Kabuk.bildir(m, o.tamam === false ? "hata" : o.tamam ? "basari" : "", o.tamam === false ? 15000 : 7000);
    if (S.ayrintili && S.ayrintili.id === o.id) S.ayrintili.kontrol = o;
  });
  const a = S.ayrintili;
  if (!a || a.durum === "bitti" || a.durum === "hata") return;
  const r = await API.ofmAyrintiliDurum(a.id).catch(() => null);
  if (!r || r.hata) return;
  a.ilerleme = r.ilerleme || a.ilerleme;
  a.duraklatildi = r.durum === "DURAKLADI";
  if (r.kontrol) a.kontrol = r.kontrol;
  if (r.durum === "TAMAM") {
    if (r.kayit && r.ofm) { a.durum = "bitti"; a.kayit = r.kayit; a.ofm = r.ofm; await ayrintiliSonucGeldi(); return; }
    if (r.ice_aktarma && String(r.ice_aktarma).indexOf("hata") === 0) { a.durum = "hata"; a.hata = r.ice_aktarma; mesaj("hata", (aTr() ? "Ayrıntılı koşu bitti ama analiz başarısız: " : "Detailed run finished but analysis failed: ") + r.ice_aktarma); agacYenile(); return; }
    a.durum = "iceAktariliyor";
  } else if (["İPTAL", "IRAKSADI", "DİSK DOLU"].indexOf(r.durum) >= 0) {
    a.durum = "hata"; a.hata = r.durum;
    mesaj("uyari", (aTr() ? "Ayrıntılı koşu sonlandı: " : "Detailed run ended: ") + r.durum);
    agacYenile();
  }
  ayrintiliBannerYaz();
}

async function ayrintiliSonucGeldi() {
  const a = S.ayrintili;
  mesaj("bilgi", (aTr() ? "Ayrıntılı (OpenFOAM) sonuç hazır: " : "Detailed (OpenFOAM) result ready: ") + a.kosu + " · " + (a.ofm.sonuc && a.ofm.sonuc.durum || ""));
  Kabuk.bildir(aTr() ? "Ayrıntılı çözüm bitti; sonuçlar Ayrıntılı (OpenFOAM) etiketiyle." : "Detailed solve finished; results are tagged Detailed (OpenFOAM).", "basari", 9000);
  if (!S.sonuc) await cozHizli(true);        // karşılaştırma için hızlı sonuç (ön tahmin kapalıysa şimdi)
  kirlet(true);
  agacYenile();
  if ((Kabuk.agacSecili() || "") === "cozum") Kabuk.agacSec("r-ozet");
  else if (/^r-/.test(Kabuk.agacSecili() || "")) gorselYenile();
}

/* ---- sonuç düğümlerinde: ön tahmin bandı, OpenFOAM ana sonuç, bekleme */
function ayrintiliBannerHtml() {
  const a = S.ayrintili, tr = aTr();
  if (!a || !(a.durum === "calisiyor" || a.durum === "iceAktariliyor")) return "";
  const p = a.ilerleme || {};
  const t = p.t == null ? "–" : Number(p.t).toPrecision(4);
  const kal = p.kalan_s == null ? "–" : aSure(p.kalan_s);
  return `<div class="ayr-banner" id="ayrBanner"><b>${esc(a.duraklatildi ? (tr ? "ön tahmin — ayrıntılı çözüm DURAKLATILDI" : "preliminary estimate — detailed solve PAUSED") : (tr ? "ön tahmin — ayrıntılı çözüm sürüyor" : "preliminary estimate — detailed solve in progress"))}</b> ` +
    `(t = ${esc(t)}${p.bitis_t ? " / " + esc(nf(p.bitis_t, 1)) + " s" : ""}, ${esc(tr ? "kalan" : "remaining")} ${esc(kal)}${a.durum === "iceAktariliyor" ? " · " + esc(tr ? "analiz yapılıyor" : "analysing") : ""})</div>`;
}
function ayrintiliBannerYaz() {
  const el = document.getElementById("ayrBanner");
  if (!el) return;
  const t = document.createElement("div"); t.innerHTML = ayrintiliBannerHtml();
  if (t.firstElementChild) el.innerHTML = t.firstElementChild.innerHTML; else el.remove();
}
/* ön tahmin kapalıyken sonuç düğümleri koşu bitene kadar yalnız bekleme ekranı gösterir */
function ayrintiliBekleGorseli(id) {
  if (!aAktif() || S.onTahmin || !/^r-/.test(id) || id === "r-llm" || id === "r-render" || id === "r-ofm") return null;
  Kabuk.gorselYaz(T("agac.ozet"), `<div class="gorunum ortala"><div class="bos"><b>${esc(aTr() ? "Ayrıntılı çözüm sürüyor" : "Detailed solve in progress")}</b>${esc(aTr() ? "Sonuçlar koşu bitince burada Ayrıntılı (OpenFOAM) etiketiyle görünür. Hızlı çözüm ön tahmini kapalı (Analiz Ayarları'ndan açılabilir)." : "Results appear here, tagged Detailed (OpenFOAM), when the run finishes. The fast preliminary estimate is off (enable it in Analysis Settings).")}</div></div></div>`);
  return true;
}

function ayrintiliGuven(b) {
  const d = b.dogrulama || {}, tr = aTr();
  return d.basari != null
    ? `<span class="etiket" style="color:var(--ok)">${esc(tr ? "deneyle doğrulandı" : "validated against experiment")} · ${esc(tr ? "başarı" : "success")} ${esc(nf(d.basari, 2))} (${esc(d.deney_adi || d.deney || "")})</span>`
    : `<span class="etiket uyari">${esc(tr ? "doğrulanmadı" : "not validated")}</span> <span class="sonuk">${esc(d.aciklama || (tr ? "bu koşul için deney karşılaştırması yok" : "no experiment comparison for this condition"))}</span>`;
}

/* Risk Özeti: ana sonuç OpenFOAM motorundan; risk modeli ve hızlı motor "karşılaştırma" olarak altta (mevcut görünüm) */
function ayrintiliOzetEkle() {
  const a = S.ayrintili, kap = document.querySelector("#gorsel .gorunum");
  if (!a || a.durum !== "bitti" || !a.ofm || !kap) return;
  const b = a.ofm, s = b.sonuc || {}, tr = aTr();
  const yandi = b.yandi === 1 ? (tr ? "YANDI" : "IGNITED") : b.yandi === 0 ? (s.durum === "tutuşmadı" ? (tr ? "TUTUŞMADI" : "NO IGNITION") : (tr ? "SÖNDÜ" : "EXTINGUISHED")) : (tr ? "BELİRSİZ" : "UNDETERMINED");
  const renk = b.yandi === 1 ? "var(--hata)" : b.yandi === 0 ? "var(--ok)" : "var(--uyari)";
  const durumMetin = s.durum || "–";
  const hiz = s.yayilma_hizi_mm_s == null ? (s.yayilma_hizi_aciklama || "–") : nf(s.yayilma_hizi_mm_s, 2) + " mm/s";
  const kontrol = a.kontrol ? `<div class="grafik-not">${esc((tr ? "Kaldırma denetimi: " : "Buoyancy check: ") + a.kontrol.mesaj)}</div>` : "";
  const blok = `<div class="kart ayr-ana"><h3>${esc(tr ? "Ana sonuç" : "Main result")} <span class="etiket">${esc(tr ? "Ayrıntılı (OpenFOAM)" : "Detailed (OpenFOAM)")}</span></h3>` +
    `<div class="risk-ust"><div class="risk-levha" style="border-color:${renk}"><div class="seviye" style="color:${renk}">${esc(yandi)}</div>` +
    (a.vekil || (a.kayit && a.kayit.vekil) ? `<div class="uyari-satir"><span>${esc(tr ? "Vekil koşu: OpenFOAM vakası yalnız SIBAL içindir; bu sonuç vaka malzemesi değil, aynı ortamda SIBAL içindir." : "Surrogate run: the OpenFOAM case covers SIBAL only; this result is for SIBAL in the same environment, not the case material.")}</span></div>` : "") +
    `<div class="sonuk" style="font-size:12px">${esc(durumMetin)} · ${esc(tr ? "koşu" : "run")} <b style="color:var(--yazi)">${esc(a.kosu)}</b> · ${esc(a.cekirdek)} ${esc(tr ? "çekirdek" : "cores")}</div></div>` +
    `<div class="kart"><table class="veri"><tbody>` +
    `<tr><td>${esc(tr ? "Tutuşma zamanı" : "Ignition time")}</td><td class="s">${esc(s.tutusma_zamani_s == null ? "–" : nf(s.tutusma_zamani_s, 2) + " s")}</td></tr>` +
    `<tr><td>${esc(tr ? "Alev yayılma hızı" : "Flame spread rate")}</td><td class="s">${esc(hiz)}</td></tr>` +
    `<tr><td>Tmax (${esc(tr ? "gaz" : "gas")})</td><td class="s">${esc(s.gaz_T_maks_K == null ? "–" : nf(s.gaz_T_maks_K, 0) + " K")}</td></tr>` +
    `<tr><td>${esc(tr ? "Benzetim süresi" : "Simulated time")}</td><td class="s">${esc(s.simulasyon_suresi_s == null ? "–" : nf(s.simulasyon_suresi_s, 2) + " s")}</td></tr>` +
    `</tbody></table></div></div>` +
    `<div class="bilgi-satir"><span class="etiket-ad" style="min-width:90px">${esc(tr ? "Güven" : "Confidence")}</span><span class="deger">${ayrintiliGuven(b)}</span></div>` +
    ((b.eksik || []).length ? `<div class="uyari-satir"><span>${esc((tr ? "Eksik çıktı: " : "Missing output: ") + b.eksik.join(" · "))}</span></div>` : "") + kontrol + `</div>` +
    `<h3 style="margin:14px 0 6px">${esc(tr ? "Karşılaştırma: risk modeli ve hızlı motor" : "Comparison: risk model and fast engine")}</h3>`;
  kap.insertAdjacentHTML("afterbegin", blok);
}

/* kayıtlı vakayı açarken: ayrıntılı koşu içe aktarılmışsa sonucu, hâlâ sürüyorsa takibi geri getirir */
async function ayrintiliGeriYukle(sv) {
  const r = await API.ofmKosuSonuc(sv.kosu).catch(() => null);
  if (r && r.kayit && r.ofm) {
    S.ayrintili = { id: sv.id, kosu: sv.kosu, dizin: r.kayit.gelen_yolu, durum: "bitti", kosul: r.kayit.kosullar, cekirdek: "–", bitis_s: null,
                    ilerleme: null, kontrol: null, kayit: r.kayit, ofm: r.ofm };
    agacYenile(); return;
  }
  if (sv.id) {
    const d = await API.ofmAyrintiliDurum(sv.id).catch(() => null);
    if (d && !d.hata && (d.durum === "ÇALIŞIYOR" || d.durum === "BEKLİYOR" || d.durum === "DURAKLADI")) {
      S.ayrintili = { id: sv.id, kosu: sv.kosu, durum: "calisiyor", kosul: null, cekirdek: "–", bitis_s: null, ilerleme: d.ilerleme, kontrol: d.kontrol, kayit: null, ofm: null };
      IZ.kaynak = sv.id; IZ.elle = true; agacYenile();
    }
  }
}
