/*---------------------------------------------------------------------------*\
    damlaBirimTest — damlaFonksiyonlari.H birim testi

    Kullanım: damlaBirimTest <damlaYakitlar dosyası>  < girdi
    Girdi satırı:  YAKIT T p Mdiger a Y1
    Çıktı satırı:  YAKIT T p pDoyma LBuhar Yfs mpp  (17 hane)
    Başta OpenFOAM sabitleri: "RR <değer>" ve "Pstd <değer>"
\*---------------------------------------------------------------------------*/

#include "damlaFonksiyonlari.H"
#include "IFstream.H"
#include "dictionary.H"
#include "thermodynamicConstants.H"
#include <cstdio>
#include <iostream>
#include <string>

using namespace Foam;

int main(int argc, char* argv[])
{
    if (argc != 2)
    {
        std::fprintf(stderr, "kullanim: damlaBirimTest <damlaYakitlar>\n");
        return 1;
    }

    IFstream is(argv[1]);
    const dictionary yakitlar(is);

    std::printf("RR %.17g\n", constant::thermodynamic::RR);
    std::printf("Pstd %.17g\n", constant::thermodynamic::pStd);

    std::string ad;
    double T, p, Mdig, a, Y1;
    while (std::cin >> ad >> T >> p >> Mdig >> a >> Y1)
    {
        const dictionary& d = yakitlar.subDict(word(ad));
        damla::yakitSabitleri y;
        y.M = d.lookup<scalar>("M");
        y.Tb = d.lookup<scalar>("Tb");
        y.Tc = d.lookup<scalar>("Tc");
        y.Lb = d.lookup<scalar>("Lb");
        y.rhoL = d.lookup<scalar>("rhoL");
        y.cL = d.lookup<scalar>("cL");

        const double Tl = damla::TlSinirla(T, y);
        const double ps = damla::pDoyma(Tl, y);
        const double L = damla::LBuhar(Tl, y);
        const double Ys = damla::Yfs(Tl, p, Mdig, y);
        const double m = damla::mpp(a, Ys, Y1);

        std::printf
        (
            "%s %.17g %.17g %.17g %.17g %.17g %.17g\n",
            ad.c_str(), T, p, ps, L, Ys, m
        );
    }

    return 0;
}
