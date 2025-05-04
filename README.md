# mxAppList

Save a list of installed flatpak and pacman applications to a database

```
usage: mxapplist [-h] [--version] [--database /path/to/db] {add,show} ...

positional arguments:
  {add,show}
    add                 Add applications to the database
    show                Show all items in the database

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  --database /path/to/db
                        the location of the database (default: $HOME/mxapplist.db)
  ```
