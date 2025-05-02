#!/usr/bin/env python3
"""mxAppList

Copyright (C) 2025 Marnix Enthoven <https://marnixenthoven.nl/>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>."""

__version__ = "0.1.0"

import argparse
import sqlite3
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Literal, Optional

from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table
from rich.text import Text

APPLIST_DATABASE = Path.home() / "applist.db"

console = Console()


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    connection = None
    try:
        connection = sqlite3.connect(APPLIST_DATABASE)
        yield connection
    except Exception as e:
        print(f"Error '{e}' occurred")
    finally:
        if connection:
            connection.close()


def initialize_database() -> None:
    statement_1 = """CREATE TABLE IF NOT EXISTS devices (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE
    )"""
    statement_2 = """CREATE TABLE IF NOT EXISTS package_managers (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE
    )"""
    statement_3 = """CREATE TABLE IF NOT EXISTS apps (
        id INTEGER PRIMARY KEY,
        app_name TEXT NOT NULL,
        device_id INTEGER,
        app_type INTEGER,
        FOREIGN KEY (device_id) REFERENCES devices (id),
        FOREIGN KEY (app_type) REFERENCES package_manager (id)
    )"""
    with get_db() as database:
        database.execute("PRAGMA journal_mode=wal")
        database.execute(statement_1)
        database.execute(statement_2)
        database.execute(statement_3)
        database.commit()


def get_flatpaks() -> list[str]:
    return (
        subprocess.run(
            ["flatpak", "list", "--app", "--columns=name"],
            capture_output=True,
            check=True,
        )
        .stdout.decode("utf-8")
        .splitlines()
    )


def get_pacman_packages(
    explicit: bool = True, util: Literal["pacman", "paru", "yay"] = "paru"
) -> list[str]:
    options = ["--query", "--quiet", "--explicit"]
    if not explicit:
        # options = ["--query", "--quiet", "--deps"]
        raise NotImplementedError(
            "Adding explicitly installed paru apps not available"
        )
    return (
        subprocess.run([util, *options], capture_output=True, check=True)
        .stdout.decode("utf-8")
        .splitlines()
    )


def get_device_id(name: str) -> Optional[int]:
    with get_db() as db:
        device_id = db.execute(
            "SELECT id FROM devices WHERE name = ?", (name,)
        ).fetchone()
        if device_id:
            return int(device_id[0])
        return None


def insert_device(name: str) -> int:
    with get_db() as db:
        insertion = db.execute("INSERT INTO devices (name) VALUES (?)", (name,))
        db.commit()
        rowid = insertion.lastrowid
        if not rowid:
            raise ValueError(
                f"Could not retrieve id for {name} from database after inserting the new device"
            )
        return rowid


def get_app_type_id(name: str) -> Optional[int]:
    with get_db() as db:
        app_type_id = db.execute(
            "SELECT id FROM package_managers WHERE name = ?", (name,)
        ).fetchone()
        if app_type_id:
            return int(app_type_id[0])

        return None


def insert_app_type(name: str) -> int:
    with get_db() as db:
        insertion = db.execute(
            "INSERT INTO package_managers (name) VALUES (?)", (name,)
        )
        db.commit()
        rowid = insertion.lastrowid
        if not rowid:
            raise ValueError(
                f"Could not retrieve id for {name} from database after inserting the new package manager"
            )
        return rowid


def get_all_items() -> list[tuple[str, str, str]]:
    sql_query = """SELECT
      app_name,
      devices.name,
      package_managers.name
    FROM apps
    INNER JOIN devices ON devices.id = apps.device_id
    INNER JOIN package_managers ON package_managers.id = apps.app_type
    ORDER BY LOWER(app_name)"""

    with get_db() as db:
        result = db.execute(sql_query).fetchall()
        if len(result) < 1:
            raise ValueError("Database seems to be empty")
        return result


