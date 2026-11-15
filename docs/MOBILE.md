# TaskStack Mobile (Android) / Мобильное приложение

Version 1.4.0 · PySide6 + Qt Quick (QML) · talks to the existing TaskStack API.

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

The APK is signed with a debug key, which is fine for installing from a file. Publishing to Google Play needs a release build (an AAB) and your own signing key; that is not set up.

### Locally (Linux or macOS host only)

Requirements from the Qt for Python documentation: Python 3.10+, JDK 17+, NDK r27c (downloaded by the helper script), SDK packages `platform-tools`, `platforms;android-35`, `build-tools;35.0.0`. The deployed app runs CPython 3.14.

```bash
python -m pip install PySide6==6.10.0 qtpip packaging
mkdir android-wheels && cd android-wheels && qtpip download PySide6 --android --arch aarch64 && cd ..
git clone --branch v6.10.0 https://code.qt.io/pyside/pyside-setup
python -m pip install -r pyside-setup/tools/cross_compile_android/requirements.txt
python pyside-setup/tools/cross_compile_android/main.py --download-only --skip-update --auto-accept-license
cd mobile
pyside6-android-deploy --name TaskStack \
  --wheel-pyside ../android-wheels/PySide6-*.whl \
  --wheel-shiboken ../android-wheels/shiboken6-*.whl
```

For an emulator use `--arch x86_64` wheels instead of `aarch64`.

## Известные ограничения / Known limitations

- Needs a connection to the server; no offline mode.
- Android blocks plain `http://` by default, so a self-hosted server must use HTTPS. (An emulator reaches the host computer at `10.0.2.2`, but only over HTTPS unless cleartext traffic is allowed in the app.)
- The sign-in token is kept in the app's private settings; the password is never stored.
- Not in the mobile app: AI tasks, tray, window pinning.
- The Android build chain (`pyside6-android-deploy`) is documented by Qt as young. The workflow in this repository was written from that documentation and has to be run once on GitHub before it can be trusted; see the first-run checklist below.

## First-run checklist (APK)

1. Run **Build Android APK** manually and read the log; fix the first failing step.
2. Install the APK on a phone. If sign-in says "Cannot reach the server" with a normal connection, check that the app has the `INTERNET` permission (`adb shell dumpsys package <package> | grep INTERNET`).
3. Sign in, add a task, tick it, share it with another account, delete it, switch the language, change the server address and back.
4. Check the same account on the desktop app: the tasks must match.
