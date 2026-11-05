"""Capture WinTeam screens on the phone and tablet simulators (iOS), or emulators or physical devices (Android).

Starts its own Appium server with logging off, since Appium logs every typed string, the password
included. Prunes expired runs, then for each device: boot it, freeze the status bar, start a session,
switch to the Testing environment, log in, visit each requested screen from screens.json and save a
screenshot and the page source in every requested orientation. Writes manifest.json into a new run folder.

One flow serves both platforms; platforms.py holds what differs (locators, alerts, the environment picker,
screenshots, rotation, device boot). On Android, a role uses a plugged-in physical device whose size bucket fits it,
mirrored in a read-only scrcpy window, and otherwise its emulator, booted with a window. The script installs --apk,
clears logcat after the login and at the end, shuts down the emulators it booted, and puts a physical device's
settings back.

Navigation is read-only: every tap after login goes through guarded_tap, which refuses blockedLabels (and on
Android blockedIds, also when they belong to an ancestor) and, on screens of a protected domain, anything
outside that domain's allowedTaps. The timeclock domain covers only the Time clock page; Punch log and
Timekeeping are checked against blockedLabels alone.

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
import platforms  # noqa: E402
import prune_runs  # noqa: E402
import wt_driver  # noqa: E402

KEYCHAIN_SERVICE = "winteam-device-testing"
label_text = platforms.label_text


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


def is_blocked(app, label):
    label = label_text(label)
    return bool(label) and any(label == label_text(b) or label.startswith(label_text(b) + " ")
                               for b in app["blockedLabels"])


def guarded_tap(session, ctx, element, allowed=None):
    """The single tap point after login: refuse blocked labels and ids, and anything outside `allowed`."""
    app, platform = ctx["app"], ctx["platform"]
    label, every_label = platform.labels(session, element)
    blocked = next((text for text in every_label if is_blocked(app, text)), None)
    if blocked is not None:
        raise wt_driver.WebDriverError("blocked", "refused to tap '{}': it is on blockedLabels".format(blocked))
    blocked_id = platform.blocked_id(session, element)
    if blocked_id:
        raise wt_driver.WebDriverError("blocked", "refused to tap '{}': {} is on blockedIds".format(
            label, blocked_id))
    if allowed is not None and label_text(label) not in {label_text(a) for a in allowed}:
        raise wt_driver.WebDriverError("blocked", "refused to tap '{}': not an allowed tap here".format(label))
    session.tap_element(element)


def handle_alert(session, ctx):
    """Press a known-safe button by name; accept only a lone informational button. Refuse anything else.

    An alert can close by itself between reading it and pressing a button; that counts as handled.
    """
    app, platform = ctx["app"], ctx["platform"]
    try:
        buttons = platform.alert_buttons(session)
    except wt_driver.WebDriverError as error:
        if error.error in platforms.GONE_ERRORS:
            return
        raise
    if not buttons:
        return
    accept = {label_text(label) for label in app["alertAcceptLabels"]}
    dismiss = {label_text(label) for label in app["alertDismissLabels"]}
    if len(buttons) == 1 and label_text(buttons[0]) in accept:
        choice = buttons[0]
    else:
        choice = next((b for b in buttons if label_text(b) in dismiss), None)
    if choice is None or is_blocked(app, choice):
        raise wt_driver.WebDriverError("blocked", "alert with buttons {} has no safe choice".format(buttons))
    try:
        platform.press_alert_button(session, choice)
    except wt_driver.WebDriverError as error:
        if error.error not in platforms.GONE_ERRORS:
            raise


def alert_showing(session, platform):
    try:
        return bool(platform.alert_buttons(session))
    except wt_driver.WebDriverError as error:
        if error.error in platforms.GONE_ERRORS:
            return False
        raise


def dismiss_prompts(session, ctx):
    """Close alerts and the app's own opt-in screens, if any are showing."""
    app, platform = ctx["app"], ctx["platform"]
    for _ in range(4):
        if alert_showing(session, platform):
            handle_alert(session, ctx)
            time.sleep(1)
            continue
        for label in app["dismissLabels"]:
            button = platform.find_visible(session, platform.button_with_label(label))
            if button is not None:
                guarded_tap(session, ctx, button, allowed=app["dismissLabels"])
                time.sleep(1.5)
                break
        else:
            return


