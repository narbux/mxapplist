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
import subprocess
from pathlib import Path
from typing import Any, Literal, Optional

from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table
from rich.text import Text
from sqlalchemy import ForeignKey, create_engine, func, select
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)


class Base(DeclarativeBase):
    pass


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False, unique=True)
    applications: Mapped[list["Application"]] = relationship(
        "Application", back_populates="device"
    )

    def __repr__(self) -> str:
        return f"<Device {self.id} => {self.name}>"


class PackageManager(Base):
    __tablename__ = "package_managers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False, unique=True)
    applications: Mapped[list["Application"]] = relationship(
        "Application", back_populates="package_manager"
    )

    def __repr__(self) -> str:
        return f"<PackageManager {self.id} => {self.name}>"


class Application(Base):
    __tablename__ = "apps"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    package_manager_id: Mapped[int] = mapped_column(
        ForeignKey("package_managers.id")
    )
    device: Mapped["Device"] = relationship(
        "Device", back_populates="applications"
    )
    package_manager: Mapped["PackageManager"] = relationship(
        "PackageManager", back_populates="applications"
    )

    def __repr__(self) -> str:
        return f"<Application {self.id} => {self.name}>"


console = Console()


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
    query = select(Device.id).where(Device.name == name)
    with Session() as session:
        result = session.execute(query).scalar()
        return result


def insert_device(name: str) -> int:
    with Session() as session:
        try:
            new_device = Device(name=name)
            session.add(new_device)
            session.commit()
            session.refresh(new_device)
            rowid = new_device.id
            if not rowid:
                raise ValueError(
                    f"Could not retrieve id for {name} from database after inserting the new device"
                )
            return rowid
        except Exception:
            session.rollback()
            raise


def get_package_manager(name: str) -> Optional[int]:
    query = select(PackageManager.id).where(PackageManager.name == name)
    with Session() as db:
        result = db.execute(query).scalar()
        return result


def insert_package_manager(name: str) -> int:
    with Session() as session:
        try:
            new_package_manager = PackageManager(name=name)
            session.add(new_package_manager)
            session.commit()
            session.refresh(new_package_manager)
            rowid = new_package_manager.id
            if not rowid:
                raise ValueError(
                    f"Could not retrieve id for {name} from database after inserting the new package manager"
                )
            return rowid
        except Exception:
            session.rollback()
            raise


def get_all_items():
    query = (
        select(Application.name, Device.name, PackageManager.name)
        .join(Device, Application.device_id == Device.id)
        .join(
            PackageManager, Application.package_manager_id == PackageManager.id
        )
        .order_by(func.lower(Application.name))
    )

    with Session() as db:
        result = db.execute(query).fetchall()
        return result


def check_ids(device: str, package_manager: str) -> tuple[int, int]:
    device_id = get_device_id(device)
    if not device_id:
        msg = Text.from_ansi(
            f"Device \033[1;32m{device}\033[0m is not present in database."
        )
        console.print(msg)
        answer = Confirm.ask("Do you want to add it?")
        if not answer:
            print("\033[31mNot adding device, quitting...\033[0m")
            raise SystemExit(1)
        device_id = insert_device(device)

    package_manager_id = get_package_manager(package_manager)
    if not package_manager_id:
        msg = Text.from_ansi(
            f"Package manager \033[1;32m{package_manager}\033[0m is not present in database."
        )
        console.print(msg)
        answer = Confirm.ask("Do you want to add it?")
        if not answer:
            print("\033[31mNot adding package manager, quitting...\033[0m")
            raise SystemExit(1)
        package_manager_id = insert_package_manager(package_manager)

    return (device_id, package_manager_id)


def insert_applications(
    items: list[str], device_id: int, package_manager_id: int
) -> None:
    apps_to_insert = [
        Application(
            name=app_name,
            device_id=device_id,
            package_manager_id=package_manager_id,
        )
        for app_name in items
    ]
    with Session() as session:
        try:
            session.add_all(apps_to_insert)
            session.commit()
        except Exception:
            session.rollback()
            raise


def add_applications_by_package_manager(arguments: dict[str, Any]) -> None:
    device_id, package_manager_id = check_ids(
        device=arguments["device"], package_manager=arguments["package"]
    )

    match arguments["package"]:
        case "flatpak":
            insert_applications(get_flatpaks(), device_id, package_manager_id)
        case "pacman":
            insert_applications(
                get_pacman_packages(), device_id, package_manager_id
            )
        case _:
            raise ValueError("Could not insert either flatpak or pacman")


def show_all_applications(*args: Any, **kwargs: Any) -> None:
    all_items = get_all_items()

    table = Table()
    table.add_column("Application")
    table.add_column("Device")

    table.add_column("Package manager", justify="right")

    color_map_devices = {}
    color_index_devices = 0
    colors_devices = ["cyan", "green", "yellow"]

    color_map_package_managers = {}
    color_index_package_managers = 0
    colors_package_managers = ["magenta", "blue", "red"]

    for item in all_items:
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
    parser.add_argument(
        "--database",
        action="store",
        type=str,
        help="the location of the database (default: $HOME/mxapplist.db)",
        default=str(Path.home() / "mxapplist.db"),
        metavar="/path/to/db",
    )

    subparsers = parser.add_subparsers(required=True)

    addition_parser = subparsers.add_parser(
        "add", help="Add applications to the database"
    )
    addition_parser.set_defaults(func=add_applications_by_package_manager)
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
    show_parser.set_defaults(func=show_all_applications)

    return vars(parser.parse_args())


def check_or_create_db(db_path: Path) -> bool:
    just_created = False

    if not db_path.exists():
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_path.touch(exist_ok=True)
            just_created = True
        except Exception as e:
            console.print(
                f"[red]Error: Cannot create or access database file at {db_path}[/red]"
            )
            raise SystemExit(1) from e

    try:
        with db_path.open("rb") as f:
            header = f.read(16)
            if (
                header and header != b"SQLite format 3\x00"
            ):  # Check if the file is a valid SQLite file (if it's not empty)
                console.print(
                    f"[red]Error: File at {db_path} is not a valid SQLite database.[/red]"
                )
                raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]Error while checking SQLite header: {e}[/red]")
        raise SystemExit(1)

    return just_created


def main() -> None:
    arguments = get_cli_options()
    db_path = Path(arguments["database"]).expanduser().resolve()
    db_validity = check_or_create_db(db_path)

    global Session
    engine = create_engine(f"sqlite:///{arguments['database']}")

    if db_validity or db_path.stat().st_size == 0:
        Base.metadata.create_all(engine)

    Session = sessionmaker(engine)
    console.print(f"Using db: {db_path}")

    arguments["func"](arguments)


if __name__ == "__main__":
    main()
