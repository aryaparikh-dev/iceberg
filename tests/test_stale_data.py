from datetime import timedelta

import pytest

from iceberg.data.validation import DataValidationError, DataValidator
from tests.test_data_validation import candle
from tests.conftest import ist_datetime


def test_validator_rejects_stale_data():
    with pytest.raises(DataValidationError) as exc:
        DataValidator(max_staleness=timedelta(minutes=5)).validate_candles(
            [candle(timestamp=ist_datetime(9, 0))],
            expected_symbol="ABC",
            now=ist_datetime(10, 0),
        )

    assert exc.value.reason == "STALE_DATA"
