def test_alert_module_imports_without_network():
    from tools.content_flow import handoff_alert
    assert callable(handoff_alert.send)
