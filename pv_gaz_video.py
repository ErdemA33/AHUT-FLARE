"""
pv_gaz_video.py — metan sızıntısı (of_gaz.py) videoları; pv_video.py / pv_3b_video.py mantığıyla.
GÖSTERİM — deney verisiyle doğrulanmadı (her karede yazılı).

    pvpython --force-offscreen-rendering pv_gaz_video.py            # üçü de (her biri ayrı ParaView oturumunda)
    pvpython --force-offscreen-rendering pv_gaz_video.py kesit      # of_gorsel/gaz_uzay_mars(_en).mp4
    pvpython --force-offscreen-rendering pv_gaz_video.py 3b         # of_gorsel/gaz_3b(_en).mp4
    pvpython --force-offscreen-rendering pv_gaz_video.py 2d4        # of_gorsel/gaz2d_4g(_en).mp4  (2 x 2, etiketler bantta)
    pvpython --force-offscreen-rendering pv_gaz_video.py 3b4        # of_gorsel/gaz_3b_4g(_en).mp4 (3B, 4 yerçekimi, 2 x 2)
    pvpython --force-offscreen-rendering pv_gaz_video.py kesit4     # of_gorsel/gaz_kesit_4g(_en).mp4 (z = 1 mm, 2 x 2)

- kesit: 3B yarım alanın z = 1 mm kesiti (simetri düzleminin ilk hücre katmanı), uzay solda / Mars sağda,
  T (300–2300 K sabit ölçek) + yeşil çizgi: stokiyometrik metan (Y_CH4 = 0,055).
- 3b: z = 0 düzleminde aynalanmış tam kabin, 1200 K sarı yarı saydam + 1800 K kırmızı eş-yüzey, kabin çerçevesi,
  delik (camgöbeği) ve tutuşturucu (yeşil, açıkken); kamera ~90° döner; uzay | Mars.
- 2d4: 2B koşular 2 x 2: g = 0 | Ay 1,62 / Mars 3,73 | Dünya 9,81.
Yazılar PIL ile (TR ve EN), ffmpeg H.264 / yuv420p. Ara kareler iş bitince silinir (PV_VIDEO_TUT=1 ise kalır).
Ortam: GAZ_KOK3 / GAZ_KOK2 (deneme için başka vaka kökü), GAZ_VIDEO_ONEK (çıktı adı öneki).
"""
import math
import os
import shutil
import subprocess
import sys

from paraview.simple import *
from PIL import Image, ImageDraw, ImageFont

KOK = os.path.expanduser('~/nasaspaceapp')
K3 = os.environ.get('GAZ_KOK3', f'{KOK}/of_kosular/gaz3d_ince')
K2 = os.environ.get('GAZ_KOK2', f'{KOK}/of_kosular/gaz2d')
ONEK = os.environ.get('GAZ_VIDEO_ONEK', '')
CIK = f'{KOK}/of_gorsel'
GEN, YUK = 1920, 1080
UST, ALT = 96, 52
GOR_Y = YUK - UST - ALT
FPS = 10
T_ARALIK = (300.0, 2300.0)
Y_ST = 0.055                       # stokiyometrik CH4 kütle kesri (havada)
DELIK = (-0.080, 0.0, 0.0)
ATES = (-0.065, 0.004, 0.0)
ATES_SURE = 0.10
ARKA = (0.075, 0.085, 0.11)
ARKA8 = tuple(int(255 * c) for c in ARKA)
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_K = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
UZAKLIK, YUKSELIS, AZ0, AZ1 = 0.76, 24.0, 40.0, -50.0

