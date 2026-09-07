import unittest
from unittest.mock import Mock, patch

from poly_position_watcher import PositionWatcherService


class WSMessageHandlerTests(unittest.TestCase):
    def make_service(self, **kwargs):
        client = Mock()
        client.builder.funder = "0xuser"
        return PositionWatcherService(client, **kwargs)

    def test_order_processing_with_default_and_disabled_logging(self):
        for kwargs, expected_logs in (({}, 1), ({"print_ws_message": False}, 0)):
            for order_type in ("PLACEMENT", "UPDATE", "CANCELLATION"):
                with self.subTest(kwargs=kwargs, order_type=order_type):
                    service = self.make_service(**kwargs)
                    payload = dict(
                        event_type="order", type=order_type, id="order-1",
                        price="0.5", side="BUY", size_matched="0", timestamp="1",
                    )
                    with patch("poly_position_watcher.position_service.logger") as logger:
                        service._handle_ws_message(payload)
                    self.assertEqual(logger.info.call_count, expected_logs)
                    if expected_logs:
                        logger.info.assert_called_once_with(f"WS message: {order_type}")
                    self.assertEqual(service.get_order("order-1").type, order_type)

    def test_auto_redeem_is_discarded_before_validation(self):
        for enabled in (True, False):
            with self.subTest(print_ws_message=enabled):
                service = self.make_service(print_ws_message=enabled)
                with patch("poly_position_watcher.position_service.logger") as logger:
                    service._handle_ws_message({"event_type": "auto_redeem"})
                self.assertEqual(service.position_store.orders, {})
                self.assertEqual(service.position_store.positions, {})
                logger.info.assert_not_called()

    def test_disabled_logging_still_ingests_trades(self):
        service = self.make_service(print_ws_message=False)
        payload = {"type": "TRADE", "event_type": "trade"}
        with patch("poly_position_watcher.position_service.TradeMessage") as model:
            with patch.object(service.position_store, "append_trade") as append:
                service._handle_ws_message(payload)
        model.assert_called_once_with(**payload)
        append.assert_called_once_with(model.return_value)
