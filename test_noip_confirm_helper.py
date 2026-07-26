import unittest

from tools.noip_confirm_helper import classify_response, extract_urls_from_text


class NoIpConfirmHelperTests(unittest.TestCase):
    def test_extracts_noip_confirmation_links(self):
        body = """
        <a href="https://www.noip.com/confirm-hostname?hostname=ntcnas.myftp.org&utm_source=email">Confirm</a>
        https://example.com/confirm
        """
        self.assertEqual(
            extract_urls_from_text(body, "ntcnas.myftp.org"),
            ["https://www.noip.com/confirm-hostname?hostname=ntcnas.myftp.org"],
        )

    def test_ignores_unrelated_noip_links(self):
        body = "https://www.noip.com/account https://www.noip.com/support"
        self.assertEqual(extract_urls_from_text(body, "ntcnas.myftp.org"), [])

    def test_classifies_success_text(self):
        status, reason = classify_response(
            "Your hostname has been confirmed.",
            "https://www.noip.com/confirm",
            200,
        )
        self.assertEqual(status, "confirmed")
        self.assertIn("successful", reason)

    def test_classifies_captcha_as_manual(self):
        status, reason = classify_response(
            "Please complete this recaptcha challenge.",
            "https://www.noip.com/confirm",
            200,
        )
        self.assertEqual(status, "manual_required")
        self.assertIn("CAPTCHA", reason)


if __name__ == "__main__":
    unittest.main()
