/*---------------------------------------------------------------------------*\
    damlaAtesleme — DM:1342-1344 ateşleme kaynağı (gaz enerji denklemi)

    t < tAtes:  q = rho cp max(TAtes - T, 0)/tau exp(-((r - rAtes)/wAtes)^2)
    r = |hücre merkezi - merkez| (1B/2D/3D; merkez varsayılan orijin). Açık kaynak.

    Girdi: tAtes, TAtes, rAtes, wAtes, tau  (DM:1164 değerleri, vaka_uret.py yazar),
           merkez (x y z) isteğe bağlı
\*---------------------------------------------------------------------------*/

#ifndef damlaAtesleme_H
#define damlaAtesleme_H

#include "fvModel.H"
#include "volFields.H"

namespace Foam
{
namespace fv
{

class damlaAtesleme
:
    public fvModel
{
    scalar tAtes_, TAtes_, rAtes_, wAtes_, tau_;
    vector merkez_;

    void readCoeffs(const dictionary& dict);

public:

    TypeName("damlaAtesleme");

    damlaAtesleme
    (
        const word& name,
        const word& modelType,
        const fvMesh& mesh,
        const dictionary& dict
    );

    virtual ~damlaAtesleme() {}

    virtual wordList addSupFields() const;

    virtual void addSup
    (
        const volScalarField& rho,
        const volScalarField& he,
        fvMatrix<scalar>& eqn
    ) const;

    virtual bool movePoints() { return true; }
    virtual void topoChange(const polyTopoChangeMap&) {}
    virtual void mapMesh(const polyMeshMap&) {}
    virtual void distribute(const polyDistributionMap&) {}

    virtual bool read(const dictionary& dict);
};

} // namespace fv
} // namespace Foam

#endif
