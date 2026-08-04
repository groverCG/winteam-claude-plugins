# `WTBaseManager`'s three synchronizers

Mechanics for step 6 of the `response-entity-sibling` skill. Read this when you are writing the Manager
method, not before — the rule ("call the synchronizer, then read the result back from `DbProxy`") is in the
skill and is the part you have to remember.

All three are `protected` on `WinTeam.Mobile.Core/Managers/WTBaseManager.cs`, and all
three do the same thing: fetch → AutoMap → `DbProxy.DeleteAllAsync<TEntity>()` → `DbProxy.SaveWithChildrenAsync(...)`,
inside a try/catch that logs and swallows.

| Synchronizer | Use for |
|---|---|
| `SynchronizeDbEntityList<TEntity, TResponse>(networkFetcher, dataFilter = null)` | a collection replacing the whole table |
| `SynchronizeDbEntity<TEntity, TResponse>(networkFetcher, dataFilter = null)` | a single entity |
| `SynchronizeDbEntityKeepingLocalEntity<TEntity, TResponse>(networkFetcher, dataFilter = null)` | a single entity where specific local rows must survive the wipe |

## 1. List — replaces the whole table

```csharp
if (forceDownload)
    await SynchronizeDbEntityList<XyzEntity, XyzResponse>(
        () => XyzProxy.GetXyzListAsync(), XyzDataFilter);

var items = (await DbProxy.AllWithChildrenAsync<XyzEntity>()).ToList();

// The filter runs after mapping, before the save — this is how local rows survive DeleteAllAsync:
private List<XyzEntity> XyzDataFilter(List<XyzEntity> incoming)
{
    var keep = DbProxy.AllWithChildren<XyzEntity>().Where(x => x.IsLocalOnly).ToList();
    return keep.Concat(incoming).ToList();
}
```

## 2. Single entity

```csharp
if (forceDownload)
    await SynchronizeDbEntity<XyzEntity, XyzResponse>(XyzProxy.GetXyzAsync);

return await DbProxy.FirstOrDefaultWithChildrenAsync<XyzEntity>();
```

## 3. Single entity, preserving a local-only row

```csharp
await SynchronizeDbEntityKeepingLocalEntity<XyzEntity, XyzResponse>(
    XyzProxy.GetXyzAsync, XyzKeepLocalFilter);

return await DbProxy.FirstOrDefaultAsync<XyzEntity>(x => !x.IsLocalOnly);

// Returns a list so the incoming entity and the preserved local one are both saved:
protected List<XyzEntity> XyzKeepLocalFilter(XyzEntity incoming)
{
    var localOnly = DbProxy.FirstOrDefault<XyzEntity>(x => x.IsLocalOnly);
    if (localOnly is null) return [incoming];
    return [incoming, localOnly];
}
```

## Connectivity is already handled — don't guard for it

The synchronizer wraps the whole fetch in try/catch and logs failures, so an offline or failing request leaves
the cached rows untouched and the `DbProxy` read below returns them. A Manager method needs no `IsConnected()`
check and no try/catch of its own around the sync. (An explicit connectivity short-circuit, to skip a pointless
network timeout, belongs *inside* the synchronizer as a future improvement — not copied into every Manager
method.)
