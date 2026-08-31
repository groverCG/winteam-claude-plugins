---
name: declarative-static-styling
description: >-
  Use when building or restyling a screen in WinTeam.Mobile.iOS or .Android — a new ViewController,
  Fragment, cell or xib, or a visual change to an existing one — or when a setup method (ViewDidLoad,
  OnCreateView, AwakeFromNib) assigns a font, colour, tint, border or corner radius.
when_to_use: >-
  Applies even mid-execution of an already-approved plan that names the file, class or method shapes —
  an approved plan is not an exemption. Applies whichever tool writes the file: Write, Edit, a Bash
  heredoc, `sed -i`, or an MCP server's own file-creation call.
---

# Keep static UI values in markup, not in code

A UI property that is the same every single time a view loads — a text color, a tint, a font, a border, a corner radius, an icon — belongs in the Android layout XML or the iOS storyboard/xib, not in a `.cs` setup method. Setting it in code:
- hides the actual value from anyone reading the markup (Interface Builder / layout preview no longer reflects reality),
- risks silently overriding a value someone edits in the storyboard later,
- and duplicates information that markup already has a first-class way to express.

The override risk is the expensive one, because nothing fails. Given a storyboard that already sets a
label's font and later gains a tablet `<variation>`:

```csharp
public override void ViewDidLoad()
{
    base.ViewDidLoad();
    TitleLabel.Font = UIFont.BoldSystemFontOfSize(17f);   // ← runs AFTER the storyboard loads, so it wins
}
```

Markup loads first and `ViewDidLoad` overwrites it, so the tablet variation **silently never applies**. No
error, no warning — the storyboard still looks correct and the variation still looks configured, so the bug
presents as "the storyboard is broken". The fix is deleting the code line, not adding logic to it.

The exception is anything that must change at runtime for a reason markup can't express: selection state, a feature flag, server-driven content, or a value computed from the view's own runtime geometry. Those stay in code.

## When to use

