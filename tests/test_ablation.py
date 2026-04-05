from investing_bot.ablation import AblationScenario, run_ablation_study


def _rows():
    return [
        {
            "broker_confirmed": True,
            "realized_alpha_density": 0.020,
            "signal_arbiter_delta_alpha_density": 0.004,
            "structure_selector_delta_alpha_density": 0.003,
            "evidence_pool_delta_alpha_density": 0.002,
            "event_regime_delta_alpha_density": 0.001,
        },
        {
            "broker_confirmed": True,
            "realized_alpha_density": 0.015,
            "signal_arbiter_delta_alpha_density": 0.003,
            "structure_selector_delta_alpha_density": 0.002,
            "evidence_pool_delta_alpha_density": 0.001,
            "event_regime_delta_alpha_density": 0.001,
        },
        {
            "broker_confirmed": False,
            "realized_alpha_density": 1.0,
            "signal_arbiter_delta_alpha_density": 0.5,
            "structure_selector_delta_alpha_density": 0.5,
            "evidence_pool_delta_alpha_density": 0.5,
            "event_regime_delta_alpha_density": 0.5,
        },
    ]


def test_ablation_study_ranks_full_stack_above_minimal_controls():
    scenarios = [
        AblationScenario(name="full", use_signal_arbiter=True, use_structure_selector=True, use_evidence_pool=True, use_event_regime_features=True),
        AblationScenario(name="minimal", use_signal_arbiter=False, use_structure_selector=False, use_evidence_pool=False, use_event_regime_features=False),
    ]
    study = run_ablation_study(_rows(), scenarios=scenarios)

    assert study.best_scenario == "full"
    top = study.results[0]
    bottom = study.results[-1]
    assert top.mean_reward > bottom.mean_reward
    assert top.sample_count == 2


def test_ablation_study_uses_broker_confirmed_rows_only_by_default():
    study = run_ablation_study(_rows())
    assert all(row.sample_count == 2 for row in study.results)
