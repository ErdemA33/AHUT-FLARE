from paraview.simple import *
import os
# GUI'de yeni veri yüklenince varsayılan ayar "ilk zamana git": betik bittikten sonra zamanı 0'a çekiyordu.
try:
    GetSettingsProxy('GeneralSettings').DefaultTimeStep = 'Leave current time unchanged, if possible'
except Exception:
    pass
kok = os.environ.get('PV_KOK', os.path.expanduser('~/nasaspaceapp/of_kosular/sizinti3d_ince'))
v1 = GetActiveViewOrCreate('RenderView')
layout = GetLayout(v1)
layout.SplitHorizontal(0, 0.5)
v2 = CreateView('RenderView')
AssignViewToLayout(view=v2, layout=layout, hint=2)
for ad, v, baslik in (('uzay', v1, 'UZAY  g = 0'), ('mars', v2, 'MARS  g = 3,73 m/s2')):
    r = OpenFOAMReader(registrationName=ad, FileName=f'{kok}/{ad}/{ad}.foam')
    r.CaseType = 'Decomposed Case'
    r.MeshRegions = ['internalMesh']
    r.SkipZeroTime = 0          # 0 s alanı da (yoksa ilk karelerde 0,05 s alevi görünüyordu)
    tam = Reflect(registrationName=ad + '_tam', Input=r)
    tam.Plane = 'Z Min'
    cer = Show(tam, v)
    cer.SetRepresentationType('Outline')
    cer.AmbientColor = cer.DiffuseColor = [1, 1, 1]
    for deger, renk, saydam in ((1200.0, [1.0, 0.85, 0.2], 0.35), (2400.0, [0.9, 0.1, 0.05], 0.9)):
        k = Contour(registrationName=f'{ad}_{int(deger)}K', Input=tam)
        k.ContourBy = ['POINTS', 'T']
        k.Isosurfaces = [deger]
        kd = Show(k, v)
        kd.ColorArrayName = ['POINTS', '']
        kd.AmbientColor = kd.DiffuseColor = renk
        kd.Opacity = saydam
    seri = f'{kok}/{ad}/damla_vtk/damla.vtp.series'
    if os.path.exists(seri):
        dr = OpenDataFile(seri)
        dt = Reflect(registrationName=ad + '_damla', Input=dr)
        dt.Plane = 'Z Min'
        dd = Show(dt, v)
        dd.SetRepresentationType('Point Gaussian')
        dd.GaussianRadius = 0.0012
        dd.ColorArrayName = ['POINTS', '']
        dd.AmbientColor = dd.DiffuseColor = [0.6, 0.9, 1.0]
    y = Text(registrationName=ad + '_yazi')
    y.Text = baslik + '\nsari: 1200 K   kirmizi: 2400 K'
    Show(y, v).FontSize = 18
    v.Background = [0.12, 0.12, 0.16]
    try:
        v.UseColorPaletteForBackground = 0
    except Exception:
        pass
    v.CameraPosition = [0.45, 0.30, 0.45]
    v.CameraFocalPoint = [0, 0, 0]
    v.CameraViewUp = [0, 1, 0]
    v.ResetCamera()
AddCameraLink(v1, v2, 'kamera')
sahne = GetAnimationScene()
sahne.UpdateAnimationUsingDataTimeSteps()
sahne.PlayMode = 'Snap To TimeSteps'
sahne.AnimationTime = 0.5
GetTimeKeeper().Time = 0.5
for v in (v1, v2):
    v.ViewTime = 0.5
Render(v1); Render(v2)
