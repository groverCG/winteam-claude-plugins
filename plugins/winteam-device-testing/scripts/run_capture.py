"""Capture WinTeam screens on the iOS phone and tablet simulators.

Starts its own Appium server with logging off, since Appium logs every typed string, the password
included. Prunes expired runs, then for each device: boot it, freeze the status bar, start a session,
switch to the Testing environment, log in, visit each requested screen from screens.json and save a
screenshot and the page source in every requested orientation. Writes manifest.json into a new run folder.

Navigation is read-only: every tap after login goes through guarded_tap, which refuses blockedLabels and,
on screens of a protected domain, anything outside that domain's allowedTaps.

Credentials come from the macOS keychain item "winteam-device-testing" (account = email, password =
secret), or from WT_TEST_USER / WT_TEST_PASSWORD. They are never printed or written to disk.
"""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prune_runs  # noqa: E402
import wt_driver  # noqa: E402

KEYCHAIN_SERVICE = "winteam-device-testing"
ORIENTATIONS = {"portrait": "PORTRAIT", "landscape": "LANDSCAPE"}


def log(message):
    print(message, flush=True)


def load_json(folder, name):
    with open(os.path.join(folder, name)) as handle:
        return json.load(handle)


def credentials():
    try:
        meta = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE],
                              capture_output=True, text=True, check=True).stdout
        account = re.search(r'"acct"<blob>="([^"]*)"', meta).group(1)
        secret = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                                capture_output=True, text=True, check=True).stdout.rstrip("\n")
        return account, secret
    except (subprocess.CalledProcessError, AttributeError):
        pass
    user, secret = os.environ.get("WT_TEST_USER"), os.environ.get("WT_TEST_PASSWORD")
    if user and secret:
        return user, secret
    raise SystemExit("No credentials: add the keychain item '{}' or set WT_TEST_USER/WT_TEST_PASSWORD".format(
        KEYCHAIN_SERVICE))


def resolve_udid(device):
    listing = json.loads(subprocess.run(["xcrun", "simctl", "list", "devices", "available", "-j"],
                                        capture_output=True, text=True, check=True).stdout)
    runtime_key = "com.apple.CoreSimulator.SimRuntime." + device["runtime"].replace(" ", "-").replace(".", "-")
    for candidate in listing["devices"].get(runtime_key, []):
        if candidate["name"] == device["name"]:
            return candidate["udid"]
    raise SystemExit("Simulator '{}' ({}) not found; create it in Xcode > Devices and Simulators".format(
        device["name"], device["runtime"]))


def prepare_simulator(udid):
    subprocess.run(["xcrun", "simctl", "boot", udid], capture_output=True)
    subprocess.run(["xcrun", "simctl", "bootstatus", udid, "-b"], capture_output=True, check=True)
    subprocess.run(["xcrun", "simctl", "status_bar", udid, "override", "--time", "9:41", "--batteryLevel", "100",
                    "--batteryState", "charged", "--wifiBars", "3"], capture_output=True)


def screenshot(udid, path):
    subprocess.run(["xcrun", "simctl", "io", udid, "screenshot", path], capture_output=True, check=True)


def predicate(expression):
    return ("-ios predicate string", expression)


def find_visible(session, expression):
    return session.find(*predicate("({}) AND visible == 1".format(expression)))


def is_blocked(app, label):
    label = (label or "").strip().lower()
    return any(label == b.lower() or label.startswith(b.lower() + " ") for b in app["blockedLabels"])


def guarded_tap(session, app, element, allowed=None):
    """The single tap point after login: refuse blocked labels, and anything outside `allowed` when given."""
    label = session.attribute(element, "label") or session.attribute(element, "name") or ""
    if is_blocked(app, label):
        raise wt_driver.WebDriverError("blocked", "refused to tap '{}': it is on blockedLabels".format(label))
    if allowed is not None and label not in allowed:
        raise wt_driver.WebDriverError("blocked", "refused to tap '{}': not an allowed tap here".format(label))
    session.tap_element(element)


def handle_alert(session, app):
    """Press a known-safe button by name; accept only a lone informational button. Refuse anything else."""
    buttons = session.alert_buttons()
    if len(buttons) == 1 and buttons[0] in app["alertAcceptLabels"]:
        choice = buttons[0]
    else:
        choice = next((b for b in buttons if b in app["alertDismissLabels"]), None)
    if choice is None or is_blocked(app, choice):
        raise wt_driver.WebDriverError("blocked", "alert with buttons {} has no safe choice".format(buttons))
    session.press_alert_button(choice)


