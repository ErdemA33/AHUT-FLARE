"use strict";
/* AHUT FLARE — Çözüm İzleyici (ANSYS Fluent "Solution Monitor" benzeri).
   Üst: canlı günlük · orta: izleme grafikleri (OpenFOAM koşusu varsa) · alt: koşu kuyruğu ve çözüm geçmişi.
   Hafiflik: yoklama 1,5 s; günlük DOM'a yalnız yeni satır eklenerek yazılır (tamamı yeniden çizilmez);
   izleyici görünür değilken yalnız koşu listesi (3. tikte bir) yoklanır. Backend sayılarına dokunulmaz:
   hızlı çözümün adım akışı tahmin.adimlar'dan, OpenFOAM akışı günlük dosyalarından (Python izleyici.py) gelir. */

const IZ = {
  kaynak: "hizli", elle: false, oto: true, sev: "hepsi", ara: "",
  log: { hizli: [] }, ofset: {}, seri: {}, ozet: {},
  kosular: [], kaynaklar: [], bekle: false, tik: 0, bildirilen: {}, ilkKosuListesi: true,
};
const IZ_SEV = { bilgi: 0, uyari: 1, hata: 2 };
const IZ_EN_FAZLA = 1500;
const izTr = () => DIL === "tr";
const izSaat = () => new Date().toLocaleTimeString(izTr() ? "tr-TR" : "en-US", { hour12: false });

/* ---------------------------------------------------------------- günlük satırları */
function izSatirEkle(kaynak, r) {
  const d = IZ.log[kaynak] || (IZ.log[kaynak] = []);
  r.saat = r.saat || izSaat();
  d.push(r);
  if (d.length > IZ_EN_FAZLA) d.splice(0, d.length - IZ_EN_FAZLA);
  if (kaynak === IZ.kaynak) izSatirCiz(r);
}

/* Hızlı çözümün akışı: tahmin.adimlar yanıt gelir gelmez satır satır (≈45 ms arayla) yazılır. */
function izHizliBaslat(k) {
  izSatirEkle("hizli", { seviye: "bilgi", kosu: izTr() ? "hızlı" : "fast",
    metin: (izTr() ? "çözüm başladı: " : "solve started: ") + `${k.malzeme} · g=${gMetni(k.g)} · %${nf(k.oksijen, 1)} O₂ · ${nf(k.basinc, 1)} kPa` });
}
function izHizliAkit(t, hata) {
  const kosu = izTr() ? "hızlı" : "fast";
  if (hata) return izSatirEkle("hizli", { seviye: "hata", kosu, metin: String(hata) });
  const sat = [];
  (t && t.adimlar ? t.adimlar.slice().sort((a, b) => a.no - b.no) : []).forEach((a) =>
    sat.push({ seviye: "bilgi", kosu, adim: a.no, ad: a.ad, sure: a.sure_ms, karar: a.karar,
               metin: `${a.no}. ${a.ad} · ${nf(a.sure_ms, 1)} ms · ${a.karar}` }));
  if (t && t.uyarilar) uyarilarGoster(t).forEach((u) => sat.push({ seviye: "uyari", kosu, metin: u }));
  sat.push({ seviye: "bilgi", kosu, metin: (izTr() ? "çözüm bitti: " : "solve finished: ") + nf(t && t.sure_sn, 2) + " s" +
    (t && t.risk_seviyesi ? " · " + t.risk_seviyesi : "") });
  sat.forEach((r, i) => setTimeout(() => izSatirEkle("hizli", r), 45 * i));
}

const izUygun = (r) => (IZ.sev === "hepsi" || IZ_SEV[r.seviye] >= IZ_SEV[IZ.sev]) &&
  (!IZ.ara || (r.saat + " " + (r.kosu || "") + " " + r.metin).toLowerCase().indexOf(IZ.ara) >= 0);

function izSatirHtml(r) {
  let ic;
  if (r.satir) {                                   // OpenFOAM adım satırı: saat | koşu | adım | t | % | Δt | Tmax | Co | kalan
    const o = r.satir, f = (v, d) => (v == null ? "–" : nf(v, d));
    const kal = o.kalan == null ? "–" : o.kalan < 86400 ? new Date(o.kalan * 1000).toISOString().substr(11, 8) : nf(o.kalan / 3600, 0) + (izTr() ? " sa" : " h");
    ic = `<span class="c">${esc(o.adim)}</span><span class="c">${esc(o.t == null ? "–" : Number(o.t).toPrecision(6))}</span><span class="c">${esc(f(o.yuzde, 1))}</span>` +
      `<span class="c">${esc(o.dt == null ? "–" : Number(o.dt).toPrecision(3))}</span><span class="c">${esc(o.tmax == null ? "–" : Number(o.tmax).toFixed(1))}</span>` +
      `<span class="c">${esc(o.co == null ? "–" : Number(o.co).toPrecision(3))}</span><span class="c">${esc(kal)}</span>`;
  } else if (r.ad) {                               // hızlı çözüm adımı: adım | ad | süre | karar
    ic = `<span class="c">${esc(r.adim)}</span><span class="m">${esc(r.ad)}</span><span class="c">${esc(nf(r.sure, 1))} ms</span><span class="m k">${esc(r.karar)}</span>`;
  } else ic = `<span class="m k">${esc(r.metin)}</span>`;
  return `<div class="izs ${esc(r.seviye)}${r.satir ? " foam" : ""}"><span class="z">${esc(r.saat)}</span><span class="ko">${esc(r.kosu || "")}</span>${ic}</div>`;
}

