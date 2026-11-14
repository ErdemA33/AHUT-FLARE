#!/usr/bin/env python3
"""Kati-bolge vakasinin bolge dosyalarini yazar (0/, constant/, system/). Tek kaynak: bu script."""
from pathlib import Path
T0 = 294.32
HDR = lambda cls, loc, obj: f'FoamFile {{ format ascii; class {cls}; location "{loc}"; object {obj}; }}\n'

def yaz(p, s):
    Path(p).parent.mkdir(parents=True, exist_ok=True); Path(p).write_text(s)

# ---------------- constant ----------------
yaz("constant/fluid/fvModels", HDR("dictionary", "constant/fluid", "fvModels") + """
// OF14: radyasyon bir fvModel olarak acilir (radiationProperties tek basina yetmez)
radiation
{
    type    radiation;
    libs    ("libradiationModels.so");
}
""")
yaz("constant/fluid/fvConstraints", HDR("dictionary", "constant/fluid", "fvConstraints") + """
limitY
{
    type            limitFields;
    fields          (CH4 O2 CO2 H2O N2 CO);
    min             0;
    max             1;
    selectionMode   all;
}
// limitTemperature yok: enerjiyi kesmesin (sonuclar fiziksel sinirlarla raporda kontrol edilir)
""")
yaz("constant/sibal/physicalProperties", HDR("dictionary", "constant/sibal", "physicalProperties") + """
// SIBAL (75% pamuk / 25% cam elyaf), 0.32 mm, 18.2 mg/cm2
// rho = 0.182 kg/m2 / 0.32e-3 m = 568.75 kg/m3 (Li & Liao 2018: 573)
// Cv baslangic = (142.1875*700 + 426.5625*1260)/568.75 = 1120 J/kgK (Olson; sibalPyrolysis gunceller)
// kappa = alpha*rho*Cs = 9.6e-8*573*1255 = 0.06904 W/mK (Li & Liao 2018 Tablo 2)
thermoType constSolidThermo;
rho   { type uniform; value 568.75; }
Cv    { type uniform; value 1120; }
kappa { type uniform; value 0.06904; }
""")
yaz("constant/sibal/fvModels", HDR("dictionary", "constant/sibal", "fvModels") + """
piroliz
{
    type            sibalPyrolysis;
    interfacePatch  sibal_to_fluid;
    // Zhao vd. 2017 Tablo 1 (GPYRO bicimi): w = A rho0 (rho/rho0)^n exp(-E/RT)
    A1      1.626e11;   E1  1.6144e5;   n1  1.035;  rho01  426.5625;   // 0.1365 kg/m2 / 0.32 mm
    A2      2.113e13;   E2  2.4589e5;   n2  2.357;  rho02  76.209375;  // 0.024387 kg/m2 / 0.32 mm
    nu      0.178659;   // ara kati verimi = 2.4387/13.65
    rhoInert 142.1875;  // 0.0455 kg/m2 / 0.32 mm (cam elyaf)
    cpInert  700;       // Olson vd.
    cpComb   1260;      // Olson vd. (pamuk; char icin ayni deger - varsayim)
    XL0      3.0e5;     // Li & Liao 2018 Tablo 2, TL = 300 K
    TL       300;
    cpF      1380;      // Li & Liao 2018 Tablo 2
}
""")
yaz("constant/tel/physicalProperties", HDR("dictionary", "constant/tel", "physicalProperties") + """
// Kanthal A-1 (kanthal.com veri sayfasi): rho 7100; cp 0.46 (20 C) -> 0.74 (1200 C) kJ/kgK
// Cv = 21->1125 C integral ortalamasi 659.6 J/kgK; kappa ayni aralik ortalamasi 19.1 W/mK
// ESDEGER TEL: r = 0.70462 r_gercek (mesh_olustur.py); rho = 7100 x 1.41921 = 10076.37
//   -> birim genislik basina isi kapasitesi gercek tele esit
thermoType constSolidThermo;
rho   { type uniform; value 10076.37; }
Cv    { type uniform; value 659.6; }
kappa { type uniform; value 19.1; }
""")
yaz("constant/tel/fvModels", HDR("dictionary", "constant/tel", "fvModels") + """
// 183 W [Olson/NASA] / 0.406 m = 450.7 W/m; simetrik yarim model x0.5; derinlik 0.01 m -> 2.2535 W
// sure: S1 telemetri 7.986 s
joule
{
    type        heatSource;
    cellZone    all;
    Q
    {
        type    scale;
        scale   table ( (0 1) (7.986 1) (7.987 0) (1000 0) );
        value   constant 2.2535;
    }
}
""")

