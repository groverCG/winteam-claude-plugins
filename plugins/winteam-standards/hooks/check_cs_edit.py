#!/usr/bin/env python3
"""Advisory size and teardown check for winteam-standards.

Runs as a PostToolUse hook after Edit/Write on a .cs file. Emits advisories as
additionalContext so Claude sees them; never blocks, always exits 0.

Four scoping decisions are load-bearing:

  * Method limits apply only under WinTeam.Mobile.Core/. Platform view methods
    are exempt by design.
  * Only methods overlapping lines this edit actually changed are reported.
    294 Core methods already exceed the length cap; reporting untouched ones
    would make the hook noise and get it disabled.
  * The file-length advisory fires only when this edit made it worse — the file
    crossed the cap here, or was already over and grew. Dozens of files are
    already over cap, so an advisory on every edit to a pre-existing offender is
    the same noise the bullet above exists to prevent. A one-line fix in a
    765-line file used to emit one every time.
  * The length check covers method bodies only. Constructors and interface
    declarations are parsed for their parameter count and nothing else, and the
    LENGTH_CARVE_OUTS names are exempt from length, not from parameters.
"""
import json
import os
import re
import subprocess
import sys

CORE_PREFIX = "WinTeam.Mobile.Core/"

# Defaults. thresholds.json is the source of truth and overrides these; they stay here
# so a missing or malformed config degrades to the documented values instead of
# breaking a hook whose contract is "never blocks, always exits 0".
FILE_CAPS = (
    ("WinTeam.Mobile.Core/", 250),
    ("WinTeam.Mobile.iOS/", 350),
    ("WinTeam.Mobile.Android/", 450),
)
LENGTH_CARVE_OUTS = {"DoBind", "RegisterInjections", "FinishedLaunching", "BuckleUp"}
MAX_BODY_LINES = 15
MAX_PARAMS = 3
# Responses that are write-results or acks, so they get no *Entity sibling. Without these
# the pair check below fires on nine correct files, and a hook that flags correct code is a
# hook that gets muted.
ENTITY_PAIR_CARVE_OUTS = {
    "ErrorResponse", "UploadPhotoResponse", "TimeClockPunchResponse", "CallLogResponse",
    "CustomerBrandingResponse", "UserSettingsResponse", "KioskProfileLastContactResponse",
    "BiometricsConsentSubmissionResponse", "TeamTimeMessageSubmissionResponse",
    "CheckpointCreateResponse", "CheckpointDetailsUpdateResponse",
}

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "thresholds.json"
)


def load_thresholds():
    """Overlay thresholds.json onto the defaults above.

    Each key is applied independently, so a config that sets only `maxParams` keeps the
    default caps for everything else. Anything of the wrong type is skipped silently —
    the hook is advisory, and a config error must not cost the user their edit.
    """
    global FILE_CAPS, LENGTH_CARVE_OUTS, MAX_BODY_LINES, MAX_PARAMS, ENTITY_PAIR_CARVE_OUTS
    try:
        with open(CONFIG_PATH, encoding="utf-8") as handle:
            config = json.load(handle)
    except Exception:
        return
    if not isinstance(config, dict):
        return

    caps = config.get("fileCaps")
    if isinstance(caps, dict):
        parsed = [(p, c) for p, c in caps.items() if isinstance(p, str) and isinstance(c, int)]
        if parsed:
            # Longest prefix first, so a nested path cannot be shadowed by its parent.
            FILE_CAPS = tuple(sorted(parsed, key=lambda pair: len(pair[0]), reverse=True))

    for key, name in (("maxBodyLines", "MAX_BODY_LINES"), ("maxParams", "MAX_PARAMS")):
        value = config.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            globals()[name] = value

    # An explicit `[]` means "no carve-outs" and is honoured; only a non-list — a typo, a
    # string, a null — falls back to the defaults. Without that distinction there would be
    # no way to clear the list, which is a legitimate thing to want.
    carve_outs = config.get("lengthCarveOuts")
    if isinstance(carve_outs, list):
        LENGTH_CARVE_OUTS = {n for n in carve_outs if isinstance(n, str)}

    pair_carve_outs = config.get("entityPairCarveOuts")
    if isinstance(pair_carve_outs, list):
        ENTITY_PAIR_CARVE_OUTS = {n for n in pair_carve_outs if isinstance(n, str)}

