"use strict";
/* AHUT FLARE — ayrıntılı OpenFOAM motoru arayüzü. Ayrı bir kaynak: hızlı motor ve model sayılarına dokunmaz.
   Düğüm "Ayrıntılı Motor (OpenFOAM)" · Motor Ayrıntıları'nda yan yana tablo · Kütüphane > Ayrıntılı koşular ·
   "OpenFOAM motoruyla koş" (Çözüm İzleyici kuyruğu). Veri: tahmin.ofm (en yakın koşu, mesafe <= 1,5) ve API.ofmKosular(). */

const bgTr = () => DIL === "tr";
const BG_TUR = { kati: ["katı", "solid"], sivi: ["sıvı", "liquid"], gaz: ["gaz", "gas"] };
const bgTurAd = (t) => (BG_TUR[t] ? BG_TUR[t][bgTr() ? 0 : 1] : t || "–");
const bgSayi = (v, d) => (v == null || v === "" ? "–" : nf(v, d == null ? 2 : d));
const bgBant = (g) => (g == null ? "–" : g < 0.01 ? (bgTr() ? "uzay (μg)" : "space (μg)") : g < 0.27 ? (bgTr() ? "Ay" : "Moon") : g < 0.6 ? "Mars" : (bgTr() ? "Dünya" : "Earth"));
const bgKosulMetni = (k) => k ? `g=${gMetni(k.g)} · %${bgSayi(k.oksijen, 1)} O₂ · ${bgSayi(k.basinc, 1)} kPa` +
  (k.akis ? ` · ${bgSayi(k.akis, 1)} cm/s` : "") + (k.kalinlik ? ` · ${bgSayi(k.kalinlik, 2)} mm` : "") : "–";

/* basit çizgi grafik: OpenFOAM eğrisi + (varsa) deney doğrusu */
function bgEgriSvg(egri) {
  if (!egri || !egri.x || egri.x.length < 2) return "";
  const W = 520, H = 170, k = 30;
  const xs = egri.x.slice(), ys = egri.y.slice();
  const ref = egri.deney_dogru || null;
  const tumx = xs.concat(ref ? ref.map((p) => p.x) : []), tumy = ys.concat(ref ? ref.map((p) => p.y) : []);
  const x0 = Math.min(...tumx), x1 = Math.max(...tumx), y0 = Math.min(...tumy), y1 = Math.max(...tumy);
  const X = (v) => k + (x1 > x0 ? (v - x0) / (x1 - x0) : 0) * (W - k - 8), Y = (v) => H - 22 - (y1 > y0 ? (v - y0) / (y1 - y0) : 0) * (H - 34);
  const yol = (px, py) => px.map((a, i) => X(a).toFixed(1) + "," + Y(py[i]).toFixed(1)).join(" ");
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:640px;background:var(--girdi);border:1px solid var(--cizgi)">` +
    `<polyline fill="none" stroke="var(--vurgu)" stroke-width="2" points="${yol(xs, ys)}"/>` +
    (ref ? `<polyline fill="none" stroke="var(--uyari)" stroke-width="1.6" stroke-dasharray="5 4" points="${ref.map((p) => X(p.x).toFixed(1) + "," + Y(p.y).toFixed(1)).join(" ")}"/>` : "") +
    `<text x="${k}" y="12" font-size="10" fill="var(--sonuk)">${esc(egri.ad)} — ${esc(bgTr() ? "OpenFOAM (düz)" : "OpenFOAM (solid)")}${ref ? " · " + esc(bgTr() ? "deney eğimi (kesik)" : "experiment slope (dashed)") : ""}</text>` +
    `<text x="${k}" y="${H - 6}" font-size="10" fill="var(--cok-sonuk)">${esc(nf(x0, 2))}</text><text x="${W - 8}" y="${H - 6}" font-size="10" text-anchor="end" fill="var(--cok-sonuk)">${esc(nf(x1, 2))}</text>` +
    `<text x="4" y="${H - 24}" font-size="10" fill="var(--cok-sonuk)">${esc(nf(y0, 1))}</text><text x="4" y="22" font-size="10" fill="var(--cok-sonuk)">${esc(nf(y1, 1))}</text></svg>`;
}

