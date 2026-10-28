"""The static dashboard's JavaScript engine (docs/dashboard/engine.js) must match the Python model."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

NODE = shutil.which("node")
JS = """
const E = require(process.argv[1] + '/docs/dashboard/engine.js');
const data = require(process.argv[1] + '/docs/dashboard/data.json');
const eng = E.create(data);
const cases = JSON.parse(process.argv[2]);
const out = cases.map(s => { const r = eng.run(s); const m = r.m;
  return {ce: m.ce, ran_out: m.ran_out, boot_run_out: m.boot_run_out, typical_1_10: m.typical_1_10,
          typical_11_20: m.typical_11_20, typical_21_30: m.typical_21_30, median_final: m.median_final,
          give_back_share: m.give_back_share, unluckiest: m.unluckiest, levels: m.levels, levels_best: m.levels_best,
          reals: Array.from({length: r.n}, (_, i) => Array.from({length: r.T}, (_, t) => r.reals(i, t))),
          balance: Array.from({length: r.n}, (_, i) => Array.from({length: r.T}, (_, t) => r.balance(i, t))),
          floor: r.floor, plan: r.plan}; });
console.log(JSON.stringify(out));
"""


def cases():
    import model
    R = model.RECOMMENDED
    yield from model.PRESETS.values()
    yield {**R, "cash": 10, "threshold": 15, "max_years": 4, "refill_years": 3}
    yield {**R, "floor_mode": "plan", "curve": "fixed", "drift": -1.5, "ceiling": 0.0}
    yield {**R, "who": "single", "bonds": "10y", "intl_series": "intl_stress", "gamma": 5.0}
    yield {**R, "gamma": 1.0, "intl": 0, "stocks": 60, "cut_step": 0, "raise_step": 0}


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_js_engine_matches_python():
    import model
    cs = list(cases())
    res = json.loads(subprocess.run([NODE, "-e", JS, str(ROOT), json.dumps(cs)], capture_output=True, text=True,
                                    check=True).stdout)
    for s, js in zip(cs, res):
        r = model.run(s)
        m = r.m
        for k in ("ce", "typical_1_10", "typical_11_20", "typical_21_30", "median_final", "give_back_share",
                  "boot_run_out"):
            assert js[k] == pytest.approx(m[k], rel=1e-9, abs=1e-12), (k, s)
        assert js["ran_out"] == m["ran_out"]
        wsum = (r.reals * m["weights"]).sum(axis=1)       # ties (e.g. fixed spending) may pick another index
        assert wsum[js["unluckiest"]] == pytest.approx(wsum.min(), rel=1e-9)
        assert js["levels"] == list(m["levels"]) and js["levels_best"] == list(m["levels_best"])
        np.testing.assert_allclose(js["reals"], r.reals, rtol=1e-9, atol=1e-12)
        np.testing.assert_allclose(js["balance"], r.balance, rtol=1e-9, atol=1e-9)
        np.testing.assert_allclose(js["floor"], r.floor, rtol=1e-12)
        np.testing.assert_allclose(js["plan"], r.plan, rtol=1e-12)