def field_value(session, ctx, spec):
    element = ctx["platform"].find(session, spec)
    return ctx["platform"].field_text(session, element) if element else None


def clear_focused_field(session, ctx, element):
    """Delete whatever the focused field holds, with Delete key presses from its end."""
    value = ctx["platform"].field_text(session, element)
    if value:
        session.type_text(ctx["platform"].backspace * (len(value) + 2))
        time.sleep(0.5)


def usable_band(session):
    """The (top, bottom) screen band where a tap reaches the page: above the keyboard when it is up."""
    height = session.window_size()["height"]
    if session.keyboard_shown():
        return height * 0.08, height * 0.55
    return height * 0.08, height * 0.85


def in_band(rect, band):
    return rect["height"] > 0 and rect["y"] >= band[0] and rect["y"] + rect["height"] <= band[1]


def scroll_into_view(session, ctx, element, name, attempts=4):
    """Scroll the page until the element sits fully inside the usable band.

    On a phone the B2C page can leave a field below the fold or under the keyboard. The driver's own element
    scroll is tried first (iOS); a swipe inside the band, toward the element, is the fallback.
    """
    width = session.window_size()["width"]
    for attempt in range(attempts):
        band = usable_band(session)
        r = session.rect(element)
        if in_band(r, band):
            return
        if attempt == 0:
            try:
                ctx["platform"].try_native_scroll(session, element)
                time.sleep(0.8)
                continue
            except wt_driver.WebDriverError:
                pass
        x = int(width / 2)
        top, bottom = int(band[0] + (band[1] - band[0]) * 0.25), int(band[0] + (band[1] - band[0]) * 0.75)
        if r["y"] + r["height"] > band[1]:
            session.swipe(x, bottom, x, top)
        else:
            session.swipe(x, top, x, bottom)
        time.sleep(0.8)
    if not in_band(session.rect(element), usable_band(session)):
        raise SystemExit("Could not scroll the {} into view; stopping before typing".format(name))


def focus_field(session, ctx, element, name):
    """Scroll the field into view and tap near its right edge, so the cursor lands at the end.

    Keyboard detection is not a signal here: on iOS it never sees the keyboard on the B2C page. The caller
    confirms focus by what lands in the field.
    """
    scroll_into_view(session, ctx, element, name)
    r = session.rect(element)
    session.tap(int(r["x"] + r["width"] - 4), int(r["y"] + r["height"] / 2))
    time.sleep(1)


def type_email(session, ctx, user, attempts=3):
    """Focus the email field, clear it and type the email, until the field holds exactly the email."""
    b2c, platform = ctx["app"]["b2c"], ctx["platform"]
    for _ in range(attempts):
        email = platform.wait_for(session, b2c["emailField"], timeout=10)
        focus_field(session, ctx, email, "email field")
        clear_focused_field(session, ctx, email)
        session.type_text(user)
        time.sleep(0.5)
        if field_value(session, ctx, b2c["emailField"]) == user:
            return
    raise SystemExit("The email did not land in the email field (focus problem); stopping before the password")


