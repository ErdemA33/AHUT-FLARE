/*---------------------------------------------------------------------------*\
Class
    Foam::coupledPyrolysisSpeciesFvPatchScalarField

Description
    Pirolize eden kati aray uzunde tur kutle kesri (Robin):

        m'' Y_w - rho D dY/dn = m'' * (fuel ? 1 : 0)

    m'' [kg/m^2/s]: komsu kati bolgenin mDotPyro patch degeri.
    fuel yes -> yakit turu (refValue 1); fuel no -> diger turler
    (refValue 0, aray uzden net tur akisi yok).
    rho D: cozucunun etkin DEff'i (fluidThermophysicalTransportModel).

SourceFiles
    coupledPyrolysisSpeciesFvPatchScalarField.C
\*---------------------------------------------------------------------------*/

#ifndef coupledPyrolysisSpeciesFvPatchScalarField_H
#define coupledPyrolysisSpeciesFvPatchScalarField_H

#include "mixedFvPatchFields.H"

namespace Foam
{

class coupledPyrolysisSpeciesFvPatchScalarField
:
    public mixedFvPatchScalarField
{
    // Private Data
        Switch fuel_;

public:

    TypeName("coupledPyrolysisSpecies");

    coupledPyrolysisSpeciesFvPatchScalarField
    (
        const fvPatch&,
        const DimensionedField<scalar, fvMesh>&
    );

    coupledPyrolysisSpeciesFvPatchScalarField
    (
        const fvPatch&,
        const DimensionedField<scalar, fvMesh>&,
        const dictionary&
    );

    coupledPyrolysisSpeciesFvPatchScalarField
    (
        const coupledPyrolysisSpeciesFvPatchScalarField&,
        const fvPatch&,
        const DimensionedField<scalar, fvMesh>&,
        const fieldMapper&
    );

    coupledPyrolysisSpeciesFvPatchScalarField
    (
        const coupledPyrolysisSpeciesFvPatchScalarField&
    ) = delete;

    coupledPyrolysisSpeciesFvPatchScalarField
    (
        const coupledPyrolysisSpeciesFvPatchScalarField&,
        const DimensionedField<scalar, fvMesh>&
    );

    virtual tmp<fvPatchScalarField> clone
    (
        const DimensionedField<scalar, fvMesh>& iF
    ) const
    {
        return tmp<fvPatchScalarField>
        (
            new coupledPyrolysisSpeciesFvPatchScalarField(*this, iF)
        );
    }

    virtual void updateCoeffs();

    virtual void write(Ostream&) const;
};

} // End namespace Foam

#endif
