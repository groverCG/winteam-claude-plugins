"""wt-pr-video subcommands written in Python: record, inspect, check, doctor, prune.

Runs on the macOS system Python 3.9, standard library only.
"""

import argparse
import importlib.util
import json
import os
import platform as host
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pr_video as pv  # noqa: E402

RUN_NAME = re.compile(r"^\d{8}-\d{6}-[A-Za-z0-9._-]+$")
RETENTION_DAYS = 7
PERMISSION_RULE = "Bash(wt-pr-video *)"
PUNCH_WORDS = ("clock in", "clock out", "break", "meal", "lunch", "punch")


def log(message):
    print(message, flush=True)


def tenant(app):
    return os.environ.get("WT_TEST_TENANT") or app.get("tenant")


# check

def data_changing_taps(scenario_path, app):
    """The blockedLabels/blockedIds of winteam-device-testing that the scenario names, plus Log out when it calls
    s.log_out(). A text match: it lists what to look at, it doesn't prove a tap happens."""
    with open(scenario_path) as handle:
        source = handle.read()
    found = [label for label in app["blockedLabels"]
             if re.search(r"""['"]{}['"]""".format(re.escape(label)), source, re.IGNORECASE)]
    found += [name for name in app["android"].get("blockedIds", []) if name in source]
    if "log_out(" in source and "Log out" not in found:
        found.append("Log out")
    return found


def report_taps(scenario_path, app):
    taps = data_changing_taps(scenario_path, app)
    if not taps:
        log("Data-changing taps: none")
        return
    log("Data-changing taps: " + ", ".join(taps))
    if any(word in tap.lower() for tap in taps for word in PUNCH_WORDS):
        log("WARNING: punch buttons create real time records on the shared Testing account")


def cmd_check(args):
    root, _ = pv.load_dependency()
    report_taps(args.scenario, pv.app_settings(root))


# record

def load_scenario(path):
    spec = importlib.util.spec_from_file_location("scenario", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "run", None)):
        raise SystemExit("{} has no run(s) function".format(path))
    return getattr(module, "setup", None), module.run


def cmd_record(args):
    root, data = pv.load_dependency()
    import run_capture
    import wt_driver
    app = pv.app_settings(root)
    report_taps(args.scenario, app)
    setup, scenario = load_scenario(args.scenario)
    out = os.path.abspath(args.out)
    run_dir = os.path.dirname(out)
    os.makedirs(run_dir, exist_ok=True)
    platform = pv.prepare_device(root, args.platform, args.app, args.avd, args.simulator)
    appium_log = os.path.join(run_dir, "appium-{}-{}.log".format(args.platform, args.mode))
    process, server = pv.start_appium(data, appium_log)
    code, session, steps, recording = 0, None, None, False
    try:
        session = pv.open_session(server, platform)
        steps = pv.Steps(session, platform, tenant(app), run_capture.credentials, args.mode)
        if setup:
            setup(steps)  # not recorded
            steps.discard_recording = False
        pv.start_recording(session, platform.name == "android")
        recording = True
        scenario(steps)
        steps.pause(2)  # hold the final screen
    except pv.Failed:
        code = 2
    except (Exception, SystemExit) as error:  # noqa: BLE001 - report every scenario error the same way
        code = 1
        log("error: {}: {}".format(type(error).__name__, error))
    finally:
        if recording:
            try:
                pv.stop_recording(session, out)
            except (wt_driver.WebDriverError, OSError) as error:
                log("could not save the recording: {}".format(error))
        if session is not None:
            session.quit()
        pv.stop_appium(process)
        pv.finish_device(platform)
    if steps is not None and steps.discard_recording and os.path.exists(out):
        os.remove(out)
        log("deleted the recording: the sign-in form wasn't filled right, so a frame could show the password")
    with open(re.sub(r"\.mp4$", "", out) + ".json", "w") as handle:
        json.dump({"mode": args.mode, "platform": args.platform, "exit": code,
                   "results": steps.results if steps else []}, handle, indent=2)
    if os.path.exists(out):
        log(out)
    return code


# inspect

def compact(source, platform_name):
    """One line per element worth a locator: Android nodes with an id, text or content-desc; iOS visible elements
    with a name or label. Field values are left out."""
    lines = []
    for node in ET.fromstring(source.encode()).iter():
        if platform_name == "android":
            rid = (node.get("resource-id") or "").split(":id/")[-1]
            text, desc = node.get("text") or "", node.get("content-desc") or ""
            if not (rid or text or desc) or node.get("displayed") == "false":
                continue
            parts = [(node.get("class") or node.tag).split(".")[-1]]
            parts += ["id=" + rid] if rid else []
            parts += ["text=" + json.dumps(text)] if text else []
            parts += ["desc=" + json.dumps(desc)] if desc else []
            parts += ["clickable"] if node.get("clickable") == "true" else []
            parts.append(node.get("bounds") or "")
        else:
            name, label = node.get("name") or "", node.get("label") or ""
            if node.get("visible") != "true" or not (name or label):
                continue
            parts = [node.tag.replace("XCUIElementType", "")]
            parts += ["name=" + json.dumps(name)] if name else []
            parts += ["label=" + json.dumps(label)] if label and label != name else []
            parts.append("[{},{} {}x{}]".format(node.get("x"), node.get("y"), node.get("width"), node.get("height")))
        line = " ".join(parts)
        if not lines or lines[-1] != line:
            lines.append(line)
    return "\n".join(lines)