def log_in(session, ctx, user, secret):
    """Fill the B2C form through the keyboard only: Tab between fields, Enter to submit.

    Login routine, exempt from guarded_tap: it taps only Log In and the email field, and may scroll the
    sign-in page to bring the email field into view. The page keeps earlier input across app launches, and
    the keyboard toolbar covers the password field on an iPhone, so fields are cleared before typing and the
    password field is never tapped.
    """
    app, platform = ctx["app"], ctx["platform"]
    session.tap_element(platform.wait_for(session, app["loginButton"], timeout=30))
    platform.wait_for(session, app["b2c"]["emailField"], timeout=45)
    time.sleep(1.5)
    type_email(session, ctx, user)
    session.type_text("\t")
    time.sleep(1)
    password = platform.wait_for(session, app["b2c"]["passwordField"])
    clear_focused_field(session, ctx, password)
    session.type_text(secret)
    time.sleep(0.5)
    typed_email = field_value(session, ctx, app["b2c"]["emailField"])
    typed_secret = field_value(session, ctx, app["b2c"]["passwordField"]) or ""
    if typed_email != user or len(typed_secret) != len(secret):
        raise SystemExit("Sign-in form was not filled correctly (focus problem); stopping without submitting")
    session.type_text(platform.enter)
    platform.after_login()


def anchor_present(session, ctx, anchor):
    """An anchor is a locator, or {"all": [...], "any": [...]}; every "all" and one "any" must be visible."""
    find = ctx["platform"].find_visible
    if not (isinstance(anchor, dict) and ("all" in anchor or "any" in anchor)):
        anchor = {"all": [anchor]}
    if any(find(session, spec) is None for spec in anchor.get("all", [])):
        return False
    return not anchor.get("any") or any(find(session, spec) is not None for spec in anchor["any"])


def wait_for_anchor(session, ctx, anchor, timeout):
    """Prompts can appear late, after the step that opened the screen, so keep closing them while waiting."""
    deadline = time.time() + timeout
    while not anchor_present(session, ctx, anchor):
        if time.time() >= deadline:
            raise wt_driver.WebDriverError("timeout", "anchor {} not visible after {}s".format(
                json.dumps(anchor), timeout))
        dismiss_prompts(session, ctx)
        time.sleep(0.5)


def go_home(session, ctx):
    """Back out to the dashboard: pushed screens hide the tab bar, so try the back button first."""
    app, platform = ctx["app"], ctx["platform"]
    for _ in range(12):
        dismiss_prompts(session, ctx)
        if anchor_present(session, ctx, app["homeAnchor"]):
            return
        back = platform.find_visible(session, app["backButton"])
        target = back if back is not None else platform.find_visible(session, app["homeTab"])
        if target is not None:
            guarded_tap(session, ctx, target)
        elif platform.name == "android":
            session.back()
        time.sleep(2.0)
    raise wt_driver.WebDriverError("navigation", "could not get back to the dashboard")


def resolve_tenant(args, app):
    return args.tenant or os.environ.get("WT_TEST_TENANT") or app.get("tenant")


def choose_account(session, ctx):
    """On "Choose an account", tap the configured tenant's row. Login routine, exempt from guarded_tap.

    Only while the picker itself shows: the dashboard header shows the same tenant name and opens "Switch
    account", so nothing is tapped once the Home menu button is visible. Returns True if it tapped.
    """
    app, platform = ctx["app"], ctx["platform"]
    picker = app["accountPicker"]
    if platform.find_visible(session, picker["title"]) is None:
        return False
    if any(platform.find_visible(session, spec) is not None for spec in app["homeAnchor"].get("all", [])):
        return False
    tenant = ctx["tenant"]
    if not tenant:
        raise SystemExit("This account belongs to several tenants: set --tenant or WT_TEST_TENANT")
    row = platform.find_visible(session, platform.with_tenant(picker["row"], tenant))
    if row is None:
        raise SystemExit("The account picker has no row for the configured tenant; check --tenant or "
                         "WT_TEST_TENANT")
    session.tap_element(row)
    time.sleep(2)
    return True


