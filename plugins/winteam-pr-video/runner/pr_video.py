"""Shared pieces of winteam-pr-video: finding winteam-device-testing, preparing a device, running Appium, and the
helpers a scenario gets (Steps).

Most of the driving comes from winteam-device-testing, imported from its install: the WebDriver client
(wt_driver), the platform layer (platforms, android_devices) and the login routine (run_capture). This file adds
what a recording needs on top: a clean install, screen recording, and scenario helpers that may tap any button.
"""

import argparse
import base64
import json
import os
import re
import socket
import subprocess
import sys
import time

DEPENDENCY = "winteam-device-testing"
MIN_DEPENDENCY_VERSION = (0, 5, 1)
HERE = os.path.dirname(os.path.abspath(__file__))
LOG_FILTERS = os.path.join(HERE, "appium-log-filters.json")
BREW_PATHS = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/local/share/dotnet"]


class Failed(Exception):
    """A check failed in "after" mode: the fix isn't proven."""


# winteam-device-testing

def version_tuple(text):
    return tuple(int(part) for part in re.findall(r"\d+", text or "")[:3])


def find_dependency():
    """(root, data dir, version) of the installed winteam-device-testing.

    WT_DEVICE_TESTING_ROOT and WT_DEVICE_TESTING_DATA override the lookup, e.g. to work from a checkout.
    """
    root = os.environ.get("WT_DEVICE_TESTING_ROOT")
    plugin_id = DEPENDENCY + "@winteam"
    if not root:
        try:
            listing = json.loads(subprocess.run(["claude", "plugin", "list", "--json"], capture_output=True,
                                                text=True, check=True, timeout=60).stdout)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise SystemExit("Could not list Claude Code plugins ({}); set WT_DEVICE_TESTING_ROOT".format(error))
        found = [p for p in listing if p.get("id", "").startswith(DEPENDENCY + "@") and p.get("enabled", True)]
        if not found:
            raise SystemExit("{} is not installed or not enabled; install it (see the README)".format(DEPENDENCY))
        root, plugin_id = found[0]["installPath"], found[0]["id"]
    data = os.environ.get("WT_DEVICE_TESTING_DATA") or os.path.expanduser(
        "~/.claude/plugins/data/" + re.sub(r"[^A-Za-z0-9_-]", "-", plugin_id))
    with open(os.path.join(root, ".claude-plugin", "plugin.json")) as handle:
        version = json.load(handle).get("version", "0")
    return root, data, version


def load_dependency():
    """Import the dependency's modules and return (root, data dir)."""
    root, data, version = find_dependency()
    if version_tuple(version) < MIN_DEPENDENCY_VERSION:
        raise SystemExit("{} {} is too old; update it to {} or later".format(
            DEPENDENCY, version, ".".join(map(str, MIN_DEPENDENCY_VERSION))))
    sys.path.insert(0, os.path.join(root, "scripts"))
    return root, data


def load_json(path):
    with open(path) as handle:
        return json.load(handle)


def setting(value):
    """A plugin option substituted into the skill text; an unset one may arrive empty or as its placeholder."""
    return "" if not value or value.startswith("${") else value


# Appium

def appium_install(dependency_data):
    """(binary, APPIUM_HOME or None). WT_PR_VIDEO_APPIUM points at another appium binary, e.g. a global one."""
    override = os.environ.get("WT_PR_VIDEO_APPIUM")
    if override:
        return override, None
    home = os.path.join(dependency_data, "appium")
    binary = os.path.join(home, "node_modules", ".bin", "appium")
    if not os.path.exists(binary):
        raise SystemExit("Appium is not installed in {}; run /winteam-device-testing:setup-devices".format(home))
    return binary, home


