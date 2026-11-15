/*---------------------------------------------------------------------------*\
Class
    Foam::pyrolysisTemperatureFvPatchScalarField

Description
    Pirolize eden kumas yuzeyi icin sicaklik sinir kosulu.

    Isil ince (thermally-thin) varsayimi: katinin ayri bir enerji denklemi
    cozulmez; yuzey sicakligi gaz tarafindaki yuzey sicakligina esittir.
    Yuzey enerji dengesi (kati icine akis ihmal):

        q_net (gazdan gelen iletim + radyasyon)  =  m_dot * L_pyrolysis

    Piroliz oncesi (T < T_threshold) saf Neumann, sonrasinda enerji
    dengesinden gelen Dirichlet gibi davranmasi icin mixedFvPatchScalarField
    tabanlidir.

    rho_s alanini YALNIZCA okur (gunceleyen pyrolysisFuelFraction'dir).

    Taban sinif: mixedFvPatchScalarField
    Ornek alinan OF14 kaynak dosyalari icin README'ye bakin.

SourceFiles
    pyrolysisTemperatureFvPatchScalarField.C

\*---------------------------------------------------------------------------*/

#ifndef pyrolysisTemperatureFvPatchScalarField_H
#define pyrolysisTemperatureFvPatchScalarField_H

#include "mixedFvPatchFields.H"

namespace Foam
{

/*---------------------------------------------------------------------------*\
          Class pyrolysisTemperatureFvPatchScalarField Declaration
\*---------------------------------------------------------------------------*/

class pyrolysisTemperatureFvPatchScalarField
:
    public mixedFvPatchScalarField
{
public:

    //- Runtime tip bilgisi
    TypeName("pyrolysisTemperature");


    // Constructors  (OF14 mixedFvPatchField ctor setiyle ayni sira)

        //- patch + ic alan
        pyrolysisTemperatureFvPatchScalarField
        (
            const fvPatch&,
            const DimensionedField<scalar, fvMesh>&
        );

        //- patch + ic alan + sozluk
        pyrolysisTemperatureFvPatchScalarField
        (
            const fvPatch&,
            const DimensionedField<scalar, fvMesh>&,
            const dictionary&
        );

        //- yeni patch'e esleyerek (OF14: fieldMapper)
        pyrolysisTemperatureFvPatchScalarField
        (
            const pyrolysisTemperatureFvPatchScalarField&,
            const fvPatch&,
            const DimensionedField<scalar, fvMesh>&,
            const fieldMapper&
        );

        //- ic alan referansi olmadan kopya: OF14'te silinmis
        pyrolysisTemperatureFvPatchScalarField
        (
            const pyrolysisTemperatureFvPatchScalarField&
        ) = delete;

        //- ic alan referansini ayarlayan kopya
        pyrolysisTemperatureFvPatchScalarField
        (
            const pyrolysisTemperatureFvPatchScalarField&,
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
                new pyrolysisTemperatureFvPatchScalarField(*this, iF)
            );
        }


    // Member Functions

        //- Katsayilari ve degerleri guncelle (enerji dengesi adim 2'de)
        virtual void updateCoeffs();

        //- Alan dosyasina yaz
        virtual void write(Ostream&) const;
};


} // End namespace Foam

#endif

// ************************************************************************* //