def cmd_inspect(args):
    root, data = pv.load_dependency()
    import run_capture
    import wt_driver
    app = pv.app_settings(root)
    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    platform = pv.prepare_device(root, args.platform, args.app, args.avd, args.simulator)
    process, server = pv.start_appium(data, os.path.join(os.path.dirname(out), "appium-inspect.log"))
    code = 0
    try:
        session = pv.open_session(server, platform, launch=bool(args.app))
        try:
            steps = pv.Steps(session, platform, tenant(app), run_capture.credentials, "inspect")
            if args.do:
                try:
                    exec(args.do, {"s": steps})  # noqa: S102 - code Claude writes to explore, like a scenario
                except (Exception, SystemExit) as error:  # noqa: BLE001
                    code = 1
                    log("action failed: {}: {}".format(type(error).__name__, error))
            time.sleep(1)
            if run_capture.on_sign_in_page(session, steps.ctx):
                log("The sign-in page is showing: nothing saved, since it can hold the typed password.")
                return code
            platform.screenshot(out + ".png")
            listing = compact(session.source(), platform.name)
            with open(out + ".txt", "w") as handle:
                handle.write(listing + "\n")
            log(listing)
            log("screenshot: {}.png".format(out))
        finally:
            session.quit()
    finally:
        pv.stop_appium(process)
        pv.finish_device(platform)
    return code


# prune

def prune(runs_dir, days):
    """Delete run folders (yyyymmdd-hhmmss-TICKET) older than `days`, or all with days=None. Returns the count."""
    runs_dir = os.path.realpath(runs_dir)
    if os.path.basename(runs_dir) != "runs" or not os.path.isdir(runs_dir):
        return 0
    cutoff = None if days is None else time.time() - days * 86400
    deleted = 0
    for name in os.listdir(runs_dir):
        path = os.path.join(runs_dir, name)
        if not RUN_NAME.match(name) or os.path.islink(path) or not os.path.isdir(path):
            continue
        if cutoff is not None and os.path.getmtime(path) >= cutoff:
            continue
        shutil.rmtree(path, ignore_errors=True)
        deleted += 1
    return deleted


def cmd_prune(args):
    try:
        deleted = prune(args.runs, None if args.all else args.days)
    except OSError:
        deleted = 0
    if deleted or not args.quiet:
        log("winteam-pr-video: deleted {} run(s)".format(deleted))
    return 0


# doctor

class Doctor:
    def __init__(self):
        self.problems = 0

    def ok(self, message):
        log("✓ " + message)

    def bad(self, message, fix):
        self.problems += 1
        log("✗ {}\n    fix: {}".format(message, fix))

    def note(self, message):
        log("• " + message)

    def run(self, command, **kwargs):
        env = dict(os.environ, PATH=":".join(pv.BREW_PATHS + [os.environ.get("PATH", "")]))
        try:
            return subprocess.run(command, capture_output=True, text=True, env=env, timeout=120, **kwargs)
        except (OSError, subprocess.SubprocessError):
            return None


def which(name):
    return shutil.which(name, path=":".join(pv.BREW_PATHS + [os.environ.get("PATH", "")]))


def settings_path():
    return os.path.expanduser("~/.claude/settings.json")


def has_permission_rule():
    try:
        settings = pv.load_json(settings_path())
    except (OSError, ValueError):
        return False
    return PERMISSION_RULE in settings.get("permissions", {}).get("allow", [])


def add_permission_rule():
    path = settings_path()
    settings = pv.load_json(path) if os.path.exists(path) else {}
    if os.path.exists(path):
        shutil.copy(path, path + ".bak-wt-pr-video")
    settings.setdefault("permissions", {}).setdefault("allow", []).append(PERMISSION_RULE)
    with open(path, "w") as handle:
        json.dump(settings, handle, indent=2)
        handle.write("\n")


