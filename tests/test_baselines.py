from investing_bot.baselines import compare_to_baselines, evaluate_baseline_performance


def _rows():
    return [
        {
            "broker_confirmed": True,
            "realized_alpha_density": 0.010,
            "cross_now_alpha_density": 0.006,
            "passive_touch_alpha_density": 0.008,
            "fixed_vertical_alpha_density": 0.007,
            "skip_alpha_density": 0.0,
        },
        {
            "broker_confirmed": True,
            "realized_alpha_density": 0.012,
            "cross_now_alpha_density": 0.007,
            "passive_touch_alpha_density": 0.009,
            "fixed_vertical_alpha_density": 0.008,
            "skip_alpha_density": 0.0,
        },
        {
            "broker_confirmed": False,
            "realized_alpha_density": 0.50,
            "cross_now_alpha_density": 0.50,
            "passive_touch_alpha_density": 0.50,
            "fixed_vertical_alpha_density": 0.50,
            "skip_alpha_density": 0.0,
        },
    ]


def test_evaluate_baseline_performance_filters_to_broker_confirmed():
    perf = evaluate_baseline_performance(_rows(), baseline="cross_now")
    assert perf.sample_count == 2
    assert perf.mean_reward == 0.0065


def test_compare_to_baselines_produces_positive_live_delta():
    suite = compare_to_baselines(_rows())
    assert suite.live.sample_count == 2
    assert suite.live.mean_reward == 0.011

    cross = next(row for row in suite.comparisons if row.baseline == "cross_now")
    assert cross.delta_mean_reward > 0
    assert cross.delta_lcb95 >= 0
