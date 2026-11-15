"""TaskStack mobile entry point (PySide6 + Qt Quick).

pyside6-android-deploy requires this file to be called main.py.
"""

import json
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

    qml_errors = []

    def on_warnings(warnings):
        for warning in warnings:
            text = warning.toString()
            qml_errors.append(text)
            logging.error("QML: %s", text)

    engine.warnings.connect(on_warnings)

    qml_file = Path(__file__).resolve().parent / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))
    if not engine.rootObjects():
        logging.error("Could not load %s", qml_file)
        # Show the reason on screen: on a phone there is usually no console,
        # and a silent exit looks like a crash.
        report = "TaskStack could not start\n\n" + (
            "\n".join(qml_errors) or f"Could not load {qml_file}"
        )
        error_qml = (
            "import QtQuick\n"
            "import QtQuick.Window\n"
            "Window {\n"
            "  visible: true; width: 360; height: 720; color: '#0d1117'\n"
            "  Text {\n"
            "    anchors.fill: parent; anchors.margins: 16; color: 'white'\n"
            "    wrapMode: Text.Wrap; font.pixelSize: 13\n"
            "    text: " + json.dumps(report) + "\n"
            "  }\n"
            "}\n"
        )
        engine.loadData(error_qml.encode("utf-8"))
        if not engine.rootObjects():
            return 1
        return app.exec()

    backend.checkServer()
    backend.refresh()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
