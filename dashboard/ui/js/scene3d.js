"use strict";
/* AHUT FLARE — 3B görüntüleyici (ANSYS benzeri). three.js YEREL kopya (vendor/three.min.js), CDN yok.
   Girdi düğümlerinde: numune tipine göre geometri (levha / damla / gaz brülörü), kabin kutusu, ölçü çizgileri, ızgara,
   yerçekimi ve akış okları, ortam etiketi; OpenFOAM vakası (SIBAL) için gerçek boyutlar (polyMesh) ve hücre kenarları.
   Sonuç düğümünde (r-3b): of_3b_export.py çıktısı — izo yüzeyleri (marching tetrahedra), z kesiti, damlalar,
   renk ölçeği, zaman kaydırıcısı + oynat, alan seçimi, kesit konumu, izo değerleri, "ParaView'da aç".
   Çizim yalnız bir şey değişince yapılır (kirli bayrağı); düşük güç modunda basit gölgelendirme. Birim: mm. */

const S3 = {
  kap: null, r: null, sahne: null, kam: null, eksen: null, eksenKam: null, kirli: true, dusuk: false,
  hedef: null, kure: { r: 400, teta: 0.9, fi: 1.0 }, sinir: null, tel: false, izgara: false, vurgu: null,
  g: {}, mat: {}, etiketler: [], vaka: null, vakaAnahtar: null, izgaraVeri: null,
  mod: "girdi", son: { liste: null, sec: null, meta: null, kareler: new Map(), i: 0, alan: "T", kesit: 0.5, izo: null, oynat: null, yukleniyor: false },
};
const s3Tr = () => DIL === "tr";
const S3_RENK = [[0, 0, 1], [0, 1, 1], [0, 1, 0], [1, 1, 0], [1, 0, 0]];         // ANSYS gökkuşağı
function s3Renk(u) {
  u = Math.max(0, Math.min(1, u)) * (S3_RENK.length - 1);
  const i = Math.min(S3_RENK.length - 2, Math.floor(u)), f = u - i, a = S3_RENK[i], b = S3_RENK[i + 1];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}
const S3_BIRIM = { T: "K", O2: "kütle kesri", U: "m/s" };
const s3Gbant = (g) => (g == null ? "–" : g < 0.01 ? (s3Tr() ? "uzay (μg)" : "space (μg)") : g < 0.27 ? (s3Tr() ? "Ay" : "Moon") : g < 0.6 ? "Mars" : (s3Tr() ? "Dünya" : "Earth"));

/* ------------------------------------------------------------------ kurulum */
function s3DusukGuc() {
  const e = S.sisEk || {};
  return /low|quiet|power-saver|cool/i.test(e.profil || "") || (e.pil && e.pil.prizde === false);
}

function s3Kur() {
  if (S3.r) return true;
  if (!window.THREE) return false;
  S3.dusuk = s3DusukGuc();
  const kap = document.createElement("div");
  kap.className = "s3-kap";
  kap.innerHTML = `<canvas class="s3-tuval"></canvas><div class="s3-etiketler"></div><div class="s3-arac"></div><div class="s3-ust"></div>` +
    `<div class="s3-olcek" hidden></div><div class="s3-sonuc" hidden></div><div class="s3-not"></div>`;
  S3.kap = kap;
  const tuval = kap.querySelector("canvas");
  try {
    S3.r = new THREE.WebGLRenderer({ canvas: tuval, antialias: !S3.dusuk, alpha: false, powerPreference: S3.dusuk ? "low-power" : "default" });
  } catch (e) { S3.r = null; return false; }
  S3.r.setPixelRatio(Math.min(window.devicePixelRatio || 1, S3.dusuk ? 1 : 1.5));
  S3.r.autoClear = false;
  S3.sahne = new THREE.Scene();
  S3.kam = new THREE.PerspectiveCamera(35, 1, 0.05, 200000);
  S3.hedef = new THREE.Vector3();
  S3.sahne.add(new THREE.HemisphereLight(0xffffff, 0x444466, S3.dusuk ? 1.1 : 0.85));
  if (!S3.dusuk) { const d = new THREE.DirectionalLight(0xffffff, 0.7); d.position.set(1, 2, 1.5); S3.sahne.add(d); S3.isik = d; }
  ["geo", "ok", "kutu", "izgara", "sonuc", "olcu"].forEach((a) => { S3.g[a] = new THREE.Group(); S3.sahne.add(S3.g[a]); });
  // eksen üçlüsü (sağ alt)
  S3.eksen = new THREE.Scene();
  S3.eksenKam = new THREE.OrthographicCamera(-1.6, 1.6, 1.6, -1.6, 0.1, 10);
  [[1, 0, 0, 0xe03030], [0, 1, 0, 0x30b030], [0, 0, 1, 0x3060e0]].forEach(([x, y, z, c]) =>
    S3.eksen.add(new THREE.ArrowHelper(new THREE.Vector3(x, y, z), new THREE.Vector3(), 1.1, c, 0.3, 0.18)));
  s3Kontrol(tuval);
  new ResizeObserver(() => s3Boyut()).observe(kap);
  const dongu = () => { requestAnimationFrame(dongu); if (S3.kirli && S3.kap.isConnected) { S3.kirli = false; s3Ciz(); } };
  dongu();
  return true;
}

function s3Boyut() {
  if (!S3.r || !S3.kap.isConnected) return;
  const w = S3.kap.clientWidth, h = S3.kap.clientHeight;
  if (w < 10 || h < 10) return;
  S3.r.setSize(w, h, false);
  S3.kam.aspect = w / h; S3.kam.updateProjectionMatrix();
  S3.kirli = true;
}

/* fare: sol sürükle döndür, sağ/orta ya da Shift kaydır, tekerlek yakınlaştır */
function s3Kontrol(el) {
  let bas = null;
  el.addEventListener("contextmenu", (e) => e.preventDefault());
  el.addEventListener("pointerdown", (e) => { bas = { x: e.clientX, y: e.clientY, b: e.button, sh: e.shiftKey }; el.setPointerCapture(e.pointerId); });
  el.addEventListener("pointerup", () => { bas = null; });
  el.addEventListener("pointermove", (e) => {
    if (!bas) return;
    const dx = e.clientX - bas.x, dy = e.clientY - bas.y; bas.x = e.clientX; bas.y = e.clientY;
    if (bas.b === 0 && !bas.sh) {
      S3.kure.teta -= dx * 0.008; S3.kure.fi = Math.max(0.03, Math.min(Math.PI - 0.03, S3.kure.fi - dy * 0.008));
    } else {
      const k = S3.kure.r * 0.0018, sag = new THREE.Vector3().setFromMatrixColumn(S3.kam.matrix, 0), yuk = new THREE.Vector3().setFromMatrixColumn(S3.kam.matrix, 1);
      S3.hedef.addScaledVector(sag, -dx * k).addScaledVector(yuk, dy * k);
    }
    s3Kamera();
  });
  el.addEventListener("wheel", (e) => { e.preventDefault(); S3.kure.r *= Math.exp(e.deltaY * 0.0012); s3Kamera(); }, { passive: false });
}

