"""
scripts/pv_3b_video.py — scripts/pv_3b.py sahnesinden (aynalanmış tam kabin, 1200 K sarı yarı saydam + 2400 K kırmızı yüzey,
kabin çerçevesi, damlalar; uzay solda, Mars sağda, kameralar bağlı) 3B video üretir.

Çalıştırma (ekransız):
    pvpython --force-offscreen-rendering scripts/pv_3b_video.py

- 1920x1080, 10 kare/s, sahnedeki tüm zaman adımları (damla serisi 0,01 s aralıklı: 101 kare).
  İnce koşuda sıcaklık alanı yalnız 20 zamanda saklandı (0, 0,05, 0,11 … 1 s): her karede yazılmış EN YAKIN
  alan zamanı gösterilir ve ekranda "sıcaklık alanı: t = …" diye yazılır; damlalar her karede kendi zamanında.
- Kamera çapraz perspektif; video boyunca kabinin etrafında ~90° döner (iki görünüm aynı kamera).
- Başlık, zaman, görünüm adları, eş-yüzey açıklaması, ilk 0,03 s'de "tutuşturucu" etiketi ve alt not PIL ile
  (TR ve EN ayrı); ffmpeg H.264 / yuv420p.
- Çıktı: of_visual/sizinti_ince_3b.mp4, of_visual/sizinti_ince_3b_en.mp4; ara PNG'ler silinir
  (PV_VIDEO_TUT=1 ise kalır). Kontrol karesi: of_visual/screen/video_leak_thin_3b_frame.png
"""
import math
import os
import shutil
import subprocess

from paraview.simple import *
from PIL import Image, ImageDraw, ImageFont

KOK = os.path.expanduser('~/nasaspaceapp')
CIK = f'{KOK}/of_gorsel'
GEN, YUK = 1920, 1080
UST, ALT = 96, 52
GOR_Y = YUK - UST - ALT                # ParaView görüntü yüksekliği (px)
FPS = 10
ARKA = (0.075, 0.085, 0.11)
ARKA8 = tuple(int(255 * c) for c in ARKA)
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_K = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
TUTUSTURUCU = (0.0, 0.020, 0.0)        # m (scripts/of_leak3d.py: z = 0 simetri düzleminde)
TUTUS_SURE = 0.03                      # s: etiket bu süreye kadar
MERKEZ = (0.0, 0.0, 0.0)
UZAKLIK = 0.76                         # m (kabin ±0,1 m küp; 30° görüş açısı; çapraz açıda yakın köşe sığsın)
YUKSELIS = 24.0                        # derece
AZ0, AZ1 = 40.0, -50.0                 # derece: +x+z köşegeninden ~90° dönüş

METIN = {
    'tr': {'baslik': 'Kabinde n-heptan sızıntısı: Uzay vs Mars (3B)',
           'uzay': 'Uzay  (g = 0)', 'mars': 'Mars  (g = 3,73 m/s²)',
           'sari': 'sarı: 1200 K', 'kirmizi': 'kırmızı: 2400 K', 'damla': 'mavi: yakıt damlaları',
           'alan': 'sıcaklık alanı: t = {} s', 'tutus': 'tutuşturucu',
           'not': 'OpenFOAM, 2,5 mm ızgara — GÖSTERİM, deney verisiyle doğrulanmadı', 'ondalik': ','},
    'en': {'baslik': 'n-Heptane leak in a cabin: Space vs Mars (3D)',
           'uzay': 'Space  (g = 0)', 'mars': 'Mars  (g = 3.73 m/s²)',
           'sari': 'yellow: 1200 K', 'kirmizi': 'red: 2400 K', 'damla': 'blue: fuel droplets',
           'alan': 'temperature field: t = {} s', 'tutus': 'igniter',
           'not': 'OpenFOAM, 2.5 mm grid — DEMONSTRATION, not validated against experimental data', 'ondalik': '.'},
}


def kamera(i, n):
    az = math.radians(AZ0 + (AZ1 - AZ0) * (i / max(n - 1, 1)))
    el = math.radians(YUKSELIS)
    return [MERKEZ[0] + UZAKLIK * math.cos(el) * math.sin(az),
            MERKEZ[1] + UZAKLIK * math.sin(el),
            MERKEZ[2] + UZAKLIK * math.cos(el) * math.cos(az)]


