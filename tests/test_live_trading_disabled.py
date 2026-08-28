import pytest

from iceberg.config.settings import default_settings
from iceberg.domain.models import TradeProposal
from iceberg.exceptions import LiveTradingDisabledError
from iceberg.execution.brokers import LiveBrokerStub

from tests.conftest import D


def test_default_configuration_disables_live_trading():
    settings = default_settings()

    assert settings.testing.paper_trading_enabled is True
    assert settings.testing.live_trading_enabled is False


def test_live_broker_stub_raises_for_any_order_submission():
    live = LiveBrokerStub()

    with pytest.raises(LiveTradingDisabledError):
        live.submit_order(TradeProposal.buy("ABC", price=D("10"), decision_id="live"), None, "live-key")
