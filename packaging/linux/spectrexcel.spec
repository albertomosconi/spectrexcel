from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs, copy_metadata


project_root = Path(SPEC).resolve().parents[2]
package_dir = project_root / "spectrexcel"

a = Analysis(
    [str(package_dir / "main.py")],
    pathex=[],
    binaries=collect_dynamic_libs("dearpygui"),
    datas=[
        (str(package_dir / "icon.ico"), "."),
        (str(package_dir / "fonts"), "fonts"),
        *copy_metadata("spectrexcel"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# Graphics drivers are loaded from the host at runtime and must use the host's
# X11 and C++ runtime libraries rather than copies from the build machine.
a.exclude_system_libraries(list_of_exceptions=["libpython*"])

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="spectrexcel",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
