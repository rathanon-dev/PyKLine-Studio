"""
PyKLine Studio - Centralized Path & Portable Workspace Manager
Resolves execution root whether running from source or PyInstaller .exe bundle.
Enforces the 'Portable Sibling Workspace' pattern.
"""

import sys
import os

def get_app_stem() -> str:
    """Returns the executable name without extension (e.g. 'PyKLine-Studio' or 'PyKLine-Simulator')"""
    if getattr(sys, 'frozen', False):
        return os.path.splitext(os.path.basename(sys.executable))[0]
    if len(sys.argv) > 0 and sys.argv[0]:
        stem = os.path.splitext(os.path.basename(sys.argv[0]))[0]
        if "sim" in stem.lower():
            return "PyKLine-Simulator"
    return "PyKLine-Studio"

def get_base_directory() -> str:
    """
    Returns the true host directory containing the executable or source project.
    Bypasses PyInstaller's temporary _MEIPASS extraction folder.
    """
    if getattr(sys, 'frozen', False):
        # Standalone .exe: points to the directory containing the .exe on user's machine
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        # Source script: core/paths.py -> go up 2 levels to project root
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_workspace_directory() -> str:
    """
    Returns the unified companion data directory named after the executable.
    Example: 'Desktop/PyKLine-Studio_Data/'
    """
    base_dir = get_base_directory()
    app_name = get_app_stem()
    if getattr(sys, 'frozen', False):
        # In Standalone .exe mode, create a single companion folder named after the .exe
        workspace = os.path.join(base_dir, f"{app_name}_Data")
    else:
        # In source development mode, keep within project root
        workspace = base_dir

    os.makedirs(workspace, exist_ok=True)
    return workspace

def get_sub_directory(sub_name: str) -> str:
    """
    Returns a managed sub-folder inside the companion workspace.
    Common sub-folders: 'logs', 'data', 'dumps'
    """
    workspace = get_workspace_directory()
    target_dir = os.path.join(workspace, sub_name)
    os.makedirs(target_dir, exist_ok=True)
    return target_dir

def get_logs_directory() -> str:
    return get_sub_directory("logs")

def get_data_directory() -> str:
    return get_sub_directory("data")

def get_dumps_directory() -> str:
    return get_sub_directory("dumps")
