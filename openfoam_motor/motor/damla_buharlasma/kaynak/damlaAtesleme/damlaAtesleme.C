/*---------------------------------------------------------------------------*\
    damlaAtesleme — bkz. .H
\*---------------------------------------------------------------------------*/

#include "damlaAtesleme.H"
#include "basicThermo.H"
#include "physicalProperties.H"
#include "fvMatrices.H"
#include "addToRunTimeSelectionTable.H"

namespace Foam
{
namespace fv
{
    defineTypeNameAndDebug(damlaAtesleme, 0);
    addToRunTimeSelectionTable(fvModel, damlaAtesleme, dictionary);
}
}


void Foam::fv::damlaAtesleme::readCoeffs(const dictionary& dict)
{
    tAtes_ = dict.lookup<scalar>("tAtes");
    TAtes_ = dict.lookup<scalar>("TAtes");
    rAtes_ = dict.lookup<scalar>("rAtes");
    wAtes_ = dict.lookup<scalar>("wAtes");
    tau_ = dict.lookup<scalar>("tau");
    merkez_ = dict.lookupOrDefault<vector>("merkez", Zero);
}


Foam::fv::damlaAtesleme::damlaAtesleme
(
    const word& name,
    const word& modelType,
    const fvMesh& mesh,
    const dictionary& dict
)
:
    fvModel(name, modelType, mesh, dict),
    tAtes_(0), TAtes_(0), rAtes_(0), wAtes_(1), tau_(1), merkez_(Zero)
{
    readCoeffs(coeffs(dict));
}


Foam::wordList Foam::fv::damlaAtesleme::addSupFields() const
{
    const basicThermo& thermo =
        mesh().lookupObject<basicThermo>(physicalProperties::typeName);
    return wordList(1, thermo.he().name());
}


void Foam::fv::damlaAtesleme::addSup
(
    const volScalarField& rho,
    const volScalarField& he,
    fvMatrix<scalar>& eqn
) const
{
    if (mesh().time().value() >= tAtes_)
    {
        return;
    }

    const basicThermo& thermo =
        mesh().lookupObject<basicThermo>(physicalProperties::typeName);
    const scalarField& T = thermo.T().primitiveField();
    const tmp<volScalarField> tCp(thermo.Cp());
    const scalarField& Cp = tCp().primitiveField();
    const scalarField& V = mesh().V();
    const vectorField& C = mesh().C().primitiveField();

    scalarField& src = eqn.source();
    forAll(src, c)
    {
        const scalar prof = exp(-sqr((mag(C[c] - merkez_) - rAtes_)/wAtes_));
        const scalar q =
            rho[c]*Cp[c]*max(TAtes_ - T[c], scalar(0))/tau_*prof;  // W/m3
        src[c] -= V[c]*q;     // fvMatrix kaynak işareti: -= ısı ekler
    }
}


bool Foam::fv::damlaAtesleme::read(const dictionary& dict)
{
    if (fvModel::read(dict))
    {
        readCoeffs(coeffs(dict));
        return true;
    }
    return false;
}