function s3Kamera() {
  const k = S3.kure;
  S3.kam.position.set(S3.hedef.x + k.r * Math.sin(k.fi) * Math.sin(k.teta), S3.hedef.y + k.r * Math.cos(k.fi), S3.hedef.z + k.r * Math.sin(k.fi) * Math.cos(k.teta));
  S3.kam.lookAt(S3.hedef);
  S3.kam.near = Math.max(0.01, k.r / 2000); S3.kam.far = k.r * 50; S3.kam.updateProjectionMatrix();
  S3.kirli = true;
}

function s3Gorunum(ad) {
  const yon = { on: [0, Math.PI / 2], ust: [0, 0.0001], yan: [Math.PI / 2, Math.PI / 2], izo: [0.8, 0.95] }[ad];
  if (yon) { S3.kure.teta = yon[0]; S3.kure.fi = yon[1]; }
  s3Sigdir();
}

function s3Sigdir() {
  const b = S3.sinir || new THREE.Box3(new THREE.Vector3(-50, -50, -50), new THREE.Vector3(50, 50, 50));
  const m = b.getCenter(new THREE.Vector3()), boyut = b.getSize(new THREE.Vector3()).length();
  S3.hedef.copy(m);
  S3.kure.r = Math.max(5, boyut * 1.25 / Math.tan((S3.kam.fov * Math.PI) / 360) / 2);
  s3Kamera();
}

function s3Ciz() {
  const r = S3.r, w = S3.kap.clientWidth, h = S3.kap.clientHeight;
  const koyu = document.documentElement.dataset.tema === "koyu" || document.body.classList.contains("koyu");
  r.setScissorTest(false);
  r.setClearColor(new THREE.Color(getComputedStyle(document.body).getPropertyValue("--girdi").trim() || (koyu ? "#1e1e1e" : "#f3f3f3")), 1);
  r.clear();
  r.render(S3.sahne, S3.kam);
  // eksen üçlüsü
  const n = 90;
  r.setScissorTest(true); r.setScissor(w - n - 6, 6, n, n); r.setViewport(w - n - 6, 6, n, n);
  r.clearDepth();
  const yon = new THREE.Vector3().subVectors(S3.kam.position, S3.hedef).normalize().multiplyScalar(4);
  S3.eksenKam.position.copy(yon); S3.eksenKam.up.copy(S3.kam.up); S3.eksenKam.lookAt(0, 0, 0);
  r.render(S3.eksen, S3.eksenKam);
  r.setScissorTest(false); r.setViewport(0, 0, w, h);
  s3EtiketYaz();
}

/* HTML etiketler (ölçü, g, akış, ortam) — 3B konumdan ekrana iz düşümü */
function s3Etiket(metin, konum, sinif) { S3.etiketler.push({ metin, konum: konum.clone(), sinif: sinif || "" }); }
function s3EtiketYaz() {
  const kat = S3.kap.querySelector(".s3-etiketler"), w = S3.kap.clientWidth, h = S3.kap.clientHeight;
  const eksen = [["x", new THREE.Vector3(1.4, 0, 0)], ["y", new THREE.Vector3(0, 1.4, 0)], ["z", new THREE.Vector3(0, 0, 1.4)]].map(([a, v]) => {
    const p = v.clone().project(S3.eksenKam);
    return `<span class="s3-eks" style="left:${(w - 96 + (p.x + 1) * 45).toFixed(0)}px;top:${(h - 96 + (1 - p.y) * 45).toFixed(0)}px">${a}</span>`;
  });
  kat.innerHTML = S3.etiketler.map((e) => {
    const p = e.konum.clone().project(S3.kam);
    if (p.z > 1 || p.z < -1) return "";
    return `<span class="s3-etiket ${e.sinif}" style="left:${((p.x + 1) / 2 * w).toFixed(0)}px;top:${((1 - p.y) / 2 * h).toFixed(0)}px">${esc(e.metin)}</span>`;
  }).join("") + eksen.join("");
}

/* ------------------------------------------------------------------ yardımcı çizimler */
function s3Temizle(grup) { while (grup.children.length) { const c = grup.children.pop(); c.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material && o.material.map) o.material.map.dispose(); if (o.material) o.material.dispose(); }); } }
function s3Malzeme(renk, ek) {
  const M = S3.dusuk ? THREE.MeshLambertMaterial : THREE.MeshStandardMaterial;
  return new M(Object.assign({ color: renk, wireframe: S3.tel }, S3.dusuk ? {} : { roughness: 0.6, metalness: 0.1 }, ek || {}));
}
function s3Kutu(x0, y0, z0, x1, y1, z1, renk, saydam) {
  const gr = new THREE.Group();
  const geo = new THREE.BoxGeometry(x1 - x0, y1 - y0, z1 - z0);
  const kenar = new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color: renk }));
  const yuz = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: renk, transparent: true, opacity: saydam == null ? 0.05 : saydam, depthWrite: false }));
  [kenar, yuz].forEach((o) => { o.position.set((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2); gr.add(o); });
  gr.userData.kenar = kenar;
  return gr;
}
function s3Ok(bas, yon, uzunluk, renk, kalin) {
  const u = Math.max(uzunluk, 1e-6);
  return new THREE.ArrowHelper(yon.clone().normalize(), bas, u, renk, Math.min(u * 0.35, kalin * 3), Math.min(u * 0.2, kalin * 1.6));
}
function s3Olcu(a, b, metin, kayma) {
  const g = new THREE.BufferGeometry().setFromPoints([a.clone().add(kayma), b.clone().add(kayma), a.clone(), a.clone().add(kayma), b.clone(), b.clone().add(kayma)]);
  const l = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints([a.clone().add(kayma), b.clone().add(kayma), a.clone(), a.clone().add(kayma), b.clone(), b.clone().add(kayma)]), new THREE.LineBasicMaterial({ color: 0x888888 }));
  g.dispose();
  S3.g.olcu.add(l);
  s3Etiket(metin, a.clone().add(b).multiplyScalar(0.5).add(kayma), "olcu");
}
const s3mm = (v) => (v >= 100 ? nf(v, 0) : v >= 10 ? nf(v, 1) : nf(v, 2)) + " mm";

