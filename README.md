# TaskStack

TaskStack — настольный менеджер задач для Windows на Python и PyQt6. Приложение позволяет создавать задачи с категорией, приоритетом и сроком, искать и фильтровать список, отмечать выполнение, а также закреплять окно поверх других окон и сворачивать его в системный трей.

**Текущая версия: 1.0.0**

## Запуск из исходного кода

Требуются Windows и Python 3.11 или новее.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

При первом запуске приложение создаёт локальный `config.json`. Список задач и пользовательские настройки сохраняются в хранилище настроек Windows через `QSettings`.

## Сборка Windows-приложения

```powershell
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean --distpath release-build\dist --workpath release-build\work TaskManager.spec
```

Готовый исполняемый файл появится в `release-build\dist\TaskManager.exe`. Для запуска `.exe` Python устанавливать не нужно.

## Релизы

Сборки Windows и заметки к выпуску публикуются на странице [Releases](https://github.com/Dgwjsjjctwk/TaskStack/releases).

## Лицензия

Лицензия в этом выпуске не предоставляется; права на исходный код сохраняются за его правообладателем.
