"use strict";
/* AHUT FLARE — kabuk.
   Menü, araç çubuğu, sekmeler, bölücüler, ağaç, Ayrıntılar tablosu,
   sağ panel (dikey sekmeler: Mesajlar / Grafik / Tablo Verisi / Günlük / Sistem),
   durum çubuğu, bildirim ve pencere.
   Burada uygulamaya özgü bilgi yoktur; içerik app.js'ten gelir. */

const $ = (s, k) => (k || document).querySelector(s);
const $$ = (s, k) => Array.prototype.slice.call((k || document).querySelectorAll(s));

const Kabuk = (function () {
  /* ------------------------------------------------ menüler */
  function menuleriKur(calistir) {
    $$(".menu").forEach((m) => {
      $(".menu-bas", m).addEventListener("click", (e) => {
        e.stopPropagation();
        const acikti = m.classList.contains("acik");
        $$(".menu").forEach((x) => x.classList.remove("acik"));
        if (!acikti) m.classList.add("acik");
      });
      m.addEventListener("mouseenter", () => {
        if ($$(".menu.acik").length) {
          $$(".menu").forEach((x) => x.classList.remove("acik"));
          m.classList.add("acik");
        }
      });
    });
    document.addEventListener("click", () => $$(".menu").forEach((x) => x.classList.remove("acik")));
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") $$(".menu").forEach((x) => x.classList.remove("acik"));
    });
    document.addEventListener("click", (e) => {
      const d = e.target.closest("[data-komut]");
      if (d && !d.disabled) {
        $$(".menu").forEach((x) => x.classList.remove("acik"));
        calistir(d.dataset.komut, d);
      }
      const b = e.target.closest("[data-birim]");
      if (b) {
        $$(".menu").forEach((x) => x.classList.remove("acik"));
        calistir("birim", b);
      }
    });
  }

  /* ------------------------------------------------ üst sekmeler */
  let sekmeDegisti = function () {};
  const EKRAN = { baslangic: "ek-baslangic", calisma: "ek-calisma", kutuphane: "ek-kutuphane", topluluk: "ek-topluluk" };
  /* Eski sekme adları tek çalışma ekranına yönlenir; sekmeDegisti istenen adı da alır
     (kurulum -> kurulum düğümü, sonuclar -> sonuç özeti, cozum -> çözüm bilgisi). */
  const TAKMA = { kurulum: "calisma", cozum: "calisma", sonuclar: "calisma" };
  let aktifSekme = "baslangic";

  function sekmeAc(istenen) {
    const ad = TAKMA[istenen] || istenen;
    if (!EKRAN[ad]) return;
    aktifSekme = ad;
    $$("#sekmeserit button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.sekme === ad)));
    const hedef = EKRAN[ad];
    $$(".ekran").forEach((e) => e.classList.toggle("acik", e.id === hedef));
    sekmeDegisti(ad, istenen);
  }

  function sekmeKur(f) {
    sekmeDegisti = f || sekmeDegisti;
    $$("#sekmeserit button").forEach((b) => b.addEventListener("click", () => sekmeAc(b.dataset.sekme)));
  }

  function sekmeKilit(ad, kapali) {
    const b = $(`#sekmeserit button[data-sekme="${ad}"]`);
    if (b) b.disabled = !!kapali;
  }

  /* ------------------------------------------------ bölücüler (yeniden boyutlama) */
  const BOLUCU = {
    sol:   { ozellik: "--sol-genislik",      eksen: "x", min: 220, max: 560, hedef: "#ek-calisma" },
    orta:  { ozellik: "--ayrinti-yukseklik", eksen: "y", min: 120, max: 720, hedef: "#sutunSol", ters: true },
    sag:   { ozellik: "--sag-genislik",      eksen: "x", min: 220, max: 760, hedef: "#ek-calisma", ters: true, pay: 0 },
  };
  const DUZEN = ["--sol-genislik", "--ayrinti-yukseklik", "--sag-genislik"];

  function bolucuKur() {
    $$(".bolucu").forEach((b) => {
      const ad = b.dataset.bolucu;
      const k = BOLUCU[ad] || BOLUCU.orta;
      b.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        b.setPointerCapture(e.pointerId);
        b.classList.add("surukleniyor");
        const kap = $(k.hedef);
        const dikdortgen = kap.getBoundingClientRect();
        const tasi = (ev) => {
          let v;
          if (k.eksen === "x") v = k.ters ? dikdortgen.right - (k.pay || 0) - ev.clientX : ev.clientX - dikdortgen.left;
          else v = k.ters ? dikdortgen.bottom - ev.clientY : ev.clientY - dikdortgen.top;
          v = Math.max(k.min, Math.min(k.max, v));
          document.documentElement.style.setProperty(k.ozellik, v + "px");
        };
        const birak = () => {
          b.classList.remove("surukleniyor");
          b.removeEventListener("pointermove", tasi);
          b.removeEventListener("pointerup", birak);
          duzenKaydet();
        };
        b.addEventListener("pointermove", tasi);
        b.addEventListener("pointerup", birak);
      });
    });
    duzenYukle();
  }

  function duzenKaydet() {
    const s = document.documentElement.style;
    const d = {};
    DUZEN.forEach((a) => {
      const v = s.getPropertyValue(a);
      if (v) d[a] = v;
    });
    try { localStorage.setItem("ahut.duzen", JSON.stringify(d)); } catch (e) {}
  }

  function duzenYukle() {
    try {
      const d = JSON.parse(localStorage.getItem("ahut.duzen") || "{}");
      Object.keys(d).forEach((a) => document.documentElement.style.setProperty(a, d[a]));
    } catch (e) {}
  }

  function duzenSifirla() {
    DUZEN.forEach((a) => document.documentElement.style.removeProperty(a));
    sagPanelAc(true);
    try { localStorage.removeItem("ahut.duzen"); } catch (e) {}
  }

  /* ------------------------------------------------ ağaç */
  const IKON = {
    vaka: '<path d="M2 3.5h5l1.5 2h5.5v7h-12z"/>',
    proje: '<rect x="2" y="2.5" width="12" height="11"/><path d="M2 5.5h12M5 8.5h6M5 11h4"/>',
    numune: '<path d="M3 11.5l5-8 5 8z"/><path d="M5.5 11.5v2h5v-2"/>',
    cozum: '<path d="M4 2.5l9 5.5-9 5.5z"/>',
    ortam: '<circle cx="8" cy="8" r="5.5"/><path d="M2.5 8h11M8 2.5c2.6 3 2.6 8 0 11M8 2.5c-2.6 3-2.6 8 0 11"/>',
    malzeme: '<rect x="2.5" y="4.5" width="11" height="7" rx="1"/><path d="M2.5 8h11"/>',
    akis: '<path d="M2 5.5h8M2 8.5h11M2 11.5h6"/><path d="M11.5 3.5L13.5 5.5 11.5 7.5"/>',
    ayar: '<circle cx="8" cy="8" r="2.4"/><path d="M8 1.6v2M8 12.4v2M1.6 8h2M12.4 8h2M3.5 3.5l1.4 1.4M11.1 11.1l1.4 1.4M12.5 3.5l-1.4 1.4M4.9 11.1l-1.4 1.4"/>',
    sonuc: '<path d="M2.5 13.5V7M6.2 13.5V3.5M9.8 13.5V9M13.5 13.5V5.5"/>',
    grafik: '<path d="M2.5 13.5h11M3.5 11l3-4 3 2.5 4-6.5"/>',
    harita: '<rect x="2.5" y="2.5" width="11" height="11"/><path d="M6.2 2.5v11M9.8 2.5v11M2.5 6.2h11M2.5 9.8h11"/>',
    tablo: '<rect x="2.5" y="3" width="11" height="10"/><path d="M2.5 6h11M6 6v7"/>',
    guven: '<path d="M8 2l5 2v4c0 3-2.2 5.3-5 6-2.8-.7-5-3-5-6V4z"/><path d="M5.8 8l1.6 1.6 3-3.2"/>',
    llm: '<path d="M2.5 3.5h11v7H9l-3 3v-3H2.5z"/>',
    render: '<rect x="2" y="3.5" width="12" height="9" rx="1"/><path d="M6.8 6.5l3.6 2.5-3.6 2.5z"/>',
    dunya: '<circle cx="8" cy="8" r="5.5"/><path d="M3 6.5c2 1 4 1 5.5 0s3.5-1 4.5.5M5 12c.5-2 2-3 3.5-3"/>',
  };

  /* Durum simgeleri: küçük, tek renkli SVG (yazı tipine bağlı emoji çizimi olmasın diye) */
  const DURUM_SIMGE = {
    tamam: { yol: '<path d="M2 6.2l2.6 2.6L10 3.2"/>', ad: ["güncel", "up to date"] },
    eski:  { yol: '<path d="M6.8 1L2.5 6.6h3.2L4.9 11 9.5 5.2H6.2z" class="dolu"/>', ad: ["girdi değişti — yeniden çözülmeli", "inputs changed — re-solve"] },
    eksik: { yol: '<path d="M3.8 4.2a2.2 2.2 0 1 1 3.2 2c-.8.4-1 .9-1 1.6"/><circle cx="6" cy="10.2" r=".6" class="dolu"/>', ad: ["eksik girdi", "missing input"] },
    hata:  { yol: '<path d="M2.5 2.5l7 7M9.5 2.5l-7 7"/>', ad: ["hata", "error"] },
    bekler:{ yol: '<circle cx="6" cy="6" r="4"/><path d="M6 3.6V6l1.8 1.2"/>', ad: ["çözülüyor", "solving"] },
  };
  function durumSimge(d) {
    const x = DURUM_SIMGE[d];
    if (!x) return `<span class="durum-simge"></span>`;
    const ad = x.ad[typeof DIL !== "undefined" && DIL === "en" ? 1 : 0];
    return `<svg class="durum-simge ${d}" viewBox="0 0 12 12" aria-label="${ad}"><title>${ad}</title>${x.yol}</svg>`;
  }

  let agacSecim = null, agacTiklama = function () {}, agacModeli = [];

  function agacCiz(model, secili) {
    agacModeli = model || agacModeli;
    if (secili) agacSecim = secili;
    const kapali = kapaliDallar();
    const dal = (d, derinlik) => {
      const cocukVar = d.cocuk && d.cocuk.length;
      const kapaliMi = kapali.indexOf(d.id) >= 0;
      const ikon = IKON[d.ikon || "ayar"] || IKON.ayar;
      let h = `<div class="agac-dal" data-dal="${esc(d.id)}">`;
      h += `<div class="agac-satir${d.id === agacSecim ? " secili" : ""}${d.pasif ? " pasif" : ""}" data-dugum="${esc(d.id)}" title="${esc(d.ipucu || d.ad)}" style="padding-left:${4 + derinlik * 16}px">`;
      h += `<span class="ok${cocukVar ? (kapaliMi ? " kapali" : "") : " yok"}" data-katla="${esc(d.id)}">▾</span>`;
      h += durumSimge(d.durum);
      h += `<svg class="agac-ikon" viewBox="0 0 16 16">${ikon}</svg>`;
      h += `<span class="agac-ad">${esc(d.ad)}</span>`;
      if (d.not) h += `<span class="agac-not">${esc(d.not)}</span>`;
      h += `</div>`;
      if (cocukVar) {
        h += `<div class="agac-cocuk${kapaliMi ? " kapali" : ""}">` + d.cocuk.map((c) => dal(c, derinlik + 1)).join("") + `</div>`;
      }
      return h + `</div>`;
    };
    $("#agac").innerHTML = `<div class="agac">` + agacModeli.map((d) => dal(d, 0)).join("") + `</div>`;
  }

  function kapaliDallar() {
    try { return JSON.parse(localStorage.getItem("ahut.kapali") || "[]"); } catch (e) { return []; }
  }

  function katla(id) {
    const k = kapaliDallar();
    const i = k.indexOf(id);
    if (i >= 0) k.splice(i, 1); else k.push(id);
    try { localStorage.setItem("ahut.kapali", JSON.stringify(k)); } catch (e) {}
    agacCiz();
  }

  function agacKur(f) {
    agacTiklama = f || agacTiklama;
    $("#agac").addEventListener("click", (e) => {
      const ok = e.target.closest("[data-katla]");
      if (ok) { katla(ok.dataset.katla); return; }
      const satir = e.target.closest("[data-dugum]");
      if (!satir || satir.classList.contains("pasif")) return;
      agacSecim = satir.dataset.dugum;
      agacCiz();
      agacTiklama(agacSecim);
    });
  }

  const agacSecili = () => agacSecim;
  function agacSec(id) { agacSecim = id; agacCiz(); agacTiklama(id); }

  /* ------------------------------------------------ Ayrıntılar tablosu */
  /* alanlar: [{grup}| {ad, etiket, tip, birim, secenekler, ipucu, salt, varsayilanli}] */
  const kapaliGruplar = new Set();

  function ozellikCiz(baslik, alanlar, degerler, olay) {
    $("#ayrintiBaslik").textContent = baslik;
    const kap = $("#ayrintilar");
    let h = `<table class="ozellik"><colgroup><col class="c-ad"><col class="c-deger"><col class="c-birim"></colgroup>`;
    let acik = false;
    (alanlar || []).forEach((a) => {
      if (a.grup) {
        const kapali = kapaliGruplar.has(a.grup);
        h += (acik ? `</tbody>` : "") + `<tbody class="grup${kapali ? " kapali" : ""}">` +
             `<tr class="baslik" data-grup="${esc(a.grup)}"><td colspan="3"><span class="grup-ok">${kapali ? "+" : "−"}</span>${esc(a.grup)}</td></tr>`;
        acik = true;
        return;
      }
      if (!acik) { h += `<tbody class="grup">`; acik = true; }
      if (a.not) { h += `<tr><td colspan="3" class="ozellik-not">${a.not}</td></tr>`; return; }
      const v = degerler[a.ad];
      const vars = a.varsayilanli && (v == null || v === "");
      const sinif = [a.vurgulu ? "vurgulu" : "", a.salt ? "salt" : ""].filter(Boolean).join(" ");
      h += `<tr${sinif ? ` class="${sinif}"` : ""} title="${esc(a.ipucu || "")}">`;
      h += `<td class="ad">${esc(a.etiket)}${a.zorunlu ? ' <span style="color:var(--hata)">*</span>' : ""}</td>`;
      h += `<td class="deger">${denetim(a, v, vars)}</td><td class="birim">${esc(a.birim || "")}</td></tr>`;
      if (a.hata) h += `<tr><td colspan="3" class="ozellik-hata">${esc(a.hata)}</td></tr>`;
    });
    kap.innerHTML = h + (acik ? `</tbody>` : "") + `</table>`;

    kap.querySelectorAll("tr[data-grup]").forEach((tr) => {
      tr.addEventListener("click", () => {
        const g = tr.dataset.grup, tb = tr.parentElement;
        if (kapaliGruplar.has(g)) kapaliGruplar.delete(g); else kapaliGruplar.add(g);
        tb.classList.toggle("kapali", kapaliGruplar.has(g));
        tr.querySelector(".grup-ok").textContent = kapaliGruplar.has(g) ? "+" : "−";
      });
    });
    kap.querySelectorAll("[data-alan]").forEach((el) => {
      const olayAdi = el.type === "checkbox" || el.tagName === "SELECT" ? "change" : "input";
      el.addEventListener(olayAdi, () => {
        const deger = el.type === "checkbox" ? el.checked : el.value;
        olay(el.dataset.alan, deger);
      });
    });
  }

  function denetim(a, v, vars) {
    const birim = "", bd = "";     // birim artık ayrı sütunda
    if (a.salt) return `<span class="sayi">${a.bicim ? a.bicim(v) : esc(v == null ? "–" : v)}</span>`;
    if (a.tip === "onay") {
      return `<label class="onay"><input type="checkbox" data-alan="${esc(a.ad)}"${v ? " checked" : ""}>` +
             `<span class="sonuk">${esc(a.yanMetin || "")}</span></label>`;
    }
    if (a.tip === "secim") {
      const sec = (a.secenekler || []).map((o) => {
        const d = typeof o === "object" ? o.deger : o;
        const ad = typeof o === "object" ? o.ad : o;
        return `<option value="${esc(d)}"${String(v == null ? "" : v) === String(d) ? " selected" : ""}>${esc(ad)}</option>`;
      }).join("");
      return `<select class="giris${vars ? " varsayilan" : ""}" data-alan="${esc(a.ad)}">${sec}</select>`;
    }
    const tip = a.tip === "sayi" ? "number" : "text";
    const ek = a.tip === "sayi" ? ` step="${a.adim || "any"}"${a.min != null ? ` min="${a.min}"` : ""}${a.max != null ? ` max="${a.max}"` : ""}` : "";
    return `<input type="${tip}" class="giris${vars ? " varsayilan" : ""}${a.hata ? " hatali" : ""}"${bd} data-alan="${esc(a.ad)}"` +
           ` value="${esc(v == null ? "" : v)}" placeholder="${esc(a.yertutucu || "")}"${ek}>${birim}`;
  }

  /* ------------------------------------------------ sağ panel (dikey sekmeli) */
  let altAktif = "sistem";
  const altIcerik = { mesaj: "", grafik: "", tablo: "", gunluk: "", sistem: "" };

  function sagPanelAcik() { return !document.body.classList.contains("sag-kapali"); }

  function sagPanelAc(acik) {
    document.body.classList.toggle("sag-kapali", !acik);
    try { localStorage.setItem("ahut.sagKapali", acik ? "0" : "1"); } catch (e) {}
  }

  function altKur() {
    $("#altKapat").addEventListener("click", () => sagPanelAc(false));
    document.addEventListener("click", (e) => {
      const d = e.target.closest("[data-alt-ac]");
      if (d) {                                             // durum çubuğu: Mesajlar açılır liste, Sistem sağ paneli aç/kapat
        if (d.dataset.altAc === "sistem" && sagPanelAcik()) sagPanelAc(false);
        else altSec(d.dataset.altAc);
        return;
      }
      const g = e.target.closest("[data-gt]");
      if (g) return gorselKipAc(g.dataset.gt);
      const tv = e.target.closest("[data-tvi]");
      if (tv) return tabloIslem(tv.dataset.tvi);
      const pp = $("#mesajPopup");                         // dışarı tıklayınca Mesajlar listesi kapanır
      if (pp && !pp.hidden && !e.target.closest("#mesajPopup")) pp.hidden = true;
    });
    let kapali = false;
    try { kapali = localStorage.getItem("ahut.sagKapali") === "1"; } catch (e) {}
    sagPanelAc(!kapali);
  }

  /* Sağ panelde yalnız Sistem kalır. Eski sekme adları yönlendirilir: mesaj → durum çubuğu listesi,
     grafik/tablo → görüntü alanının alt kenarındaki geçiş, gunluk → Çözüm İzleyici. */
  let gorselKip = "grafik";
  let gorselSon = null;      // son gorselYaz: {baslik, html, araclar, tablo}
  function mesajPopupAc(ac) {
    const pp = $("#mesajPopup");
    if (!pp) return;
    const goster = ac == null ? pp.hidden : ac;
    pp.hidden = !goster;
    if (goster) mesajPopupYaz();
  }
  function mesajPopupYaz() {
    const pp = $("#mesajPopup");
    if (!pp || pp.hidden) return;
    pp.innerHTML = `<div class="mp-bas"><span>${DIL === "tr" ? "MESAJLAR" : "MESSAGES"}</span><button id="mpKapat" title="×">×</button></div>` + (altIcerik.mesaj || "");
    $("#mpKapat").addEventListener("click", () => { pp.hidden = true; });
  }
  /* Grafik | Tablo Verisi: yalnız gorselYaz'a tablo verisi verilen düğümlerde görünür.
     tablo = {ad, sutunlar: [{ad, birim, d}], satirlar: [[...]]}; sayılar ham tutulur (CSV için). */
  function gorselKipAc(kip) {
    const t = gorselSon && gorselSon.tablo;
    if (!t) kip = "grafik";
    gorselKip = kip;
    $$("#gtGecis button").forEach((b) => b.classList.toggle("secili", b.dataset.gt === kip));
    if (!gorselSon) return;
    const g = $("#gorsel");
    g.innerHTML = gorselOnek(gorselSon.baslik) + (kip === "tablo" ? tabloHtml(t) : (gorselSon.html || ""));
    g.scrollTop = 0;
  }
  function hucre(v, d) {
    if (v == null || v === "") return "–";
    if (typeof v === "number") return isFinite(v) ? (d == null ? String(v) : v.toLocaleString(DIL === "tr" ? "tr-TR" : "en-US", { minimumFractionDigits: d, maximumFractionDigits: d })) : "–";
    return String(v);
  }
  function kacis(x) { return String(x).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
  function tabloHtml(t) {
    const tr = DIL === "tr";
    return `<div class="tv-arac"><span class="sonuk">${kacis(t.satirlar.length)} ${tr ? "satır" : "rows"}</span><span class="sag">` +
      `<button class="dugme" data-tvi="kopyala">${tr ? "Kopyala" : "Copy"}</button> ` +
      `<button class="dugme" data-tvi="csv">${tr ? "CSV'ye aktar…" : "Export CSV…"}</button></span></div>` +
      `<div class="tablo-kap tv-kap" style="border:0"><table class="veri"><thead><tr>` +
      t.sutunlar.map((c) => `<th class="${c.d != null ? "s" : ""}">${kacis(c.ad)}${c.birim ? `<span class="birim">${kacis(c.birim)}</span>` : ""}</th>`).join("") +
      `</tr></thead><tbody>` +
      t.satirlar.map((r) => `<tr>` + r.map((v, i) => `<td class="${t.sutunlar[i].d != null ? "s" : ""}">${kacis(hucre(v, t.sutunlar[i].d))}</td>`).join("") + `</tr>`).join("") +
      `</tbody></table></div>`;
  }
  function tabloMetni(t, ayr) {
    const al = (x) => { const s = x == null ? "" : String(x); return ayr === "," && /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
    const bas = t.sutunlar.map((c) => al(c.ad + (c.birim ? " [" + c.birim + "]" : "")));
    return [bas.join(ayr)].concat(t.satirlar.map((r) => r.map(al).join(ayr))).join("\n") + "\n";
  }
  function tabloIslem(ne) {
    const t = gorselSon && gorselSon.tablo;
    if (!t) return;
    const tr = DIL === "tr";
    if (ne === "kopyala") {
      const m = tabloMetni(t, "\t");
      const bitti = () => bildir(tr ? "Tablo panoya kopyalandı." : "Table copied to clipboard.", "basari", 2500);
      const yedek = () => {
        const a = document.createElement("textarea"); a.value = m; a.style.position = "fixed"; a.style.opacity = "0";
        document.body.appendChild(a); a.select(); try { document.execCommand("copy"); bitti(); } catch (e) {} a.remove();
      };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(m).then(bitti, yedek); else yedek();
      return;
    }
    if (ne === "csv") {
      Promise.resolve(API.csvKaydet(tabloMetni(t, ","), t.ad || "tablo")).then((r) => {
        if (r && r.yol) bildir((tr ? "CSV kaydedildi: " : "CSV saved: ") + r.yol, "basari");
      }).catch((e) => bildir(String(e && e.message || e), "hata"));
    }
  }
  function altSec(ad) {
    if (ad === "mesaj") return mesajPopupAc();
    if (ad === "grafik" || ad === "tablo") {
      sekmeAc("calisma");
      if (!(gorselSon && gorselSon.tablo)) agacSec("r-oksijen");
      return gorselKipAc(ad);
    }
    if (ad === "gunluk") { sekmeAc("calisma"); return agacSec("cozum"); }
    altAktif = "sistem";
    $("#altBaslik").dataset.d = "panel.sistem";
    $("#altBaslik").textContent = DIL === "tr" ? "Sistem" : "System";
    $("#altIc").innerHTML = altIcerik.sistem || `<div class="bos" style="margin:14px">—</div>`;
    sagPanelAc(true);
  }

  function altYaz(ad, html) {
    altIcerik[ad] = html;
    if (ad === "sistem") { if (altAktif === "sistem") $("#altIc").innerHTML = html; }
    else if (ad === "mesaj") mesajPopupYaz();
  }

  /* ------------------------------------------------ durum çubuğu */
  function durum(alan, metin, sinif) {
    const e = $("#" + alan);
    if (!e) return;
    e.textContent = metin;
    if (sinif !== undefined) e.className = (alan === "dMotor" ? "nokta " : "") + (sinif || "");
    if (alan === "dBirim") e.className = "db-sag";
  }

  /* ------------------------------------------------ bildirim */
  let kayanZaman = null;
  function bildir(metin, tur, ms) {
    const k = $("#kayan");
    k.textContent = metin;
    k.className = "kayan " + (tur || "");
    k.style.display = "block";
    clearTimeout(kayanZaman);
    kayanZaman = setTimeout(() => (k.style.display = "none"), ms || 4500);
  }

  /* ------------------------------------------------ pencere (modal) */
  let pencereKapanisi = null;
  function pencereAc(secenek) {
    const o = $("#ortu"), ic = $("#pencereIc");
    const dugmeler = (secenek.dugmeler || []).map((d, i) =>
      `<button class="dugme ${esc(d.sinif || "")}" data-pd="${i}">${esc(d.ad)}</button>`).join("");
    ic.innerHTML =
      `<div class="pencere-bas"><h3>${esc(secenek.baslik || "")}</h3><button class="kapat" data-pkapat>×</button></div>` +
      `<div class="pencere-ic secilebilir">${secenek.ic || ""}</div>` +
      (dugmeler ? `<div class="pencere-alt">${dugmeler}</div>` : "");
    o.hidden = false;
    pencereKapanisi = secenek.kapanista || null;
    ic.querySelectorAll("[data-pd]").forEach((b) => {
      b.addEventListener("click", () => {
        const d = secenek.dugmeler[Number(b.dataset.pd)];
        if (!d.islev || d.islev(ic) !== false) pencereKapat();
      });
    });
    ic.querySelector("[data-pkapat]").addEventListener("click", pencereKapat);
    if (secenek.hazir) secenek.hazir(ic);
    const ilk = ic.querySelector(".pencere-ic input, .pencere-ic textarea, .pencere-ic select");
    if (ilk) setTimeout(() => ilk.focus(), 30);
  }

  function pencereKapat() {
    $("#ortu").hidden = true;
    $("#pencereIc").innerHTML = "";
    if (pencereKapanisi) { const f = pencereKapanisi; pencereKapanisi = null; f(); }
  }

  function pencereKur() {
    $("#ortu").addEventListener("mousedown", (e) => { if (e.target.id === "ortu") pencereKapat(); });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !$("#ortu").hidden) pencereKapat();
    });
  }

  /* ------------------------------------------------ görsel alan */
  /* önek: görüntü alanının sol üstüne konan başlık bloğu (uygulama verir; sonuç değilse "") */
  let gorselOnek = function () { return ""; };
  function gorselOnekKur(f) { gorselOnek = f || gorselOnek; }

  /* tablo (isteğe bağlı): grafiğin verisi; verilirse alt kenarda Grafik | Tablo Verisi şeridi açılır.
     Aynı düğüm yeniden çizilirken seçili kip korunur, düğüm değişince Grafik'e döner. */
  function gorselYaz(baslik, html, araclar, tablo) {
    const ayniDugum = gorselSon && gorselSon.dugum === agacSecim;
    gorselSon = { baslik, html, araclar, tablo: tablo && tablo.satirlar && tablo.satirlar.length ? tablo : null, dugum: agacSecim };
    $("#gorselBaslik").textContent = baslik || "—";
    $("#gorselArac").innerHTML = araclar || "";
    $("#gtGecis").hidden = !gorselSon.tablo;
    gorselKipAc(ayniDugum ? gorselKip : "grafik");
  }

  function ekranYaz(id, html) { $("#" + id).innerHTML = html; }

  return {
    menuleriKur, sekmeKur, sekmeAc, sekmeKilit, aktif: () => aktifSekme,
    bolucuKur, duzenSifirla,
    agacKur, agacCiz, agacSec, agacSecili,
    ozellikCiz, altKur, altSec, altYaz, altAktif: () => altAktif, sagPanelAc, sagPanelAcik,
    durum, bildir, pencereAc, pencereKapat, pencereKur,
    gorselYaz, gorselOnekKur, ekranYaz,
  };
})();