/* ------------------------------------------------------------------ geometri (girdiye göre) */
function s3Parametre() {
  const vd = malzemeVarsayilani(S.girdi.malzeme) || [];
  const tip = S.girdi.numune_tipi || vd[0] || "thin_sheet";
  const kal = S.girdi.kalinlik != null && !isNaN(S.girdi.kalinlik) ? S.girdi.kalinlik : vd[1];
  const yakit = S.girdi.yakit_turu || vd[2] || (GAZ_NUMUNE.indexOf(tip) >= 0 ? "gaz" : tip === "droplet" ? "sivi" : "kati");
  return { malzeme: String(S.girdi.malzeme || "").trim(), tip, kal, yakit, g: S.girdi.g, akis: S.girdi.akisBilinmiyor ? null : S.girdi.akis,
           oksijen: S.girdi.oksijen, basinc: S.girdi.basinc };
}

async function s3VakaAl(p) {
  const anahtar = p.malzeme.toLowerCase();
  if (S3.vakaAnahtar === anahtar) return S3.vaka;
  S3.vakaAnahtar = anahtar;
  try { S3.vaka = await API.sahneVaka({ malzeme: p.malzeme, kalinlik: p.kal }); } catch (e) { S3.vaka = { kaynak: "temsili" }; }
  return S3.vaka;
}

