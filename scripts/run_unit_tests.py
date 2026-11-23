"""Dependency-free launcher for the frozen and candidate unittest suite."""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
sys.path.insert(0,str(ROOT/"tests"))
if __name__=="__main__":
    suite=unittest.TestLoader().discover(str(ROOT/"tests"),pattern="test*.py")
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():sys.exit(1)
