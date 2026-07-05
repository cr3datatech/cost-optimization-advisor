#!/usr/bin/env python3
"""Backward-compatible wrapper around scripts/manage.py deploy."""

from manage import main

if __name__ == "__main__":
    import sys

    argv = ["deploy", *sys.argv[1:]]
    if "--list-profiles" in argv:
        argv = ["list-profiles"]
    main(argv)
