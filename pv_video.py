"""
pv_video.py — pv_kesit.py sahnesinden (uzay solda, Mars sağda, z = 0 kesiti, damlalar, sabit 300–2900 K) video üretir.

Çalıştırma (ekransız):
    pvpython --force-offscreen-rendering pv_video.py              # sızıntı + tek damla, TR + EN
    pvpython --force-offscreen-rendering pv_video.py sizinti      # yalnız sızıntı
    pvpython --force-offscreen-rendering pv_video.py tek_damla    # yalnız tek damla

Akış: ParaView her zaman adımını bir kez çizer (yazısız); başlık, zaman, görünüm adları ve not PIL ile
TR ve EN olarak ayrı ayrı eklenir; ffmpeg ile H.264 / yuv420p mp4 (PowerPoint / Google Slides uyumlu).
Ara PNG kareleri iş bitince silinir. Damlalar için önce: python3 damla_vtk.py (damla_vtk/damla.vtp.series).
"""
import os
import shutil
import subprocess
import sys

from paraview.simple import *
from PIL import Image, ImageDraw, ImageFont

KOK = os.path.expanduser('~/nasaspaceapp')
CIK = f'{KOK}/of_gorsel'
GEN, YUK = 1920, 1080
UST, ALT = 96, 52                      # PIL ile eklenen başlık ve not bantları (px)
FPS = 10
T_ARALIK = (300.0, 2900.0)
YAKIN = 0.025                          # tek damla: gösterilen yarı genişlik (m)
CUBUK_X = {'sizinti': [800, 1760], 'sizinti_ince': [800, 1760], 'tek_damla': [1500]}   # renk çubuğu sol kenarı (px)
ARKA = (0.075, 0.085, 0.11)
ARKA8 = tuple(int(255 * c) for c in ARKA)
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_K = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

METIN = {
    'tr': {'sizinti': 'Kabinde n-heptan sızıntısı: Uzay vs Mars',
           'sizinti_ince': 'Kabinde n-heptan sızıntısı: Uzay vs Mars — ince ızgara',
           'not_ince': 'OpenFOAM, ince ızgara (2,5 mm, 3B yarım alan; simetri düzlemi) — GÖSTERİM, deney verisiyle doğrulanmadı',
           'tek_damla': 'Tek n-heptan damlası (2 mm), mikro yerçekimi — ışınımsız',
           'uzay': 'Uzay  (g = 0)', 'mars': 'Mars  (g = 3,73 m/s²)',
           'damla_g': 'g = 0 · damla gerçek boyutunda',
           'not': 'OpenFOAM, kaba ızgara — GÖSTERİM, deney verisiyle doğrulanmadı',
           'not_damla': 'OpenFOAM, kaba ızgara (2,4 mm) — FLEX ile karşılaştırma için; K ≈ 1,8 × FLEX',
           'ondalik': ','},
    'en': {'sizinti': 'n-Heptane leak in a cabin: Space vs Mars',
           'sizinti_ince': 'n-Heptane leak in a cabin: Space vs Mars — fine grid',
           'not_ince': 'OpenFOAM, fine grid (2.5 mm, 3D half domain; symmetry plane) — DEMONSTRATION, not validated against experimental data',
           'tek_damla': 'Single n-heptane droplet (2 mm), microgravity — no radiation',
           'uzay': 'Space  (g = 0)', 'mars': 'Mars  (g = 3.73 m/s²)',
           'damla_g': 'g = 0 · droplet at true size',
           'not': 'OpenFOAM, coarse grid — DEMONSTRATION, not validated against experimental data',
           'not_damla': 'OpenFOAM, coarse grid (2.4 mm) — for comparison with FLEX; K ≈ 1.8 × FLEX',
           'ondalik': '.'},
}


def olcek_sabitle():
    """pv_kesit.py ile aynı: her ColorBy'dan SONRA; zaman değişince yeniden ayarlanmaz."""
    lut = GetColorTransferFunction('T')
    pwf = GetOpacityTransferFunction('T')
    lut.ApplyPreset('Inferno (matplotlib)', True)
    lut.AutomaticRescaleRangeMode = 'Never'
    lut.RescaleTransferFunction(*T_ARALIK)
    pwf.RescaleTransferFunction(*T_ARALIK)
    return lut


