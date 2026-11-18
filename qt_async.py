"""Run blocking calls on a worker thread and deliver the result on the UI thread."""

import logging
import threading

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

logger = logging.getLogger("qt_async")


class _Bus(QObject):
    """Lives in the UI thread; a signal emitted from any thread runs its
    payload there (queued connection)."""

    message = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.message.connect(self._run)

    @pyqtSlot(object)
    def _run(self, callback):
        try:
            callback()
        except RuntimeError as error:
            # The widget that asked has been closed and deleted meanwhile.
            logger.debug("Результат запроса не доставлен: %s", error)
        except Exception:
            logger.exception("Ошибка в обработчике результата запроса")


_bus = None


def run_async(func, on_done=None, on_error=None):
    """Call ``func()`` on a worker thread.

    ``on_done(result)`` or ``on_error(exception)`` is then called on the UI
    thread. Call this from the UI thread only. Worker threads are daemons, so
    a request that is still waiting never keeps the application from exiting.
    """
    global _bus
    if _bus is None:
        _bus = _Bus()
    bus = _bus

    def work():
        try:
            result = func()
        except Exception as error:  # delivered to on_error, not lost
            # Python unbinds `error` when this block ends, so the callback
            # (which runs later, on the UI thread) must capture it now.
            if on_error is not None:
                bus.message.emit(lambda failure=error: on_error(failure))
            else:
                logger.error("Запрос завершился ошибкой: %s", error)
        else:
            if on_done is not None:
                bus.message.emit(lambda value=result: on_done(value))

    thread = threading.Thread(target=work, name="taskstack-request", daemon=True)
    thread.start()
    return thread
