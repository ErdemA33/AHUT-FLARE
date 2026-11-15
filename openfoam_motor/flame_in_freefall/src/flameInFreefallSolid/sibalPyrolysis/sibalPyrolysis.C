/*---------------------------------------------------------------------------*\
    sibalPyrolysis — bkz. sibalPyrolysis.H
\*---------------------------------------------------------------------------*/

#include "sibalPyrolysis.H"
#include "solidThermo.H"
#include "physicalProperties.H"
#include "fvMatrices.H"
#include "fvmSup.H"
#include "calculatedFvPatchFields.H"
#include "addToRunTimeSelectionTable.H"
#include "Pstream.H"

namespace Foam
{
namespace fv
{
    defineTypeNameAndDebug(sibalPyrolysis, 0);
    addToRunTimeSelectionTable(fvModel, sibalPyrolysis, dictionary);
}
}

static const Foam::scalar Ru = 8.3145;   // J/mol/K (Olson vd., Zhao vd.)


// * * * * * * * * * * * * * * Private Functions * * * * * * * * * * * * * * //

void Foam::fv::sibalPyrolysis::readCoeffs(const dictionary& dict)
{
    A1_   = dict.lookup<scalar>("A1");
    E1_   = dict.lookup<scalar>("E1");
    n1_   = dict.lookup<scalar>("n1");
    rho01_= dict.lookup<scalar>("rho01");
    A2_   = dict.lookup<scalar>("A2");
    E2_   = dict.lookup<scalar>("E2");
    n2_   = dict.lookup<scalar>("n2");
    rho02_= dict.lookup<scalar>("rho02");
    nu_   = dict.lookup<scalar>("nu");
    rhoInert_ = dict.lookup<scalar>("rhoInert");
    cpInert_  = dict.lookup<scalar>("cpInert");
    cpComb_   = dict.lookup<scalar>("cpComb");
    XL0_  = dict.lookup<scalar>("XL0");
    TL_   = dict.lookup<scalar>("TL");
    cpF_  = dict.lookup<scalar>("cpF");
    interfacePatchName_ = dict.lookup<word>("interfacePatch");
}


void Foam::fv::sibalPyrolysis::buildColumnMap()
{
    patchi_ = mesh().poly().boundary().findIndex(interfacePatchName_);
    if (patchi_ < 0)
    {
        FatalErrorInFunction
            << "interfacePatch " << interfacePatchName_ << " bulunamadi"
            << exit(FatalError);
    }

    const polyPatch& pp = mesh().poly().boundary()[patchi_];
    const pointField& pts = mesh().points();
    const label nP = Pstream::nProcs();
    const label me = Pstream::myProcNo();

    // Yerel yuz x-araliklari ve merkezleri
    scalarField xmin(pp.size(), great), xmax(pp.size(), -great), fcx(pp.size());
    const vectorField Cf(pp.faceCentres());
    forAll(pp, f)
    {
        const face& fc = pp[f];
        forAll(fc, k)
        {
            xmin[f] = min(xmin[f], pts[fc[k]].x());
            xmax[f] = max(xmax[f], pts[fc[k]].x());
        }
        fcx[f] = Cf[f].x();
    }

    // Tum islemcilerin yuz ve hucre bilgisi (kolon islemci sinirinda
    // bolunse bile esleme global ve deterministik)
    List<scalarField> gxmin(nP), gxmax(nP), gfcx(nP), gcx(nP);
    gxmin[me] = xmin; gxmax[me] = xmax; gfcx[me] = fcx;
    gcx[me] = mesh().C().primitiveField().component(vector::X);
    Pstream::gatherList(gxmin); Pstream::scatterList(gxmin);
    Pstream::gatherList(gxmax); Pstream::scatterList(gxmax);
    Pstream::gatherList(gfcx);  Pstream::scatterList(gfcx);
    Pstream::gatherList(gcx);   Pstream::scatterList(gcx);

    DynamicList<label> sp, sc, df;
    label nAcik = 0, nKapali = 0;

    forAll(gcx, p)
    {
        forAll(gcx[p], i)
        {
            const scalar x = gcx[p][i];
            label bq = -1, bf = -1;
            forAll(gxmin, q)
            {
                forAll(gxmin[q], f)
                {
                    if (x > gxmin[q][f] && x < gxmax[q][f])
                    {
                        bq = q; bf = f; break;
                    }
                }
                if (bq >= 0) break;
            }
            if (bq >= 0)
            {
                ++nAcik;
            }
            else
            {
                // telin altindaki kirisin altinda: global en yakin aray uz yuzu
                scalar dmin = great;
                forAll(gfcx, q)
                {
                    forAll(gfcx[q], f)
                    {
                        const scalar d = mag(gfcx[q][f] - x);
                        if (d < dmin) { dmin = d; bq = q; bf = f; }
                    }
                }
                ++nKapali;
            }
            if (bq < 0)
            {
                FatalErrorInFunction
                    << "hucre (islemci " << p << ", " << i << ") icin "
                    << interfacePatchName_ << " yuzu yok" << exit(FatalError);
            }
            if (bq == me)
            {
                sp.append(p); sc.append(i); df.append(bf);
            }
        }
    }

    srcProc_.transfer(sp);
    srcCell_.transfer(sc);
    dstFace_.transfer(df);

    Info<< "sibalPyrolysis: kolon eslemesi: " << nAcik
        << " hucre dogrudan, " << nKapali
        << " hucre (tel alti) en yakin yuze" << endl;
}


