"""Summarize 5-second 10x2 fixed-gain test results. Standard library only."""
from pathlib import Path
import csv, math

BASE=Path(__file__).parent
for mode in ('manual','optimized'):
    path=BASE/('pd_5sec_'+mode+'_10_results.csv')
    if not path.exists():
        print(mode,': CSV not found:',path.name)
        continue
    with path.open(newline='',encoding='utf-8-sig') as f:
        rows=list(csv.DictReader(f))
    good=[r for r in rows if r['reason']=='Time limit' and
          str(r['released']).lower()=='true' and
          int(r['eval_samples'])>=290 and int(r['samples_1_3'])>=190 and
          float(r['rms'])>=0 and float(r['rms_1_3'])>=0]
    print('\n',mode,':',len(good),'/',len(rows),'successful')
    for key,window in [('rms','2-5 s'),('rms_1_3','1-3 s')]:
        vals=[float(r[key]) for r in good]
        if not vals: continue
        mean=sum(vals)/len(vals)
        sd=math.sqrt(sum((v-mean)**2 for v in vals)/(len(vals)-1)) if len(vals)>1 else float('nan')
        print(window,'mean=%.4f SD=%.4f min=%.4f max=%.4f' % (mean,sd,min(vals),max(vals)))
