#!/usr/bin/env python3
"""Saffire-III S1 kati-bolge vakasi: conformal 2D blockMeshDict ureticisi.

Bolgeler (cellZone): fluid, tel (Kanthal, O-grid), sibal (kumas yarim kalinligi).
Tel kumas yuzeyinde, yaricapin %10'u kadar gomulu (kullanici karari).
Cikti: system/blockMeshDict. Blok yonelimi (sag el) ve paylasilan kenar hucre
sayilari script icinde kontrol edilir; tutarsizlikta durur.
"""
import math
from pathlib import Path

# ---------------- Geometri [m] ----------------
X0, X1, X4, X5 = 0.0, 0.15, 1.09, 1.30
H = 0.30
xw = 0.15625                 # tel merkezi x (zikzak bolgesi 0.150-0.1625 ortasi)
r_gercek = 0.143e-3          # 29 gauge Kanthal, d = 0.286 mm
# Esdeger tel (2D): ust yuzdeki tel uzunlugu / genislik = 0.57215 m / 0.406 m / 2 = 0.70462.
# r = 0.70462 r_gercek -> birim genislik basina yuzey alani gercege esit;
# yogunluk x1.41921 (constant/tel/physicalProperties) -> isi kapasitesi esit; guc 225 W/m esit.
k_esd = 0.70462
r = k_esd * r_gercek
gom = 0.10 * r               # gomulme derinligi
yc = r - gom                 # tel merkezi y
c = math.sqrt(r * r - yc * yc)   # temas kirisi yari genisligi
h = 0.16e-3                  # SIBAL yarim kalinlik (0.32 mm / 2)
b = 0.6e-3                   # tel kutusu yari genislik
bt = 0.75e-3                 # tel kutusu ust siniri (alt satir yuksekligi)
X2, X3 = xw - b, xw + b
zlo, zhi = -0.005, 0.005

thC = math.degrees(math.asin(-yc / r))          # -64.16
ang = {"TR": 45.0, "TL": 135.0, "BL": 180.0 - thC, "BR": 360.0 + thC}
# BL = 244.16, BR = 295.84

# ---------------- Hucre sayilari ----------------
Nt = 5        # tel ust yay = alt (kirisi) yay = cekirdek x
Nl = 7        # tel sol/sag yay = alt satir y sayisi
Nrs = 14      # kutu radyal (yan ve ust); hucre basina buyume <= 1.2 icin
Nwr = 4       # tel ici halka radyal
nf = 4        # SIBAL kalinlik
first_ring = 0.026e-3   # tel cevresi yay boyu ~0.013 mm ile uyumlu    # tele bitisik radyal hucre (hedef)
er = 1.15                # buyume orani


def geo_count(L, d0, ratio):
    """d0'dan ratio ile buyuyen hucrelerle L'yi dolduran n ve son/ilk orani."""
    n = max(1, round(math.log(1 + L * (ratio - 1) / d0) / math.log(ratio)))
    # n sabitken ilk hucre d0 kalsin diye orani yeniden coz
    lo, hi = 1.0 + 1e-9, 3.0
    for _ in range(200):
        m = 0.5 * (lo + hi)
        s = d0 * (m ** n - 1) / (m - 1)
        lo, hi = (m, hi) if s < L else (lo, m)
    q = 0.5 * (lo + hi)
    return n, q ** (n - 1), q


# kutu radyal: yan (kutu kenari -> tel) uzunlugu ~ b - c, ust ~ bt - (yc + r)
Ls = b - c
Lt = bt - (yc + r)
# radyal hucreler: tele bitisik first_ring; Nrs sabit, oran coz
def ratio_for(L, n, d0):
    lo, hi = 1.0 + 1e-9, 3.0
    for _ in range(200):
        m = 0.5 * (lo + hi)
        s = d0 * (m ** n - 1) / (m - 1)
        lo, hi = (m, hi) if s < L else (lo, m)
    q = 0.5 * (lo + hi)
    return q ** (n - 1)      # son/ilk


