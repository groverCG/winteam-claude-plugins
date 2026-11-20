#!/usr/bin/env bash
# Usage: build.sh <android|ios> <source-dir> <dest-dir>
# Debug build for the emulator/simulator; copies the .apk / .app into dest-dir and prints its path.
set -euo pipefail
platform="$1"; src="$2"; dest="$3"
[ -d "$src" ] || { echo "source dir not found: $src" >&2; exit 1; }
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
mkdir -p "$dest"

case "$platform" in
  android)
    # Debug defaults to Fast Deployment (assemblies outside the APK), which crashes when installed with plain
    # adb, so embed them.
    dotnet build "$src/WinTeam.Mobile.Android/WinTeam.Mobile.Android.csproj" -nologo -v q \
      -c Debug -f net10.0-android -r android-arm64 \
      -p:EmbedAssembliesIntoApk=true -p:AndroidSdkDirectory="$ANDROID_HOME" >&2
    apk="$(ls -t "$src"/WinTeam.Mobile.Android/bin/Debug/net10.0-android/android-arm64/*-Signed.apk | head -1)"
    cp "$apk" "$dest/app.apk"
    echo "$dest/app.apk" ;;
  ios)
    dotnet build "$src/WinTeam.Mobile.iOS/WinTeam.Mobile.iOS.csproj" -nologo -v q \
      -c Debug -f net10.0-ios -r iossimulator-arm64 >&2
    app="$(ls -dt "$src"/WinTeam.Mobile.iOS/bin/Debug/net10.0-ios/iossimulator-arm64/*.app | head -1)"
    rm -rf "$dest/app.app"; cp -R "$app" "$dest/app.app"
    echo "$dest/app.app" ;;
  *) echo "unknown platform: $platform" >&2; exit 1 ;;
esac
