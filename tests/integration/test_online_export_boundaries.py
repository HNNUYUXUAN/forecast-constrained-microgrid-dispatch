from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from c_grid.src import data_loader
from scripts.online_report import emergency_events,storage_rows,clock


def test_missing_numeric_input_is_rejected(monkeypatch):
    original=pd.read_excel(data_loader.ATTACHMENTS_DIR/'附件1.xlsx')
    original.iloc[0,1]=np.nan
    monkeypatch.setattr(pd,'read_excel',lambda *a,**k:original)
    with pytest.raises(ValueError,match='Non-finite'):data_loader.load_problem1()


def test_duplicate_time_is_rejected(monkeypatch):
    original=pd.read_excel(data_loader.ATTACHMENTS_DIR/'附件1.xlsx')
    original.iloc[1,0]=original.iloc[0,0]
    monkeypatch.setattr(pd,'read_excel',lambda *a,**k:original)
    with pytest.raises(ValueError,match='clock labels'):data_loader.load_problem1()


def test_emergency_midnight_and_total():
    values=np.zeros(144);values[:2]=60;values[-2:]=120
    assert emergency_events(values)==[('00:00-00:20',20.),('23:40-24:00',40.)]
    assert sum(v for _,v in emergency_events(values))==values.sum()/6


def test_storage_six_blocks_and_endpoints():
    rows=storage_rows(np.ones(144)*6,np.ones(144)*12,6000,6500)
    assert len(rows)==6
    assert sum(r[1] for r in rows)==144
    assert sum(r[2] for r in rows)==288
    assert rows[0][3:]==['0:00',6000.]
    assert rows[1][3:]==['24:00',6500.]
    assert clock(1440)=='24:00'