function bgDogrulamaTablosu(d) {
  if (!d) return "";
  const tr = bgTr();
  const satir = (o) => `<tr><td>${esc(o.ad)}</td><td class="s">${esc(bgSayi(o.ofm, 3))} ${esc(o.birim || "")}</td><td class="s">${esc(typeof o.deney === "number" ? bgSayi(o.deney, 3) : (o.deney == null ? "–" : o.deney))}</td>` +
    `<td class="s">${esc(o.tolerans || "")}</td><td>${o.tuttu == null ? "–" : o.tuttu ? `<span class="yandi">${tr ? "tuttu" : "within"}</span>` : `<span class="sondu">${tr ? "tutmadı" : "outside"}</span>`}</td></tr>`;
  return `<table class="veri"><thead><tr><th>${tr ? "Ölçü" : "Measure"}</th><th class="s">OpenFOAM</th><th class="s">${tr ? "Deney" : "Experiment"}</th><th class="s">${tr ? "Tolerans" : "Tolerance"}</th><th></th></tr></thead><tbody>` +
    (d.olculer || []).map(satir).join("") + `</tbody></table>`;
}

function bgSonucSatirlari(s, tur) {
  if (!s) return [];
  const tr = bgTr(), r = [];
  r.push([tr ? "Durum" : "Status", s.durum || "–"]);
  r.push([tr ? "Tutuşma zamanı" : "Ignition time", s.tutusma_zamani_s == null ? "–" : bgSayi(s.tutusma_zamani_s, 2) + " s"]);
  r.push([tr ? "Tmax (gaz)" : "Tmax (gas)", s.gaz_T_maks_K == null ? "–" : bgSayi(s.gaz_T_maks_K, 0) + " K"]);
  r.push([tr ? "Benzetim süresi" : "Simulated time", s.simulasyon_suresi_s == null ? "–" : bgSayi(s.simulasyon_suresi_s, 2) + " s"]);
  if (tur === "kati") {
    r.push([tr ? "Alev yayılma hızı" : "Flame spread rate", s.yayilma_hizi_mm_s == null ? (s.yayilma_hizi_aciklama || "–") : bgSayi(s.yayilma_hizi_mm_s, 2) + " mm/s"]);
    r.push([tr ? "Tel (ateşleyici) Tmax" : "Igniter Tmax", s.tel_T_maks_K == null ? "–" : bgSayi(s.tel_T_maks_K, 0) + " K"]);
  } else if (tur === "sivi") {
    r.push([tr ? "K (yanma hızı sabiti)" : "K (burning rate)", s.K_mm2_s == null ? "–" : bgSayi(s.K_mm2_s, 3) + " mm²/s"]);
    r.push([tr ? "Sönme çapı" : "Extinction diameter", s.sonme_capi_mm == null ? "–" : bgSayi(s.sonme_capi_mm, 3) + " mm"]);
    r.push([tr ? "Alev yarıçapı (maks)" : "Flame radius (max)", s.alev_yaricapi_maks_mm == null ? "–" : bgSayi(s.alev_yaricapi_maks_mm, 2) + " mm"]);
  } else if (tur === "gaz") {
    r.push([tr ? "Alev boyu" : "Flame length", s.alev_boyu_mm == null ? "–" : bgSayi(s.alev_boyu_mm, 1) + " mm"]);
    r.push([tr ? "Alev yarıçapı" : "Flame radius", s.alev_yaricapi_mm == null ? "–" : bgSayi(s.alev_yaricapi_mm, 1) + " mm"]);
  }
  return r;
}

