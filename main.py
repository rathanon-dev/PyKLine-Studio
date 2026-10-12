"""
========================================================================================
 PyKLine Studio - Main Entry Point
 Double-clickable launcher for the Universal K-Line ECU Diagnostic & Telemetry Suite.
========================================================================================
"""

import sys
import os

# Ensure package directory is on python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.app import PyKLineApp

def main():
    app = PyKLineApp()
    app.mainloop()

if __name__ == '__main__':
    main()
