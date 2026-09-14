"""Causal photovoltaic-storage dispatch on a ten-minute decision grid.

Power is kW at the public boundary; the optimization uses interval kWh.
Measurements for the current interval are assumed available before dispatch.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from functools import lru_cache
import warnings

import numpy as np
from scipy.optimize import linprog, milp, Bounds, LinearConstraint, OptimizeWarning
from scipy.sparse import lil_matrix, csr_matrix, hstack, vstack

from .data_loader import (load_problem1, load_attachment2_actual_profiles,
                          load_attachment3_forecasts, load_attachment4_actual_prices)
from .settlement import settle_purchase, storage_residual

DT, ETA, PMAX, SMIN, SMAX = 1 / 6, .9, 5000., 1200., 10800.


@dataclass(frozen=True)
class ScenarioConfig:
    name: str
    forecasts: bool = False
    price_information: str = 'fixed'
    update_hours: tuple[int, ...] = (0, 6, 12, 18)
    quantile: float = .8
    terminal_multiplier: float = 1.
    daily_closure: bool = False
    interpolation: str = 'linear'

    def __post_init__(self):
        if self.price_information not in ('fixed', 'predicted', 'announced'):
            raise ValueError('Unsupported price information')
        if not 0 < self.quantile < 1 or self.terminal_multiplier < 0:
            raise ValueError('Invalid risk or terminal parameter')
        if not self.update_hours or self.update_hours[0] != 0 or any(h not in (0,6,12,18) for h in self.update_hours) or tuple(sorted(set(self.update_hours))) != self.update_hours:
            raise ValueError('Forecast issue hours must start at zero')
        if self.interpolation not in ('linear', 'constant'):
            raise ValueError('Unsupported interpolation')


@dataclass
class DispatchState:
    storage_kwh: float
    day0_plan_kw: np.ndarray
    effective_plan_kw: np.ndarray


@dataclass(frozen=True)
class InformationSet:
    day: int
    period: int
    training_last_day: int
    issue_hour: int
    net_forecast_kw: np.ndarray
    price_forecast: np.ndarray


@dataclass
class DataBundle:
    load: np.ndarray
    pv: np.ndarray
    prices: np.ndarray
    forecasts: np.ndarray
    reference_load: np.ndarray
    reference_pv: np.ndarray
    fixed_price: np.ndarray

    @classmethod
    def load_inputs(cls):
        ref = load_problem1()
        actual = load_attachment2_actual_profiles()
        price = load_attachment4_actual_prices()
        forecast = load_attachment3_forecasts()
        return cls(actual.load_actual_kw.to_numpy().reshape(365,144),
                   actual.pv_actual_kw.to_numpy().reshape(365,144),
                   price.price_actual_yuan_per_kwh.to_numpy().reshape(365,144),
                   forecast.iloc[:,2:].to_numpy().reshape(365,4,24),
                   ref.load_kw.to_numpy(), ref.pv_forecast_kw.to_numpy(),
                   ref.price_yuan_per_kwh.to_numpy())


class ForecastProvider:
    """Forecast construction uses completed days and released issue rows only."""
    def __init__(self, data: DataBundle, config: ScenarioConfig):
        self.data, self.config = data, config
        self.cache = {}

    def historical_profile(self, array, target_day, known_day, reference):
        source = target_day - 7
        if not 0 <= source < known_day:
            source = known_day - 1
        return array[source] if source >= 0 else reference

    def pv_issue(self, day, issue_hour, target_minutes):
        values = self.data.forecasts[day, issue_hour // 6]
        points = issue_hour * 60 + np.arange(1,25) * 60
        if self.config.interpolation == 'linear':
            return np.interp(target_minutes, points, values)
        index = np.searchsorted(points, target_minutes, side='left').clip(0,23)
        return values[index]

    def day_forecasts(self, day, issue_hour):
        key = (day, issue_hour)
        if key in self.cache:
            return self.cache[key]
        data, cfg = self.data, self.config
        load = np.concatenate([self.historical_profile(data.load,d,day,data.reference_load) for d in (day,day+1)])
        pv = np.concatenate([self.historical_profile(data.pv,d,day,data.reference_pv) for d in (day,day+1)])
        if cfg.forecasts:
            pv = self.pv_issue(day,issue_hour,np.arange(1,289)*10)
        errors = []
        for past in range(max(7,day-28),day):
            if cfg.forecasts:
                historical_pv = self.pv_issue(past,issue_hour,np.arange(1,289)*10)
                historical_load = np.r_[data.load[past-7],data.load[past-6]]
                next_actual = (data.load[past+1]-data.pv[past+1]
                               if past+1<day else np.full(144,np.nan))
                actual_net = np.r_[data.load[past]-data.pv[past],next_actual]
                errors.append(actual_net-(historical_load-historical_pv))
            else:
                error=data.load[past]-data.pv[past]-(data.load[past-7]-data.pv[past-7])
                errors.append(np.tile(error,2))
        if len(errors)>=14:
            samples=np.asarray(errors)
            counts=np.isfinite(samples).sum(axis=0)
            margin=np.where(counts>=14,np.nanquantile(samples,cfg.quantile,axis=0),0.)
        else:
            margin=np.zeros(288)
        net = load - pv + margin
        if cfg.price_information == 'fixed':
            prices = np.tile(data.fixed_price,2)
        else:
            past = data.prices[max(0,day-28):day]
            estimated = np.median(past,axis=0) if len(past) else data.fixed_price.copy()
            prices = np.tile(estimated,2)
            if cfg.price_information == 'announced':
                prices[:144] = data.prices[day]
        self.cache[key] = (net,prices)
        return net,prices

    def information(self, day, period):
        issue = max(h for h in self.config.update_hours if h*6 <= period) if self.config.forecasts else 0
        net,price = self.day_forecasts(day,issue)
        return InformationSet(day,period,day-1,issue,net[period:period+144].copy(),price[period:period+144].copy())


@lru_cache(maxsize=4)
def matrix_template(n):
    # grid, charge, discharge, spill, emergency, adjustment absolute value, SOC.
    size = 7*n+1
    matrix = lil_matrix((2*n+1,size))
    absolute = lil_matrix((2*n,size))
    for t in range(n):
        matrix[t,t] = 1
        matrix[t,n+t] = -1
        matrix[t,2*n+t] = 1
        matrix[t,3*n+t] = -1
        matrix[t,4*n+t] = 1
        matrix[n+t,n+t] = -ETA
        matrix[n+t,2*n+t] = 1/ETA
        matrix[n+t,6*n+t] = -1
        matrix[n+t,6*n+t+1] = 1
        absolute[2*t,t],absolute[2*t,5*n+t] = 1,-1
        absolute[2*t+1,t],absolute[2*t+1,5*n+t] = -1,-1
    matrix[-1,6*n] = 1
    return matrix.tocsr(), absolute.tocsr()


def optimize(net_kw, prices, initial_soc, *, fixed_plan_kw=None, anchor_kw=None,
             committed_periods=0, terminal_value=0., closure_at=None, closure_soc=None):
    net, prices = np.asarray(net_kw,float), np.asarray(prices,float)
    n = len(net)
    if net.shape != prices.shape or not np.isfinite(net).all() or not np.isfinite(prices).all() or np.any(prices<0):
        raise ValueError('Finite, aligned forecasts and nonnegative prices required')
    if not SMIN-1e-6 <= initial_soc <= SMAX+1e-6:
        raise ValueError('Storage outside bounds')
    ae, au = matrix_template(n)
    c = np.zeros(7*n+1)
    c[:n] = prices
    c[n:3*n] = 1e-8
    c[4*n:5*n] = 5*prices
    c[-1] = -terminal_value
    low,high = np.zeros(7*n+1),np.full(7*n+1,np.inf)
    high[n:3*n] = PMAX*DT
    low[6*n:],high[6*n:] = SMIN,SMAX
    b = np.r_[net*DT,np.zeros(n),initial_soc]
    bu = np.zeros(2*n)
    if anchor_kw is not None:
        anchor = np.asarray(anchor_kw)[:committed_periods]*DT
        bu[:2*committed_periods:2] = anchor
        bu[1:2*committed_periods:2] = -anchor
        c[5*n:5*n+committed_periods] = .5*prices[:committed_periods]
    if fixed_plan_kw is not None:
        fixed = np.asarray(fixed_plan_kw)[:committed_periods]*DT
        low[:committed_periods] = fixed
        high[:committed_periods] = fixed
    if closure_at is not None:
        low[6*n+closure_at] = high[6*n+closure_at] = closure_soc
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',OptimizeWarning)
        result = linprog(c,A_eq=ae,b_eq=b,A_ub=au,b_ub=bu,bounds=np.column_stack((low,high)),
                         method='highs',options={'threads':1})
    if not result.success:
        raise RuntimeError(f'Dispatch LP: {result.message}')
    fallback = False
    if np.max(np.minimum(result.x[n:2*n],result.x[2*n:3*n])) > 1e-5:
        fallback = True
        constraint = lil_matrix((2*n,8*n+1))
        for t in range(n):
            constraint[t,n+t],constraint[t,7*n+1+t] = 1,-PMAX*DT
            constraint[n+t,2*n+t],constraint[n+t,7*n+1+t] = 1,PMAX*DT
        zero = csr_matrix((ae.shape[0],n))
        constraints = [LinearConstraint(hstack([ae,zero]).tocsr(),b,b),
                       LinearConstraint(hstack([au,csr_matrix((au.shape[0],n))]).tocsr(),-np.inf,bu),
                       LinearConstraint(constraint.tocsr(),-np.inf,np.r_[np.zeros(n),np.full(n,PMAX*DT)])]
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',RuntimeWarning)
            result = milp(np.r_[c,np.zeros(n)],integrality=np.r_[np.zeros(len(c)),np.ones(n)],
                          bounds=Bounds(np.r_[low,np.zeros(n)],np.r_[high,np.ones(n)]),
                          constraints=constraints,options={'threads':1,'mip_rel_gap':1e-9})
        if not result.success:
            raise RuntimeError(f'Dispatch MILP: {result.message}')
    x = result.x
    return {'grid':x[:n]/DT,'charge':x[n:2*n]/DT,'discharge':x[2*n:3*n]/DT,
            'spill':x[3*n:4*n]/DT,'emergency':x[4*n:5*n]/DT,
            'soc':x[6*n:7*n+1], 'milp_fallback':fallback}


COLUMNS = ('plan_kw','effective_kw','charge_kw','discharge_kw','spill_kw','emergency_kw',
           'soc_start_kwh','soc_end_kwh','price','load_kw','pv_kw','issue_hour','training_last_day',
           'forecast_net_kw','forecast_price','milp_fallback')


def simulate_day(data, cfg, day, initial_soc, provider=None):
    provider = provider or ForecastProvider(data,cfg)
    info = provider.information(day,0)
    terminal = ETA*np.mean(info.price_forecast)*cfg.terminal_multiplier
    plan = optimize(info.net_forecast_kw,info.price_forecast,initial_soc,
                    terminal_value=terminal,closure_at=144 if cfg.daily_closure else None,
                    closure_soc=initial_soc)
    state = DispatchState(initial_soc,plan['grid'].copy(),plan['grid'].copy())
    records = np.zeros((144,len(COLUMNS)))
    for t in range(144):
        info = provider.information(day,t)
        net,price = info.net_forecast_kw.copy(),info.price_forecast.copy()
        forecast_net,forecast_price = net[0],price[0]
        net[0] = data.load[day,t]-data.pv[day,t]
        price[0] = data.fixed_price[t] if cfg.price_information=='fixed' else data.prices[day,t]
        update = cfg.forecasts and t>0 and t%36==0 and t//6 in cfg.update_hours
        ncommit = 144-t
        result = optimize(net,price,state.storage_kwh,
                          fixed_plan_kw=None if update else state.effective_plan_kw[t:],
                          anchor_kw=state.day0_plan_kw[t:] if update else None,
                          committed_periods=ncommit,
                          terminal_value=ETA*np.mean(info.price_forecast)*cfg.terminal_multiplier,
                          closure_at=ncommit if cfg.daily_closure else None,closure_soc=initial_soc)
        if update:
            state.effective_plan_kw[t:] = result['grid'][:ncommit]
        values = (state.day0_plan_kw[t],state.effective_plan_kw[t],result['charge'][0],
                  result['discharge'][0],result['spill'][0],result['emergency'][0],
                  state.storage_kwh,result['soc'][1],price[0],data.load[day,t],data.pv[day,t],
                  info.issue_hour,info.training_last_day,forecast_net,forecast_price,int(result['milp_fallback']))
        records[t] = values
        state.storage_kwh = result['soc'][1]
    validate_records(records)
    return records


def validate_records(records):
    a = {key:records[...,i] for i,key in enumerate(COLUMNS)}
    power = a['effective_kw']+a['pv_kw']+a['discharge_kw']+a['emergency_kw']-a['load_kw']-a['charge_kw']-a['spill_kw']
    sr = a['soc_end_kwh']-a['soc_start_kwh']-ETA*a['charge_kw']*DT+a['discharge_kw']/ETA*DT
    if not np.isfinite(records).all() or np.max(np.abs(power))*DT>.01 or np.max(np.abs(sr))>.01:
        raise AssertionError('Energy conservation failed')
    for key in ('plan_kw','effective_kw','charge_kw','discharge_kw','spill_kw','emergency_kw'):
        if np.min(a[key]) < -1e-5:
            raise AssertionError(f'Negative {key}')
    if min(a['soc_start_kwh'].min(),a['soc_end_kwh'].min())<SMIN-.01 or max(a['soc_start_kwh'].max(),a['soc_end_kwh'].max())>SMAX+.01:
        raise AssertionError('Storage bounds failed')
    if max(a['charge_kw'].max(),a['discharge_kw'].max())>PMAX+.01:
        raise AssertionError('Power bounds failed')
    if np.max(np.minimum(a['charge_kw'],a['discharge_kw']))>1e-4:
        raise AssertionError('Simultaneous charge and discharge')
    flat_start,flat_end = a['soc_start_kwh'].ravel(),a['soc_end_kwh'].ravel()
    if len(flat_start)>1 and np.max(np.abs(flat_start[1:]-flat_end[:-1]))>.01:
        raise AssertionError('Storage continuity failed')
    return {'max_balance_residual_kwh':float(np.max(np.abs(power))*DT),
            'max_storage_residual_kwh':float(np.max(np.abs(sr)))}


def summarize(records):
    a = {key:records[...,i] for i,key in enumerate(COLUMNS)}
    components = settle_purchase(np.maximum(a['price'],0),np.maximum(a['plan_kw'],0),
                                 np.maximum(a['effective_kw'],0),np.maximum(a['emergency_kw'],0))
    result = {key+'_yuan':float(value.sum()) for key,value in components.items()}
    result.update(emergency_kwh=float(a['emergency_kw'].sum()*DT),
                  planned_kwh=float(a['plan_kw'].sum()*DT),
                  adjusted_kwh=float(a['effective_kw'].sum()*DT),
                  charge_kwh=float(a['charge_kw'].sum()*DT),discharge_kwh=float(a['discharge_kw'].sum()*DT),
                  initial_soc=float(a['soc_start_kwh'].ravel()[0]),final_soc=float(a['soc_end_kwh'].ravel()[-1]),
                  milp_fallbacks=int(a['milp_fallback'].sum()))
    daily_emergency=a['emergency_kw'].reshape(-1,144).sum(axis=1)*DT
    result['emergency_days']=int(np.sum(daily_emergency>1e-6))
    result['p95_daily_emergency_kwh']=float(np.quantile(daily_emergency,.95))
    result.update(validate_records(records))
    return result
