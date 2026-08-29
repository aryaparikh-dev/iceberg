import json

from iceberg.research.cli import main


def test_validate_data_cli_reports_quality_status(capsys):
    exit_code = main(
        [
            "validate-data",
            "--csv",
            "tests/fixtures/sample_ohlcv.csv",
            "--symbol",
            "ABC",
            "--allow-irregular-spacing",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["quality_status"] == "PASS"
    assert output["number_of_bars"] == 3


def test_walk_forward_cli_outputs_chronological_splits(capsys):
    exit_code = main(
        [
            "walk-forward",
            "--start",
            "2020-01-01",
            "--end",
            "2020-01-30",
            "--train-days",
            "10",
            "--validation-days",
            "5",
            "--test-days",
            "5",
            "--step-days",
            "5",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output[0]["train"]["start"] == "2020-01-01"
    assert output[0]["shuffled"] is False


def test_research_cli_exposes_no_live_brokerage_commands(capsys):
    try:
        main(["--help"])
    except SystemExit:
        pass

    help_text = capsys.readouterr().out
    assert "validate-data" in help_text
    assert "backtest" in help_text
    assert "live" not in help_text.lower()
    assert "broker" not in help_text.lower()
