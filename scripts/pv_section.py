from paraview.simple import *
import os
# PV_KOK / PV_KESIT_Z: ince 3B yarım alan koşusu için (of_kosular/sizinti3d_ince, kesit z = 1 mm; z = 0 simetri sınırı)
kok = os.environ.get('PV_KOK', os.path.expanduser('~/nasaspaceapp/of_kosular/sizinti'))
KESIT_Z = float(os.environ.get('PV_KESIT_Z', '0'))
DAMLA_BUYUTME = 20   # damlalar 20-100 um; 200 mm kabinde gercek boyutta gorunmez -> capla orantili, 20 kat buyuk
v1 = GetActiveViewOrCreate('RenderView')
layout = GetLayout(v1)
layout.SplitHorizontal(0, 0.5)
v2 = CreateView('RenderView')
AssignViewToLayout(view=v2, layout=layout, hint=2)
T_ARALIK = (300.0, 2900.0)   # iki gorunumde de sabit sicaklik olcegi (K)


def olcek_sabitle():
    """ColorBy olcegi veriye gore yeniden ayarlar; bu yuzden her ColorBy'dan SONRA cagrilir.
    'Never': zaman degisince de yeniden ayarlanmaz."""
    lut = GetColorTransferFunction('T')
    pwf = GetOpacityTransferFunction('T')
    lut.ApplyPreset('Inferno (matplotlib)', True)
    lut.AutomaticRescaleRangeMode = 'Never'
    lut.RescaleTransferFunction(*T_ARALIK)
    pwf.RescaleTransferFunction(*T_ARALIK)
    return lut


for ad, v, baslik in (('uzay', v1, 'UZAY  g = 0'), ('mars', v2, 'MARS  g = 3,73 m/s2')):
    dosya = f'{kok}/{ad}/{ad}.foam'
    r = OpenFOAMReader(registrationName=ad, FileName=dosya)
    r.CaseType = 'Decomposed Case'
    r.MeshRegions = ['internalMesh']
    r.UpdatePipelineInformation()
    s = Slice(registrationName=ad + '_kesit', Input=r)
    s.SliceType = 'Plane'
    s.SliceType.Origin = [0, 0, KESIT_Z]
    s.SliceType.Normal = [0, 0, 1]
    d = Show(s, v)
    ColorBy(d, ('POINTS', 'T'))
    olcek_sabitle()
    d.SetScalarBarVisibility(v, True)
    # buharlasmis yakit: kontur cizgileri
    yakit = [a for a in r.CellArrays.Available if 'C7H16' in a.upper()]
    if yakit:
        k = Contour(registrationName=ad + '_yakit', Input=s)
        k.ContourBy = ['POINTS', yakit[0]]
        k.Isosurfaces = [0.01, 0.05, 0.1, 0.2]
        kd = Show(k, v)
        ColorBy(kd, None)
        kd.AmbientColor = kd.DiffuseColor = [0.2, 1.0, 0.3]
        kd.LineWidth = 2
    else:
        print('Yakit alani bulunamadi:', list(r.CellArrays.Available))
    # damlalar: OpenFOAM okuyucusu lagrangian bölgesini veriyorsa onu, yoksa scripts/droplet_vtk.py'nin
    # yazdığı damla.vtp.series zaman serisini kullan (ParaView 5.11 OpenFOAM 14 bulutunu okuyamıyor)
    rl = OpenFOAMReader(registrationName=ad + '_damla', FileName=dosya)
    rl.CaseType = 'Decomposed Case'
    rl.UpdatePipelineInformation()
    lag = [m for m in rl.MeshRegions.Available if m.lower().startswith('lagrangian')]
    seri = f'{kok}/{ad}/droplet_vtk/damla.vtp.series'
    if lag:
        rl.MeshRegions = lag
        dkaynak = rl
    elif os.path.exists(seri):
        Delete(rl)
        dkaynak = XMLPolyDataReader(registrationName=ad + '_damla_vtp', FileName=[seri])
        dkaynak.PointArrayStatus = ['d', 'T']
    else:
        Delete(rl)
        dkaynak = None
        print('Damla verisi yok: lagrangian bolgesi bulunamadi ve', seri, 'yok (python3 scripts/droplet_vtk.py calistir)')
    if dkaynak is not None:
        dd = Show(dkaynak, v)
        dd.SetRepresentationType('Point Gaussian')
        dd.ColorArrayName = ['POINTS', '']                       # tek renk
        dd.AmbientColor = dd.DiffuseColor = [0.6, 0.9, 1.0]      # acik mavi
        dd.ShaderPreset = 'Sphere'
        dd.ScaleByArray = 1                                      # yaricap = GaussianRadius * d
        dd.SetScaleArray = ['POINTS', 'd']
        dd.UseScaleFunction = 0
        dd.GaussianRadius = 0.5 * DAMLA_BUYUTME                  # 0,5 = gercek boyut (d capi)
    y = Text(registrationName=ad + '_yazi')
    y.Text = baslik
    Show(y, v).FontSize = 20
    v.CameraPosition = [0, 0, 1]
    v.CameraFocalPoint = [0, 0, 0]
    v.CameraViewUp = [0, 1, 0]
    v.ResetCamera()
AddCameraLink(v1, v2, 'kamera')
sahne = GetAnimationScene()
sahne.UpdateAnimationUsingDataTimeSteps()
olcek_sabitle()
sahne.AnimationTime = 0.15
Render(v1); Render(v2)
