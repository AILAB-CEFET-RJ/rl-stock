"""Lazy, manifest-bound Gym adapter for conditional historical train sessions."""
import json
from collections import OrderedDict
from datetime import date
from decimal import Decimal
from pathlib import Path

import gymnasium as gym
import numpy as np

from .data_pipeline import digest
from .historical_normalization import HistoricalMaskedNormalizer,load_train_normalizer
from .masked_env import MaskedTrainingEnv
from .masked_observations import MaskedEncoder,masked_market_rows
from .masked_eligibility import read_eligible_session
from .masked_preparation import verify


class HistoricalTrainingEnv(MaskedTrainingEnv):
    """Uniform sampling of all frozen train dates, bounded cache, fixed economics."""
    def __init__(self,normalizer_dir,scenario,*,cache_size=2):
        gym.Env.__init__(self)
        if type(cache_size) is not int or cache_size<1:raise ValueError('positive session cache size required')
        self.normalizer_dir=Path(normalizer_dir);self.scenario=scenario
        normalizer=load_train_normalizer(self.normalizer_dir,scenario)
        if not isinstance(normalizer,HistoricalMaskedNormalizer) or normalizer.partition!='train':
            raise ValueError('scenario-bound historical train normalizer required')
        source=json.loads((self.normalizer_dir/'manifest.json').read_text())['normalizers'][scenario]['eligibility_manifest']
        self.eligibility_dir=Path(source['path']).parent
        child=json.loads(Path(source['path']).read_text())
        if normalizer.eligibility_sha256!=source['sha256']:raise ValueError('normalizer and eligibility binding differ')
        protocol=json.loads((self.eligibility_dir/'protocol.json').read_text())
        rule=child['primary_rule'];expected=protocol['experimental_scenarios']['scenarios'][scenario]
        if rule!={'mode':expected['primary_mode'],'cap_grid_points':expected['cap_grid_points']}:
            raise ValueError('scenario rule differs from frozen design')
        if tuple(protocol['tickers'])!=normalizer.tickers:raise ValueError('asset order differs from normalizer')
        e=protocol['environment']
        if e['execution_lag_grid_steps']!=1 or e['peak_drawdown_stop'] is not None:
            raise ValueError('unsupported historical economic rule')
        self.economic_options=dict(initial_capital=Decimal(str(e['initial_capital_usd'])),
            fee_rate=Decimal(str(e['fee_bps_per_side']))/10000,participation=Decimal(str(e['participation_cap'])),
            dead_zone=Decimal(str(e['action_dead_zone'])),reward_scale=Decimal(str(e['reward_scale'])),
            capital_floor=Decimal(str(e['initial_capital_floor_fraction'])))
        # The immutable producing protocol owns this rule. Old bundles keep one
        # final attempt; a working-tree proposal cannot silently change their replay.
        wind_down_points=protocol['episode'].get('wind_down_execution_points',1)
        if type(wind_down_points) is not int or wind_down_points<1:
            raise ValueError('invalid frozen wind-down execution points')
        self.economic_options['wind_down_points']=wind_down_points
        from .missing_data_replay import REWARD_OBJECTIVES
        objective=e.get('reward_objective','marked_wealth')
        if objective not in REWARD_OBJECTIVES:raise ValueError('invalid frozen reward objective')
        self.economic_options['reward_objective']=objective
        from .missing_data_replay import ACCOUNT_REGIMES
        account=e.get('account_regime','legacy_reinvest')
        if account not in ACCOUNT_REGIMES:raise ValueError('invalid frozen account regime')
        self.economic_options['account_regime']=account
        self.encoder=MaskedEncoder(normalizer,e['initial_capital_usd'],include_account_context=account!='legacy_reinvest')
        self.tickers=normalizer.tickers;self.window_features=20
        self.dates=tuple(date.fromisoformat(d) for d in normalizer.sessions)
        self.cache_size=cache_size;self._cache=OrderedDict();self._market_encoders={};self.loaded_dates=[]
        self.sampling_order=[];self.completed=[];self.episode=None
        # Verify every fitting-date canonical/grid hash before the first learning step.
        self.input_hashes={str((self.normalizer_dir/'manifest.json').resolve()):digest(self.normalizer_dir/'manifest.json'),
            str(Path(source['path']).resolve()):source['sha256']}
        prepared_path=Path(child['prepared_manifest']['path']);verify(prepared_path,child['prepared_manifest']['sha256'])
        self.input_hashes[str(prepared_path)]=child['prepared_manifest']['sha256']
        prepared=json.loads(prepared_path.read_text())
        for row in prepared['sessions']:
            if row['session_id'] not in normalizer.sessions:continue
            for p,h in row['canonical_inputs'].items():self.input_hashes[p]=h
            grid=prepared_path.parent/row['grid_file'];self.input_hashes[str(grid.resolve())]=prepared['outputs'][row['grid_file']]
        self.verify_inputs()
        self.action_space=gym.spaces.Box(-1,1,(len(self.tickers),),dtype=np.float32)
        self.observation_space=gym.spaces.Box(-np.inf,np.inf,(20*43*len(self.tickers)+len(self.tickers)+4+3*self.encoder.include_account_context,),dtype=np.float32)

    def verify_inputs(self):
        for p,h in self.input_hashes.items():verify(p,h)
        current=load_train_normalizer(self.normalizer_dir,self.scenario)
        if current!=self.encoder.normalizer:raise ValueError('normalizer changed during run')

    def session_for_day(self,day):
        if day not in self.dates:raise ValueError('date outside frozen scenario train set')
        if day in self._cache:
            session=self._cache.pop(day);self._cache[day]=session;return session
        session=read_eligible_session(self.eligibility_dir,day,partition='train')
        if session.synthetic is not False:raise ValueError('historical source session required')
        # Validate the full feature tail, even if the policy will stop early.
        from .cached_observations import CachedMaskedEncoder
        self._market_encoders[day]=CachedMaskedEncoder(self.encoder.normalizer,session,self.encoder.initial_capital,
            include_account_context=self.encoder.include_account_context)
        self.loaded_dates.append(str(day));self._cache[day]=session
        while len(self._cache)>self.cache_size:
            old,_=self._cache.popitem(last=False);self._market_encoders.pop(old)
        return session

    def _encoded(self,terminal=False):
        return self._market_encoders[self.session.day].flatten(
            self.episode.observation(allow_terminal=terminal),self.session.trades)

    def reset(self,*,seed=None,options=None):
        gym.Env.reset(self,seed=seed)
        if options:raise ValueError('sample all frozen train dates uniformly; no override')
        day=self.dates[int(self.np_random.integers(len(self.dates)))];self.session=self.session_for_day(day)
        self.sampling_order.append(str(day));self.episode=self._controller().start(day,self.session.frames)
        return self._encoded(),{'session_id':str(day),'scenario':self.scenario,'partition':'train'}