g_side = ratio_for(Ls, Nrs, first_ring)   # tel->kutu yonunde buyume (son/ilk)
g_top = g_side   # yan ve ust halka capraz kenari paylasir: oran ayni olmali
d_box_side = first_ring * g_side          # kutu kenarindaki radyal hucre
# Kutu kenarindan uzaga (x) devam: ilk hucre d_box_side, er ile buyu
nxB, gB, _ = geo_count(X2 - X1, d_box_side, er)        # X2'den geriye
d_X1 = d_box_side * gB
# A blogu: X1'den geriye, d_X1 ile basla, 7.5 mm'ye kadar buyu, sonra sabit
dA_max = 7.5e-3
kA = max(1, round(math.log(dA_max / d_X1) / math.log(er)))
LA1 = d_X1 * (er ** kA - 1) / (er - 1)
nA2 = max(1, round((X1 - X0 - LA1) / dA_max))
# C blogu: X3'ten ileri, d_box_side'dan 5.875 mm'ye buyu, sonra sabit
dC_max = (X4 - X1) / 160
kC = max(1, round(math.log(dC_max / d_box_side) / math.log(er)))
LC1 = d_box_side * (er ** kC - 1) / (er - 1)
nC2 = max(1, round((X4 - X3 - LC1) / dC_max))
nD = 36
# y: alt satir Nl uniform (bt), ust satir bt..H, ilk hucre bt/Nl
dy0 = bt / Nl
dyU_max = 16e-3          # ust satir hucre tavani (en-boy orani <~150, tel sutununda dx ~0.11 mm)
kU = max(1, round(math.log(dyU_max / dy0) / math.log(er)))
LU1 = dy0 * (er ** kU - 1) / (er - 1)
nU2 = max(1, round((H - bt - LU1) / dyU_max))
nyU = kU + nU2

# ---------------- Noktalar ----------------
pts = []
idx = {}


def P(name, x, y):
    idx[name] = len(pts)
    pts.append((x, y))


def onC(a, rr=r):
    t = math.radians(a)
    return xw + rr * math.cos(t), yc + rr * math.sin(t)


for k, a in ang.items():
    P("W" + k, *onC(a))
    P("K" + k, *onC(a, 0.5 * r))
# W_BL, W_BR y=0 uzerinde olmali (temas noktalari)
for k in ("BL", "BR"):
    pts[idx["W" + k]] = (pts[idx["W" + k]][0], 0.0)
P("BBL", X2, 0.0); P("BBR", X3, 0.0); P("BTL", X2, bt); P("BTR", X3, bt)
P("QL", xw - c, -h); P("QR", xw + c, -h); P("FBL", X2, -h); P("FBR", X3, -h)
for nm, x in (("0", X0), ("1", X1), ("4", X4), ("5", X5)):
    P("G%s_0" % nm, x, 0.0); P("G%s_t" % nm, x, bt); P("G%s_H" % nm, x, H)
P("G2_H", X2, H); P("G3_H", X3, H)
P("F1", X1, -h); P("F4", X4, -h)

N = len(pts)


def V(n, z=0):
    return idx[n] + (N if z else 0)


# ---------------- Bloklar ----------------
blocks = []   # (zone, [v0..v3 names], (nx, ny), grading_str)


def area(names):
    q = [pts[idx[n]] for n in names]
    s = 0.0
    for i in range(4):
        x1, y1 = q[i]; x2, y2 = q[(i + 1) % 4]
        s += x1 * y2 - x2 * y1
    return 0.5 * s


def B(zone, names, n, grad):
    if area(names) <= 0:
        raise SystemExit(f"Blok yonelimi ters/dejenere: {zone} {names} alan={area(names)}")
    blocks.append((zone, names, n, grad))


ml = lambda segs: "(" + " ".join(f"({a:.10g} {b_:.10g} {g:.10g})" for a, b_, g in segs) + ")"

