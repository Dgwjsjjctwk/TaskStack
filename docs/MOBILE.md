# TaskStack Mobile (Android) / Мобильное приложение

Version 1.4.1 · PySide6 + Qt Quick (QML) · talks to the existing TaskStack API.

## Что это / What it is

**RU.** Мобильный клиент в папке `mobile/`. Те же аккаунты и тот же сервер, что у настольного приложения (`server.py` не менялся). Настольное приложение остаётся на PyQt6; мобильное использует PySide6, потому что именно он официально поддерживает Android (`pyside6-android-deploy`). Классы виджетов (`QWidget`) на телефоне неудобны, поэтому интерфейс написан на QML.

**EN.** The client lives in `mobile/`. Same accounts and server as the desktop app (`server.py` is unchanged). The desktop app stays on PyQt6; the mobile app uses PySide6 because that is the binding with official Android deployment. The interface is QML instead of `QWidget`, which is not usable on a phone.

## Структура / Layout

| File | Role |
| --- | --- |
| `mobile/main.py` | Entry point (must be called `main.py` for the Android tool). |
| `mobile/backend.py` | Qt object exposed to QML; runs every request on a worker thread. |
| `mobile/taskstack_api.py` | HTTP client, standard library only, no Qt. |
| `mobile/taskstack_logic.py` | Sorting, filtering, statistics, deadlines, no Qt. |
| `mobile/strings.py` | Russian and English texts. |
| `mobile/qml/Main.qml` | The whole interface. |
| `mobile/pyproject.toml` | List of files bundled into the APK. |
| `.github/workflows/android.yml` | APK build in GitHub Actions. |

## Проверка на компьютере / Run it on a computer

Fastest way to see and check the interface before building an APK:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install PySide6
python mobile/main.py
```

The window is phone-sized (360×720). Sign in with a desktop account. Settings (⚙) hold the server address and language.

## Тесты / Tests

The API client, the logic and the string tables are covered by tests that need no Qt and no network:

```bash
python -m unittest tests.test_mobile_api tests.test_mobile_logic tests.test_mobile_strings
```

## Сборка APK / Building the APK

### In GitHub Actions (recommended)

`android.yml` runs on a `v*` tag, on a pull request touching `mobile/`, or by hand (**Actions → Build Android APK → Run workflow**). It produces `TaskStack-<version>-android-aarch64.apk` as a build artifact and, for a tag, attaches it to the release. It is a separate workflow so that a problem in the Android toolchain never blocks the desktop installers.

**Where to get the APK.** For a pull request or a manual run, open the run in the **Actions** tab and download the artifact `taskstack-android-aarch64` at the bottom of the page (a zip with the APK inside). For a `v*` tag the APK is also attached to the GitHub release.

**Build status.** The workflow completes on GitHub Actions in about 6 minutes (a first build with Qt for Python 6.10.0 succeeded, but its APK closed right after launch; see the known limitations). The APK targets ARM64 phones (`arm64-v8a`), needs Android 5.0 or newer (API 21), declares the `INTERNET` permission, and bundles the Qt Quick Controls with the Material style that the interface uses. **Checked on a device:** on a Samsung phone the app starts, signs in to the server, and a task created on the phone appears in the desktop app. Deleting, sharing, switching language and changing the server address have not been checked on a device yet.

**Cosmetic limits of the generated APK.** The internal version name is `0.1` and the icon is the default Qt for Python one, because `pyside6-android-deploy` does not take them from `VERSION`. The package name is `org.taskstack.taskstack`.

The APK is signed with a debug key, which is fine for installing from a file. Publishing to Google Play needs a release build (an AAB) and your own signing key; that is not set up.

### Locally (Linux or macOS host only)

Requirements: a host Python 3.10 to 3.14 (it only runs the tools), JDK 17 or newer, NDK r28c and the SDK packages (both downloaded by the helper script). The Android wheels of Qt for Python 6.12.0 use Python's stable ABI (`cp310-abi3`), so they run on the CPython 3.14 that python-for-android builds into the app. Do not use the 6.10 or 6.11 wheels: they target CPython 3.11 and the app closes right after the splash screen.

```bash
python -m pip install PySide6==6.12.0 packaging
python -m pip install -r "$(python -c 'import os, PySide6; print(os.path.join(os.path.dirname(PySide6.__file__), "scripts", "requirements-android.txt"))')"
mkdir android-wheels && cd android-wheels
base=https://download.qt.io/official_releases/QtForPython
tag=6.12.0-6.12.0-cp310-abi3-android_aarch64.whl
curl -fLO "$base/pyside6/pyside6-$tag"
curl -fLO "$base/shiboken6/shiboken6-$tag"
cd ..
git clone --branch v6.12.0 https://code.qt.io/pyside/pyside-setup
python -m pip install -r pyside-setup/tools/cross_compile_android/requirements.txt
python pyside-setup/tools/cross_compile_android/main.py --download-only --skip-update --auto-accept-license
cd mobile
pyside6-android-deploy --name TaskStack \
  --wheel-pyside ../android-wheels/pyside6-$tag \
  --wheel-shiboken ../android-wheels/shiboken6-$tag
```

For an emulator use the `android_x86_64` wheels instead of `android_aarch64`. `qtpip` is not needed: it only serves commercial Qt licenses.

## Известные ограничения / Known limitations

- Needs a connection to the server; no offline mode.
- Android blocks plain `http://` by default, so a self-hosted server must use HTTPS. (An emulator reaches the host computer at `10.0.2.2`, but only over HTTPS unless cleartext traffic is allowed in the app.)
- The sign-in token is kept in the app's private settings; the password is never stored.
- Not in the mobile app: AI tasks, tray, window pinning.
- The Android build chain (`pyside6-android-deploy`) is young and its version pins matter: keep Qt for Python at 6.12.0 or newer, because its tool pins python-for-android and its Android wheels are `abi3`. Qt for Python 6.10.0 produced an APK that closed right after start.

## If the app closes right after it starts

If the interface cannot be loaded, the app now stays open and prints the reason on a dark screen (QML error text) instead of closing silently. Send that text (a screenshot is enough) when reporting the problem. The first Android build closed immediately because `Main.qml` declared a function whose name began with an upper case letter, which QML forbids; a test now guards against it.

## First-run checklist (APK)

1. Run **Build Android APK** manually and read the log; fix the first failing step.
2. Install the APK on a phone. If sign-in says "Cannot reach the server" with a normal connection, check that the app has the `INTERNET` permission (`adb shell dumpsys package <package> | grep INTERNET`).
3. Sign in, add a task, tick it, share it with another account, delete it, switch the language, change the server address and back.
4. Check the same account on the desktop app: the tasks must match.
