"""Summarize published CSV files without third-party dependencies."""
from pathlib import Path
import csv, statistics
DATA = Path(__file__).resolve().parents[1] / 'data'
def read(name):
    with (DATA / name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))
search = read('pd_bayes_stage1_results.csv')
print('Search trials:', len(search))
for label in ('Time limit','Rise failure','Fall'):
    print(label, sum(r['reason'] == label for r in search))
good = [r for r in search if r['reason']=='Time limit' and float(r['rms'])>=0]
best = min(good, key=lambda r: float(r['rms']))
print('Best search trial:', best['trial'], 'Kp:',best['kp'],'Kd:',best['kd'],'RMS:',best['rms'])
means=[]
for name in ('pd_5sec_manual_10_results.csv','pd_5sec_optimized_10_results.csv'):
    rows = read(name)
    values = [float(r['rms']) for r in rows if r['reason']=='Time limit' and float(r['rms'])>=0]
    print(name, 'success:', len(values),'/',len(rows), 'mean:',round(statistics.mean(values),6),'SD:',round(statistics.stdev(values),6))
    means.append(statistics.mean(values))
print('RMS reduction (%):', round((1-means[1]/means[0])*100,2))
