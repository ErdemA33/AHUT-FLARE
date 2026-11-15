/*---------------------------------------------------------------------------*\
Class
    Foam::pyrolysisFuelFractionFvPatchScalarField

Description
    Yakit turunun (ornegin CH4) kutle kesri icin piroliz sinir kosulu.

    Katidan Arrhenius yasasina gore cikan m_dot kadar yakit akisini yuzeyden
    gaz hacmine verir. Piroliz basinci (T >= T_threshold ve rho_s > 0) yokken
    saf Neumann (zeroGradient), varken karisik (mixed) davranir.

    Ayrica paylasilan rho_s (katinin alansal yogunlugu) alanini bu sinir kosulu
    SAHIPLENIR: her zaman adiminda Euler ileri adimiyla gunceller ve mesh'e geri
    yazar (lookupObjectRef, const_cast DEGIL). pyrolysisTemperature bu alani
    yalnizca okur.

    Taban sinif: mixedFvPatchScalarField
    Ornek alinan OF14 kaynak dosyalari icin README'ye bakin.

SourceFiles
    pyrolysisFuelFractionFvPatchScalarField.C

\*---------------------------------------------------------------------------*/

#ifndef pyrolysisFuelFractionFvPatchScalarField_H
#define pyrolysisFuelFractionFvPatchScalarField_H

#include "mixedFvPatchFields.H"

namespace Foam
{

/*---------------------------------------------------------------------------*\
          Class pyrolysisFuelFractionFvPatchScalarField Declaration
\*---------------------------------------------------------------------------*/

class pyrolysisFuelFractionFvPatchScalarField
:
    public mixedFvPatchScalarField
{
    // Private Data

        //- rho_s'in en son guncellendigi zaman indeksi. updateCoeffs() bir
        //  zaman adiminda birden cok kez cagrilabildiginden, Euler adiminin
        //  adim basina yalnizca bir kez atilmasini saglar.
        label curTimeIndex_;


public:

    //- Runtime tip bilgisi
    TypeName("pyrolysisFuelFraction");


    // Constructors  (OF14 mixedFvPatchField ctor setiyle ayni sira)

        //- patch + ic alan
        pyrolysisFuelFractionFvPatchScalarField
        (
            const fvPatch&,
            const DimensionedField<scalar, fvMesh>&
        );

        //- patch + ic alan + sozluk
        pyrolysisFuelFractionFvPatchScalarField
        (
            const fvPatch&,
            const DimensionedField<scalar, fvMesh>&,
            const dictionary&
        );

        //- yeni patch'e esleyerek (OF14: fieldMapper)
        pyrolysisFuelFractionFvPatchScalarField
        (
            const pyrolysisFuelFractionFvPatchScalarField&,
            const fvPatch&,
            const DimensionedField<scalar, fvMesh>&,
            const fieldMapper&
        );

        //- ic alan referansi olmadan kopya: OF14'te silinmis
        pyrolysisFuelFractionFvPatchScalarField
        (
            const pyrolysisFuelFractionFvPatchScalarField&
        ) = delete;

        //- ic alan referansini ayarlayan kopya
        pyrolysisFuelFractionFvPatchScalarField
        (
            const pyrolysisFuelFractionFvPatchScalarField&,
            const DimensionedField<scalar, fvMesh>&
        );

        //- Clone
        virtual tmp<fvPatchScalarField> clone
        (
            const DimensionedField<scalar, fvMesh>& iF
        ) const
        {
            return tmp<fvPatchScalarField>
            (
                new pyrolysisFuelFractionFvPatchScalarField(*this, iF)
            );
        }


    // Member Functions

        //- Katsayilari ve degerleri guncelle (fizik adim 2'de)
        virtual void updateCoeffs();

        //- Alan dosyasina yaz
        virtual void write(Ostream&) const;
};


} // End namespace Foam

#endif

// ************************************************************************* //
