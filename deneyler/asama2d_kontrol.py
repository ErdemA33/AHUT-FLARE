import sys,json; sys.path.insert(0,'/path/to/ahut-flare')
import numpy as np, contextlib, io, damla_motoru as dm
from sklearn.metrics import roc_auc_score
out={}
for ad,f in [(a,f) for a,f in (('mevcut','vr/C_tum.json'),('C_rad 0.3','cr/P0.3_tum.json'),('C_rad 0.5','cr/P0.5_tum.json'),('C_rad 1.0','cr/P1.0_tum.json'))]:
    p=json.load(open(f))['p']
    with contextlib.redirect_stdout(io.StringIO()): d,m=dm.flex2_kontrol(p)
    r={'kontrol hepsi AUC':m['auc'],'kontrol doğr':m['dogruluk']}
    for b,mk in (('µg',d.g_seviyesi<0.01),('1 g',d.g_seviyesi>=0.9)):
        x=d[mk]; r[f'{b} AUC']=roc_auc_score(x.yanar,x.model); r[f'{b} doğr']=float(((x.model>.5)==x.yanar).mean())
    # sönme türü örnekleri
    X=dm.ortam_bilesimi(21,'n2'); tur=[]
    for d0 in (1,2,3,4):
        o,_=dm._hizli_tek(p,'NC7H16',X,101.3,d0,1e-4,0); sc=float(o['sonme_capi'][0])
        tur.append(f"{d0}mm:{sc:.2f}/{dm.sonme_turu(p,'NC7H16',X,101.3,d0,1e-4,0,sc)}")
    r['heptan sönme (d0: çap/tür)']=' '.join(tur)
    out[ad]=r; print(ad,{k:(round(v,3) if isinstance(v,float) else v) for k,v in r.items()})
json.dump(out,open('cr/kontrol.json','w'),ensure_ascii=False)
