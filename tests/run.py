#!/usr/bin/env python3
"""Run the whole suite. No dependencies beyond the standard library.

    python tests/run.py           everything, including the Tk tests
    python tests/run.py --no-gui  skip anything that opens a window
"""

import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))


def main(argv):
    if "--no-gui" in argv:
        os.environ["LMS_SKIP_GUI_TESTS"] = "1"
    loader = unittest.TestLoader()
    suite = loader.discover(str(HERE), pattern="test_*.py", top_level_dir=str(HERE))
    if loader.errors:
        for error in loader.errors:
            print(error, file=sys.stderr)
        return 2
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(
        f"\n{result.testsRun} tests, {len(result.failures)} failures, "
        f"{len(result.errors)} errors, {len(result.skipped)} skipped"
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
