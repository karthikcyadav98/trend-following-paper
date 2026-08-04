"""The rules that let a research loop learn instead of fooling itself.

THE DANGER THIS EXISTS TO PREVENT
---------------------------------
The obvious way to build a "self-improving trader" is to let it watch live
results and retune. That is the single most reliable way to destroy an account,
and this project already has the receipts:

  * fib extension, best config chosen on training data: +0.559R
    ...the same config out of sample:                   +0.180R +/- 0.393
  * crypto edge on 4 pairs   +0.18R  ->  on 10 pairs   +0.01R
  * forex edge on 4 pairs    +0.006R ->  on 16 pairs   -0.07R

Every single "improvement" found by looking at results evaporated when tested on
data that had not been looked at. A live book produces ~10 trades a month. You
cannot learn anything from 10 samples of a process whose per-trade noise is 20x
its edge -- you can only memorise noise.

SO THIS ENGINE LEARNS A DIFFERENT WAY
-------------------------------------
It accumulates *validated knowledge*, not tuned parameters:

  1. PRE-REGISTER. A hypothesis must state its acceptance criteria before it is
     run. No deciding what counts as success after seeing the answer.
  2. HOLD OUT. Selection happens on train; the reported number comes from data
     never consulted during selection.
  3. PAY FOR EVERY LOOK. The significance bar rises with the number of
     hypotheses tested, because testing 20 ideas guarantees one looks good at
     p<0.05. This is the piece that ad-hoc "AI improvement" always omits.
  4. BEAT THE NULL. A strategy must beat randomised signals, not merely be
     profitable.
  5. REMEMBER. Every result is journalled forever, so a dead idea is never
     rediscovered and the same mistake is not paid for twice.
  6. NEVER AUTO-DEPLOY ON LIVE P&L. Live results can raise an alarm; they can
     never promote a change. Promotion requires passing 1-5.

That is genuinely compounding: the set of things known to be false grows
monotonically, and the bar for a new claim gets harder, not easier.
"""

import math

# Two-sided z thresholds; we work in z rather than p to keep it dependency-free.
BASE_ALPHA = 0.05


def _phi(z):
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def two_sided_p(z):
    return 2.0 * (1.0 - _phi(abs(z)))


def required_z(n_tests_so_far, alpha=BASE_ALPHA):
    """Bonferroni-adjusted z needed for significance after n prior tests.

    The bar rises with every hypothesis the engine has ever run. This is the
    honest cost of searching: if you look 20 times, one look at p<0.05 means
    nothing, so the threshold must tighten to keep the family-wise error rate
    at alpha.
    """
    n = max(1, n_tests_so_far + 1)
    target = alpha / n
    # invert the normal tail by bisection -- no scipy dependency
    lo, hi = 0.0, 12.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if two_sided_p(mid) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def evaluate(observed_mean, observed_sd, n_obs, n_prior_tests, min_effect=0.0):
    """Verdict on one hypothesis, given the search cost paid so far."""
    if n_obs < 30:
        return {"verdict": "INSUFFICIENT", "reason": f"only {n_obs} observations; need >= 30",
                "z": None, "required_z": None, "p": None}
    se = observed_sd / math.sqrt(n_obs)
    if se == 0:
        return {"verdict": "INVALID", "reason": "zero variance", "z": None, "required_z": None, "p": None}
    z = (observed_mean - min_effect) / se
    need = required_z(n_prior_tests)
    p = two_sided_p(z)
    if z >= need:
        verdict = "SUPPORTED"
    elif z > 0:
        verdict = "NOT SIGNIFICANT"
    else:
        verdict = "REJECTED"
    return {"verdict": verdict, "z": z, "required_z": need, "p": p,
            "se": se, "n": n_obs,
            "reason": f"z={z:.2f} vs required {need:.2f} after {n_prior_tests} prior tests"}


def sample_size_needed(effect, sd, n_prior_tests, alpha=BASE_ALPHA):
    """How many trades before this effect COULD be detected. Reality check.

    Run this before running a live test: if the answer is 4,000 trades and the
    book does 10 a month, the live test cannot answer the question and should
    not be presented as if it might.
    """
    if effect == 0:
        return float("inf")
    z = required_z(n_prior_tests, alpha)
    return math.ceil((z * sd / abs(effect)) ** 2)
