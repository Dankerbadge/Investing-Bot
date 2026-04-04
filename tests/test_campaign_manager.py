from investing_bot.campaign_manager import CampaignManager, allocate_probe_budget, resolve_family_probe_weight


def test_allocate_probe_budget_respects_stage_and_health():
    budget = allocate_probe_budget(
        alpha_name="filing_vol",
        stage="probe",
        total_budget=10000,
        bucket_health_score=0.8,
    )
    assert budget == 400.0


def test_resolve_family_probe_weight_uses_default_family_map():
    assert resolve_family_probe_weight("post_event_iv") == 0.6
    assert resolve_family_probe_weight("filing_vol") == 0.25
    assert resolve_family_probe_weight("open_drive") == 0.15


def test_campaign_manager_updates_only_on_broker_confirmed_rows():
    manager = CampaignManager()
    manager.start_campaign(alpha_name="filing_vol", stage="probe", total_budget=10000)

    manager.update_alpha_posterior(
        alpha_name="filing_vol",
        realized_alpha_density=0.01,
        broker_confirmed=False,
        probe_cost=5,
    )
    campaign = manager.get_campaign("filing_vol")
    assert campaign is not None
    assert campaign.confirmed_samples == 0
    assert campaign.spent_budget == 5.0


def test_campaign_manager_promotes_and_kills_by_sequential_state():
    manager = CampaignManager()
    manager.start_campaign(alpha_name="open_drive", stage="probe", total_budget=10000)

    for _ in range(35):
        manager.update_alpha_posterior(alpha_name="open_drive", realized_alpha_density=0.02)

    decision = manager.evaluate_alpha(alpha_name="open_drive", min_samples=30, min_lcb=0.0)
    assert decision.promote
    assert decision.next_stage == "scaled_1"

    manager.start_campaign(alpha_name="post_event_iv", stage="probe", total_budget=10000)
    for _ in range(35):
        manager.update_alpha_posterior(alpha_name="post_event_iv", realized_alpha_density=-0.02)

    kill_decision = manager.evaluate_alpha(alpha_name="post_event_iv", min_samples=30, max_ucb_kill=-0.001)
    assert kill_decision.kill
    assert kill_decision.next_stage == "disabled"


def test_campaign_manager_allocates_probe_budget_explicitly_by_family_weights():
    manager = CampaignManager()
    manager.start_campaign(alpha_name="post_event_iv", stage="probe", total_budget=10000)
    manager.start_campaign(alpha_name="filing_vol", stage="probe", total_budget=10000)
    manager.start_campaign(alpha_name="open_drive", stage="probe", total_budget=10000)

    allocations = manager.allocate_family_probe_budgets(total_budget=1000)
    post = allocations["post_event_iv"].allocated_probe_budget
    filing = allocations["filing_vol"].allocated_probe_budget
    open_drive = allocations["open_drive"].allocated_probe_budget

    assert round(post + filing + open_drive, 6) == 1000.0
    assert post > filing > open_drive
