#!/usr/bin/env python3
"""Pre-brief for winteam-standards' entity/response pair rules.

Runs as a PreToolUse hook before Edit/Write. Emits the pair rules as
additionalContext so they land *before* the file is authored, rather than as a
fix-up advisory afterwards. Never blocks, always exits 0.

Why this exists: the `response-entity-sibling` skill was not firing on the work
that needed it. Its description is now written for author intent, but a
description only competes for attention at turn start — by the time a Manager or
an Entity is actually being written the model is mid-execution. This hook is the
deterministic half of the fix, and it is the only lever that reaches a Write to a
file that does not exist yet.

Three scoping decisions are load-bearing:

  * Path match only, no file parsing. On a Write the target may not exist, and on
    an Edit the content on disk is the *pre*-edit state, so neither is worth
    reading here. The stateful checks belong in check_cs_edit.py, which runs
    after the write and can see the result.
  * `Entities/**`, not `Entities/Response/`. Pairs live in the flat folder, in
    `Response/`, and in feature subfolders like `Entities/Checkpoints/` — where
    an entire feature's pair rules were missed because the old trigger named one
    path. `Entities/Request/` is excluded: request payloads get no Entity.
  * Two different briefs. An Entity/Response write needs the attribute rules; a
    Manager write needs the synchronizer rule. Emitting both every time is how a
    hook becomes wallpaper.
"""
import json
import os
import re
import sys

ENTITIES_RE = re.compile(r"(^|/)WinTeam\.Mobile\.Core/Entities/")
REQUEST_RE = re.compile(r"(^|/)WinTeam\.Mobile\.Core/Entities/Request/")
MANAGER_RE = re.compile(r"(^|/)WinTeam\.Mobile\.Core/Managers/.*Manager\.cs$")

ENTITY_BRIEF = """winteam-standards — entity/response pair rules (invoke `response-entity-sibling` before writing):
  - An *Entity extends WinTeamBusinessEntityBase, carries [AutoMap(typeof(*Response))], and has exactly one
    [PrimaryKey]. Missing any of the three and the type is silently never persisted.
  - An *Entity must never carry [JsonProperty] — that means you are holding the wire DTO, and the pair has
    not been split yet.
  - Each nested/complex property is [TextBlob("XBlobbed")] plus a companion `public string XBlobbed`.
  - Editing one half of an existing pair? Mirror the field on the other half in this same change; the Entity
    is the source of truth.
  - A Response that only reports the result of a write (an ack, an upload result) gets no Entity."""

MANAGER_BRIEF = """winteam-standards — Manager caching rules (invoke `response-entity-sibling` before writing):
  - Map Response -> Entity only through WTBaseManager's synchronizers: SynchronizeDbEntityList,
    SynchronizeDbEntity, SynchronizeDbEntityKeepingLocalEntity. Never call MapperConfigSingleton /
    AutoMapper directly from a Manager.
  - The shape is: call the synchronizer, then read the result back from DbProxy. They already try/catch and
    log, so no connectivity guard is needed.
  - Return Entity types. A *Response must not escape above the Manager — the one exception is a write-result
    or ack Response, which has no Entity by design.
  - DeleteAllAsync<TEntity>() inside the synchronizer wipes the whole table. If the data is scoped to one
    parent, surface that tradeoff rather than inventing scoped-delete infrastructure."""


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    path = (payload.get("tool_input") or {}).get("file_path") or ""
    if not path.endswith(".cs"):
        return 0

    rel = path.replace(os.sep, "/")
    if "/obj/" in rel or "/bin/" in rel or os.path.basename(rel).lower().endswith(".designer.cs"):
        return 0

    if ENTITIES_RE.search(rel) and not REQUEST_RE.search(rel):
        brief = ENTITY_BRIEF
    elif MANAGER_RE.search(rel):
        brief = MANAGER_BRIEF
    else:
        return 0

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": brief,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