def ensure_logged_in(session, ctx, user, secret, role):
    """From a fresh launch, reach the dashboard: log in if the login screen shows."""
    app, platform = ctx["app"], ctx["platform"]
    deadline = time.time() + 60
    while platform.find(session, app["loginButton"]) is None and not anchor_present(session, ctx,
                                                                                    app["homeAnchor"]):
        dismiss_prompts(session, ctx)
        choose_account(session, ctx)
        if time.time() >= deadline:
            raise wt_driver.WebDriverError("timeout", "neither the login screen nor the dashboard appeared")
        time.sleep(1)
    if platform.find(session, app["loginButton"]) is None:
        return
    log("[{}] switching to {} and logging in".format(role, app["environment"]))
    platform.select_environment(session, app["environment"])
    log_in(session, ctx, user, secret)
    deadline = time.time() + 120
    while not anchor_present(session, ctx, app["homeAnchor"]):
        if not choose_account(session, ctx):
            dismiss_prompts(session, ctx)
        if time.time() >= deadline:
            raise wt_driver.WebDriverError("timeout", "the dashboard did not appear after signing in")
        time.sleep(1)


def wait_until_loaded(session, ctx, anchor, timeout=30.0):
    """Wait for the screen's anchor, then for any loading indicator to clear."""
    wait_for_anchor(session, ctx, anchor, timeout)
    wait_while_loading(session, ctx, timeout)


def wait_while_loading(session, ctx, timeout=60.0):
    """A tap made while a screen is still loading can be undone when it finishes, e.g. the Time tab's pager."""
    deadline = time.time() + timeout
    while ctx["platform"].loading_visible(session) and time.time() < deadline:
        time.sleep(0.5)


def fully_inside(inner, outer):
    return (inner["width"] > 0 and inner["height"] > 0 and inner["x"] >= outer["x"] - 1 and
            inner["y"] >= outer["y"] - 1 and inner["x"] + inner["width"] <= outer["x"] + outer["width"] + 1 and
            inner["y"] + inner["height"] <= outer["y"] + outer["height"] + 1)


def scroll_to(session, ctx, step):
    """Swipe inside `within` (or the screen's middle band) until `target` is fully visible. Never taps.

    Only leftward and upward swipes, which reveal content further along and can't trigger pull-to-refresh.
    A list recycles its views while it scrolls, so a stale element just means looking again.
    """
    deadline = time.time() + step.get("timeout", 20)
    swipes = 0
    while swipes <= step.get("maxSwipes", 6) and time.time() < deadline:
        dismiss_prompts(session, ctx)
        try:
            area = scroll_area(session, ctx, step)
            if area is None:
                time.sleep(0.5)
                continue
            target = ctx["platform"].find_visible(session, step["target"])
            if target is not None and fully_inside(session.rect(target), area):
                return
        except wt_driver.WebDriverError as error:
            if error.error not in platforms.GONE_ERRORS:
                raise
            time.sleep(0.5)
            continue
        swipe_across(session, area, step.get("direction", "vertical"))
        swipes += 1
        time.sleep(0.8)
    raise wt_driver.WebDriverError("timeout", "{} not reached by scrolling".format(json.dumps(step["target"])))


def scroll_area(session, ctx, step):
    """The rect to swipe in: the `within` element, None while it isn't showing, or the screen's middle band."""
    if step.get("within"):
        container = ctx["platform"].find_visible(session, step["within"])
        return session.rect(container) if container is not None else None
    size = session.window_size()
    return {"x": 0, "y": size["height"] * 0.2, "width": size["width"], "height": size["height"] * 0.6}


def swipe_across(session, area, direction):
    middle_x, middle_y = int(area["x"] + area["width"] / 2), int(area["y"] + area["height"] / 2)
    if direction == "horizontal":
        session.swipe(int(area["x"] + area["width"] * 0.8), middle_y, int(area["x"] + area["width"] * 0.2), middle_y)
    else:
        session.swipe(middle_x, int(area["y"] + area["height"] * 0.8), middle_x, int(area["y"] + area["height"] * 0.2))