MODIFIER = r"public|private|protected|internal|static|virtual|override|async|sealed|partial|new|extern|unsafe"

SIGNATURE = re.compile(
    r"^\s*(?:\[[^\]]*\]\s*)*"
    r"(?:(?:" + MODIFIER + r")\s+)+"
    r"[\w<>\[\],\.\?]+\s+(\w+)\s*(?:<[^>]*>)?\s*\("
)
# A constructor has no return type: modifiers, then the type's own name, then `(`.
CONSTRUCTOR = re.compile(
    r"^\s*(?:\[[^\]]*\]\s*)*"
    r"(?:(?:" + MODIFIER + r")\s+)+"
    r"(\w+)\s*\("
)
# An interface member carries no modifier at all. Only trusted inside an interface
# body — the same shape matches `await Foo(bar);` anywhere else.
DECLARATION = re.compile(
    r"^\s*(?:\[[^\]]*\]\s*)*"
    r"[\w<>\[\],\.\?]+\s+(\w+)\s*(?:<[^>]*>)?\s*\("
)
TYPE_DECL = re.compile(r"\b(?:class|record|struct|interface)\s+(\w+)")
INTERFACE_DECL = re.compile(r"\binterface\s+\w+")
NOT_A_METHOD = {"if", "while", "for", "foreach", "switch", "catch", "lock", "using", "return", "get", "set"}

# The left-hand side of a subscription is an event member. `NavigationEvent` is the one
# observed shape that carries no other signal, because its handler is inherited.
# No leading \b: the member name is one word, so there is no boundary between the `n` of
# `Navigation` and the `E` of `Event`, and `\bEvent` therefore never matches.
EVENT_LHS = re.compile(r"Event\s*$")


def is_handler_reference(name, line, whole):
    """Is `x += name;` a subscription rather than accumulation?

    Two signals, either sufficient. Measured against every `+= identifier;` in the three
    projects: this keeps all 44 real subscriptions and drops all 8 accumulations
    (`MeasuredHeight`, `WidthDp`, `Length`, `FirstDp`, `FailMessage`, and three camelCase
    locals). Name shape alone cannot do it — real handlers include the plain verbs
    `Navigate`, `UpdateTaxFormsList` and `ShowToastMessage`, while the accumulated values
    are PascalCase properties.

    1. A method of that name is declared in this file. Covers 43 of the 44.
    2. The subscribed-to member ends in `Event`. Covers the 44th —
       `ViewModel.NavigationEvent += Navigate;`, where `Navigate` is a `protected virtual`
       inherited from a base view controller and so is not declared locally.

    The known gap is any other handler inherited from a base class or declared in a
    different partial. Advisory-only, so a false negative is the right way to fail.
    """
    declared_here = re.search(
        r"(?:void|Task|bool|async)[\w<>,\[\]\s\?]*\b" + re.escape(name) + r"\s*\(", whole
    )
    return bool(declared_here) or bool(EVENT_LHS.search(line.split("+=")[0]))


def repo_relative(path):
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=os.path.dirname(path) or ".",
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if root:
            return os.path.relpath(path, root).replace(os.sep, "/"), root
    except Exception:
        pass
    return path.replace(os.sep, "/"), None


