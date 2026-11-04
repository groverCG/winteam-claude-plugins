"""What differs between the iOS simulator and the Android emulator, behind one interface for run_capture.py.

A locator ("spec") in app.json and screens.json is platform-specific:
  iOS      a predicate string, e.g. "type == 'XCUIElementTypeButton' AND label == 'Home'"
  Android  a dict combined into one UiSelector:
             id        resource id in the app package ("home" -> "com.workwave.winteam:id/home"),
                       or a full id when it contains ':'
             rawId     resource id as is (the B2C WebView's "email")
             class     class name
             text      exact text;  label: the same, case-insensitive;  textMatches: a regex
             desc      exact content-desc
             clickable, selected  true or false
             in        a spec for an ancestor: matches this spec inside it
Everything that taps goes through run_capture.py, which owns the read-only guards.
"""

import json
import subprocess
import time

import android_devices
import wt_driver

ORIENTATIONS = {"portrait": "PORTRAIT", "landscape": "LANDSCAPE"}
GONE_ERRORS = {"no such alert", "no such element", "stale element reference"}
ALERT_BUTTONS = ("android:id/button[123]|com[.]android[.]permissioncontroller:id/permission_.*_button")
REGEX_SPECIALS = set("\\^$.|?*+()[]{}")


def label_text(value):
    """Normalise a label for list matching: case, surrounding space and curly apostrophes don't count."""
    return (value or "").strip().replace("’", "'").casefold()


class DeviceError(Exception):
    """The device can't produce a meaningful capture; recorded in the manifest, the other device still runs."""


class IosPlatform:
    name = "ios"
    backspace = "\b"
    enter = "\n"
    density = 1.0

    def __init__(self, app, device, args):
        self.app, self.device, self.args = app, device, args
        self.udid = None

    # Device lifecycle

    def prepare(self):
        self.udid = resolve_udid(self.device)
        subprocess.run(["xcrun", "simctl", "boot", self.udid], capture_output=True)
        subprocess.run(["xcrun", "simctl", "bootstatus", self.udid, "-b"], capture_output=True, check=True)
        subprocess.run(["xcrun", "simctl", "status_bar", self.udid, "override", "--time", "9:41", "--batteryLevel",
                        "100", "--batteryState", "charged", "--wifiBars", "3"], capture_output=True)
        return {"name": self.device["name"], "runtime": self.device["runtime"], "udid": self.udid}

    def describe(self):
        return "{} ({})".format(self.device["name"], self.udid)

    def cleanup(self):
        """Simulators stay booted; the skill shuts them down after reviewing."""

    def capabilities(self):
        return {
            "platformName": "iOS",
            "appium:automationName": "XCUITest",
            "appium:udid": self.udid,
            "appium:bundleId": self.app["bundleId"],
            "appium:noReset": True,
            "appium:forceAppLaunch": True,
            "appium:newCommandTimeout": 900,
            "appium:wdaLaunchTimeout": 600000,
        }

    def after_login(self):
        """Nothing on the simulator keeps the typed text."""

    # Locating

    def find(self, session, spec):
        return session.find("-ios predicate string", spec)

    def find_visible(self, session, spec):
        return session.find("-ios predicate string", "({}) AND visible == 1".format(spec))

    def wait_for(self, session, spec, timeout=20.0):
        return session.wait_for("-ios predicate string", spec, timeout=timeout)

    def with_tenant(self, spec, tenant):
        return spec.replace("{tenant}", tenant.replace("\\", "\\\\").replace("'", "\\'"))

    def button_with_label(self, label):
        return "type == 'XCUIElementTypeButton' AND label == '{}'".format(label)

    def loading_visible(self, session):
        loading = " OR ".join("label == '{}'".format(label) for label in self.app["loadingLabels"])
        return self.find_visible(session, loading) is not None

    def labels(self, session, element):
        """The tapped element's own label, and every label the guard must also check (the same one on iOS)."""
        label = session.attribute(element, "label") or session.attribute(element, "name") or ""
        return label, [label]

    def blocked_id(self, session, element):
        return None

    def field_text(self, session, element):
        """A field's typed content; an empty iOS web field reports its label as its value."""
        value = session.attribute(element, "value") or ""
        return "" if value == session.attribute(element, "label") else value

    # Alerts

    def alert_buttons(self, session):
        if session.alert_text() is None:
            return []
        return session.alert_buttons()

    def press_alert_button(self, session, label):
        session.press_alert_button(label)

    # Login routine pieces

    def select_environment(self, session, environment):
        """Exempt from guarded_tap: it taps only the fixed environment-picker controls."""
        switch = self.wait_for(session, "name == '{}'".format(self.app["environmentSwitch"]), timeout=30)
        x, y = session.center(switch)
        session.long_press(x, y, 1500)
        field = self.wait_for(session, "type == 'XCUIElementTypeTextField'", timeout=15)
        if (session.attribute(field, "value") or "").strip() != environment:
            session.tap_element(field)
            wheel = self.wait_for(session, "type == 'XCUIElementTypePickerWheel'", timeout=10)
            session.set_value(wheel, environment)
            time.sleep(1)
            session.tap_element(self.wait_for(session, "type == 'XCUIElementTypeButton' AND name == 'Done'"))
            time.sleep(1)
        current = (session.attribute(field, "value") or "").strip()
        if current != environment:
            raise SystemExit("Environment picker shows '{}' and could not be set to '{}'".format(
                current, environment))
        session.tap_element(self.wait_for(session, "type == 'XCUIElementTypeButton' AND name == 'Submit'"))
        time.sleep(2)

    def try_native_scroll(self, session, element):
        session.execute("mobile: scroll", {"elementId": element, "toVisible": True})

    # Capture

    def relaunch(self, session):
        session.execute("mobile: terminateApp", {"bundleId": self.app["bundleId"]})
        time.sleep(1)
        session.execute("mobile: activateApp", {"bundleId": self.app["bundleId"]})
        time.sleep(3)

    def set_orientation(self, session, name):
        session.set_orientation(ORIENTATIONS[name])

    def screenshot(self, path):
        subprocess.run(["xcrun", "simctl", "io", self.udid, "screenshot", path], capture_output=True, check=True)