def dismiss_prompts(session, app):
    """Close alerts and the app's own opt-in screens, if any are showing."""
    for _ in range(4):
        if session.alert_text() is not None:
            handle_alert(session, app)
            time.sleep(1)
            continue
        for label in app["dismissLabels"]:
            button = find_visible(session, "type == 'XCUIElementTypeButton' AND label == '{}'".format(label))
            if button is not None:
                guarded_tap(session, app, button, allowed=app["dismissLabels"])
                time.sleep(1.5)
                break
        else:
            return


def select_environment(session, app):
    """Login routine, exempt from guarded_tap: it taps only the fixed environment-picker controls."""
    switch = session.wait_for(*predicate("name == '{}'".format(app["environmentSwitch"])), timeout=30)
    x, y = session.center(switch)
    session.long_press(x, y, 1500)
    field = session.wait_for(*predicate("type == 'XCUIElementTypeTextField'"), timeout=15)
    if (session.attribute(field, "value") or "").strip() != app["environment"]:
        session.tap_element(field)
        wheel = session.wait_for(*predicate("type == 'XCUIElementTypePickerWheel'"), timeout=10)
        session.set_value(wheel, app["environment"])
        time.sleep(1)
        session.tap_element(session.wait_for(*predicate("type == 'XCUIElementTypeButton' AND name == 'Done'")))
        time.sleep(1)
    current = (session.attribute(field, "value") or "").strip()
    if current != app["environment"]:
        raise SystemExit("Environment picker shows '{}' and could not be set to '{}'".format(
            current, app["environment"]))
    session.tap_element(session.wait_for(*predicate("type == 'XCUIElementTypeButton' AND name == 'Submit'")))
    time.sleep(2)


def field_value(session, expression):
    element = session.find(*predicate(expression))
    return session.attribute(element, "value") if element else None


def clear_focused_field(session, element):
    """Delete whatever the focused field holds; an empty web field reports its label as its value."""
    value = session.attribute(element, "value") or ""
    if value and value != session.attribute(element, "label"):
        session.type_text("\b" * (len(value) + 2))
        time.sleep(0.5)


def log_in(session, app, user, secret):
    """Fill the B2C form through the keyboard only: Tab between fields, Enter to submit.

    Login routine, exempt from guarded_tap: it taps only Log In and the email field. The page keeps
    earlier input across app launches, and the keyboard toolbar covers the password field on a phone, so
    fields are cleared before typing and never tapped once the keyboard is up.
    """
    session.tap_element(session.wait_for(*predicate(app["loginButton"]), timeout=30))
    email = session.wait_for(*predicate(app["b2c"]["emailField"]), timeout=45)
    time.sleep(1.5)
    r = session.rect(email)
    session.tap(int(r["x"] + r["width"] - 4), int(r["y"] + r["height"] / 2))
    time.sleep(1)
    clear_focused_field(session, email)
    session.type_text(user)
    time.sleep(0.5)
    if field_value(session, app["b2c"]["emailField"]) != user:
        raise SystemExit("The email did not land in the email field (focus problem); stopping before the password")
    session.type_text("\t")
    time.sleep(1)
    password = session.wait_for(*predicate(app["b2c"]["passwordField"]))
    clear_focused_field(session, password)
    session.type_text(secret)
    time.sleep(0.5)
    typed_email = field_value(session, app["b2c"]["emailField"])
    typed_secret = field_value(session, app["b2c"]["passwordField"]) or ""
    if typed_email != user or len(typed_secret) != len(secret):
        raise SystemExit("Sign-in form was not filled correctly (focus problem); stopping without submitting")
    session.type_text("\n")


def anchor_present(session, anchor):
    """An anchor is a predicate, or {"all": [...], "any": [...]}; every "all" and one "any" must be visible."""
    if isinstance(anchor, str):
        anchor = {"all": [anchor]}
    if any(find_visible(session, expression) is None for expression in anchor.get("all", [])):
        return False
    return not anchor.get("any") or any(find_visible(session, e) is not None for e in anchor["any"])


def wait_for_anchor(session, app, anchor, timeout):
    """Prompts can appear late, after the step that opened the screen, so keep closing them while waiting."""
    deadline = time.time() + timeout
    while not anchor_present(session, anchor):
        if time.time() >= deadline:
            raise wt_driver.WebDriverError("timeout", "anchor {} not visible after {}s".format(anchor, timeout))
        dismiss_prompts(session, app)
        time.sleep(0.5)


