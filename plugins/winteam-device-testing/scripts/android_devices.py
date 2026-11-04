"""Android emulators for the capture run: find, create, boot, inspect and shut down AVDs. Standard library only.

As a CLI it serves setup-devices:
  android_devices.py check --data <data folder>             report each devices.json AVD, and its bucket if running
  android_devices.py create-avd --data <data folder> --role tablet
                                                             create a missing AVD from its "create" entry
  android_devices.py bucket --data <data folder> --role tablet
                                                             boot the AVD if needed, print its size bucket, shut down

create-avd copies the source AVD's config.ini only, never its disk images: the emulator builds the new AVD's
userdata from the system image on its first boot. It refuses to touch an AVD that already exists.
"""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time

SIZE_BUCKETS = ("small", "normal", "large", "xlarge")


def sdk_root():
    for name in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(name) and os.path.isdir(os.environ[name]):
            return os.environ[name]
    default = os.path.expanduser("~/Library/Android/sdk")
    if os.path.isdir(default):
        return default
    raise SystemExit("Android SDK not found: set ANDROID_HOME or install it under ~/Library/Android/sdk")


def tool(name):
    folder = {"adb": "platform-tools", "emulator": "emulator"}[name]
    path = os.path.join(sdk_root(), folder, name)
    if not os.path.exists(path):
        raise SystemExit("{} not found at {}; install it with Android Studio's SDK Manager".format(name, path))
    return path


def adb(serial, *args, check=True, timeout=120):
    command = [tool("adb")] + (["-s", serial] if serial else []) + list(args)
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode != 0:
        raise RuntimeError("adb {} failed: {}".format(" ".join(args[:2]), result.stderr.strip()[:200]))
    return result.stdout


def avd_home():
    return os.environ.get("ANDROID_AVD_HOME") or os.path.expanduser("~/.android/avd")


def list_avds():
    out = subprocess.run([tool("emulator"), "-list-avds"], capture_output=True, text=True).stdout
    return [line.strip() for line in out.splitlines() if line.strip() and not line.startswith("INFO")]


def running_emulators():
    """Map AVD name -> serial for every emulator adb can see."""
    found = {}
    for line in adb(None, "devices").splitlines()[1:]:
        parts = line.split()
        if len(parts) == 2 and parts[0].startswith("emulator-") and parts[1] == "device":
            name = adb(parts[0], "emu", "avd", "name", check=False, timeout=10).splitlines()
            if name:
                found[name[0].strip()] = parts[0]
    return found


def free_console_port():
    """Emulators take an even console port and the odd one above it, in 5554..5682."""
    for port in range(5580, 5682, 2):
        if all(port_is_free(p) for p in (port, port + 1)):
            return port
    raise SystemExit("No free emulator port between 5580 and 5682")


def port_is_free(port):
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def boot(avd, timeout=300, window=False):
    """Return (serial, booted_by_us). Reuses an emulator already running that AVD; headless unless window."""
    if avd not in list_avds():
        raise SystemExit("AVD '{}' not found; run /winteam-device-testing:setup-devices".format(avd))
    running = running_emulators()
    if avd in running:
        wait_for_boot(running[avd], timeout)
        return running[avd], False
    port = free_console_port()
    command = [tool("emulator"), "-avd", avd, "-port", str(port), "-no-snapshot-save", "-no-audio", "-no-boot-anim"]
    if not window:
        command.append("-no-window")
    subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    serial = "emulator-{}".format(port)
    wait_for_boot(serial, timeout)
    return serial, True


def wait_for_boot(serial, timeout=300):
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = adb(serial, "shell", "getprop", "sys.boot_completed", check=False, timeout=10).strip()
        if state == "1":
            time.sleep(2)
            return
        time.sleep(2)
    raise SystemExit("{} did not finish booting within {}s".format(serial, timeout))


def shutdown(serial):
    adb(serial, "emu", "kill", check=False, timeout=30)
    deadline = time.time() + 60
    while time.time() < deadline and serial in adb(None, "devices"):
        time.sleep(1)


def screen_info(serial):
    """Size bucket from the resource configuration, density in dpi, and the screen size in pixels."""
    config = adb(serial, "shell", "am", "get-config")
    bucket = next((token for line in config.splitlines() if line.startswith("config:")
                   for token in line.split("-") if token in SIZE_BUCKETS), None)
    density_out = adb(serial, "shell", "wm", "density")
    densities = re.findall(r"(\w+) density: (\d+)", density_out)
    density = int(dict(densities).get("Override", dict(densities).get("Physical", 160)))
    size = re.findall(r"(\d+)x(\d+)", adb(serial, "shell", "wm", "size"))[-1]
    return {"screenSize": bucket, "dpi": density, "pixels": [int(size[0]), int(size[1])]}


def display_state(serial):
    """(landscape, rotation): wider than tall is landscape, whatever the device's natural orientation."""
    out = adb(serial, "shell", "dumpsys", "window", "displays")
    size = re.search(r"\bcur=(\d+)x(\d+)", out)
    rotation = re.search(r"mCurrentRotation=ROTATION_(\d+)", out)
    return (bool(size) and int(size.group(1)) > int(size.group(2)),
            int(rotation.group(1)) if rotation else 0)


def rotate_to(serial, landscape, attempts=5):
    """Turn the emulated device a quarter at a time, which apps that follow the sensor obey; never upside down."""
    for _ in range(attempts):
        current, rotation = display_state(serial)
        if current == landscape and rotation != 180:
            return True
        adb(serial, "emu", "rotate", check=False, timeout=15)
        time.sleep(1.5)
    current, rotation = display_state(serial)
    return current == landscape and rotation != 180


