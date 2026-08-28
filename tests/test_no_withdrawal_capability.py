from iceberg.execution.brokers import BrokerInterface, LiveBrokerStub, PaperBroker


def test_trading_engine_exposes_no_withdrawal_or_bank_transfer_methods(safe_context):
    broker = PaperBroker(safe_context.portfolio, safe_context.guard, safe_context.cost_model)
    live = LiveBrokerStub()

    forbidden = [
        "withdraw",
        "bank_transfer",
        "upi_transfer",
        "add_beneficiary",
        "change_bank_account",
        "external_transfer",
    ]

    for name in forbidden:
        assert not hasattr(BrokerInterface, name)
        assert not hasattr(broker, name)
        assert not hasattr(live, name)
