/*---------------------------------------------------------------------------*\
    pyrolysisThinSolidTemperatureFvPatchScalarField — bkz. .H
\*---------------------------------------------------------------------------*/

#include "pyrolysisThinSolidTemperatureFvPatchScalarField.H"
#include "pyrolysisArrhenius.H"
#include "addToRunTimeSelectionTable.H"
#include "fieldMapper.H"
#include "volFields.H"
#include "surfaceFields.H"
#include "thermophysicalTransportModel.H"

void Foam::pyrolysisThinSolidTemperatureFvPatchScalarField::readDict
(
    const dictionary& dict
)
{
    c_s_     = dict.lookup<scalar>("c_s");
    m_inert_ = dict.lookup<scalar>("m_inert");
    qrName_  = dict.lookupOrDefault<word>("qr", "qr");
    const dictionary& ig = dict.subDict("igniter");
    W_m_   = ig.lookup<scalar>("W_m");
    t_on_  = ig.lookup<scalar>("t_on");
    t_off_ = ig.lookup<scalar>("t_off");
    x_min_ = ig.lookup<scalar>("x_min");
    x_max_ = ig.lookup<scalar>("x_max");
}


Foam::pyrolysisThinSolidTemperatureFvPatchScalarField::
pyrolysisThinSolidTemperatureFvPatchScalarField
(
    const fvPatch& p,
    const DimensionedField<scalar, fvMesh>& iF
)
:
    mixedFvPatchScalarField(p, iF),
    c_s_(1255), m_inert_(0), qrName_("qr"),
    W_m_(0), t_on_(0), t_off_(0), x_min_(0), x_max_(0),
    Ts0_(p.size(), 300),
    timeIndex_(-1)
{
    this->refValue() = 300;
    this->refGrad() = 0;
    this->valueFraction() = 1;
}


Foam::pyrolysisThinSolidTemperatureFvPatchScalarField::
pyrolysisThinSolidTemperatureFvPatchScalarField
(
    const fvPatch& p,
    const DimensionedField<scalar, fvMesh>& iF,
    const dictionary& dict
)
:
    mixedFvPatchScalarField(p, iF),
    Ts0_(p.size(), 300),
    timeIndex_(-1)
{
    readDict(dict);
    if (dict.found("value"))
    {
        fvPatchScalarField::operator=
        (
            scalarField("value", iF.dimensions(), dict, p.size())
        );
    }
    else
    {
        fvPatchScalarField::operator=(this->patchInternalField());
    }
    Ts0_ = *this;
    this->refValue() = *this;
    this->refGrad() = 0;
    this->valueFraction() = 1;
}


Foam::pyrolysisThinSolidTemperatureFvPatchScalarField::
pyrolysisThinSolidTemperatureFvPatchScalarField
(
    const pyrolysisThinSolidTemperatureFvPatchScalarField& ptf,
    const fvPatch& p,
    const DimensionedField<scalar, fvMesh>& iF,
    const fieldMapper& mapper
)
:
    mixedFvPatchScalarField(ptf, p, iF, mapper),
    c_s_(ptf.c_s_), m_inert_(ptf.m_inert_), qrName_(ptf.qrName_),
    W_m_(ptf.W_m_), t_on_(ptf.t_on_), t_off_(ptf.t_off_),
    x_min_(ptf.x_min_), x_max_(ptf.x_max_),
    Ts0_(mapper(ptf.Ts0_)),
    timeIndex_(ptf.timeIndex_)
{}


Foam::pyrolysisThinSolidTemperatureFvPatchScalarField::
pyrolysisThinSolidTemperatureFvPatchScalarField
(
    const pyrolysisThinSolidTemperatureFvPatchScalarField& ptf,
    const DimensionedField<scalar, fvMesh>& iF
)
:
    mixedFvPatchScalarField(ptf, iF),
    c_s_(ptf.c_s_), m_inert_(ptf.m_inert_), qrName_(ptf.qrName_),
    W_m_(ptf.W_m_), t_on_(ptf.t_on_), t_off_(ptf.t_off_),
    x_min_(ptf.x_min_), x_max_(ptf.x_max_),
    Ts0_(ptf.Ts0_),
    timeIndex_(ptf.timeIndex_)
{}


