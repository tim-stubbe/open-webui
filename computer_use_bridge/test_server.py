import unittest
from http import HTTPStatus

from server import RequestError, validate_action


class ValidateActionTests(unittest.TestCase):
    def test_accepts_supported_actions(self):
        self.assertEqual(validate_action({'action': 'click', 'x': 12, 'y': 34})['action'], 'click')
        self.assertEqual(validate_action({'action': 'type', 'text': 'Hallo'})['text'], 'Hallo')
        self.assertEqual(validate_action({'action': 'scroll', 'delta_y': -250})['delta_y'], -250)
        self.assertEqual(validate_action({'action': 'browser_click', 'selector': '#submit'})['selector'], '#submit')
        self.assertEqual(
            validate_action({'action': 'browser_navigate', 'url': 'https://example.com'})['action'],
            'browser_navigate',
        )

    def test_rejects_unknown_action(self):
        with self.assertRaises(RequestError) as caught:
            validate_action({'action': 'shell', 'command': 'whoami'})
        self.assertEqual(caught.exception.status, HTTPStatus.BAD_REQUEST)

    def test_rejects_invalid_coordinates_and_large_text(self):
        with self.assertRaises(RequestError):
            validate_action({'action': 'click', 'x': -1, 'y': 4})
        with self.assertRaises(RequestError):
            validate_action({'action': 'type', 'text': 'x' * 4001})
        with self.assertRaises(RequestError):
            validate_action({'action': 'browser_navigate', 'url': 'file:///etc/passwd'})


if __name__ == '__main__':
    unittest.main()
