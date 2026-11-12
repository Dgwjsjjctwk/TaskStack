import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class PackagingTests(unittest.TestCase):
    def test_release_assets_cover_all_requested_platforms(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )

        for expected in (
            'tags:\n      - "v*"',
            "if: startsWith(github.ref, 'refs/tags/')",
            "windows-2025",
            "ubuntu-22.04",
            "macos-15-intel",
            "macos-15",
            "TaskStack-Setup-",
            "AppImage",
            "sha256sum --check",
            "macos-$ARCHITECTURE.dmg",
            "architecture: x86_64",
            "architecture: arm64",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, workflow)

    def test_version_is_shared_by_the_release_and_documentation(self):
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertEqual(version, "1.3.0")
        self.assertIn(f"## {version}", changelog)
        self.assertIn(f"Version: {version}", readme)
        self.assertIn("Установка", readme)
        self.assertIn("Installation", readme)
        self.assertIn("Сборка из исходного кода", readme)
        self.assertIn("Build from source", readme)

    def test_platform_package_definitions_are_present(self):
        required_files = (
            ROOT / "packaging" / "windows" / "TaskStack.iss",
            ROOT / "packaging" / "linux" / "AppRun",
            ROOT / "packaging" / "linux" / "taskstack.desktop",
            ROOT / "packaging" / "linux" / "taskstack.svg",
        )

        for file_path in required_files:
            with self.subTest(path=file_path.relative_to(ROOT)):
                self.assertTrue(file_path.is_file())

        windows_installer = required_files[0].read_text(encoding="utf-8")
        linux_desktop = required_files[2].read_text(encoding="utf-8")
        macos_spec = (ROOT / "TaskManager.spec").read_text(encoding="utf-8")
        self.assertIn("ArchitecturesInstallIn64BitMode=x64", windows_installer)
        self.assertIn("AppVersion={#AppVersion}", windows_installer)
        self.assertIn("Exec=TaskStack", linux_desktop)
        self.assertIn('name="TaskStack.app"', macos_spec)


if __name__ == "__main__":
    unittest.main()
