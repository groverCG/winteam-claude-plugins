---
name: response-entity-sibling
description: >-
  Use when creating or changing an entity/response pair in WinTeam.Mobile.Core — adding a new Entity or a new
  Response class anywhere under Entities/, adding, renaming or removing a field on either half of an existing
  pair, porting or migrating a model class into Entities/, or wiring a Manager to cache an API payload for
  offline use. Also use when a Manager, ViewModel or platform View is typed with a *Response instead of its
  *Entity sibling. Covers [AutoMap], WinTeamBusinessEntityBase, choosing the [PrimaryKey], TextBlob companion
  strings, and the WTBaseManager synchronizers.
---

# Response → Entity siblings, and Entity as the single source of truth

This repo caches API responses locally (SQLite via `DbProxy`, `sqlite-net` + `SQLiteNetExtensions`) so screens can show cached data offline. The convention: every top-level `XyzResponse` that a `*Proxy` method returns gets a matching `XyzEntity`, even before a manager actually wires up the offline-cache read/write path for it. Both halves live under `WinTeam.Mobile.Core/Entities/` — historically the Response in `Entities/Response/` and the Entity in the flat folder, though a subfolder may hold both. **The folder is a filing decision; the rules below are not.** Reference example: `ContactInformationEntity`/`ContactInformationResponse`.

**Once the Entity exists, it is the single source of truth** — the Response is only a wire-format DTO for deserializing the JSON. Nothing above the Manager should ever reference the `Response` type. The Manager maps `Response` → `Entity` internally and returns or accepts only `Entity` types; ViewModel properties, command generic parameters, and platform View method signatures on both iOS and Android are all typed `XyzEntity`, never `XyzResponse`.

## When to use

**Anywhere under `WinTeam.Mobile.Core/Entities/`** — the flat folder, `Entities/Response/`, and any
subfolder all count. The pair rules do not care which folder you picked.

Four entry points:

- **Writing a new `public class XyzResponse { ... }`**, or any new top-level property bag a Proxy method
  returns: does an `XyzEntity` exist? If not, create it before considering the response type done.
- **Writing a new `public class XyzEntity`**: it needs the base class, the `[AutoMap]`, and a `[PrimaryKey]`
  before it is finished. An Entity missing any of the three is not persisted at all — see step 0.
- **Adding, renaming or removing a field on an existing pair.** The two halves have to move together. If you
  edit `XyzResponse` and `XyzEntity` exists, mirror the field on the Entity **in the same change** — the
  Entity is the source of truth, and a field that only exists on the Response is a field no screen can read
  offline.
- **Porting or migrating a model class into `Entities/`** — from another app, another project, or a Response
  that has outgrown its folder. A lifted class arrives with none of the three requirements.

Also check the reverse direction: if a Manager method, ViewModel property/command, or platform View is
typed with `XyzResponse` anywhere and a matching `XyzEntity` already exists, that's a violation to fix —
Response should not leak past the Manager.

## When NOT to use

Do not create a sibling for:

- **child classes carried inside a response.** The qualifying test is whether *we expect the type back from
  an API* — that is, whether a `*Proxy` method returns it at the top level. Only that outer type gets an
  Entity. A class that merely travels inside one never gets a sibling of its own: it lives in the entity
  sibling's domain as a single plain-named class shared by both halves. See step 5 for the shape;
- request/payload DTOs (anything in `Entities/Request/`);
- types never returned by a Proxy method, e.g. UI-only value objects;
- **write-results and acks.** The rule in one line: *a Response that is a cached read model always gets an
  Entity; a Response that reports the outcome of a write does not.* Nothing persists an ack, so there is
  nothing to cache. The nine that legitimately have no Entity today: `ErrorResponse`, `UploadPhotoResponse`,
  `TimeClockPunchResponse`, `CallLogResponse`, `CustomerBrandingResponse`, `UserSettingsResponse`,
  `KioskProfileLastContactResponse`, `BiometricsConsentSubmissionResponse`,
  `TeamTimeMessageSubmissionResponse`. A Manager returning one of these directly is fine and is the one
  sanctioned exception to "no Response above the Manager".

