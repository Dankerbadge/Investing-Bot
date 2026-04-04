from investing_bot.online_policy import OnlinePolicyState, choose_online_action, update_online_policy


def test_online_policy_updates_only_on_broker_confirmed_rewards():
    state = OnlinePolicyState()
    state = update_online_policy(state, action="passive_touch", reward=0.01, broker_confirmed=False)
    arm = state.arms["passive_touch"]
    assert arm.attempts == 1
    assert arm.broker_confirmed_attempts == 0
    assert arm.cumulative_reward == 0.0

    state = update_online_policy(state, action="passive_touch", reward=0.02, broker_confirmed=True)
    arm = state.arms["passive_touch"]
    assert arm.attempts == 2
    assert arm.broker_confirmed_attempts == 1
    assert arm.cumulative_reward == 0.02


def test_online_policy_prefers_skip_when_event_risk_is_extreme():
    state = OnlinePolicyState()
    choice, _scores = choose_online_action(
        state=state,
        allowed_actions=("skip", "cross_now"),
        baseline_action="cross_now",
        event_risk_score=1.0,
        regime_multiplier=0.6,
    )
    assert choice == "skip"
