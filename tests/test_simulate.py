import pandas as pd
from bengen import data, simulate as sim


def flat(ret=0.0, infl=0.0, n=60):
    idx = range(2000, 2000 + n)
    return pd.DataFrame({"stocks": ret, "bonds": ret, "bills": ret, "inflation": infl}, index=idx)


def test_zero_return_lasts_one_over_rate():
    r = sim.longevity(flat(), 2000, 0.04, max_years=60)
    assert r.depleted and abs(r.years - 25) < 1e-9


def test_safemax_zero_return_is_one_over_horizon():
    assert abs(sim.safemax(flat(), 2000, 30) - 1 / 30) < 1e-4


def test_snapshot_spot_values():
    df = data.load(prefer_downloaded=False)
    assert abs(df.loc[2008, "stocks"] + 0.3655) < 1e-9
    assert abs(df.loc[1974, "inflation"] - 0.123) < 1e-9
    assert df.index.min() == 1928


def test_bengen_headline():
    df = data.load(prefer_downloaded=False)
    df = df.assign(bonds=0.5 * df.bills + 0.5 * df.bonds)
    b94 = sim.bengen1994_series(df)
    worst = min(range(1928, 1977), key=lambda y: sim.safemax(b94, y, 30, 0.5, "end"))
    assert worst == 1966
    assert 0.04 < sim.safemax(b94, 1966, 30, 0.5, "end") < 0.043


# ---- guardrails
from bengen import strategies as st


def _hist():
    df = data.load(prefer_downloaded=False)
    return df.assign(bonds=0.5 * df.bills + 0.5 * df.bonds)


def test_step_zero_matches_bengen():
    df = _hist()
    for y in (1937, 1966, 1973):
        for r in (0.045, 0.05, 0.06):
            a = sim.longevity(df, y, r, 0.5, 30, "end")
            p = st.simulate_path(df, y, r, st.Guardrails(step=0), 0.5, 30, "end")
            assert a.depleted == p.shortfall.any()
            assert int(a.years) == int((~p.shortfall).sum())


def test_step_caps_yearly_real_change():
    df = _hist()
    for step in (0.05, 0.1, 0.2):
        p = st.simulate_path(df, 1966, 0.05, st.Guardrails(step=step), 0.5, 30, "end")
        chg = p.real_spend.pct_change().dropna().abs()
        assert chg.max() <= step + 1e-9


def test_floor_holds_while_money_lasts():
    df = _hist()
    p = st.simulate_path(df, 1966, 0.05, st.Guardrails(step=0.2, floor=0.8), 0.5, 30, "end")
    assert (p.real_spend[~p.shortfall] >= 0.8 * 0.05 - 1e-9).all()


def test_leverage_returns():
    df = _hist()
    r = st.portfolio_returns(df, 1.5, borrow_spread=0.01)
    exp = 1.5 * df.stocks - 0.5 * (df.bills + 0.01)
    assert (r - exp).abs().max() < 1e-12
    assert (st.portfolio_returns(df, 1.0) - df.stocks).abs().max() < 1e-12


def test_fast_kernel_matches_simulate_path():
    df = _hist()
    for y, r, s, f, sh in [(1929, 0.05, 0.2, 0.8, 1.0), (1966, 0.055, 0.3, 0.73, 0.8), (1973, 0.04, 0.1, None, 1.5)]:
        p = st.simulate_path(df, y, r, st.Guardrails(step=s, floor=f), sh, 30, "end")
        rets = st.portfolio_returns(df, sh).loc[y:y + 29]
        d, mn, av, fb, _ = st.fast_guardrails(list(rets), list(df.inflation.loc[y:y + 29]), r, s, floor=f)
        assert d == p.shortfall.any() and abs(mn - p.real_spend.min()) < 1e-12 and abs(av - p.real_spend.mean()) < 1e-12