METIN = {
    'tr': {'kesit': 'Kabinde metan sızıntısı: Uzay vs Mars (z = 0 kesiti)',
           '3b': 'Kabinde metan sızıntısı: Uzay vs Mars (3B)',
           '2d4': 'Kabinde metan sızıntısı: 4 yerçekimi (2B)',
           '3b4': 'Kabinde metan sızıntısı: 4 yerçekimi (3B)', 'kesit4': 'Kabinde metan sızıntısı: 4 yerçekimi (z = 1 mm kesiti)',
           'g_uzay': 'Uzay  (g = 0)', 'g_ay': 'Ay  (g = 1,62 m/s²)', 'g_mars': 'Mars  (g = 3,73 m/s²)', 'g_dunya': 'Dünya  (g = 9,81 m/s²)',
           'iso1': '900 K (yarı saydam)', 'iso2': '1400 K (yarı saydam)', 'tel': 'yeşil tel: stokiyometrik yüzey',
           'uzay': 'Uzay  (g = 0)', 'mars': 'Mars  (g = 3,73 m/s²)',
           '0': 'g = 0', '1.62': 'Ay  (g = 1,62 m/s²)', '3.73': 'Mars  (g = 3,73 m/s²)', '9.81': 'Dünya  (g = 9,81 m/s²)',
           'yesil': 'yeşil çizgi: stokiyometrik metan', 'sari': 'sarı: 1200 K', 'kirmizi': 'kırmızı: 1800 K',
           'delik': 'camgöbeği: sızıntı deliği', 'tutus': 'tutuşturucu açık',
           'not3': 'OpenFOAM, 2,5 mm ızgara, 3B yarım alan (simetri) — GÖSTERİM, deney verisiyle doğrulanmadı',
           'not34': 'OpenFOAM, 2,5 mm ızgara, 3B yarım alan (z = 0 simetri; görüntü aynalanmış) — GÖSTERİM, deney verisiyle doğrulanmadı',
           'not2': 'OpenFOAM 2B (z\'de tek hücre, 1,25 mm) — GÖSTERİM, deney verisiyle doğrulanmadı', 'ondalik': ','},
    'en': {'kesit': 'Methane leak in a cabin: Space vs Mars (z = 0 section)',
           '3b': 'Methane leak in a cabin: Space vs Mars (3D)',
           '2d4': 'Methane leak in a cabin: four gravity levels (2D)',
           '3b4': 'Methane leak in a cabin: four gravity levels (3D)', 'kesit4': 'Methane leak in a cabin: four gravity levels (z = 1 mm section)',
           'g_uzay': 'Space  (g = 0)', 'g_ay': 'Moon  (g = 1.62 m/s²)', 'g_mars': 'Mars  (g = 3.73 m/s²)', 'g_dunya': 'Earth  (g = 9.81 m/s²)',
           'iso1': '900 K (semi-transparent)', 'iso2': '1400 K (semi-transparent)', 'tel': 'green wire: stoichiometric surface',
           'uzay': 'Space  (g = 0)', 'mars': 'Mars  (g = 3.73 m/s²)',
           '0': 'g = 0', '1.62': 'Moon  (g = 1.62 m/s²)', '3.73': 'Mars  (g = 3.73 m/s²)', '9.81': 'Earth  (g = 9.81 m/s²)',
           'yesil': 'green line: stoichiometric methane', 'sari': 'yellow: 1200 K', 'kirmizi': 'red: 1800 K',
           'delik': 'cyan: leak hole', 'tutus': 'igniter on',
           'not3': 'OpenFOAM, 2.5 mm grid, 3D half domain (symmetry) — DEMONSTRATION, not validated against experimental data',
           'not34': 'OpenFOAM, 2.5 mm grid, 3D half domain (z = 0 symmetry; mirrored view) — DEMONSTRATION, not validated against experimental data',
           'not2': 'OpenFOAM 2D (single cell in z, 1.25 mm) — DEMONSTRATION, not validated against experimental data',
           'ondalik': '.'},
}


def okuyucu(ad, vaka):
    foam = f'{vaka}/{os.path.basename(vaka)}.foam'
    if not os.path.exists(foam):
        open(foam, 'w').close()
    r = OpenFOAMReader(registrationName=ad, FileName=foam)
    r.CaseType = 'Decomposed Case'
    r.MeshRegions = ['internalMesh']
    r.CellArrays = ['T', 'CH4']
    r.UpdatePipelineInformation()
    return r


def olcek():
    lut = GetColorTransferFunction('T')
    lut.ApplyPreset('Inferno (matplotlib)', True)
    lut.AutomaticRescaleRangeMode = 'Never'
    lut.RescaleTransferFunction(*T_ARALIK)
    GetOpacityTransferFunction('T').RescaleTransferFunction(*T_ARALIK)
    return lut


