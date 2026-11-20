# iOS UI facts

The iOS app has few accessibility ids, so find views by visible label (`s.text`). Confirm anything not listed here
with `wt-pr-video … inspect`.

- Use an iOS 26.x simulator: on iOS 27 the app crashes at launch (it doesn't adopt the UIScene lifecycle).
- Login screen: "Log In"; once a PIN exists, "Log in with PIN".
- The sign-in page is an SFSafariViewController. Only `s.log_in()` / `s.sign_in()` type into it: WDA types into
  whichever field has focus, and a wrong focus once put the password in plain text into the email field.
  `s.close_sign_in()` closes it without signing in.
- After the first password login: "Set up PIN" / "No thanks", the PIN twice, "Choose an account" for accounts with
  several tenants, then "Not right now" on the notifications prompt, then Home. `s.sign_in()` handles all of these.
- Home: the side menu button is named "ic menu". `s.log_out()` uses it.
- PIN login: the keypad shows "Enter your PIN"; keys are Buttons named by digit (`s.key`); "Use password";
  "Return to login".
- Dark mode: `s.simctl("ui", "appearance", "dark")` (and `"light"`).
- Recordings stay portrait: after a rotation to landscape, that part of the video shows the screen turned 90°.