# ---------------- system ----------------
yaz("system/fvSolution", HDR("dictionary", "system", "fvSolution") + "PIMPLE\n{\n    nOuterCorrectors 1;\n}\n")
solid_schemes = HDR("dictionary", "system/X", "fvSchemes") + """
ddtSchemes { default Euler; }
gradSchemes { default Gauss linear; }
divSchemes { default none; }
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
"""
solid_solution = HDR("dictionary", "system/X", "fvSolution") + """
solvers
{
    "e.*"
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-10;
        relTol          0;
    }
}
PIMPLE { nNonOrthogonalCorrectors 1; }
relaxationFactors { equations { ".*" 1; } }
"""
for r in ("sibal", "tel"):
    yaz(f"system/{r}/fvSchemes", solid_schemes.replace("system/X", f"system/{r}"))
    yaz(f"system/{r}/fvSolution", solid_solution.replace("system/X", f"system/{r}"))
yaz("system/decomposeParDict", HDR("dictionary", "system", "decomposeParDict") + """
numberOfSubdomains 4;
method          scotch;
""")

# ---------------- 0/ ----------------
def alan(reg, ad, boyut, ic, bc, cls="volScalarField"):
    s = HDR(cls, f"0/{reg}", ad) + f"dimensions {boyut};\ninternalField {ic};\nboundaryField\n{{\n"
    s += '    #includeEtc "caseDicts/setConstraintTypes"\n'
    for p, v in bc.items():
        s += f"    {p} {{ {v} }}\n"
    yaz(f"0/{reg}/{ad}", s + "}\n")

Tu = f"uniform {T0}"
# fluid
alan("fluid", "T", "[0 0 0 1 0 0 0]", Tu, {
    "inlet": f"type fixedValue; value {Tu};",
    "outlet": f"type inletOutlet; inletValue {Tu}; value {Tu};",
    "top": "type zeroGradient;", "base": "type zeroGradient;",
    "fluid_to_sibal": f"type coupledTemperature; qr qr; value {Tu};",
    "fluid_to_tel": f"type coupledTemperature; qr qr; value {Tu};"})
alan("fluid", "U", "[0 1 -1 0 0 0 0]", "uniform (0.2453 0 0)", {
    "inlet": "type fixedValue; value uniform (0.2453 0 0);",
    "outlet": "type pressureInletOutletVelocity; value uniform (0.2453 0 0);",
    "top": "type slip;", "base": "type slip;",
    "fluid_to_sibal": "type coupledPyrolysisVelocity; value uniform (0 0 0);",
    "fluid_to_tel": "type noSlip;"}, cls="volVectorField")
alan("fluid", "p", "[1 -1 -2 0 0 0 0]", "uniform 99451", {
    "inlet": "type zeroGradient;", "outlet": "type totalPressure; p0 uniform 99451; value uniform 99451;",
    "top": "type zeroGradient;", "base": "type zeroGradient;",
    "fluid_to_sibal": "type zeroGradient;", "fluid_to_tel": "type zeroGradient;"})
G_bc = lambda e: f"type MarshakRadiation; emissivityMode lookup; emissivity uniform {e}; value uniform 0;"
alan("fluid", "G", "[1 0 -3 0 0 0 0]", "uniform 0", {
    "inlet": G_bc(1.0), "outlet": G_bc(1.0), "top": G_bc(1.0), "base": G_bc(1.0),
    "fluid_to_sibal": G_bc(0.8),     # SIBAL, Olson vd.
    "fluid_to_tel": G_bc(0.7)})      # Kanthal tam oksitlenmis
Y = {"CH4": 0.0, "CO": 0.0, "CO2": 0.006037, "H2O": 0.0072, "O2": 0.235494, "N2": 0.751269}
for sp, y in Y.items():
    fuel = "yes" if sp == "CH4" else "no"
    alan("fluid", sp, "[0 0 0 0 0 0 0]", f"uniform {y}", {
        "inlet": f"type fixedValue; value uniform {y};",
        "outlet": f"type inletOutlet; inletValue uniform {y}; value uniform {y};",
        "top": "type zeroGradient;", "base": "type zeroGradient;",
        "fluid_to_sibal": f"type coupledPyrolysisSpecies; fuel {fuel}; value uniform {y};",
        "fluid_to_tel": "type zeroGradient;"})
alan("fluid", "Ydefault", "[0 0 0 0 0 0 0]", "uniform 0", {
    "inlet": "type fixedValue; value uniform 0;", "outlet": "type inletOutlet; inletValue uniform 0; value uniform 0;",
    "top": "type zeroGradient;", "base": "type zeroGradient;",
    "fluid_to_sibal": "type zeroGradient;", "fluid_to_tel": "type zeroGradient;"})
# sibal
alan("sibal", "T", "[0 0 0 1 0 0 0]", Tu, {
    "sibalUc": "type zeroGradient;",
    "sibal_to_fluid": f"type coupledTemperature; qrNbr qr; value {Tu};",
    "sibal_to_tel": f"type coupledTemperature; value {Tu};"})
# tel
alan("tel", "T", "[0 0 0 1 0 0 0]", Tu, {
    "tel_to_fluid": f"type coupledTemperature; qrNbr qr; value {Tu};",
    "tel_to_sibal": f"type coupledTemperature; value {Tu};"})
print("tamam")