function s3Geometri(p, vaka) {
  ["geo", "ok", "kutu", "olcu", "izgara"].forEach((a) => s3Temizle(S3.g[a]));
  S3.etiketler = []; S3.mat = {};
  const tr = s3Tr(), V = THREE.Vector3;
  const sayfa = ["thin_sheet", "fabric", "thick_sheet", "rod", "wire", "pool"].indexOf(p.tip) >= 0 || (p.yakit === "kati" && p.tip !== "sphere" && p.tip !== "droplet");
  const gaz = GAZ_NUMUNE.indexOf(p.tip) >= 0 || p.yakit === "gaz";
  let kutu, nesneMerkez, temsili = true;
  const mNumune = s3Malzeme(0xd9a441, { emissive: 0x000000 });
  S3.mat.numune = mNumune;
  if (vaka && vaka.kaynak === "vaka" && vaka.bolge && sayfa) {
    // OpenFOAM Saffire vakası: gerçek boyutlar (m → mm)
    temsili = false;
    const f = vaka.bolge.fluid, sb = vaka.bolge.sibal, mm = (v) => v.map((x) => x * 1000);
    const [fx0, fy0, fz0] = mm(f.min), [fx1, fy1, fz1] = mm(f.max), [sx0, sy0, sz0] = mm(sb.min), [sx1, sy1, sz1] = mm(sb.max);
    kutu = [fx0, fy0, fz0, fx1, fy1, fz1];
    const kalG = Math.max(sy1 - sy0, 0.6);                                     // 0,16 mm: görünür olsun diye en az 0,6 mm çizilir
    const lev = new THREE.Mesh(new THREE.BoxGeometry(sx1 - sx0, kalG, sz1 - sz0), mNumune);
    lev.position.set((sx0 + sx1) / 2, -kalG / 2, (sz0 + sz1) / 2); S3.g.geo.add(lev);
    if (vaka.tel) {
      const rr = Math.max(vaka.tel.r * 1000, 0.6);
      const tel = new THREE.Mesh(new THREE.CylinderGeometry(rr, rr, fz1 - fz0, 10), s3Malzeme(0xb04020, { emissive: 0x401000 }));
      tel.rotation.x = Math.PI / 2; tel.position.set(vaka.tel.x * 1000, rr, 0); S3.g.geo.add(tel);
      s3Etiket(tr ? "ateşleyici teli" : "igniter wire", new V(vaka.tel.x * 1000, 12, fz1), "kucuk");
    }
    s3Olcu(new V(sx0, 0, fz1), new V(sx1, 0, fz1), (tr ? "numune " : "sample ") + s3mm(sx1 - sx0), new V(0, -18, 0));
    s3Olcu(new V(fx0, fy0, fz1), new V(fx0, fy1, fz1), s3mm(fy1 - fy0), new V(-25, 0, 0));
    s3Olcu(new V(fx0, fy1, fz0), new V(fx1, fy1, fz0), s3mm(fx1 - fx0), new V(0, 18, 0));
    s3Etiket((tr ? "2B vaka · derinlik " : "2D case · depth ") + s3mm(fz1 - fz0) + (tr ? " · kalınlık " : " · thickness ") + s3mm(sy1 - sy0), new V(sx1, -40, fz1), "kucuk");
    nesneMerkez = new V((sx0 + sx1) / 2, 0, 0);
  } else if (sayfa) {
    const L = 100, W = 50, k = Math.max(p.kal || 0.2, 0.05), kG = Math.max(k, 0.5);
    kutu = [-120, -60, -60, 180, 90, 60];
    const lev = new THREE.Mesh(new THREE.BoxGeometry(L, kG, W), mNumune); lev.position.set(L / 2, 0, 0); S3.g.geo.add(lev);
    const cer = s3Malzeme(0x707680);                                                       // tutucu çerçeve
    [[L / 2, -W / 2 - 3, L + 12, 6], [L / 2, W / 2 + 3, L + 12, 6]].forEach(([x, z, lx, lz]) => { const m = new THREE.Mesh(new THREE.BoxGeometry(lx, 3, lz), cer); m.position.set(x, -kG / 2 - 1.5, z); S3.g.geo.add(m); });
    [[-3], [L + 3]].forEach(([x]) => { const m = new THREE.Mesh(new THREE.BoxGeometry(6, 3, W + 12), cer); m.position.set(x, -kG / 2 - 1.5, 0); S3.g.geo.add(m); });
    const tel = new THREE.Mesh(new THREE.CylinderGeometry(0.6, 0.6, W + 6, 10), s3Malzeme(0xb04020, { emissive: 0x401000 }));
    tel.rotation.x = Math.PI / 2; tel.position.set(2, kG / 2 + 0.8, 0); S3.g.geo.add(tel);
    s3Etiket(tr ? "ateşleyici teli" : "igniter wire", new V(2, 10, W / 2 + 4), "kucuk");
    s3Olcu(new V(0, 0, W / 2), new V(L, 0, W / 2), s3mm(L), new V(0, 0, 14));
    s3Olcu(new V(L, 0, -W / 2), new V(L, 0, W / 2), s3mm(W), new V(14, 0, 0));
    s3Etiket((tr ? "kalınlık " : "thickness ") + s3mm(k) + (kG > k ? (tr ? " (görünür olsun diye büyütüldü)" : " (exaggerated for visibility)") : ""), new V(L / 2, -12, -W / 2), "kucuk");
    nesneMerkez = new V(L / 2, 0, 0);
  } else if (!gaz) {
    // damla (ya da küre): fiberde asılı, kutu içinde
    const d = Math.max(p.kal || 2, 0.2), r = d / 2, yk = Math.max(6 * d, 6);        // kutu damlaya göre (temsili)
    kutu = [-yk, -yk, -yk, yk, yk, yk];
    const kure = new THREE.Mesh(new THREE.SphereGeometry(r, 32, 20), s3Malzeme(p.tip === "droplet" ? 0x5aa0e0 : 0xd9a441, { transparent: p.tip === "droplet", opacity: 0.9 }));
    S3.mat.numune = kure.material; S3.g.geo.add(kure);
    const fib = s3Malzeme(0x404040);
    [0, Math.PI / 2].forEach((a) => { const f = new THREE.Mesh(new THREE.CylinderGeometry(Math.max(0.02, d * 0.03), Math.max(0.02, d * 0.03), 2 * yk, 6), fib); f.rotation.z = Math.PI / 2; f.rotation.y = a; S3.g.geo.add(f); });
    [-1, 1].forEach((s) => { const t = new THREE.Mesh(new THREE.TorusGeometry(0.8, 0.12, 6, 16), s3Malzeme(0xb04020, { emissive: 0x401000 })); t.scale.setScalar(Math.max(0.3, d / 2)); t.position.set(0, -r * 0.2, s * (r + 1.6 * Math.max(0.3, d / 2))); S3.g.geo.add(t); });
    s3Etiket(tr ? "ateşleyici (iki tel)" : "igniters (two wires)", new V(0, -r * 1.5, r * 2.5), "kucuk");
    s3Etiket(tr ? "SiC fiber" : "SiC fibre", new V(yk * 0.75, r * 0.4, 0), "kucuk");
    s3Olcu(new V(-r, 0, 0), new V(r, 0, 0), "d₀ = " + s3mm(d), new V(0, r * 2.2, 0));
    nesneMerkez = new V(0, 0, 0);
  } else {
    // gaz: gözenekli küre / jet / düz brülör
    const d = Math.max(p.kal || (p.tip === "flat_burner" ? 25 : 6.35), 0.5), r = d / 2, yk = Math.max(5 * d, 20);
    kutu = [-yk, -yk, -yk, yk, yk * 1.3, yk];
    const boru = s3Malzeme(0x8a8f98);
    if (p.tip === "flat_burner") {
      const b = new THREE.Mesh(new THREE.CylinderGeometry(r, r, 5, 32), mNumune); b.position.y = -2.5; S3.g.geo.add(b);
      const ay = new THREE.Mesh(new THREE.CylinderGeometry(3, 3, 50, 12), boru); ay.position.y = -30; S3.g.geo.add(ay);
    } else if (p.tip === "gas_jet") {
      const b = new THREE.Mesh(new THREE.CylinderGeometry(r, r, 30, 24, 1, true), mNumune); b.position.y = -15; S3.g.geo.add(b);
      const ic = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.8, r * 0.8, 30.2, 24), s3Malzeme(0x202020)); ic.position.y = -15; S3.g.geo.add(ic);
    } else {
      const k = new THREE.Mesh(new THREE.SphereGeometry(r, 32, 20), mNumune); S3.g.geo.add(k);
      const ay = new THREE.Mesh(new THREE.CylinderGeometry(Math.max(r * 0.25, 0.4), Math.max(r * 0.25, 0.4), 50, 12), boru); ay.position.y = -r - 25; S3.g.geo.add(ay);
    }
    const tel = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.3, 14, 8), s3Malzeme(0xb04020, { emissive: 0x401000 }));
    tel.rotation.z = Math.PI / 2; tel.position.set(r + 8, r * 0.6, 0); S3.g.geo.add(tel);
    s3Etiket(tr ? "ateşleyici" : "igniter", new V(r + 10, r + 4, 0), "kucuk");
    s3Etiket({ porous_sphere: tr ? "gözenekli küre brülör (sızıntı)" : "porous-sphere burner (leak)", gas_jet: tr ? "jet ağzı" : "jet nozzle", flat_burner: tr ? "düz brülör" : "flat burner" }[p.tip] || (tr ? "gaz kaynağı" : "gas source"), new V(0, -r - 8, r + 6), "kucuk");
    s3Olcu(new V(-r, 0, 0), new V(r, 0, 0), "Ø " + s3mm(d), new V(0, r + 6, 0));
    nesneMerkez = new V(0, 0, 0);
  }
  // kabin kutusu (yarı saydam tel çerçeve) + zemin ızgarası
  const [x0, y0, z0, x1, y1, z1] = kutu;
  const kb = s3Kutu(x0, y0, z0, x1, y1, z1, 0x5a7fb0, 0.04); S3.g.kutu.add(kb); S3.mat.kutu = kb.userData.kenar.material;
  const gen = Math.max(x1 - x0, z1 - z0);
  const iz = new THREE.GridHelper(gen * 1.3, 20, 0x9a9a9a, 0xc8c8c8); iz.position.set((x0 + x1) / 2, y0 - 0.5, (z0 + z1) / 2);
  iz.material.transparent = true; iz.material.opacity = 0.45; S3.g.kutu.add(iz);
  S3.sinir = new THREE.Box3(new V(x0, y0, z0), new V(x1, y1, z1));
  const H = y1 - y0;
  // yerçekimi oku: uzunluk g ile (log ölçek); etiket bant adı
  const g = p.g == null || isNaN(p.g) ? 0 : p.g;
  const gU = g < 0.01 ? H * 0.06 : H * (0.12 + 0.28 * Math.min(1, Math.log10(g / 0.01) / 2));
  const gBas = new V(x1 + gen * 0.08, y1 - H * 0.05, z0);
  S3.g.ok.add(s3Ok(gBas, new V(0, -1, 0), gU, 0x7a3fb0, H * 0.02));
  s3Etiket(`g = ${gMetni(g)} g₀ · ${s3Gbant(g)}`, gBas.clone().add(new V(0, H * 0.04, 0)), "g");
  // akış okları (+x)
  const okRenk = 0x1f8fd6; S3.mat.okRenk = okRenk;
  if (p.akis == null) s3Etiket(tr ? "akış bilinmiyor (en kötü durum)" : "flow unknown (worst case)", new V(x0, y1 - H * 0.15, z1), "akis");
  else if (p.akis <= 0) s3Etiket(tr ? "durgun ortam (akış 0)" : "quiescent (no flow)", new V(x0, y1 - H * 0.15, z1), "akis");
  else {
    const u = Math.min(gen * 0.3, gen * 0.06 + gen * 0.012 * p.akis);
    [-0.25, 0.25].forEach((fy) => [-0.3, 0.3].forEach((fz) =>
      S3.g.ok.add(s3Ok(new V(x0 + gen * 0.02, (y0 + y1) / 2 + fy * H, (z0 + z1) / 2 + fz * (z1 - z0)), new V(1, 0, 0), u, okRenk, H * 0.015))));
    s3Etiket(`${tr ? "akış" : "flow"} ${nf(p.akis, 1)} cm/s`, new V(x0 + u * 0.5, (y0 + y1) / 2 + H * 0.33, z1), "akis");
  }
  s3Etiket(`%${nf(p.oksijen, 1)} O₂ · ${nf(p.basinc, 1)} kPa` + (S.girdi.seyreltici && S.girdi.seyreltici !== "n2" ? " · " + S.girdi.seyreltici.toUpperCase() : ""), new V(x0, y1 + H * 0.04, z0), "ortam");
  S3.kap.querySelector(".s3-not").innerHTML = temsili
    ? `<span class="etiket uyari">${esc(tr ? "temsili boyutlar" : "representative dimensions")}</span>`
    : `<span class="etiket">${esc(tr ? "boyutlar OpenFOAM vakasından (polyMesh)" : "dimensions from OpenFOAM case (polyMesh)")}</span>`;
  S3.temsili = temsili;
  if (S3.izgara) s3IzgaraCiz();
  s3Vurgula(S3.vurgu);
  return nesneMerkez;
}

