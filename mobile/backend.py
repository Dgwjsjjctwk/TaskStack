"""Bridge between the QML interface and the TaskStack API.

All network calls run on worker threads; results are delivered back to the
GUI thread through a queued signal, so the interface never blocks.
"""

import logging
import threading
import time
from datetime import datetime

from PySide6.QtCore import Property, QObject, QSettings, Signal, Slot

from strings import DEFAULT_LANGUAGE, STRINGS, translate
from taskstack_api import (
    DEFAULT_SERVER_URL,
    ApiError,
    NetworkError,
    TaskStackClient,
    normalize_server_url,
)
from taskstack_logic import (
    CATEGORY_CHOICES,
    PRIORITY_CHOICES,
    compute_stats,
    deadline_from_choice,
    filter_tasks,
    normalize_deadline_text,
    normalize_task,
    parse_deadline,
    sort_tasks,
)
from version import __version__

logger = logging.getLogger("TaskStackMobile")

REFRESH_MIN_INTERVAL = 2.0  # seconds; guards against duplicate refreshes


class Backend(QObject):
    # property change notifications
    busyChanged = Signal()
    loggedInChanged = Signal()
    usernameChanged = Signal()
    serverUrlChanged = Signal()
    languageChanged = Signal()
    onlineChanged = Signal()
    tasksChanged = Signal()
    statsChanged = Signal()
    usersChanged = Signal()
    groupsChanged = Signal()

    # events for QML
    message = Signal(str, bool)  # text, isError
    taskAdded = Signal()
    groupCreated = Signal()
    registered = Signal()

    # worker thread -> GUI thread
    _done = Signal(object, object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = QSettings()
        self._client = TaskStackClient(
            normalize_server_url(self._settings.value("server_url", DEFAULT_SERVER_URL))
        )
        language = self._settings.value("language", DEFAULT_LANGUAGE)
        self._language = language if language in STRINGS else DEFAULT_LANGUAGE

        self._busy_count = 0
        self._logged_in = False
        self._online = False
        self._all_tasks = []
        self._visible_tasks = []
        self._stats = compute_stats([])
        self._users = []
        self._groups = []
        self._status = "all"
        self._search = ""
        self._category = ""
        self._last_refresh = 0.0
        # Bumped on every sign-out: an answer to a request that was started in
        # an earlier session must not fill the screen of the next one.
        self._generation = 0

        self._done.connect(self._finish)
        self._restore_session()

    # -- helpers -----------------------------------------------------------

    def _t(self, key, **values):
        return translate(self._language, key, **values)

    def _run(self, work, on_ok=None, on_error=None, show_busy=True):
        if show_busy:
            self._busy_count += 1
            self.busyChanged.emit()

        generation = self._generation

        def target():
            try:
                result = work()
            except Exception as error:  # delivered to the GUI thread
                self._done.emit((on_ok, on_error, show_busy, generation), None, error)
            else:
                self._done.emit((on_ok, on_error, show_busy, generation), result, None)

        threading.Thread(target=target, daemon=True).start()

    @Slot(object, object, object)
    def _finish(self, callbacks, result, error):
        on_ok, on_error, show_busy, generation = callbacks
        if show_busy:
            self._busy_count = max(0, self._busy_count - 1)
            self.busyChanged.emit()
        if generation != self._generation:
            return  # the user signed out meanwhile; drop the late answer
        if error is None:
            self._set_online(True)
            if on_ok:
                on_ok(result)
            return
        if isinstance(error, NetworkError):
            self._set_online(False)
        if on_error and on_error(error):
            return
        self._report(error)

    def _report(self, error):
        if isinstance(error, ApiError):
            if error.status == 429:
                self.message.emit(self._t("err_too_many_attempts"), True)
            elif error.is_unauthorized and self._logged_in:
                self._sign_out()
                self.message.emit(self._t("err_session"), True)
            elif error.is_unauthorized:
                self.message.emit(self._t("err_bad_credentials"), True)
            else:
                self.message.emit(error.detail, True)
        elif isinstance(error, NetworkError):
            self.message.emit(self._t("err_network", reason=str(error)), True)
        else:
            logger.exception("Unexpected error", exc_info=error)
            self.message.emit(str(error), True)

    def _set_online(self, online):
        if online != self._online:
            self._online = online
            self.onlineChanged.emit()

    def _restore_session(self):
        token = self._settings.value("token", "")
        user_id = self._settings.value("user_id", None)
        username = self._settings.value("username", "")
        if token and user_id not in (None, "") and username:
            try:
                user_id = int(user_id)
            except (TypeError, ValueError):
                return  # damaged saved session: start signed out
            self._client.restore_session(token, user_id, username)
            self._logged_in = True

    def _save_session(self):
        self._settings.setValue("token", self._client.token or "")
        self._settings.setValue("user_id", self._client.user_id)
        self._settings.setValue("username", self._client.username or "")
        self._settings.sync()

    def _sign_out(self):
        self._generation += 1
        self._client.logout()
        for key in ("token", "user_id", "username"):
            self._settings.remove(key)
        self._settings.sync()
        self._logged_in = False
        self._all_tasks = []
        self._users = []
        self._groups = []
        self._recompute()
        self.loggedInChanged.emit()
        self.usernameChanged.emit()
        self.usersChanged.emit()
        self.groupsChanged.emit()

    def _recompute(self):
        self._visible_tasks = filter_tasks(
            self._all_tasks, self._status, self._search, self._category
        )
        self._stats = compute_stats(self._all_tasks)
        self.tasksChanged.emit()
        self.statsChanged.emit()

    def _set_tasks(self, raw_tasks):
        user_id = self._client.user_id
        username = self._client.username
        tasks = [normalize_task(raw, user_id, username) for raw in raw_tasks]
        self._all_tasks = sort_tasks(tasks)
        self._recompute()

    # -- properties --------------------------------------------------------

    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._busy_count > 0

    @Property(bool, notify=loggedInChanged)
    def loggedIn(self):
        return self._logged_in

    @Property(str, notify=usernameChanged)
    def username(self):
        return self._client.username or ""

    @Property(str, notify=serverUrlChanged)
    def serverUrl(self):
        return self._client.base_url

    @Property(str, notify=languageChanged)
    def language(self):
        return self._language

    @Property(bool, notify=onlineChanged)
    def online(self):
        return self._online

    @Property("QVariantList", notify=tasksChanged)
    def tasks(self):
        return self._visible_tasks

    @Property("QVariantMap", notify=statsChanged)
    def stats(self):
        return self._stats

    @Property("QVariantList", notify=usersChanged)
    def users(self):
        return self._users

    @Property("QVariantList", notify=groupsChanged)
    def groups(self):
        return self._groups

    @Property("QVariantList", notify=languageChanged)
    def priorityChoices(self):
        return PRIORITY_CHOICES[self._language]

    @Property("QVariantList", notify=languageChanged)
    def categoryChoices(self):
        return CATEGORY_CHOICES[self._language]

    @Property(str, constant=True)
    def version(self):
        return __version__

    @Property(str, constant=True)
    def defaultServerUrl(self):
        return DEFAULT_SERVER_URL

    # -- slots: strings and small helpers ----------------------------------

    @Slot(str, result=str)
    def tr(self, key):
        return self._t(key)

    @Slot(str, result=str)
    def quickDeadline(self, choice):
        return deadline_from_choice(choice)

    # -- slots: settings ---------------------------------------------------

    @Slot(str)
    def setLanguage(self, language):
        if language in STRINGS and language != self._language:
            self._language = language
            self._settings.setValue("language", language)
            self.languageChanged.emit()

    @Slot(str)
    def setServerUrl(self, url):
        url = normalize_server_url(url)
        if url == self._client.base_url:
            return
        if self._logged_in:
            # The sign-in token belongs to the old server; never send it to a
            # different address.
            self._sign_out()
            self.message.emit(self._t("server_changed_signed_out"), False)
        self._client.base_url = url
        self._settings.setValue("server_url", url)
        self.serverUrlChanged.emit()
        self.checkServer()

    # -- slots: account ----------------------------------------------------

    @Slot()
    def checkServer(self):
        self._run(
            self._client.health,
            on_error=lambda error: True,  # only the indicator changes
            show_busy=False,
        )

    @Slot(str, str)
    def login(self, username, password):
        username = username.strip()
        if not username or not password:
            self.message.emit(self._t("err_fill_fields"), True)
            return

        def done(_data):
            self._save_session()
            self._logged_in = True
            self.loggedInChanged.emit()
            self.usernameChanged.emit()
            self.refresh()

        self._run(lambda: self._client.login(username, password), done)

    @Slot(str, str)
    def register(self, username, password):
        username = username.strip()
        if not username or not password:
            self.message.emit(self._t("err_fill_fields"), True)
            return
        if len(password) < 8:
            self.message.emit(self._t("err_password_short"), True)
            return

        def done(_data):
            self.message.emit(self._t("registered_ok"), False)
            self.registered.emit()

        self._run(lambda: self._client.register(username, password), done)

    @Slot()
    def logout(self):
        self._sign_out()

    # -- slots: tasks ------------------------------------------------------

    def _refresh(self, force):
        if not self._logged_in:
            return
        now = time.monotonic()
        if not force and now - self._last_refresh < REFRESH_MIN_INTERVAL:
            return
        self._last_refresh = now
        self._run(self._client.list_tasks, self._set_tasks)

    @Slot()
    def refresh(self):
        """Reload the task list now (button, pull-to-refresh, after changes)."""
        self._refresh(force=True)

    def refresh_if_stale(self):
        """Reload unless a refresh just happened (app returning to foreground)."""
        self._refresh(force=False)

    @Slot(str, str, str)
    def setFilter(self, status, search, category):
        self._status = status
        self._search = search
        self._category = category
        self._recompute()

    @Slot(str, str, str, str, "QVariantList", "QVariantList")
    def addTask(self, title, priority, category, deadline_text, user_ids, group_ids):
        title = title.strip()
        if not title:
            self.message.emit(self._t("err_empty_title"), True)
            return
        deadline = normalize_deadline_text(deadline_text)
        if deadline is None:
            self.message.emit(self._t("err_bad_deadline"), True)
            return
        users = [int(value) for value in user_ids]
        groups = [int(value) for value in group_ids]

        def done(_data):
            self.taskAdded.emit()
            self.refresh()

        self._run(
            lambda: self._client.add_task(title, priority, category, deadline, users, groups),
            done,
        )

    @Slot(int, bool)
    def toggleTask(self, task_id, completed):
        # Optimistic update; the list is reloaded if the server refuses.
        for task in self._all_tasks:
            if task["id"] == task_id:
                task["completed"] = completed
        self._set_tasks_from_cache()

        def failed(error):
            self.refresh()
            return False  # still show the error

        self._run(
            lambda: self._client.set_task_status(task_id, completed),
            on_error=failed,
            show_busy=False,
        )

    def _set_tasks_from_cache(self):
        # Re-derive overdue flags and ordering after a local change.
        now = datetime.now()
        for task in self._all_tasks:
            parsed = parse_deadline(task["deadline"])
            task["overdue"] = bool(parsed and not task["completed"] and parsed < now)
        self._all_tasks = sort_tasks(self._all_tasks)
        self._recompute()

    @Slot(int)
    def deleteTask(self, task_id):
        task = next((t for t in self._all_tasks if t["id"] == task_id), None)
        if task is None:
            return
        if not task["isOwner"]:
            self.message.emit(self._t("delete_owner_only"), True)
            return

        def done(_data):
            self._all_tasks = [t for t in self._all_tasks if t["id"] != task_id]
            self._recompute()

        self._run(lambda: self._client.delete_task(task_id), done)

    # -- slots: sharing ----------------------------------------------------

    @Slot()
    def loadSharing(self):
        if not self._logged_in:
            return

        def work():
            return self._client.list_users(), self._client.list_groups()

        def done(result):
            users, groups = result
            self._users = [{"id": u["id"], "username": u["username"]} for u in users]
            self._groups = [{"id": g["id"], "name": g["name"]} for g in groups]
            self.usersChanged.emit()
            self.groupsChanged.emit()

        self._run(work, done)

    @Slot(str, "QVariantList")
    def createGroup(self, name, member_ids):
        name = name.strip()
        if not name:
            self.message.emit(self._t("err_group_name"), True)
            return
        members = [int(value) for value in member_ids]

        def done(_data):
            self.message.emit(self._t("group_created"), False)
            self.groupCreated.emit()
            self.loadSharing()

        self._run(lambda: self._client.create_group(name, members), done)
