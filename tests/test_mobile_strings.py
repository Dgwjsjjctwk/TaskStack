import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mobile"))

from strings import STRINGS, translate  # noqa: E402
from version import __version__  # noqa: E402

QML = (ROOT / "mobile" / "qml" / "Main.qml").read_text(encoding="utf-8")
BACKEND = (ROOT / "mobile" / "backend.py").read_text(encoding="utf-8")


class MobileResourcesTests(unittest.TestCase):
    def test_languages_have_identical_keys(self):
        self.assertEqual(set(STRINGS["ru"]), set(STRINGS["en"]))

    def test_placeholders_match_between_languages(self):
        pattern = re.compile(r"\{(\w+)\}")
        for key in STRINGS["ru"]:
            self.assertEqual(
                set(pattern.findall(STRINGS["ru"][key])),
                set(pattern.findall(STRINGS["en"][key])),
                key,
            )

    def test_translate_falls_back_and_formats(self):
        self.assertEqual(translate("en", "overdue", n=3), "overdue: 3")
        self.assertEqual(translate("xx", "sign_in"), STRINGS["ru"]["sign_in"])
        self.assertEqual(translate("en", "no_such_key"), "no_such_key")

    def test_every_key_used_in_qml_exists(self):
        used = set(re.findall(r'\btxt\("(\w+)"\)', QML))
        used |= set(re.findall(r'label: "(\w+)"', QML))
        used |= set(re.findall(r'backend\.tr\("(\w+)"\)', QML))
        missing = sorted(key for key in used if key not in STRINGS["ru"])
        self.assertEqual(missing, [])

    def test_every_key_used_by_backend_exists(self):
        used = set(re.findall(r'self\._t\("(\w+)"', BACKEND))
        missing = sorted(key for key in used if key not in STRINGS["ru"])
        self.assertEqual(missing, [])

    def test_backend_members_used_by_qml_are_defined(self):
        used = set(re.findall(r"\bbackend\.(\w+)", QML))
        defined = set(re.findall(r"def (\w+)\(self", BACKEND))
        signals = set(re.findall(r"^\s+(\w+) = Signal\(", BACKEND, re.M))
        known = defined | signals
        missing = sorted(name for name in used if name not in known)
        self.assertEqual(missing, [])

    def test_qml_method_names_start_with_lowercase(self):
        # QML refuses to load a file declaring a method whose name begins with
        # an upper case letter ("Method names cannot begin with an upper case
        # letter"), which made the first Android build exit right after start.
        names = re.findall(r"\bfunction\s+(\w+)\s*\(", QML)
        self.assertTrue(names)
        self.assertEqual([n for n in names if n[0].isupper()], [])

    def test_qml_braces_are_balanced(self):
        stripped = re.sub(r'"(?:\\.|[^"\\])*"', '""', QML)
        stripped = re.sub(r"//[^\n]*", "", stripped)
        for opening, closing in ("{}", "()", "[]"):
            self.assertEqual(stripped.count(opening), stripped.count(closing), opening)

    def test_mobile_version_matches_release_version(self):
        self.assertEqual(
            (ROOT / "VERSION").read_text(encoding="utf-8").strip(), __version__
        )


if __name__ == "__main__":
    unittest.main()