async function s3IzgaraCiz() {
  s3Temizle(S3.g.izgara);
  if (!S3.izgara) { S3.kirli = true; return; }
  if (!S3.vaka || S3.vaka.kaynak !== "vaka" || S3.mod !== "girdi") {
    Kabuk.bildir(s3Tr() ? "Ağ (polyMesh) yalnız OpenFOAM vakası olan malzemede gösterilir (şimdilik SIBAL)." : "The mesh (polyMesh) is shown only for materials with an OpenFOAM case (SIBAL for now).", "", 5000);
    return;
  }
  if (!S3.izgaraVeri) S3.izgaraVeri = await API.sahneIzgara().catch(() => null);
  const v = S3.izgaraVeri;
  if (!v || !v.veri) return;
  const b = Uint8Array.from(atob(v.veri), (c) => c.charCodeAt(0));
  const f = new Float32Array(b.buffer);
  for (let i = 0; i < f.length; i++) f[i] *= 1000;
  const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.BufferAttribute(f, 3));
  S3.g.izgara.add(new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: 0x3a5f8f, transparent: true, opacity: 0.55 })));
  S3.kirli = true;
}

function s3Vurgula(id) {
  S3.vurgu = id;
  const n = S3.mat.numune;
  if (n && n.emissive) n.emissive.setHex(id === "malzeme" || id === "numune" ? 0x6a5200 : 0x000000);
  if (S3.mat.kutu) S3.mat.kutu.color.setHex(id === "ortam" ? 0xe0a000 : 0x5a7fb0);
  S3.g.ok.children.forEach((o) => { if (o.setColor && o.line && o.position.x < (S3.sinir ? S3.sinir.max.x : 1e9)) o.setColor(id === "akis" ? 0xff7a00 : S3.mat.okRenk || 0x1f8fd6); });
  S3.kirli = true;
}

/* ------------------------------------------------------------------ görünüm alanı */
function s3AracYaz() {
  const tr = s3Tr(), a = S3.kap.querySelector(".s3-arac");
  const d = (k, ad, sec) => `<button class="dugme kucuk${sec ? " birincil" : ""}" data-s3="${k}">${esc(ad)}</button>`;
  a.innerHTML = d("on", tr ? "Ön" : "Front") + d("ust", tr ? "Üst" : "Top") + d("yan", tr ? "Yan" : "Side") + d("izo", tr ? "İzometrik" : "Iso") +
    d("sigdir", tr ? "Sığdır" : "Fit") + d("tel", tr ? "Tel çerçeve" : "Wireframe", S3.tel) + d("izgara", tr ? "Izgara (ağ)" : "Mesh", S3.izgara);
  a.onclick = (e) => {
    const b = e.target.closest("[data-s3]"); if (!b) return;
    const k = b.dataset.s3;
    if (["on", "ust", "yan", "izo"].indexOf(k) >= 0) s3Gorunum(k);
    else if (k === "sigdir") s3Sigdir();
    else if (k === "tel") { S3.tel = !S3.tel; S3.sahne.traverse((o) => { if (o.isMesh && o.material && "wireframe" in o.material && !o.userData.sonuc) o.material.wireframe = S3.tel; }); S3.kirli = true; s3AracYaz(); }
    else if (k === "izgara") { S3.izgara = !S3.izgara; s3IzgaraCiz(); s3AracYaz(); }
  };
}

