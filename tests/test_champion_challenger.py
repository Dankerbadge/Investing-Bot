from investing_bot.champion_challenger import (
    PolicyPerformance,
    composite_policy_score,
    select_champion_policy,
)


def test_composite_score_penalizes_operational_risk():
    clean = PolicyPerformance(name="clean", replay_alpha_density_lcb=0.01, live_alpha_density_lcb=0.02)
    risky = PolicyPerformance(
        name="risky",
        replay_alpha_density_lcb=0.03,
        live_alpha_density_lcb=0.03,
        operational_penalty=0.05,
    )
    assert composite_policy_score(clean) > composite_policy_score(risky)


def test_select_champion_promotes_eligible_better_challenger():
    current = PolicyPerformance(name="champion", replay_alpha_density_lcb=0.005, probe_alpha_density_lcb=0.004, live_alpha_density_lcb=0.003, sample_count=120)
    challenger = PolicyPerformance(name="challenger", replay_alpha_density_lcb=0.02, probe_alpha_density_lcb=0.02, live_alpha_density_lcb=0.01, sample_count=120)

    decision = select_champion_policy(current=current, challengers=[challenger], min_sample_count=30)
    assert decision.promoted
    assert decision.champion == "challenger"
