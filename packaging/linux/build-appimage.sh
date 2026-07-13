#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
appdir="$project_root/build/SpectrExcel.AppDir"
appimagetool=${APPIMAGETOOL:-"$project_root/appimagetool"}
runtime=${APPIMAGE_RUNTIME:-"$project_root/runtime-x86_64"}

rm -rf "$appdir"
mkdir -p "$appdir/usr/bin" "$appdir/usr/share/applications"
mkdir -p "$appdir/usr/share/icons/hicolor/128x128/apps"
install -m 755 "$project_root/dist/spectrexcel" "$appdir/usr/bin/spectrexcel"
install -m 755 "$project_root/packaging/linux/AppRun" "$appdir/AppRun"
install -m 644 "$project_root/packaging/linux/spectrexcel.desktop" \
    "$appdir/spectrexcel.desktop"
install -m 644 "$project_root/packaging/linux/spectrexcel.desktop" \
    "$appdir/usr/share/applications/spectrexcel.desktop"
install -m 644 "$project_root/spectrexcel/icon.png" "$appdir/spectrexcel.png"
install -m 644 "$project_root/spectrexcel/icon.png" \
    "$appdir/usr/share/icons/hicolor/128x128/apps/spectrexcel.png"

ARCH=x86_64 "$appimagetool" --appimage-extract-and-run --runtime-file "$runtime" \
    "$appdir" "$project_root/dist/SpectrExcel-x86_64.AppImage"
