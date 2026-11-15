/*---------------------------------------------------------------------------*\
    damlaIzgaraHareketi — damla çevresindeki ağı r_s'ye göre radyal küçültür
    (1B piramit dilim, 2D kama, 3D küre kabuğu: hepsi aynı kural)

    Her nokta için merkeze uzaklık rho0 = |p0 - c|, iç yarıçap ri0 = min rho0,
    xi = (rho0 - ri0)/(R - ri0). Ölçek s = r_s/r_s0 (r_s0 = d0/2):
        rho = s ri0 + (R - s ri0) xi,   p = c + (p0 - c) rho/rho0
    rho0 >= R olan noktalar kıpırdamaz (kutu alanlarda dış bölge sabit).
    1B piramitte ri0 = r_s0 sqrt(1 + 2 t^2) olduğundan ölçek oranı kullanılır;
    küre yüzeyinde ri0 = r_s0.

    r_s = rsDamla (damlaBuharlasma), bir adım gecikmeli (SPEC §3, §6.7).
    Kalıp: inkJet_fvMeshMover.C

    Girdi (constant/<bölge>/dynamicMeshDict):
        mover
        {
            type    damlaIzgaraHareketi;
            libs    ("libFlameInFreefallDroplet.so");
            d0      0.001;          // başlangıç çapı (fvModels ile aynı)
            merkez  (0 0 0);        // isteğe bağlı, varsayılan orijin
            R       0.03;           // isteğe bağlı, varsayılan en uzak nokta
        }
\*---------------------------------------------------------------------------*/

#ifndef damlaIzgaraHareketi_H
#define damlaIzgaraHareketi_H

#include "fvMeshMover.H"
#include "pointIOField.H"

namespace Foam
{
namespace fvMeshMovers
{

class damlaIzgaraHareketi
:
    public fvMeshMover
{
    pointIOField p0_;
    vector merkez_;
    scalar rs0_;
    scalarField rho0_;
    scalar ri0_;
    scalar R_;

public:

    TypeName("damlaIzgaraHareketi");

    damlaIzgaraHareketi(fvMesh& mesh, const dictionary& dict);

    damlaIzgaraHareketi(const damlaIzgaraHareketi&) = delete;

    virtual ~damlaIzgaraHareketi() {}

    virtual bool update();

    virtual void topoChange(const polyTopoChangeMap&) { NotImplemented; }
    virtual void mapMesh(const polyMeshMap&) { NotImplemented; }
    virtual void distribute(const polyDistributionMap&) { NotImplemented; }

    void operator=(const damlaIzgaraHareketi&) = delete;
};

} // namespace fvMeshMovers
} // namespace Foam

#endif