def izdusum(X, P, F, aci, w, h):
    """Dünya noktası -> görünüm pikseli (VTK perspektif kamerası, yukarı = +y, dikey görüş açısı)."""
    sub = lambda a, b: [a[k] - b[k] for k in range(3)]
    dot = lambda a, b: sum(a[k] * b[k] for k in range(3))
    crs = lambda a, b: [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
    nrm = lambda a: [x / math.sqrt(dot(a, a)) for x in a]
    d = nrm(sub(F, P))
    r = nrm(crs(d, [0, 1, 0]))
    u = crs(r, d)
    q = sub(X, P)
    z = dot(q, d)
    t = math.tan(math.radians(aci) / 2)
    return (w / 2 * (1 + dot(q, r) / (z * t * w / h)), h / 2 * (1 - dot(q, u) / (z * t)))


def sahne():
    ns = {}
    exec(open(f'{KOK}/pv_3b.py').read(), ns)
    v1, v2, layout = ns['v1'], ns['v2'], ns['layout']
    for ad in ('uzay', 'mars'):                    # görünüm yazıları PIL ile (iki dil)
        y = FindSource(ad + '_yazi')
        if y:
            for v in (v1, v2):
                Hide(y, v)
    isaret = Sphere(registrationName='tutusturucu', Center=list(TUTUSTURUCU), Radius=0.004,
                    ThetaResolution=24, PhiResolution=12)
    gos = []
    for v in (v1, v2):
        d = Show(isaret, v)
        d.ColorArrayName = ['POINTS', '']
        d.AmbientColor = d.DiffuseColor = [0.3, 1.0, 0.4]
        gos.append(d)
        try:
            v.UseColorPaletteForBackground = 0
        except AttributeError:
            pass
        v.Background = list(ARKA)
        v.OrientationAxesVisibility = 0
        v.CameraParallelProjection = 0
    Render(v1)
    Render(v2)
    zaman = list(GetTimeKeeper().TimestepValues)
    alan_z = list(FindSource('uzay').TimestepValues)
    return [v1, v2], layout, zaman, alan_z, gos


def kareleri_ciz(gor, layout, zaman, gos, klasor):
    sahne_ = GetAnimationScene()
    sahne_.PlayMode = 'Snap To TimeSteps'
    os.makedirs(klasor, exist_ok=True)
    kam = []
    for i, t in enumerate(zaman):
        sahne_.AnimationTime = t
        P = kamera(i, len(zaman))
        for d in gos:
            d.Visibility = 1 if t <= TUTUS_SURE + 1e-9 else 0
        # yeni veriyle ilk çizim kamerayı sıfırlayabiliyor: önce çiz, sonra kamerayı (yeniden) ayarla
        for adim in range(2):
            for v in gor:
                v.CameraPosition = P
                v.CameraFocalPoint = list(MERKEZ)
                v.CameraViewUp = [0, 1, 0]
                v.CameraViewAngle = 30
            if adim == 0:
                for v in gor:
                    Render(v)
        SaveScreenshot(f'{klasor}/ham_{i:04d}.png', layout, ImageResolution=[GEN, GOR_Y],
                       OverrideColorPalette='', TransparentBackground=0)
        kam.append(P)
        if i % 20 == 0:
            print(f'  kare {i + 1}/{len(zaman)}  t = {t:.3f} s', flush=True)
    return kam


def yazilari_ekle(klasor, zaman, alan_z, kam, dil):
    M = METIN[dil]
    f_bas = ImageFont.truetype(FONT_K, 40)
    f_t = ImageFont.truetype(FONT_K, 38)
    f_g = ImageFont.truetype(FONT_K, 28)
    f_k = ImageFont.truetype(FONT, 22)
    f_e = ImageFont.truetype(FONT_K, 24)
    sayi = lambda x: f'{x:.2f}'.replace('.', M['ondalik'])
    gw = GEN // 2
    for i, t in enumerate(zaman):
        ham = Image.open(f'{klasor}/ham_{i:04d}.png').convert('RGB')
        k = Image.new('RGB', (GEN, YUK), ARKA8)
        k.paste(ham, (0, UST))
        c = ImageDraw.Draw(k)
        c.text((36, UST // 2), M['baslik'], font=f_bas, fill=(240, 240, 240), anchor='lm')
        c.text((GEN - 36, UST // 2 - 10), f't = {sayi(t)} s', font=f_t, fill=(255, 213, 79), anchor='rm')
        ta = min(alan_z, key=lambda a: abs(a - t))          # OpenFOAM okuyucusu en yakın yazılmış zamanı verir
        c.text((GEN - 36, UST - 12), M['alan'].format(sayi(ta)), font=f_k, fill=(170, 175, 190), anchor='rb')
        c.line([(0, UST - 1), (GEN, UST - 1)], fill=(60, 66, 80), width=2)
        c.line([(gw, UST), (gw, YUK - ALT)], fill=(60, 66, 80), width=2)
        for j, e in enumerate((M['uzay'], M['mars'])):
            c.text((j * gw + 36, UST + 22), e, font=f_g, fill=(230, 230, 230), anchor='lt')
            # eş-yüzey açıklaması (her görünümün sol altında)
            x, y = j * gw + 36, YUK - ALT - 40
            for renk, yazi in (((255, 217, 51), M['sari']), ((230, 26, 13), M['kirmizi']),
                               ((153, 230, 255), M['damla'])):
                c.rectangle([x, y - 10, x + 20, y + 10], fill=renk)
                c.text((x + 30, y), yazi, font=f_k, fill=(225, 225, 225), anchor='lm')
                x += 60 + c.textlength(yazi, font=f_k)
            if t <= TUTUS_SURE + 1e-9:
                px, py = izdusum(TUTUSTURUCU, kam[i], MERKEZ, 30, gw, GOR_Y)
                px, py = j * gw + px, UST + py
                lx, ly = px + 90, py - 70
                c.line([(px + 6, py - 5), (lx, ly)], fill=(77, 255, 102), width=3)
                c.text((lx + 6, ly), M['tutus'], font=f_e, fill=(77, 255, 102), anchor='lm')
        c.line([(0, YUK - ALT), (GEN, YUK - ALT)], fill=(60, 66, 80), width=2)
        c.text((GEN // 2, YUK - ALT // 2), M['not'], font=f_k, fill=(239, 154, 154), anchor='mm')
        k.save(f'{klasor}/{dil}_{i:04d}.png', compress_level=1)


def mp4(klasor, onek, cikti):
    r = subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', f'{klasor}/{onek}_%04d.png',
                        '-c:v', 'libx264', '-preset', 'slow', '-crf', '20', '-pix_fmt', 'yuv420p',
                        '-profile:v', 'high', '-level', '4.1', '-movflags', '+faststart', cikti],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f'ffmpeg başarısız: {r.stderr[-800:]}')
    print(f'  -> {cikti}  ({os.path.getsize(cikti) / 1e6:.2f} MB)', flush=True)


def uret():
    if shutil.which('ffmpeg') is None:
        raise SystemExit('ffmpeg yok:  sudo apt install ffmpeg')
    klasor = f'{CIK}/_video_3b'
    if os.path.exists(klasor):
        shutil.rmtree(klasor)
    try:
        print('3b: sahne kuruluyor', flush=True)
        gor, layout, zaman, alan_z, gos = sahne()
        print(f'3b: {len(zaman)} zaman adımı ({zaman[0]}–{zaman[-1]} s), {len(alan_z)} alan zamanı', flush=True)
        kam = kareleri_ciz(gor, layout, zaman, gos, klasor)
        for dil in ('tr', 'en'):
            yazilari_ekle(klasor, zaman, alan_z, kam, dil)
            mp4(klasor, dil, f'{CIK}/sizinti_ince_3b{"" if dil == "tr" else "_en"}.mp4')
        os.makedirs(f'{CIK}/ekran', exist_ok=True)
        for i, ek in ((1, '_tutus'), (len(zaman) // 2, '')):
            shutil.copy(f'{klasor}/tr_{i:04d}.png', f'{CIK}/ekran/video_sizinti_ince_3b{ek}_kare.png')
    finally:
        if not os.environ.get('PV_VIDEO_TUT'):
            shutil.rmtree(klasor, ignore_errors=True)


if __name__ == '__main__':
    uret()
