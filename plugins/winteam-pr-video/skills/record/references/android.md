# Android UI facts

Find views by resource id (`s.id`). Confirm anything not listed here with `wt-pr-video … inspect`.

- A fresh install starts in Production: `s.select_environment()` (or `s.sign_in()`) comes first.
- Login screen: "Log In" and "Log in with PIN" are the same view, `{"id": "loadingButton", "in": {"id":
  "loginButtonLayout"}}`; `s.text("Log in with PIN")` tells them apart.
- After the first password login: "Set up a PIN instead?" (Set up PIN = `main_action_button`, No thanks =
  `secondary_action_button`); the PIN is typed twice. Then "Choose an account" for accounts with several tenants.
  Then "Enable notifications" (Not right now = `secondary_action_button`), which can take more than 30 s after the
  tenant pick. Then Home. `s.sign_in()` handles all of these.
- Home: the side menu is the ImageButton with content-desc "WinTeam". `s.log_out()` uses it.
- PIN login: keypad `numericPadLayout`, keys are Buttons with the digit as text (`s.key`), "Use password" =
  `pinLoginUsePasswordLink`, "Return to login" = `pinLoginReturnToLogin`.
- A "Change user warning" dialog appears before the sign-in page only when punches or messages are pending, never
  on a fresh install.
- `s.close_sign_in()` (Android back) leaves the sign-in page without signing in.
- Dark mode: `s.adb("shell", "cmd", "uimode", "night", "yes")` (and `"no"` to go back).
- Biometrics need a fingerprint enrolled on the emulator: `s.adb("shell", "locksettings", "set-pin", "1111")`,
  `s.adb("shell", "am", "start", "-a", "android.settings.FINGERPRINT_ENROLL")`, then `s.adb("emu", "finger",
  "touch", "1")` until enrolled. Without one the app skips straight to "Set up a PIN instead?". The emulator runs
  with `-no-snapshot-save`, so the enrollment is lost when it restarts.