/* ---- "Ayrıntılı Motor (OpenFOAM)" düğümü */
function ofmGorseli() {
  const tr = bgTr(), t = S.sonuc && S.sonuc.tahmin, b = (S.ayrintili && S.ayrintili.ofm) || (t && t.ofm);
  const dugme = `<button class="dugme birincil" data-komut="ofm-kos">${esc(tr ? "OpenFOAM motoruyla koş…" : "Run with OpenFOAM engine…")}</button>`;
  if (!b) {
    return Kabuk.gorselYaz(T("agac.ofm"), `<div class="gorunum ortala"><div class="bos"><b>${esc(tr ? "Bu koşulda ayrıntılı koşu yok" : "No detailed run for this condition")}</b>` +
      esc(tr ? "Aynı malzeme ve yakıt türünde, mesafesi ≤ 1,5 olan içe aktarılmış OpenFOAM koşusu bulunamadı. Hızlı motor ve model sonuçları değişmedi." :
               "No imported OpenFOAM run of the same material and fuel type within distance ≤ 1.5. Fast-engine and model results are unchanged.") +
      `<div style="margin-top:12px">${dugme}</div></div></div>`);
  }
  const tur = b.yakit_turu, k = b.kosullar || {}, g = t.girdi;
  const fark = (a, c, d) => (a == null || c == null ? "–" : (a - c >= 0 ? "+" : "") + nf(a - c, d));
  const kosulTablo = `<table class="veri"><thead><tr><th></th><th class="s">${tr ? "Vaka" : "Case"}</th><th class="s">${tr ? "OpenFOAM koşusu" : "OpenFOAM run"}</th><th class="s">Δ</th></tr></thead><tbody>` +
    `<tr><td>g</td><td class="s">${esc(gMetni(g.g))} (${esc(bgBant(g.g))})</td><td class="s">${esc(gMetni(k.g))} (${esc(bgBant(k.g))})</td><td class="s"></td></tr>` +
    `<tr><td>O₂ %</td><td class="s">${esc(bgSayi(g.oksijen, 1))}</td><td class="s">${esc(bgSayi(k.oksijen, 1))}</td><td class="s">${esc(fark(k.oksijen, g.oksijen, 1))}</td></tr>` +
    `<tr><td>${tr ? "Basınç" : "Pressure"} kPa</td><td class="s">${esc(bgSayi(g.basinc, 1))}</td><td class="s">${esc(bgSayi(k.basinc, 1))}</td><td class="s">${esc(fark(k.basinc, g.basinc, 1))}</td></tr>` +
    `<tr><td>${tr ? "Akış" : "Flow"} cm/s</td><td class="s">${esc(bgSayi(g.akis || 0, 1))}</td><td class="s">${esc(bgSayi(k.akis || 0, 1))}</td><td class="s">${esc(fark(k.akis || 0, g.akis || 0, 1))}</td></tr>` +
    `<tr><td>${tur === "sivi" ? (tr ? "Çap" : "Diameter") : (tr ? "Kalınlık" : "Thickness")} mm</td><td class="s">${esc(bgSayi(g.kalinlik, 2))}</td><td class="s">${esc(bgSayi(k.kalinlik, 2))}</td><td class="s"></td></tr></tbody></table>`;
  const sonuc = `<table class="veri"><tbody>` + bgSonucSatirlari(b.sonuc, tur).map((x) => `<tr><td>${esc(x[0])}</td><td class="s">${esc(x[1])}</td></tr>`).join("") + `</tbody></table>`;
  const dg = b.dogrulama || {};
  const w = b.agirlik || 0;
  const durumKutu = w > 0
    ? `<div class="grafik-not">${esc(tr ? `Birleşik ihtimale katılıyor: ağırlık ${nf(w, 2)} = doğrulama başarısı × (1 − mesafe/1,5), tavan 0,5.` : `Included in the combined probability: weight ${nf(w, 2)} = validation success × (1 − distance/1.5), capped at 0.5.`)}</div>`
    : `<div class="uyari-satir"><span>${esc(b.uyari || (tr ? "Ayrıntılı motor bu koşulda doğrulanmadı." : "The detailed engine is not validated for this condition."))}</span></div>`;
  const eksik = (b.eksik || []).length ? `<div class="uyari-satir"><span><b>${esc(tr ? "Eksik çıktı (uydurulmadı):" : "Missing output (not invented):")}</b> ${esc(b.eksik.join(" · "))}</span></div>` : "";
  const render = (b.render || []).length
    ? `<div class="grafik-not">${esc(tr ? "Render dosyaları" : "Render files")}: ` + b.render.map((r) => `<a href="#" data-bg-render="${esc(r)}">${esc(r)}</a>`).join(" · ") + `</div>` : "";
  Kabuk.gorselYaz(T("agac.ofm"),
    `<div class="gorunum"><div class="kutular k2">` +
    `<div class="kart"><h3>${esc(tr ? "En yakın OpenFOAM koşusu" : "Nearest OpenFOAM run")}</h3>` +
    `<div class="bilgi-satir"><span class="etiket-ad" style="min-width:150px">${esc(tr ? "Koşu" : "Run")}</span><span class="deger"><b>${esc(b.kosu)}</b></span></div>` +
    `<div class="bilgi-satir"><span class="etiket-ad" style="min-width:150px">${esc(tr ? "Tür · boyut" : "Type · dim.")}</span><span class="deger">${esc(bgTurAd(tur))} · ${esc(b.boyut || "–")} · ${esc(b.malzeme)}</span></div>` +
    `<div class="bilgi-satir"><span class="etiket-ad" style="min-width:150px">${esc(tr ? "Mesafe" : "Distance")}</span><span class="deger sayi">${esc(nf(b.mesafe, 2))}</span><span class="sonuk" style="margin-left:auto">≤ 1,5</span></div>` +
    `<div class="bilgi-satir"><span class="etiket-ad" style="min-width:150px">${esc(tr ? "Birleşik ağırlığı" : "Combined weight")}</span><span class="deger sayi">${esc(nf(w, 2))}</span></div>` +
    durumKutu + eksik + `<div style="margin-top:10px">${dugme}</div></div>` +
    `<div class="kart"><h3>${esc(tr ? "Koşullar" : "Conditions")}</h3><div class="tablo-kap" style="border:0">${kosulTablo}</div></div>` +
    `<div class="kart"><h3>${esc(tr ? "Sonuçlar" : "Results")}</h3><div class="tablo-kap" style="border:0">${sonuc}</div></div>` +
    `<div class="kart"><h3>${esc(tr ? "Deneyle karşılaştırma" : "Comparison with experiment")}</h3>` +
    `<div class="sonuk" style="margin-bottom:6px">${esc(dg.deney_adi || dg.deney || (tr ? "deney yok" : "no experiment"))} · ${esc(dg.aciklama || "")}${dg.basari == null ? "" : " · " + esc(tr ? "başarı " : "success ") + esc(nf(dg.basari, 2))}</div>` +
    `<div class="tablo-kap" style="border:0">${bgDogrulamaTablosu(dg)}</div>${bgEgriSvg(b.egri)}</div></div>${render}` +
    `<div class="grafik-not">${esc(tr ? "Ayrıntılı OpenFOAM koşusu; yönlendirici yalnız bu koşu yakın ve deneyle doğrulanmışsa birleşik ihtimale katar." : "Detailed OpenFOAM run; the router includes it only when the run is near and validated against experiment.")}</div></div>`,
    "", ofmTablo(b, g, tr));
}
/* Tablo Verisi: koşullar (vaka ↔ OpenFOAM) ve OpenFOAM çıktıları tek tabloda */
function ofmTablo(b, g, tr) {
  const k = b.kosullar || {}, kal = b.yakit_turu === "sivi" ? (tr ? "Çap" : "Diameter") : (tr ? "Kalınlık" : "Thickness");
  const kos = tr ? "Koşul" : "Condition", cik = tr ? "Çıktı" : "Output";
  const r = [[kos, "g", "g₀", g.g, k.g], [kos, "O₂", "%", g.oksijen, k.oksijen], [kos, tr ? "Basınç" : "Pressure", "kPa", g.basinc, k.basinc],
    [kos, tr ? "Akış" : "Flow", "cm/s", g.akis || 0, k.akis || 0], [kos, kal, "mm", g.kalinlik, k.kalinlik]];
  bgSonucSatirlari(b.sonuc, b.yakit_turu).forEach((x) => r.push([cik, x[0], "", null, x[1]]));
  return { ad: "ofm_" + (b.kosu || "kosu"), sutunlar: [{ ad: tr ? "Grup" : "Group", birim: "", d: null }, { ad: tr ? "Büyüklük" : "Quantity", birim: "", d: null },
    { ad: tr ? "Birim" : "Unit", birim: "", d: null }, { ad: tr ? "Vaka" : "Case", birim: "", d: null }, { ad: tr ? "OpenFOAM koşusu" : "OpenFOAM run", birim: "", d: null }],
    satirlar: r };
}
document.addEventListener("click", (e) => {
  const a = e.target.closest("[data-bg-render]");
  if (!a) return;
  e.preventDefault(); S.renderSecili = a.dataset.bgRender; Kabuk.agacSec("r-render");
});

