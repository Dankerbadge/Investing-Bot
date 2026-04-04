from investing_bot.sequential_tests import (
    SequentialTestState,
    lower_confidence_bound,
    should_kill_alpha,
    should_promote_alpha,
    success_rate,
    update_state,
)


def test_update_state_tracks_samples_and_success_rate():
    state = SequentialTestState()
    state = update_state(state, 0.01)
    state = update_state(state, -0.02)
    state = update_state(state, 0.03)

    assert state.sample_count == 3
    assert state.positive_count == 2
    assert success_rate(state) == 2 / 3


def test_should_promote_alpha_requires_positive_lcb_and_samples():
    state = SequentialTestState()
    for _ in range(50):
        state = update_state(state, 0.01)

    assert lower_confidence_bound(state) > 0
    assert should_promote_alpha(
        state=state,
        min_samples=30,
        min_lcb=0.0,
        min_success_rate=0.50,
    )


def test_should_kill_alpha_when_upper_bound_is_below_threshold():
    state = SequentialTestState()
    for _ in range(50):
        state = update_state(state, -0.02)

    assert should_kill_alpha(
        state=state,
        min_samples=30,
        max_ucb=-0.001,
    )
