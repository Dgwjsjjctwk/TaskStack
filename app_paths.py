import shutil
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QStandardPaths


ORGANIZATION_NAME = "MTUCI"
APPLICATION_NAME = "TaskManagerLab"

QCoreApplication.setOrganizationName(ORGANIZATION_NAME)
QCoreApplication.setApplicationName(APPLICATION_NAME)


def get_writable_directory(location, path_provider=None):
    if path_provider is None:
        path_provider = QStandardPaths.writableLocation

    path = path_provider(location)
    if not path:
        raise OSError(f"No writable directory is available for {location!r}")

    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def config_directory():
    return get_writable_directory(QStandardPaths.StandardLocation.AppConfigLocation)


def app_data_directory():
    return get_writable_directory(QStandardPaths.StandardLocation.AppLocalDataLocation)


def migrate_legacy_config(legacy_path, destination_path, is_legacy_config=None):
    legacy_path = Path(legacy_path)
    destination_path = Path(destination_path)
    if destination_path.exists() or not legacy_path.is_file():
        return False
    if is_legacy_config is not None and not is_legacy_config(legacy_path):
        return False

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(legacy_path, destination_path)
    return True
