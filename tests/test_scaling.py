from quadtank_control.experiments.scaling import (
    DELAYS_S,
    Variant,
    make_config,
    overflow_thresholds,
    variants,
)


def test_variants_change_one_thing_at_a_time_from_the_baseline():
    vs = variants()
    base = Variant(10.0, 0.5, 18.0)
    assert vs[0] == base
    assert len(vs) == 7 and len(set(vs)) == 7
    for v in vs[1:]:
        differing = sum(
            a != b
            for a, b in zip(
                (v.hold_s, v.gamma, v.h_safe), (base.hold_s, base.gamma, base.h_safe), strict=True
            )
        )
        assert differing == 1


def test_hold_periods_are_multiples_of_the_plant_step():
    """A period that is not a whole number of 2 s steps would silently round and change the experiment."""
    assert all(v.hold_s % 2.0 == 0.0 for v in variants())


def test_config_wires_the_variant_through():
    cfg = make_config(Variant(20.0, 0.8, 16.0), runs=4)
    assert cfg.supervisor_period_s == 20.0 and cfg.cbf.gamma == 0.8 and cfg.cbf.h_safe == 16.0
    assert cfg.protocols == ["cbf_only@remote"] and cfg.attacks == ["overt"]
    assert cfg.runs_per_cell == 4 and cfg.rtts_s == DELAYS_S


def test_overflow_thresholds_picks_overt_overflow_rows_only():
    summary = {
        "delay_thresholds": [
            {
                "harm_type": "overflow",
                "attack": "overt",
                "plant": "min_phase",
                "d_star_first_harm": 8.0,
                "d_star_point": 12.0,
                "d_star_confirmed": 13.0,
            },
            {
                "harm_type": "harm",
                "attack": "overt",
                "plant": "min_phase",
                "d_star_first_harm": 1.0,
                "d_star_point": 1.0,
                "d_star_confirmed": 1.0,
            },
            {
                "harm_type": "overflow",
                "attack": "honest",
                "plant": "min_phase",
                "d_star_first_harm": 2.0,
                "d_star_point": 2.0,
                "d_star_confirmed": 2.0,
            },
        ]
    }
    assert overflow_thresholds(summary) == {
        "min_phase": {"first_harm": 8.0, "point": 12.0, "confirmed": 13.0}
    }
