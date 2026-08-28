from iceberg.execution.brokers import PaperBroker


def test_restart_reconciliation_fails_closed_when_broker_state_unknown(safe_context):
    broker = PaperBroker(safe_context.portfolio, safe_context.guard, safe_context.cost_model)
    broker.mark_state_uncertain("simulated crash during fill")

    assert not broker.reconcile()
    assert safe_context.guard.state.broker_state_known is False
