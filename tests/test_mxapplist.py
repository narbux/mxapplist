import sqlite3
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from mxapplist import mxapplist


@pytest.fixture
def temp_db(monkeypatch):
    # Use a temporary database for testing
    with tempfile.NamedTemporaryFile() as tf:
        test_db_path = Path(tf.name)
        monkeypatch.setattr(mxapplist, "APPLIST_DATABASE", test_db_path)
        mxapplist.initialize_database()
        yield test_db_path


def test_initialize_database(temp_db):
    with sqlite3.connect(temp_db) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table';"
        ).fetchall()
        table_names = {t[0] for t in tables}
        assert {"devices", "package_managers", "apps"}.issubset(table_names)


def test_insert_and_get_device(temp_db):
    device_name = "test_device"
    device_id = mxapplist.insert_device(device_name)
    assert isinstance(device_id, int)

    fetched_id = mxapplist.get_device_id(device_name)
    assert fetched_id == device_id


def test_insert_and_get_app_type(temp_db):
    package_name = "pacman"
    app_type_id = mxapplist.insert_app_type(package_name)
    assert isinstance(app_type_id, int)

    fetched_id = mxapplist.get_app_type_id(package_name)
    assert fetched_id == app_type_id


@mock.patch("mxapplist.mxapplist.subprocess.run")
def test_get_flatpaks(mock_run):
    mock_run.return_value.stdout = b"App1\nApp2\n"
    result = mxapplist.get_flatpaks()
    assert result == ["App1", "App2"]


@mock.patch("mxapplist.mxapplist.subprocess.run")
def test_get_pacman_packages(mock_run):
    mock_run.return_value.stdout = b"pkg1\npkg2\n"
    result = mxapplist.get_pacman_packages()
    assert result == ["pkg1", "pkg2"]
    mock_run.assert_called_with(
        ["paru", "--query", "--quiet", "--explicit"],
        capture_output=True,
        check=True,
    )


@mock.patch("mxapplist.mxapplist.get_flatpaks")
@mock.patch("mxapplist.mxapplist.Confirm.ask", return_value=True)
def test_add_flatpak_items(mock_confirm, mock_get_flatpaks, temp_db):
    mock_get_flatpaks.return_value = ["TestApp"]
    args = {"device": "dev1", "package": "flatpak"}

    mxapplist.add_items(args)
    results = mxapplist.get_all_items()
    assert results[0][0] == "TestApp"
    assert results[0][1] == "dev1"
    assert results[0][2] == "flatpak"


@mock.patch("mxapplist.mxapplist.get_pacman_packages")
@mock.patch("mxapplist.mxapplist.Confirm.ask", return_value=True)
def test_add_pacman_items(mock_confirm, mock_get_pacman, temp_db):
    mock_get_pacman.return_value = ["pkgA", "pkgB"]
    args = {"device": "dev2", "package": "pacman"}

    mxapplist.add_items(args)
    results = mxapplist.get_all_items()
    app_names = [r[0] for r in results]
    assert "pkgA" in app_names and "pkgB" in app_names
