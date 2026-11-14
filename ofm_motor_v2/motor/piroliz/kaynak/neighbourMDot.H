/*---------------------------------------------------------------------------*\
    neighbourMDot — akiskan aray uz patch'inde, komsu kati bolgenin
    (sibalPyrolysis) mDotPyro [kg/m^2/s] patch degerini esler.
    Komsu alan henuz yoksa (kurulum sirasi) sifir dondurur.
\*---------------------------------------------------------------------------*/
#ifndef neighbourMDot_H
#define neighbourMDot_H

#include "mappedFvPatchBaseBase.H"
#include "volFields.H"

namespace Foam
{
namespace flameInFreefall
{

inline tmp<scalarField> neighbourMDot(const fvPatch& p, const word& name)
{
    const mappedFvPatchBaseBase& mapper = mappedFvPatchBaseBase::getMap(p);
    const fvPatch& nbr = mapper.nbrFvPatch();
    const fvMesh& nbrMesh = nbr.boundaryMesh().mesh();

    if (!nbrMesh.foundObject<volScalarField>(name))
    {
        return tmp<scalarField>(new scalarField(p.size(), 0));
    }
    const scalarField& mN =
        nbrMesh.lookupObject<volScalarField>(name).boundaryField()[nbr.index()];
    return mapper.fromNeighbour(mN);
}

} // namespace flameInFreefall
} // namespace Foam

#endif
