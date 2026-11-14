/*---------------------------------------------------------------------------*\
    pyrolysisVelocityFvPatchVectorField (adim 2)

    U = (m_dot / rho_gaz) * (-nf)   (domain icine ufleme), teget bilesen 0.
    rho_s YALNIZCA okunur.
\*---------------------------------------------------------------------------*/

#include "pyrolysisVelocityFvPatchVectorField.H"
#include "pyrolysisArrhenius.H"
#include "addToRunTimeSelectionTable.H"
#include "fieldMapper.H"
#include "volFields.H"
#include "surfaceFields.H"

// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

Foam::pyrolysisVelocityFvPatchVectorField::
pyrolysisVelocityFvPatchVectorField
(
    const fvPatch& p,
    const DimensionedField<vector, fvMesh>& iF
)
:
    fixedValueFvPatchVectorField(p, iF)
{}


Foam::pyrolysisVelocityFvPatchVectorField::
pyrolysisVelocityFvPatchVectorField
(
    const fvPatch& p,
    const DimensionedField<vector, fvMesh>& iF,
    const dictionary& dict
)
:
    fixedValueFvPatchVectorField(p, iF, dict)
{}


Foam::pyrolysisVelocityFvPatchVectorField::
pyrolysisVelocityFvPatchVectorField
(
    const pyrolysisVelocityFvPatchVectorField& ptf,
    const fvPatch& p,
    const DimensionedField<vector, fvMesh>& iF,
    const fieldMapper& mapper
)
:
    fixedValueFvPatchVectorField(ptf, p, iF, mapper)
{}


Foam::pyrolysisVelocityFvPatchVectorField::
pyrolysisVelocityFvPatchVectorField
(
    const pyrolysisVelocityFvPatchVectorField& ptf,
    const DimensionedField<vector, fvMesh>& iF
)
:
    fixedValueFvPatchVectorField(ptf, iF)
{}


// * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * //

void Foam::pyrolysisVelocityFvPatchVectorField::updateCoeffs()
{
    if (this->updated())
    {
        return;
    }

    const fvMesh& mesh = internalField().mesh();
    const label patchi = patch().index();

    const flameInFreefall::pyrolysisParams p =
        flameInFreefall::readPyrolysisDict(flameInFreefall::pyrolysisDict(mesh));

    const scalarField& Tp =
        mesh.lookupObject<volScalarField>("T").boundaryField()[patchi];

    // rho_s: YALNIZCA oku
    const scalarField& rho_s =
        flameInFreefall::rhoSField(mesh).boundaryField()[patchi];

    // Yuzeydeki gaz yogunlugu rho_gaz [kg/m^3]
    // >>> DERLEMEDE DOGRULA (adim 3): multicomponentFluid "rho" alanini kayitli
    //     tutar; aksi halde thermo.rho(patchi) kullanilabilir.
    const scalarField& rhoGas =
        mesh.lookupObject<volScalarField>("rho").boundaryField()[patchi];

    // Arrhenius m_dot [kg/m^2/s]
    scalarField mDot(patch().size());
    forAll(mDot, i)
    {
        mDot[i] = flameInFreefall::arrheniusRate(Tp[i], rho_s[i], p);
    }

    // nf(): fluid domaininden DISARI birim normal. Piroliz gazi domaine
    // GIRER -> hiz -nf yonunde. Teget bilesen dogal olarak 0.
    const vectorField nHat(patch().nf());
    const scalarField Un(p.yuzeyPayi*mDot/max(rhoGas, small));   // bu yuzun payi

    this->operator==(-Un*nHat);

    fixedValueFvPatchVectorField::updateCoeffs();
}


void Foam::pyrolysisVelocityFvPatchVectorField::write(Ostream& os) const
{
    fixedValueFvPatchVectorField::write(os);
}


// * * * * * * * * * * * * * * * * Kayit  * * * * * * * * * * * * * * * * * * //

namespace Foam
{
    makePatchTypeField
    (
        fvPatchVectorField,
        pyrolysisVelocityFvPatchVectorField
    );
}

// ************************************************************************* //
