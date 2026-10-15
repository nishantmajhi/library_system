#!/usr/bin/env python3
"""LMS - Library Management System.

The program lives in the `lms` package; this is only the entry point, kept at
the old path so `python library_system.py` still starts it.
"""

import sys

from lms.app import main

if __name__ == "__main__":
    sys.exit(main())