function izSatirCiz(r) {
  const kap = document.getElementById("izLog");
  if (!kap || !izUygun(r)) return;
  const yer = kap.querySelector(".izbos"); if (yer) yer.remove();
  kap.insertAdjacentHTML("beforeend", izSatirHtml(r));
  while (kap.childElementCount > 800) kap.firstElementChild.remove();
  if (IZ.oto) kap.scrollTop = kap.scrollHeight;
}

function izLogYenidenCiz() {
  const kap = document.getElementById("izLog");
  if (!kap) return;
  const l = (IZ.log[IZ.kaynak] || []).filter(izUygun).slice(-800);
  kap.innerHTML = l.length ? l.map(izSatirHtml).join("")
    : `<div class="izbos">${esc(S.sonuc || IZ.kaynak !== "hizli" ? (izTr() ? "Bu süzgeçle satır yok." : "No lines match.") : T("sonuc.yokHenuzAlt"))}</div>`;
  if (IZ.oto) kap.scrollTop = kap.scrollHeight;
}

/* ---------------------------------------------------------------- iskelet */
function izleyiciGoster() {
  const kok = document.getElementById("izKok");
  if (document.getElementById("izLog") && kok && kok.dataset.dil === DIL) { izDurumCiz(); return; }   // iskelet var: yalnız güncelle
  const tr = izTr();
  Kabuk.gorselYaz(T("agac.cozum"),
    `<div class="gorunum izk" id="izKok" data-dil="${esc(DIL)}">` +
    `<div id="izDurum" class="izkart"></div>` +
    `<div class="izarac"><select class="giris" id="izKaynak" title="${esc(tr ? "Günlük kaynağı" : "Log source")}"></select>` +
    `<select class="giris" id="izSev"><option value="hepsi">${esc(tr ? "tüm seviyeler" : "all levels")}</option><option value="uyari">${esc(tr ? "uyarı ve hata" : "warnings+errors")}</option><option value="hata">${esc(tr ? "yalnız hata" : "errors only")}</option></select>` +
    `<input class="giris" id="izAra" type="search" placeholder="${esc(tr ? "günlükte ara" : "search log")}" style="width:150px">` +
    `<button class="dugme kucuk" id="izOto"></button>` +
    `<button class="dugme kucuk" id="izKopya">${esc(tr ? "Kopyala" : "Copy")}</button>` +
    `<button class="dugme kucuk" id="izAc">${esc(tr ? "Günlük dosyasını aç" : "Open log file")}</button></div>` +
    `<div class="izbas" id="izBas"></div>` +
    `<div id="izLog" class="izlog" tabindex="0"></div>` +
    `<div id="izGraf"></div>` +
    `<div style="display:flex;align-items:center;gap:10px"><h3 class="izb" style="margin:8px 0 0">${esc(tr ? "Koşu kuyruğu" : "Run queue")}</h3><button class="dugme kucuk" data-komut="ofm-kos" style="margin-top:6px">${esc(tr ? "OpenFOAM motoruyla koş…" : "Run with OpenFOAM engine…")}</button>` +
    `<button class="dugme kucuk" id="izDogrulama" style="margin-top:6px">${esc(tr ? "Sıvı doğrulama (FLEX)…" : "Liquid validation (FLEX)…")}</button></div><div id="izKuyruk"></div>` +
    `<h3 class="izb">${esc(tr ? "Çözüm geçmişi (son 20)" : "Solve history (last 20)")}</h3><div id="izGecmis"></div></div>`);
  const sec = document.getElementById("izKaynak");
  sec.addEventListener("change", () => { IZ.kaynak = sec.value; IZ.elle = true; izKaynakDegisti(); });
  document.getElementById("izSev").value = IZ.sev;
  document.getElementById("izSev").addEventListener("change", (e) => { IZ.sev = e.target.value; izLogYenidenCiz(); });
  const ara = document.getElementById("izAra"); ara.value = IZ.ara;
  ara.addEventListener("input", () => { IZ.ara = ara.value.trim().toLowerCase(); izLogYenidenCiz(); });
  document.getElementById("izOto").addEventListener("click", () => { IZ.oto = !IZ.oto; izOtoYaz(); if (IZ.oto) izLogYenidenCiz(); });
  document.getElementById("izKopya").addEventListener("click", izKopyala);
  document.getElementById("izAc").addEventListener("click", async () => {
    if (IZ.kaynak === "hizli") return Kabuk.bildir(izTr() ? "Hızlı çözümün günlüğü bellekte; Kopyala ile alın." : "The fast-solve log lives in memory; use Copy.", "bilgi");
    const r = await API.kosuLogAc(IZ.kaynak).catch((e) => ({ hata: e.message }));
    if (r && r.hata) Kabuk.bildir(r.hata, "hata");
  });
  document.getElementById("izDogrulama").addEventListener("click", dogrulamaPenceresi);
  document.getElementById("izKok").addEventListener("click", (e) => {          // kuyruk satırları ve durum kartı
    const b = e.target.closest("[data-iz-kontrol]"); if (!b) return;
    kosuKontrol(b.dataset.izKontrol, b.dataset.izId);
  });
  izOtoYaz(); izKaynakDoldur(); izLogYenidenCiz(); izDurumCiz(); izGrafCiz(); izKuyrukCiz(); izGecmisCiz();
  izPoll(true);
}