# x yonu derecelendirmeleri
LA = X1 - X0
gradA = ml([((LA - LA1) / LA, nA2 / (nA2 + kA), 1.0), (LA1 / LA, kA / (nA2 + kA), 1 / (er ** (kA - 1)))])
gradB = f"{1/gB:.10g}"                               # X1 -> X2 kuculur
LC = X4 - X3
gradC = ml([(LC1 / LC, kC / (kC + nC2), er ** (kC - 1)), ((LC - LC1) / LC, nC2 / (kC + nC2), 1.0)])
nxA, nxC = nA2 + kA, kC + nC2
LUt = H - bt
gU = ml([(LU1 / LUt, kU / nyU, er ** (kU - 1)), ((LUt - LU1) / LUt, nU2 / nyU, 1.0)])


def sg(gx, gy):
    return f"simpleGrading ({gx} {gy} 1)"


# A
B("fluid", ["G0_0", "G1_0", "G1_t", "G0_t"], (nxA, Nl), sg(gradA, 1))
B("fluid", ["G0_t", "G1_t", "G1_H", "G0_H"], (nxA, nyU), sg(gradA, gU))
# B
B("fluid", ["G1_0", "BBL", "BTL", "G1_t"], (nxB, Nl), sg(gradB, 1))
B("fluid", ["G1_t", "BTL", "G2_H", "G1_H"], (nxB, nyU), sg(gradB, gU))
# W (kutu ustu)
B("fluid", ["BTL", "BTR", "G3_H", "G2_H"], (Nt, nyU), sg(1, gU))
# C
B("fluid", ["BBR", "G4_0", "G4_t", "BTR"], (nxC, Nl), sg(gradC, 1))
B("fluid", ["BTR", "G4_t", "G4_H", "G3_H"], (nxC, nyU), sg(gradC, gU))
# D
B("fluid", ["G4_0", "G5_0", "G5_t", "G4_t"], (nD, Nl), sg(1, 1))
B("fluid", ["G4_t", "G5_t", "G5_H", "G4_H"], (nD, nyU), sg(1, gU))
# Kutu halkalari (fluid)
B("fluid", ["BBL", "WBL", "WTL", "BTL"], (Nrs, Nl), sg(f"{1/g_side:.10g}", 1))   # sol: kutu->tel kuculur
B("fluid", ["WBR", "BBR", "BTR", "WTR"], (Nrs, Nl), sg(f"{g_side:.10g}", 1))     # sag: tel->kutu buyur
B("fluid", ["WTL", "WTR", "BTR", "BTL"], (Nt, Nrs), sg(1, f"{g_top:.10g}"))      # ust: tel->kutu buyur
# Tel
B("tel", ["KBL", "KBR", "KTR", "KTL"], (Nt, Nl), sg(1, 1))
B("tel", ["KTL", "KTR", "WTR", "WTL"], (Nt, Nwr), sg(1, 1))
B("tel", ["WBL", "KBL", "KTL", "WTL"], (Nwr, Nl), sg(1, 1))
B("tel", ["KBR", "WBR", "WTR", "KTR"], (Nwr, Nl), sg(1, 1))
B("tel", ["WBL", "WBR", "KBR", "KBL"], (Nt, Nwr), sg(1, 1))
# SIBAL
B("sibal", ["F1", "FBL", "BBL", "G1_0"], (nxB, nf), sg(gradB, 1))
B("sibal", ["FBL", "QL", "WBL", "BBL"], (Nrs, nf), sg(f"{1/g_side:.10g}", 1))
B("sibal", ["QL", "QR", "WBR", "WBL"], (Nt, nf), sg(1, 1))
B("sibal", ["QR", "FBR", "BBR", "WBR"], (Nrs, nf), sg(f"{g_side:.10g}", 1))
B("sibal", ["FBR", "F4", "G4_0", "BBR"], (nxC, nf), sg(gradC, 1))