def gorunum_ayarla(v, merkez, yari):
    """Koyu arka plan, eksen işareti yok, paralel izdüşüm; alan solda, renk çubuğu (PIL) sağda.
    İlk Render kamerayı sıfırladığı için çağıran tüm görünümleri ÖNCE bir kez çizer."""
    try:
        v.UseColorPaletteForBackground = 0
    except AttributeError:
        pass
    v.Background = list(ARKA)
    v.OrientationAxesVisibility = 0
    v.CameraParallelProjection = 1
    v.CameraPosition = [merkez[0], merkez[1], 1.0]
    v.CameraFocalPoint = [merkez[0], merkez[1], 0.0]
    v.CameraViewUp = [0, 1, 0]
    v.CameraParallelScale = yari
    # renk çubuğu PIL ile çizilir (ekransız çizimde ParaView çubuğunun yazıları kayıyor/kesiliyor)
    GetScalarBar(GetColorTransferFunction('T'), v).Visibility = 0


def sahne_sizinti():
    """pv_kesit.py'deki kurulumu çalıştırır, video için görünümü ayarlar. -> (görünümler, düzen, zamanlar)."""
    ns = {}
    exec(open(f'{KOK}/pv_kesit.py').read(), ns)
    v1, v2, layout = ns['v1'], ns['v2'], ns['layout']
    for ad in ('uzay', 'mars'):                    # görünüm adları PIL ile (iki dil) yazılır
        y = FindSource(ad + '_yazi')
        if y:
            for v in (v1, v2):
                Hide(y, v)
    # alan ±100 mm: yükseklikte %80, sağda renk çubuğuna yer
    # damlalar kesit düzleminin (z = 0) önüne: z < 0'dakiler opak kesitin arkasında kalıyordu
    for ad in ('uzay', 'mars'):
        dk = FindSource(ad + '_damla_vtp') or FindSource(ad + '_damla')
        if dk:
            GetDisplayProperties(dk, v1 if ad == 'uzay' else v2).Position = [0, 0, 0.2]
    Render(v1)
    Render(v2)
    for v in (v1, v2):
        gorunum_ayarla(v, (0.024, 0.0), 0.125)
    zaman = list(GetAnimationScene().TimeKeeper.TimestepValues)
    return [v1, v2], layout, zaman


def sahne_tek_damla():
    v = GetActiveViewOrCreate('RenderView')
    layout = GetLayout(v)
    vaka = f'{KOK}/of_kosular/tek_damla/isinimsiz'
    foam = f'{vaka}/isinimsiz.foam'
    if not os.path.exists(foam):
        open(foam, 'w').close()
    r = OpenFOAMReader(registrationName='tek_damla', FileName=foam)
    r.CaseType = 'Decomposed Case'
    r.MeshRegions = ['internalMesh']
    r.UpdatePipelineInformation()
    s = Slice(registrationName='tek_damla_kesit', Input=r)
    s.SliceType = 'Plane'
    s.SliceType.Origin = [0, 0, 0]
    s.SliceType.Normal = [0, 0, 1]
    kr = Clip(registrationName='tek_damla_yakin', Input=s)      # damla yakını: ±25 mm
    kr.ClipType = 'Box'
    kr.ClipType.Position = [-YAKIN, -YAKIN, -0.01]
    kr.ClipType.Length = [2 * YAKIN, 2 * YAKIN, 0.02]
    kr.Exact = 1
    kr.Invert = 1
    d = Show(kr, v)
    ColorBy(d, ('POINTS', 'T'))
    olcek_sabitle()
    yakit = [a for a in r.CellArrays.Available if 'C7H16' in a.upper()]
    if yakit:
        k = Contour(registrationName='tek_damla_yakit', Input=kr)
        k.ContourBy = ['POINTS', yakit[0]]
        k.Isosurfaces = [0.01, 0.05, 0.1, 0.2]
        kd = Show(k, v)
        kd.ColorArrayName = ['POINTS', '']
        kd.AmbientColor = kd.DiffuseColor = [0.2, 1.0, 0.3]
        kd.LineWidth = 2
    seri = f'{vaka}/damla_vtk/damla.vtp.series'
    if os.path.exists(seri):
        dr = XMLPolyDataReader(registrationName='tek_damla_vtp', FileName=[seri])
        dr.PointArrayStatus = ['d', 'T']
        # tek parsel: Point Gaussian tek noktada yarım daire çiziyor -> çapa göre ölçekli küre glifi (gerçek boyut)
        gl = Glyph(registrationName='tek_damla_kure', Input=dr, GlyphType='Sphere')
        gl.ScaleArray = ['POINTS', 'd']
        gl.ScaleFactor = 1.0                           # Sphere glifi yarıçap 0,5 -> çap = d
        gl.GlyphMode = 'All Points'
        gl.GlyphType.ThetaResolution = 48
        gl.GlyphType.PhiResolution = 24
        dd = Show(gl, v)
        dd.ColorArrayName = ['POINTS', '']
        dd.AmbientColor = dd.DiffuseColor = [0.6, 0.9, 1.0]
        dd.Ambient = 0.6
        dd.Position = [0, 0, 0.05]                     # kesit düzleminin önünde
    else:
        print('Damla serisi yok:', seri, '(python3 damla_vtk.py tek_damla)')
    sahne = GetAnimationScene()
    sahne.UpdateAnimationUsingDataTimeSteps()
    olcek_sabitle()
    Render(v)
    gorunum_ayarla(v, (0.006, 0.0), 0.0285)
    return [v], layout, list(sahne.TimeKeeper.TimestepValues)


