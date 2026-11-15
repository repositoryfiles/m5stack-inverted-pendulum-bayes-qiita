"""PC server for two fixed PD gains, 10 trials each, 5-second control.
Python 3 standard library only. Start with --mode manual or --mode optimized.
Never run two servers on port 8000 simultaneously.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from datetime import datetime
import argparse, csv, json, math, threading

HOST, PORT = '0.0.0.0', 8000
MAX_TRIALS = 10
GAIN = {'manual': (40.0, 1.0), 'optimized': (47.2206, 1.5453)}
FIELDS = ['datetime','trial','kp','kd','reason','score','elapsed_ms','samples',
          'initial_theta','final_theta','min_theta','max_theta','min_abs_theta',
          'rms','eval_samples','rms_1_3','samples_1_3',
          'upright_ms','rise_ms','max_command','max_dt_ms','released']
lock = threading.Lock()
rows = []

def is_success(d):
    return (d['reason']=='Time limit' and d['released'] is True
            and int(d['eval_samples'])>=290 and int(d['samples_1_3'])>=190
            and float(d['rms'])>=0 and float(d['rms_1_3'])>=0)

def read_history():
    if not CSV_PATH.exists():
        with CSV_PATH.open('w', newline='', encoding='utf-8-sig') as f:
            csv.writer(f).writerow(FIELDS)
    with CSV_PATH.open('r', newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != FIELDS:
            raise SystemExit('CSV columns differ: use a fresh CSV filename')
        history=list(reader)
    for index,r in enumerate(history,1):
        if int(r['trial']) != index or index>MAX_TRIALS:
            raise SystemExit('Unexpected trial in existing CSV')
        if abs(float(r['kp'])-KP)>1e-4 or abs(float(r['kd'])-KD)>1e-4:
            raise SystemExit('Gain mismatch in existing CSV')
    rows.extend(history)
    print('Loaded',len(rows),'completed trials')

def summary():
    good=[r for r in rows if r['reason']=='Time limit' and
          str(r['released']).lower()=='true' and
          int(r['eval_samples'])>=290 and int(r['samples_1_3'])>=190 and
          float(r['rms'])>=0 and float(r['rms_1_3'])>=0]
    print('Progress:',len(rows),'/',MAX_TRIALS,'valid:',len(good),'failed:',len(rows)-len(good),flush=True)
    for key,label in [('rms','2-5s'),('rms_1_3','1-3s')]:
        values=[float(r[key]) for r in good]
        if values:
            avg=sum(values)/len(values)
            sd=(sum((x-avg)**2 for x in values)/(len(values)-1))**0.5 if len(values)>1 else 0.0
            print('%s RMS mean=%.4f SD=%.4f min=%.4f max=%.4f' %
                  (label,avg,sd,min(values),max(values)),flush=True)

class Handler(BaseHTTPRequestHandler):
    def reply(self,obj,code=200):
        body=json.dumps(obj).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        with lock:
            if self.path=='/gains':
                if len(rows)>=MAX_TRIALS:
                    self.reply({'status':'finished','trials':len(rows)})
                else:
                    self.reply({'status':'ready','trial':len(rows)+1,'kp':KP,'kd':KD})
            elif self.path=='/status':
                self.reply({'mode':MODE,'completed':len(rows),'max_trials':MAX_TRIALS,
                            'kp':KP,'kd':KD,'trial_ms':5000,'eval_start_ms':2000})
            else:
                self.send_error(404)

    def do_POST(self):
        if self.path!='/result':
            self.send_error(404);return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=4096:
                self.reply({'error':'invalid body size'},400);return
            d=json.loads(self.rfile.read(size))
            if not isinstance(d,dict):
                raise ValueError('JSON object required')
            with lock:
                trial=int(d['trial'])
                kp,kd=float(d['kp']),float(d['kd'])
                if not math.isfinite(kp) or not math.isfinite(kd):
                    raise ValueError('nonfinite gain')
                if abs(kp-KP)>1e-4 or abs(kd-KD)>1e-4:
                    self.reply({'error':'gain mismatch'},409);return
                if 1<=trial<=len(rows):
                    old=rows[trial-1]
                    if str(d.get('reason'))==old['reason'] and abs(float(d['rms'])-float(old['rms']))<1e-5 and abs(float(d['rms_1_3'])-float(old['rms_1_3']))<1e-5:
                        self.reply({'status':'duplicate','completed':trial})
                    else:
                        self.reply({'error':'different result already recorded'},409)
                    return
                if trial!=len(rows)+1 or trial>MAX_TRIALS:
                    self.reply({'error':'trial mismatch','expected':len(rows)+1},409);return
                for key in ('elapsed_ms','rms','min_abs_theta','eval_samples','rms_1_3','samples_1_3'):
                    if not math.isfinite(float(d[key])):
                        raise ValueError('invalid '+key)
                if not isinstance(d.get('released'),bool):
                    raise ValueError('released must be boolean')
                score=float(d['rms']) if is_success(d) else -1.0
                row={k:d.get(k,'') for k in FIELDS}
                row['datetime']=datetime.now().isoformat(timespec='seconds')
                row['score']=score
                with CSV_PATH.open('a',newline='',encoding='utf-8-sig') as f:
                    csv.DictWriter(f,fieldnames=FIELDS).writerow(row)
                    f.flush()
                rows.append(row)
                print('Saved',trial,d['reason'],'RMS 2-5s:',d['rms'],'RMS 1-3s:',d['rms_1_3'],flush=True)
                summary()
                self.reply({'status':'ok','completed':trial})
        except (KeyError,ValueError,TypeError,OverflowError) as e:
            self.reply({'error':str(e)},400)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=('manual','optimized'),required=True)
    args=parser.parse_args()
    MODE=args.mode
    KP,KD=GAIN[MODE]
    CSV_PATH=Path(__file__).with_name('pd_5sec_'+MODE+'_10_results.csv')
    read_history()
    print('Mode:',MODE,'Kp:',KP,'Kd:',KD,'5s; RMS 2-5s',flush=True)
    print('CSV:',CSV_PATH,flush=True)
    summary()
    HTTPServer((HOST,PORT),Handler).serve_forever()
