/*---------------------------------------------------------------------------*\
Class
    Foam::coupledPyrolysisSpeciesFvPatchScalarField

Description
    Pirolize eden kati aray uzunde tur kutle kesri (Robin):

        m'' Y_w - rho D dY/dn = m'' * (fuel ? Yf0 : 0)

    m'' [kg/m^2/s]: komsu kati bolgenin mDotPyro patch degeri.
    fuel yes -> yakit turu (refValue Yf0); fuel no -> diger turler
    (refValue 0, aray uzden net tur akisi yok).
    Yf0 (istege bagli, varsayilan 1): piroliz gazindaki vekil yakit (CH4)
    kutle kesri. Kalan (1 - Yf0) defaultSpecie (N2) olarak girer.
    Gerekce (10.11.2026): selulozik piroliz gazi ~16.74 MJ/kg, O2 talebi
    1.185 kg/kg; CH4 50.01 MJ/kg, 3.989 kg/kg. Yf0 ~0.30-0.335 enerji ve
    O2 talebini esitler.
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
        scalar yf0_;

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
