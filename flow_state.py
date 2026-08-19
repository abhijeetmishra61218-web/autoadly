"""
AutoAdly centralized per-user interaction state.

There is exactly one active interaction bucket per Telegram user.
When one bucket receives a new state for a user, every other bucket
automatically loses that user's previous state.

This preserves the existing handler architecture while enforcing:

    one user -> one active flow

Buckets that hold something worth cleaning up on eviction (background
tasks, a message on screen, a customer waiting on a countdown) can pass
on_evict=<callable> to FlowBucket(). It's called as
on_evict(user_id, old_value) whenever another bucket silently takes over
that user. It may return a coroutine, in which case it's scheduled on
the running loop. Never lets a bucket disappear without a chance to
clean up after itself.
"""

import asyncio

_BUCKETS = []


class FlowBucket(dict):
    def __init__(self, name, on_evict=None):
        super().__init__()
        self.name = name
        self.on_evict = on_evict
        _BUCKETS.append(self)

    def __setitem__(self, user_id, value):
        user_id = int(user_id)

        # A user may only have one active flow.
        for bucket in _BUCKETS:
            if bucket is not self:
                old = dict.pop(bucket, user_id, None)
                if old is not None and bucket.on_evict:
                    _fire_evict(bucket, user_id, old)

        dict.__setitem__(self, user_id, value)

    def __delitem__(self, user_id):
        dict.__delitem__(self, int(user_id))

    def pop(self, user_id, default=None):
        return dict.pop(self, int(user_id), default)

    def clear_user(self, user_id):
        dict.pop(self, int(user_id), None)


def _fire_evict(bucket, user_id, old_value):
    try:
        result = bucket.on_evict(user_id, old_value)
        if asyncio.iscoroutine(result):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(result)
            except RuntimeError:
                # No running loop (e.g. called from sync/test context) —
                # nothing sensible to do with the coroutine, drop it.
                result.close()
    except Exception as e:
        print(f"[flow_state] on_evict error in bucket '{bucket.name}': {e}")


def cancel_user(user_id):
    """Cancel every unfinished interaction for one user."""
    user_id = int(user_id)

    for bucket in _BUCKETS:
        old = dict.pop(bucket, user_id, None)
        if old is not None and bucket.on_evict:
            _fire_evict(bucket, user_id, old)


def get_active_flow(user_id):
    """Return (bucket_name, state) or (None, None)."""
    user_id = int(user_id)

    for bucket in _BUCKETS:
        state = dict.get(bucket, user_id)
        if state is not None:
            return bucket.name, state

    return None, None