def wait_for_step(session, ctx, spec, timeout):
    """Wait for a step's element, closing prompts that open late (the tenant's test message, for one)."""
    deadline = time.time() + timeout
    while True:
        element = ctx["platform"].find(session, spec)
        if element is not None:
            return element
        if time.time() >= deadline:
            raise wt_driver.WebDriverError("timeout", "{} not found after {}s".format(json.dumps(spec), timeout))
        dismiss_prompts(session, ctx)
        time.sleep(0.5)


def tap_step(session, ctx, spec, allowed, timeout):
    """Find the step's element and tap it through guarded_tap.

    An alert opening over the page makes UiAutomator2 drop its cached elements. Then the guard can't finish
    and nothing is tapped. Close the prompt, find the element again and re-run the whole guard.
    """
    deadline = time.time() + timeout
    while True:
        element = wait_for_step(session, ctx, spec, max(1.0, deadline - time.time()))
        try:
            guarded_tap(session, ctx, element, allowed)
            return
        except wt_driver.WebDriverError as error:
            if error.error not in platforms.GONE_ERRORS or time.time() >= deadline:
                raise
        dismiss_prompts(session, ctx)
        time.sleep(0.5)


def expected_shows(session, ctx, spec, timeout=6.0):
    """A tap step's optional "expect": a pager that finishes loading can undo a tap made during the load."""
    deadline = time.time() + timeout
    while ctx["platform"].find_visible(session, spec) is None:
        if time.time() >= deadline:
            return False
        dismiss_prompts(session, ctx)
        time.sleep(0.5)
    return True


def run_steps(session, ctx, screen):
    """Navigation steps; a screen in a protected domain may only tap that domain's allowedTaps.

    tap       {"action": "tap", "predicate" (iOS) | "locator" (Android), "settle"?, "timeout"?, "expect"?}
              With "expect", the tap is repeated once if that locator doesn't show afterwards.
    scroll_to {"action": "scroll_to", "target", "direction": "horizontal"|"vertical", "within"?, "maxSwipes"?}
    """
    app, platform = ctx["app"], ctx["platform"]
    domain = app["protectedDomains"].get(screen.get("domain", ""))
    allowed = domain["allowedTaps"] if domain else None
    for step in screen[platform.name]["steps"]:
        wait_while_loading(session, ctx)
        if step["action"] == "scroll_to":
            scroll_to(session, ctx, step)
            continue
        spec = step["predicate"] if platform.name == "ios" else step["locator"]
        if step["action"] != "tap":
            raise ValueError("unknown step action '{}'".format(step["action"]))
        for attempt in (1, 2):
            tap_step(session, ctx, spec, allowed, step.get("timeout", 20))
            time.sleep(step.get("settle", 2.0))
            dismiss_prompts(session, ctx)
            if not step.get("expect") or expected_shows(session, ctx, step["expect"]):
                break
            if attempt == 2:
                raise wt_driver.WebDriverError("timeout", "{} did not show after tapping {}".format(
                    json.dumps(step["expect"]), json.dumps(spec)))


def reset_orientation(session, ctx):
    try:
        ctx["platform"].set_orientation(session, "portrait")
    except wt_driver.WebDriverError:
        pass


def capture_screen(session, ctx, screen_id, spec, orientations, out_dir):
    """The anchor is checked once, in portrait: rotating can scroll it out of view, which is a finding."""
    platform = ctx["platform"]
    results = {}
    reset_orientation(session, ctx)
    wait_until_loaded(session, ctx, spec["anchor"])
    for name in orientations:
        platform.set_orientation(session, name)
        time.sleep(2.0)
        dismiss_prompts(session, ctx)
        wait_until_loaded(session, ctx, {"all": []})
        base = os.path.join(out_dir, "{}-{}".format(screen_id, name))
        platform.screenshot(base + ".png")
        with open(base + ".xml", "w") as handle:
            handle.write(session.source())
        results[name] = {"png": base + ".png", "xml": base + ".xml"}
    platform.set_orientation(session, "portrait")
    time.sleep(1.0)
    return results


