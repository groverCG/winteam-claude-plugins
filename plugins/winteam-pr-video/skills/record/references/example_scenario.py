"""MO-8964: "Log in with PIN" stays on the login screen after a PIN lockout and "Return to login".

Runs unchanged on the before and after builds, on Android and iOS, from a fresh install. setup() isn't recorded;
run() is.
"""


def setup(s):
    # Testing environment, password login with PIN 1357, then log out.
    s.sign_in(pin="1357")
    s.log_out()


def run(s):
    keypad = s.pick(android=s.id("numericPadLayout"), ios=s.text("Enter your PIN"))
    log_in_with_pin = s.text("Log in with PIN")
    return_to_login = s.pick(android=s.id("pinLoginReturnToLogin"), ios=s.text("Return to login"))

    s.pause(1.5)
    s.tap(log_in_with_pin)              # 1. Log in with PIN: the keypad opens
    s.find(keypad, timeout=10)
    s.pause(1)
    for _ in range(5):                  # 2. A wrong PIN five times: locked out
        s.enter_pin("2468")
        s.pause(1.5)
    s.tap(return_to_login)              # 3. Return to login
    s.pause(1.5)

    # Expected: the PIN option is gone right away, without relaunching.
    s.check('"Log in with PIN" is hidden after returning from the lockout', lambda: s.gone(log_in_with_pin, 5))
    s.check('"Log In" is shown', lambda: s.exists(s.text("Log In"), 3))
    s.pause(2)