void Foam::pyrolysisThinSolidTemperatureFvPatchScalarField::updateCoeffs()
{
    if (this->updated())
    {
        return;
    }

    const fvMesh& mesh = internalField().mesh();
    const label patchi = patch().index();
    const Time& runTime = mesh.time();
    const scalar t = runTime.value();
    const scalar dt = runTime.deltaTValue();

    // Zaman adimi degistiyse onceki adimin sicakligini sakla
    if (timeIndex_ != runTime.timeIndex())
    {
        Ts0_ = *this;
        timeIndex_ = runTime.timeIndex();
    }

    const flameInFreefall::pyrolysisParams p =
        flameInFreefall::readPyrolysisDict(flameInFreefall::pyrolysisDict(mesh));
    const scalar f = p.yuzeyPayi;

    const scalarField& rho_s =
        flameInFreefall::rhoSField(mesh).boundaryField()[patchi];

    const thermophysicalTransportModel& ttm =
        patch().mesh().lookupType<thermophysicalTransportModel>();
    const scalarField kappap(ttm.kappaEff(patchi));
    const scalarField Tc(this->patchInternalField());
    const scalarField& delta = patch().deltaCoeffs();

    // Net radyasyon (duvara giren +)
    scalarField qr(patch().size(), 0);
    if (mesh.foundObject<volScalarField>(qrName_))
    {
        qr = mesh.lookupObject<volScalarField>(qrName_).boundaryField()[patchi];
    }

    // Igniter: birim genislik basina guc korunur
    scalarField qIgn(patch().size(), 0);
    if (W_m_ > 0 && t >= t_on_ && t < t_off_)
    {
        const scalar depth = mesh.bounds().span().z();
        const vectorField& Cf = patch().Cf();
        const scalarField& magSf = patch().magSf();
        scalar genislik = 0;
        forAll(Cf, i)
        {
            if (Cf[i].x() >= x_min_ && Cf[i].x() <= x_max_)
            {
                genislik += magSf[i]/depth;
            }
        }
        reduce(genislik, sumOp<scalar>());
        if (genislik > 0)
        {
            const scalar q = W_m_*f/genislik;
            forAll(Cf, i)
            {
                if (Cf[i].x() >= x_min_ && Cf[i].x() <= x_max_)
                {
                    qIgn[i] = q;
                }
            }
        }
    }

    const scalarField& Tp = *this;
    scalarField Ts(patch().size());
    forAll(Ts, i)
    {
        const scalar mDot = flameInFreefall::arrheniusRate(Tp[i], rho_s[i], p);
        const scalar C = f*c_s_*(m_inert_ + rho_s[i]);
        const scalar h = kappap[i]*delta[i];
        Ts[i] =
            (C/dt*Ts0_[i] + h*Tc[i] + qIgn[i] + qr[i] - f*mDot*p.L_pyrolysis)
           /(C/dt + h);
        Ts[i] = max(Ts[i], scalar(200));
    }

    this->refValue() = Ts;
    this->refGrad() = 0;
    this->valueFraction() = 1;

    mixedFvPatchScalarField::updateCoeffs();
}


void Foam::pyrolysisThinSolidTemperatureFvPatchScalarField::write
(
    Ostream& os
) const
{
    fvPatchScalarField::write(os);
    writeEntry(os, "c_s", c_s_);
    writeEntry(os, "m_inert", m_inert_);
    writeEntry(os, "qr", qrName_);
    os.writeKeyword("igniter") << nl << indent << token::BEGIN_BLOCK << incrIndent << nl;
    writeEntry(os, "W_m", W_m_);
    writeEntry(os, "t_on", t_on_);
    writeEntry(os, "t_off", t_off_);
    writeEntry(os, "x_min", x_min_);
    writeEntry(os, "x_max", x_max_);
    os << decrIndent << indent << token::END_BLOCK << nl;
    writeEntry(os, "value", *this);
}


namespace Foam
{
    makePatchTypeField
    (
        fvPatchScalarField,
        pyrolysisThinSolidTemperatureFvPatchScalarField
    );
}
