/*---------------------------------------------------------------------------*\
    coupledEvaporationSpeciesFvPatchScalarField — damla yüzeyi tür BC (Robin)

    m'' Y_w - rho D dY/dn = m'' epsilon
    mixed: alpha = m''/(rho D), valueFraction = alpha/(alpha + deltaCoeffs),
           refValue = epsilon, refGrad = 0
    m'' aynı bölgedeki mDotEvap alanının patch değeri (damlaBuharlasma).
    Kalıp: coupledPyrolysisSpeciesFvPatchScalarField (kilitli; yeni adla kopya)

    Girdi:  type coupledEvaporationSpecies; epsilon 1;  (yakıt) / 0 (diğer)
\*---------------------------------------------------------------------------*/

#ifndef coupledEvaporationSpeciesFvPatchScalarField_H
#define coupledEvaporationSpeciesFvPatchScalarField_H

#include "mixedFvPatchFields.H"

namespace Foam
{

class coupledEvaporationSpeciesFvPatchScalarField
:
    public mixedFvPatchScalarField
{
        scalar epsilon_;

public:

    TypeName("coupledEvaporationSpecies");

    coupledEvaporationSpeciesFvPatchScalarField
    (
        const fvPatch&,
        const DimensionedField<scalar, fvMesh>&
    );

    coupledEvaporationSpeciesFvPatchScalarField
    (
        const fvPatch&,
        const DimensionedField<scalar, fvMesh>&,
        const dictionary&
    );

    coupledEvaporationSpeciesFvPatchScalarField
    (
        const coupledEvaporationSpeciesFvPatchScalarField&,
        const fvPatch&,
        const DimensionedField<scalar, fvMesh>&,
        const fieldMapper&
    );

    coupledEvaporationSpeciesFvPatchScalarField
    (
        const coupledEvaporationSpeciesFvPatchScalarField&
    ) = delete;

    coupledEvaporationSpeciesFvPatchScalarField
    (
        const coupledEvaporationSpeciesFvPatchScalarField&,
        const DimensionedField<scalar, fvMesh>&
    );

    virtual tmp<fvPatchScalarField> clone
    (
        const DimensionedField<scalar, fvMesh>& iF
    ) const
    {
        return tmp<fvPatchScalarField>
        (
            new coupledEvaporationSpeciesFvPatchScalarField(*this, iF)
        );
    }

    virtual void updateCoeffs();
    virtual void write(Ostream&) const;
};

} // End namespace Foam

#endif