class AndroidPlatform:
    name = "android"
    backspace = ""
    enter = ""

    def __init__(self, app, device, args):
        self.app, self.device, self.args = app, device, args
        self.package = app["package"]
        self.serial, self.booted, self.activity, self.density = None, False, None, 1.0

    # Device lifecycle

    def prepare(self):
        self.serial, self.booted = android_devices.boot(self.device["avd"], window=self.args.show)
        info = android_devices.screen_info(self.serial)
        self.density = info["dpi"] / 160.0
        report = {"avd": self.device["avd"], "api": self.device.get("api"), "serial": self.serial,
                  "screenSize": info["screenSize"], "dpi": info["dpi"], "pixels": info["pixels"]}
        expected = self.device.get("screenSize")
        if expected and info["screenSize"] != expected:
            raise DeviceError("{} resolves to the '{}' size bucket, not '{}': its captures would not show the "
                              "resources this role should get".format(self.device["avd"], info["screenSize"],
                                                                      expected))
        if self.args.apk:
            android_devices.install(self.serial, self.args.apk)
            android_devices.adb(self.serial, "shell", "run-as", self.package, "rm", "-rf", "files/.__override__",
                                check=False)
        if not android_devices.is_installed(self.serial, self.package):
            raise DeviceError("{} is not installed on {}; pass --apk".format(self.package, self.serial))
        self.activity = android_devices.launcher_activity(self.serial, self.package)
        android_devices.freeze_status_bar(self.serial)
        return report

    def describe(self):
        return "{} ({})".format(self.device["avd"], self.serial)

    def cleanup(self):
        if self.serial is None:
            return
        android_devices.clear_logcat(self.serial)
        if self.booted:
            android_devices.shutdown(self.serial)
        else:
            android_devices.exit_demo_mode(self.serial)

    def capabilities(self):
        return {
            "platformName": "Android",
            "appium:automationName": "UiAutomator2",
            "appium:udid": self.serial,
            "appium:appPackage": self.package,
            "appium:appActivity": self.activity,
            "appium:appWaitActivity": "*",
            "appium:noReset": True,
            "appium:forceAppLaunch": True,
            "appium:skipLogcatCapture": True,
            "appium:newCommandTimeout": 900,
            "appium:uiautomator2ServerLaunchTimeout": 120000,
        }

    def after_login(self):
        """The UiAutomator2 server logs requests to logcat, typed text included."""
        android_devices.clear_logcat(self.serial)

    # Locating

    def selector(self, spec):
        parts = []
        for key, value in spec.items():
            if key == "in":
                continue
            if key == "id":
                value = value if ":" in value else "{}:id/{}".format(self.package, value)
                parts.append('resourceId("{}")'.format(quoted(value)))
            elif key == "rawId":
                parts.append('resourceId("{}")'.format(quoted(value)))
            elif key == "class":
                parts.append('className("{}")'.format(quoted(value)))
            elif key == "text":
                parts.append('text("{}")'.format(quoted(value)))
            elif key == "label":
                parts.append('textMatches("(?i){}")'.format(quoted(literal_regex(value))))
            elif key == "textMatches":
                parts.append('textMatches("{}")'.format(quoted(value)))
            elif key == "desc":
                parts.append('description("{}")'.format(quoted(value)))
            elif key in ("clickable", "selected"):
                parts.append("{}({})".format(key, "true" if value else "false"))
            else:
                raise ValueError("unknown Android locator key '{}' in {}".format(key, spec))
        selector = "new UiSelector()" + "".join("." + part for part in parts)
        if "in" in spec:
            selector = "{}.childSelector({})".format(self.selector(spec["in"]), selector)
        return selector

    def find(self, session, spec):
        return self.find_visible(session, spec)

    def find_visible(self, session, spec):
        for element in session.find_all("-android uiautomator", self.selector(spec)):
            try:
                if session.displayed(element):
                    return element
            except wt_driver.WebDriverError as error:
                if error.error not in GONE_ERRORS:
                    raise
        return None

    def wait_for(self, session, spec, timeout=20.0, interval=0.5):
        deadline = time.time() + timeout
        while True:
            element = self.find_visible(session, spec)
            if element is not None:
                return element
            if time.time() >= deadline:
                raise wt_driver.WebDriverError("timeout", "{} not found after {}s".format(
                    json.dumps(spec), timeout))
            time.sleep(interval)

    def with_tenant(self, spec, tenant):
        return {key: (self.with_tenant(value, tenant) if isinstance(value, dict) else
                      value.replace("{tenant}", tenant) if isinstance(value, str) else value)
                for key, value in spec.items()}

    def button_with_label(self, label):
        return {"class": "android.widget.Button", "label": label}

    def loading_visible(self, session):
        return any(self.find_visible(session, spec) is not None for spec in self.app["loading"])

    def labels(self, session, element):
        """Own text or content-desc, plus every text inside: a punch button keeps its label in a child."""
        own = clean(session.attribute(element, "text")) or clean(session.attribute(element, "content-desc"))
        inner = [clean(session.attribute(child, "text"))
                 for child in session.find_within(element, "xpath", ".//*[@text!='']")]
        inner = [text for text in inner if text]
        return own or (inner[0] if inner else ""), [own] + inner

    def blocked_id(self, session, element):
        """The blockedIds view the tap would land on, if any; fails closed if the check can't run.

        Checked by where the tap lands, not by the element's own id: a punch button is a container whose inner
        Button has an id of its own and no label, and UiAutomator2 can't search an element's ancestors.
        An element that vanished mid-check raises its error, so the caller looks again without tapping.
        """
        try:
            x, y = session.center(element)
            for name in self.app.get("blockedIds", []):
                for blocked in session.find_all("id", "{}:id/{}".format(self.package, name)):
                    r = session.rect(blocked)
                    if r["x"] <= x <= r["x"] + r["width"] and r["y"] <= y <= r["y"] + r["height"]:
                        return name
        except wt_driver.WebDriverError as error:
            if error.error in GONE_ERRORS:
                raise
            return "unknown (the blockedIds check failed: {})".format(error.error)
        return None

    def field_text(self, session, element):
        return session.attribute(element, "text") or ""

    # Alerts: AlertDialog buttons and the permission controller's dialog

    def alert_button_elements(self, session):
        found = session.find_all("-android uiautomator",
                                 'new UiSelector().resourceIdMatches("{}")'.format(quoted(ALERT_BUTTONS)))
        visible = []
        for element in found:
            try:
                text = clean(session.attribute(element, "text"))
                if text and session.displayed(element):
                    visible.append((text, element))
            except wt_driver.WebDriverError as error:
                if error.error not in GONE_ERRORS:
                    raise
        return visible

    def alert_buttons(self, session):
        return [label for label, _ in self.alert_button_elements(session)]

    def press_alert_button(self, session, label):
        for text, element in self.alert_button_elements(session):
            if text == label:
                session.tap_element(element)
                return
        raise wt_driver.WebDriverError("no such alert", "the alert closed before '{}' was pressed".format(label))

    # Login routine pieces

    def select_environment(self, session, environment):
        """Exempt from guarded_tap: it taps only the dev-tools button, the spinner, its row and the submit id."""
        switch = self.wait_for(session, self.app["environmentSwitch"], timeout=30)
        x, y = session.center(switch)
        session.long_press(x, y, 1500)
        spinner = self.wait_for(session, self.app["environmentSpinner"], timeout=15)
        if self.spinner_value(session, spinner) != environment:
            session.tap_element(spinner)
            row = self.wait_for(session, {"class": "android.widget.TextView", "text": environment,
                                          "clickable": True}, timeout=10)
            session.tap_element(row)
            time.sleep(1)
            spinner = self.wait_for(session, self.app["environmentSpinner"], timeout=10)
        current = self.spinner_value(session, spinner)
        if current != environment:
            raise SystemExit("Environment picker shows '{}' and could not be set to '{}'".format(
                current, environment))
        session.tap_element(self.wait_for(session, self.app["environmentSubmit"]))
        time.sleep(2)

    def spinner_value(self, session, spinner):
        texts = session.find_within(spinner, "xpath", ".//android.widget.TextView")
        return clean(session.attribute(texts[0], "text")).strip() if texts else ""

    def try_native_scroll(self, session, element):
        raise wt_driver.WebDriverError("unsupported", "no element scroll on Android; swipe instead")

    # Capture

    def relaunch(self, session):
        session.execute("mobile: terminateApp", {"appId": self.package})
        time.sleep(1)
        session.execute("mobile: activateApp", {"appId": self.package})
        time.sleep(3)

    def set_orientation(self, session, name):
        """The app's activity follows the sensor, which ignores UiAutomator2's rotation; turn the emulator."""
        if not android_devices.rotate_to(self.serial, landscape=(name == "landscape")):
            raise wt_driver.WebDriverError("orientation", "could not rotate {} to {}".format(self.serial, name))

    def screenshot(self, path):
        android_devices.screenshot(self.serial, path)


def make(platform, app, device, args):
    merged = {key: value for key, value in app.items() if key not in ("ios", "android")}
    merged.update(app[platform])
    return (IosPlatform if platform == "ios" else AndroidPlatform)(merged, device, args)


def resolve_udid(device):
    listing = json.loads(subprocess.run(["xcrun", "simctl", "list", "devices", "available", "-j"],
                                        capture_output=True, text=True, check=True).stdout)
    runtime_key = "com.apple.CoreSimulator.SimRuntime." + device["runtime"].replace(" ", "-").replace(".", "-")
    for candidate in listing["devices"].get(runtime_key, []):
        if candidate["name"] == device["name"]:
            return candidate["udid"]
    raise SystemExit("Simulator '{}' ({}) not found; create it in Xcode > Devices and Simulators".format(
        device["name"], device["runtime"]))


def clean(value):
    """UiAutomator2 reports a missing attribute as None or the string "null"."""
    return "" if value in (None, "null") else value


def quoted(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def literal_regex(value):
    """A regex matching value literally: specials go in a character class, and only \\ [ ] ^ get escaped."""
    return "".join("[{}]".format(char) if char in REGEX_SPECIALS and char not in "\\[]^" else
                   "\\" + char if char in "\\[]^" else char for char in value)