def kareleri_ciz(gorunumler, layout, zaman, klasor):
    sahne = GetAnimationScene()
    sahne.PlayMode = 'Snap To TimeSteps'
    os.makedirs(klasor, exist_ok=True)
    for i, t in enumerate(zaman):
        sahne.AnimationTime = t
        for v in gorunumler:
            Render(v)
        SaveScreenshot(f'{klasor}/ham_{i:04d}.png', layout, ImageResolution=[GEN, YUK - UST - ALT],
                       OverrideColorPalette='', TransparentBackground=0)
        if i % 20 == 0:
            print(f'  kare {i + 1}/{len(zaman)}  t = {t:.3f} s', flush=True)


def renk_cubugu(c, x, y0, y1, font):
    from matplotlib import colormaps
    cm = colormaps['inferno']
    gen = 30
    for y in range(y0, y1 + 1):
        f = 1 - (y - y0) / (y1 - y0)
        c.line([(x, y), (x + gen, y)], fill=tuple(int(255 * a) for a in cm(f)[:3]))
    c.rectangle([x, y0, x + gen, y1], outline=(150, 150, 150))
    for deger in (300, 1000, 1500, 2000, 2500, 2900):
        y = y1 - (deger - T_ARALIK[0]) / (T_ARALIK[1] - T_ARALIK[0]) * (y1 - y0)
        c.line([(x + gen, y), (x + gen + 8, y)], fill=(220, 220, 220), width=2)
        c.text((x + gen + 14, y), f'{deger}', font=font, fill=(225, 225, 225), anchor='lm')
    c.text((x + gen // 2, y0 - 18), 'T (K)', font=font, fill=(235, 235, 235), anchor='ms')


def yazilari_ekle(klasor, zaman, tur, dil, n_gorunum):
    M = METIN[dil]
    f_bas = ImageFont.truetype(FONT_K, 40)
    f_t = ImageFont.truetype(FONT_K, 38)
    f_g = ImageFont.truetype(FONT_K, 28)
    f_not = ImageFont.truetype(FONT, 22)
    baslik = M[tur]
    if tur.startswith('sizinti'):
        etiket = [M['uzay'], M['mars']]
    else:
        etiket = [M['damla_g']]
    notu = {'sizinti': M['not'], 'sizinti_ince': M['not_ince']}.get(tur, M['not_damla'])
    for i, t in enumerate(zaman):
        ham = Image.open(f'{klasor}/ham_{i:04d}.png').convert('RGB')
        k = Image.new('RGB', (GEN, YUK), ARKA8)
        k.paste(ham, (0, UST))
        c = ImageDraw.Draw(k)
        c.text((36, UST // 2), baslik, font=f_bas, fill=(240, 240, 240), anchor='lm')
        ts = f't = {t:.2f} s'.replace('.', M['ondalik'])
        c.text((GEN - 36, UST // 2), ts, font=f_t, fill=(255, 213, 79), anchor='rm')
        c.line([(0, UST - 1), (GEN, UST - 1)], fill=(60, 66, 80), width=2)
        gw = GEN // n_gorunum
        for j, e in enumerate(etiket):
            c.text((j * gw + 36, UST + 22), e, font=f_g, fill=(230, 230, 230), anchor='lt')
        if n_gorunum == 2:
            c.line([(gw, UST), (gw, YUK - ALT)], fill=(60, 66, 80), width=2)
        f_c = ImageFont.truetype(FONT, 22)
        for x in CUBUK_X[tur]:
            renk_cubugu(c, x, UST + 130, YUK - ALT - 80, f_c)
        c.line([(0, YUK - ALT), (GEN, YUK - ALT)], fill=(60, 66, 80), width=2)
        c.text((GEN // 2, YUK - ALT // 2), notu, font=f_not, fill=(239, 154, 154), anchor='mm')
        k.save(f'{klasor}/{dil}_{i:04d}.png', compress_level=1)


def mp4(klasor, onek, cikti):
    r = subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', f'{klasor}/{onek}_%04d.png',
                        '-c:v', 'libx264', '-preset', 'slow', '-crf', '20', '-pix_fmt', 'yuv420p',
                        '-profile:v', 'high', '-level', '4.1', '-movflags', '+faststart', cikti],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f'ffmpeg başarısız: {r.stderr[-800:]}')
    print(f'  -> {cikti}  ({os.path.getsize(cikti) / 1e6:.2f} MB)', flush=True)


def uret(tur):
    if shutil.which('ffmpeg') is None:
        raise SystemExit('ffmpeg yok:  sudo apt install ffmpeg')
    klasor = f'{CIK}/_video_{tur}'
    if os.path.exists(klasor):
        shutil.rmtree(klasor)
    try:
        print(f'{tur}: sahne kuruluyor', flush=True)
        if tur == 'sizinti_ince':
            os.environ['PV_KOK'] = f'{KOK}/of_kosular/sizinti3d_ince'
            os.environ['PV_KESIT_Z'] = '0.001'
        gorunumler, layout, zaman = sahne_sizinti() if tur.startswith('sizinti') else sahne_tek_damla()
        print(f'{tur}: {len(zaman)} zaman adımı çiziliyor ({zaman[0]}–{zaman[-1]} s)', flush=True)
        kareleri_ciz(gorunumler, layout, zaman, klasor)
        ad = {'sizinti': 'sizinti_uzay_mars', 'sizinti_ince': 'sizinti_ince_uzay_mars'}.get(tur, 'tek_damla')
        for dil in ('tr', 'en'):
            yazilari_ekle(klasor, zaman, tur, dil, len(gorunumler))
            mp4(klasor, dil, f'{CIK}/{ad}{"" if dil == "tr" else "_en"}.mp4')
        # kontrol için ortadaki karenin TR hali korunur
        orta = len(zaman) // 2
        shutil.copy(f'{klasor}/tr_{orta:04d}.png', f'{CIK}/ekran/video_{ad}_kare.png')
    finally:
        if not os.environ.get('PV_VIDEO_TUT'):
            shutil.rmtree(klasor, ignore_errors=True)


if __name__ == '__main__':
    turler = [a for a in sys.argv[1:] if not a.startswith('-')] or ['sizinti', 'tek_damla']
    if len(turler) == 1:
        uret(turler[0])
    else:                                  # her sahne temiz bir ParaView oturumunda
        pv = shutil.which('pvpython') or 'pvpython'
        for tur in turler:
            rc = subprocess.run([pv, '--force-offscreen-rendering', os.path.abspath(__file__), tur]).returncode
            if rc != 0:
                raise SystemExit(f'{tur}: pvpython çıkış {rc}')
