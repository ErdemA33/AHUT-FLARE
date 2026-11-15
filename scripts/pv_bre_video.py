"""
pv_bre_video.py — ISS BRE gaz doğrulama vakalarından (of_gaz_bre.py) yan yana sıcaklık videosu.
Sol: deneyde kendiliğinden sönen test, sağ: deneyde yanan test. 2B eksenel simetrik kama, eksene göre aynalanır.

    pvpython --force-offscreen-rendering scripts/pv_bre_video.py <sol_vaka_klasörü> <sağ_vaka_klasörü> <çıktı.mp4>

Her vaka klasöründe parçalanmış koşu (processor*), BILGI.json; <vaka>.foam yoksa oluşturulur.
Yazılar PIL ile, video ffmpeg (H.264, yuv420p). Ara kareler çıktının yanında <ad>_kareler/ altında, iş bitince silinir.
"""
import json
import os
import shutil
import subprocess
import sys

from paraview.simple import *
from PIL import Image, ImageDraw, ImageFont

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOL, SAG, CIKTI = sys.argv[1:4]
W, H = 640, 760            # tek panel (piksel)
T_MIN, T_MAX = 300.0, 2300.0
FPS = 4
YAZI = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
YAZI_K = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def oku(vaka):
    ad = os.path.basename(os.path.normpath(vaka))
    foam = os.path.join(vaka, ad + ".foam")
    open(foam, "a").close()
    r = OpenFOAMReader(registrationName=ad, FileName=foam)
    r.CaseType = "Decomposed Case"
    r.MeshRegions = ["internalMesh"]
    r.CellArrays = ["T"]
    r.UpdatePipelineInformation()
    zam = list(r.TimestepValues)
    m = MergeBlocks(Input=r)
    m = CellDatatoPointData(Input=m)
    ayna = Reflect(Input=m)
    ayna.Plane = "X Min"     # eksen x = 0
    ayna.CopyInput = 1
    b = json.load(open(os.path.join(vaka, "BILGI.json")))
    adaylar = [os.path.join(vaka, "sonuc.json"), os.path.join(KOK, f"of_kosular/gaz_bre/auc40/{ad}/sonuc.json"),
               os.path.join(KOK, f"of_kosular/gaz_bre/{ad}/sonuc.json")]
    sf = next((x for x in adaylar if os.path.exists(x)), None)
    b["model_t_sonme"] = json.load(open(sf)).get("t_sonme_s") if sf else None
    return b.get("test", ad), ayna, zam, b


def panel_kareleri(vaka, klasor):
    ad, kaynak, zam, b = oku(vaka)
    v = CreateView("RenderView")
    v.ViewSize = [W, H]
    v.OrientationAxesVisibility = 0
    v.Background = [0.0, 0.0, 0.0]
    try:
        v.UseColorPaletteForBackground = 0
    except AttributeError:
        pass
    d = Show(kaynak, v)
    ColorBy(d, ("POINTS", "T"))
    lut = GetColorTransferFunction("T")
    lut.ApplyPreset("Black-Body Radiation", True)
    lut.RescaleTransferFunction(T_MIN, T_MAX)
    lut.AutomaticRescaleRangeMode = "Never"
    d.SetScalarBarVisibility(v, False)
    # görüş: r -55..55 mm, y 0..130 mm
    v.CameraPosition = [0.0, 0.072, 1.0]
    v.CameraFocalPoint = [0.0, 0.072, 0.0]
    v.CameraViewUp = [0.0, 1.0, 0.0]
    v.CameraParallelProjection = 1
    v.CameraParallelScale = 0.074
    kareler = {}
    for t in zam:
        v.ViewTime = t
        f = os.path.join(klasor, f"{ad}_{t:07.2f}.png")
        SaveScreenshot(f, v, ImageResolution=[W, H])
        kareler[round(t, 3)] = f
    Delete(v)
    return ad, kareler, b


def renk(val):
    p = list(GetColorTransferFunction("T").RGBPoints)
    xs = p[0::4]
    for i in range(len(xs) - 1):
        if xs[i] <= val <= xs[i + 1]:
            a = (val - xs[i]) / max(xs[i + 1] - xs[i], 1e-12)
            return [p[4 * i + 1 + c] * (1 - a) + p[4 * (i + 1) + 1 + c] * a for c in range(3)]
    return p[1:4] if val < xs[0] else p[-3:]


def main():
    klasor = os.path.splitext(CIKTI)[0] + "_kareler"
    os.makedirs(klasor, exist_ok=True)
    sol = panel_kareleri(SOL, klasor)
    sag = panel_kareleri(SAG, klasor)
    f_b = ImageFont.truetype(YAZI_K, 26)
    f_n = ImageFont.truetype(YAZI, 20)
    f_k = ImageFont.truetype(YAZI, 16)
    t_son = max(max(sol[1]), max(sag[1]))
    zamanlar = sorted(set(sol[1]) | set(sag[1]))
    UST, ALT = 120, 110
    for i, t in enumerate(zamanlar):
        img = Image.new("RGB", (2 * W + 20, H + UST + ALT), (12, 12, 16))
        dr = ImageDraw.Draw(img)
        for j, (ad, kar, b) in enumerate((sol, sag)):
            x0 = j * (W + 20)
            onceki = [k for k in kar if k <= t]
            f = kar[max(onceki)] if onceki else kar[min(kar)]
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
        dr.text((W - 40, H + UST + 14), f"t = {t:4.0f} s", font=f_b, fill=(255, 255, 255))
        # renk çubuğu
        cx, cy, cw = 2 * W + 20 - 420, H + UST + 64, 380
        for k in range(cw):
            val = T_MIN + (T_MAX - T_MIN) * k / (cw - 1)
            c = renk(val)
            dr.line([(cx + k, cy), (cx + k, cy + 18)], fill=tuple(int(255 * q) for q in c))
        dr.text((cx, cy - 24), "Sıcaklık (K)", font=f_k, fill=(220, 220, 220))
        dr.text((cx - 4, cy + 22), f"{T_MIN:.0f}", font=f_k, fill=(220, 220, 220))
        dr.text((cx + cw - 40, cy + 22), f"{T_MAX:.0f}", font=f_k, fill=(220, 220, 220))
        dr.text((16, H + UST + 64), "OpenFOAM 14 · tek adım etilen · P1 ışınım · g = 0", font=f_k, fill=(170, 170, 180))
        dr.text((16, H + UST + 86), "AHUT FLARE — ISS BRE doğrulaması (Dehghani ve ark. 2021)", font=f_k, fill=(170, 170, 180))
        img.save(os.path.join(klasor, f"kare_{i:04d}.png"))
        if abs(t - 5.0) < 1e-6:
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
