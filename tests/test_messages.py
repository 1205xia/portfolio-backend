import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class MessageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).resolve().parents[1] / "main.py"
        cls.temp = tempfile.TemporaryDirectory()
        cls.original_cwd = os.getcwd()
        os.chdir(cls.temp.name)
        spec = importlib.util.spec_from_file_location("portfolio_test", source)
        cls.app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.app)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.original_cwd)
        cls.temp.cleanup()

    def setUp(self):
        with self.app.closing(self.app.get_db()) as conn, conn:
            conn.execute("DELETE FROM mail_deliveries")

    def test_no_configuration_does_not_send(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(self.app, "send_mail") as send:
            with self.assertRaises(self.app.HTTPException) as raised:
                self.app.add_message(self.app.MessageInput(name="Test", content="Hello"))
            self.assertEqual(raised.exception.status_code, 503)
            send.assert_not_called()

    def test_retry_and_new_id_do_not_duplicate_email(self):
        with patch.dict(os.environ, {"SMTP_HOST": "test", "SMTP_USER": "test", "SMTP_PASSWORD": "test"}), patch.object(self.app, "send_mail") as send:
            first = self.app.add_message(self.app.MessageInput(name="Test", content="Hello", request_id="one"))
            again = self.app.add_message(self.app.MessageInput(name="Test", content="Hello", request_id="one"))
            other = self.app.add_message(self.app.MessageInput(name="Test", content="Hello", request_id="two"))
            self.assertTrue(first["email_sent"])
            self.assertTrue(again["duplicate"])
            self.assertTrue(other["duplicate"])
            send.assert_called_once_with("Test", "Hello")

    def test_uncertain_delivery_is_not_automatically_retried(self):
        with patch.dict(os.environ, {"SMTP_HOST": "test", "SMTP_USER": "test", "SMTP_PASSWORD": "test"}), patch.object(self.app, "send_mail", side_effect=TimeoutError) as send:
            data = self.app.MessageInput(name="Test", content="Hello", request_id="one")
            with self.assertRaises(self.app.HTTPException) as raised:
                self.app.add_message(data)
            self.assertEqual(raised.exception.status_code, 502)
            with self.assertRaises(self.app.HTTPException) as raised:
                self.app.add_message(data)
            self.assertEqual(raised.exception.status_code, 409)
            send.assert_called_once()

    def test_messages_are_private(self):
        self.assertEqual(self.app.get_messages(), [])

    def test_blank_message_is_rejected(self):
        with self.assertRaises(self.app.HTTPException) as raised:
            self.app.add_message(self.app.MessageInput(name=" ", content="Hello"))
        self.assertEqual(raised.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
