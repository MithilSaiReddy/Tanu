import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "src" / "tanu" / "security.py"
SPEC = importlib.util.spec_from_file_location("tanu_security", MODULE_PATH)
security = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(security)


class SkillNameTests(unittest.TestCase):
    def test_accepts_safe_names(self):
        self.assertEqual(security.safe_skill_name("My-skill_2"), "my-skill_2")

    def test_rejects_path_traversal_and_hidden_names(self):
        for name in ("../outside", "a/b", ".hidden", "", "two words"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                security.safe_skill_name(name)


class OriginTests(unittest.TestCase):
    def test_accepts_native_and_local_origins(self):
        for origin in ("", "http://localhost:7337", "https://127.0.0.1:7337"):
            with self.subTest(origin=origin):
                self.assertTrue(security.origin_is_local(origin))

    def test_rejects_remote_or_malformed_origins(self):
        for origin in ("https://example.com", "file://localhost/tmp", "not a url"):
            with self.subTest(origin=origin):
                self.assertFalse(security.origin_is_local(origin))


class SecretMaskingTests(unittest.TestCase):
    def test_masks_nested_secrets_without_mutating_input(self):
        config = {
            "providers": {"openai": {"api_key": "sk-secret-value"}},
            "tools": {"gmail": {"client_creds": "oauth-secret"}},
            "model": "local-model",
        }
        masked = security.mask_secrets(config)

        self.assertNotIn("secret", masked["providers"]["openai"]["api_key"])
        self.assertNotIn("secret", masked["tools"]["gmail"]["client_creds"])
        self.assertEqual(masked["model"], "local-model")
        self.assertEqual(config["providers"]["openai"]["api_key"], "sk-secret-value")


if __name__ == "__main__":
    unittest.main()