def add_items(arguments: dict[str, Any]) -> None:
    device_id = get_device_id(arguments["device"])
    if not device_id:
        msg = Text.from_ansi(
            f"Device \033[1;32m{arguments['device']}\033[0m is not present in database."
        )
        console.print(msg)
        answer = Confirm.ask("Do you want to add it?")
        if not answer:
            print("\033[31mNot adding device, quitting...\033[0m")
            raise SystemExit(1)
        device_id = insert_device(arguments["device"])

    app_type_id = get_app_type_id(arguments["package"])
    if not app_type_id:
        msg = Text.from_ansi(
            f"Package manager \033[1;32m{arguments['package']}\033[0m is not present in database."
        )
        console.print(msg)
        answer = Confirm.ask("Do you want to add it?")

        if not answer:
            print("\033[31mNot adding package manager, quitting...\033[0m")
            raise SystemExit(1)
        app_type_id = insert_app_type(arguments["package"])

    match arguments["package"]:
        case "flatpak":
            with get_db() as db:
                flatpaks = get_flatpaks()
                insert_flatpaks = [
                    (app_name, device_id, app_type_id) for app_name in flatpaks
                ]
                db.executemany(
                    "INSERT INTO apps (app_name, device_id, app_type) VALUES (?,?,?)",
                    insert_flatpaks,
                )
                db.commit()
        case "pacman":
            with get_db() as db:
                pacman_packages = get_pacman_packages()
                insert_pacman_packages = [
                    (app_name, device_id, app_type_id)
                    for app_name in pacman_packages
                ]
                db.executemany(
                    "INSERT INTO apps (app_name, device_id, app_type) VALUES (?,?,?)",
                    insert_pacman_packages,
                )
                db.commit()
        case _:
            raise ValueError("Could not insert either flatpak or pacman")


def show_all_items(*args: Any, **kwargs: Any) -> None:
    table = Table()
    table.add_column("Application")
    table.add_column("Device")

    table.add_column("Package manager", justify="right")

    color_map_devices = {}
    color_index_devices = 0
    colors_devices = ["cyan", "green", "yellow"]
    color_map_package_managers = {}
    color_index_package_managers = 0
    colors_package_managers = ["blue", "magenta", "red", "white"]

    for item in get_all_items():
        if item[1] not in color_map_devices:
            color_map_devices[item[1]] = colors_devices[
                color_index_devices % len(colors_devices)
            ]
            color_index_devices += 1
        colored_devices = Text(str(item[1]), style=color_map_devices[item[1]])

        if item[2] not in color_map_package_managers:
            color_map_package_managers[item[2]] = colors_package_managers[
                color_index_package_managers % len(colors_package_managers)
            ]
            color_index_package_managers += 1
        colored_package_manager = Text(
            str(item[2]), style=color_map_package_managers[item[2]]
        )
        table.add_row(item[0], colored_devices, colored_package_manager)
    console.print(table)


def get_cli_options() -> dict[str, Any]:
    parser = argparse.ArgumentParser(prog="mxapplist")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    # parser.add_argument(
    #     "-d",
    #     "--database",
    #     action="store",
    #     type=Path,
    #     help=f"the location of the database (default: {APPLIST_DATABASE})",
    #     default=APPLIST_DATABASE,
    #     metavar="/path/to/db",
    # )

    subparsers = parser.add_subparsers(required=True)

    addition_parser = subparsers.add_parser(
        "add", help="Add applications to the database"
    )
    addition_parser.set_defaults(func=add_items)
    addition_parser.add_argument(
        "device",
        action="store",
        help="input the name of this device",
        metavar="my_desktop",
    )
    addition_parser.add_argument(
        "package",
        action="store",
        choices=["flatpak", "pacman"],
        help="the package manager to add",
    )

    show_parser = subparsers.add_parser(
        "show", help="Show all items in the database"
    )
    show_parser.set_defaults(func=show_all_items)

    return vars(parser.parse_args())


def main() -> None:
    arguments = get_cli_options()
    initialize_database()
    arguments["func"](arguments)


if __name__ == "__main__":
    main()
