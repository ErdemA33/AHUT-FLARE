/*---------------------------------------------------------------------------*\
    damlaBuharlasma — bkz. damlaBuharlasma.H
    Kalıp: sibalPyrolysis.C (kilitli; burada yeni adla yeniden yazıldı)
\*---------------------------------------------------------------------------*/

#include "damlaBuharlasma.H"
#include "fluidMulticomponentThermo.H"
#include "fluidThermophysicalTransportModel.H"
#include "physicalProperties.H"
#include "surfaceFields.H"
#include "calculatedFvPatchFields.H"
#include "addToRunTimeSelectionTable.H"
#include "OSspecific.H"
#include <cstdio>

// * * * * * * * * * * * * * Static Data Members * * * * * * * * * * * * * * //

namespace Foam
{
namespace fv
{
    defineTypeNameAndDebug(damlaBuharlasma, 0);
    addToRunTimeSelectionTable(fvModel, damlaBuharlasma, dictionary);
}
}


// * * * * * * * * * * * * Private Member Functions  * * * * * * * * * * * * //

void Foam::fv::damlaBuharlasma::readCoeffs(const dictionary& dict)
{
    interfacePatchName_ = dict.lookup<word>("interfacePatch");
    yakit_ = dict.lookup<word>("yakit");
    TL0_ = dict.lookup<scalar>("TL0");
    d0_ = dict.lookup<scalar>("d0");
    capSabit_ = dict.lookupOrDefault<Switch>("capSabit", false);
    rMinOran_ = dict.lookupOrDefault<scalar>("rMinOran", 0.1);

    // Yakıt sabitleri: damlaYakitlar (#include) içinden, elle kopya yok
    const dictionary& yd = dict.subDict(yakit_);
    y_.M = yd.lookup<scalar>("M");
    y_.Tb = yd.lookup<scalar>("Tb");
    y_.Tc = yd.lookup<scalar>("Tc");
    y_.Lb = yd.lookup<scalar>("Lb");
    y_.rhoL = yd.lookup<scalar>("rhoL");
    y_.cL = yd.lookup<scalar>("cL");
}


void Foam::fv::damlaBuharlasma::datAc()
{
    if (!Pstream::master())
    {
        return;
    }

    const fileName dir
    (
        mesh().time().globalPath()/"postProcessing"/"damla"
       /mesh().time().name()
    );
    mkDir(dir);
    dat_.reset(new std::ofstream((dir/"damla.dat").c_str()));
    *dat_
        << "# t dt rs d2d02 Tl mpp qs Yfs YwF mdot_ug_s mYakitGaz_ug"
           " yakitCikis_ug_s phiDamla_ug_s bcHataYakit bcHataDiger\n"
        << "# kutle sutunlari tam kure esdegeri (dilim / (A_dilim/(4 pi rs^2)))"
           ", mikrogram\n";
    dat_->flush();
}


// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