/* giriş noktası: mod "girdi" (ortam/malzeme/numune/akış) ya da "sonuc" (r-3b) */
async function s3Goster(mod, baslik, vurgu, ustHtml) {
  if (!s3Kur()) return false;
  const ilk = !S3.kap.isConnected || S3.mod !== mod;
  Kabuk.gorselYaz(baslik, `<div class="s3-yer"></div>`);
  const yer = document.querySelector("#gorsel .s3-yer");
  yer.appendChild(S3.kap);
  S3.kap.querySelector(".s3-ust").innerHTML = ustHtml || "";
  S3.mod = mod;
  s3AracYaz(); s3Boyut();
  const p = s3Parametre();
  const vaka = await s3VakaAl(p);
  if (!S3.kap.isConnected) return true;
  const yeniGeo = JSON.stringify([p, vaka && vaka.kaynak, S3.tel]);
  if (S3.sonGeo !== yeniGeo || mod === "girdi") { s3Geometri(p, vaka); S3.sonGeo = yeniGeo; }
  if (mod === "sonuc") await s3SonucHazirla();
  else { S3.g.sonuc.visible = false; S3.g.geo.visible = S3.g.ok.visible = true; S3.kap.querySelector(".s3-olcek").hidden = true; S3.kap.querySelector(".s3-sonuc").hidden = true; }
  s3Vurgula(vurgu);
  const sk = S3.sinir ? [S3.sinir.min.toArray(), S3.sinir.max.toArray()].join() : "";
  if (ilk || !S3.kamuraKuruldu) { S3.kamuraKuruldu = true; S3.sigdirSinir = sk; s3Gorunum("izo"); }
  else if (S3.sigdirSinir !== sk) { S3.sigdirSinir = sk; s3Sigdir(); }       // geometri boyutu değişti: yön aynı, sığdır
  S3.kirli = true;
  return true;
}

/* ------------------------------------------------------------------ SONUÇ: izo yüzey, kesit, damlalar */
function s3Eslesen(liste) {
  const t = S.sonuc && S.sonuc.tahmin, ad = String((t && t.girdi.malzeme) || S.girdi.malzeme || "").toLowerCase();
  const g = t ? t.girdi.g : S.girdi.g;
  const ayni = (a) => { a = String(a || "").toLowerCase(); return a && (a === ad || a.indexOf(ad) >= 0 || ad.indexOf(a) >= 0); };
  return liste.find((x) => x.kosul && ayni(x.kosul.malzeme) && s3Gbant(x.kosul.g) === s3Gbant(g)) || null;
}

async function s3SonucHazirla() {
  const tr = s3Tr(), so = S3.son;
  if (!so.liste) so.liste = await API.sonuc3bListe().catch(() => []);
  const es = s3Eslesen(so.liste);
  if (!so.sec || (so.otomatik && es && es.yol !== so.sec)) { so.sec = es ? es.yol : null; so.otomatik = true; }
  const panel = S3.kap.querySelector(".s3-sonuc"), ust = S3.kap.querySelector(".s3-ust");
  const secim = `<select class="giris" id="s3Sec"><option value="">${esc(tr ? "— 3B sonuç seç —" : "— pick 3D result —")}</option>` +
    so.liste.map((x) => `<option value="${esc(x.yol)}"${x.yol === so.sec ? " selected" : ""}>${esc(x.ad)} · ${esc(x.kosul && x.kosul.malzeme || "?")} · ${esc(s3Gbant(x.kosul && x.kosul.g))}</option>`).join("") + `</select>`;
  if (!so.sec) {
    ust.innerHTML = `<div class="s3-bant">${esc(tr ? "3B alan sonucu yok (hızlı çözüm)" : "No 3D field result (fast solve)")}` +
      `${so.liste.length ? ` · ${esc(tr ? "başka koşulun sonucu:" : "result of another condition:")} ${secim}` : ""}</div>`;
    S3.g.sonuc.visible = false; S3.g.geo.visible = S3.g.ok.visible = true;
    panel.hidden = true; S3.kap.querySelector(".s3-olcek").hidden = true;
    s3SecBagla(); return;
  }
  if (!so.meta || so.meta.yol !== so.sec) {
    so.meta = await API.sonuc3bMeta(so.sec); so.meta.yol = so.sec; so.kareler.clear(); so.i = so.meta.zamanlar.length - 1;
    so.alan = so.meta.alanlar.indexOf(so.alan) >= 0 ? so.alan : so.meta.alanlar[0];
    so.izo = null;
  }
  const m = so.meta;
  const k = m.kosul || {};
  const esit = es && es.yol === so.sec;
  ust.innerHTML = `<div class="s3-bant bilgi">${esc(tr ? "3B alan sonucu" : "3D field result")}: <b>${esc(m.ad)}</b> · ${esc(k.malzeme || "?")} · ${esc(s3Gbant(k.g))}` +
    (esit ? "" : ` · <span class="etiket uyari">${esc(tr ? "bu vakanın koşulu değil" : "not this case's condition")}</span>`) + ` ${secim}</div>`;
  s3SecBagla();
  S3.g.geo.visible = S3.g.ok.visible = false;
  // sonuç kutusu (alan sınırları, mm)
  const b = m.sinir.map((v) => v * 1000);
  S3.sinir = new THREE.Box3(new THREE.Vector3(b[0], b[2], b[4]), new THREE.Vector3(b[1], b[3], b[5]));
  s3Temizle(S3.g.kutu); S3.etiketler = []; s3Temizle(S3.g.olcu);
  const kb = s3Kutu(b[0], b[2], b[4], b[1], b[3], b[5], 0x5a7fb0, 0.02); S3.g.kutu.add(kb); S3.mat.kutu = kb.userData.kenar.material;
  s3Olcu(new THREE.Vector3(b[0], b[2], b[5]), new THREE.Vector3(b[1], b[2], b[5]), s3mm(b[1] - b[0]), new THREE.Vector3(0, -12, 0));
  s3Olcu(new THREE.Vector3(b[0], b[2], b[5]), new THREE.Vector3(b[0], b[3], b[5]), s3mm(b[3] - b[2]), new THREE.Vector3(-12, 0, 0));
  if (k.g != null) { const H = b[3] - b[2]; S3.g.ok.visible = true; s3Temizle(S3.g.ok); S3.g.ok.add(s3Ok(new THREE.Vector3(b[1] + H * 0.1, b[3], b[4]), new THREE.Vector3(0, -1, 0), k.g < 0.01 ? H * 0.06 : H * 0.3 * Math.min(1, 0.4 + k.g), 0x7a3fb0, H * 0.02)); s3Etiket(`g = ${gMetni(k.g)} g₀ · ${s3Gbant(k.g)}`, new THREE.Vector3(b[1] + H * 0.1, b[3] + H * 0.05, b[4]), "g"); }
  S3.g.sonuc.visible = true;
  S3.kap.querySelector(".s3-not").innerHTML = `<span class="etiket">${esc(tr ? "boyutlar koşunun ağından (ResampleToImage " + m.boyut.join("×") + ")" : "dimensions from the run mesh (ResampleToImage " + m.boyut.join("×") + ")")}</span>` +
    (m.yansitildi ? ` <span class="etiket">${esc(tr ? "z = 0 simetri düzleminde yansıtıldı" : "mirrored at z = 0 symmetry plane")}</span>` : "");
  panel.hidden = false;
  s3PanelYaz();
  await s3KareGoster(so.i);
  if (!S3.sonucKamera || S3.sonucKamera !== so.sec) { S3.sonucKamera = so.sec; s3Gorunum("izo"); }
}

