# Changelog / История изменений

## Unreleased / Не выпущено

### Русский

- Имена пользователей теперь уникальны без учёта регистра: «Иван», «иван» и «ИВАН» — одно имя. Регистрация с занятым именем отклоняется при любом пароле. Вход тоже не зависит от регистра имени (пароль по-прежнему должен совпадать точно).
- Имена нормализуются (NFKC), а невидимые и управляющие символы в имени запрещены, чтобы нельзя было создать двойника, неотличимого на экране.
- После 5 неверных паролей подряд вход для этого имени блокируется на 5 минут (ответ 429 с `Retry-After`); то же действует для входа через MCP/OAuth. Счётчик хранится в памяти процесса и сбрасывается при перезапуске.
- При первом запуске существующие аккаунты получают служебный ключ имени. Если в старой базе уже есть имена, различающиеся только регистром, уникальный индекс не создаётся (в лог пишется предупреждение), старые аккаунты продолжают работать, а новые дубликаты блокируются проверкой при регистрации.
- Названия колонок в запросе обновления задачи строятся из фиксированного списка (укрепление защиты от SQL-инъекций; поведение не изменилось).
- Настольное приложение: кнопка «Очистить всё» заменена на «Очистить завершённые». Она удаляет только ваши завершённые задачи, в вопросе указано их число; активные и чужие задачи не затрагиваются.
- Сервер возвращает задачи в стабильном порядке (по номеру, то есть по времени создания).
- Бесплатный хостинг усыпляет сервер, и первый запрос после простоя может занять около минуты. Вход и регистрация на компьютере ждут до 60 секунд и сообщают об этом на кнопке, мобильный клиент ждёт ответа до 60 секунд (раньше 10).
- Добавлен `GET /ping` — проверка доступности без обращения к базе данных. Индикатор связи на компьютере теперь спрашивает `/ping` (на старых серверах `/health`), раз в 30 секунд вместо 5 и не опрашивает сервер, пока окно скрыто в трей или свёрнуто; открытые клиенты больше не мешают серверу и базе уснуть. `/health` по-прежнему проверяет базу.
- Удалён дублирующийся код виджета задачи в `main_window.py` (поведение не изменилось).
- Добавлен workflow `tests.yml`: все тесты запускаются при каждом pull request и push в `main`.

### English

- Usernames are now unique regardless of letter case: "Ivan", "ivan" and "IVAN" are the same name. Registering a taken name is refused whatever the password. Sign-in also ignores the case of the name (the password must still match exactly).
- Names are normalized (NFKC) and invisible or control characters are refused, so a look-alike account that cannot be told apart on screen cannot be created.
- After 5 wrong passwords in a row, sign-in for that name is locked for 5 minutes (HTTP 429 with `Retry-After`); this also covers MCP/OAuth sign-in. The counter lives in process memory and resets on restart.
- On first start, existing accounts get an internal name key. If an old database already holds names that differ only by case, the unique index is not built (a warning is logged), the old accounts keep working, and new duplicates are blocked by the check at registration.
- Column names in the task update query now come from a fixed list (SQL injection hardening; no behaviour change).
- Desktop app: the "Clear All" button is now "Clear Completed". It deletes only your own completed tasks, the confirmation shows how many, and active tasks or other people's tasks are never touched.
- The server returns tasks in a stable order (by id, which is creation order).
- The free hosting plan puts the server to sleep, and the first request after idle time can take about a minute. Desktop sign-in and registration now wait up to 60 seconds and say so on the button, and the mobile client waits up to 60 seconds for an answer (it was 10).
- Added `GET /ping`, a liveness check that never touches the database. The desktop network indicator now asks `/ping` (`/health` on older servers), every 30 seconds instead of 5, and does not poll while the window is hidden in the tray or minimized; open clients no longer keep the server and its database awake. `/health` still checks the database.
- Removed duplicated task-widget code from `main_window.py` (no behaviour change).
- Added a `tests.yml` workflow: the whole test suite runs on every pull request and every push to `main`.

## 1.4.0 — 2026-11-15

### Русский

- Добавлено мобильное приложение для Android (`mobile/`, PySide6 и Qt Quick) с теми же учётными записями и тем же API, что у настольной версии.
- Мобильный клиент: вход и регистрация, список задач с поиском, фильтрами и категориями, добавление задач со сроком и приоритетом, отметка выполнения, удаление (только владелец), совместный доступ пользователям и группам, создание групп, русский и английский язык, адрес сервера в настройках.
- Сетевые запросы выполняются в фоне и не блокируют интерфейс; при истёкшей сессии выполняется выход с понятным сообщением.
- Добавлен отдельный workflow `android.yml`, который собирает APK и прикладывает его к релизу; его сбой не мешает публикации настольных установщиков.
- Не входит в мобильную версию: ИИ-задачи, трей, закрепление окна, офлайн-режим.
- Сервер и настольное приложение не менялись.

### English

- Added an Android app (`mobile/`, PySide6 and Qt Quick) using the same accounts and API as the desktop app.
- Mobile client: sign-in and registration, task list with search, filters and categories, adding tasks with deadline and priority, marking tasks complete, deletion (owner only), sharing with users and groups, creating groups, Russian and English, and a server address in Settings.
- Network requests run in the background and never block the interface; an expired session signs the user out with a clear message.
- Added a separate `android.yml` workflow that builds the APK and attaches it to the release; a failure there does not block the desktop installers.
- Not included in the mobile app: AI tasks, tray, window pinning, offline mode.
- The server and the desktop app are unchanged.

## 1.3.0 — 2026-11-13

### Русский

