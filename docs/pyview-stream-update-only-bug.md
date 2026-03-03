# PyView Bug: `Stream.insert(update_only=True)` has no effect

## Summary

`Stream.insert(item, update_only=True)` is documented to "only update existing
items (don't add new)", but the `update_only` flag is silently discarded — it
has **zero effect** on behavior. Every `insert()` call produces an identical
wire-format operation regardless of the flag, causing the client to create
**duplicate DOM elements** instead of updating existing ones.

## Reproduction

```python
from pyview.stream import Stream

@dataclass
class Item:
    id: str
    value: int

stream = Stream([Item("abc", 1)], name="items")
# Initial render sends: insert "items-abc" at -1

# Later, on a tick:
stream.insert(Item("abc", 2), update_only=True)
# Expected: update the existing "items-abc" element in place
# Actual:   sends another insert for "items-abc" at -1 → client creates a
#           SECOND <div id="items-abc">, triggering mounted() again
```

**Observed symptom:** The browser console shows:
```
Multiple IDs detected: items-abc. Ensure unique element ids.
```
The `phx-hook` `mounted()` fires a second time for the same ID, creating
duplicate state (in our case, duplicate Leaflet map markers).

## Root cause

### 1. `update_only` is stored but never checked (lines 126-139)

`_do_insert()` unconditionally appends to `_ops.inserts` and
`_pending_items` — it never checks whether an item with the same `dom_id`
already exists:

```python
def _do_insert(self, item: T, at: int, limit: int | None, update_only: bool) -> str:
    dom_id = self._dom_id_fn(item)
    self._ops.inserts.append(          # ← always appends, never deduplicates
        StreamInsert(dom_id=dom_id, item=item, at=at, limit=limit, update_only=update_only)
    )
    self._pending_items.append((dom_id, item))  # ← also always appends
    return dom_id
```

### 2. `update_only` is never transmitted to the client (lines 274-297)

The wire format serialization explicitly drops the flag:

```python
def _to_wire_format(self, ops: StreamOps) -> list:
    # ...
    # Note: update_only is stored internally but not sent over wire in 0.20 format.
    inserts = [[ins.dom_id, ins.at, ins.limit] for ins in ops.inserts]
    # ...
```

The client receives `["items", [["items-abc", -1, null]], []]` — identical to a
fresh insert. It creates a new DOM element, producing a duplicate.

### 3. No deduplication in `_pending_items`

`_pending_items` is a plain list. Multiple `insert()` calls for the same
`dom_id` within one render cycle all accumulate. When the template iterates
the stream (`{% for dom_id, item in items %}`), it yields duplicates.

## Impact

Any code using `insert(item, update_only=True)` to update an existing stream
item will instead create a duplicate DOM element on every call. This:

- Triggers `mounted()` instead of `updated()` on phx-hooks
- Produces "Multiple IDs detected" console errors from LiveView's DOM patcher
- Causes state duplication in any hook that creates objects in `mounted()`

## Suggested fix

Two things need to happen:

### A. Server-side deduplication in `_do_insert()`

When `update_only=True`, either:
- Skip the insert entirely if the `dom_id` is not in the current render
  (requires tracking which dom_ids are "live" on the client), **or**
- At minimum, deduplicate `_pending_items` — if a `(dom_id, ...)` entry
  already exists, replace it instead of appending

### B. Transmit `update_only` on the wire (if Phoenix supports it)

Phoenix LiveView 0.20 may not have a wire-format slot for `update_only`.
If that's the case, the server should handle it entirely:

- When `update_only=True` and the item's `dom_id` has NOT been previously
  inserted in this stream (i.e., it was rendered on a prior cycle and is
  already in the client DOM), send the insert normally — the client will
  update the existing element in place.
- When `update_only=True` and the `dom_id` has NOT been seen before at all,
  **skip the insert** (don't add a new item).

The key insight is that Phoenix's client-side JS *does* handle the case where
an insert's `dom_id` matches an existing DOM element — it updates in place and
calls `updated()` rather than `mounted()`. So the wire format is fine for
updates. The problem is purely that `_do_insert` doesn't deduplicate
`_pending_items`, causing the **template** to render two elements with the
same ID in the initial HTML, which confuses the differ.

## Workaround

Until this is fixed, callers can guard on the client side:

```javascript
// In the phx-hook mounted() callback, check for duplicates:
window.Hooks.MyHook = {
  mounted() {
    if (myRegistry.has(this.el.id)) {
      // Duplicate — treat as update, not add
      return;
    }
    // ... normal mounted() logic
  },
};
```

## Affected version

- PyView Stream implementation as of 2026-03-03
- File: `pyview/stream.py`, lines 126-139 and 274-297

## Environment

- Python 3.14
- PyView (installed from git)
- Phoenix LiveView wire protocol 0.20 format
