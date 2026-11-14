# Changelog / История изменений

## 1.4.0 — 2026-11-14

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