Run after writing or touching a "one-time setup" method on a screen/view (`ViewDidLoad`,
`InitStylesAndContent`, `OnCreateView`/`OnViewCreated`, `AwakeFromNib`, a view's constructor) that sets a
visual property directly on a control instance. Also run when asked to "review this screen's code," "clean
up static values," or similar.

## When NOT to use

Don't touch an assignment that is genuinely state/data-driven: anything read from a ViewModel property, an
`IsSelected`/`IsExpanded`/similar runtime flag, a `Setup(item)`-style method populating content from a data
model instance, or a value computed from runtime layout (e.g. `CornerRadius = Bounds.Height / 2`). Also
skip values already fully declared in markup with no code override left behind.

## Step 1 — Find the candidates

Grep the view's setup method(s) for direct property assignment on a control:

- iOS: `.TextColor =`, `.BackgroundColor =`, `.TintColor =`, `.Font =`, `.Image =`, `Layer.Border...=`, `Layer.CornerRadius =`, `Layer.Shadow...=`, `.Hidden = true/false` (a literal, not a binding).
- Android: `.SetTextColor(`, `.SetBackgroundColor(`, `ImageViewCompat.SetImageTintList(`, `.Typeface =`, `.SetImageResource(` with a fixed literal, `.CardElevation =`, `.SetStroke(`/`.SetCornerRadius(` with a fixed literal.

## Step 2 — Classify each one

Ask: **does this value ever differ between two loads of this same view, for reasons other than a full redesign?**

- **No, it's always the same** → it's a markup candidate. Move it (Step 3), then delete the code line entirely — don't leave it commented out.
- **Yes, it depends on runtime state** → leave it in code. Typical legitimate cases seen in this codebase:
  - **A selected/unselected appearance toggle on a cell.** Legitimately code-driven on iOS, which has no
    state-selector equivalent in markup:

    ```csharp
    private void UpdateAppearance()
    {
        ContentView.BackgroundColor = _isSelected ? Colors.PrimaryMain : UIColor.Clear;
        ContentView.Layer.BorderWidth = _isSelected ? 0f : 1f;

        var contentColor = _isSelected ? Colors.PrimaryContrastText : Colors.TextPrimary;
        TitleLabel.TextColor = contentColor;
        IconImageView.TintColor = contentColor;
    }
    ```

    **On Android the same toggle belongs in markup.** Set the state and let an XML state selector resolve
    appearance:

    ```csharp
    public bool IsItemSelected
    {
        get => _isItemSelected;
        set { _isItemSelected = value; ItemView.Selected = value; }
    }
    ```

    Decision order on Android: **prefer the XML state selector whenever the state is expressible there
    (`android:state_selected`, `android:state_pressed`, …); fall back to
    `ImageViewCompat.SetImageTintList` only when it isn't**, mirroring the iOS approach. The platform
    asymmetry is intentional — iOS toggles in code because it has to, Android shouldn't because it doesn't.
  - `EmergencyContactUiView.cs` / `ItemEmergencyContact.cs`: shadow/elevation toggled by a `showShadow` parameter that differs per calling screen — legitimately code-driven per call site, not per-load-random.
  - An icon chosen per bound content type, e.g. `IconImageView.Image = GetIcon(ViewModel.ItemType);` — a `Setup`-style data-driven assignment, not a static constant.
  - Anything computed from the view's own measured bounds (e.g. `CornerRadius = Bounds.Height / 2` in `LayoutSubviews()`/`OnSizeChanged`) — markup has no way to express "half of my own runtime height."

## Step 3 — Move a static value into markup

**Android XML** (`Resources/layout/*.xml`): add the equivalent attribute directly on the element and delete the code line.
- Text color → `android:textColor="@color/x"`
- Background → `android:background="@color/x"` (or a `@drawable/` shape resource for anything beyond a flat fill)
- Icon tint → `app:tint="@color/x"` on the `ImageView` (only for genuinely tintable/template icons — see the sibling skill `checking-dark-mode` for which icons are pre-colored/self-adapting and must NOT be tinted at all)
- Font → `android:fontFamily`/`android:textAppearance` referencing the existing style, not `Typeface` set in code
- Elevation/corner radius/stroke → `app:cardElevation`, `app:cornerRadius`, `app:strokeWidth`/`app:strokeColor` on the `MaterialCardView`/shape drawable

**iOS storyboard/xib**: set the corresponding Interface Builder attribute and delete the code line.
- Text color → `<color key="textColor" name="color_x"/>`
- Font → `<fontDescription key="fontDescription" .../>` (add a `<variation>` for tablet sizing per the `sizing-for-tablets` skill if needed)
- Image → `image="icon_name"` directly on the `<imageView>` element — this repo's established pattern, used across the cell xibs. Once the attribute is in the xib, the matching `.Image`/`.TintColor` assignment in `AwakeFromNib()` should be deleted, not left as a duplicate:

  ```xml
  <imageView contentMode="scaleAspectFit" image="ic_example_icon"
             translatesAutoresizingMaskIntoConstraints="NO" id="xxx-iv-icon">
  ```
- Border/corner radius/shadow — IB exposes `layer.borderWidth`/`layer.cornerRadius`/`layer.shadowXxx` as **User Defined Runtime Attributes** in the Identity Inspector when there's no dedicated inspector field; use that instead of a code assignment when the value is constant

## Step 4 — Re-check the setup method

After moving everything static, the setup method should only contain: outlet wiring, `AppStrings`-driven text (still code, since it's localized at runtime, not a design-time constant), and the state-driven exceptions from Step 2. If the method is now empty or near-empty, that's a good sign the view is now fully markup-driven.

## Verify

```bash
dotnet build WinTeam.Mobile.iOS/WinTeam.Mobile.iOS.csproj
dotnet build WinTeam.Mobile.Android/WinTeam.Mobile.Android.csproj
```

**What the build proves:** only that deleting the code lines left nothing dangling. A value moved to the wrong
markup attribute — or deleted from code and never added to markup at all — compiles perfectly cleanly.

**What it cannot catch:**

- **A value dropped entirely.** The control silently falls back to its platform default and looks subtly off.
  Compare the screen against its appearance before the change.
- **A surviving code assignment overriding the markup.** This is the exact failure the skill exists to prevent
  and it is invisible to the compiler — the storyboard value loads, then code overwrites it. Re-grep the setup
  method for the patterns in Step 1 before calling it done.
- **A lost `<variation>`.** Moving a font into markup without carrying its tablet variation across renders
  correctly on phone and wrong on tablet. Check both size classes.
