from pathlib import Path

from snapmaker_u1_mcp.gcode import analyze_gcode


def test_analyze_missing_gcode(tmp_path):
    result = analyze_gcode(tmp_path / "missing.gcode")
    assert result["file_size"] == 0
    assert result["warnings"]


def test_analyze_gcode_extracts_metadata(tmp_path):
    gcode = tmp_path / "part.gcode"
    gcode.write_text(
        "\n".join([
            "; filament_type = PETG",
            "; estimated printing time: 2h 3m",
            "; filament used [mm] = 1234.5",
            "; filament used [g] = 12.3",
            "; layer_height = 0.2",
            "; LAYER:0",
            "; LAYER:9",
            "M104 S240",
            "M109 S245",
            "M140 S80",
            "M190 S85",
            "T0",
            "T1",
        ]),
        encoding="utf-8",
    )

    result = analyze_gcode(gcode, requested_material="PETG")

    assert result["layer_count"] == 10
    assert result["estimated_print_time"] == "2h 3m"
    assert result["filament_length"] == "1234.5"
    assert result["filament_weight"] == "12.3"
    assert result["detected_material"] == "PETG"
    assert result["nozzle_temperatures"] == [240, 245]
    assert result["bed_temperatures"] == [80, 85]
    assert result["tool_count"] == 2
    assert result["warnings"] == []


def test_analyze_gcode_material_mismatch_warns(tmp_path):
    gcode = tmp_path / "part.gcode"
    gcode.write_text("; filament_type = PLA\n", encoding="utf-8")

    result = analyze_gcode(gcode, requested_material="PETG")

    assert result["warnings"]