def capture_device(args, app, device, screens, user, secret):
    platform = platforms.make(args.platform, app, device, args)
    ctx = {"app": platform.app, "platform": platform, "tenant": resolve_tenant(args, platform.app)}
    role = device["role"]
    out_dir = os.path.join(args.out, role)
    os.makedirs(out_dir, exist_ok=True)
    report = {"platform": platform.name, "screens": {}, "errors": {}}
    try:
        log("[{}] preparing {}".format(role, device.get("name") or device.get("avd")))
        try:
            report.update(platform.prepare())
        except platforms.DeviceError as error:
            report["errors"]["device"] = str(error)
            log("[{}] {}".format(role, error))
            return report
        report["density"] = platform.density
        log("[{}] using {}".format(role, platform.describe()))
        session = wt_driver.Session(args.server, platform.capabilities())
        try:
            capture_screens(args, ctx, session, screens, user, secret, out_dir, report)
        finally:
            session.quit()
    finally:
        platform.cleanup()
    return report


def capture_screens(args, ctx, session, screens, user, secret, out_dir, report):
    role, platform = os.path.basename(out_dir), ctx["platform"]
    try:
        ensure_logged_in(session, ctx, user, secret, role)
    except wt_driver.WebDriverError as error:
        report["errors"]["login"] = str(error)
        log("[{}] could not reach the dashboard: {}".format(role, error))
        return
    for screen_id in args.screens:
        spec = screens[screen_id][platform.name]
        for attempt in (1, 2):
            try:
                go_home(session, ctx)
                run_steps(session, ctx, screens[screen_id])
                report["screens"][screen_id] = capture_screen(session, ctx, screen_id, spec, args.orientations,
                                                              out_dir)
                log("[{}] captured {}".format(role, screen_id))
                break
            except wt_driver.WebDriverError as error:
                reset_orientation(session, ctx)
                retryable = error.error == "navigation" or error.error in platforms.GONE_ERRORS
                if not retryable or attempt == 2:
                    report["errors"][screen_id] = str(error)
                    log("[{}] could not capture {}: {}".format(role, screen_id, error))
                    break
                if error.error != "navigation":
                    log("[{}] {} changed under a tap; trying {} again".format(role, screen_id, screen_id))
                    continue
                log("[{}] stuck away from the dashboard; relaunching the app".format(role))
                report.setdefault("relaunches", []).append(screen_id)
                platform.relaunch(session)
                ensure_logged_in(session, ctx, user, secret, role)


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
    parser.add_argument("--platform", choices=["ios", "android"], default="ios")
    parser.add_argument("--apk", help="Android: install this APK on each device before capturing")
    parser.add_argument("--tenant", help="tenant to pick on 'Choose an account' (or WT_TEST_TENANT)")
    parser.add_argument("--roles", default="phone,tablet", help="comma-separated device roles")
    parser.add_argument("--orientations", default="portrait,landscape")
    args = parser.parse_args()
    if args.apk and args.platform != "android":
        parser.error("--apk is for --platform android")

    app = load_json(args.data, "app.json")
    devices = load_json(args.data, "devices.json")[args.platform]
    screens = load_json(args.data, "screens.json")["screens"]
    mapped = [s for s in screens if args.platform in screens[s]]
    args.screens = mapped if args.screens == "all" else args.screens.split(",")
    unknown = [s for s in args.screens if s not in mapped]
    if unknown:
        raise SystemExit("Not in screens.json for {}: {}".format(args.platform, ", ".join(unknown)))
    args.orientations = args.orientations.split(",")
    roles = args.roles.split(",")

    user, secret = credentials()
    os.makedirs(args.runs, exist_ok=True)
    expired = prune_runs.prune(args.runs, prune_runs.retention_days(args.data))
    if expired:
        log("deleted {} expired run(s)".format(expired))
    args.out = os.path.join(args.runs, time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(args.out)
    manifest = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "platform": args.platform,
                "screens": args.screens, "orientations": args.orientations, "devices": {}}
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