function izOtoYaz() {
  const b = document.getElementById("izOto");
  if (b) b.textContent = IZ.oto ? (izTr() ? "Kaydırma: açık (durdur)" : "Autoscroll: on (pause)") : (izTr() ? "Kaydırma: durdu (devam)" : "Autoscroll: paused (resume)");
}

function izKaynakDoldur() {
  const sec = document.getElementById("izKaynak");
  if (!sec) return;
  const L = [{ id: "hizli", ad: izTr() ? "Hızlı çözüm (bu oturum)" : "Fast solve (this session)" }]
    .concat(IZ.kaynaklar.map((k) => ({ id: k.id, ad: (k.tur === "canli" ? "📄 " : k.durum === "ÇALIŞIYOR" ? "● " : "") + k.ad })));
  const imza = L.map((x) => x.id + x.ad).join("|") + IZ.kaynak;
  if (sec.dataset.imza === imza) return;
  sec.dataset.imza = imza;
  sec.innerHTML = L.map((x) => `<option value="${esc(x.id)}"${x.id === IZ.kaynak ? " selected" : ""}>${esc(x.ad)}</option>`).join("");
}

function izKaynakDegisti() {
  IZ.ofset[IZ.kaynak] = null; IZ.log[IZ.kaynak] = IZ.kaynak === "hizli" ? IZ.log.hizli : [];
  izLogYenidenCiz(); izDurumCiz(); izGrafCiz();
  if (IZ.kaynak !== "hizli") izPoll(true, true);
}

function izKopyala() {
  const m = (IZ.log[IZ.kaynak] || []).filter(izUygun).map((r) => r.saat + " | " + (r.kosu || "") + " | " + r.metin).join("\n");
  const bitti = () => Kabuk.bildir(izTr() ? "Günlük panoya kopyalandı." : "Log copied to clipboard.", "basari", 2500);
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(m).then(bitti, () => izKopyaYedek(m, bitti));
  else izKopyaYedek(m, bitti);
}
function izKopyaYedek(m, bitti) {
  const t = document.createElement("textarea"); t.value = m; t.style.position = "fixed"; t.style.opacity = "0";
  document.body.appendChild(t); t.select(); try { document.execCommand("copy"); bitti(); } catch (e) {} t.remove();
}