## Steps

0. **An `*Entity` must never carry `[JsonProperty]`.** That attribute is how a wire DTO is deserialized, so
   its presence on a class named `*Entity` means the pair was never split — you have one class doing both
   jobs, and it is the Response. Symptom to recognise: `public class XyzEntity` with `[JsonProperty]` on its
   members, no base class, no `[AutoMap]`, no `[PrimaryKey]`. Nothing persists, nothing maps, and
   `DatabaseManager`'s reflection over `WinTeamBusinessEntityBase` never creates the table. Split it: the
   `[JsonProperty]` half becomes `XyzResponse`, and `XyzEntity` is rebuilt per the steps below.

1. **Name it** `<ResponseNameMinusResponse>Entity`, e.g. `XyzResponse` → `XyzEntity`, in `WinTeam.Mobile.Core/Entities/XyzEntity.cs` (namespace `WinTeam.Mobile.Core.Entities`, not `.Entities.Response`).

   Match the names for a new pair. One existing pair does not — `ProfilePhotosEntity` maps from `PhotosProfileResponse`, with the words swapped — so when you are looking for an existing sibling, **the `[AutoMap(typeof(...))]` target is the authoritative link, not the file name.** Do not add a second Entity because a name lookup came up empty.

2. **Extend `WinTeamBusinessEntityBase`** and mark it mapped from the response:
   ```csharp
   [AutoMap(typeof(XyzResponse))]
   public class XyzEntity : WinTeamBusinessEntityBase
   {
       ...
   }
   ```
   `[AutoMap]` is picked up automatically by `MapperConfigSingleton` (`cfg.AddMaps(AppDomain.CurrentDomain.GetAssemblies())` in `WinTeam.Mobile.Core/Utils/MapperConfigSingleton.cs`) — there is no manual per-entity registration step. Once the attribute exists, `MapperConfigSingleton.Instance.Mapper.Map<XyzEntity>(response)` (or `Map<List<XyzEntity>>(responseList)`) just works.

3. **Pick a `[PrimaryKey]`.** sqlite-net requires exactly one:
   - If the response already carries a natural unique value (an id, a number, a token/guid), reuse that property directly as the key — a `Number`, a `WorkerId`, a document's `Token`.
   - Otherwise add an **entity-only** auto-increment integer key, named after the domain concept rather than a bare `Id` (the base class already reserves `Id` as an ignored `Guid` — see `WinTeamBusinessEntityBase`). Follow the `ContactInformationEntity.ProfileId` precedent:
     ```csharp
     [PrimaryKey]
     [AutoIncrement]
     public int XyzId { get; set; }
     ```
     This property has no matching property on the Response — AutoMapper's convention-based mapping just leaves it untouched (defaults to 0), and sqlite-net assigns the real value on insert.

4. **Mirror the response's scalar properties 1:1** (same names/types) unless a type needs a SQLite-friendly stand-in.

5. **Blob nested complex properties** (objects or lists) rather than giving them their own table, and give
   each blobbed property a companion `string` for the serialized form.

   **The child is one plain-named class, declared in the Entity's own file, and used by *both* halves.** Not
   a `*Response` type, and not a second class per side:

   ```csharp
   // ContactInformationEntity.cs — the child is declared here, in the entity's domain:
   [TextBlob("Phone1Blobbed")]
   public PhoneNumber Phone1 { get; set; }
   public string Phone1Blobbed { get; set; }

   // ...and further down that same file:
   public class PhoneNumber { /* ... */ }

   // ContactInformationResponse.cs references that identical type:
   public PhoneNumber Phone1 { get; set; }
   ```

   **Why it has to be the same type on both sides:** AutoMapper then carries the value across with no child
   mapping configuration at all. This holds for collections too, which is the case people doubt —
   `KioskProfileEntity.Jobs` and its response are both `List<KioskJob>`, and
   `LastStatusEntity.AvailableActions` and its response are both `List<AvailableActionResponse>`. Both ship.

   Naming follows from that: the child is a domain type, so it is named for the concept (`PhoneNumber`,
   `ContactAddress`, `KioskJob`, `WageDetail`) rather than suffixed `Response`.

   **The one case where a `*Response` type belongs in a blob** is when the wire payload *itself* is what you
   are caching — `TimePunchEntity` deliberately blobs `ErrorResponse` and `TimeClockPunchResponse` so a
   failed punch can be replayed later. If you are storing a record of a response rather than a piece of your
   own domain, the `*Response` type is correct.

