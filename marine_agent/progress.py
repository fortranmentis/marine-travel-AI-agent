"""Public task status only; never model reasoning or provider request payloads."""
from contextlib import contextmanager
from contextvars import ContextVar

_reporter = ContextVar('progress_reporter', default=None)


@contextmanager
def reporting(callback):
    token = _reporter.set(callback)
    try:
        yield
    finally:
        _reporter.reset(token)


def emit(stage, message, state='started', event='stage', **extra):
    from .runs import capture
    event_value = capture(dict(type=event, stage=stage, state=state, message=message, **extra))
    callback = _reporter.get()
    if callback:
        callback(event_value)