function s3SecBagla() {
  const s = document.getElementById("s3Sec");
  if (s) s.onchange = () => { S3.son.sec = s.value || null; S3.son.otomatik = false; S3.son.meta = null; s3SonucHazirla(); };
}

function s3PanelYaz() {
  const tr = s3Tr(), so = S3.son, m = so.meta;
  const izoV = so.izo || s3IzoVarsayilan();
  S3.kap.querySelector(".s3-sonuc").innerHTML =
    `<div class="s3-satir"><button class="dugme kucuk" id="s3Oynat">${so.oynat ? "❚❚" : "▶"}</button>` +
    `<input type="range" id="s3Zaman" min="0" max="${m.zamanlar.length - 1}" value="${so.i}" style="flex:1">` +
    `<span class="sayi" id="s3T">t = ${esc(nf(m.zamanlar[so.i], 3))} s</span></div>` +
    `<div class="s3-satir"><label>${esc(tr ? "Alan" : "Field")} <select class="giris" id="s3Alan">${m.alanlar.map((a) => `<option${a === so.alan ? " selected" : ""}>${esc(a)}</option>`).join("")}</select></label>` +
    `<label>${esc(tr ? "Kesit z" : "Slice z")} <input type="range" id="s3Kesit" min="0" max="1" step="0.01" value="${so.kesit}"></label>` +
    `<label>${esc(tr ? "İzo" : "Iso")} <input class="giris" id="s3Izo" value="${esc(izoV.map((v) => +v.toPrecision(4)).join(", "))}" style="width:120px"></label>` +
    `<button class="dugme kucuk" id="s3Pv">${esc(tr ? "ParaView'da aç" : "Open in ParaView")}</button></div>`;
  const $q = (s) => S3.kap.querySelector(s);
  $q("#s3Zaman").oninput = (e) => s3KareGoster(Number(e.target.value));
  $q("#s3Alan").onchange = (e) => { so.alan = e.target.value; so.izo = null; s3PanelYaz(); s3KareGoster(so.i); };
  $q("#s3Kesit").oninput = (e) => { so.kesit = Number(e.target.value); s3KesitCiz(); };
  $q("#s3Izo").onchange = (e) => { const v = e.target.value.split(/[;, ]+/).map(Number).filter((x) => isFinite(x)); so.izo = v.slice(0, 4); s3IzoCiz(); };
  $q("#s3Oynat").onclick = () => {
    if (so.oynat) { clearInterval(so.oynat); so.oynat = null; }
    else so.oynat = setInterval(() => { if (!S3.kap.isConnected) { clearInterval(so.oynat); so.oynat = null; return; } s3KareGoster((so.i + 1) % m.zamanlar.length); }, 500);
    $q("#s3Oynat").textContent = so.oynat ? "❚❚" : "▶";
  };
  $q("#s3Pv").onclick = async () => {
    const r = await API.paraviewAc(m.kosu).catch((e) => ({ hata: e.message }));
    if (r.hata) Kabuk.bildir(r.hata, "hata"); else { Kabuk.bildir((tr ? "ParaView açılıyor: " : "Opening ParaView: ") + r.aciklama, "basari", 6000); mesaj("bilgi", "ParaView: " + r.komut); }
  };
}

function s3IzoVarsayilan() {
  const so = S3.son, ar = so.meta.aralik[so.alan];
  if (so.alan === "T") return [1200, 2000].filter((v) => v > ar[0] && v < ar[1]).concat(ar[1] <= 1200 ? [ar[0] + 0.6 * (ar[1] - ar[0])] : []);
  return [ar[0] + 0.3 * (ar[1] - ar[0]), ar[0] + 0.7 * (ar[1] - ar[0])];
}

async function s3KareGoster(i) {
  const so = S3.son, m = so.meta;
  so.i = i;
  let k = so.kareler.get(i);
  if (!k) {
    if (so.yukleniyor) return;
    so.yukleniyor = true;
    try { k = await API.sonuc3bKare(so.sec, i); } finally { so.yukleniyor = false; }
    const coz = (b64) => { const b = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)); return new Uint16Array(b.buffer); };
    k.q = {}; Object.keys(k.alanlar).forEach((a) => { k.q[a] = coz(k.alanlar[a]); }); delete k.alanlar;
    const db = Uint8Array.from(atob(k.damla), (c) => c.charCodeAt(0)); k.d = new Float32Array(db.buffer);
    so.kareler.set(i, k);
    if (so.kareler.size > 24) so.kareler.delete(so.kareler.keys().next().value);
  }
  const zs = S3.kap.querySelector("#s3Zaman"); if (zs) zs.value = i;
  const tt = S3.kap.querySelector("#s3T"); if (tt) tt.textContent = `t = ${nf(m.zamanlar[i], 3)} s`;
  s3IzoCiz(); s3KesitCiz(); s3DamlaCiz(); s3OlcekYaz();
}

function s3Deger(q, j, ar) { return q[j] === 0 ? NaN : ar[0] + (q[j] - 1) / 65534 * (ar[1] - ar[0]); }

function s3SonucTemizle(ad) {
  const g = S3.g.sonuc;
  g.children.filter((o) => o.userData.tur === ad).forEach((o) => { g.remove(o); o.geometry.dispose(); if (o.material.map) o.material.map.dispose(); o.material.dispose(); });
}

