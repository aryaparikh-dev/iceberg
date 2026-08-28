import pytest

from iceberg.config.settings import default_settings, load_settings, settings_for_strategy
from iceberg.exceptions import ConfigurationError


def test_unsafe_configuration_rejected(tmp_path):
    config = tmp_path / "unsafe.toml"
    config.write_text(
        """
[capital]
maximum_stock_allocation = "0.50"
leverage_allowed = true
"""
    )

    with pytest.raises(ConfigurationError):
        load_settings(config)


def test_strategy_cannot_change_safety_config():
    settings = default_settings()
    readonly = settings_for_strategy(settings)

    with pytest.raises(ConfigurationError):
        readonly.capital.leverage_allowed = True


def test_live_trading_config_cannot_be_enabled_v1(tmp_path):
    config = tmp_path / "live.toml"
    config.write_text(
        """
[testing]
live_trading_enabled = true
"""
    )

    with pytest.raises(ConfigurationError):
        load_settings(config)
