"""Run chronological strategies concurrently and retain restartable daily results."""
from __future__ import annotations
import os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import platform
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from c_grid.src.online_dispatch import (ScenarioConfig, DataBundle, ForecastProvider,
    COLUMNS, simulate_day, summarize)
from c_grid.src.problem1 import solve_problem1


def write_json(path,value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)


def campaign_configs():
    configs=[ScenarioConfig('q2'),ScenarioConfig('q42',price_information='predicted'),
             ScenarioConfig('q42_announced',price_information='announced')]
    for price,prefix in [('fixed','q3'),('predicted','q43'),('announced','q43_announced')]:
        for bits in itertools.product((False,True),repeat=3):
            hours=(0,)+tuple(h for h,enabled in zip((6,12,18),bits) if enabled)
            name=prefix if all(bits) else prefix+'_updates_'+''.join(str(int(x)) for x in bits)
            configs.append(ScenarioConfig(name,True,price,hours))
    for prefix,price in [('q3','fixed'),('q43','predicted')]:
        base=ScenarioConfig(prefix,True,price)
        for value in (.5,.9):
            configs.append(replace(base,name=f'{prefix}_risk_{value}',quantile=value))
        for value in (.5,1.5):
            configs.append(replace(base,name=f'{prefix}_terminal_{value}',terminal_multiplier=value))
        configs.append(replace(base,name=prefix+'_daily_closure',daily_closure=True))
        configs.append(replace(base,name=prefix+'_constant',interpolation='constant'))
    return configs


def fingerprints():
    files=list((ROOT/'c_grid/src').glob('*.py'))+[Path(__file__)]+list((ROOT/'c_grid/attachments').glob('*.xlsx'))
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
    return hashes,hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()


def init_worker(data):
    global DATA
    DATA=data


def run_strategy(cfg, initial_soc, output, start, stop, fingerprint, resume):
    directory=Path(output)/cfg.name
    directory.mkdir(parents=True,exist_ok=True)
    expected={'config':asdict(cfg),'fingerprint':fingerprint,'start_day':start,'stop_day':stop,'initial_soc':initial_soc}
    expected=json.loads(json.dumps(expected))
    manifest=directory/'configuration.json'
    if manifest.exists() and json.loads(manifest.read_text()) != expected:
        raise ValueError(f'Checkpoint configuration changed: {cfg.name}')
    write_json(manifest,expected)
    provider=ForecastProvider(DATA,cfg)
    soc=initial_soc
    started=time.monotonic()
    records=[]
    for day in range(start,stop):
        path=directory/f'day_{day:03d}.npz'
        if resume and path.exists():
            with np.load(path) as saved:
                row=saved['records']
            if abs(row[0,6]-soc)>.01:
                raise ValueError(f'Checkpoint initial state differs: {cfg.name} {day}')
            summarize(row)
        else:
            row=simulate_day(DATA,cfg,day,soc,provider)
            temp=path.with_suffix('.tmp.npz')
            np.savez_compressed(temp,records=row,day=day,columns=COLUMNS)
            temp.replace(path)
        soc=float(row[-1,7])
        records.append(row)
        write_json(directory/'progress.json',{'completed_days':day-start+1,'total_days':stop-start,
            'latest_day':day,'soc':soc,'elapsed_seconds':time.monotonic()-started,'pid':os.getpid()})
    all_records=np.stack(records)
    np.savez_compressed(directory/'intervals.npz',records=all_records,days=np.arange(start,stop),columns=COLUMNS)
    summary=summarize(all_records)
    summary.update(name=cfg.name,days=stop-start,elapsed_seconds=time.monotonic()-started)
    write_json(directory/'summary.json',summary)
    write_json(directory/'daily.json',[{'day':day,**summarize(row)} for day,row in zip(range(start,stop),records)])
    return summary


def monitor_resources(output, stop_event):
    def readcpu():
        values=[int(v) for v in Path('/proc/stat').read_text().splitlines()[0].split()[1:]]
        return sum(values[:8]),values[3]+values[4]
    if not Path('/proc/stat').exists():
        return
    prior=readcpu()
    with (output/'resource_usage.jsonl').open('a',encoding='utf-8') as handle:
        while not stop_event.wait(5):
            current=readcpu()
            busy=100*(1-(current[1]-prior[1])/max(1,current[0]-prior[0]))
            prior=current
            memory={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemTotal:','MemAvailable:'))}
            handle.write(json.dumps({'utc':datetime.now(timezone.utc).isoformat(),'cpu_busy_percent':busy,
                                    'load_average':os.getloadavg(),'memory_kb':memory})+'\n')
            handle.flush()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=os.cpu_count() or 1)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--days',type=int,default=334)
    parser.add_argument('--scenarios',nargs='*')
    args=parser.parse_args()
    if not 1<=args.days<=334 or args.workers<1:
        parser.error('days must be 1..334 and workers positive')
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    hashes,fingerprint=fingerprints()
    configs=campaign_configs()
    if args.scenarios:
        names=set(args.scenarios)
        configs=[cfg for cfg in configs if cfg.name in names]
        if len(configs)!=len(names):
            parser.error('Unknown scenario name')
    data=DataBundle.load_inputs()
    write_json(output/'manifest.json',{'utc':datetime.now(timezone.utc).isoformat(),'source_hashes':hashes,
        'fingerprint':fingerprint,'python':sys.version,'platform':platform.platform(),'workers':args.workers,
        'cpu_count':os.cpu_count(),'numpy':np.__version__,'scenarios':[asdict(c) for c in configs],
        'evaluation_start':'2025-02-01','evaluation_days':args.days,'columns':COLUMNS})
    event=threading.Event()
    thread=threading.Thread(target=monitor_resources,args=(output,event),daemon=True)
    thread.start()
    try:
        warm=output/'warmup'
        warm.mkdir(exist_ok=True)
        global DATA
        DATA=data
        warm_summary=run_strategy(ScenarioConfig('common_initialization'),6000.,warm,0,31,fingerprint,args.resume)
        initial=warm_summary['final_soc']
        schedule,metrics=solve_problem1()
        schedule.to_csv(output/'problem1.csv',index=False)
        write_json(output/'problem1.json',asdict(metrics))
        print(json.dumps({'phase':'warmup_complete','initial_soc':initial,'strategies':len(configs)},ensure_ascii=False),flush=True)
        results=[]
        with ProcessPoolExecutor(max_workers=args.workers,initializer=init_worker,initargs=(data,)) as pool:
            futures={pool.submit(run_strategy,cfg,initial,output,31,31+args.days,fingerprint,args.resume):cfg.name for cfg in configs}
            for future in as_completed(futures):
                result=future.result()
                results.append(result)
                print(json.dumps(result,ensure_ascii=False),flush=True)
                write_json(output/'summary.json',sorted(results,key=lambda x:x['name']))
        write_json(output/'completion.json',{'completed':len(results),'expected':len(configs),'status':'PASS'})
    finally:
        event.set()
        thread.join(timeout=6)


if __name__=='__main__':
    main()