def gorunum(v, merkez=(0.0, 0.0), yari=0.105, paralel=True):
    try:
        v.UseColorPaletteForBackground = 0
    except AttributeError:
        pass
    v.Background = list(ARKA)
    v.OrientationAxesVisibility = 0
    v.CameraParallelProjection = 1 if paralel else 0
    if paralel:
        v.CameraPosition = [merkez[0], merkez[1], 1.0]
        v.CameraFocalPoint = [merkez[0], merkez[1], 0.0]
        v.CameraViewUp = [0, 1, 0]
        v.CameraParallelScale = yari
    GetScalarBar(GetColorTransferFunction('T'), v).Visibility = 0


def isaret(v, merkez, r, renk):
    s = Sphere(Center=list(merkez), Radius=r, ThetaResolution=24, PhiResolution=12)
    d = Show(s, v)
    d.ColorArrayName = ['POINTS', '']
    d.AmbientColor = d.DiffuseColor = renk
    return d


def stok_cizgi(kaynak, v):
    k = Contour(Input=kaynak)
    k.ContourBy = ['POINTS', 'CH4']
    k.Isosurfaces = [Y_ST]
    d = Show(k, v)
    d.ColorArrayName = ['POINTS', '']
    d.AmbientColor = d.DiffuseColor = [0.25, 1.0, 0.35]
    d.LineWidth = 3
    d.Position = [0, 0, 0.01]


def yerlesim(n):
    v1 = GetActiveViewOrCreate('RenderView')
    lay = GetLayout(v1)
    if n == 1:
        return [v1], lay
    lay.SplitHorizontal(0, 0.5)
    if n == 2:
        v2 = CreateView('RenderView')
        AssignViewToLayout(view=v2, layout=lay, hint=2)
        return [v1, v2], lay
    lay.SplitVertical(1, 0.5)
    lay.SplitVertical(2, 0.5)
    vs = [v1]
    for h in (4, 5, 6):
        v = CreateView('RenderView')
        AssignViewToLayout(view=v, layout=lay, hint=h)
        vs.append(v)
    return vs, lay


# ------------------------------------------------------------------ sahneler
def sahne_kesit():
    vs, lay = yerlesim(2)
    for ad, v in zip(('uzay', 'mars'), vs):
        r = okuyucu(ad, f'{K3}/{ad}')
        s = Slice(Input=r)
        s.SliceType = 'Plane'
        s.SliceType.Origin = [0, 0, 0.001]
        s.SliceType.Normal = [0, 0, 1]
        d = Show(s, v)
        ColorBy(d, ('POINTS', 'T'))
        olcek()
        stok_cizgi(s, v)
        isaret(v, (DELIK[0], 0, 0.02), 0.0025, [0.3, 0.9, 1.0])
    GetAnimationScene().UpdateAnimationUsingDataTimeSteps()
    olcek()
    for v in vs:
        Render(v)
    for v in vs:
        gorunum(v, (0.024, 0.0), 0.125)
    return vs, lay, list(GetTimeKeeper().TimestepValues), []


def sahne_2d4():
    vs, lay = yerlesim(4)
    # yerleşim: sol üst g=0, sol alt Ay, sağ üst Mars, sağ alt Dünya
    for ad, v in zip(('0', '1.62', '3.73', '9.81'), vs):
        r = okuyucu('g' + ad, f'{K2}/{ad}')
        d = Show(r, v)
        ColorBy(d, ('POINTS', 'T'))
        olcek()
        stok_cizgi(r, v)
        isaret(v, (DELIK[0], 0, 0.01), 0.0025, [0.3, 0.9, 1.0])
    GetAnimationScene().UpdateAnimationUsingDataTimeSteps()
    olcek()
    for v in vs:
        Render(v)
    for v in vs:
        gorunum(v, (0.03, 0.0), 0.106)
    return vs, lay, list(GetTimeKeeper().TimestepValues), []


