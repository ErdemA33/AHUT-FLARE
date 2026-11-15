"""
pv_bre_3b.py — ISS BRE gaz vakalarının (of_gaz_bre.py) 3B görünümü: 2B eksenel simetrik kesit eksen (y) etrafında
360° döndürülür; 1100 K (sarı, yarı saydam) ve 1500 K (kırmızı) eş-sıcaklık yüzeyleri, brülör diski; kamera döner.
Gösterim amaçlı: alan eksenel simetrik varsayımıyla tam 3B'ye açılır (yeni benzetim yok).

    pvpython --force-offscreen-rendering scripts/pv_bre_3b.py <sol_vaka> <sağ_vaka> <çıktı.mp4>
"""
import json
import math
import os
import shutil
import subprocess
import sys

from paraview.simple import *
from PIL import Image, ImageDraw, ImageFont

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOL, SAG, CIKTI = sys.argv[1:4]
W, H = 640, 640
FPS = 6
ARA = 3                       # iki kayıt arasına konan kamera adımı (alan aynı kalır, kamera döner)
YAZI = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
YAZI_K = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def kur(vaka, v):
    ad = os.path.basename(os.path.normpath(vaka))
    foam = os.path.join(vaka, ad + ".foam")
    open(foam, "a").close()
    r = OpenFOAMReader(registrationName=ad, FileName=foam)
    r.CaseType = "Decomposed Case"
    r.MeshRegions = ["internalMesh"]
    r.CellArrays = ["T"]
    r.UpdatePipelineInformation()
    zam = list(r.TimestepValues)
    m = CellDatatoPointData(Input=MergeBlocks(Input=r))
    kes = Slice(Input=m)
    kes.SliceType = "Plane"
    kes.SliceType.Origin = [0, 0, 0]
    kes.SliceType.Normal = [0, 0, 1]
    don = Transform(Input=kes)
    don.Transform.Rotate = [90, 0, 0]          # y (eksen) -> z
    yuz = []
    for T, renk, op in ((1100.0, [1.0, 0.8, 0.15], 0.28), (1500.0, [1.0, 0.25, 0.05], 0.85)):
        c = Contour(Input=don)
        c.ContourBy = ["POINTS", "T"]
        c.Isosurfaces = [T]
        e = RotationalExtrusion(Input=c)
        e.Resolution = 90
        e.Angle = 360.0
        d = Show(e, v)
        d.ColorArrayName = ["POINTS", ""]
        d.AmbientColor = d.DiffuseColor = renk
        d.Opacity = op
        d.Specular = 0.3
        yuz.append(e)
    disk = Disk(InnerRadius=0.0, OuterRadius=0.0125, CircumferentialResolution=64)
    dd = Show(disk, v)
    dd.ColorArrayName = ["POINTS", ""]
    dd.DiffuseColor = [0.55, 0.55, 0.6]
    taban = Disk(InnerRadius=0.0125, OuterRadius=0.03, CircumferentialResolution=64)
    dt = Show(taban, v)
    dt.ColorArrayName = ["POINTS", ""]
    dt.DiffuseColor = [0.25, 0.25, 0.28]
    b = json.load(open(os.path.join(vaka, "BILGI.json")))
    sf = os.path.join(KOK, f"of_kosular/gaz_bre/auc40/{ad}/sonuc.json")
    b["model_t_sonme"] = json.load(open(sf)).get("t_sonme_s") if os.path.exists(sf) else None
    return ad, zam, b


def gorunum():
    v = CreateView("RenderView")
    v.ViewSize = [W, H]
    v.OrientationAxesVisibility = 0
    try:
        v.UseColorPaletteForBackground = 0
    except AttributeError:
        pass
    v.Background = [0.02, 0.02, 0.04]
    v.CameraViewUp = [0, 0, 1]
    v.CameraFocalPoint = [0, 0, 0.03]
    return v