def changed_line_numbers(path, root):
    """Lines this edit touched, per git.

    Returns None to mean "treat every line as changed" (a brand new file), or a
    set of 1-based line numbers. An empty set means nothing changed relative to
    HEAD, so no method-level advisory should fire.

    Distinguishing "untracked" from "tracked but identical to HEAD" is the whole
    point: 294 Core methods already exceed the length cap, and treating a clean
    tracked file as fully changed would report all of them on an unrelated edit.
    """
    if not root:
        return set()
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", path],
            cwd=root, capture_output=True, text=True, timeout=5,
        ).returncode == 0
    except Exception:
        return set()

    if not tracked:
        # New file: all of it is this author's work.
        return None

    try:
        out = subprocess.run(
            ["git", "diff", "-U0", "--no-color", "HEAD", "--", path],
            cwd=root, capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception:
        return set()

    changed = set()
    for hunk in re.finditer(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", out, re.M):
        start = int(hunk.group(1))
        count = int(hunk.group(2) or 1)
        changed.update(range(start, start + count))
    return changed


def head_line_count(path, root):
    """This file's length at HEAD, or None when there is nothing to compare against.

    None means "treat the file as new" — untracked, added since HEAD, or git unavailable —
    and the caller reports unconditionally in that case.

    Counted the same way as the working copy: split on newlines, then drop the trailing
    empty element a final newline leaves behind. The two counts have to be produced
    identically or the comparison is off by one on exactly the files that end in a newline.
    """
    if not root:
        return None
    try:
        out = subprocess.run(
            ["git", "show", f"HEAD:{path}"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return None
    if out.returncode != 0:
        return None
    lines = out.stdout.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return len(lines)


def interface_body_lines(lines):
    """1-based line numbers sitting inside an `interface` body.

    Interface members declare no modifier, so they are invisible to SIGNATURE. They
    still matter for the parameter check: an 8-parameter interface method commits
    every implementor. Scoping DECLARATION to these lines is what keeps it from
    matching an ordinary `await Foo(bar);` elsewhere in the file.
    """
    inside = set()
    i, n = 0, len(lines)
    while i < n:
        if not INTERFACE_DECL.search(lines[i]) or lines[i].lstrip().startswith("//"):
            i += 1
            continue
        open_at = i
        while open_at < n and "{" not in lines[open_at]:
            open_at += 1
        if open_at >= n:
            break
        depth = 0
        end = open_at
        while end < n:
            depth += lines[end].count("{") - lines[end].count("}")
            inside.add(end + 1)
            if depth <= 0:
                break
            end += 1
        i = end + 1
    return inside


def parse_methods(lines):
    """Yield (name, decl_line_1based, body_lines, param_count, end_line_1based, kind).

    `kind` is "method", "ctor" or "decl". Only "method" is eligible for the body
    length check; constructors and interface declarations are parameter-check only.
    """
    type_names = set(TYPE_DECL.findall("\n".join(lines)))
    interface_lines = interface_body_lines(lines)
    i = 0
    n = len(lines)
    while i < n:
        kind = "method"
        match = SIGNATURE.match(lines[i])
        if not match:
            match = CONSTRUCTOR.match(lines[i])
            if match and match.group(1) in type_names:
                kind = "ctor"
            else:
                match = None
        if not match and (i + 1) in interface_lines:
            match = DECLARATION.match(lines[i])
            kind = "decl"
        if not match:
            i += 1
            continue
        name = match.group(1)
        if name in NOT_A_METHOD or (kind == "decl" and name in type_names):
            i += 1
            continue

        # Collect the signature across lines until parens balance.
        depth = 0
        j = i
        sig = ""
        while j < n:
            sig += lines[j]
            depth += lines[j].count("(") - lines[j].count(")")
            if depth <= 0 and "(" in sig:
                break
            j += 1
        if j >= n:
            break

        params = ""
        if "(" in sig and ")" in sig:
            params = sig[sig.index("(") + 1:sig.rindex(")")]
        param_count = 0
        if params.strip():
            depth = 0
            param_count = 1
            for ch in params:
                if ch in "<([{":
                    depth += 1
                elif ch in ">)]}":
                    depth -= 1
                elif ch == "," and depth == 0:
                    param_count += 1

        # Find the body, skipping expression-bodied and abstract declarations.
        k = j
        while k < n and "{" not in lines[k] and ";" not in lines[k] and "=>" not in lines[k]:
            k += 1
        if k >= n:
            break
        if "{" not in lines[k]:
            yield name, i + 1, 0, param_count, k + 1, kind
            i = k + 1
            continue

        depth = 0
        started = False
        end = k
        body = 0
        while end < n:
            depth += lines[end].count("{") - lines[end].count("}")
            if "{" in lines[end]:
                started = True
            if started and depth <= 0:
                break
            end += 1
            body += 1
        yield name, i + 1, max(0, body - 1), param_count, end + 1, kind
        i = end + 1


def unpaired_handlers(lines, changed):
    """Event subscriptions added by this edit with no matching -= anywhere in the file.

    `+=` is also numeric and string accumulation, so both branches below have to
    establish that a line is a *subscription* before it can be a teardown finding. Two
    real false positives measured across the three projects before this narrowing:
    `height += (int)constraint.Constant;` read as a lambda, and `total += punch.Hours;`
    read as a handler named `Hours`. Precision is the priority here — this hook's whole
    contract is that it stays quiet enough not to get disabled, and a missed advisory
    costs far less than noise.
    """
    whole = "\n".join(lines)
    findings = []
    for index, line in enumerate(lines, start=1):
        if changed is not None and index not in changed:
            continue
        if "+=" not in line or line.lstrip().startswith("//"):
            continue
        # A lambda needs an actual `=>` on the line. Without that check, a cast or any
        # parenthesised right-hand side matches the bare `+= (` form.
        lambda_sub = re.search(r"\+=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_]\w*)\s*=>", line)
        if lambda_sub:
            findings.append((index, "lambda subscription cannot be unsubscribed"))
            continue
        handler = re.search(r"\+=\s*([A-Za-z_][\w\.]*)\s*;", line)
        if not handler:
            continue
        name = handler.group(1).split(".")[-1]
        if not is_handler_reference(name, line, whole):
            continue
        # The qualifier is optional. Requiring one matched `-= this.OnFoo` but not the
        # far commoner `-= OnFoo`, so correctly paired handlers were reported as leaks.
        if not re.search(r"-=\s*(?:[A-Za-z_][\w\.]*\.)?" + re.escape(name) + r"\b", whole):
            findings.append((index, f"'{name}' subscribed with no matching -= in this file"))
    return findings


# --- Entity/Response pair checks -------------------------------------------------
#
# Added because `response-entity-sibling` was not firing on the work that needed it, and
# nothing in this hook was watching Entities/ at all. The description rewrite makes the
# skill competitive at turn start; these checks are the deterministic backstop for when it
# still is not invoked.
#
# Scoped to Entities/**, not Entities/Response/ — pairs live in the flat folder, in
# Response/, and in feature subfolders like Entities/Checkpoints/, which is exactly where a
# whole feature's pair rules were missed. Entities/Request/ is excluded: request payloads
# get no Entity.

ENTITIES_DIR = "WinTeam.Mobile.Core/Entities"
CLASS_DECL = re.compile(r"\b(?:class|record)\s+(\w+)\s*(?::\s*([^{\r\n]+))?")
PRIMARY_KEY = re.compile(r"\[\s*PrimaryKey\s*\]")
AUTOMAP = re.compile(r"\[\s*AutoMap\s*\(")
AUTOMAP_TARGET = re.compile(r"\[\s*AutoMap\s*\(\s*typeof\s*\(\s*([\w\.]+?)\s*\)")
JSON_PROPERTY = re.compile(r"\[\s*JsonProperty\s*[\(\]]")
TEXT_BLOB = re.compile(r"""\[\s*TextBlob\s*\(\s*["'](\w+)["']\s*\)\s*\]""")
MANUAL_MAP = re.compile(r"\.Mapper\s*\.\s*Map\s*<")
# A declared return type naming a Response, on a member of a Manager or an I*Manager.
#
# Three things this has to avoid, all measured against the real Managers:
#   * The leading \b is load-bearing. Without it `List` matched as a *suffix* of
#     `SynchronizeDbEntityList<KioskProfileEntity, KioskProfileResponse>(`, so all five
#     correct synchronizer call sites were reported as leaks.
#   * The trailing `>\s+\w+\s*\(` is what makes this a signature rather than any generic
#     mentioning a Response — a call site closes with `>(`, with no name in between.
#   * `.*` is greedy so it reaches the outermost `>` of a nested return type like
#     `Task<Result<KioskProfileResponse, List<ErrorResponse>>>`.
MANAGER_RETURNS_RESPONSE = re.compile(
    r"\b(?:Task|List|IEnumerable|IList)\s*<.*\b(\w+Response)\b.*>\s+(\w+)\s*\(")
# A generic type parameter, not a concrete Response. WTBaseManager's synchronizers declare it.
GENERIC_RESPONSE_PARAM = "TResponse"
# Only members visible outside the Manager can leak. A private helper returning a Response is
# how a Manager legitimately holds the wire shape before mapping it.
NON_PUBLIC = re.compile(r"\b(?:private|internal)\b")
LEAK_DIRS = ("WinTeam.Mobile.Core/ViewModels/", "WinTeam.Mobile.Core/UseCases/",
             "WinTeam.Mobile.iOS/", "WinTeam.Mobile.Android/")

_INDEX_CACHE = {}


def entity_index(root):
    """Every class declared under Entities/**, as name -> {base, haspk}.

    Built by walking the tree once per hook run (about 60 small files) because the checks
    below all need cross-file knowledge: whether an *Entity has a *Response counterpart,
    whether a *Response has an *Entity, and whether a base class supplies the
    WinTeamBusinessEntityBase inheritance or the [PrimaryKey].

    `haspk` is per *file*, not per class. These files are one class each in practice, and
    the alternative — tracking brace depth to attribute an attribute to a class — buys
    accuracy this advisory does not need.
    """
    if root in _INDEX_CACHE:
        return _INDEX_CACHE[root]
    index = {}
    mapped = set()
    base_dir = os.path.join(root, ENTITIES_DIR)
    for dirpath, _dirnames, filenames in os.walk(base_dir):
        for filename in filenames:
            if not filename.endswith(".cs"):
                continue
            try:
                with open(os.path.join(dirpath, filename), encoding="utf-8-sig",
                          errors="replace") as handle:
                    text = handle.read()
            except Exception:
                continue
            haspk = bool(PRIMARY_KEY.search(text))
            for target in AUTOMAP_TARGET.findall(text):
                mapped.add(target.split(".")[-1])
            for name, bases in CLASS_DECL.findall(text):
                index[name] = {"base": _first_base(bases), "haspk": haspk}
    index["__mapped__"] = mapped
    _INDEX_CACHE[root] = index
    return index


def _first_base(bases):
    """The first name in a base list, which in C# is the base class if there is one.

    Interfaces cannot come first, so this is either the base class or an interface when the
    type has no base class. A wrong guess here only ever costs a suppressed advisory.
    """
    bases = (bases or "").split("where")[0]
    for part in bases.split(","):
        part = part.strip().split("<")[0].strip()
        if part:
            return part
    return None


def _inherits(name, index, target, seen=None):
    """Does `name` reach `target` through its base chain? Handles ContentEntityBase-style
    intermediates, where the entity does not name WinTeamBusinessEntityBase directly."""
    seen = seen or set()
    while name and name not in seen:
        if name == target:
            return True
        seen.add(name)
        entry = index.get(name)
        if not entry:
            return False
        name = entry["base"]
    return name == target


def _has_pk_in_chain(name, index, seen=None):
    seen = seen or set()
    while name and name not in seen:
        entry = index.get(name)
        if not entry:
            return False
        if entry["haspk"]:
            return True
        seen.add(name)
        name = entry["base"]
    return False


SKILL = "see the response-entity-sibling skill"


def class_body(text, name):
    """The body of `class <name>`, brace-matched, or None if it cannot be found.

    Needed because the shared-child convention puts a plain child class — which legitimately carries
    [JsonProperty], since it deserializes as part of the wire response — in the *same file* as the entity
    that blobs it. Searching the whole file for [JsonProperty] therefore reports correct code, which is
    what this exists to prevent. Falling back to None (and so skipping the check) is the right failure
    mode for an advisory.
    """
    match = re.search(r"\bclass\s+" + re.escape(name) + r"\b", text)
    if not match:
        return None
    open_at = text.find("{", match.end())
    if open_at < 0:
        return None
    depth = 0
    for index in range(open_at, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[open_at:index + 1]
    return None


def entity_pair_advisories(rel, lines, root, changed):
    """Pair advisories for this edit. Empty list when the file is out of scope.

    `changed is None` means a brand new file. The checks that describe a *whole file* being
    wrong (a missing [AutoMap], an Entity holding [JsonProperty]) fire whenever the author
    touched the file at all, because all twelve existing pairs already satisfy them — there
    is no backlog for them to be noisy about, unlike the 294 over-length methods above. The
    checks that scan for a mention (the Response leak) stay scoped to changed lines.
    """
    if not root:
        return []
    text = "\n".join(lines)
    base = os.path.basename(rel)
    out = []
    touched_anything = changed is None or bool(changed)

    in_entities = rel.startswith(ENTITIES_DIR + "/") and not rel.startswith(
        ENTITIES_DIR + "/Request/")

    if in_entities and base.endswith("Entity.cs") and touched_anything:
        index = entity_index(root)
        name = base[:-3]
        stem = name[:-len("Entity")]
        missing = []
        if not _inherits(name, index, "WinTeamBusinessEntityBase"):
            missing.append("does not extend WinTeamBusinessEntityBase, so DatabaseManager's "
                           "reflection never creates its table")
        # Only demand [AutoMap] when there is something to map from. ProcessedMessageEntity
        # is local-only and correct without it.
        if not AUTOMAP.search(text) and (stem + "Response") in index:
            missing.append("has no [AutoMap(typeof(%sResponse))], so MapperConfigSingleton "
                           "cannot map it" % stem)
        if not _has_pk_in_chain(name, index) and not PRIMARY_KEY.search(text):
            missing.append("has no [PrimaryKey], which sqlite-net requires exactly one of")
        if missing:
            out.append("%s: %s — %s." % (rel, "; ".join(missing), SKILL))

        entity_body = class_body(text, name)
        if entity_body is not None and JSON_PROPERTY.search(entity_body):
            out.append(
                "%s carries [JsonProperty] on a type named *Entity — that attribute means this is the wire "
                "DTO, so the pair was never split. The [JsonProperty] half should be %sResponse, with %s "
                "rebuilt as its Entity sibling — %s."
                % (rel, stem, name, SKILL))

        for blob in TEXT_BLOB.findall(text):
            if not re.search(r"\bstring\s+" + re.escape(blob) + r"\b", text):
                out.append("%s: [TextBlob(\"%s\")] has no companion `public string %s` — the blobbed value "
                           "is never serialized — %s." % (rel, blob, blob, SKILL))

    if in_entities and base.endswith("Response.cs") and touched_anything:
        index = entity_index(root)
        name = base[:-3]
        stem = name[:-len("Response")]
        sibling = stem + "Entity"
        if not stem:
            # `Response.cs` itself is the shared base DTO, not one half of a pair.
            return out
        if name in ENTITY_PAIR_CARVE_OUTS:
            pass
        elif sibling in index or name in index.get("__mapped__", ()):
            # The pair exists, so the halves have to move together. Only meaningful on an
            # edit to a tracked file — on a brand new Response there is nothing to mirror.
            if changed:
                out.append(
                    "%s changed and an Entity maps from it (%s or an [AutoMap] target) — mirror any field "
                    "change there in this same "
                    "change; the Entity is the source of truth and a field only on the Response cannot be "
                    "read offline — %s." % (rel, sibling, SKILL))
        else:
            out.append(
                "%s has no %s sibling under Entities/. Create it, or if this Response only reports the "
                "result of a write (an ack, an upload result) it is exempt — add it to entityPairCarveOuts "
                "in thresholds.json — %s." % (rel, sibling, SKILL))

    if (rel.startswith("WinTeam.Mobile.Core/Managers/") and base.endswith("Manager.cs")
            and base != "WTBaseManager.cs"):
        for index_no, line in enumerate(lines, start=1):
            if changed is not None and index_no not in changed:
                continue
            returned = MANAGER_RETURNS_RESPONSE.search(line)
            if (returned
                    and returned.group(1) != GENERIC_RESPONSE_PARAM
                    and returned.group(1) not in ENTITY_PAIR_CARVE_OUTS
                    and not NON_PUBLIC.search(line)):
                out.append(
                    "%s:%d hands back %s. A Manager maps Response -> Entity internally and returns only "
                    "Entity types — either give it an Entity sibling and return that, or if it is a "
                    "write-result add it to entityPairCarveOuts in thresholds.json — %s."
                    % (rel, index_no, returned.group(1), SKILL))
            if MANUAL_MAP.search(line):
                out.append(
                    "%s:%d maps with AutoMapper directly. Managers map Response -> Entity only through "
                    "WTBaseManager's synchronizers (SynchronizeDbEntityList, SynchronizeDbEntity, "
                    "SynchronizeDbEntityKeepingLocalEntity) — %s." % (rel, index_no, SKILL))

    if rel.startswith(LEAK_DIRS):
        index = entity_index(root)
        seen = set()
        for index_no, line in enumerate(lines, start=1):
            if changed is not None and index_no not in changed:
                continue
            for match in re.finditer(r"\b(\w+)Response\b", line):
                name = match.group(1) + "Response"
                sibling = match.group(1) + "Entity"
                if name in seen or name in ENTITY_PAIR_CARVE_OUTS or sibling not in index:
                    continue
                seen.add(name)
                out.append(
                    "%s:%d references %s above the Manager, and %s exists. Nothing above the Manager should "
                    "name a Response type — %s." % (rel, index_no, name, sibling, SKILL))
    return out

def advisories_for(path):
    """Every advisory this file earns, or [] when it is out of scope.

    Everything main() used to do between reading `file_path` off the payload and building the
    additionalContext block. Extracted so the PostToolBatch sweep in sweep_tool_writes.py runs
    these exact checks on files written by Bash or an MCP tool, rather than a second copy that
    would drift. The early returns are the scope contract and are unchanged: non-.cs, missing,
    generated, build output, or outside the three capped projects all yield nothing.

    Callers must have run load_thresholds() first. It is not called here because a sweep checks
    many files in one process and the config only needs reading once.
    """
    if not path.endswith(".cs") or not os.path.isfile(path):
        return []
    base = os.path.basename(path)
    if base.endswith(".Designer.cs") or base.endswith(".designer.cs"):
        return []

    rel, root = repo_relative(path)
    if "/obj/" in rel or "/bin/" in rel:
        return []

    cap = next((c for prefix, c in FILE_CAPS if rel.startswith(prefix)), None)
    if cap is None:
        return []

    try:
        with open(path, encoding="utf-8-sig", errors="replace") as handle:
            lines = handle.read().split("\n")
    except Exception:
        return []

    # A trailing newline leaves a final empty element that is not a line, which made the
    # count one high for the 139 Core files that end in one. The other 395 do not, and for
    # those the count was already right — `wc -l` is the counter that under-reports there,
    # which is why /winteam-standards:size-report uses `awk 'END{print NR}'` to agree.
    if lines and lines[-1] == "":
        lines.pop()

    advisories = []
    total = len(lines)
    if total >= cap:
        # Only advise when this edit made it worse. Dozens of files are already over cap, and
        # the method check below is scoped to changed lines for exactly this reason — advising
        # on every edit to a pre-existing offender is what gets a hook muted. Three cases
        # report: a new file, a file that crossed the cap here, and one already over that grew.
        # A file already over cap that stayed the same length or shrank stays silent, because
        # the author is either working elsewhere in it or already improving it.
        before = head_line_count(rel, root)
        if before is None or before < cap:
            advisories.append(
                f"{rel} is {total} lines, at or over the {cap}-line cap for this project. "
                f"Consider whether a responsibility can come out — see the keeping-files-small skill."
            )
        elif total > before:
            advisories.append(
                f"{rel} is {total} lines, up from {before}, and was already at or over the "
                f"{cap}-line cap for this project. Consider whether a responsibility can come "
                f"out instead — see the keeping-files-small skill."
            )

    changed = changed_line_numbers(rel, root)

    if rel.startswith(CORE_PREFIX):
        for name, decl, body, params, end, kind in parse_methods(lines):
            touched = changed is None or any(ln in changed for ln in range(decl, end + 1))
            if not touched:
                continue
            # Length applies to method bodies only. A constructor that just assigns its
            # parameters and an interface declaration with no body are both exempt.
            if kind == "method" and body > MAX_BODY_LINES and name not in LENGTH_CARVE_OUTS:
                advisories.append(
                    f"{rel}:{decl} {name}() body is {body} lines, over the {MAX_BODY_LINES}-line "
                    f"limit for WinTeam.Mobile.Core."
                )
            if params > MAX_PARAMS:
                extra = ""
                if kind == "decl":
                    extra = " Declared on an interface, so every implementor inherits it."
                elif kind == "ctor":
                    extra = " Past three collaborators, prefer [Inject] properties over a constructor."
                advisories.append(
                    f"{rel}:{decl} {name}() takes {params} parameters, over the limit of "
                    f"{MAX_PARAMS}. Collaborators become [Inject] properties; data becomes a "
                    f"record.{extra}"
                )

    for line_number, reason in unpaired_handlers(lines, changed):
        advisories.append(f"{rel}:{line_number} {reason} — see the tearing-down-subscriptions skill.")

    advisories.extend(entity_pair_advisories(rel, lines, root, changed))

    return advisories


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    load_thresholds()

    advisories = advisories_for((payload.get("tool_input") or {}).get("file_path") or "")
    if not advisories:
        return 0

    context = "winteam-standards advisories (non-blocking):\n" + "\n".join(
        f"  - {item}" for item in advisories
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": context,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
