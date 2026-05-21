from pathlib import Path

import google_sheets_mirror as mirror


def test_load_report_items_parses_final_markdown(tmp_path, monkeypatch):
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    report = report_dir / "20260521_morning_report.md"
    report.write_text(
        "\n".join(
            [
                "[보고 기사]",
                "",
                "※첫 기사 제목/연합",
                "-첫 기사 요약.",
                "https://example.com/one",
                "",
                "※둘째 기사/중앙 온라인",
                "-둘째 기사 요약.",
                "https://example.com/two",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mirror, "SAFE_DIR", Path(tmp_path))

    items = mirror.load_report_items("20260521")
    rows = mirror.report_rows_from_report("20260521", items)

    assert [item["url"] for item in items] == ["https://example.com/one", "https://example.com/two"]
    assert len(rows) == 2
    assert rows[0] == ["20260521", "첫 기사 제목", "연합", "selected", "", "", "첫 기사 요약."]

