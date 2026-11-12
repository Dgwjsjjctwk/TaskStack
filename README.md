# TaskStack

Настольный менеджер задач на Python и PyQt6: задачи по категориям, приоритетам и срокам, поиск, совместное использование задач и групп, закрепление окна и системный трей (если он доступен в рабочем окружении).

Desktop task manager built with Python and PyQt6: organize tasks by category, priority, and deadline; search; share tasks and groups; pin the window; and use the system tray when the desktop provides one.

**Версия / Version: 1.2.0**

## Установка

### Простая установка

Скачайте установщик для своей платформы со страницы [GitHub Releases](https://github.com/Dgwjsjjctwk/TaskStack/releases). Готовые сборки по умолчанию подключаются к существующему production API; устанавливать Python или настраивать сервер не нужно.

| Платформа | Файл | Установка и запуск |
| --- | --- | --- |
| Windows 10/11, x64 | `TaskStack-Setup-1.2.0-win-x64.exe` | Запустите Setup, затем откройте TaskStack из меню «Пуск» или с рабочего стола. |
| Linux, x64 | `TaskStack-1.2.0-linux-x86_64.AppImage` | Выполните `chmod +x TaskStack-*.AppImage`, затем `./TaskStack-*.AppImage`. |
| macOS, Intel | `TaskStack-1.2.0-macos-x86_64.dmg` | Откройте DMG и перетащите TaskStack в Applications. |
| macOS, Apple Silicon | `TaskStack-1.2.0-macos-arm64.dmg` | Откройте DMG и перетащите TaskStack в Applications. |

Приложения в DMG для macOS не подписаны и не нотарифицированы. При первом запуске macOS Gatekeeper может показать предупреждение. Для подписанной и нотарифицированной публикации нужны учётные данные Apple Developer, которые не настроены для этого проекта.

При первом запуске настройки сохраняются в пользовательские папки операционной системы. Старый `config.json` из прежней рабочей папки копируется в новое расположение без удаления оригинала. Настройки окна продолжают храниться через стандартный для платформы механизм `QSettings`.

### Сборка из исходного кода

Нужен Python 3.11 или новее. В каталоге репозитория создайте виртуальное окружение, установите зависимости клиента и запустите приложение:

```powershell
# Windows PowerShell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

```sh
# Linux или macOS
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

### Свой сервер API и база данных

Если не задана переменная `TASKSTACK_SERVER_URL`, клиент использует `https://taskstack-o9vw.onrender.com`. Чтобы команда использовала собственный API TaskStack, задайте адрес **перед запуском клиента**. Поведение авторизации, совместных задач и групп при этом не меняется.

```powershell
# Windows PowerShell
$env:TASKSTACK_SERVER_URL = "https://tasks.example.com"
python main.py
```

```sh
# Linux или macOS
TASKSTACK_SERVER_URL="https://tasks.example.com" python3 main.py
```

Для локальной разработки укажите `http://127.0.0.1:8000`. Сохранённый пользовательский адрес сервера сохраняется; старый сохранённый localhost URL по-прежнему заменяется на production URL, если переменная окружения не задана.

Исходный код API находится в `server.py`, а его зависимости отделены от зависимостей клиента. Для локальной разработки запустите сервер в одном терминале, а клиент — в другом:

```sh
python -m pip install -r requirements-server.txt
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

Локальный MCP использует `http://127.0.0.1:8000` как публичный issuer. Если сервер запущен на другом хосте или порту, задайте `TASKSTACK_PUBLIC_URL` точно равным адресу, который использует MCP-клиент, чтобы OAuth и проверка audience совпадали.

Для локального API SQLite используется по умолчанию. Для размещённого сервиса укажите `DATABASE_URL` с адресом PostgreSQL в секретах/переменных среды хостинг-провайдера и задайте `TASKSTACK_REQUIRE_DATABASE_URL=true`, чтобы запретить переход на эфемерную SQLite. Не добавляйте строки подключения и учётные данные в git. Перед сетевым доступом настройте HTTPS на платформе или reverse proxy. Этот выпуск не добавляет функции API и не выполняет миграцию данных; локальная база SQLite автоматически не переносится.

### Удалённый MCP (функция будущего выпуска, пока недоступна)

Ветка разработки добавляет MCP endpoint в существующий API; он не доступен на production-сервисе версии 1.2.0 до отдельного выпуска и развёртывания. После включения endpoint будет `https://taskstack-o9vw.onrender.com/mcp` (если публичный URL сервиса не изменится). Для Claude Code клиент настраивается на URL endpoint, например:

```sh
claude mcp add --transport http taskstack https://taskstack-o9vw.onrender.com/mcp
```

Авторизация проходит на странице TaskStack: войдите существующей учётной записью и отдельно подтвердите доступ для каждого MCP-клиента. Не помещайте пароль или скопированный bearer token в конфигурацию клиента. Разрешения ограничиваются чтением, записью и удалением; для удаления клиент должен показать preview и ссылку подтверждения. Пользователь открывает ссылку, повторно входит в TaskStack и подтверждает удаление именно этой задачи; один MCP-вызов `confirm=true` без такого действия сервер отклоняет.

**Совместимость:** проверены OAuth-поток, Streamable HTTP handshake и вызовы tools через официальный MCP Python SDK 2.3.0 с FastAPI TestClient; сторонние приложения пока не тестировались. Claude Code документирует удалённые HTTP-серверы и OAuth, поэтому ожидается совместимость, но конкретная версия клиента не проверялась. OpenAI Responses API документирует удалённые MCP-серверы, однако его API-вызов требует передавать access token приложением; безопасная пользовательская OAuth-интеграция и приложение ChatGPT не проверялись. Документация DeepSeek описывает API function calling, но не нативный удалённый MCP-клиент; прямую совместимость DeepSeek API не заявляем. Другие клиенты ожидаются совместимыми только если поддерживают Streamable HTTP и стандартное OAuth-обнаружение/PKCE.

### Локальная сборка установщиков

Установите инструменты сборки командой `python -m pip install -r requirements-build.txt` и собирайте приложение на целевой ОС (PyInstaller не выполняет кросс-компиляцию):

```powershell
# Windows: создаёт release-build\dist\TaskStack.exe
python -m PyInstaller --noconfirm --clean --distpath release-build\dist --workpath release-build\work TaskManager.spec
```

```sh
# Linux: создаёт release-build/dist/TaskStack
# macOS: создаёт release-build/dist/TaskStack.app
python -m PyInstaller --noconfirm --clean --distpath release-build/dist --workpath release-build/work TaskManager.spec
```

Для локальной сборки Windows Setup установите Inno Setup и выполните `ISCC.exe /DAppVersion=1.2.0 packaging\windows\TaskStack.iss` после сборки executable. GitHub Actions упаковывает Windows executable с помощью Inno Setup и собирает Linux/macOS на соответствующих runner-ах. Linux AppImage предназначен для x64; DMG собираются отдельно для Intel и Apple Silicon.

## Installation

### Beginner installation

Download the installer for your platform from [GitHub Releases](https://github.com/Dgwjsjjctwk/TaskStack/releases). Ready-to-use builds connect to the existing production API by default; Python and server setup are not required.

| Platform | File | Install and launch |
| --- | --- | --- |
| Windows 10/11, x64 | `TaskStack-Setup-1.2.0-win-x64.exe` | Run Setup, then launch TaskStack from the Start menu or desktop shortcut. |
| Linux, x64 | `TaskStack-1.2.0-linux-x86_64.AppImage` | Run `chmod +x TaskStack-*.AppImage`, then `./TaskStack-*.AppImage`. |
| macOS, Intel | `TaskStack-1.2.0-macos-x86_64.dmg` | Open the DMG and drag TaskStack to Applications. |
| macOS, Apple Silicon | `TaskStack-1.2.0-macos-arm64.dmg` | Open the DMG and drag TaskStack to Applications. |

The apps in the macOS DMGs are not code-signed or notarized. macOS Gatekeeper may show a warning on first launch. Signed and notarized distribution requires Apple Developer credentials, which are not configured for this project.

On first launch, settings are stored in the operating system's per-user application folders. An existing `config.json` in the old working directory is copied to the new location without removing the original. Window settings continue to use the platform's standard `QSettings` storage.

### Build from source

Install Python 3.11 or newer. From the repository directory, create a virtual environment, install the client dependencies, and run TaskStack:

```powershell
# Windows PowerShell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

```sh
# Linux or macOS
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

### Self-host the API and database

Unless `TASKSTACK_SERVER_URL` is set, the client uses `https://taskstack-o9vw.onrender.com`. To point a team build at its own TaskStack API, set the URL **before launching the client**. Authentication, shared tasks, and groups continue to work as before.

```powershell
# Windows PowerShell
$env:TASKSTACK_SERVER_URL = "https://tasks.example.com"
python main.py
```

```sh
# Linux or macOS
TASKSTACK_SERVER_URL="https://tasks.example.com" python3 main.py
```

For local development, use `http://127.0.0.1:8000`. A saved custom server URL is retained; the legacy saved localhost URL continues to fall back to production unless the environment variable is set.

The API source is `server.py`, and its dependencies are separate from the desktop client's. For local development, start the API in one terminal and the client in another:

```sh
python -m pip install -r requirements-server.txt
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

Local MCP uses `http://127.0.0.1:8000` as its public issuer. If the server uses another host or port, set `TASKSTACK_PUBLIC_URL` to the exact address used by the MCP client so OAuth discovery and audience validation agree.

Local API development uses SQLite by default. For a hosted service, set `DATABASE_URL` to a PostgreSQL connection string in the hosting provider's secret/environment settings and set `TASKSTACK_REQUIRE_DATABASE_URL=true` to prevent fallback to ephemeral SQLite. Do not commit connection strings or credentials. Configure HTTPS at the hosting platform or reverse proxy before allowing network access. This release adds no API features or data migration; local SQLite data is not transferred automatically.

### Remote MCP (future feature; not available yet)

The development branch adds an MCP endpoint to the existing API; it is not available on the v1.2.0 production service until a separate release and deployment. Once enabled, the endpoint will be `https://taskstack-o9vw.onrender.com/mcp` (unless the service's public URL changes). For Claude Code, configure the endpoint URL, for example:

```sh
claude mcp add --transport http taskstack https://taskstack-o9vw.onrender.com/mcp
```

Authorization takes place on a TaskStack page: sign in with an existing account and approve a separate grant for each MCP client. Do not put a password or copied bearer token in client configuration. Access is scoped to read, write, and delete; for deletion, the client must show the preview and confirmation link. The user opens the link, signs into TaskStack again, and approves deletion of that exact task; an MCP `confirm=true` call without this action is rejected by the server.

**Compatibility:** OAuth, the Streamable HTTP handshake, and tool calls are tested with the official MCP Python SDK 2.3.0 and FastAPI TestClient; third-party applications have not been tested. Claude Code documents remote HTTP servers and OAuth, so interoperability is expected but no specific client version was tested. The OpenAI Responses API documents remote MCP servers, but its API request requires the application to provide an access token; the per-user OAuth handoff and ChatGPT app have not been tested. DeepSeek documentation describes API function calling but not a native remote MCP client, so direct compatibility with the DeepSeek API is not claimed. Other clients are expected to interoperate only if they support Streamable HTTP and standard OAuth discovery/PKCE.

### Build installers locally

Install build dependencies with `python -m pip install -r requirements-build.txt` and build on the target operating system (PyInstaller does not cross-compile):

```powershell
# Windows: creates release-build\dist\TaskStack.exe
python -m PyInstaller --noconfirm --clean --distpath release-build\dist --workpath release-build\work TaskManager.spec
```

```sh
# Linux: creates release-build/dist/TaskStack
# macOS: creates release-build/dist/TaskStack.app
python -m PyInstaller --noconfirm --clean --distpath release-build/dist --workpath release-build/work TaskManager.spec
```

To build Windows Setup locally, install Inno Setup and run `ISCC.exe /DAppVersion=1.2.0 packaging\windows\TaskStack.iss` after building the executable. GitHub Actions wraps the Windows executable with Inno Setup and builds Linux/macOS on their respective runners. The Linux AppImage is x64; DMGs are built separately for Intel and Apple Silicon.

## Релизы / Releases

Загрузки установщиков и заметки к выпуску / Installer downloads and release notes: [GitHub Releases](https://github.com/Dgwjsjjctwk/TaskStack/releases). Подробности версии 1.2.0 / See the [1.2.0 changelog](CHANGELOG.md).

## Лицензия / License

Лицензия в этом выпуске не предоставляется; права на исходный код сохраняются за его правообладателем. / No license is granted with this release; all rights to the source code remain with its owner.