def go_home(session, app):
    """Back out to the dashboard: pushed screens hide the tab bar, so try the back button first."""
    for _ in range(12):
        dismiss_prompts(session, app)
        if anchor_present(session, app["homeAnchor"]):
            return
        back = find_visible(session, app["backButton"])
        target = back if back is not None else find_visible(session, app["homeTab"])
        if target is not None:
            guarded_tap(session, app, target)
        time.sleep(2.0)
    raise wt_driver.WebDriverError("navigation", "could not get back to the dashboard")


def ensure_logged_in(session, app, user, secret, role):
    """From a fresh launch, reach the dashboard: log in if the login screen shows."""
    login = predicate(app["loginButton"])
    deadline = time.time() + 60
    while session.find(*login) is None and not anchor_present(session, app["homeAnchor"]):
        dismiss_prompts(session, app)
        if time.time() >= deadline:
            raise wt_driver.WebDriverError("timeout", "neither the login screen nor the dashboard appeared")
        time.sleep(1)
    if session.find(*login) is None:
        return
    log("[{}] switching to {} and logging in".format(role, app["environment"]))
    select_environment(session, app)
    log_in(session, app, user, secret)
    deadline = time.time() + 120
    while not anchor_present(session, app["homeAnchor"]):
        dismiss_prompts(session, app)
        if time.time() >= deadline:
            raise wt_driver.WebDriverError("timeout", "the dashboard did not appear after signing in")
        time.sleep(1)


def relaunch(session, app):
    """Cold-start the app; it logs out on a cold start, so log in again afterwards."""
    session.execute("mobile: terminateApp", {"bundleId": app["bundleId"]})
    time.sleep(1)
    session.execute("mobile: activateApp", {"bundleId": app["bundleId"]})
    time.sleep(3)


def wait_until_loaded(session, app, anchor, timeout=30.0):
    """Wait for the screen's anchor, then for any loading label to clear."""
    wait_for_anchor(session, app, anchor, timeout)
    wait_while_loading(session, app, timeout)


def wait_while_loading(session, app, timeout=60.0):
    """A tap made while a screen is still loading can be undone when it finishes, e.g. the Time tab's pager."""
    deadline = time.time() + timeout
    loading = " OR ".join("label == '{}'".format(label) for label in app["loadingLabels"])
    while find_visible(session, loading) is not None and time.time() < deadline:
        time.sleep(0.5)


def run_steps(session, app, screen):
    """Navigation steps; a screen in a protected domain may only tap that domain's allowedTaps."""
    domain = app["protectedDomains"].get(screen.get("domain", ""))
    allowed = domain["allowedTaps"] if domain else None
    for step in screen["ios"]["steps"]:
        wait_while_loading(session, app)
        element = session.wait_for(*predicate(step["predicate"]), timeout=step.get("timeout", 20))
        if step["action"] == "tap":
            guarded_tap(session, app, element, allowed)
            time.sleep(step.get("settle", 2.0))
            dismiss_prompts(session, app)


def reset_orientation(session):
    try:
        session.set_orientation("PORTRAIT")
    except wt_driver.WebDriverError:
        pass


def capture_screen(session, app, udid, screen_id, spec, orientations, out_dir):
    """The anchor is checked once, in portrait: rotating can scroll it out of view, which is a finding."""
    results = {}
    reset_orientation(session)
    wait_until_loaded(session, app, spec["anchor"])
    for name in orientations:
        session.set_orientation(ORIENTATIONS[name])
        time.sleep(2.0)
        dismiss_prompts(session, app)
        wait_until_loaded(session, app, {"all": []})
        base = os.path.join(out_dir, "{}-{}".format(screen_id, name))
        screenshot(udid, base + ".png")
        with open(base + ".xml", "w") as handle:
            handle.write(session.source())
        results[name] = {"png": base + ".png", "xml": base + ".xml"}
    session.set_orientation("PORTRAIT")
    time.sleep(1.0)
    return results


