from investing_bot.policy import ActionPolicyStats, choose_entry_action, update_entry_policy


def test_policy_update_requires_broker_confirmation_for_learning():
    state = {}
    state = update_entry_policy(
        state,
        action="passive_touch",
        realized_alpha_density=0.01,
        broker_confirmed=False,
    )
    stats = state["passive_touch"]
    assert stats.attempts == 1
    assert stats.broker_confirmed_attempts == 0
    assert stats.positive_outcomes == 0

    state = update_entry_policy(
        state,
        action="passive_touch",
        realized_alpha_density=0.02,
        broker_confirmed=True,
    )
    stats = state["passive_touch"]
    assert stats.attempts == 2
    assert stats.broker_confirmed_attempts == 1
    assert stats.positive_outcomes == 1


def test_policy_can_select_skip_when_trade_action_is_unreliable():
    state = {
        "skip": ActionPolicyStats(
            action="skip",
            attempts=40,
            broker_confirmed_attempts=40,
            positive_outcomes=28,
            cumulative_alpha_density=0.40,
        ),
        "passive_touch": ActionPolicyStats(
            action="passive_touch",
            attempts=40,
            broker_confirmed_attempts=40,
            positive_outcomes=8,
            cumulative_alpha_density=-0.10,
        ),
    }
    action, _scores = choose_entry_action(
        allowed_actions=("skip", "passive_touch"),
        baseline_action="passive_touch",
        policy_state=state,
        min_confirmed_samples=20,
    )
    assert action == "skip"
