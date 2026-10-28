import numpy as np

from bengen import alt, vec


def test_blanchett_curve_averages_about_minus_one_percent():
    d = [vec.blanchett_change(a) for a in range(65, 95)]
    assert -0.0115 < np.mean(d) < -0.009          # Blanchett (2014): about -0.96%/yr
    assert min(d) == vec.blanchett_change(78)     # steepest in the late 70s
    assert d[0] > d[13] < d[-1]                   # the "smile"


def test_curve_plan_and_ceiling_match_between_engines():
    rng = np.random.default_rng(0)
    S = rng.normal(0.08, 0.18, (40, 30)); B = rng.normal(0.03, 0.06, (40, 30)); I = rng.normal(0.03, 0.02, (40, 30))
    p = vec.Params(rate=0.065, stocks=0.8, band=0.22, cut_step=0.085, raise_step=0.15, floor=0.42, floor_flat=True,
                   ceiling=1.1, curve="blanchett")
    a = alt.Alt(kind="guard", stocks0=0.8, rate=0.065, gband=0.22, cut_step=0.085, raise_step=0.15, floor=0.42,
                ceiling=1.1, curve="blanchett")
    o1 = vec.simulate(p, S, B, B * 0, I)
    o2 = alt.simulate(a, S, B, I)
    assert np.allclose(o1["reals"], o2["reals"])
    assert (o1["reals"] <= 1.1 * p.plan(30) + 1e-12).all()


def test_bootstrap_index_is_reproducible():
    a = alt.bootstrap_index(98, n=10, seed=3)
    b = alt.bootstrap_index(98, n=10, seed=3)
    assert a.shape == (10, 30) and (a == b).all() and a.max() < 98
