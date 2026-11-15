/*---------------------------------------------------------------------------*\
    damlaIzgaraHareketi — bkz. .H
\*---------------------------------------------------------------------------*/

#include "damlaIzgaraHareketi.H"
#include "uniformDimensionedFields.H"
#include "addToRunTimeSelectionTable.H"

namespace Foam
{
namespace fvMeshMovers
{
    defineTypeNameAndDebug(damlaIzgaraHareketi, 0);
    addToRunTimeSelectionTable(fvMeshMover, damlaIzgaraHareketi, fvMesh);
}
}


Foam::fvMeshMovers::damlaIzgaraHareketi::damlaIzgaraHareketi
(
    fvMesh& mesh,
    const dictionary& dict
)
:
    fvMeshMover(mesh),
    p0_
    (
        IOobject
        (
            "points",
            mesh.time().constant(),
            fvMesh::meshSubDir,
            mesh,
            IOobject::MUST_READ,
            IOobject::NO_WRITE
        )
    ),
    merkez_(dict.lookupOrDefault<vector>("merkez", Zero)),
    rs0_(0.5*dict.lookup<scalar>("d0")),
    rho0_(mag(p0_ - merkez_)),
    ri0_(gMin(rho0_)),
    R_(dict.lookupOrDefault<scalar>("R", gMax(rho0_)))
{
    if (ri0_ <= 0 || R_ <= ri0_)
    {
        FatalIOErrorInFunction(dict)
            << "gecersiz geometri: ic yaricap " << ri0_ << ", R " << R_
            << " (merkez " << merkez_ << ")" << exit(FatalIOError);
    }

    Info<< "damlaIzgaraHareketi: merkez " << merkez_ << ", ic yaricap "
        << ri0_ << ", R " << R_ << ", r_s0 " << rs0_ << endl;
}


bool Foam::fvMeshMovers::damlaIzgaraHareketi::update()
{
    if (!mesh().foundObject<uniformDimensionedScalarField>("rsDamla"))
    {
        return false;
    }

    const scalar s =
        mesh().lookupObject<uniformDimensionedScalarField>("rsDamla").value()
       /rs0_;
    const scalar ri = s*ri0_;

    pointField p(p0_);
    forAll(p, i)
    {
        if (rho0_[i] < R_)
        {
            const scalar xi = (rho0_[i] - ri0_)/(R_ - ri0_);
            const scalar rho = ri + (R_ - ri)*xi;
            p[i] = merkez_ + (p0_[i] - merkez_)*(rho/rho0_[i]);
        }
    }

    mesh().movePoints(p);

    return true;
}
