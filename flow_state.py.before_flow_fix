"""
AutoAdly centralized per-user interaction state.

There is exactly one active interaction bucket per Telegram user.
When one bucket receives a new state for a user, every other bucket
automatically loses that user's previous state.

This preserves the existing handler architecture while enforcing:

    one user -> one active flow
"""

_BUCKETS = []


class FlowBucket(dict):
    def __init__(self, name):
        super().__init__()
        self.name = name
        _BUCKETS.append(self)

    def __setitem__(self, user_id, value):
        user_id = int(user_id)

        # A user may only have one active flow.
        for bucket in _BUCKETS:
            if bucket is not self:
                dict.pop(bucket, user_id, None)

        dict.__setitem__(self, user_id, value)

    def __delitem__(self, user_id):
        dict.__delitem__(self, int(user_id))

    def pop(self, user_id, default=None):
        return dict.pop(self, int(user_id), default)

    def clear_user(self, user_id):
        dict.pop(self, int(user_id), None)


def cancel_user(user_id):
    """Cancel every unfinished interaction for one user."""
    user_id = int(user_id)

    for bucket in _BUCKETS:
        dict.pop(bucket, user_id, None)


def get_active_flow(user_id):
    """Return (bucket_name, state) or (None, None)."""
    user_id = int(user_id)

    for bucket in _BUCKETS:
        state = dict.get(bucket, user_id)
        if state is not None:
            return bucket.name, state

    return None, None