def sahne_3b():
    vs, lay = yerlesim(2)
    ates = []
    for ad, v in zip(('uzay', 'mars'), vs):
        r = okuyucu(ad, f'{K3}/{ad}')
        tam = Reflect(Input=r)
        tam.Plane = 'Z Min'
        cer = Show(tam, v)
        cer.SetRepresentationType('Outline')
        cer.ColorArrayName = ['POINTS', '']
        cer.AmbientColor = cer.DiffuseColor = [1, 1, 1]
        for deger, renk, saydam in ((1200.0, [1.0, 0.85, 0.2], 0.35), (1800.0, [0.9, 0.1, 0.05], 1.0)):
            k = Contour(Input=tam)
            k.ContourBy = ['POINTS', 'T']
            k.Isosurfaces = [deger]
            kd = Show(k, v)
            kd.ColorArrayName = ['POINTS', '']
            kd.AmbientColor = kd.DiffuseColor = renk
            kd.Opacity = saydam
        isaret(v, DELIK, 0.004, [0.3, 0.9, 1.0])
        ates.append(isaret(v, ATES, 0.004, [0.3, 1.0, 0.4]))
        try:
            v.UseColorPaletteForBackground = 0
        except AttributeError:
            pass
        v.Background = list(ARKA)
        v.OrientationAxesVisibility = 0
        v.CameraParallelProjection = 0
    GetAnimationScene().UpdateAnimationUsingDataTimeSteps()
    for v in vs:
        Render(v)
    return vs, lay, list(GetTimeKeeper().TimestepValues), ates


def kamera(i, n):
    az = math.radians(AZ0 + (AZ1 - AZ0) * (i / max(n - 1, 1)))
    el = math.radians(YUKSELIS)
    return [UZAKLIK * math.cos(el) * math.sin(az), UZAKLIK * math.sin(el), UZAKLIK * math.cos(el) * math.cos(az)]


def kareleri_ciz(vs, lay, zaman, ates, klasor, uc_b):
    sahne = GetAnimationScene()
    sahne.PlayMode = 'Snap To TimeSteps'
    os.makedirs(klasor, exist_ok=True)
    for i, t in enumerate(zaman):
        sahne.AnimationTime = t
        for d in ates:
            d.Visibility = 1 if t <= ATES_SURE + 1e-9 else 0
        if uc_b:
            P = kamera(i, len(zaman))
            for adim in range(2):
                for v in vs:
                    v.CameraPosition = P
                    v.CameraFocalPoint = [0.0, 0.0, 0.0]
                    v.CameraViewUp = [0, 1, 0]
                    v.CameraViewAngle = 30
                if adim == 0:
                    for v in vs:
                        Render(v)
        else:
            for v in vs:
                Render(v)
        SaveScreenshot(f'{klasor}/ham_{i:04d}.png', lay, ImageResolution=[GEN, GOR_Y],
                       OverrideColorPalette='', TransparentBackground=0)
        if i % 10 == 0:
            print(f'  kare {i + 1}/{len(zaman)}  t = {t:.3f} s', flush=True)


