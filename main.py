"""
Android entry point for buildozer
"""
import os
import runpy
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(here, "src"), os.path.join(here, "UI")]

# Updated libraries load first
try:
    from jnius import autoclass
    from downloadity import updates

    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    package = activity.getPackageManager().getPackageInfo(activity.getPackageName(), 0)
    updates.activate(os.path.join(activity.getFilesDir().getAbsolutePath(), "libs"), package.versionName)
except Exception:
    import traceback
    traceback.print_exc()
# Android keeps only .pyc files
runpy.run_module("main", run_name="__main__")
