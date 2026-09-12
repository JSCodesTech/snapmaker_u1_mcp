import pytest

from snapmaker_u1_mcp.errors import ProfileError
from snapmaker_u1_mcp.overrides import apply_process_overrides


def test_all_allowed_overrides_are_applied():
    process = {
        "layer_height": "0.2",
        "wall_loops": "2",
        "top_shell_layers": "4",
        "bottom_shell_layers": "3",
        "sparse_infill_density": "15%",
        "sparse_infill_pattern": "grid",
        "enable_support": "0",
        "brim_type": "no_brim",
    }

    updated, report = apply_process_overrides(process, {
        "layer_height": 0.24,
        "wall_loops": 5,
        "top_shell_layers": 6,
        "bottom_shell_layers": 5,
        "sparse_infill_density": "20%",
        "sparse_infill_pattern": "gyroid",
        "enable_support": "true",
        "brim_type": "outer_only",
    })

    assert updated["layer_height"] == "0.24"
    assert updated["wall_loops"] == "5"
    assert updated["top_shell_layers"] == "6"
    assert updated["bottom_shell_layers"] == "5"
    assert updated["sparse_infill_density"] == "20%"
    assert updated["sparse_infill_pattern"] == "gyroid"
    assert updated["enable_support"] == "1"
    assert updated["brim_type"] == "outer_only"
    assert report["layer_height"]["original"] == "0.2"


@pytest.mark.parametrize("overrides", [
    {"layer_height": 99},
    {"wall_loops": True},
    {"top_shell_layers": -1},
    {"sparse_infill_density": 101},
    {"sparse_infill_pattern": "bad-pattern"},
    {"enable_support": "maybe"},
    {"brim_type": "bad-brim"},
    {"nozzle_temperature": 260},
])
def test_invalid_overrides_are_rejected(overrides):
    with pytest.raises(ProfileError):
        apply_process_overrides({}, overrides)


def test_no_overrides_returns_copy_and_empty_report():
    original = {"wall_loops": "2"}
    updated, report = apply_process_overrides(original, None)
    assert updated == original
    assert updated is not original
    assert report == {}


def test_overrides_must_be_dict():
    with pytest.raises(ProfileError):
        apply_process_overrides({}, ["wall_loops"])
