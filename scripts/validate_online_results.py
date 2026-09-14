"""Independent accounting, physical, information, and solver checks."""
import os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='1'
from pathlib import Path
import argparse
import json
import sys
import hashlib
import importlib.metadata
import numpy as np
import pandas as pd
import pulp
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from c_grid.src.data_loader import load_problem1
from c_grid.src.online_dispatch import COLUMNS,validate_records
from scripts.online_report import emergency_events,clock,load_records,read_compact_records


def independent_q1(run):
    data=load_problem1()
    model=pulp.LpProblem('reference_day',pulp.LpMinimize)
    q=[pulp.LpVariable(f'q{i}',lowBound=0) for i in range(144)]
    u=[pulp.LpVariable(f'u{i}',0,5000/6) for i in range(144)]
    v=[pulp.LpVariable(f'v{i}',0,5000/6) for i in range(144)]
    w=[pulp.LpVariable(f'w{i}',lowBound=0) for i in range(144)]
    s=[pulp.LpVariable(f's{i}',1200,10800) for i in range(145)]
    model+=pulp.lpSum(float(data.price_yuan_per_kwh.iloc[i])*q[i] for i in range(144))
    model+=s[0]==6000
    model+=s[-1]==6000
    for i in range(144):
        model+=q[i]+v[i]-u[i]-w[i]==float(data.load_kw.iloc[i]-data.pv_forecast_kw.iloc[i])/6
        model+=s[i+1]==s[i]+.9*u[i]-(1/.9)*v[i]
    import shutil
    cbc_path=shutil.which('cbc') or str(Path(sys.prefix)/'bin/cbc')
    solver=pulp.COIN_CMD(path=cbc_path,msg=False,threads=1) if Path(cbc_path).exists() else pulp.PULP_CBC_CMD(msg=False,threads=1)
    model.solve(solver)
    assert pulp.LpStatus[model.status]=='Optimal'
    cbc=float(pulp.value(model.objective))
    highs=json.loads((run/'problem1.json').read_text())['purchase_cost_yuan']
    assert abs(cbc-highs)<.01,(cbc,highs)
    return {'cbc_cost_yuan':cbc,'highs_cost_yuan':highs,'difference_yuan':abs(cbc-highs)}


def validate(run):
    run=Path(run)
    results=[]
    compact_names=set(read_compact_records(str(run/'process_records.xz'))[0]) if (run/'process_records.xz').exists() else set()
    for folder in sorted(run.iterdir()):
        if not (folder/'configuration.json').exists():continue
        if not (folder/'intervals.npz').exists() and folder.name not in compact_names:continue
        a=load_records(run,folder.name)
        assert a.shape==(334,144,len(COLUMNS))
        physical=validate_records(a)
        q0,q,e,c=a[:,:,0],a[:,:,1],a[:,:,5],a[:,:,8]
        terms=[float(np.sum(c*q0/6)),float(np.sum(c*1.5*np.maximum(q-q0,0)/6)),
               float(np.sum(c*.5*np.maximum(q0-q,0)/6)),float(np.sum(c*5*e/6))]
        independently=terms[0]+terms[1]-terms[2]+terms[3]
        summary=json.loads((folder/'summary.json').read_text())
        assert abs(independently-summary['total_cost_yuan'])<.005
        daily=json.loads((folder/'daily.json').read_text())
        assert abs(sum(x['total_cost_yuan'] for x in daily)-independently)<.005
        cfg=json.loads((folder/'configuration.json').read_text())['config']
        hours=np.arange(144)/6
        assert np.all(a[:,:,11]<=hours[None,:])
        assert np.all(a[:,:,12]<np.arange(31,365)[:,None])
        assert set(np.unique(a[:,:,11]).astype(int)).issubset(set(cfg['update_hours']))
        if not cfg['forecasts']:
            assert np.max(abs(q-q0))<1e-5
        merged=sum(amount for day in e for _,amount in emergency_events(day))
        assert abs(merged-e.sum()/6)<.01
        results.append({'name':folder.name,**physical,'accounting_difference_yuan':abs(independently-summary['total_cost_yuan']),
                        'emergency_merge_difference_kwh':abs(merged-e.sum()/6),'intervals':334*144})
    assert len(results) in (6,39)
    if len(results)==6:assert {r['name'] for r in results}=={'q2','q3','q42','q43','q42_announced','q43_announced'}
    from openpyxl import load_workbook
    book=load_workbook(ROOT/'c_grid/attachments/附件5/result1.xlsx',read_only=True)
    labels=[r[0] for r in list(book['计划购电量'].values)[1:]];book.close()
    source=load_problem1()
    pd.DataFrame({'period_index':range(144),'source_time_label':source.source_time_label,
                  'internal_interval':[f'{clock(i*10)}-{clock((i+1)*10)}' for i in range(144)],
                  'template_label':labels,'excel_row_result1':range(2,146),
                  'excel_column_result2_3_4':range(2,146)}).to_csv(run/'time_mapping.csv',index=False)
    versions={name:importlib.metadata.version(name) for name in ('numpy','scipy','pandas','matplotlib','pulp','openpyxl','pytest')}
    (run/'environment_versions.json').write_text(json.dumps(versions,indent=2))
    result={'status':'PASS','strategies':len(results),'intervals':len(results)*334*144,'problem1':independent_q1(run),'checks':results}
    (run/'validation.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='checks'}))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True)
    validate(p.parse_args().run)
