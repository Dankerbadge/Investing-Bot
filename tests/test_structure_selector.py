from investing_bot.structure_selector import StructureCandidate, select_structure


def test_structure_selector_prefers_defined_risk_and_best_score():
    structures = [
        StructureCandidate(
            structure_id="long-single",
            structure_type="long_single",
            alpha_density_lcb=0.010,
            spread_cost=0.015,
            assignment_risk=0.10,
            capital_required=500,
            max_loss=500,
        ),
        StructureCandidate(
            structure_id="debit-spread",
            structure_type="debit_spread",
            alpha_density_lcb=0.012,
            spread_cost=0.010,
            assignment_risk=0.05,
            capital_required=400,
            max_loss=400,
        ),
        StructureCandidate(
            structure_id="naked-short",
            structure_type="naked_short_call",
            alpha_density_lcb=0.030,
            spread_cost=0.010,
            assignment_risk=0.50,
            capital_required=300,
            max_loss=2000,
        ),
    ]

    decision = select_structure(structures, require_defined_risk=True)
    assert decision.selected is not None
    assert decision.selected.structure_id == "debit-spread"
    assert any(row.structure_id == "naked-short" for row in decision.rejected)


def test_structure_selector_applies_assignment_and_capital_limits():
    structures = [
        StructureCandidate(
            structure_id="too-risky",
            structure_type="credit_spread",
            alpha_density_lcb=0.02,
            spread_cost=0.01,
            assignment_risk=0.8,
            capital_required=500,
            max_loss=500,
        ),
        StructureCandidate(
            structure_id="too-expensive",
            structure_type="debit_spread",
            alpha_density_lcb=0.02,
            spread_cost=0.01,
            assignment_risk=0.1,
            capital_required=2000,
            max_loss=2000,
        ),
    ]

    decision = select_structure(structures, max_assignment_risk=0.6, max_capital_required=1000)
    assert decision.selected is None
    assert decision.reason == "no_eligible_structures"
    assert len(decision.rejected) == 2