# ---------------- Paylasilan kenar kontrolu ----------------
edges = {}
for zone, nm, (nx, ny), g in blocks:
    e = [(nm[0], nm[1], nx), (nm[3], nm[2], nx), (nm[0], nm[3], ny), (nm[1], nm[2], ny)]
    for a, b_, n in e:
        key = tuple(sorted((a, b_)))
        if key in edges and edges[key] != n:
            raise SystemExit(f"Kenar hucre sayisi tutarsiz: {key} {edges[key]} vs {n}")
        edges[key] = n

# ---------------- Yaylar ----------------
def mid(a1, a2):
    return onC(0.5 * (a1 + a2))


arcs = [("WTR", "WTL", mid(45, 135)), ("WTL", "WBL", mid(135, ang["BL"])),
        ("WBL", "WBR", mid(ang["BL"], ang["BR"])), ("WBR", "WTR", mid(ang["BR"], 405))]

# ---------------- Yaz ----------------
L = ["FoamFile { format ascii; class dictionary; object blockMeshDict; }",
     "// mesh_olustur.py tarafindan uretildi - elle duzenleme yapmayin",
     f"// tel: xw={xw} r={r} yc={yc:.6e} temas genisligi={2*c:.6e} m; SIBAL yarim kalinlik {h}",
     "convertToMeters 1;", "vertices", "("]
for z in (zlo, zhi):
    for i, (x, y) in enumerate(pts):
        L.append(f"    ({x:.12g} {y:.12g} {z})  // {i + (N if z == zhi else 0)}")
L += [");", "blocks", "("]
for zone, nm, (nx, ny), g in blocks:
    v = [V(n) for n in nm] + [V(n, 1) for n in nm]
    L.append(f"    hex ({' '.join(map(str, v))}) {zone} ({nx} {ny} 1) {g}")
L += [");", "edges", "("]
for a, b_, (mx, my) in arcs:
    for zz, z in ((0, zlo), (1, zhi)):
        L.append(f"    arc {V(a, zz)} {V(b_, zz)} ({mx:.12g} {my:.12g} {z})")
L += [");"]


def F(a, b_):
    return f"({V(a)} {V(b_)} {V(b_, 1)} {V(a, 1)})"


L += ["boundary", "(",
      f"    inlet   {{ type patch; faces ( {F('G0_0','G0_t')} {F('G0_t','G0_H')} ); }}",
      f"    outlet  {{ type patch; faces ( {F('G5_0','G5_t')} {F('G5_t','G5_H')} ); }}",
      f"    top     {{ type wall; faces ( {F('G0_H','G1_H')} {F('G1_H','G2_H')} {F('G2_H','G3_H')} {F('G3_H','G4_H')} {F('G4_H','G5_H')} ); }}",
      f"    base    {{ type wall; faces ( {F('G0_0','G1_0')} {F('G4_0','G5_0')} ); }}",
      f"    sibalAlt {{ type symmetryPlane; faces ( {F('F1','FBL')} {F('FBL','QL')} {F('QL','QR')} {F('QR','FBR')} {F('FBR','F4')} ); }}",
      f"    sibalUc {{ type wall; faces ( {F('F1','G1_0')} {F('F4','G4_0')} ); }}",
      ");",
      "defaultPatch { name frontAndBack; type empty; }"]

Path("system/blockMeshDict").write_text("\n".join(L) + "\n")
print(f"bloklar {len(blocks)}, noktalar {N}x2")
print(f"x: A {nxA} B {nxB} W {Nt} C {nxC} D {nD}; y: alt {Nl} ust {nyU}; tel cevre {2*Nt+2*Nl}")
print(f"temas genisligi {2*c*1e3:.4f} mm, yc {yc*1e3:.4f} mm, kutu radyal son/ilk yan {g_side:.3f} ust {g_top:.3f}")
print(f"d_box_side {d_box_side*1e3:.4f} mm, d_X1 {d_X1*1e3:.3f} mm, dy0 {dy0*1e3:.4f} mm")