/* marching tetrahedra (küp → 6 dörtyüzlü): izo yüzeyi; geçersiz (alan dışı) hücreler atlanır */
function s3IzoCiz() {
  s3SonucTemizle("izo");
  const so = S3.son, m = so.meta, k = so.kareler.get(so.i);
  if (!k) return;
  const [nx, ny, nz] = m.boyut, q = k.q[so.alan], ar = m.aralik[so.alan], b = m.sinir.map((v) => v * 1000);
  const dx = (b[1] - b[0]) / (nx - 1), dy = (b[3] - b[2]) / (ny - 1), dz = (b[5] - b[4]) / (nz - 1);
  const f = new Float32Array(q.length); for (let j = 0; j < q.length; j++) f[j] = s3Deger(q, j, ar);
  const idx = (x, y, z) => (z * ny + y) * nx + x;
  const KO = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]];
  const TET = [[0, 5, 1, 6], [0, 1, 2, 6], [0, 2, 3, 6], [0, 3, 7, 6], [0, 7, 4, 6], [0, 4, 5, 6]];
  (so.izo || s3IzoVarsayilan()).forEach((iso, ii) => {
    const p = [];
    const kv = new Float32Array(8), kx = new Float32Array(8), ky = new Float32Array(8), kz = new Float32Array(8);
    const kes = (a, c) => { const t = (iso - kv[a]) / (kv[c] - kv[a]); p.push(kx[a] + t * (kx[c] - kx[a]), ky[a] + t * (ky[c] - ky[a]), kz[a] + t * (kz[c] - kz[a])); };
    for (let z = 0; z < nz - 1; z++) for (let y = 0; y < ny - 1; y++) for (let x = 0; x < nx - 1; x++) {
      let lo = Infinity, hi = -Infinity, bad = false;
      for (let c = 0; c < 8; c++) {
        const v = f[idx(x + KO[c][0], y + KO[c][1], z + KO[c][2])];
        if (v !== v) { bad = true; break; }
        kv[c] = v; if (v < lo) lo = v; if (v > hi) hi = v;
      }
      if (bad || lo > iso || hi < iso) continue;
      for (let c = 0; c < 8; c++) { kx[c] = b[0] + (x + KO[c][0]) * dx; ky[c] = b[2] + (y + KO[c][1]) * dy; kz[c] = b[4] + (z + KO[c][2]) * dz; }
      for (const t of TET) {
        const ic = t.filter((c) => kv[c] >= iso), dis = t.filter((c) => kv[c] < iso);
        if (ic.length === 0 || ic.length === 4) continue;
        if (ic.length === 1 || ic.length === 3) {
          const a = ic.length === 1 ? ic[0] : dis[0], o = ic.length === 1 ? dis : ic;
          kes(a, o[0]); kes(a, o[1]); kes(a, o[2]);
        } else {
          kes(ic[0], dis[0]); kes(ic[0], dis[1]); kes(ic[1], dis[1]);
          kes(ic[0], dis[0]); kes(ic[1], dis[1]); kes(ic[1], dis[0]);
        }
      }
    }
    if (!p.length) return;
    const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.Float32BufferAttribute(p, 3)); geo.computeVertexNormals();
    const rk = s3Renk((iso - ar[0]) / (ar[1] - ar[0] || 1));
    const mat = new (S3.dusuk ? THREE.MeshLambertMaterial : THREE.MeshStandardMaterial)({ color: new THREE.Color(rk[0], rk[1], rk[2]), side: THREE.DoubleSide,
      transparent: true, opacity: ii === 0 ? 0.35 : 0.85, depthWrite: ii !== 0 });
    const ms = new THREE.Mesh(geo, mat); ms.userData = { tur: "izo", sonuc: true };
    S3.g.sonuc.add(ms);
  });
  S3.kirli = true;
}

function s3KesitCiz() {
  s3SonucTemizle("kesit");
  const so = S3.son, m = so.meta, k = so.kareler.get(so.i);
  if (!k) return;
  const [nx, ny, nz] = m.boyut, q = k.q[so.alan], ar = m.aralik[so.alan], b = m.sinir.map((v) => v * 1000);
  const kz = Math.round(so.kesit * (nz - 1));
  const veri = new Uint8Array(nx * ny * 4);
  for (let y = 0; y < ny; y++) for (let x = 0; x < nx; x++) {
    const j = (kz * ny + y) * nx + x, o = (y * nx + x) * 4;
    if (q[j] === 0) { veri[o + 3] = 0; continue; }
    const c = s3Renk((q[j] - 1) / 65534);
    veri[o] = c[0] * 255; veri[o + 1] = c[1] * 255; veri[o + 2] = c[2] * 255; veri[o + 3] = 235;
  }
  const tex = new THREE.DataTexture(veri, nx, ny, THREE.RGBAFormat); tex.magFilter = tex.minFilter = THREE.LinearFilter; tex.needsUpdate = true;
  const geo = new THREE.PlaneGeometry(b[1] - b[0], b[3] - b[2]);
  const ms = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ map: tex, transparent: true, side: THREE.DoubleSide, depthWrite: false }));
  ms.position.set((b[0] + b[1]) / 2, (b[2] + b[3]) / 2, b[4] + kz * (b[5] - b[4]) / (nz - 1)); ms.userData = { tur: "kesit", sonuc: true };
  S3.g.sonuc.add(ms);
  S3.kirli = true;
}

function s3DamlaCiz() {
  s3SonucTemizle("damla");
  const k = S3.son.kareler.get(S3.son.i);
  if (!k || !k.d.length) return;
  const p = new Float32Array(k.d.length); for (let i = 0; i < p.length; i++) p[i] = k.d[i] * 1000;
  const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.BufferAttribute(p, 3));
  const ms = new THREE.Points(geo, new THREE.PointsMaterial({ color: 0xffffff, size: 3, sizeAttenuation: false, depthTest: false, transparent: true, opacity: 0.9 }));
  ms.userData = { tur: "damla", sonuc: true }; S3.g.sonuc.add(ms);
  S3.kirli = true;
}

function s3OlcekYaz() {
  const so = S3.son, ar = so.meta.aralik[so.alan], el = S3.kap.querySelector(".s3-olcek"), k = so.kareler.get(so.i);
  const birim = S3_BIRIM[so.alan] || (so.alan === so.meta.yakit_alani ? (s3Tr() ? "kütle kesri" : "mass fraction") : "");
  const n = 8, tik = [];
  for (let i = n; i >= 0; i--) tik.push(`<span>${esc((+(ar[0] + i / n * (ar[1] - ar[0])).toPrecision(4)).toString())}</span>`);
  el.hidden = false;
  el.innerHTML = `<b>${esc(so.alan)}</b><small>${esc(birim)}</small><div class="s3-cubuk-kap"><div class="s3-cubuk"></div><div class="s3-tik">${tik.join("")}</div></div>` +
    `<small>${esc(s3Tr() ? "damla" : "droplets")}: ${k ? k.damla_sayisi : 0}</small>`;
}
