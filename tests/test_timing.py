import warnings
import pytest

from easypy.timing import iter_wait, wait, repeat, iter_wait_progress, Timer, TimeoutException, PredicateNotSatisfied, timing
from easypy.timing import waiting
from easypy.bunch import Bunch


def test_wait_exception():
    with pytest.raises(Exception, match=".*`message` is required.*"):
        wait(0.1, pred=lambda: True)

    wait(0.1)
    wait(0.1, pred=lambda: True, message='message')
    wait(0.1, pred=lambda: True, message=False)
    repeat(0.1, callback=lambda: True)


def test_wait_better_exception():

    class TimedOut(PredicateNotSatisfied):
        pass

    i = 0

    def check():
        nonlocal i
        i += 1
        if i < 3:
            raise TimedOut(a=1, b=2)
        return True

    with pytest.raises(TimedOut):
        # due to the short timeout and long sleep, the pred would called exactly twice
        wait(.1, pred=check, sleep=1, message=False)

    assert i == 2
    wait(.1, pred=check, message=False)


def test_wait_better_exception_nested():

    class TimedOut(PredicateNotSatisfied):
        pass

    i = 0

    def check():
        nonlocal i
        i += 1
        if i < 3:
            raise TimedOut(a=1, b=2)
        return True

    with pytest.raises(TimedOut):
        # due to the short timeout and long sleep, the pred would called exactly twice
        # also, the external wait should call the inner one only once, due to the TimedOut exception,
        # which it knows not to swallow
        wait(5, lambda: wait(.1, pred=check, sleep=1, message=False), sleep=1, message=False)

    assert i == 2
    wait(.1, pred=check, message=False)


def test_iter_wait_warning():
    with pytest.raises(Exception, match=".*`message` is required.*"):
        for _ in iter_wait(0.1, pred=lambda: True):
            pass

    no_warn_iters = [
        iter_wait(0.1),
        iter_wait(0.1, pred=lambda: True, message='message'),
        iter_wait(0.1, pred=lambda: True, throw=False),
        iter_wait(0.1, pred=lambda: True, message=False)
    ]
    for i in no_warn_iters:
        for _ in i:
            pass


def test_iter_wait_progress_inbetween_sleep():
    data = Bunch(a=3)

    def get():
        data.a -= 1
        return data.a

    sleep = .1
    g = iter_wait_progress(get, advance_timeout=10, sleep=sleep)

    # first iteration should be immediate
    t = Timer()
    next(g)
    assert t.duration < sleep

    # subsequent iteration should be at least 'sleep' long
    next(g)
    assert t.duration >= sleep

    for state in g:
        pass
    assert state.finished is True


def test_iter_wait_progress_total_timeout():
    data = Bunch(a=1000)

    def get():
        data.a -= 1
        return data.a

    with pytest.raises(TimeoutException) as exc:
        for state in iter_wait_progress(get, advance_timeout=1, sleep=.05, total_timeout=.1):
            pass
    assert exc.value.message.startswith("advanced but failed to finish")


def test_wait_long_predicate():
    """
    After the actual check the predicate is held for .3 seconds. Make sure
    that we don't get a timeout after .2 seconds - because the actual
    condition should be met in .1 second!
    """

    t = Timer()

    def pred():
        try:
            return 0.1 < t.duration
        finally:
            wait(0.3)

    wait(0.2, pred, message=False)


def test_timeout_exception():
    exc = None

    with timing() as t:
        try:
            wait(0.5, lambda: False, message=False)
        except TimeoutException as e:
            exc = e

    assert exc.duration > 0.5
    assert exc.start_time >= t.start_time
    assert exc.start_time < t.stop_time
    assert t.duration > exc.duration


def test_wait_with_callable_message():
    val = ['FOO']

    with pytest.raises(TimeoutException) as e:
        def pred():
            val[0] = 'BAR'
            return False
        wait(pred=pred, timeout=.1, message=lambda: 'val is %s' % val[0])

    assert val[0] == 'BAR'
    assert e.value.message == 'val is BAR'


@pytest.mark.parametrize("multipred", [False, True])
def test_wait_do_something_on_final_attempt(multipred):
    data = []

    def pred(is_final_attempt):
        if is_final_attempt:
            data.append('final')
        data.append('regular')
        return False

    if multipred:
        pred = [pred]

    with pytest.raises(TimeoutException):
        wait(pred=pred, timeout=.5, sleep=.1, message=False)

    assert all(iteration == 'regular' for iteration in data[:-2])
    assert data[-2] == 'final'
    assert data[-1] == 'regular'


def test_waiting():
    with timing() as t:
        with waiting(.2):
            wait(.1)
    assert .2 <= t.duration, 'did not wait the reminder of the `waiting` timeout'
    assert t.duration < .3, 'waited the entire `waiting` timeout without considering time spend inside context manager'