def freeze_status_bar(serial):
    """SystemUI demo mode: a fixed clock and full battery and signal, like simctl status_bar."""
    adb(serial, "shell", "settings", "put", "global", "sysui_demo_allowed", "1", check=False)
    for extras in (["-e", "command", "enter"],
                   ["-e", "command", "clock", "-e", "hhmm", "0941"],
                   ["-e", "command", "battery", "-e", "level", "100", "-e", "plugged", "false"],
                   ["-e", "command", "network", "-e", "wifi", "show", "-e", "level", "4"],
                   ["-e", "command", "notifications", "-e", "visible", "false"]):
        adb(serial, "shell", "am", "broadcast", "-a", "com.android.systemui.demo", *extras, check=False)


def exit_demo_mode(serial):
    adb(serial, "shell", "am", "broadcast", "-a", "com.android.systemui.demo", "-e", "command", "exit",
        check=False)


def is_installed(serial, package):
    return "package:" in adb(serial, "shell", "pm", "path", package, check=False)


def install(serial, apk):
    if not os.path.isfile(apk):
        raise SystemExit("APK not found: {}".format(apk))
    adb(serial, "install", "-r", apk, timeout=600)


def launcher_activity(serial, package):
    """Xamarin names activities like crc64....SplashScreenActivity, so ask the package manager."""
    out = adb(serial, "shell", "cmd", "package", "resolve-activity", "--brief", package).strip().splitlines()
    component = out[-1].strip() if out else ""
    if "/" not in component:
        raise SystemExit("Could not resolve the launcher activity of {}".format(package))
    return component.split("/", 1)[1]


def clear_logcat(serial):
    """The UiAutomator2 server logs requests to logcat; clear it so typed text doesn't stay there."""
    adb(serial, "logcat", "-c", check=False, timeout=30)


def screenshot(serial, path):
    with open(path, "wb") as handle:
        subprocess.run([tool("adb"), "-s", serial, "exec-out", "screencap", "-p"], stdout=handle, check=True,
                       timeout=60)


def create_avd(name, source, width, height, density):
    """Write <name>.ini and <name>.avd/config.ini from the source AVD's config.ini, with a new screen."""
    home = avd_home()
    ini_path, avd_dir = os.path.join(home, name + ".ini"), os.path.join(home, name + ".avd")
    if os.path.exists(ini_path) or os.path.exists(avd_dir):
        raise SystemExit("AVD '{}' already exists; leaving it untouched".format(name))
    source_ini = read_ini(os.path.join(home, source + ".ini"))
    source_dir = source_ini.get("path") or os.path.join(home, source + ".avd")
    config = read_ini(os.path.join(source_dir, "config.ini"))
    config.pop("hw.device.hash2", None)
    config.update({
        "AvdId": name, "avd.ini.displayname": name.replace("_", " "),
        "hw.lcd.width": str(width), "hw.lcd.height": str(height), "hw.lcd.density": str(density),
        "hw.device.name": "winteam_tablet", "hw.device.manufacturer": "Generic",
        "skin.name": "{}x{}".format(width, height), "skin.path": "{}x{}".format(width, height),
        "skin.dynamic": "yes", "showDeviceFrame": "no", "hw.initialOrientation": "landscape",
        "hw.ramSize": "4096", "fastboot.forceColdBoot": "no", "fastboot.forceFastBoot": "yes",
    })
    os.makedirs(avd_dir)
    write_ini(os.path.join(avd_dir, "config.ini"), config)
    write_ini(ini_path, {"avd.ini.encoding": "UTF-8", "path": avd_dir, "path.rel": "avd/{}.avd".format(name),
                         "target": source_ini.get("target", config.get("target", ""))})
    return avd_dir


def read_ini(path):
    values = {}
    with open(path) as handle:
        for line in handle:
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.rstrip("\n").split("=", 1)
                values[key.strip()] = value.strip()
    return values


def write_ini(path, values):
    with open(path, "w") as handle:
        for key in values:
            handle.write("{}={}\n".format(key, values[key]))


def android_devices(data_dir):
    with open(os.path.join(data_dir, "devices.json")) as handle:
        return json.load(handle).get("android", [])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["check", "create-avd", "bucket"])
    parser.add_argument("--data", required=True, help="folder with devices.json")
    parser.add_argument("--role", help="device role for create-avd and bucket")
    args = parser.parse_args()
    devices = android_devices(args.data)
    if args.command == "check":
        avds, running = list_avds(), running_emulators()
        for device in devices:
            state = "found" if device["avd"] in avds else "missing"
            if device["avd"] in running:
                info = screen_info(running[device["avd"]])
                state += ", running as {}, bucket {}".format(running[device["avd"]], info["screenSize"])
            print("{}: {} ({})".format(device["role"], device["avd"], state))
        return
    device = next((d for d in devices if d["role"] == args.role), None)
    if device is None:
        raise SystemExit("No android device with role '{}' in devices.json".format(args.role))
    if args.command == "create-avd":
        spec = device.get("create")
        if not spec:
            raise SystemExit("devices.json has no 'create' entry for {}".format(device["avd"]))
        print("created {}".format(create_avd(device["avd"], spec["from"], spec["width"], spec["height"],
                                             spec["density"])))
        return
    serial, booted = boot(device["avd"])
    try:
        info = screen_info(serial)
        verdict = "ok" if info["screenSize"] == device.get("screenSize") else "MISMATCH"
        print("{}: bucket {} (expected {}) {}, {} dpi, {}x{} px".format(
            device["avd"], info["screenSize"], device.get("screenSize"), verdict, info["dpi"], *info["pixels"]))
    finally:
        if booted:
            shutdown(serial)
    if verdict != "ok":
        sys.exit(1)


if __name__ == "__main__":
    main()
