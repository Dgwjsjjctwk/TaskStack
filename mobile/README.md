# TaskStack Mobile

## Русский

Мобильный клиент TaskStack для Android: PySide6 и Qt Quick (QML). Использует API и учётные записи настольного приложения; `server.py` не менялся.

**Запуск на компьютере**

```bash
python -m pip install PySide6
python mobile/main.py
```

**Тесты** (не требуют Qt и сети): `python -m unittest tests.test_mobile_api tests.test_mobile_logic tests.test_mobile_strings`

**Файлы**

- `main.py` — точка входа (для Android-сборки файл должен называться так);
- `backend.py` — объект Qt для QML; все запросы выполняются в фоновых потоках;
- `taskstack_api.py` — HTTP-клиент на стандартной библиотеке;
- `taskstack_logic.py` — сортировка, фильтры, статистика, сроки;
- `strings.py` — тексты на русском и английском;
- `qml/Main.qml` — интерфейс;
- `pyproject.toml` — список файлов, которые попадают в APK.

Сборка APK и ограничения: [../docs/MOBILE.md](../docs/MOBILE.md).

## English

The TaskStack client for Android, built with PySide6 and Qt Quick (QML). It uses the desktop app's API and accounts; `server.py` is unchanged.

**Run on a computer**

```bash
python -m pip install PySide6
python mobile/main.py
```

**Tests** (no Qt or network needed): `python -m unittest tests.test_mobile_api tests.test_mobile_logic tests.test_mobile_strings`

**Files**

- `main.py`: entry point (the Android build requires this name);
- `backend.py`: the Qt object exposed to QML; every request runs on a worker thread;
- `taskstack_api.py`: HTTP client, standard library only;
- `taskstack_logic.py`: sorting, filtering, statistics, deadlines;
- `strings.py`: Russian and English texts;
- `qml/Main.qml`: the interface;
- `pyproject.toml`: the list of files bundled into the APK.

Building the APK and known limitations: [../docs/MOBILE.md](../docs/MOBILE.md).