Foam::fv::damlaBuharlasma::damlaBuharlasma
(
    const word& name,
    const word& modelType,
    const fvMesh& mesh,
    const dictionary& dict
)
:
    fvModel(name, modelType, mesh, dict),
    interfacePatchName_(coeffs(dict).lookup<word>("interfacePatch")),
    yakit_(coeffs(dict).lookup<word>("yakit")),
    y_(),
    TL0_(coeffs(dict).lookup<scalar>("TL0")),
    d0_(coeffs(dict).lookup<scalar>("d0")),
    capSabit_(false),
    rMinOran_(0.1),
    mDotEvap_
    (
        IOobject("mDotEvap", mesh.time().name(), mesh,
            IOobject::NO_READ, IOobject::AUTO_WRITE),
        mesh,
        dimensionedScalar(dimMass/dimArea/dimTime, 0),
        calculatedFvPatchScalarField::typeName
    ),
    TlDamla_
    (
        IOobject("TlDamla", mesh.time().name(), "uniform", mesh,
            IOobject::READ_IF_PRESENT, IOobject::AUTO_WRITE),
        dimensionedScalar(dimTemperature, TL0_)
    ),
    rsDamla_
    (
        IOobject("rsDamla", mesh.time().name(), "uniform", mesh,
            IOobject::READ_IF_PRESENT, IOobject::AUTO_WRITE),
        dimensionedScalar(dimLength, 0.5*d0_)
    ),
    Tl0_(0),
    rs0_(0),
    timeIndex_(-1),
    patchi_(-1),
    dat_(),
    bcHataYakitMax_(0),
    bcHataDigerMax_(0)
{
    readCoeffs(coeffs(dict));

    patchi_ = mesh.boundary().findIndex(interfacePatchName_);
    if (patchi_ < 0)
    {
        FatalIOErrorInFunction(dict)
            << "interfacePatch " << interfacePatchName_ << " bulunamadi"
            << exit(FatalIOError);
    }

    Tl0_ = TlDamla_.value();
    rs0_ = rsDamla_.value();

    datAc();
}


// * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * //

void Foam::fv::damlaBuharlasma::correct()
{
    const Time& runTime = mesh().time();
    const scalar dt = runTime.deltaTValue();

    // timeIndex_ kalıbı (SP.C): adım başı değerleri bir kez saklanır;
    // aynı adımda ikinci correct() aynı başlangıçtan hesaplar
    if (timeIndex_ != runTime.timeIndex())
    {
        Tl0_ = TlDamla_.value();
        rs0_ = rsDamla_.value();
        timeIndex_ = runTime.timeIndex();
    }

    const fluidMulticomponentThermo& thermo =
        mesh().lookupObject<fluidMulticomponentThermo>
        (
            physicalProperties::typeName
        );
    const PtrList<volScalarField>& Y = thermo.Y();
    const label iF = thermo.species()[yakit_];

    const fluidThermophysicalTransportModel& ttm =
        mesh().lookupType<fluidThermophysicalTransportModel>();

    const fvPatch& pp = mesh().boundary()[patchi_];
    const scalarField& magSf = pp.magSf();
    const scalarField& dC = pp.deltaCoeffs();
    const scalarField& pW = thermo.p().boundaryField()[patchi_];
    const scalarField Y1(Y[iF].boundaryField()[patchi_].patchInternalField());

    // DM:1273-1275 — yakıt dışı türlerin ortalama mol kütlesi (ilk hücre)
    scalarField s(pp.size(), 0), sm(pp.size(), 0);
    forAll(Y, k)
    {
        if (k == iF) continue;
        const scalarField Yc(Y[k].boundaryField()[patchi_].patchInternalField());
        s += Yc;
        sm += Yc/thermo.WiValue(k);
    }

    // a = rho D_F / delta
    const scalarField aF(ttm.DEff(Y[iF], patchi_)*dC);

    const scalar TlS = damla::TlSinirla(Tl0_, y_);

    scalarField mpp(pp.size()), Ys(pp.size());
    forAll(mpp, i)
    {
        const scalar Mdig = s[i] > 0 ? s[i]/sm[i] : 28.0;
        Ys[i] = damla::Yfs(TlS, pW[i], Mdig, y_);
        mpp[i] = damla::mpp(aF[i], Ys[i], Y1[i]);
    }

    mDotEvap_.boundaryFieldRef()[patchi_] = mpp;

    // q_s = lambda dT/dr|_s; patch normali sıvıya doğru (dışa) → -snGrad
    const scalarField qs
    (
        -ttm.kappaEff(patchi_)*thermo.T().boundaryField()[patchi_].snGrad()
    );

    const scalar A = gSum(magSf);
    const scalar mppA = gSum(mpp*magSf)/A;
    const scalar qsA = gSum(qs*magSf)/A;
    const scalar YfsA = gSum(Ys*magSf)/A;

    // Sıvı: açık Euler, adım başı değerlerle
    const scalar TlYeni = damla::TlAdim(TlS, rs0_, qsA, mppA, dt, y_);
    const scalar rsYeni =
        capSabit_ ? rs0_ : damla::rsAdim(rs0_, mppA, dt, y_);

    TlDamla_.value() = TlYeni;
    rsDamla_.value() = rsYeni;

    // BC cebri denetimi: BC'ler yeni mDotEvap ile güncellenip değerlendirilir
    // yakıt: Y_w = Yfs; diğer: Y_w = a_k Y_c/(m'' + a_k)
    scalar hataF = 0, hataD = 0, YwF = 0;
    forAll(Y, k)
    {
        if (k == thermo.defaultSpecie()) continue;

        fvPatchScalarField& pf =
            const_cast<fvPatchScalarField&>(Y[k].boundaryField()[patchi_]);
        pf.updateCoeffs();
        pf.evaluate();

        const scalarField Yc(pf.patchInternalField());
        if (k == iF)
        {
            hataF = max(hataF, gMax(mag(pf - Ys)/max(mag(Ys), small)));
            YwF = gSum(pf*magSf)/A;
        }
        else
        {
            const scalarField ak(ttm.DEff(Y[k], patchi_)*dC);
            const scalarField beklenen(ak*Yc/(mpp + ak));
            hataD = max
            (
                hataD,
                gMax(mag(pf - beklenen)/max(mag(beklenen), scalar(1e-12)))
            );
        }
    }
    bcHataYakitMax_ = max(bcHataYakitMax_, hataF);
    bcHataDigerMax_ = max(bcHataDigerMax_, hataD);

    // Kütle tanılama (dilim → tam küre eşdeğeri, mikrogram)
    const scalar kure = 4*constant::mathematical::pi*sqr(rs0_)/A*1e9;

    const tmp<volScalarField> trho
    (
        mesh().foundObject<volScalarField>("rho")
      ? tmp<volScalarField>(mesh().lookupObject<volScalarField>("rho"))
      : thermo.rho()
    );
    const scalar mYakitGaz = gSum
    (
        trho().primitiveField()*Y[iF].primitiveField()*scalarField(mesh().V())
    );

    scalar yakitCikis = 0, phiDamla = 0;
    if (mesh().foundObject<surfaceScalarField>("phi"))
    {
        const surfaceScalarField& phi =
            mesh().lookupObject<surfaceScalarField>("phi");
        forAll(mesh().boundary(), pI)
        {
            const scalarField& pp_ = phi.boundaryField()[pI];
            if (pI == patchi_)
            {
                phiDamla = gSum(pp_);
            }
            else
            {
                yakitCikis += gSum(pp_*Y[iF].boundaryField()[pI]);
            }
        }
    }

    if (Pstream::master() && dat_)
    {
        char b[640];
        std::snprintf
        (
            b, sizeof(b),
            "%.9f %.12f %.12f %.12f %.9f %.12f %.6f %.12f %.12f "
            "%.12f %.12f %.12f %.12f %.12f %.12f\n",
            runTime.value(), dt, rsYeni, sqr(rsYeni/(0.5*d0_)), TlYeni,
            mppA, qsA, YfsA, YwF,
            mppA*A*kure, mYakitGaz*kure, yakitCikis*kure, phiDamla*kure,
            hataF, hataD
        );
        *dat_ << b;
        dat_->flush();
    }

    if (!capSabit_ && rsYeni < rMinOran_*0.5*d0_)
    {
        Info<< "damlaBuharlasma: d < " << rMinOran_ << " d0, kosu bitiyor"
            << endl;
        const_cast<Time&>(runTime).writeAndEnd();
    }
}


bool Foam::fv::damlaBuharlasma::read(const dictionary& dict)
{
    if (fvModel::read(dict))
    {
        readCoeffs(coeffs(dict));
        return true;
    }
    return false;
}


// ************************************************************************* //