/* ---- Motor Ayrıntıları: hızlı motor ↔ OpenFOAM ↔ deney (yan yana) */
function ofmYanYana(t) {
  const tr = bgTr(), b = (S.ayrintili && S.ayrintili.ofm) || t.ofm, m = t.motor || {};
  if (!b) return `<div class="kart"><h3>${esc(tr ? "Hızlı motor ↔ OpenFOAM motoru ↔ deney" : "Fast engine ↔ OpenFOAM engine ↔ experiment")}</h3><div class="sonuk">${esc(tr ? "Bu koşulda ayrıntılı koşu yok." : "No detailed run for this condition.")}</div></div>`;
  const s = b.sonuc || {}, o = {};
  (b.dogrulama && b.dogrulama.olculer || []).forEach((x) => { o[x.ad] = x; });
  const hiz = (v, d, u) => (v == null ? "–" : nf(v, d) + (u ? " " + u : ""));
  const dn = (ad, d, u) => (o[ad] && typeof o[ad].deney === "number" ? nf(o[ad].deney, d) + (u ? " " + u : "") : (o[ad] && o[ad].deney ? String(o[ad].deney) : "–"));
  const r = [
    [tr ? "Yanma" : "Burning", m.yanma == null ? "–" : "%" + nf(m.yanma * 100, 1), s.durum || "–", (b.dogrulama && b.dogrulama.deney && b.dogrulama.deney !== "yok") ? (tr ? "bkz. karşılaştırma" : "see comparison") : "–"],
    [tr ? "Tmax" : "Tmax", hiz(m.sicaklik, 0, "K"), hiz(s.gaz_T_maks_K, 0, "K"), "–"],
    [tr ? "Yayılma hızı" : "Spread rate", hiz(m.yayilma_hizi, 2, "mm/s"), hiz(s.yayilma_hizi_mm_s, 2, "mm/s"), dn("yayılma hızı", 2, "mm/s")],
    ["K", hiz(m.yanma_hizi_K, 3, "mm²/s"), hiz(s.K_mm2_s, 3, "mm²/s"), dn("K", 3, "mm²/s")],
    [tr ? "Sönme çapı" : "Extinction diameter", hiz(m.sonme_capi, 3, "mm"), hiz(s.sonme_capi_mm, 3, "mm"), dn("sönme çapı", 3, "mm")],
    [tr ? "Alev boyu" : "Flame length", hiz(m.alev_boyu, 1, "mm"), hiz(s.alev_boyu_mm, 1, "mm"), "–"],
    [tr ? "Alev yarıçapı" : "Flame radius", hiz(m.alev_yaricapi, 1, "mm"), hiz(s.alev_yaricapi_mm != null ? s.alev_yaricapi_mm : s.alev_yaricapi_maks_mm, 1, "mm"), "–"],
  ].filter((x) => x.slice(1).some((v) => v !== "–"));
  return `<div class="kart"><h3>${esc(tr ? "Hızlı motor ↔ OpenFOAM motoru ↔ deney" : "Fast engine ↔ OpenFOAM engine ↔ experiment")}</h3><div class="tablo-kap" style="border:0"><table class="veri"><thead><tr><th></th><th class="s">${esc(tr ? "Hızlı motor" : "Fast engine")}</th><th class="s">OpenFOAM</th><th class="s">${esc(tr ? "Deney" : "Experiment")}</th></tr></thead><tbody>` +
    r.map((x) => `<tr><td>${esc(x[0])}</td><td class="s">${esc(x[1])}</td><td class="s">${esc(x[2])}</td><td class="s">${esc(x[3])}</td></tr>`).join("") +
    `</tbody></table></div><div class="grafik-not">${esc(tr ? "OpenFOAM: " : "OpenFOAM: ")}${esc(b.kosu)} · ${esc(tr ? "mesafe " : "distance ")}${esc(nf(b.mesafe, 2))} · ${esc(tr ? "ağırlık " : "weight ")}${esc(nf(b.agirlik || 0, 2))}</div></div>`;
}

