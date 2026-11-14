"""TaskStack mobile entry point (PySide6 + Qt Quick).

pyside6-android-deploy requires this file to be called main.py.
"""

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from backend import Backend


def main():
    logging.basicConfig(level=logging.INFO)
    QCoreApplication.setOrganizationName("TaskStack")
    QCoreApplication.setApplicationName("TaskStackMobile")

    app = QGuiApplication(sys.argv)
    QQuickStyle.setStyle("Material")

    backend = Backend()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)

    def on_state_changed(state):
        # Pick up changes made elsewhere (desktop app, other devices).
        if state == Qt.ApplicationState.ApplicationActive:
            backend.refresh_if_stale()

    app.applicationStateChanged.connect(on_state_changed)

    qml_file = Path(__file__).resolve().parent / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))
    if not engine.rootObjects():
        logging.error("Could not load %s", qml_file)
        return 1

    backend.checkServer()
    backend.refresh()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
