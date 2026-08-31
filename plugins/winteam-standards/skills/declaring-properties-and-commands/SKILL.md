---
name: declaring-properties-and-commands
description: >-
  Use when adding a bindable property or command to a ViewModel in WinTeam.Mobile.Core — [ObservableProperty],
  SetProperty(ref, [RelayCommand] — or making a view react to a value changing.
when_to_use: >-
  Applies even mid-execution of an already-approved plan that names the file, class or method shapes —
  an approved plan is not an exemption. Applies whichever tool writes the file: Write, Edit, a Bash
  heredoc, `sed -i`, or an MCP server's own file-creation call.
---

# Declare bindable members with the source generators

CommunityToolkit.Mvvm's generators produce the property, the change notification, and the command plumbing from
an attribute. Hand-writing that boilerplate is more code, and every hand-written `SetProperty` is a place where
a wrong property name in a notification silently stops a binding from updating.

## Which shape applies here

Decide by looking at the type you are editing:

- **The file is new, or the type has no existing manual `SetProperty(ref …)` or `new RelayCommand(...)`
  members** → use the generators, as below.
- **The type already declares members that way** → match what is already there, and leave the existing
  members alone. Converting them is a separate, reviewed change; ask for
  `/winteam-standards:mvvm-audit` when you want that done deliberately.

Mixing both styles inside one class is the outcome to avoid — it makes the class read as though one half is
mid-migration, and reviewers cannot tell which style is intended.

## When to use

Before writing the member. Fires when you are about to add a property the view binds to, a command the view
invokes, or a property whose change should refresh another property or a command's enabled state.

## When NOT to use

- Non-bindable state — a private field, a computed `=>` property, a constant. Those need no attribute.
- Static display strings. The idiom here is a plain computed property, grouped in a region:
  `public string Title => AppStrings.Title;`
- Entities, DTOs, records, and messages.
- Platform view code.
- A type already built on manual `SetProperty` — see the shape rule above.

## Properties

```csharp
public partial class ThingViewModel : WTBaseObservableRecipient
{
    [ObservableProperty]
    private string _displayName;          // generates DisplayName

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(CanSubmit))]
    private bool _isConfirmed;            // changing this also notifies CanSubmit

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(SubmitCommand))]
    private bool _hasSelection;           // changing this re-evaluates SubmitCommand

    public bool CanSubmit => IsConfirmed && HasSelection;
}
```

- **`partial` is mandatory** on the class. Without it the generator cannot emit, and you get a compile error
  that does not name the missing keyword.
- Declare the **backing field**, not the property. The generator produces the public member from it.
- `[NotifyPropertyChangedFor]` for a dependent computed property; `[NotifyCanExecuteChangedFor]` for a
  command's enabled state. Reaching for these is what removes hand-written notification chains.
- Side effects on change go in the generated `OnXChanged` partial hook, not in a hand-written setter.

  ```csharp
  partial void OnIsConfirmedChanged(bool value) => RefreshBanner();
  ```

## Commands

```csharp
[RelayCommand]
private async Task SubmitAsync()          // generates SubmitCommand
{
}

[RelayCommand(CanExecute = nameof(CanSubmit))]
private void Clear()                      // generates ClearCommand
{
}
```

The generated name is the method name plus `Command`, with any `Async` suffix dropped.

### The one real trap: two `IRelayCommand` types

CommunityToolkit and MobileCore each define an `IRelayCommand`, and both extend `ICommand`. **Bindings accept
either**, so this is not a runtime binding failure — but the two names collide, and in a file that imports both
namespaces you get an ambiguous-reference compile error.

Resolve it with a `using` alias naming the one you mean, which is already the established pattern in this
codebase:

```csharp
using IRelayCommand = Mobile.Core.Mvvm.Common.Commands.IRelayCommand;
```

Pick the alias to match how the type exposes its other commands. If you are hand-declaring a command property
of MobileCore's type alongside a generated one, alias explicitly rather than relying on import order.

## Rules

1. **`partial class`, always** — for both attributes.
2. **Never hand-write a `SetProperty` in a type that uses `[ObservableProperty]`.** Pick one style per class.
3. **Use the `Notify*For` attributes instead of a manual `OnPropertyChanged(nameof(Other))` chain.** The
   attribute is checked against a real member name at compile time; a string in a manual call is not, so a typo
   there is a binding that silently never updates.
4. **Don't rename a generated command or property by hand.** Rename the method or backing field and let the
   generated name follow.
5. **Async command methods return `Task`, not `void`,** so the generated command is an async command with
   proper execution tracking.

## Known offenders

The codebase is mid-transition and the generators are still the minority — manual `SetProperty` sites
outnumber `[ObservableProperty]`, and manual `new RelayCommand(...)`/`new AsyncRelayCommand(...)`
constructions outnumber `[RelayCommand]` by a wide margin. Ask for `/winteam-standards:mvvm-audit` for the
live split — no count is recorded anywhere, because one written down here would go stale silently.

That is why the shape rule above keys off the type you are editing rather than a global preference — new code
uses generators; existing manual types stay internally consistent until deliberately migrated.

## Verify

- The class is `partial`; the build is clean.
- The view binds the generated names — property without the leading underscore, method name plus `Command`.
- No manual `OnPropertyChanged(nameof(...))` chain remains where a `Notify*For` attribute would do.
- `dotnet build WinTeam.Mobile.Core/WinTeam.Mobile.Core.csproj`, plus the platform csproj if a view binds the
  new member. **A binding to a name that no longer exists compiles cleanly**, so open the screen and confirm the
  member actually updates.