def cmd_doctor(args):
    d = Doctor()
    if sys.platform == "darwin" and host.machine() == "arm64":
        d.ok("macOS on Apple Silicon")
    else:
        d.bad("not macOS on Apple Silicon", "winteam-pr-video only runs on Apple Silicon Macs")

    dependency = None
    try:
        root, data, version = pv.find_dependency()
        if pv.version_tuple(version) < pv.MIN_DEPENDENCY_VERSION:
            d.bad("{} {} is too old".format(pv.DEPENDENCY, version),
                  "claude plugin update {}@winteam -s local".format(pv.DEPENDENCY))
        else:
            d.ok("{} {}".format(pv.DEPENDENCY, version))
            dependency = (root, data)
    except (SystemExit, OSError, ValueError) as error:
        d.bad(str(error), "claude plugin install {}@winteam -s local".format(pv.DEPENDENCY))

    if dependency:
        sys.path.insert(0, os.path.join(dependency[0], "scripts"))
        try:
            binary, _ = pv.appium_install(dependency[1])
            d.ok("Appium: {}".format(binary))
        except SystemExit as error:
            d.bad(str(error), "/winteam-device-testing:setup-devices")
        result = d.run(["security", "find-generic-password", "-s", "winteam-device-testing"])
        if (result and result.returncode == 0) or os.environ.get("WT_TEST_USER"):
            d.ok("Testing account (Keychain item winteam-device-testing, or WT_TEST_USER)")
        else:
            d.bad("no Testing account", "security add-generic-password -U -s winteam-device-testing "
                  "-a <test account email> -w   (prompts for the password)")
        if not tenant(pv.app_settings(dependency[0])):
            d.note("WT_TEST_TENANT is not set: needed only when the account shows 'Choose an account'")

    tools = {"ffmpeg": "brew install ffmpeg", "ffprobe": "brew install ffmpeg", "gh": "brew install gh",
             "git": "xcode-select --install", "dotnet": "install the .NET 10 SDK from https://dotnet.microsoft.com",
             "xcrun": "install Xcode", "osascript": "comes with macOS"}
    for name, fix in tools.items():
        if which(name):
            d.ok(name)
        else:
            d.bad("{} not found".format(name), fix)
    if which("gh"):
        result = d.run(["gh", "auth", "status"])
        if result and result.returncode == 0:
            d.ok("gh is signed in")
        else:
            d.bad("gh is not signed in", "gh auth login")
    if which("dotnet"):
        result = d.run(["dotnet", "workload", "list"])
        listed = result.stdout if result else ""
        for workload in ("android", "ios"):
            if re.search(r"^{}\s".format(workload), listed, re.MULTILINE):
                d.ok("dotnet workload " + workload)
            else:
                d.bad("dotnet workload {} missing".format(workload), "sudo dotnet workload install " + workload)

    if dependency:
        import android_devices
        import platforms
        try:
            avd = pv.phone(dependency[0], "android", avd=args.avd)["avd"]
            if avd in android_devices.list_avds():
                d.ok("Android emulator " + avd)
            else:
                d.bad("AVD '{}' not found".format(avd), "create it in Android Studio > Device Manager, or set the "
                      "plugin option android_avd")
        except SystemExit as error:
            d.bad(str(error), "install the Android SDK with Android Studio")
        sim = pv.phone(dependency[0], "ios", simulator=args.simulator)
        try:
            platforms.resolve_udid(sim)
            d.ok("iOS simulator {} ({})".format(sim["name"], sim["runtime"]))
        except SystemExit:
            d.bad("simulator '{}' ({}) not found".format(sim["name"], sim["runtime"]),
                  "Xcode > Window > Devices and Simulators, or set the plugin option ios_simulator")

    if has_permission_rule():
        d.ok("permission rule {}".format(PERMISSION_RULE))
    elif args.add_permission:
        add_permission_rule()
        d.ok("added {} to {} (backup: settings.json.bak-wt-pr-video)".format(PERMISSION_RULE, settings_path()))
    else:
        d.note("{} is not in {}: Claude will ask before each wt-pr-video step after you approve the scenario. "
               "Add it with: doctor --add-permission".format(PERMISSION_RULE, settings_path()))
    d.note("The Jira ticket is read through the claude.ai Atlassian connector when it's connected; otherwise you "
           "paste the repro steps.")
    log("{} problem(s)".format(d.problems) if d.problems else "Ready.")
    return 1 if d.problems else 0


def main():
    parser = argparse.ArgumentParser(prog="wt-pr-video")
    sub = parser.add_subparsers(dest="command", required=True)

    def device_options(p):
        p.add_argument("--avd", default="", help="Android AVD (default: the dependency's phone AVD)")
        p.add_argument("--simulator", default="", help="iOS simulator name (default: the dependency's phone)")

    p = sub.add_parser("record", help="clean-install the app and record the scenario")
    p.add_argument("platform", choices=["android", "ios"])
    p.add_argument("app", help="the .apk or .app to clean-install")
    p.add_argument("scenario")
    p.add_argument("mode", choices=["before", "after"])
    p.add_argument("out", help="the .mp4 to write; results go next to it as .json")
    device_options(p)
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("inspect", help="list the visible elements and save a screenshot")
    p.add_argument("platform", choices=["android", "ios"])
    p.add_argument("out", help="path prefix for <out>.txt and <out>.png")
    p.add_argument("--app", help="clean-install this .apk/.app and launch it first")
    p.add_argument("--do", help="Python to run first, with the scenario helpers as s")
    device_options(p)
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("check", help="list the data-changing buttons a scenario names")
    p.add_argument("scenario")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("prune", help="delete expired runs")
    p.add_argument("--runs", required=True)
    p.add_argument("--days", type=float, default=RETENTION_DAYS)
    p.add_argument("--all", action="store_true")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_prune)

    p = sub.add_parser("doctor", help="check this machine")
    p.add_argument("--add-permission", action="store_true", help="add {} to ~/.claude/settings.json".format(
        PERMISSION_RULE))
    device_options(p)
    p.set_defaults(func=cmd_doctor)

    args = parser.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