def start_appium(dependency_data, log_path):
    """Our own server on a free port, so we never share one with winteam-device-testing. It logs to log_path,
    with typed text (the password included) redacted by the log filters. Returns (process, server URL)."""
    import wt_driver
    binary, home = appium_install(dependency_data)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    import android_devices
    env = dict(os.environ, PATH=":".join(BREW_PATHS + [os.environ.get("PATH", "")]))
    if home:
        env["APPIUM_HOME"] = home
    try:
        env.setdefault("ANDROID_HOME", android_devices.sdk_root())
    except SystemExit:
        pass  # iOS works without the Android SDK
    if "JAVA_HOME" not in env:
        java = subprocess.run(["/usr/libexec/java_home"], capture_output=True, text=True)
        if java.returncode == 0:
            env["JAVA_HOME"] = java.stdout.strip()
    process = subprocess.Popen([binary, "--address", "127.0.0.1", "--port", str(port), "--log-timestamp",
                                "--log-no-colors", "--log", log_path, "--log-filters", LOG_FILTERS],
                               env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    server = "http://127.0.0.1:{}".format(port)
    deadline = time.time() + 60
    while not wt_driver.server_is_up(server):
        if process.poll() is not None or time.time() >= deadline:
            stop_appium(process)
            raise SystemExit("Appium did not start; see {}".format(log_path))
        time.sleep(0.5)
    return process, server


def stop_appium(process):
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()


# Devices

def phone(dependency_root, platform, avd="", simulator=""):
    """The phone entry of the dependency's devices.json, with the user's AVD or simulator name on top."""
    devices = load_json(os.path.join(dependency_root, "data", "devices.json"))[platform]
    device = dict(next(d for d in devices if d["role"] == "phone"))
    if platform == "android" and setting(avd):
        device["avd"] = setting(avd)
    if platform == "ios" and setting(simulator):
        device["name"] = setting(simulator)
    return device


def app_settings(dependency_root):
    return load_json(os.path.join(dependency_root, "data", "app.json"))


def android_online(serial):
    import android_devices
    return "1 received" in android_devices.adb(serial, "shell", "ping -c1 -W2 google.com", check=False)


def prepare_device(dependency_root, platform_name, app_path=None, avd="", simulator=""):
    """Boot the phone (reusing a running one) and, with app_path, clean-install the app.

    Returns the dependency's platform object, ready for platform.capabilities().
    """
    import android_devices
    import platforms
    app = app_settings(dependency_root)
    device = phone(dependency_root, platform_name, avd, simulator)
    platform = platforms.make(platform_name, app, device, argparse.Namespace(keep_devices=False, apk=None))
    if platform_name == "android":
        serial, _ = android_devices.boot(device["avd"])
        platform.serial = serial
        if not android_online(serial):
            # The emulator sometimes loses its network while the Mac is online; toggling the radios brings it back.
            android_devices.adb(serial, "shell", "svc wifi disable; svc data disable; sleep 2; "
                                "svc wifi enable; svc data enable", check=False)
            for _ in range(15):
                if android_online(serial):
                    break
                time.sleep(2)
            else:
                raise SystemExit("The emulator has no network")
        # Don't flash the last typed character of the password in the recording.
        android_devices.adb(serial, "shell", "settings", "put", "system", "show_password", "0")
        if app_path:
            android_devices.adb(serial, "uninstall", platform.package, check=False)
            android_devices.adb(serial, "install", "-g", app_path, timeout=600)
        if not android_devices.is_installed(serial, platform.package):
            raise SystemExit("{} is not installed on {}; pass the app".format(platform.package, serial))
        platform.activity = android_devices.launcher_activity(serial, platform.package)
        android_devices.freeze_status_bar(serial)
    else:
        platform.prepare()
        if app_path:
            bundle = platform.app["bundleId"]
            subprocess.run(["xcrun", "simctl", "uninstall", platform.udid, bundle], capture_output=True)
            subprocess.run(["xcrun", "simctl", "install", platform.udid, app_path], capture_output=True, check=True)
            subprocess.run(["xcrun", "simctl", "privacy", platform.udid, "grant", "all", bundle], capture_output=True)
        subprocess.run(["open", "-a", "Simulator"], capture_output=True)
    return platform


def capabilities(platform, launch=True):
    caps = platform.capabilities()
    if platform.name == "ios":
        caps["appium:mjpegServerFramerate"] = 24  # the stream the iOS recording is made from (default 10 fps)
    else:
        # A Debug build's first launch after a clean install, on a just-booted emulator, can exceed 20 s.
        caps["appium:adbExecTimeout"] = 90000
        caps["appium:appWaitDuration"] = 90000
    if not launch:
        caps.pop("appium:forceAppLaunch", None)
        caps["appium:autoLaunch"] = False
        caps["appium:dontStopAppOnReset"] = True
    return caps


def open_session(server, platform, launch=True):
    """A session on our server. On Android, UiAutomator2 waits up to 10 s for the UI to go idle before every
    lookup, and the app's loading animations keep it busy, so each miss cost seconds; 100 ms is enough."""
    import wt_driver
    session = wt_driver.Session(server, capabilities(platform, launch))
    if platform.name == "android":
        session._cmd("POST", "/appium/settings", {"settings": {"waitForIdleTimeout": 100, "waitForSelectorTimeout": 0}})
    return session


def finish_device(platform):
    """After a session: nothing typed may stay in logcat (the UiAutomator2 server logs requests there)."""
    if platform.name == "android":
        import android_devices
        android_devices.clear_logcat(platform.serial)
        android_devices.exit_demo_mode(platform.serial)


# Recording

def start_recording(session, android):
    options = ({"timeLimit": 1800, "bitRate": 6000000} if android else
               {"timeLimit": 1800, "videoType": "libx264", "videoFps": 24, "videoQuality": "high"})
    session._cmd("POST", "/appium/start_recording_screen", {"options": options})


def stop_recording(session, path):
    payload = session._cmd("POST", "/appium/stop_recording_screen", {"options": {}}, timeout=600)
    with open(path, "wb") as handle:
        handle.write(base64.b64decode(payload or ""))


# Scenario helpers

def quote(value):
    return value.replace("\\", "\\\\").replace("'", "\\'")


class Steps:
    """What a scenario gets as `s`. Locators are winteam-device-testing's: an iOS predicate string, or an
    Android dict such as {"id": "numericPadLayout"} or {"text": "5", "in": {"id": "numericKeysGrid"}}.
    Build them with s.id(), s.text(), s.contains(), s.key() and s.pick() rather than by hand."""

    def __init__(self, session, platform, tenant, credentials, mode):
        """credentials: a function returning (user, secret), called only when the scenario logs in."""
        import run_capture
        self.rc = run_capture
        self.driver, self.device, self.mode = session, platform, mode
        self.app = platform.app
        self.ctx = {"app": platform.app, "platform": platform, "tenant": tenant}
        self.platform = platform.name
        self.android, self.ios = platform.name == "android", platform.name == "ios"
        self._credentials = credentials
        self.results = []
        self.discard_recording = False

    # Locators

    def id(self, name):
        return {"id": name} if self.android else "name == '{}'".format(quote(name))

    def text(self, text):
        return {"text": text} if self.android else "label == '{0}' OR name == '{0}'".format(quote(text))

    def contains(self, text):
        import platforms
        if self.android:
            return {"textMatches": ".*{}.*".format(platforms.literal_regex(text))}
        return "label CONTAINS '{}'".format(quote(text))

    def key(self, digit):
        """A PIN keypad key."""
        if self.android:
            return {"class": "android.widget.Button", "text": str(digit)}
        return "type == 'XCUIElementTypeButton' AND name == '{}'".format(digit)

    def pick(self, android=None, ios=None):
        return android if self.android else ios

    # Actions

    def find(self, locator, timeout=15):
        return self.device.wait_for(self.driver, locator, timeout=timeout)

    def exists(self, locator, timeout=3):
        """Whether the element is visible within the timeout."""
        deadline = time.time() + timeout
        while True:
            if self.device.find_visible(self.driver, locator) is not None:
                return True
            if time.time() >= deadline:
                return False
            time.sleep(0.5)

    def gone(self, locator, timeout=5):
        """Whether the element is no longer visible within the timeout."""
        deadline = time.time() + timeout
        while True:
            if self.device.find_visible(self.driver, locator) is None:
                return True
            if time.time() >= deadline:
                return False
            time.sleep(0.5)

    def tap(self, locator, timeout=15):
        self.driver.tap_element(self.find(locator, timeout))

    def type(self, locator, text):
        """Type into a field. Never for credentials: only log_in() and sign_in() type those."""
        self.driver.set_value(self.find(locator), text)

    def long_press(self, locator, seconds=2):
        x, y = self.driver.center(self.find(locator))
        self.driver.long_press(x, y, int(seconds * 1000))

    def swipe(self, x1, y1, x2, y2, ms=500):
        self.driver.swipe(x1, y1, x2, y2, ms)

    def back(self):
        if not self.android:
            raise RuntimeError("no back button on iOS")
        self.driver.back()

    def pause(self, seconds):
        time.sleep(seconds)

    def adb(self, *args):
        """Run an adb command on the emulator, e.g. s.adb("shell", "cmd", "uimode", "night", "yes")."""
        import android_devices
        return android_devices.adb(self.device.serial, *args, check=False)

    def simctl(self, *args):
        """Run an xcrun simctl command on the simulator; the udid is added after the subcommand, e.g.
        s.simctl("ui", "appearance", "dark")."""
        command = ["xcrun", "simctl", args[0], self.device.udid] + list(args[1:])
        return subprocess.run(command, capture_output=True, text=True).stdout

    # App flows

    def select_environment(self):
        """Long-press the hidden dev-tools button and pick the Testing environment."""
        self.device.select_environment(self.driver, self.app["environment"])

    def log_in(self):
        """Log In, then fill and submit the B2C form through the keyboard. The recording is thrown away if the
        form wasn't filled right, since a frame could then show the password in the email field."""
        user, secret = self._credentials()
        try:
            self.rc.log_in(self.driver, self.ctx, user, secret)
        except BaseException:
            self.discard_recording = True
            raise

    def close_sign_in(self):
        """Leave the B2C sign-in page without signing in: Android back; on iOS the Safari sheet's Close, tapped by
        coordinates because an element tap on it doesn't dismiss the sheet."""
        if self.android:
            self.driver.back()
            return
        x, y = self.driver.center(self.find("type == 'XCUIElementTypeButton' AND name == 'Close'"))
        self.driver.tap(x, y)

    def set_up_pin(self, pin):
        """On "Set up a PIN instead?": Set up PIN, then the PIN twice (create and confirm)."""
        button = self.pick(android={"id": "main_action_button"},
                           ios="type == 'XCUIElementTypeButton' AND label == 'Set up PIN'")
        self.tap(button, timeout=60)
        # A tap while the prompt is still animating in can be lost: tap again if the keypad didn't open.
        if not self.exists(self.key(1), 6) and self.exists(button, 1):
            self.tap(button)
        self.find(self.key(1), 15)
        self.pause(0.5)
        self.enter_pin(pin)
        self.pause(1)
        self.enter_pin(pin)

    def enter_pin(self, pin):
        for digit in str(pin):
            self.tap(self.key(digit))
            self.pause(0.3)

    def finish_sign_in(self, timeout=150):
        """After the sign-in (and the PIN setup, if any): pick the tenant on "Choose an account" and close the
        app's prompts (the PIN offer with No thanks, notifications with Not right now) until Home loads."""
        deadline = time.time() + timeout
        while not self.rc.anchor_present(self.driver, self.ctx, self.app["homeAnchor"]):
            if not self.rc.choose_account(self.driver, self.ctx):
                self.rc.dismiss_prompts(self.driver, self.ctx)
            if time.time() >= deadline:
                raise RuntimeError("Home did not appear after signing in")
            time.sleep(1)

    def sign_in(self, pin=None):
        """From a fresh install to Home: Testing environment, password login, a PIN when given, tenant, prompts."""
        self.select_environment()
        self.pause(1)
        self.log_in()
        if pin is not None:
            self.set_up_pin(pin)
        self.finish_sign_in()
        self.pause(1)

    def log_out(self):
        """Side menu > Log out, then wait for the login screen."""
        self.tap(self.app["homeAnchor"]["all"][0])
        self.pause(0.8)
        self.tap(self.text("Log out"))
        login = self.pick(android=self.app["loginButton"],
                          ios="type == 'XCUIElementTypeButton' AND (label == 'Log In' OR label == 'Log in with PIN')")
        self.find(login, timeout=30)

    # Expected result

    def check(self, name, condition):
        """condition() must return true. In "before" mode a failure is only logged (it shows the bug); in "after"
        mode it stops the run with exit code 2."""
        ok, error = False, None
        try:
            ok = bool(condition())
        except Exception as exc:  # noqa: BLE001 - any failure of the condition is a failed check
            error = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        self.results.append(dict(name=name, ok=ok, **({"error": error} if error else {})))
        print("{} {}{}".format("PASS" if ok else "FAIL", name, " ({})".format(error) if error else ""), flush=True)
        if not ok and self.mode == "after":
            raise Failed(name)
