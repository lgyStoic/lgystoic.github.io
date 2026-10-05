def test_delivery_notification_imports_without_network():
    from tools.content_flow.delivery_notification import send
    assert callable(send)
