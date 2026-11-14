"""
pv_sizinti_4g.py — n-heptan (sıvı) sızıntısının 4 yerçekimli videoları (2 x 2: sol üst uzay, sağ üst Mars,
sol alt Ay, sağ alt Dünya). GÖSTERİM — deney verisiyle doğrulanmadı (her karede yazılı).

    pvpython --force-offscreen-rendering pv_sizinti_4g.py            # ikisi de (ayrı ParaView oturumlarında)
    pvpython --force-offscreen-rendering pv_sizinti_4g.py 3b         # of_gorsel/sizinti_3b_4g(_en).mp4
    pvpython --force-offscreen-rendering pv_sizinti_4g.py kesit      # of_gorsel/sizinti_kesit_4g(_en).mp4

- 3b: z = 0'da aynalanmış tam kabin + çerçeve, 1200 K yarı saydam + 2400 K eş-yüzey (renkleri tek T çubuğundan,
  çubukta işaretli), damlalar (aynalanmış), dört görünümde aynı (bağlı) kamera, ~90° dönüş.
- kesit: z = 1 mm kesiti (simetri düzleminin ilk hücre katmanı), T + n-heptan buharı konturları (yeşil),
  damlalar (20 kat büyütülmüş).
- Kare zamanları damla serisinden (damla_vtk.py, 0,01 s, 101 kare); sıcaklık alanı her koşuda yazılmış en yakın
  zamandan (20 zaman: 0, 0,05, 0,11 … 1 s) — üstte "sıcaklık alanı: t = …" olarak yazılır.
- Düzen, kamera ve yazı yardımcıları pv_gaz_video.py'den (2 x 2: etiketler panel üstü bantta, tek renk çubuğu).
Ortam: SIZINTI_KOK (deneme için başka vaka kökü), PV_VIDEO_ONEK (çıktı öneki), PV_KARE_SINIR (deneme: ilk N kare).
"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.expanduser('~/nasaspaceapp'))
import pv_gaz_video as g                      # noqa: E402  (2 x 2 düzen / kamera / yardımcılar)
from paraview.simple import *                # noqa: E402,F401
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

KOK = os.path.expanduser('~/nasaspaceapp')
K = os.environ.get('SIZINTI_KOK', f'{KOK}/of_kosular/sizinti3d_ince')
ONEK = os.environ.get('PV_VIDEO_ONEK', '')
SINIR = int(os.environ.get('PV_KARE_SINIR', '0'))
CIK = f'{KOK}/of_gorsel'
g.T_ARALIK = (300.0, 2900.0)                  # sıvı sızıntısı videolarıyla aynı ölçek
g.ATES = (0.0, 0.020, 0.0)                    # of_sizinti3d.py tutuşturucu
g.ATES_SURE = 0.03                            # darbe 0,01 s + sönümlenme (pv_3b_video.py ile aynı etiket süresi)
ENJ = (-0.080, 0.0, 0.0)
ISO = ((1200.0, 0.35), (2400.0, 1.0))
SIRA = ['uzay', 'ay', 'mars', 'dunya']        # yerlesim(4): sol üst, sol alt, sağ üst, sağ alt
POZ = [(0, 0), (0, 1), (1, 0), (1, 1)]
ETIKET = {'uzay': 'g_uzay', 'ay': 'g_ay', 'mars': 'g_mars', 'dunya': 'g_dunya'}
DAMLA_BUYUTME = 20
METIN = {
    'tr': {'3b': 'Kabinde n-heptan sızıntısı: 4 yerçekimi (3B)', 'kesit': 'Kabinde n-heptan sızıntısı: 4 yerçekimi (z = 1 mm kesiti)',
           'iso1': '1200 K (yarı saydam)', 'iso2': '2400 K', 'damla3': 'açık mavi: yakıt damlaları',
           'buhar': 'yeşil: n-heptan buharı (Y = 0,01 / 0,05 / 0,1 / 0,2)', 'damla2': 'açık mavi: damlalar (20× büyütülmüş)',
           'alan': 'sıcaklık alanı: t = {} s', 'tutus': 'tutuşturucu',
           'not3': 'OpenFOAM, 2,5 mm ızgara, 3B yarım alan (z = 0 simetri; görüntü aynalanmış) — GÖSTERİM, deney verisiyle doğrulanmadı',
           'not2': 'OpenFOAM, 2,5 mm ızgara, 3B yarım alan (simetri düzlemi, z = 1 mm) — GÖSTERİM, deney verisiyle doğrulanmadı',
           'ondalik': ','},
    'en': {'3b': 'n-Heptane leak in a cabin: four gravity levels (3D)', 'kesit': 'n-Heptane leak in a cabin: four gravity levels (z = 1 mm section)',
           'iso1': '1200 K (semi-transparent)', 'iso2': '2400 K', 'damla3': 'light blue: fuel droplets',
           'buhar': 'green: n-heptane vapour (Y = 0.01 / 0.05 / 0.1 / 0.2)', 'damla2': 'light blue: droplets (20× enlarged)',
           'alan': 'temperature field: t = {} s', 'tutus': 'igniter',
           'not3': 'OpenFOAM, 2.5 mm grid, 3D half domain (z = 0 symmetry; mirrored view) — DEMONSTRATION, not validated against experimental data',
           'not2': 'OpenFOAM, 2.5 mm grid, 3D half domain (symmetry plane, z = 1 mm) — DEMONSTRATION, not validated against experimental data',
           'ondalik': '.'},
}
for d in ('tr', 'en'):
    for k in ('g_uzay', 'g_ay', 'g_mars', 'g_dunya'):
        METIN[d][k] = g.METIN[d][k]


def okuyucu(ad):
    vaka = f'{K}/{ad}'
    foam = f'{vaka}/{ad}.foam'
    if not os.path.exists(foam):
        open(foam, 'w').close()
    r = OpenFOAMReader(registrationName=ad, FileName=foam)
    r.CaseType = 'Decomposed Case'
    r.MeshRegions = ['internalMesh']
    r.SkipZeroTime = 0
    r.UpdatePipelineInformation()
    return r


def damlalar(ad):
    seri = f'{K}/{ad}/damla_vtk/damla.vtp.series'
    if not os.path.exists(seri):
        raise SystemExit(f'damla serisi yok: {seri} (önce damla_vtk.py)')
    dr = XMLPolyDataReader(registrationName=ad + '_damla', FileName=[seri])
    dr.PointArrayStatus = ['d', 'T']
    return dr


def sahne_3b():
    vs, lay = g.yerlesim(4)
    ates = []
    for ad, v in zip(SIRA, vs):
        r = okuyucu(ad)
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
            kd.AmbientColor = kd.DiffuseColor = g.inferno(deger)
            kd.Opacity = saydam
            kd.Ambient = 0.3
        dt = Reflect(Input=damlalar(ad))
        dt.Plane = 'Z Min'
        dd = Show(dt, v)
        dd.SetRepresentationType('Point Gaussian')
        dd.GaussianRadius = 0.0012
        dd.ColorArrayName = ['POINTS', '']
        dd.AmbientColor = dd.DiffuseColor = [0.6, 0.9, 1.0]
        g.isaret(v, ENJ, 0.003, [0.3, 0.9, 1.0])
        ates.append(g.isaret(v, g.ATES, 0.004, [0.3, 1.0, 0.4]))
        try:
            v.UseColorPaletteForBackground = 0
        except AttributeError:
            pass
        v.Background = list(g.ARKA)
        v.OrientationAxesVisibility = 0
        v.CameraParallelProjection = 0
    GetAnimationScene().UpdateAnimationUsingDataTimeSteps()
    for v in vs:
        Render(v)
    return vs, lay, ates


def sahne_kesit():
    vs, lay = g.yerlesim(4)
    for ad, v in zip(SIRA, vs):
        r = okuyucu(ad)
        s = Slice(Input=r)
        s.SliceType = 'Plane'
        s.SliceType.Origin = [0, 0, 0.001]
        s.SliceType.Normal = [0, 0, 1]
        d = Show(s, v)
        ColorBy(d, ('POINTS', 'T'))
        g.olcek()
        k = Contour(Input=s)
        k.ContourBy = ['POINTS', 'C7H16']
        k.Isosurfaces = [0.01, 0.05, 0.1, 0.2]
        kd = Show(k, v)
        kd.ColorArrayName = ['POINTS', '']
        kd.AmbientColor = kd.DiffuseColor = [0.2, 1.0, 0.3]
        kd.LineWidth = 2
        kd.Position = [0, 0, 0.01]
        dd = Show(damlalar(ad), v)
        dd.SetRepresentationType('Point Gaussian')
        dd.ColorArrayName = ['POINTS', '']
        dd.AmbientColor = dd.DiffuseColor = [0.6, 0.9, 1.0]
        dd.ShaderPreset = 'Sphere'
        dd.ScaleByArray = 1
        dd.SetScaleArray = ['POINTS', 'd']
        dd.UseScaleFunction = 0
        dd.GaussianRadius = 0.5 * DAMLA_BUYUTME
        dd.Position = [0, 0, 0.2]                  # kesit düzleminin önünde (z < 0 damlalar opak kesitin arkasında kalmasın)
    GetAnimationScene().UpdateAnimationUsingDataTimeSteps()
    g.olcek()
    for v in vs:
        Render(v)
    for v in vs:
        g.gorunum4(v)
    return vs, lay, []


def alan_zamanlari(ad):
    p0 = f'{K}/{ad}/processor0'
    z = []
    for n in os.listdir(p0):
        try:
            z.append(float(n))
        except ValueError:
            pass
    return sorted(z)


def renk_cubugu(c, x, y0, y1, font, isaretler):
    from matplotlib import colormaps
    cm = colormaps['inferno']
    gen = 26
    lo, hi = g.T_ARALIK
    for y in range(y0, y1 + 1):
        f = 1 - (y - y0) / (y1 - y0)
        c.line([(x, y), (x + gen, y)], fill=tuple(int(255 * a) for a in cm(f)[:3]))
    c.rectangle([x, y0, x + gen, y1], outline=(150, 150, 150))
    for deger in (300, 1000, 1500, 2000, 2500, 2900):
        y = y1 - (deger - lo) / (hi - lo) * (y1 - y0)
        c.line([(x + gen, y), (x + gen + 7, y)], fill=(220, 220, 220), width=2)
        c.text((x + gen + 12, y), f'{deger}', font=font, fill=(225, 225, 225), anchor='lm')
    for deger in isaretler:
        y = y1 - (deger - lo) / (hi - lo) * (y1 - y0)
        c.polygon([(x - 4, y), (x - 16, y - 7), (x - 16, y + 7)], fill=(240, 240, 240))
        c.text((x - 20, y), f'{int(deger)}', font=font, fill=(240, 240, 240), anchor='rm')
    c.text((x + gen // 2, y0 - 16), 'T (K)', font=font, fill=(235, 235, 235), anchor='ms')


def yazilar(klasor, zaman, tur, dil, alan_z):
    M = METIN[dil]
    f_bas, f_t = ImageFont.truetype(g.FONT_K, 38), ImageFont.truetype(g.FONT_K, 34)
    f_g, f_k = ImageFont.truetype(g.FONT_K, 25), ImageFont.truetype(g.FONT, 21)
    sayi = lambda x: f'{x:.2f}'.replace('.', M['ondalik'])
    PAN_W, PAN_H, UST, GOR = g.PAN_W, g.PAN_H, g.UST, g.GOR_Y4
    for i, t in enumerate(zaman):
        ham = Image.open(f'{klasor}/ham_{i:04d}.png').convert('RGB')
        k = Image.new('RGB', (g.GEN, g.YUK), g.ARKA8)
        k.paste(ham, (0, UST))
        c = ImageDraw.Draw(k)
        c.text((36, UST // 2), M[tur], font=f_bas, fill=(240, 240, 240), anchor='lm')
        c.text((g.GEN - 36, UST // 2 - 12), f't = {sayi(t)} s', font=f_t, fill=(255, 213, 79), anchor='rm')
        ta = min(alan_z, key=lambda a: abs(a - t))
        c.text((g.GEN - 36, UST - 10), M['alan'].format(sayi(ta)), font=f_k, fill=(170, 175, 190), anchor='rb')
        c.line([(0, UST - 1), (g.GEN, UST - 1)], fill=(60, 66, 80), width=2)
        c.line([(PAN_W, UST), (PAN_W, UST + GOR)], fill=(60, 66, 80), width=2)
        c.line([(0, UST + PAN_H), (g.GEN, UST + PAN_H)], fill=(60, 66, 80), width=2)
        for ad, (sx, sy) in zip(SIRA, POZ):
            x0, y0 = sx * PAN_W + 24, UST + sy * PAN_H + g.BANT // 2
            e = M[ETIKET[ad]]
            c.text((x0, y0), e, font=f_g, fill=(230, 230, 230), anchor='lm')
            if t <= g.ATES_SURE + 1e-9:
                c.text((x0 + c.textlength(e, font=f_g) + 24, y0), M['tutus'], font=f_k, fill=(77, 255, 102), anchor='lm')
        renk_cubugu(c, g.GEN - 112, UST + 70, UST + GOR - 40, f_k, [d for d, _ in ISO] if tur == '3b' else ())
        y, x = g.YUK - g.ALT4 + 22, 36
        if tur == '3b':
            ogeler = [(tuple(int(255 * a) for a in g.inferno(1200.0)), M['iso1']),
                      (tuple(int(255 * a) for a in g.inferno(2400.0)), M['iso2']),
                      ((153, 230, 255), M['damla3']), ((77, 230, 255), g.METIN[dil]['delik'])]
        else:
            ogeler = [((51, 255, 77), M['buhar']), ((153, 230, 255), M['damla2'])]
        for renk, yazi in ogeler:
            c.rectangle([x, y - 9, x + 18, y + 9], fill=renk)
            c.text((x + 26, y), yazi, font=f_k, fill=(225, 225, 225), anchor='lm')
            x += 60 + c.textlength(yazi, font=f_k)
        c.line([(0, UST + GOR), (g.GEN, UST + GOR)], fill=(60, 66, 80), width=2)
        c.text((g.GEN // 2, g.YUK - 22), M['not3'] if tur == '3b' else M['not2'], font=f_k, fill=(239, 154, 154),
               anchor='mm')
        k.save(f'{klasor}/{dil}_{i:04d}.png', compress_level=1)


AD = {'3b': 'sizinti_3b_4g', 'kesit': 'sizinti_kesit_4g'}


def uret(tur):
    klasor = f'{CIK}/_video_sizinti4_{tur}'
    shutil.rmtree(klasor, ignore_errors=True)
    try:
        print(f'{tur}: sahne kuruluyor', flush=True)
        vs, lay, ates = sahne_3b() if tur == '3b' else sahne_kesit()
        zaman = list(GetTimeKeeper().TimestepValues)
        if SINIR:
            zaman = zaman[:: max(1, len(zaman) // SINIR)][:SINIR]
        alan_z = sorted(set().union(*[alan_zamanlari(a) for a in SIRA]))
        print(f'{tur}: {len(zaman)} kare ({zaman[0]}–{zaman[-1]} s), alan zamanları {len(alan_z)}', flush=True)
        g.kareleri_ciz4(vs, lay, zaman, ates, klasor, tur == '3b')
        for dil in ('tr', 'en'):
            yazilar(klasor, zaman, tur, dil, alan_z)
            g.mp4(klasor, dil, f'{CIK}/{ONEK}{AD[tur]}{"" if dil == "tr" else "_en"}.mp4')
        os.makedirs(f'{CIK}/ekran', exist_ok=True)
        for hedef in (0.15, 0.55):              # kontrol kareleri
            j = min(range(len(zaman)), key=lambda q: abs(zaman[q] - hedef))
            shutil.copy(f'{klasor}/tr_{j:04d}.png', f'{CIK}/ekran/video_{ONEK}{AD[tur]}_t{hedef:.2f}.png')
    finally:
        if not os.environ.get('PV_VIDEO_TUT'):
            shutil.rmtree(klasor, ignore_errors=True)


if __name__ == '__main__':
    turler = [a for a in sys.argv[1:] if not a.startswith('-')] or ['3b', 'kesit']
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
