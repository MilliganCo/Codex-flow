"""Optional direct launcher; `python -m ascii_tree` is equivalent."""

from ascii_tree.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