def kamera(v, aci):
    R, Z = 0.2, 0.13
    v.CameraPosition = [R * math.cos(aci), R * math.sin(aci), Z]
    v.CameraFocalPoint = [0, 0, 0.03]
    v.CameraViewUp = [0, 0, 1]
    v.CameraViewAngle = 30


def main():
    klasor = os.path.splitext(CIKTI)[0] + "_kareler"
    os.makedirs(klasor, exist_ok=True)
    paneller = []
    for vaka in (SOL, SAG):
        v = gorunum()
        ad, zam, b = kur(vaka, v)
        paneller.append((v, ad, zam, b))
    t_hepsi = sorted(set(paneller[0][2]) | set(paneller[1][2]))
    adim = [(t, k) for t in t_hepsi for k in range(ARA)]
    f_b = ImageFont.truetype(YAZI_K, 26)
    f_n = ImageFont.truetype(YAZI, 20)
    f_k = ImageFont.truetype(YAZI, 16)
    UST, ALT = 120, 90
    for i, (t, k) in enumerate(adim):
        aci = 2 * math.pi * i / len(adim) * 1.5
        img = Image.new("RGB", (2 * W + 20, H + UST + ALT), (12, 12, 16))
        dr = ImageDraw.Draw(img)
        for j, (v, ad, zam, b) in enumerate(paneller):
            tv = max([z for z in zam if z <= t] or [zam[0]])
            v.ViewTime = tv
            kamera(v, aci)
            f = os.path.join(klasor, f"p{j}.png")
            SaveScreenshot(f, v, ImageResolution=[W, H])
            x0 = j * (W + 20)
            img.paste(Image.open(f).convert("RGB"), (x0, UST))
            deney = "söndü" if b["yanar"] == 0 else "yandı"
            tb = f" ({b['t_b_s']:.0f} s'de)" if b["yanar"] == 0 and b.get("t_b_s") else ""
            dr.text((x0 + 16, 14), f"Test {ad}", font=f_b, fill=(255, 255, 255))
            dr.text((x0 + 16, 50), f"O₂ %{100 * b['x_o2']:.0f}   p {b['p_bar']:.2f} bar   yakıt {b['m_akisi_g_m2s']:.2f} g/m²s",
                    font=f_k, fill=(200, 200, 210))
            dr.text((x0 + 16, 80), f"ISS deneyi: {deney}{tb}", font=f_n,
                    fill=(120, 200, 255) if b["yanar"] == 0 else (255, 170, 80))
            ts = b.get("model_t_sonme")
            if ts is not None and t >= ts:
                m_yazi, m_renk = f"Model: söndü ({ts:.1f} s'de)", (120, 200, 255)
            else:
                m_yazi, m_renk = "Model: alev yanıyor", (255, 170, 80)
            dr.text((x0 + 16, UST + 12), m_yazi, font=f_n, fill=m_renk)
        dr.text((W - 40, H + UST + 12), f"t = {t:4.0f} s", font=f_b, fill=(255, 255, 255))
        dr.text((16, H + UST + 50), "Eş-sıcaklık yüzeyleri: sarı 1100 K, kırmızı 1500 K · gri disk: 25 mm brülör",
                font=f_k, fill=(200, 200, 210))
        dr.text((2 * W + 20 - 560, H + UST + 50), "OpenFOAM 14 · eksenel simetrik çözüm 3B'ye açıldı · g = 0",
                font=f_k, fill=(170, 170, 180))
        img.save(os.path.join(klasor, f"kare_{i:04d}.png"))
        if abs(t - 5.0) < 1e-6 and k == 0:
            img.save(os.path.splitext(CIKTI)[0] + "_t5.png")
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", f"{klasor}/kare_%04d.png",
                        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264", "-pix_fmt", "yuv420p", CIKTI],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("ffmpeg başarısız: " + r.stderr[-600:])
    if not os.environ.get("PV_VIDEO_TUT"):
        shutil.rmtree(klasor)
    print("->", CIKTI)


main()