6. **Wire the Manager through `WTBaseManager`'s synchronizers — never call AutoMapper manually from a Manager.** There are three, all `protected` on `WTBaseManager`, all doing fetch → AutoMap → `DbProxy.DeleteAllAsync<TEntity>()` → `DbProxy.SaveWithChildrenAsync(...)` inside a try/catch that logs and swallows:

   | Synchronizer | Use for |
   |---|---|
   | `SynchronizeDbEntityList<TEntity, TResponse>(networkFetcher, dataFilter = null)` | a collection replacing the whole table |
   | `SynchronizeDbEntity<TEntity, TResponse>(networkFetcher, dataFilter = null)` | a single entity |
   | `SynchronizeDbEntityKeepingLocalEntity<TEntity, TResponse>(networkFetcher, dataFilter = null)` | a single entity where specific local rows must survive the wipe |

   The rule in one line: **call the synchronizer, then read the result back from `DbProxy`.** The Manager never hands a `Response` to anyone.

   The three call shapes, the `dataFilter` mechanics, and why no connectivity guard is needed:
   [`references/wtbasemanager-synchronizers.md`](references/wtbasemanager-synchronizers.md). Read it when you
   write the method — the rule above is the part to remember.

   **Know what `DeleteAllAsync<TEntity>()` costs** — this is the one call in the reference whose consequence is a design decision, not a mechanic. It wipes the *entire* table for that entity type before saving the fresh batch — there is no built-in scoping by a parent id. If the entity represents a list scoped to one parent among several the user might visit, only the most-recently-synced parent's rows stay cached, and switching parents while offline shows whichever parent was synced last. The `dataFilter` parameter is the sanctioned hook for surviving the wipe, and it has exactly two precedents here (both in the reference): carrying local-only rows forward, and preserving a single row alongside the incoming entity. What has **no** precedent here is using `dataFilter` to scope by a parent id. If parent-scoping matters for the feature, surface the tradeoff rather than inventing new scoped-delete infrastructure unprompted.

7. **Check every downstream consumer.** ViewModel properties/fields, command generic parameters (`IAsyncRelayCommand<T>`, `IRelayCommand<T>`), and platform View method signatures on both iOS and Android should all reference the `Entity`, never the `Response` — update the Manager interface (`IXyzManager`) to match the Entity-typed return, and if retrofitting onto code that used the Response end-to-end, a global rename of the type name across the ViewModel and both platform Views is usually the full fix (their shapes are otherwise identical to the Response).

## Verify

```bash
dotnet build WinTeam.Mobile.Core/WinTeam.Mobile.Core.csproj   # plus the iOS/Android csproj if Views changed
```

**What the build proves:** the entity compiles, the `[AutoMap]` target type resolves, and no lingering
`Response` reference remains above the Manager. **What it cannot catch:**

- **The sync path.** Whether the synchronizer populates the table, and whether cached rows come back offline,
  only shows at runtime. Exercise the screen once online, then again in airplane mode.
- **`DeleteAllAsync<TEntity>()` blast radius.** The whole-table wipe compiles perfectly. If the entity is a
  list scoped to one parent, visit two parents online, go offline, revisit the first — stale rows are the bug.
- **A wrong `[PrimaryKey]`.** A non-unique key silently overwrites rows instead of accumulating them.