def renk_cubugu(c, x, y0, y1, font):
    from matplotlib import colormaps
    cm = colormaps['inferno']
    gen = 26
    for y in range(y0, y1 + 1):
        f = 1 - (y - y0) / (y1 - y0)
        c.line([(x, y), (x + gen, y)], fill=tuple(int(255 * a) for a in cm(f)[:3]))
    c.rectangle([x, y0, x + gen, y1], outline=(150, 150, 150))
    for deger in (300, 800, 1300, 1800, 2300):
        y = y1 - (deger - T_ARALIK[0]) / (T_ARALIK[1] - T_ARALIK[0]) * (y1 - y0)
        c.line([(x + gen, y), (x + gen + 7, y)], fill=(220, 220, 220), width=2)
        c.text((x + gen + 12, y), f'{deger}', font=font, fill=(225, 225, 225), anchor='lm')
    c.text((x + gen // 2, y0 - 16), 'T (K)', font=font, fill=(235, 235, 235), anchor='ms')


def yazilar(klasor, zaman, tur, dil):
    M = METIN[dil]
    f_bas, f_t = ImageFont.truetype(FONT_K, 38), ImageFont.truetype(FONT_K, 36)
    f_g, f_k = ImageFont.truetype(FONT_K, 26), ImageFont.truetype(FONT, 21)
    if tur == '2d4':
        etiket = [(M['0'], 0, 0), (M['1.62'], 0, 1), (M['3.73'], 1, 0), (M['9.81'], 1, 1)]
        notu = M['not2']
    else:
        etiket = [(M['uzay'], 0, 0), (M['mars'], 1, 0)]
        notu = M['not3']
    gw = GEN // 2
    for i, t in enumerate(zaman):
        ham = Image.open(f'{klasor}/ham_{i:04d}.png').convert('RGB')
        k = Image.new('RGB', (GEN, YUK), ARKA8)
        k.paste(ham, (0, UST))
        c = ImageDraw.Draw(k)
        c.text((36, UST // 2), M[tur], font=f_bas, fill=(240, 240, 240), anchor='lm')
        c.text((GEN - 36, UST // 2), f't = {t:.2f} s'.replace('.', M['ondalik']), font=f_t, fill=(255, 213, 79),
               anchor='rm')
        c.line([(0, UST - 1), (GEN, UST - 1)], fill=(60, 66, 80), width=2)
        c.line([(gw, UST), (gw, YUK - ALT)], fill=(60, 66, 80), width=2)
        if tur == '2d4':
            c.line([(0, UST + GOR_Y // 2), (GEN, UST + GOR_Y // 2)], fill=(60, 66, 80), width=2)
        for e, sx, sy in etiket:
            c.text((sx * gw + 30, UST + sy * (GOR_Y // 2) + 18), e, font=f_g, fill=(230, 230, 230), anchor='lt')
            if t <= ATES_SURE + 1e-9:
                c.text((sx * gw + 30, UST + sy * (GOR_Y // 2) + 54), M['tutus'], font=f_k, fill=(77, 255, 102),
                       anchor='lt')
        if tur == '3b':
            for j in range(2):
                x, y = j * gw + 30, YUK - ALT - 36
                for renk, yazi in (((255, 217, 51), M['sari']), ((230, 26, 13), M['kirmizi']),
                                   ((77, 230, 255), M['delik'])):
                    c.rectangle([x, y - 10, x + 20, y + 10], fill=renk)
                    c.text((x + 28, y), yazi, font=f_k, fill=(225, 225, 225), anchor='lm')
                    x += 56 + c.textlength(yazi, font=f_k)
        else:
            for sx in range(2):
                renk_cubugu(c, sx * gw + gw - 120, UST + 120, YUK - ALT - 90 if tur != '2d4' else UST + GOR_Y // 2 - 40,
                            f_k)
            c.text((36, YUK - ALT - 24), M['yesil'], font=f_k, fill=(120, 255, 140), anchor='lm')
        c.line([(0, YUK - ALT), (GEN, YUK - ALT)], fill=(60, 66, 80), width=2)
        c.text((GEN // 2, YUK - ALT // 2), notu, font=f_k, fill=(239, 154, 154), anchor='mm')
        k.save(f'{klasor}/{dil}_{i:04d}.png', compress_level=1)


def mp4(klasor, onek, cikti):
    r = subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', f'{klasor}/{onek}_%04d.png',
                        '-c:v', 'libx264', '-preset', 'slow', '-crf', '20', '-pix_fmt', 'yuv420p',
                        '-profile:v', 'high', '-level', '4.1', '-movflags', '+faststart', cikti],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f'ffmpeg başarısız: {r.stderr[-800:]}')
    print(f'  -> {cikti}  ({os.path.getsize(cikti) / 1e6:.2f} MB)', flush=True)


# ------------------------------------------------------------------ 2 x 2 (4 yerçekimi) düzeni
# Panel sırası (yerlesim(4)): sol üst, sol alt, sağ üst, sağ alt.  Etiketler panelin ÜSTÜNDEKİ boş banda yazılır;
# alan bandın altına yerleşir (v1'de 2B etiketleri tavandaki aleve biniyordu). Tek renk çubuğu sağ kenarda.
ALT4 = 88                          # alt bant: açıklama + GÖSTERİM notu
GOR_Y4 = YUK - UST - ALT4
PAN_H, PAN_W = GOR_Y4 // 2, GEN // 2
BANT = 46                          # panel üstü etiket bandı (px)
ALAN_PX = PAN_H - BANT - 14        # 200 mm alanın panel içindeki yüksekliği (px)
M_PX = 0.2 / ALAN_PX               # m / px
YARI4 = PAN_H / 2 * M_PX           # paralel izdüşüm yarı yüksekliği
ODAK_Y4 = (BANT + ALAN_PX / 2 - PAN_H / 2) * M_PX     # alanı bandın altına itmek için kamera kaydırması
SIRA4 = {'kesit4': ['uzay', 'ay', 'mars', 'dunya'], '3b4': ['uzay', 'ay', 'mars', 'dunya'],
         '2d4': ['0', '1.62', '3.73', '9.81']}
ETIKET4 = {'uzay': 'g_uzay', 'ay': 'g_ay', 'mars': 'g_mars', 'dunya': 'g_dunya',
           '0': 'g_uzay', '1.62': 'g_ay', '3.73': 'g_mars', '9.81': 'g_dunya'}
POZ4 = [(0, 0), (0, 1), (1, 0), (1, 1)]                  # (sütun, satır), yerlesim(4) sırasıyla
ISO = ((900.0, 0.45), (1400.0, 0.6))   # 1400 K de yarı saydam: içindeki stokiyometrik tel görünsün


def inferno(T):
    from matplotlib import colormaps
    return list(colormaps['inferno']((T - T_ARALIK[0]) / (T_ARALIK[1] - T_ARALIK[0]))[:3])


def gorunum4(v):
    gorunum(v, (0.0, ODAK_Y4), YARI4)


def sahne_duz4(tur):
    """kesit4 (3B koşuların z = 1 mm kesiti) ve 2d4 (2B koşular)."""
    vs, lay = yerlesim(4)
    for ad, v in zip(SIRA4[tur], vs):
        if tur == 'kesit4':
            r = okuyucu(ad, f'{K3}/{ad}')
            s = Slice(Input=r)
            s.SliceType = 'Plane'
            s.SliceType.Origin = [0, 0, 0.001]
            s.SliceType.Normal = [0, 0, 1]
        else:
            # 2B dilim tek hücre kalın: orta düzlemden kes (kontur kameraya yandan bakan şerit değil çizgi olsun)
            r = okuyucu('g' + ad, f'{K2}/{ad}')
            s = Slice(Input=r)
            s.SliceType = 'Plane'
            s.SliceType.Origin = [0, 0, 0.000625]
            s.SliceType.Normal = [0, 0, 1]
        d = Show(s, v)
        ColorBy(d, ('POINTS', 'T'))
        olcek()
        stok_cizgi(s, v)
        isaret(v, (DELIK[0], 0, 0.02), 0.0025, [0.3, 0.9, 1.0])
    GetAnimationScene().UpdateAnimationUsingDataTimeSteps()
    olcek()
    for v in vs:
        Render(v)
    for v in vs:
        gorunum4(v)
    return vs, lay, list(GetTimeKeeper().TimestepValues), []


def sahne_3b4():
    vs, lay = yerlesim(4)
    ates = []
    for ad, v in zip(SIRA4['3b4'], vs):
        r = okuyucu(ad, f'{K3}/{ad}')
        tam = Reflect(Input=r)
        tam.Plane = 'Z Min'
        cer = Show(tam, v)
        cer.SetRepresentationType('Outline')
        cer.ColorArrayName = ['POINTS', '']
        cer.AmbientColor = cer.DiffuseColor = [1, 1, 1]
        for deger, saydam in ISO:
            k = Contour(Input=tam)
            k.ContourBy = ['POINTS', 'T']
            k.Isosurfaces = [deger]
            kd = Show(k, v)
            kd.ColorArrayName = ['POINTS', '']
            kd.AmbientColor = kd.DiffuseColor = inferno(deger)
            kd.Opacity = saydam
            kd.Ambient = 0.35                        # koyu arka planda seçilebilsin
        st = Contour(Input=tam)                      # stokiyometrik yüzey, ince tel
        st.ContourBy = ['POINTS', 'CH4']
        st.Isosurfaces = [Y_ST]
        sd = Show(st, v)
        sd.SetRepresentationType('Wireframe')
        sd.ColorArrayName = ['POINTS', '']
        sd.AmbientColor = sd.DiffuseColor = [0.25, 1.0, 0.35]
        sd.LineWidth = 1.5
        sd.Opacity = 0.85
        isaret(v, DELIK, 0.004, [0.3, 0.9, 1.0])
        ates.append(isaret(v, ATES, 0.004, [0.3, 1.0, 0.4]))
        try:
            v.UseColorPaletteForBackground = 0
        except AttributeError:
            pass
        v.Background = list(ARKA)
        v.OrientationAxesVisibility = 0
        v.CameraParallelProjection = 0
    GetAnimationScene().UpdateAnimationUsingDataTimeSteps()
    for v in vs:
        Render(v)
    return vs, lay, list(GetTimeKeeper().TimestepValues), ates


UZAKLIK4 = 0.60


def kamera4(i, n):
    az = math.radians(AZ0 + (AZ1 - AZ0) * (i / max(n - 1, 1)))
    el = math.radians(YUKSELIS)
    return [UZAKLIK4 * math.cos(el) * math.sin(az), UZAKLIK4 * math.sin(el) - 0.012,
            UZAKLIK4 * math.cos(el) * math.cos(az)]


def kareleri_ciz4(vs, lay, zaman, ates, klasor, uc_b):
    sahne = GetAnimationScene()
    sahne.PlayMode = 'Snap To TimeSteps'
    os.makedirs(klasor, exist_ok=True)
    for i, t in enumerate(zaman):
        sahne.AnimationTime = t
        for d in ates:
            d.Visibility = 1 if t <= ATES_SURE + 1e-9 else 0
        if uc_b:                                   # dört görünüm aynı (bağlı) kamera, ~90° dönüş
            P = kamera4(i, len(zaman))
            for adim in range(2):
                for v in vs:
                    v.CameraPosition = P
                    v.CameraFocalPoint = [0.0, -0.012, 0.0]
                    v.CameraViewUp = [0, 1, 0]
                    v.CameraViewAngle = 30
                if adim == 0:
                    for v in vs:
                        Render(v)
        else:
            for v in vs:
                Render(v)
        SaveScreenshot(f'{klasor}/ham_{i:04d}.png', lay, ImageResolution=[GEN, GOR_Y4],
                       OverrideColorPalette='', TransparentBackground=0)
        if i % 10 == 0:
            print(f'  kare {i + 1}/{len(zaman)}  t = {t:.3f} s', flush=True)


def renk_cubugu4(c, x, y0, y1, font, isaretler=()):
    from matplotlib import colormaps
    cm = colormaps['inferno']
    gen = 26
    for y in range(y0, y1 + 1):
        f = 1 - (y - y0) / (y1 - y0)
        c.line([(x, y), (x + gen, y)], fill=tuple(int(255 * a) for a in cm(f)[:3]))
    c.rectangle([x, y0, x + gen, y1], outline=(150, 150, 150))
    for deger in (300, 800, 1300, 1800, 2300):
        y = y1 - (deger - T_ARALIK[0]) / (T_ARALIK[1] - T_ARALIK[0]) * (y1 - y0)
        c.line([(x + gen, y), (x + gen + 7, y)], fill=(220, 220, 220), width=2)
        c.text((x + gen + 12, y), f'{deger}', font=font, fill=(225, 225, 225), anchor='lm')
    for deger in isaretler:                        # eş-yüzey değerleri: çubuğun solunda ok
        y = y1 - (deger - T_ARALIK[0]) / (T_ARALIK[1] - T_ARALIK[0]) * (y1 - y0)
        c.polygon([(x - 4, y), (x - 16, y - 7), (x - 16, y + 7)], fill=(240, 240, 240))
        c.text((x - 20, y), f'{int(deger)}', font=font, fill=(240, 240, 240), anchor='rm')
    c.text((x + gen // 2, y0 - 16), 'T (K)', font=font, fill=(235, 235, 235), anchor='ms')


def yazilar4(klasor, zaman, tur, dil):
    M = METIN[dil]
    f_bas, f_t = ImageFont.truetype(FONT_K, 38), ImageFont.truetype(FONT_K, 36)
    f_g, f_k = ImageFont.truetype(FONT_K, 25), ImageFont.truetype(FONT, 21)
    notu = {'2d4': M['not2'], '3b4': M['not34'], 'kesit4': M['not3']}[tur]
    for i, t in enumerate(zaman):
        ham = Image.open(f'{klasor}/ham_{i:04d}.png').convert('RGB')
        k = Image.new('RGB', (GEN, YUK), ARKA8)
        k.paste(ham, (0, UST))
        c = ImageDraw.Draw(k)
        c.text((36, UST // 2), M[tur], font=f_bas, fill=(240, 240, 240), anchor='lm')
        c.text((GEN - 36, UST // 2), f't = {t:.2f} s'.replace('.', M['ondalik']), font=f_t, fill=(255, 213, 79),
               anchor='rm')
        c.line([(0, UST - 1), (GEN, UST - 1)], fill=(60, 66, 80), width=2)
        c.line([(PAN_W, UST), (PAN_W, UST + GOR_Y4)], fill=(60, 66, 80), width=2)
        c.line([(0, UST + PAN_H), (GEN, UST + PAN_H)], fill=(60, 66, 80), width=2)
        for ad, (sx, sy) in zip(SIRA4[tur], POZ4):
            x0, y0 = sx * PAN_W + 24, UST + sy * PAN_H + BANT // 2
            e = M[ETIKET4[ad]]
            c.text((x0, y0), e, font=f_g, fill=(230, 230, 230), anchor='lm')
            if t <= ATES_SURE + 1e-9:
                c.text((x0 + c.textlength(e, font=f_g) + 24, y0), M['tutus'], font=f_k, fill=(77, 255, 102), anchor='lm')
        renk_cubugu4(c, GEN - 112, UST + 70, UST + GOR_Y4 - 40, f_k, [d for d, _ in ISO] if tur == '3b4' else ())
        # alt bant: açıklama satırı + GÖSTERİM notu
        y = YUK - ALT4 + 22
        x = 36
        if tur == '3b4':
            ogeler = [(tuple(int(255 * a) for a in inferno(900.0)), M['iso1']),
                      (tuple(int(255 * a) for a in inferno(1400.0)), M['iso2']),
                      ((64, 255, 90), M['tel']), ((77, 230, 255), M['delik'])]
        else:
            ogeler = [((64, 255, 90), M['yesil']), ((77, 230, 255), M['delik'])]
        for renk, yazi in ogeler:
            c.rectangle([x, y - 9, x + 18, y + 9], fill=renk)
            c.text((x + 26, y), yazi, font=f_k, fill=(225, 225, 225), anchor='lm')
            x += 60 + c.textlength(yazi, font=f_k)
        c.line([(0, UST + GOR_Y4), (GEN, UST + GOR_Y4)], fill=(60, 66, 80), width=2)
        c.text((GEN // 2, YUK - 22), notu, font=f_k, fill=(239, 154, 154), anchor='mm')
        k.save(f'{klasor}/{dil}_{i:04d}.png', compress_level=1)


AD = {'kesit': 'gaz_uzay_mars', '3b': 'gaz_3b', '2d4': 'gaz2d_4g', '3b4': 'gaz_3b_4g', 'kesit4': 'gaz_kesit_4g'}
DORT = ('2d4', '3b4', 'kesit4')


def uret(tur):
    klasor = f'{CIK}/_video_gaz_{tur}'
    shutil.rmtree(klasor, ignore_errors=True)
    try:
        print(f'{tur}: sahne kuruluyor', flush=True)
        if tur in DORT:
            vs, lay, zaman, ates = sahne_3b4() if tur == '3b4' else sahne_duz4(tur)
        else:
            vs, lay, zaman, ates = {'kesit': sahne_kesit, '3b': sahne_3b}[tur]()
        print(f'{tur}: {len(zaman)} zaman ({zaman[0]}–{zaman[-1]} s)', flush=True)
        if tur in DORT:
            kareleri_ciz4(vs, lay, zaman, ates, klasor, tur == '3b4')
        else:
            kareleri_ciz(vs, lay, zaman, ates, klasor, tur == '3b')
        for dil in ('tr', 'en'):
            (yazilar4 if tur in DORT else yazilar)(klasor, zaman, tur, dil)
            mp4(klasor, dil, f'{CIK}/{ONEK}{AD[tur]}{"" if dil == "tr" else "_en"}.mp4')
        os.makedirs(f'{CIK}/ekran', exist_ok=True)
        shutil.copy(f'{klasor}/tr_{len(zaman) // 2:04d}.png', f'{CIK}/ekran/video_{ONEK}{AD[tur]}_kare.png')
    finally:
        if not os.environ.get('PV_VIDEO_TUT'):
            shutil.rmtree(klasor, ignore_errors=True)


if __name__ == '__main__':
    if shutil.which('ffmpeg') is None:
        raise SystemExit('ffmpeg yok')
    turler = [a for a in sys.argv[1:] if not a.startswith('-')] or ['kesit', '3b', '2d4', '3b4', 'kesit4']
    if len(turler) == 1:
        uret(turler[0])
    else:
        pv = shutil.which('pvpython') or 'pvpython'
        hata = 0
        for tur in turler:
            rc = subprocess.run([pv, '--force-offscreen-rendering', os.path.abspath(__file__), tur]).returncode
            print(f'{tur}: pvpython çıkış {rc}', flush=True)
            hata += rc != 0
        sys.exit(1 if hata else 0)
