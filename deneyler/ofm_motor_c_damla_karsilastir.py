# OpenFOAM motor_c: C++ damlaBirimTest ile Python damla_motoru.py ilkellerini (pDoyma, LBuhar, Yfs, mpp) karşılaştırır.
# Kullanım: python3 -I bu_betik.py <damlaBirimTest ikilisi> <damlaYakitlar sözlüğü>
import sys, json, subprocess, importlib.util, math, itertools
sys.dont_write_bytecode = True
sp = importlib.util.spec_from_file_location("dm", "/home/user/Desktop/damla_cpp_paketi/referans/damla_motoru.py")
dm = importlib.util.module_from_spec(sp); sp.loader.exec_module(dm)
yakitlar = ["NC7H16", "CH3OH", "C2H5OH", "NC10H22", "NC3H7OH"]
satir = []
Ts = [250, 280, 300, 330, 360, 400, 450]; ps = [20e3, 50e3, 101325, 200e3]
for yk in yakitlar:
    for T, p in itertools.product(Ts, ps):
        satir.append((yk, T, p, 28.5, 0.01, 0.0))
inp = "\n".join(" ".join(map(str, s)) for s in satir) + "\n"
out = subprocess.run([sys.argv[1], sys.argv[2]], input=inp, capture_output=True, text=True).stdout.splitlines()
out = [l for l in out if not l.startswith(("RR", "Pstd"))]
print("C++ satır", len(out))
worst = {k: 0.0 for k in ("pDoyma", "LBuhar", "Yfs", "mpp")}; ayrisan = []
for s, l in zip(satir, out):
    yk, T, p, Md, a, Y1 = s
    y = dm.YAKIT[yk]
    Tl = min(max(T, 200.0), y["Tc"] - 1.0)
    ps_ = float(dm.p_doyma(Tl, y)); L = float(dm.L_buhar(Tl, y))
    X = min(ps_ / p, 0.98); Ys = X * y["M"] / (X * y["M"] + (1 - X) * Md)
    m = max(a * (Ys - Y1) / max(1 - Ys, 1e-6), 0.0)
    c = list(map(float, l.split()[3:7]))
    for k, py, cc in zip(worst, (ps_, L, Ys, m), c):
        r = abs(py - cc) / max(abs(py), 1e-300) if py != 0 else abs(cc)
        worst[k] = max(worst[k], r)
        if r > 1e-9: ayrisan.append((yk, T, p, k, py, cc))
print("en büyük bağıl fark:", worst); print("1e-9 üstü:", len(ayrisan), ayrisan[:3])
