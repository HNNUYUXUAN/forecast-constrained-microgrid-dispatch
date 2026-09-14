from dataclasses import replace
import numpy as np
import pytest
from c_grid.src.online_dispatch import (ScenarioConfig,DataBundle,ForecastProvider,optimize,
                                        simulate_day,summarize,COLUMNS)


def synthetic():
    n=365
    return DataBundle(np.full((n,144),1000.),np.zeros((n,144)),np.full((n,144),.5),
                      np.zeros((n,4,24)),np.full(144,1000.),np.zeros(144),np.full(144,.5))


def test_emergency_at_lower_storage_bound():
    result=optimize([10000.],[1.],1200.,fixed_plan_kw=[0.],committed_periods=1)
    assert result['emergency'][0]==pytest.approx(10000.)
    assert result['soc'][1]==pytest.approx(1200.)


def test_optimization_power_and_soc():
    result=optimize([1000.,-3000.,3000.],[.2,.2,1.],6000.,terminal_value=.6)
    assert np.max(np.minimum(result['charge'],result['discharge']))<1e-4
    np.testing.assert_allclose(np.diff(result['soc']),.9*result['charge']/6-result['discharge']/.9/6,atol=.01)


@pytest.mark.parametrize('mode',['fixed','predicted','announced'])
def test_forecast_future_actuals_invariance(mode):
    data=synthetic()
    cfg=ScenarioConfig('test',True,mode)
    before=ForecastProvider(data,cfg).information(50,36)
    data.load[50:]+=100000
    data.pv[50:]+=40000
    data.forecasts[50,2:]+=90000
    data.forecasts[51:]+=90000
    if mode!='announced':
        data.prices[50:]*=100
    else:
        data.prices[51:]*=100
    after=ForecastProvider(data,cfg).information(50,36)
    np.testing.assert_array_equal(before.net_forecast_kw,after.net_forecast_kw)
    np.testing.assert_array_equal(before.price_forecast,after.price_forecast)


def test_announced_price_is_current_day_only():
    data=synthetic()
    data.prices[50]=.9
    info=ForecastProvider(data,ScenarioConfig('a',True,'announced')).information(50,108)
    assert np.all(info.price_forecast[:36]==.9)
    assert np.all(info.price_forecast[36:]==.5)


def test_reference_history_initialization():
    data=synthetic()
    a=ForecastProvider(data,ScenarioConfig('a')).information(0,0)
    assert np.all(a.net_forecast_kw==1000)
    assert a.training_last_day==-1


def test_config_invalid():
    with pytest.raises(ValueError):
        ScenarioConfig('invalid',price_information='other')
    with pytest.raises(ValueError):
        ScenarioConfig('invalid',update_hours=(6,))


def test_fixed_price_reduction_and_continuity():
    data=synthetic()
    fixed=simulate_day(data,ScenarioConfig('f',True),31,6000.)
    variable=simulate_day(data,ScenarioConfig('v',True,'predicted'),31,6000.)
    np.testing.assert_allclose(fixed,variable,atol=.001)
    summary=summarize(fixed)
    assert summary['max_storage_residual_kwh']<.01
    assert summary['total_cost_yuan']>=0


@pytest.mark.parametrize('forecasts,mode',[(False,'predicted'),(True,'predicted'),(True,'announced')])
def test_decisions_before_future_measurement_perturbation(forecasts,mode):
    data=synthetic()
    cfg=ScenarioConfig('probe',forecasts,mode)
    original=simulate_day(data,cfg,50,6000.)
    data.load[50,18:36]+=7000
    data.forecasts[50,2:]+=20000
    if mode=='predicted':
        data.prices[50,18:]*=3
    changed=simulate_day(data,cfg,50,6000.)
    np.testing.assert_allclose(original[:18],changed[:18],atol=.001)
