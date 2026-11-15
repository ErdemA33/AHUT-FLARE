import sys, json; sys.path.insert(0,'/path/to/ahut-flare')
import numpy as np, droplet_engine as dm
t=dm.flex_oku(); X=dm.flex_bilesim(t)
n2=(t.seyreltici=='n2').to_numpy()
tohum=int(sys.argv[1]); r=dm.kalibre_hizli(t[n2].reset_index(drop=True), X[:,n2], baslangic_sayisi=6, tohum=tohum)
p=dm.param_sozluk(r.x); o=dm.hizli_tahmin(p,t,X)
out={'w':dm.IC_BOLGE_W,'p':p,'kayip':float(r.fun),'tohum':tohum}
for ad,mk in (('N2 (içeride)',n2),('CO2',(t.seyreltici=='co2').to_numpy()),('He',(t.seyreltici=='he').to_numpy()),('CO2+He',~n2)):
    out[ad]=dm.olcutler(t[mk].reset_index(drop=True),{k:v[mk] for k,v in o.items()})
for yk in ('NC7H16','CH3OH'):
    mk=((t.seyreltici=='he')&(t.yakit==yk)).to_numpy()
    m=dm.olcutler(t[mk].reset_index(drop=True),{k:v[mk] for k,v in o.items()})
    Kobs=t.yanma_hizi_mm2_s.to_numpy()[mk]; ok=np.isfinite(Kobs)&(Kobs>0.05)
    m['K_oran_medyan']=float(np.median(o['K'][mk][ok]/Kobs[ok])); out[f'He {yk}']=m
print(json.dumps(out,ensure_ascii=False))
