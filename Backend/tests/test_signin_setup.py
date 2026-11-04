import importlib.util
from pathlib import Path
import tempfile
import unittest

from dotenv import dotenv_values

spec = importlib.util.spec_from_file_location("signin_setup", Path(__file__).parents[1] / "setup_signin.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class SignInSetupTests(unittest.TestCase):
    def test_saves_provider_values_without_changing_gemini_or_database_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text("# Keep this comment\nGEMINI_API_KEY=test-existing-key\nDATABASE_URL=sqlite:///test.db\nGOOGLE_CLIENT_ID=\n", encoding="utf-8")
            setup.save_settings({"GOOGLE_CLIENT_ID": "client.apps.googleusercontent.com", "OWNER_EMAIL": "owner@gmail.com",
                                 "GITHUB_CLIENT_SECRET": "test-with-'quote-and-$-symbol"}, path)
            values = dotenv_values(path)
            self.assertEqual(values["GEMINI_API_KEY"], "test-existing-key")
            self.assertEqual(values["DATABASE_URL"], "sqlite:///test.db")
            self.assertEqual(values["GOOGLE_CLIENT_ID"], "client.apps.googleusercontent.com")
            self.assertEqual(values["GITHUB_CLIENT_SECRET"], "test-with-'quote-and-$-symbol")
            self.assertIn("# Keep this comment", path.read_text(encoding="utf-8"))

    def test_invalid_step_never_partially_changes_the_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            original = "GEMINI_API_KEY=keep\n"
            path.write_text(original, encoding="utf-8")
            for changes in [{"GITHUB_CLIENT_ID": "client", "MICROSOFT_CLIENT_ID": "wrong"},
                            {"GOOGLE_CLIENT_ID": "not-a-web-client-id"}, {"GITHUB_CLIENT_SECRET": "bad\nINJECTED=yes"},
                            {"GEMINI_API_KEY": "replace"}]:
                with self.assertRaises(ValueError):
                    setup.save_settings(changes, path)
                self.assertEqual(path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