/* ---- Kütüphane > Ayrıntılı koşular */
async function ofmKutuphaneCiz() {
  const tr = bgTr();
  let v = { kosular: [] };
  try { v = await API.ofmKosular(); } catch (e) { v = { kosular: [], hata: e.message }; }
  const l = v.kosular || [];
  if (!l.length) return `<div class="bos"><b>${esc(tr ? "Henüz ayrıntılı koşu yok" : "No detailed runs yet")}</b>${esc(tr ? "OpenFOAM koşu klasörleri ofm_ice_aktar.py ile içe aktarılınca burada listelenir." : "OpenFOAM run folders appear here after ofm_ice_aktar.py imports them.")}${v.hata ? `<div class="uyari-satir"><span>${esc(v.hata)}</span></div>` : ""}</div>`;
  return `<div class="tablo-kap"><table class="veri"><thead><tr><th>${tr ? "Koşu" : "Run"}</th><th>${tr ? "Tür" : "Type"}</th><th>${tr ? "Malzeme" : "Material"}</th><th>${tr ? "Boyut" : "Dim."}</th><th>${tr ? "Koşullar" : "Conditions"}</th><th>${tr ? "Durum" : "Status"}</th><th>${tr ? "Deney" : "Experiment"}</th><th class="s">${tr ? "Başarı" : "Success"}</th><th class="s">Render</th><th>${tr ? "İçe aktarma" : "Imported"}</th></tr></thead><tbody>` +
    l.map((x) => `<tr><td><b>${esc(x.kosu)}</b></td><td>${esc(bgTurAd(x.yakit_turu))}</td><td>${esc(x.malzeme)}</td><td>${esc(x.boyut || "")}</td><td class="tek">${esc(bgKosulMetni(x.kosullar))}</td>` +
      `<td>${esc((x.sonuc && x.sonuc.durum) || "–")}</td><td>${esc((x.dogrulama && x.dogrulama.deney) || "yok")}</td>` +
      `<td class="s">${x.dogrulama && x.dogrulama.basari != null ? esc(nf(x.dogrulama.basari, 2)) : "–"}</td><td class="s">${esc((x.render || []).length)}</td><td class="tek">${esc(x.ice_aktarma || "")}</td></tr>`).join("") +
    `</tbody></table></div><div class="grafik-not">${esc(tr ? "Dizin: " : "Index: ")}${esc(v.kok || "")}</div>`;
}