/* ---------------------------------------------------------------- durum kartı, grafikler, tablolar */
function izDurumCiz() {
  const kap = document.getElementById("izDurum"), bas = document.getElementById("izBas");
  if (!kap) return;
  const tr = izTr(), o = IZ.kaynak !== "hizli" ? IZ.ozet[IZ.kaynak] : null;
  let baslik, yuzde, alt;
  if (o) {
    const k = IZ.kosular.find((x) => x.id === IZ.kaynak);
    baslik = (k ? k.ad : IZ.kaynak) + (k ? " — " + k.durum : "");
    yuzde = o.yuzde == null ? 0 : o.yuzde;
    const bit = o.bitis_saati ? new Date(o.bitis_saati * 1000).toLocaleString(tr ? "tr-TR" : "en-US", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" }) : "–";
    alt = `${tr ? "t" : "t"} = ${o.t == null ? "–" : Number(o.t).toPrecision(5)} / ${o.bitis_t == null ? "?" : o.bitis_t} s · ` +
      `${tr ? "adım/dk" : "steps/min"} ${o.adim_dk == null ? "–" : nf(o.adim_dk, 0)} · ${tr ? "tahmini bitiş" : "est. finish"} ${bit}`;
  } else if (IZ.kaynak !== "hizli" && IZ.kosular.some((x) => x.id === IZ.kaynak)) {
    const k = IZ.kosular.find((x) => x.id === IZ.kaynak);
    baslik = k.ad + " — " + izDurumAd(k.durum); yuzde = null;
    alt = k.durum === "BEKLİYOR" ? (tr ? "Kuyrukta, sırasını bekliyor." : "Queued.") : k.durum === "DURAKLADI" ? (tr ? "Duraklatıldı: çekirdekler boşta, Devam ile kaldığı yerden sürer." : "Paused: cores idle; Resume continues where it stopped.") : (tr ? "Günlük bekleniyor…" : "Waiting for log…");
  } else if (IZ.kaynak.indexOf("canli:") === 0) {
    baslik = IZ.kaynak.slice(6); yuzde = null; alt = tr ? "Kuyruk günlüğü (canlı izleniyor)" : "Queue log (live)";
  } else {
    const ilr = S.cozumIlerleme;
    baslik = tr ? "Hızlı çözüm" : "Fast solve";
    if (S.cozuluyor && ilr) { yuzde = ilr.yuzde; alt = (ilr.adim || "") + " · " + (tr ? "çözülüyor…" : "solving…"); }
    else if (S.cozumHata) { yuzde = 100; alt = S.cozumHata; }
    else if (S.sonuc) { yuzde = 100; alt = (tr ? "son çözüm " : "last solve ") + nf(S.sonSolveSure, 2) + " s · " + (S.baslik || ""); }
    else { yuzde = null; alt = T("sonuc.yokHenuzAlt"); }
  }
  const kk = IZ.kaynak !== "hizli" ? IZ.kosular.find((x) => x.id === IZ.kaynak) : null;
  const dg = kk ? izKontrolDugmeleri(kk, true) : "";
  kap.innerHTML = `<div class="izkart-bas"><b>${esc(baslik)}</b>${yuzde == null ? "" : `<span class="sayi">%${esc(nf(yuzde, 1))}</span>`}` +
    `${dg ? `<span style="display:flex;gap:6px;${yuzde == null ? "margin-left:auto" : ""}">${dg}</span>` : ""}</div>` +
    (yuzde == null ? "" : `<div class="ilerleme"><i style="width:${Math.max(0, Math.min(100, yuzde))}%"></i></div>`) +
    `<div class="sonuk" style="font-size:11.5px;margin-top:5px">${esc(alt)}</div>`;
  if (bas) bas.innerHTML = IZ.kaynak !== "hizli" && IZ.kaynak.indexOf("canli:") !== 0
    ? ["saat", tr ? "koşu" : "run", tr ? "adım" : "step", "t (s)", "%", "Δt", "Tmax", "Co", tr ? "kalan" : "left"].map((x) => `<span>${esc(x)}</span>`).join("")
    : ["saat", tr ? "koşu" : "run", tr ? "ileti" : "message"].map((x) => `<span>${esc(x)}</span>`).join("");
  if (bas) bas.className = "izbas" + (IZ.kaynak !== "hizli" && IZ.kaynak.indexOf("canli:") !== 0 ? " foam" : "");
}

function izCizgi(seri, anahtar, ad, birim, renk, esik) {
  const p = seri.filter((x) => x[anahtar] != null && x.t != null);
  const W = 260, H = 84, kenar = 4;
  if (p.length < 2) return `<div class="izg"><b>${esc(ad)}</b><div class="sonuk">${esc(izTr() ? "veri bekleniyor" : "waiting for data")}</div></div>`;
  const xs = p.map((x) => x.t), ys = p.map((x) => x[anahtar]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const yb = y1 > y0 ? y1 - y0 : Math.abs(y1) * 0.1 || 1;
  const X = (v) => kenar + (x1 > x0 ? (v - x0) / (x1 - x0) : 0) * (W - 2 * kenar);
  const Y = (v) => H - kenar - ((v - y0) / yb) * (H - 2 * kenar);
  const yol = p.map((x) => `${X(x.t).toFixed(1)},${Y(x[anahtar]).toFixed(1)}`).join(" ");
  const e = esik != null && esik >= y0 && esik <= y0 + yb ? `<line x1="0" x2="${W}" y1="${Y(esik)}" y2="${Y(esik)}" stroke="var(--uyari)" stroke-dasharray="3 3"/>` : "";
  const son = ys[ys.length - 1];
  return `<div class="izg"><div class="izg-bas"><b>${esc(ad)}</b><span>${esc(Number(son).toPrecision(4))} ${esc(birim)}</span></div>` +
    `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${e}<polyline fill="none" stroke="${renk}" stroke-width="1.6" points="${yol}"/></svg>` +
    `<div class="izg-alt"><span>${esc(Number(y0).toPrecision(3))}</span><span>${esc(Number(y1).toPrecision(3))}</span></div></div>`;
}

function izGrafCiz() {
  const kap = document.getElementById("izGraf");
  if (!kap) return;
  const s = IZ.seri[IZ.kaynak];
  if (IZ.kaynak === "hizli" || IZ.kaynak.indexOf("canli:") === 0 || !s) { kap.innerHTML = ""; return; }
  const tr = izTr();
  kap.innerHTML = `<h3 class="izb">${esc(tr ? "İzleme grafikleri (x: benzetim zamanı t, s)" : "Monitors (x: simulation time t, s)")}</h3><div class="izgrid">` +
    izCizgi(s, "dt", "Δt", "s", "var(--vurgu)") + izCizgi(s, "tmax", "Tmax", "K", "var(--hata)") +
    izCizgi(s, "co", tr ? "Courant (maks)" : "Courant (max)", "", "var(--uyari)", 0.5) + izCizgi(s, "adim_dk", tr ? "adım/dk" : "steps/min", "", "var(--ok)") + `</div>`;
}

const izDurumSinif = (d) => ({ "TAMAM": "tamam", "ÇALIŞIYOR": "calisiyor", "DURAKLADI": "uyari", "BEKLİYOR": "bekle", "IRAKSADI": "hata", "İPTAL": "uyari", "DİSK DOLU": "hata" }[d] || "");
const izDurumAd = (d) => (izTr() ? d : { "TAMAM": "DONE", "ÇALIŞIYOR": "RUNNING", "DURAKLADI": "PAUSED", "BEKLİYOR": "QUEUED", "IRAKSADI": "FAILED", "İPTAL": "CANCELLED", "DİSK DOLU": "DISK FULL" }[d] || d);
const izSureMetni = (sn) => (sn == null ? "–" : sn < 90 ? nf(sn, 0) + " s" : sn < 5400 ? nf(sn / 60, 0) + (izTr() ? " dk" : " min") : nf(sn / 3600, 1) + (izTr() ? " sa" : " h"));

function izKuyrukCiz() {
  const kap = document.getElementById("izKuyruk");
  if (!kap) return;
  const tr = izTr(), k = IZ.kosular;
  if (!k.length) { kap.innerHTML = `<div class="sonuk" style="font-size:12px">${esc(tr ? "Bekleyen, çalışan ya da biten koşu yok." : "No queued, running or finished runs.")}</div>`; return; }
  kap.innerHTML = `<div class="tablo-kap"><table class="veri"><thead><tr><th>${esc(tr ? "Koşu" : "Run")}</th><th>${esc(tr ? "Başlangıç" : "Started")}</th><th class="s">${esc(tr ? "Süre" : "Time")}</th><th>${esc(tr ? "Durum" : "Status")}</th><th></th></tr></thead><tbody>` +
    k.map((x) => `<tr><td>${esc(x.ad)}${x.harici ? ` <span class="sonuk">(${esc(tr ? "harici" : "external")})</span>` : ""}${x.cekirdek ? ` <span class="sonuk">${esc(x.cekirdek)}${esc(tr ? " çk" : " cores")}</span>` : ""}</td>` +
      `<td class="tek">${x.baslangic ? esc(new Date(x.baslangic * 1000).toLocaleString(tr ? "tr-TR" : "en-US", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })) : "–"}</td>` +
      `<td class="s">${esc(izSureMetni(x.sure))}</td><td><span class="izdurum ${izDurumSinif(x.durum)}">${esc(izDurumAd(x.durum))}</span></td>` +
      `<td style="white-space:nowrap">${izKontrolDugmeleri(x)}</td></tr>`).join("") +
    `</tbody></table></div>`;
}

/* koşu denetimi: Duraklat / Devam / Kes (yalnız kendi koşularımız; bekleyende yalnız Kes) */
function izKontrolDugmeleri(x, buyuk) {
  if (!x || x.harici) return "";
  const tr = izTr(), c = "dugme" + (buyuk ? "" : " kucuk");
  const d = (ne, ad, ek) => `<button class="${c}${ek || ""}" data-iz-kontrol="${ne}" data-iz-id="${esc(x.id)}">${esc(ad)}</button>`;
  if (x.durum === "ÇALIŞIYOR") return d("duraklat", tr ? "❚❚ Duraklat" : "❚❚ Pause") + " " + d("kes", tr ? "■ Kes" : "■ Stop", " tehlike");
  if (x.durum === "DURAKLADI") return d("devam", tr ? "▶ Devam" : "▶ Resume", " birincil") + " " + d("kes", tr ? "■ Kes" : "■ Stop", " tehlike");
  if (x.durum === "BEKLİYOR") return d("kes", tr ? "■ Kes" : "■ Stop", " tehlike");
  return "";
}

function izGecmisCiz() {
  const kap = document.getElementById("izGecmis");
  if (!kap) return;
  const tr = izTr();
  const l = S.gunluk.filter((x) => x.tur === "Çöz" || x.tur === "Solve").slice(0, 20);
  if (!l.length) { kap.innerHTML = `<div class="sonuk" style="font-size:12px">${esc(tr ? "Bu oturumda çözüm yok." : "No solves in this session.")}</div>`; return; }
  kap.innerHTML = `<div class="tablo-kap"><table class="veri"><thead><tr><th>${esc(tr ? "Zaman" : "Time")}</th><th>${esc(tr ? "Girdiler" : "Inputs")}</th><th class="s">${esc(tr ? "Süre" : "Duration")}</th><th>${esc(tr ? "Sonuç" : "Result")}</th></tr></thead><tbody>` +
    l.map((x) => `<tr><td class="tek">${esc(x.zaman)}</td><td class="tek">${esc(x.girdi || "")}</td><td class="s">${x.sure == null ? "–" : esc(nf(x.sure, 2)) + " s"}</td>` +
      `<td style="${x.hata ? "color:var(--hata)" : ""}">${esc(x.hata || x.sonuc || "")}</td></tr>`).join("") + `</tbody></table></div>`;
}

/* ---------------------------------------------------------------- yoklama (1,5 s) */
async function izPoll(zorla, kaynakSifirla) {
  if (IZ.bekle) return;
  IZ.bekle = true;
  try {
    const gorunur = !!document.getElementById("izKok");
    IZ.tik++;
    if (!gorunur && !zorla && IZ.tik % 3) return;            // izleyici kapalıyken 4,5 s'de bir yalnız liste
    const k = await API.kosular();
    IZ.kosular = k.kosular || [];
    (k.biten || []).forEach((b) => {                         // bitince Mesajlar + ekran bildirimi (Python masaüstü bildirimi de yollar)
      const tam = b.durum === "TAMAM";
      const m = (izTr() ? "Koşu " : "Run ") + izDurumAd(b.durum) + ": " + b.ad;
      mesaj(tam ? "bilgi" : "uyari", m);
      Kabuk.bildir(m, tam ? "basari" : "hata", 9000);
      gunluk({ tur: izTr() ? "Koşu" : "Run", sure: null, girdi: b.ad, sonuc: izDurumAd(b.durum) });
    });
    if (typeof ayrintiliTakip === "function") await ayrintiliTakip(k);
    if (!gorunur) return;
    if (!IZ.elle && IZ.kaynak === "hizli") {                  // kullanıcı seçmediyse çalışan bir koşuya otomatik geç
      const c = IZ.kosular.find((x) => x.durum === "ÇALIŞIYOR");
      if (c) { IZ.kaynak = c.id; IZ.ofset[c.id] = null; IZ.log[c.id] = []; izLogYenidenCiz(); }
    }
    if (IZ.tik % 4 === 1 || zorla) IZ.kaynaklar = await API.kosuKaynaklari();
    izKaynakDoldur();
    if (IZ.kaynak !== "hizli") {
      const r = await API.izle(IZ.kaynak, IZ.ofset[IZ.kaynak] == null ? null : IZ.ofset[IZ.kaynak], !!kaynakSifirla);
      if (r && !r.hata) {
        IZ.ofset[IZ.kaynak] = r.ofset;
        (r.satirlar || []).forEach((x) => izSatirEkle(IZ.kaynak, { seviye: x.seviye, kosu: (IZ.kosular.find((q) => q.id === IZ.kaynak) || {}).ad || IZ.kaynak.replace("canli:", ""), metin: x.metin, satir: x.satir }));
        if (r.seri) IZ.seri[IZ.kaynak] = r.seri;
        if (r.ozet) IZ.ozet[IZ.kaynak] = r.ozet;
      } else if (r && r.hata && !IZ.hataGosterildi) { IZ.hataGosterildi = true; izSatirEkle(IZ.kaynak, { seviye: "uyari", metin: r.hata }); }
    }
    izDurumCiz(); izGrafCiz(); izKuyrukCiz(); izGecmisCiz();
  } catch (e) { /* köprü yokken sessiz */ }
  finally { IZ.bekle = false; }
}

/* ---------------------------------------------------------------- SİSTEM sekmesinin ek bölümleri */
const SIC = { gecmis: [], son: null };
const sicRenk = (t) => (t >= 95 ? "var(--hata)" : t >= 90 ? "var(--uyari)" : "var(--ok)");

async function sistemEkYokla() {
  try {
    const e = await API.sistemEk();
    S.sisEk = e;
    const p = e && e.sicaklik && e.sicaklik.paket;
    if (p != null) {
      SIC.gecmis.push({ z: Date.now(), t: p });
      const kes = Date.now() - 600000;
      while (SIC.gecmis.length && SIC.gecmis[0].z < kes) SIC.gecmis.shift();
    }
    if (S.sisSon) sistemCiz(S.sisSon);
  } catch (x) {}
}

function sistemEkHtml(e) {
  if (!e) return "";
  const tr = izTr();
  const bas = (ad, orta, sag, renk) => `<div class="sis-bas" style="margin-top:12px"><b>${esc(ad)}</b><span>${esc(orta || "")}</span>${sag ? `<span class="sag sayi" style="color:${renk || "inherit"}">${esc(sag)}</span>` : ""}</div>`;
  let h = "";
  const s = e.sicaklik;
  if (s) {
    const p = s.paket;
    h += bas(tr ? "SICAKLIK" : "TEMPERATURE", "Package", p == null ? "–" : nf(p, 0) + " °C", p == null ? "" : sicRenk(p));
    if (p != null && p >= 90) h += `<div class="sis-uyari ${p >= 95 ? "kirmizi" : ""}">${esc(p >= 95 ? (tr ? "Kritik sıcaklık (≥95 °C): ağır koşuyu azaltın ya da bekleyin." : "Critical temperature (≥95 °C): reduce load or wait.") : (tr ? "Yüksek sıcaklık (≥90 °C)." : "High temperature (≥90 °C)."))}</div>`;
    if (SIC.gecmis.length > 1) {                          // son 10 dk
      const t0 = SIC.gecmis[0].z, t1 = SIC.gecmis[SIC.gecmis.length - 1].z, lo = 40, hi = 100, W = 300, H = 52;
      const X = (z) => (t1 > t0 ? ((z - t0) / (t1 - t0)) * W : W), Y = (t) => H - ((Math.max(lo, Math.min(hi, t)) - lo) / (hi - lo)) * H;
      h += `<svg class="sis-sparkline" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><rect x="0" y="${Y(95)}" width="${W}" height="${Y(90) - Y(95)}" fill="var(--uyari)" opacity=".18"/>` +
        `<rect x="0" y="0" width="${W}" height="${Y(95)}" fill="var(--hata)" opacity=".15"/>` +
        `<polyline fill="none" stroke="${sicRenk(p == null ? 0 : p)}" stroke-width="1.6" points="${SIC.gecmis.map((q) => X(q.z).toFixed(1) + "," + Y(q.t).toFixed(1)).join(" ")}"/></svg>` +
        `<div class="sis-not" style="margin-top:0">${esc(tr ? "son 10 dk · 90 °C sarı, 95 °C kırmızı" : "last 10 min · 90 °C yellow, 95 °C red")}</div>`;
    }
    h += `<div class="sis-cekirdekler">` + s.cekirdekler.map((c) => `<div class="sis-cek"><span class="no">${esc(c.ad.replace("Core ", ""))}</span><div class="sis-cubuk"><i style="width:${Math.max(0, Math.min(100, (c.t - 30) / 0.7))}%;background:${sicRenk(c.t)}"></i><u>${esc(nf(c.t, 0))}°</u></div></div>`).join("") + `</div>`;
  }
  if (e.fan && e.fan.length) h += bas("FAN", "", e.fan.map((f) => f.ad + " " + nf(f.rpm, 0) + " rpm").join(" · "));
  if (e.profil) h += bas(tr ? "GÜÇ PROFİLİ" : "POWER PROFILE", "", e.profil);
  if (e.pil) {
    h += bas(tr ? "GÜÇ" : "POWER", e.pil.prizde ? (tr ? "prizde" : "plugged in") : (tr ? "pilde" : "on battery"), "%" + nf(e.pil.yuzde, 0), e.pil.prizde ? "" : "var(--uyari)");
    if (!e.pil.prizde) h += `<div class="sis-uyari">${esc(tr ? "Pilde çalışıyor: uzun koşuda prize takın." : "Running on battery: plug in for long runs.")}</div>`;
  }
  if (e.disk) {
    const gb = e.disk.bos / 1073741824;
    h += bas(tr ? "DİSK" : "DISK", tr ? "boş" : "free", nf(gb, 1) + " GB", gb < 1 ? "var(--hata)" : gb < 5 ? "var(--uyari)" : "");
    if (gb < 5) h += `<div class="sis-uyari ${gb < 1 ? "kirmizi" : ""}">${esc(gb < 1 ? (tr ? "Disk dolmak üzere: koşular DİSK DOLU ile bitebilir." : "Disk nearly full: runs may stop with DISK FULL.") : (tr ? "Boş disk az (<5 GB): uzun koşu yazarken dolabilir." : "Low free disk (<5 GB)."))}</div>`;
  }
  if (e.foam) {
    h += bas("OpenFOAM", tr ? "çözücü süreç" : "solver procs", e.foam.cozucu + " · " + nf(e.foam.cekirdek, 1) + (tr ? " çekirdek" : " cores"));
    const ds = e.foam.calisma_dizinleri || [];
    h += ds.length ? `<div class="sis-not">${ds.map((d) => esc(d.split("/").slice(-2).join("/"))).join("<br>")}</div>` : `<div class="sis-not">${esc(tr ? "çalışan foamRun/mpirun yok" : "no foamRun/mpirun running")}</div>`;
  }
  return h;
}

/* ---------------------------------------------------------------- motor doğrulama: sıvı (n-heptan, NASA FLEX)
   of_damla_dogrulama.py vakaları: seçilenler Çözüm İzleyici kuyruğuna (bash kos.sh <çekirdek>) eklenir; her koşu
   bitince sonuc.json yazılır; özet (AUC, doğruluk, K oranı) pencerede. */
async function dogrulamaPenceresi() {
  const tr = izTr();
  const o = await API.dogrulamaSivi().catch((e) => ({ hata: e.message }));
  if (o.hata) return Kabuk.bildir(o.hata, "hata", 9000);
  const kuyrukta = new Set(IZ.kosular.filter((x) => ["BEKLİYOR", "ÇALIŞIYOR", "DURAKLADI"].indexOf(x.durum) >= 0).map((x) => x.dizin));
  const f = (v, d) => (v == null ? "–" : nf(v, d));
  const durumAd = (v) => kuyrukta.has(v.dizin) ? (tr ? "kuyrukta" : "queued")
    : v.durum === "bitti" ? (tr ? "bitti" : "done") : v.durum === "kuruldu" ? (tr ? "hazır" : "ready") : (tr ? "kurulmadı" : "not set up");
  const sonucAd = (y) => (y === 1 ? (tr ? "yandı" : "burned") : y === 0 ? (tr ? "söndü" : "extinguished") : "–");
  const satir = o.vakalar.map((v) => {
    const sec = v.durum !== "bitti" && !kuyrukta.has(v.dizin);
    const uyum = v.yanar_of == null ? "" : v.yanar_of === v.flex_yanar ? ' style="color:var(--ok)"' : ' style="color:var(--hata)"';
    return `<tr><td><input type="checkbox" data-dd="${esc(v.ad)}"${sec ? " checked" : ""}${kuyrukta.has(v.dizin) ? " disabled" : ""}></td>` +
      `<td>${esc(v.ad)}</td><td>${esc(v.seyreltici.toUpperCase())}</td><td class="s">${f(v.basinc_kpa, 1)}</td><td class="s">${f(v.o2, 1)}</td>` +
      `<td class="s">${f(v.d0_mm, 2)}</td><td class="s">${f(v.bitis_s, 1)}</td><td>${esc(sonucAd(v.flex_yanar))}</td>` +
      `<td${uyum}>${esc(sonucAd(v.yanar_of))}</td><td class="s">${f(v.flex_K, 2)}</td><td class="s">${f(v.K_of_mm2_s, 2)}</td><td>${esc(durumAd(v))}</td></tr>`;
  }).join("");
  const ozet = o.n ? `${tr ? "Biten" : "Done"} ${o.n}/${o.n_toplam} · AUC ${o.auc == null ? "–" : nf(o.auc, 2)} · ${tr ? "doğruluk" : "accuracy"} ${o.dogruluk == null ? "–" : "%" + nf(o.dogruluk * 100, 0)}` +
    ` · K OpenFOAM/FLEX ${o.K_oran_medyan == null ? "–" : "×" + nf(o.K_oran_medyan, 2)}` + (o.belirsiz_n ? ` · ${o.belirsiz_n} ${tr ? "belirsiz" : "undetermined"}` : "") +
    (o.n < 10 ? ` · ${tr ? "n < 10: AUC güvenilmez" : "n < 10: AUC unreliable"}` : "")
    : (tr ? "Henüz biten koşu yok." : "No finished runs yet.");
  Kabuk.pencereAc({
    baslik: tr ? "Sıvı motoru doğrulaması — n-heptan damla, NASA FLEX" : "Liquid engine validation — n-heptane droplet, NASA FLEX",
    ic: `<p class="sonuk">${esc(tr ? "OpenFOAM tek damla (ışınımsız, g = 0, tek adım kimya). Kriter FLEX ile aynı: alev d/d0 = 0,85'e inmeden sönerse 'söndü'. Koşular sırayla çalışır; Çözüm İzleyici'den duraklatılır / kesilir." : "OpenFOAM single droplet (no radiation, g = 0, one-step chemistry). Same criterion as FLEX: 'extinguished' if the flame dies before d/d0 = 0.85. Runs execute one at a time; pause/stop from the Solution Monitor.")}</p>` +
      `<div class="uyari-satir"><span>${esc(tr ? "Işınım kapalı: FLEX'teki büyük damla sönmeleri çoğunlukla ışınım kaybından olur; bu turda OpenFOAM onları 'yandı' bulabilir. K'nın ~1,5–1,8 kat yüksek çıkması bilinen bir fark." : "Radiation off: large-droplet extinctions in FLEX are mostly radiative; this round OpenFOAM may call them 'burned'. K ~1.5–1.8× high is a known offset.")}</span></div>` +
      `<p><b>${esc(ozet)}</b></p>` +
      `<div class="tablo-kap" style="max-height:330px"><table class="veri"><thead><tr><th></th><th>${tr ? "Test" : "Test"}</th><th>${tr ? "Seyr." : "Dil."}</th><th class="s">kPa</th><th class="s">O₂ %</th><th class="s">d0 mm</th><th class="s">${tr ? "süre s" : "time s"}</th><th>FLEX</th><th>OpenFOAM</th><th class="s">K FLEX</th><th class="s">K OF</th><th>${tr ? "Durum" : "Status"}</th></tr></thead><tbody>${satir}</tbody></table></div>` +
      `<div class="bilgi-satir" style="margin-top:8px"><span class="etiket-ad" style="min-width:120px">${esc(tr ? "Çekirdek" : "Cores")}</span><input class="giris" id="ddCek" type="number" min="1" max="${o.nproc}" value="${Math.min(15, o.nproc)}" style="width:70px"> <span class="sonuk">/ ${o.nproc}</span></div>`,
    dugmeler: [{ ad: tr ? "Seçilenleri kuyruğa ekle" : "Queue selected", sinif: "birincil", islev: async (ic) => {
        const adlar = [...ic.querySelectorAll("[data-dd]:checked")].map((x) => x.dataset.dd);
        if (!adlar.length) return;
        const n = Math.max(1, Math.min(o.nproc, Number(ic.querySelector("#ddCek").value) || 15));
        const k = await API.dogrulamaSiviKur(adlar).catch((e) => ({ hata: e.message }));
        if (k.hata) { Kabuk.bildir(k.hata, "hata", 12000); mesaj("hata", k.hata); return; }
        let eklenen = 0;
        for (const ad of adlar) {
          const v = o.vakalar.find((x) => x.ad === ad);
          const r = await API.kosuEkle(`${tr ? "Sıvı doğrulama" : "Liquid validation"}: ${ad}`, v.dizin, ["bash", "kos.sh", String(n)], "log.run", n).catch((e) => ({ hata: e.message }));
          if (r && r.hata) { Kabuk.bildir(r.hata, "hata"); break; }
          eklenen++;
        }
        mesaj("bilgi", `${tr ? "Sıvı doğrulama: kuyruğa eklenen" : "Liquid validation queued"} ${eklenen} · ${n} ${tr ? "çekirdek" : "cores"}`);
        Kabuk.bildir(`${eklenen} ${tr ? "koşu kuyruğa eklendi" : "runs queued"} (${n} ${tr ? "çekirdek" : "cores"})`, "basari");
        IZ.elle = false; izPoll(true);
      } }, { ad: tr ? "Kapat" : "Close" }],
  });
}
