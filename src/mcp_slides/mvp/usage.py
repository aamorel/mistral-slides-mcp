"""Lifetime provider-call allowance and concurrency bound for one service process."""
from contextlib import closing
import os
import threading

from . import auth


class UsageLimitError(RuntimeError):
    pass


_lock = threading.Lock()
_active = 0


def settings():
    limit = int(os.getenv("PILOT_MAX_PAID_CALLS", "100"))
    concurrent = int(os.getenv("PILOT_MAX_CONCURRENT_CALLS", "2"))
    if limit < 0 or concurrent < 1:
        raise ValueError("Pilot allowance must be nonnegative and concurrency positive.")
    enabled = os.getenv("PILOT_PAID_CALLS_ENABLED", "true").lower()
    if enabled not in ("true", "false"):
        raise ValueError("PILOT_PAID_CALLS_ENABLED must be true or false.")
    return limit, concurrent, enabled == "true"


def paid_call(function, **kwargs):
    """Count each attempted provider request, including explicit validation retries.

    SDK retries are disabled. Failed/uncertain calls are deliberately not refunded.
    Image conversations can contain multiple provider-internal steps: this is an
    operation allowance, not a currency ceiling. Run a single worker/replica.
    """
    global _active
    limit, concurrent, enabled = settings()
    if not enabled:
        raise UsageLimitError("Paid generation is paused for this pilot. Contact the operator.")
    with _lock:
        if _active >= concurrent:
            raise UsageLimitError("The pilot is busy. Try again shortly.")
        _active += 1
    try:
        with closing(auth.connect()) as db:
            db.execute('begin immediate')
            reserved = db.execute('update pilot_usage set calls=calls+1 where id=1 and calls<?', (limit,))
            if reserved.rowcount != 1:
                raise UsageLimitError("The pilot generation allowance is exhausted. Contact the operator.")
            db.commit()
        return function(**{**kwargs, "retries": None})
    finally:
        with _lock:
            _active -= 1
