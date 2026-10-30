import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bengen import vec, stockrule as sr
from app import model


def test_constant_share_matches_vec():
    p = model.to_params(model.RECOMMENDED)
    US, INTL, B, C, I = model._boot("intermediate", "intl")
    S = 0.7 * US + 0.3 * INTL
    a = vec.simulate(p, S, B, C, I)
    b = sr.simulate(p, np.full(S.shape, p.stocks), S, B, I)
    assert np.allclose(a["reals"], b["reals"]) and (a["depleted"] == b["depleted"]).all()
    assert np.allclose(a["final"], b["final"])
