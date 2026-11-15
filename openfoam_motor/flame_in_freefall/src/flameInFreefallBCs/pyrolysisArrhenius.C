/*---------------------------------------------------------------------------*\
    pyrolysisArrhenius.C — m_dot_max cap eklenmis
\*---------------------------------------------------------------------------*/

#include "pyrolysisArrhenius.H"
#include "volFields.H"
#include "calculatedFvPatchFields.H"

namespace Foam
{
namespace flameInFreefall
{

const IOdictionary& pyrolysisDict(const fvMesh& mesh)
{
    if (!mesh.foundObject<IOdictionary>("pyrolysisProperties"))
    {
        mesh.objectRegistry::store
        (
            new IOdictionary
            (
                IOobject
                (
                    "pyrolysisProperties",
                    mesh.time().constant(),
                    mesh,
                    IOobject::MUST_READ_IF_MODIFIED,
                    IOobject::NO_WRITE
                )
            )
        );
    }
    return mesh.lookupObject<IOdictionary>("pyrolysisProperties");
}


pyrolysisParams readPyrolysisDict(const dictionary& dict)
{
    pyrolysisParams p;
    p.A           = dict.lookup<scalar>("A");
    p.E           = dict.lookup<scalar>("E");
    p.n           = dict.lookup<scalar>("n");
    p.L_pyrolysis = dict.lookup<scalar>("L_pyrolysis");
    p.fuelSpecies = dict.lookup<word>("fuelSpecies");
    p.rho_s_ref   = dict.lookup<scalar>("rho_s_ref")  * 1e-3;
    p.rho_s_init  = dict.lookup<scalar>("rho_s_init") * 1e-3;
    // cap: dosyada yoksa pratik olarak sinir yok (1e10)
    p.m_dot_max   = dict.lookupOrDefault<scalar>("m_dot_max", 1e10);
    p.yuzeyPayi   = dict.lookupOrDefault<scalar>("yuzeyPayi", 1.0);
    return p;
}


scalar arrheniusRate(scalar T, scalar rho_s, const pyrolysisParams& p)
{
    static const scalar R = 8.314;
    if (rho_s <= 0 || T <= small)
    {
        return 0;
    }
    const scalar mdot =
        p.A*rho_s
       *Foam::exp(-p.E/(R*T))
       *Foam::pow(rho_s/p.rho_s_ref, p.n - 1);
    return min(mdot, p.m_dot_max);
}


void updateRhoS(scalarField& rho_s, const scalarField& m_dot, scalar deltaT)
{
    forAll(rho_s, i)
    {
        rho_s[i] = max(scalar(0), rho_s[i] - m_dot[i]*deltaT);
    }
}


volScalarField& rhoSField(const fvMesh& mesh)
{
    if (!mesh.foundObject<volScalarField>("rho_s"))
    {
        const pyrolysisParams p = readPyrolysisDict(pyrolysisDict(mesh));
        mesh.objectRegistry::store
        (
            new volScalarField
            (
                IOobject
                (
                    "rho_s",
                    mesh.time().name(),
                    mesh,
                    IOobject::READ_IF_PRESENT,
                    IOobject::AUTO_WRITE
                ),
                mesh,
                dimensionedScalar
                (
                    "rho_s_init",
                    dimensionSet(1, -2, 0, 0, 0, 0, 0),
                    p.rho_s_init
                ),
                calculatedFvPatchScalarField::typeName
            )
        );
    }
    return mesh.lookupObjectRef<volScalarField>("rho_s");
}


} // namespace flameInFreefall
} // namespace Foam
