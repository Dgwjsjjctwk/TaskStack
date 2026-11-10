import tempfile
import unittest
from pathlib import Path

from PyQt6.QtCore import QStandardPaths

QStandardPaths.setTestModeEnabled(True)

from app_paths import (
    app_data_directory,
    config_directory,
    get_writable_directory,
    migrate_legacy_config,
)
from config import (
    DEFAULT_SERVER_URL,
    CONFIG_FILE,
    is_legacy_taskstack_config,
    resolve_server_url,
)


class AppPathsTests(unittest.TestCase):
    def test_application_files_use_platform_data_folders(self):
        config_path = config_directory()
        data_path = app_data_directory()

        self.assertTrue(CONFIG_FILE.is_absolute())
        self.assertEqual(CONFIG_FILE.parent, config_path)
        self.assertNotEqual(config_path, Path.cwd())
        self.assertNotEqual(data_path, Path.cwd())
        self.assertTrue(config_path.is_dir())
        self.assertTrue(data_path.is_dir())

    def test_writable_directory_uses_the_platform_location(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            expected = Path(temporary_directory) / "config" / "TaskStack"
            directory = get_writable_directory(
                QStandardPaths.StandardLocation.AppConfigLocation,
                lambda _location: str(expected),
            )
            self.assertEqual(directory, expected)
            self.assertTrue(directory.is_dir())

    def test_legacy_config_is_copied_without_removing_the_source(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            legacy = root / "legacy" / "config.json"
            destination = root / "new" / "config.json"
            legacy.parent.mkdir()
            legacy.write_text(
                '{"organization_name":"MTUCI",'
                '"application_name":"TaskManagerLab",'
                '"server_url":"https://company.example"}',
                encoding="utf-8",
            )

            migrated = migrate_legacy_config(legacy, destination)

            self.assertTrue(migrated)
            self.assertEqual(destination.read_text(encoding="utf-8"), legacy.read_text(encoding="utf-8"))
            self.assertTrue(legacy.exists())

    def test_unrelated_current_directory_config_is_not_migrated(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            legacy = root / "config.json"
            destination = root / "new" / "config.json"
            legacy.write_text('{"server_url": "https://other.example"}', encoding="utf-8")

            migrated = migrate_legacy_config(
                legacy,
                destination,
                lambda path: "application_name" in path.read_text(encoding="utf-8"),
            )

            self.assertFalse(migrated)
            self.assertFalse(destination.exists())

    def test_legacy_config_does_not_replace_existing_user_config(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            legacy = root / "legacy.json"
            destination = root / "config.json"
            legacy.write_text("legacy", encoding="utf-8")
            destination.write_text("current", encoding="utf-8")

            self.assertFalse(migrate_legacy_config(legacy, destination))
            self.assertEqual(destination.read_text(encoding="utf-8"), "current")

    def test_only_taskstack_config_is_eligible_for_migration(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_file = Path(temporary_directory) / "config.json"
            config_file.write_text(
                '{"organization_name":"MTUCI",'
                '"application_name":"TaskManagerLab",'
                '"server_url":"https://company.example"}',
                encoding="utf-8",
            )
            self.assertTrue(is_legacy_taskstack_config(config_file))

            config_file.write_text('{"server_url":"https://other.example"}', encoding="utf-8")
            self.assertFalse(is_legacy_taskstack_config(config_file))

    def test_server_url_environment_override_takes_precedence_and_is_normalized(self):
        self.assertEqual(
            resolve_server_url(
                {"server_url": "https://saved.example/"},
                {"TASKSTACK_SERVER_URL": " https://custom.example/// "},
            ),
            "https://custom.example",
        )

    def test_legacy_local_server_url_falls_back_to_production(self):
        self.assertEqual(
            resolve_server_url(
                {"server_url": "http://localhost:8000"},
                {},
            ),
            DEFAULT_SERVER_URL,
        )

    def test_missing_saved_server_url_uses_production(self):
        self.assertEqual(resolve_server_url({}, {}), DEFAULT_SERVER_URL)

    def test_custom_saved_server_url_is_preserved(self):
        self.assertEqual(
            resolve_server_url(
                {"server_url": "https://company.example/"},
                {},
            ),
            "https://company.example",
        )


if __name__ == "__main__":
    unittest.main()
