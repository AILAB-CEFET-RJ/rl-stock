"""Three synthetic daily v3 cases; never reads market data or trains agents."""
import json
from datetime import date,timedelta
from pathlib import Path

from rl_boleta.data_pipeline import digest
from rl_boleta.economic_kernel import Book,Level
from rl_boleta.missing_data_replay import MaskedDailyReplay,PartialFrame
from rl_boleta.session_replay import session_plan


def inputs(case):
    day=date(2025,3,3);plan=session_plan(day)
    for q in range(1,390):
        books=[]
        for ticker in ('SYNTA','SYNTB'):
            if q==1 and ticker=='SYNTB':continue
            if 40<=q<=42 and ticker=='SYNTA':continue
            if 100<=q<=103:continue
            if case=='missing_exit' and q==389 and ticker=='SYNTA':continue
            mid=95 if ticker=='SYNTA' and q>=43 else 100
            size=1 if case=='insufficient_exit_depth' and q==389 else 1000
            at=plan.opening+timedelta(minutes=q)
            books.append(Book(ticker,f'{case}-{ticker}-{q}',at,
                tuple(Level(mid-1-i,size) for i in range(5)),
                tuple(Level(mid+1+i,size) for i in range(5))))
        yield PartialFrame(plan.opening+timedelta(minutes=q),str(day),tuple(books))


def main():
    output=Path('results/v3_core_synthetic_2026-10-12')
    output.mkdir(parents=True,exist_ok=False)
    cases=[]
    for case in ('late_entry_and_gaps','missing_exit','insufficient_exit_depth'):
        calls=[]
        def policy(obs):
            calls.append(obs)
            return (1,1) if len(calls)==1 else (0,0)
        result=MaskedDailyReplay(('SYNTA','SYNTB'),initial_capital=1000).run(
            date(2025,3,3),inputs(case),policy)
        last=result.transitions[-1]
        expected={'late_entry_and_gaps':'scheduled_end','missing_exit':'exit_data_missing',
                  'insufficient_exit_depth':'liquidation_failure'}[case]
        assert result.status==expected
        assert result.plan.first_decision==session_plan(date(2025,3,3)).opening+timedelta(minutes=22)
        assert len(result.transitions)==367
        assert not result.training_ready
        fees=sum(e.fees for t in result.transitions for e in t.executions)
        # Decimal has finite precision: verify telescope to a much tighter
        # tolerance than price/fee scales, without changing stored values.
        difference=sum(t.reward for t in result.transitions)-(last.after_wealth/1000-1)
        assert abs(difference)<1e-25
        record=dict(case=case,status=result.status,entry_at=result.plan.first_decision.isoformat(),
            exit_at=result.plan.liquidation.isoformat(),transitions=len(result.transitions),
            coverage_candidate=result.coverage_candidate,flat=last.flat,
            truncated=last.truncated,cash=str(result.portfolio.cash),holdings=result.portfolio.holdings,
            terminal_marked_wealth=str(last.after_wealth),fees=str(fees),
            marked_return=None if result.marked_return is None else str(result.marked_return),
            realized_return=None if result.realized_return is None else str(result.realized_return))
        cases.append(record)
        path=output/f'{case}.jsonl'
        with path.open('w') as handle:
            for t in result.transitions:
                handle.write(json.dumps(dict(at=t.at.isoformat(),reward=str(t.reward),
                    wealth=str(t.after_wealth),availability=t.availability,
                    mark_capture_times=[at.isoformat() for at in t.mark_capture_times],
                    reason=t.reason,holdings=t.residual_holdings,canceled_pending=t.canceled_pending,
                    fills=[dict(ticker=f.ticker,side=f.side,quantity=f.quantity,price=str(f.price),fee=str(f.fee))
                           for e in t.executions for f in e.fills]))+'\n')
    report=dict(status='passed',synthetic=True,training_ready=False,cases=cases,
        code_sha256={str(p):digest(p) for p in (Path(__file__),Path('rl_boleta/missing_data_replay.py'),Path('rl_boleta/economic_kernel.py'))},
        outputs_sha256={p.name:digest(p) for p in output.iterdir()},
        limitations=['Synthetic core only; no feature encoder, Gym adapter or historical eligibility.',
                     'Exit quote coverage does not imply sufficient liquidation depth.'])
    (output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