- Добавлен удалённый MCP endpoint `/mcp` на существующем API TaskStack с транспортом Streamable HTTP и OAuth 2.1/PKCE.
- MCP-клиенты получают отдельное согласие и ограниченные разрешения для каждой учётной записи TaskStack; доступ можно отозвать в настройках подключений.
- Добавлены инструменты создания, чтения, изменения и удаления задач с соблюдением существующих правил владения и совместного доступа.
- Удаление требует отдельного подтверждения пользователем на странице TaskStack; одного вызова MCP недостаточно.
- Добавлены инструкция по подключению и описание проверенной и ожидаемой совместимости. Внешние AI-клиенты и PostgreSQL не проходили end-to-end проверку; доступность MCP на production зависит от развёртывания обновлённого API.
- Сохранены настольное приложение и установщики для Windows x64, Linux x64 (AppImage), macOS Intel и Apple Silicon.

### English

- Added a remote MCP endpoint at `/mcp` to the existing TaskStack API, using Streamable HTTP and OAuth 2.1/PKCE.
- MCP clients receive separate, scoped consent for each TaskStack account; users can revoke access from connected-client settings.
- Added tools to create, read, update, and delete tasks while preserving existing ownership and sharing rules.
- Deletion requires separate user approval on a TaskStack page; an MCP call alone cannot delete a task.
- Added setup instructions and documented tested versus expected compatibility. Third-party AI clients and PostgreSQL have not been tested end to end; production MCP availability depends on deploying the updated API.
- Preserved the desktop app and installers for Windows x64, Linux x64 (AppImage), macOS Intel, and Apple Silicon.

## 1.2.0 — 2026-11-10

### Русский

- Добавлены установщики Windows x64, Linux x64 (AppImage), macOS Intel (DMG) и Apple Silicon (DMG), собираемые в GitHub Actions.
- Установленная версия по-прежнему подключается к production API; сборки из исходного кода могут использовать собственный API через `TASKSTACK_SERVER_URL`.
- Конфигурация и журналы теперь хранятся в пользовательских папках ОС, а старый `config.json` переносится копированием при первом запуске.
- Сворачивание в системный трей доступно только если трей поддерживается текущим рабочим столом.
- Добавлены инструкции для начинающих и расширенные инструкции по сборке и самостоятельному размещению API/базы данных на русском и английском языках.
- Поведение авторизации, совместного доступа к задачам и группам из версии 1.1 сохранено.

### English

- Added Windows x64 Setup, Linux x64 AppImage, macOS Intel DMG, and Apple Silicon DMG installers built by GitHub Actions.
- Installed builds continue to use the production API; source builds can use a custom API through `TASKSTACK_SERVER_URL`.
- Configuration and logs now use per-user operating-system folders. An existing `config.json` is copied to the new location on first launch.
- Minimize-to-tray is offered only when the current desktop provides a system tray.
- Added beginner installation and advanced build/API/database self-hosting instructions in Russian and English.
- Preserved the authentication, task-sharing, and group behavior introduced in 1.1.

## 1.1.0 — 2026-11-08

### Русский

- Добавлены регистрация и вход пользователей через сервер задач.
- Добавлены общие задачи, выбор пользователей и групп, создание групп и совместный доступ.
- Задачи передают серверу статус, приоритет, категорию, срок выполнения и автора.
- Добавлены проверка доступности сервера и настраиваемый URL серверного API через `TASKSTACK_SERVER_URL`; production API: https://taskstack-o9vw.onrender.com.
- Защищённые серверные маршруты требуют bearer-токен; новые пароли хешируются PBKDF2-HMAC-SHA256, старые SHA-256-хеши обновляются при следующем успешном входе.
- Ограничены действия с задачами и группами текущим пользователем и участниками совместного доступа.
- Добавлено подключение к PostgreSQL через `DATABASE_URL`; локальная разработка по умолчанию продолжает использовать SQLite.
- Обновлено отображение задач: компактные элементы списка, кнопки статуса, индикаторы срока и обрезка длинных названий.
- Добавлены создание задачи с помощью ИИ, настройки языка и API-ключа, таймер сессии.

### English

- Added user registration and sign-in through the task API.
- Added shared tasks, user and group selection, group creation, and sharing.
- Tasks now send their status, priority, category, deadline, and author to the server.
- Added server availability checks and a configurable API URL via `TASKSTACK_SERVER_URL`; production API: https://taskstack-o9vw.onrender.com.
- Protected API routes require a bearer token. New passwords use PBKDF2-HMAC-SHA256, and legacy SHA-256 hashes are upgraded after successful sign-in.
- Restricted task and group actions to the current user and authorized collaborators.
- Added PostgreSQL support through `DATABASE_URL`; local development continues to use SQLite by default.
- Improved task display with compact list items, status controls, deadline indicators, and long-title truncation.
- Added AI-assisted task creation, language and AI API-key settings, and a session timer.

Production API health checks were confirmed at `/health`. The Render Blueprint requires an external `DATABASE_URL` and checks database connectivity to avoid ephemeral SQLite storage. Neon Free is a possible PostgreSQL option, subject to its storage, compute, availability, and backup limitations.

## 1.0.0 — 2026-11-07

### Русский

Первый публичный выпуск TaskStack:

- создание задач с категорией, приоритетом и сроком выполнения;
- поиск, фильтрация по категории и статусу, индикатор прогресса;
- сохранение списка задач и настроек между запусками;
- системный трей, закрепление окна и регулировка прозрачности;
- автономная сборка для Windows.

### English

First public release of TaskStack:

- create tasks with a category, priority, and deadline;
- search and filter by category and status, with a progress indicator;
- retain tasks and settings between launches;
- system tray, always-on-top mode, and window opacity controls;
- standalone Windows build.
