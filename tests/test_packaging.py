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

        self.assertEqual(version, "1.4.0")
        self.assertIn(f"## {version}", changelog)
        self.assertIn(f"Version: {version}", readme)
        self.assertIn("Установка", readme)
        self.assertIn("Installation", readme)
        self.assertIn("Сборка из исходного кода", readme)
        self.assertIn("Build from source", readme)

    def test_android_build_is_separate_from_the_desktop_release(self):
        android = (ROOT / ".github" / "workflows" / "android.yml").read_text(
            encoding="utf-8"
        )
        desktop = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("pyside6-android-deploy", android)
        # Qt for Python < 6.12 wheels target CPython 3.11 while the app runs 3.14,
        # and qtpip serves only commercial wheels (it downloads nothing otherwise).
        self.assertIn('PYSIDE_VERSION: "6.12.0"', android)
        self.assertIn("cp310-abi3-android_aarch64", android)
        self.assertNotIn("cp311-cp311-android", android)
        self.assertIn('python-version: "3.11"', android)
        self.assertNotIn("qtpip", android)
        self.assertIn("download.qt.io/official_releases/QtForPython", android)
        self.assertIn("android-aarch64.apk", android)
        self.assertNotIn("android", desktop.lower())
        for name in ("main.py", "backend.py", "qml/Main.qml"):
            with self.subTest(file=name):
                self.assertTrue((ROOT / "mobile" / name).is_file())

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

    def test_desktop_build_finds_the_client_shared_with_android(self):
        spec = (ROOT / "TaskManager.spec").read_text(encoding="utf-8")
        self.assertIn("import os", spec)
        self.assertIn("os.path.join(SPECPATH, 'mobile')", spec)
        self.assertTrue((ROOT / "mobile" / "taskstack_api.py").is_file())
        # The Android app bundles the same file.
        pyproject = (ROOT / "mobile" / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("taskstack_api.py", pyproject)


if __name__ == "__main__":
    unittest.main()
