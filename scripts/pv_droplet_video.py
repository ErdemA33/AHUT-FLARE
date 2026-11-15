"""
pv_damla_video.py — NASA FLEX damla doğrulama vakalarından (of_kosular/damla_cpp, C++ buharlaşma modeli)
yan yana sıcaklık videosu: z = 0 kesiti, damla merkezde. Sol: deneyde sönen, sağ: deneyde yanan test.

    pvpython --force-offscreen-rendering scripts/pv_droplet_video.py <sol_vaka> <sağ_vaka> <çıktı.mp4> [bitis_s]
"""
import json
import os
import shutil
import subprocess
import sys

from paraview.simple import *
from PIL import Image, ImageDraw, ImageFont

SOL, SAG, CIKTI = sys.argv[1:4]
BITIS = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0
W, H = 640, 640
T_MIN, T_MAX = 300.0, 2800.0
FPS = 8
YAZI = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
YAZI_K = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def panel(vaka, klasor, j):
    ad = os.path.basename(os.path.normpath(vaka))
    foam = os.path.join(vaka, ad + ".foam")
    open(foam, "a").close()
    r = OpenFOAMReader(registrationName=ad, FileName=foam)
    r.CaseType = "Reconstructed Case"
    r.MeshRegions = ["internalMesh"]
    r.CellArrays = ["T"]
    r.UpdatePipelineInformation()
    zam = [t for t in r.TimestepValues if t <= BITIS + 1e-9]
    m = CellDatatoPointData(Input=MergeBlocks(Input=r))
    k = Slice(Input=m)
    k.SliceType = "Plane"
    k.SliceType.Origin = [0, 0, 0]
    k.SliceType.Normal = [0, 0, 1]
    v = CreateView("RenderView")
    v.ViewSize = [W, H]
    v.OrientationAxesVisibility = 0
    try:
        v.UseColorPaletteForBackground = 0
    except AttributeError:
        pass
    v.Background = [0, 0, 0]
    d = Show(k, v)
    ColorBy(d, ("POINTS", "T"))
    lut = GetColorTransferFunction("T")
    lut.ApplyPreset("Black-Body Radiation", True)
    lut.RescaleTransferFunction(T_MIN, T_MAX)
    lut.AutomaticRescaleRangeMode = "Never"
    d.SetScalarBarVisibility(v, False)
    bx = r.GetDataInformation().GetBounds()
    yari = 0.5 * (bx[1] - bx[0])
    v.CameraPosition = [0, 0, 10 * yari]
    v.CameraFocalPoint = [0, 0, 0]
    v.CameraViewUp = [0, 1, 0]
    v.CameraParallelProjection = 1
    v.CameraParallelScale = yari / 4.0            # merkez ±%25
    kar = {}
    for t in zam:
        v.ViewTime = t
        f = os.path.join(klasor, f"p{j}_{t:08.4f}.png")
        SaveScreenshot(f, v, ImageResolution=[W, H])
        kar[round(t, 4)] = f
    b = json.load(open(os.path.join(vaka, "BILGI.json")))
    s = json.load(open(os.path.join(vaka, "sonuc.json"))) if os.path.exists(os.path.join(vaka, "sonuc.json")) else {}
    olcek_mm = 1000 * yari / 4.0 if yari < 1 else yari / 4.0
    return b, s, kar, olcek_mm


def main():
    klasor = os.path.splitext(CIKTI)[0] + "_kareler"
    os.makedirs(klasor, exist_ok=True)
    p = [panel(SOL, klasor, 0), panel(SAG, klasor, 1)]
    f_b = ImageFont.truetype(YAZI_K, 26)
    f_n = ImageFont.truetype(YAZI, 19)
    f_k = ImageFont.truetype(YAZI, 16)
    zam = sorted(set(p[0][2]) | set(p[1][2]))
    UST, ALT = 130, 96
    for i, t in enumerate(zam):
        img = Image.new("RGB", (2 * W + 20, H + UST + ALT), (12, 12, 16))
        dr = ImageDraw.Draw(img)
        for j, (b, s, kar, olcek) in enumerate(p):
            x0 = j * (W + 20)
            once = [z for z in kar if z <= t]
            img.paste(Image.open(kar[max(once)] if once else kar[min(kar)]).convert("RGB"), (x0, UST))
            deney = "söndü" if b["flex_yanar"] == 0 else "yandı"
            dr.text((x0 + 16, 12), f"FLEX test {b['test']}", font=f_b, fill=(255, 255, 255))
            dr.text((x0 + 16, 48), f"n-heptan d0 {b['d0_mm']:g} mm   O₂ %{b['o2']:g}   {b['basinc_kpa']:g} kPa", font=f_k, fill=(200, 200, 210))
            dr.text((x0 + 16, 74), f"ISS deneyi: {deney}", font=f_n, fill=(120, 200, 255) if b["flex_yanar"] == 0 else (255, 170, 80))
            if s.get("skor_T_K"):
                dr.text((x0 + 16, 100), f"Model skoru {s['skor_T_K']:.0f} K  (sıralama: sönenler < 2000 K < yananlar)",
                        font=f_k, fill=(200, 200, 210))
            # ölçek çubuğu: panel genişliği = 2 x olcek mm
            px_mm = W / (2 * olcek)
            L = 5.0
            dr.line([(x0 + 20, UST + H - 24), (x0 + 20 + L * px_mm, UST + H - 24)], fill=(230, 230, 230), width=3)
            dr.text((x0 + 20, UST + H - 48), f"{L:g} mm", font=f_k, fill=(230, 230, 230))
        dr.text((W - 50, H + UST + 10), f"t = {t:4.2f} s", font=f_b, fill=(255, 255, 255))
        dr.text((16, H + UST + 50), "Sıcaklık 300–2800 K (siyah → beyaz) · z = 0 kesiti, damla merkezde · g = 0", font=f_k, fill=(200, 200, 210))
        dr.text((16, H + UST + 72), "OpenFOAM 14 + C++ damla buharlaşma modeli (damlaBulutBuharlasma), tek adım heptan, ışınımsız",
                font=f_k, fill=(170, 170, 180))
        img.save(os.path.join(klasor, f"kare_{i:04d}.png"))
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", f"{klasor}/kare_%04d.png",
                        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264", "-pix_fmt", "yuv420p", CIKTI],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("ffmpeg başarısız: " + r.stderr[-600:])
    if not os.environ.get("PV_VIDEO_TUT"):
        shutil.rmtree(klasor)
    print("->", CIKTI)


main()