void Foam::fv::sibalPyrolysis::updateThermo() const
{
    solidThermo& thermo = const_cast<solidThermo&>
    (
        mesh().lookupObject<solidThermo>(physicalProperties::typeName)
    );

    volScalarField& rho = thermo.rho();
    volScalarField& Cv = const_cast<volScalarField&>(thermo.Cv());

    forAll(rho, c)
    {
        const scalar mComb = rhoV_[c] + rhoCh_[c];
        rho[c] = rhoInert_ + mComb;
        Cv[c] = (rhoInert_*cpInert_ + mComb*cpComb_)/rho[c];
    }
    forAll(rho.boundaryField(), p)
    {
        rho.boundaryFieldRef()[p] = rho.boundaryField()[p].patchInternalField();
        Cv.boundaryFieldRef()[p] = Cv.boundaryField()[p].patchInternalField();
    }
}


// * * * * * * * * * * * * * * * * Constructor * * * * * * * * * * * * * * * //

Foam::fv::sibalPyrolysis::sibalPyrolysis
(
    const word& name,
    const word& modelType,
    const fvMesh& mesh,
    const dictionary& dict
)
:
    fvModel(name, modelType, mesh, dict),
    A1_(0), E1_(0), n1_(1), rho01_(1), A2_(0), E2_(0), n2_(1), rho02_(1),
    nu_(0), rhoInert_(0), cpInert_(0), cpComb_(0), XL0_(0), TL_(300), cpF_(0),
    interfacePatchName_(),
    rhoV_
    (
        IOobject("rhoV", mesh.time().name(), mesh,
            IOobject::READ_IF_PRESENT, IOobject::AUTO_WRITE),
        mesh,
        dimensionedScalar(dimDensity, coeffs(dict).lookup<scalar>("rho01")),
        calculatedFvPatchScalarField::typeName
    ),
    rhoCh_
    (
        IOobject("rhoCh", mesh.time().name(), mesh,
            IOobject::READ_IF_PRESENT, IOobject::AUTO_WRITE),
        mesh,
        dimensionedScalar(dimDensity, 0),
        calculatedFvPatchScalarField::typeName
    ),
    mDotPyro_
    (
        IOobject("mDotPyro", mesh.time().name(), mesh,
            IOobject::NO_READ, IOobject::AUTO_WRITE),
        mesh,
        dimensionedScalar(dimMass/dimArea/dimTime, 0),
        calculatedFvPatchScalarField::typeName
    ),
    mVap_
    (
        IOobject("mVapPyro", mesh.time().name(), mesh),
        mesh,
        dimensionedScalar(dimDensity/dimTime, 0)
    ),
    rhoV0_(mesh.nCells(), 0),
    rhoCh0_(mesh.nCells(), 0),
    timeIndex_(-1),
    patchi_(-1),
    srcProc_(), srcCell_(), dstFace_()
{
    readCoeffs(coeffs(dict));
    buildColumnMap();
    updateThermo();

    // ddt(rho,e) icin eski zaman degerleri baslangicta dogru olsun
    solidThermo& thermo = const_cast<solidThermo&>
    (
        mesh.lookupObject<solidThermo>(physicalProperties::typeName)
    );
    thermo.rho().oldTime();
    thermo.he().primitiveFieldRef() =
        thermo.Cv().primitiveField()*thermo.T().primitiveField();   // e = Cv T
    thermo.he().oldTime();
}


// * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * //

Foam::wordList Foam::fv::sibalPyrolysis::addSupFields() const
{
    const basicThermo& thermo =
        mesh().lookupObject<basicThermo>(physicalProperties::typeName);
    return wordList(1, thermo.he().name());
}


void Foam::fv::sibalPyrolysis::correct()
{
    const scalar dt = mesh().time().deltaTValue();

    if (timeIndex_ != mesh().time().timeIndex())
    {
        rhoV0_  = rhoV_.primitiveField();
        rhoCh0_ = rhoCh_.primitiveField();
        timeIndex_ = mesh().time().timeIndex();
    }

    const solidThermo& thermo =
        mesh().lookupObject<solidThermo>(physicalProperties::typeName);
    const scalarField& T = thermo.T().primitiveField();

    forAll(T, c)
    {
        const scalar rv = max(rhoV0_[c], scalar(0));
        const scalar rc = max(rhoCh0_[c], scalar(0));

        const scalar w1 =
            A1_*rho01_*pow(rv/rho01_, n1_)*exp(-E1_/(Ru*T[c]));
        const scalar w2 =
            A2_*rho02_*pow(rc/rho02_, n2_)*exp(-E2_/(Ru*T[c]));

        const scalar dv = min(w1*dt, rv);   // fiziksel sinir: mevcut kutle
        const scalar dc = min(w2*dt, rc);

        rhoV_[c]  = rv - dv;
        rhoCh_[c] = rc + nu_*dv - dc;
        mVap_[c]  = ((1 - nu_)*dv + dc)/dt;
    }
    rhoV_.correctBoundaryConditions();
    rhoCh_.correctBoundaryConditions();

    updateThermo();

    // Aray uz kutle akisi
    // Hucre kutle debisi [kg/s] tum islemcilerde; her islemci kendi yuzlerine toplar
    const label nP = Pstream::nProcs();
    List<scalarField> gm(nP);
    gm[Pstream::myProcNo()] = scalarField(mVap_)*scalarField(mesh().V());
    Pstream::gatherList(gm);
    Pstream::scatterList(gm);

    scalarField& mp = mDotPyro_.boundaryFieldRef()[patchi_];
    mp = 0;
    forAll(dstFace_, k)
    {
        mp[dstFace_[k]] += gm[srcProc_[k]][srcCell_[k]];
    }
    mp /= mesh().magSf().boundaryField()[patchi_];
}


void Foam::fv::sibalPyrolysis::addSup
(
    const volScalarField& he,
    fvMatrix<scalar>& eqn
) const
{
    const solidThermo& thermo =
        mesh().lookupObject<solidThermo>(physicalProperties::typeName);
    const scalarField& T = thermo.T().primitiveField();
    const scalarField& Cv = thermo.Cv().primitiveField();
    const scalarField& V = mesh().V();

    // Aciklik: -mVap*XL(T)
    scalarField& src = eqn.source();
    forAll(src, c)
    {
        const scalar XL = XL0_ + (cpF_ - Cv[c])*(T[c] - TL_);
        src[c] += V[c]*mVap_[c]*XL;     // fvMatrix kaynak isareti: -= ekler, += cikarir
    }

    // Ortuk: -mVap*cpComb*T = -(mVap*cpComb/Cv) e
    volScalarField::Internal k
    (
        IOobject("sibalPyrolysis:k", mesh().time().name(), mesh()),
        mesh(),
        dimensionedScalar(dimDensity/dimTime, 0)
    );
    k.primitiveFieldRef() = scalarField(mVap_)*cpComb_/Cv;   // [kg/m^3/s]
    eqn -= fvm::Sp(k, he);
}


void Foam::fv::sibalPyrolysis::addSup
(
    const volScalarField& rho,
    const volScalarField& he,
    fvMatrix<scalar>& eqn
) const
{
    addSup(he, eqn);
}


bool Foam::fv::sibalPyrolysis::read(const dictionary& dict)
{
    if (fvModel::read(dict))
    {
        readCoeffs(coeffs(dict));
        return true;
    }
    return false;
}
