"""
Android entry point for buildozer
"""
import os
import runpy
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(here, "src"), os.path.join(here, "UI")]
# Android keeps only .pyc files
runpy.run_module("main", run_name="__main__")
