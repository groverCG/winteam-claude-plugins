"""Minimal W3C WebDriver client for a local Appium server, standard library only.

Every pointer interaction is sent as a W3C pointer action at screen coordinates. On iOS, element clicks
are ignored on the B2C sign-in page and on the keyboard toolbar, while coordinate taps work everywhere.
"""

import json
import time
import urllib.error
import urllib.request

ELEMENT_KEY = "element-6066-11e4-a52e-4f735466cecf"


class WebDriverError(Exception):
    def __init__(self, error, message):
        super().__init__("{}: {}".format(error, message))
        self.error = error


def _request(method, url, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as http_error:
        try:
            value = json.loads(http_error.read()).get("value", {})
        except ValueError:
            value = {}
        raise WebDriverError(value.get("error", "http {}".format(http_error.code)), value.get("message", ""))
    return payload.get("value")


def server_is_up(server):
    try:
        _request("GET", server + "/status", timeout=3)
        return True
    except (OSError, WebDriverError):
        return False


class Session:
    def __init__(self, server, capabilities, timeout=900):
        self.server = server
        value = _request("POST", server + "/session", {"capabilities": {"alwaysMatch": capabilities}}, timeout)
        self.id = value["sessionId"]
        self.capabilities = value.get("capabilities", {})

    def _cmd(self, method, path, body=None, timeout=120):
        return _request(method, "{}/session/{}{}".format(self.server, self.id, path), body, timeout)

    def quit(self):
        try:
            self._cmd("DELETE", "")
        except (OSError, WebDriverError):
            pass

    def find(self, strategy, selector):
        try:
            value = self._cmd("POST", "/element", {"using": strategy, "value": selector})
        except WebDriverError as error:
            if error.error == "no such element":
                return None
            raise
        return value[ELEMENT_KEY]

    def wait_for(self, strategy, selector, timeout=20.0, interval=0.5):
        deadline = time.time() + timeout
        while True:
            element = self.find(strategy, selector)
            if element is not None:
                return element
            if time.time() >= deadline:
                raise WebDriverError("timeout", "{} '{}' not found after {}s".format(strategy, selector, timeout))
            time.sleep(interval)

    def wait_for_any(self, locators, timeout=20.0, interval=0.5):
        """Wait until one of several (strategy, selector) pairs matches; return (index, element)."""
        deadline = time.time() + timeout
        while True:
            for index, (strategy, selector) in enumerate(locators):
                element = self.find(strategy, selector)
                if element is not None:
                    return index, element
            if time.time() >= deadline:
                raise WebDriverError("timeout", "none of {} found after {}s".format(locators, timeout))
            time.sleep(interval)

    def rect(self, element):
        return self._cmd("GET", "/element/{}/rect".format(element))

    def attribute(self, element, name):
        return self._cmd("GET", "/element/{}/attribute/{}".format(element, name))

    def center(self, element):
        r = self.rect(element)
        return int(r["x"] + r["width"] / 2), int(r["y"] + r["height"] / 2)

    def _pointer(self, x, y, hold_ms):
        actions = [
            {"type": "pointerMove", "duration": 0, "x": x, "y": y},
            {"type": "pointerDown", "button": 0},
            {"type": "pause", "duration": hold_ms},
            {"type": "pointerUp", "button": 0},
        ]
        self._cmd("POST", "/actions", {"actions": [
            {"type": "pointer", "id": "finger", "parameters": {"pointerType": "touch"}, "actions": actions}]})
        self._cmd("DELETE", "/actions")

    def tap(self, x, y):
        self._pointer(x, y, 80)

    def long_press(self, x, y, hold_ms=1500):
        self._pointer(x, y, hold_ms)

    def tap_element(self, element):
        self.tap(*self.center(element))

    def type_text(self, text):
        """Type into whichever field has focus, one key at a time."""
        keys = []
        for char in text:
            keys.append({"type": "keyDown", "value": char})
            keys.append({"type": "keyUp", "value": char})
        self._cmd("POST", "/actions", {"actions": [{"type": "key", "id": "keyboard", "actions": keys}]})
        self._cmd("DELETE", "/actions")

    def set_value(self, element, text):
        """Send a value to an element; on a picker wheel this spins it to that row."""
        self._cmd("POST", "/element/{}/value".format(element), {"text": text, "value": list(text)})

    def execute(self, script, arguments=None):
        """Run an Appium extension command such as "mobile: terminateApp"."""
        return self._cmd("POST", "/execute/sync", {"script": script, "args": [arguments or {}]})

    def source(self):
        return self._cmd("GET", "/source")

    def window_size(self):
        return self._cmd("GET", "/window/rect")

    def set_orientation(self, orientation):
        self._cmd("POST", "/orientation", {"orientation": orientation})

    def alert_text(self):
        try:
            return self._cmd("GET", "/alert/text")
        except WebDriverError:
            return None

    def alert_buttons(self):
        return self.execute("mobile: alert", {"action": "getButtons"}) or []

    def press_alert_button(self, label):
        """Press one alert button by its label; WebDriver's own dismiss picks a button by itself."""
        self.execute("mobile: alert", {"action": "accept", "buttonLabel": label})
