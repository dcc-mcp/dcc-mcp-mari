from dcc_mcp_mari import skill_tools


def test_wait_for_export_files_requires_stable_non_empty_outputs(tmp_path, monkeypatch):
    output = tmp_path / "BaseColor.1001.png"
    output.write_bytes(b"png")
    monkeypatch.setattr(skill_tools.time, "sleep", lambda _seconds: None)

    result = skill_tools.wait_for_export_files(
        {
            "background_export": True,
            "scheduled_item_count": 1,
            "planned_files": {"BaseColor": [str(output)]},
        }
    )

    assert result["background_export"] is False
    assert result["exported_item_count"] == 1
    assert result["exported_files"] == [str(output)]