/* ---- "OpenFOAM motoruyla koş": kuyruğa ekler (Çözüm İzleyici); sıvı/gaz vakaları gelince eklenecek */
async function ofmKosDialog() {
  const tr = bgTr();
  let k;
  try { k = await API.ofmKosKontrol("kati"); } catch (e) { return Kabuk.bildir(e.message, "hata"); }
  const uyarilar = (k.uyarilar || []).map((u) => `<div class="uyari-satir"><span>${esc(u)}</span></div>`).join("");
  Kabuk.pencereAc({
    baslik: tr ? "OpenFOAM motoruyla koş" : "Run with OpenFOAM engine",
    ic: k.hazir
      ? `<p><b>${esc(tr ? "Katı: Saffire-III S1 (kilitli motor, 10 s)" : "Solid: Saffire-III S1 (locked engine, 10 s)")}</b></p>` +
        `<p class="sonuk">${esc(k.sure_uyarisi || "")}</p>${uyarilar}` +
        `<p class="sonuk">${esc(tr ? `En çok ${k.cekirdek} çekirdek, düşük öncelik. Koşu Çözüm İzleyici kuyruğuna eklenir; bitince BILGI.json ile içe aktarılabilir (ofm_ice_aktar.py). Sıvı ve gaz vakaları OpenFOAM motorundan gelince eklenecek.` : `At most ${k.cekirdek} cores, low priority. The run is added to the Solution Monitor queue. Liquid and gas cases will be added when OpenFOAM delivers them.`)}</p>`
      : `<div class="uyari-satir"><span>${esc(k.neden || (tr ? "Hazır değil." : "Not ready."))}</span></div>`,
    dugmeler: k.hazir
      ? [{ ad: tr ? "Kuyruğa ekle" : "Add to queue", sinif: "birincil", islev: async () => {
            const r = await API.ofmKosBaslat("kati").catch((e) => ({ hata: e.message }));
            if (r && r.hata) Kabuk.bildir(r.hata, "hata", 9000);
            else { mesaj("bilgi", (tr ? "OpenFOAM koşusu kuyruğa eklendi: " : "OpenFOAM run queued: ") + r.dizin); Kabuk.agacSec("cozum"); izPoll(true); }
          } }, { ad: tr ? "Vazgeç" : "Cancel" }]
      : [{ ad: tr ? "Tamam" : "OK" }],
  });
}