def capture_device(args, app, device, screens, user, secret):
    udid = resolve_udid(device)
    out_dir = os.path.join(args.out, device["role"])
    os.makedirs(out_dir, exist_ok=True)
    report = {"name": device["name"], "runtime": device["runtime"], "udid": udid, "screens": {}, "errors": {}}
    log("[{}] booting {} ({})".format(device["role"], device["name"], udid))
    prepare_simulator(udid)
    capabilities = {
        "platformName": "iOS",
        "appium:automationName": "XCUITest",
        "appium:udid": udid,
        "appium:bundleId": app["bundleId"],
        "appium:noReset": True,
        "appium:forceAppLaunch": True,
        "appium:newCommandTimeout": 900,
        "appium:wdaLaunchTimeout": 600000,
    }
    session = wt_driver.Session(args.server, capabilities)
    role = device["role"]
    try:
        try:
            ensure_logged_in(session, app, user, secret, role)
        except wt_driver.WebDriverError as error:
            report["errors"]["login"] = str(error)
            log("[{}] could not reach the dashboard: {}".format(role, error))
            return report
        for screen_id in args.screens:
            spec = screens[screen_id]["ios"]
            for attempt in (1, 2):
                try:
                    go_home(session, app)
                    run_steps(session, app, screens[screen_id])
                    report["screens"][screen_id] = capture_screen(session, app, udid, screen_id, spec,
                                                                  args.orientations, out_dir)
                    log("[{}] captured {}".format(role, screen_id))
                    break
                except wt_driver.WebDriverError as error:
                    reset_orientation(session)
                    if error.error != "navigation" or attempt == 2:
                        report["errors"][screen_id] = str(error)
                        log("[{}] could not capture {}: {}".format(role, screen_id, error))
                        break
                    log("[{}] stuck away from the dashboard; relaunching the app".format(role))
                    report.setdefault("relaunches", []).append(screen_id)
                    relaunch(session, app)
                    ensure_logged_in(session, app, user, secret, role)
    finally:
        session.quit()
    return report


def start_appium(appium_home):
    """Start Appium on a free localhost port with logging off; its log would contain the typed password."""
    binary = os.path.join(appium_home, "node_modules", ".bin", "appium")
    if not os.path.exists(binary):
        raise SystemExit("Appium is not installed in {}; run /winteam-device-testing:setup-devices".format(
            appium_home))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    process = subprocess.Popen([binary, "--address", "127.0.0.1", "--port", str(port), "--log-level", "error"],
                               env=dict(os.environ, APPIUM_HOME=appium_home), stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    server = "http://127.0.0.1:{}".format(port)
    deadline = time.time() + 60
    while not wt_driver.server_is_up(server):
        if process.poll() is not None or time.time() >= deadline:
            stop_appium(process)
            raise SystemExit("Appium did not start")
        time.sleep(0.5)
    return process, server


def stop_appium(process):
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", required=True, help="folder with app.json, devices.json, screens.json")
    parser.add_argument("--runs", required=True, help="the plugin's runs folder; a new run folder goes inside")
    parser.add_argument("--appium-home", required=True, help="the Appium install from setup-devices")
    parser.add_argument("--screens", required=True, help="comma-separated screen ids, or 'all'")
    parser.add_argument("--roles", default="phone,tablet", help="comma-separated device roles")
    parser.add_argument("--orientations", default="portrait,landscape")
    args = parser.parse_args()

    app = load_json(args.data, "app.json")
    devices = load_json(args.data, "devices.json")["ios"]
    screens = load_json(args.data, "screens.json")["screens"]
    args.screens = list(screens) if args.screens == "all" else args.screens.split(",")
    unknown = [s for s in args.screens if s not in screens or "ios" not in screens[s]]
    if unknown:
        raise SystemExit("Not in screens.json for iOS: {}".format(", ".join(unknown)))
    args.orientations = args.orientations.split(",")
    roles = args.roles.split(",")

    user, secret = credentials()
    os.makedirs(args.runs, exist_ok=True)
    expired = prune_runs.prune(args.runs, prune_runs.retention_days(args.data))
    if expired:
        log("deleted {} expired run(s)".format(expired))
    args.out = os.path.join(args.runs, time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(args.out)
    manifest = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "screens": args.screens,
                "orientations": args.orientations, "devices": {}}
    process, args.server = start_appium(args.appium_home)
    try:
        for device in devices:
            if device["role"] in roles:
                manifest["devices"][device["role"]] = capture_device(args, app, device, screens, user, secret)
    finally:
        stop_appium(process)
        with open(os.path.join(args.out, "manifest.json"), "w") as handle:
            json.dump(manifest, handle, indent=2)
    log("run folder: {}".format(args.out))


if __name__ == "__main__":
    main()
