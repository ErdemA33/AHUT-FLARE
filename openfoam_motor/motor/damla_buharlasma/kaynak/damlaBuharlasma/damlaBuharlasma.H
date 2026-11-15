/*---------------------------------------------------------------------------*\
    damlaBuharlasma — sıvı damladan gaza yakıt veren fvModel (gaz bölgesi)

    Piroliz kalıbı (sibalPyrolysis): akı tek yerde hesaplanır, mDotEvap
    alanının interfacePatch değerine yazılır; BC'ler oradan okur.

    Sıvı topaklanmış 0B: T_l, r_s (açık Euler, adım başı değerlerle).
    TlDamla, rsDamla ağ kaydına uniformDimensionedScalarField olarak yazılır.

    Girdi:
        damla
        {
            type            damlaBuharlasma;
            interfacePatch  damla;
            yakit           NC7H16;
            #include        "<PAKET>/tablolar/damlaYakitlar"
            TL0             300;
            d0              0.001;
            capSabit        yes;
            rMinOran        0.1;
        }

    Çıktı: postProcessing/damla/0/damla.dat
\*---------------------------------------------------------------------------*/

#ifndef damlaBuharlasma_H
#define damlaBuharlasma_H

#include "fvModel.H"
#include "volFields.H"
#include "uniformDimensionedFields.H"
#include "damlaFonksiyonlari.H"
#include <fstream>
#include <memory>

namespace Foam
{
namespace fv
{

class damlaBuharlasma
:
    public fvModel
{
    // Girdiler
        word interfacePatchName_;
        word yakit_;
        damla::yakitSabitleri y_;
        scalar TL0_;
        scalar d0_;
        Switch capSabit_;
        scalar rMinOran_;

    // Alanlar
        mutable volScalarField mDotEvap_;
        mutable uniformDimensionedScalarField TlDamla_;
        mutable uniformDimensionedScalarField rsDamla_;

    // Adım başı değerleri
        scalar Tl0_;
        scalar rs0_;
        label timeIndex_;
        label patchi_;

    // Çıktı
        std::unique_ptr<std::ofstream> dat_;
        scalar bcHataYakitMax_;
        scalar bcHataDigerMax_;

    void readCoeffs(const dictionary& dict);
    void datAc();


public:

    TypeName("damlaBuharlasma");

    damlaBuharlasma
    (
        const word& name,
        const word& modelType,
        const fvMesh& mesh,
        const dictionary& dict
    );

    virtual ~damlaBuharlasma() {}

    virtual wordList addSupFields() const { return wordList(); }

    virtual void correct();

    virtual bool movePoints() { return true; }
    virtual void topoChange(const polyTopoChangeMap&) {}
    virtual void mapMesh(const polyMeshMap&) {}
    virtual void distribute(const polyDistributionMap&) {}

    virtual bool read(const dictionary& dict);
};

} // namespace fv
} // namespace Foam

#endif