def test_drift_and_ceiling_match_between_engines():
    df = _hist()
    for y, sh in [(1929, 1.0), (1966, 0.8), (1982, 0.9)]:
        rule = st.Guardrails(step=0.2, floor=0.04 / 0.06, ceiling=1.5, drift=-0.005)
        p = st.simulate_path(df, y, 0.06, rule, sh, 30, "end")
        rets = st.portfolio_returns(df, sh).loc[y:y + 29]
        d, mn, av, fb, ea = st.fast_guardrails(list(rets), list(df.inflation.loc[y:y + 29]), 0.06, 0.2,
                                               floor=0.04 / 0.06, ceiling=1.5, drift=-0.005)
        assert d == p.shortfall.any() and abs(av - p.real_spend.mean()) < 1e-12
        assert abs(ea - p.real_spend.iloc[:10].mean()) < 1e-12
        # ceiling: real spending never above 1.5 x the declining plan
        cap = 1.5 * 0.06 * (1 - 0.005) ** pd.Series(range(len(p)))
        assert (p.real_spend <= cap + 1e-12).all()


def test_drift_without_guardrails_declines_half_percent():
    df = _hist()
    p = st.simulate_path(df, 1950, 0.04, st.Guardrails(step=0, drift=-0.005), 0.5, 30, "end")
    ratio = (p.real_spend / p.real_spend.shift()).dropna()
    assert ((ratio - 0.995).abs() < 1e-12).all()


def test_declining_floor_matches_between_engines():
    df = _hist()
    for y in (1929, 1966):
        rule = st.Guardrails(step=0.3, floor=0.04 / 0.075, drift=-0.005, floor_follows_drift=True)
        p = st.simulate_path(df, y, 0.075, rule, 0.8, 30, "end")
        rets = st.portfolio_returns(df, 0.8).loc[y:y + 29]
        d, mn, av, fb, ea = st.fast_guardrails(list(rets), list(df.inflation.loc[y:y + 29]), 0.075, 0.3,
                                               floor=0.04 / 0.075, drift=-0.005, floor_drift=-0.005)
        assert d == p.shortfall.any() and abs(av - p.real_spend.mean()) < 1e-12
        adj = (p.real_spend / 0.995 ** pd.Series(range(len(p)))).min()
        assert abs(mn - adj) < 1e-12


# ---- international
def test_intl_series_complete_and_spliced():
    df = data.load(prefer_downloaded=False)
    assert df["intl"].notna().all() and df.index.min() == 1928 and df.index.max() == 2025
    assert abs(df.loc[2008, "intl"] + 0.432) < 1e-9    # MSCI World ex USA from 1970
    assert abs(df.loc[1931, "intl"] + 0.2557) < 1e-9   # JST build before 1970


def test_with_intl_mixes_stocks_only():
    df = data.load(prefer_downloaded=False)
    m = data.with_intl(df, 0.25)
    assert ((m.stocks - (0.75 * df.stocks + 0.25 * df.intl)).abs() < 1e-12).all()
    assert (m.bonds == df.bonds).all() and data.with_intl(df, 0) is df


# ---- cash bucket
from bengen import bucket as bk


def test_bucket_engine_matches_without_cash():
    df = data.with_intl(_hist(), 0.25)
    for y in (1929, 1966, 1973):
        sl = df.loc[y:y + 29]
        rets = list(st.portfolio_returns(df, 0.8).loc[y:y + 29])
        a = st.fast_guardrails(rets, list(sl.inflation), 0.08, 0.3, 0.2, 0.5, 2.0, "end", -0.005, 10, -0.005)
        r = bk.run(list(sl.stocks), list(sl.bonds), list(sl.bills), list(sl.inflation), 0.08, 0.8, cash=0.0,
                   bucket=False, step=0.3, floor=0.5, ceiling=2.0, drift=-0.005)
        assert a[0] == r["depleted"] and abs(a[2] - sum(r["reals"]) / 30) < 1e-12 and abs(a[3] - r["final"]) < 1e-12


def test_bucket_never_sells_stocks_in_first_downturn_year():
    # flat bonds/cash, stocks fall 30% in year 1: spending must come from cash, stocks keep 70% of value
    s, b, c, inf = [-0.3] + [0.05] * 29, [0.0] * 30, [0.0] * 30, [0.0] * 30
    r = bk.run(s, b, c, inf, 0.04, 0.8, cash=0.10, bucket=True)
    assert not r["depleted"] and r["bucket_years"] >= 1
