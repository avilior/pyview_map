# ADR: Dialog Box Implementation in PyView

**Status:** Accepted
**Date:** 2026-03-17

## Context

PyView (Python LiveView) does not include a pre-built dialog or modal component. We need a pattern for implementing dialog boxes (confirmations, forms, informational popups) in our BFF views.

PyView provides three relevant primitives:

1. **`pyview.js` module** — chainable client-side commands (`show`, `hide`, `toggle`, `push_focus`, `pop_focus`, `push`) that render into `phx-click` attributes. No server round-trip for visibility changes.
2. **Server-side context + conditional rendering** — t-string templates can conditionally include dialog markup based on dataclass context fields. Each toggle is a server round-trip.
3. **`push_event` + custom hooks** — server can push named events to the client; a `phx-hook` on the element handles them in JavaScript (e.g., calling `el.showModal()` on the native `<dialog>` element).

## Decision

We adopt three approaches, chosen per use case:

### Approach A: JS Commands (default for simple dialogs)

Use `pyview.js` commands for simple confirm/cancel dialogs where the content is static and no server state gates visibility.

```python
from pyview.js import js

def template(self, assigns, meta):
    return t'''
    <button phx-click="{js.show('#my-dialog')}">Open</button>

    <div id="my-dialog" style="display:none" class="dialog-backdrop">
      <div class="dialog-content">
        <h2>Confirm Action</h2>
        <p>Are you sure?</p>
        <button phx-click="{js.hide('#my-dialog').push('confirmed')}">Yes</button>
        <button phx-click="{js.hide('#my-dialog')}">Cancel</button>
      </div>
    </div>
    '''
```

- Commands are chainable: `js.show('#el').push_focus(to='#input').push('opened')`
- No server round-trip for open/close; `.push('event')` sends to `handle_event` only when needed
- Visibility managed entirely client-side via CSS display

### Approach B: Server-side state (when content depends on server state)

Track open/closed in the view context when the dialog content is dynamic or server logic must gate visibility.

```python
@dataclass
class MyContext:
    show_dialog: bool = False

async def handle_event(self, event, payload, socket):
    if event == "open-dialog":
        socket.context.show_dialog = True
    elif event == "close-dialog":
        socket.context.show_dialog = False
    elif event == "confirmed":
        socket.context.show_dialog = False
        # ... perform action

def template(self, assigns, meta):
    dialog = t''
    if assigns.show_dialog:
        dialog = t'''
        <div class="dialog-backdrop">
          <div class="dialog-content">
            <button phx-click="confirmed">Yes</button>
            <button phx-click="close-dialog">Cancel</button>
          </div>
        </div>
        '''
    return t'''
    <button phx-click="open-dialog">Open</button>
    {dialog}
    '''
```

- Each open/close triggers a server round-trip and re-render
- Dialog content can depend on any server state
- Server controls when the dialog appears

### Approach C: Native `<dialog>` element + push_event + hook (for native behavior or server-triggered dialogs)

Use the HTML `<dialog>` element with a custom hook when you need native dialog features (backdrop, escape-to-close, focus trapping) or when the server must trigger the dialog programmatically.

```javascript
// hooks.js
Hooks.Dialog = {
    mounted() {
        this.handleEvent("show-dialog", () => this.el.showModal());
        this.handleEvent("close-dialog", () => this.el.close());
    }
}
```

```python
# Template
def template(self, assigns, meta):
    return t'''
    <dialog id="my-dialog" phx-hook="Dialog">
      <form method="dialog">
        <p>Are you sure?</p>
        <button phx-click="confirmed">Yes</button>
        <button>Cancel</button>
      </form>
    </dialog>
    '''

# Server-side trigger
await socket.push_event("show-dialog", {})
```

- Native backdrop, escape-to-close, and focus trapping from the browser
- Server can open the dialog at any time via `push_event`
- Hook wires up the `showModal()` / `close()` calls

### Approach D: Server-triggered question/answer dialog (Approach B + C combined)

When the server needs to ask the user a question and handle the response, combine server-side state (for the question content and correlation) with a hook (for native `<dialog>` behavior). The server controls what question is shown; the hook handles `showModal()`/`close()` after DOM updates.

```python
@dataclass
class MyContext:
    dialog_question: str | None = None
    dialog_id: str | None = None  # correlate question to answer handler

class MyView(TemplateView, LiveView[MyContext]):

    async def ask_user(self, socket, question: str, dialog_id: str):
        """Server triggers a dialog with a question."""
        socket.context.dialog_question = question
        socket.context.dialog_id = dialog_id
        # push_event fires AFTER the re-render delivers the new DOM
        await socket.push_event("show-dialog", {})

    async def handle_event(self, event, payload, socket):
        if event == "dialog-response":
            answer = payload["answer"]        # "yes" / "no" / free text
            dialog_id = payload["dialog_id"]
            socket.context.dialog_question = None
            socket.context.dialog_id = None
            await self._on_dialog_answer(dialog_id, answer, socket)

    async def _on_dialog_answer(self, dialog_id: str, answer: str, socket):
        """Route the answer to the right handler."""
        if dialog_id == "confirm-delete":
            if answer == "yes":
                ...  # perform the delete

    def template(self, assigns, meta):
        dialog = t''
        if assigns.dialog_question:
            dialog = t'''
            <dialog id="app-dialog" phx-hook="Dialog">
              <form method="dialog">
                <p>{assigns.dialog_question}</p>
                <button phx-click="dialog-response"
                        phx-value-answer="yes"
                        phx-value-dialog_id="{assigns.dialog_id}">Yes</button>
                <button phx-click="dialog-response"
                        phx-value-answer="no"
                        phx-value-dialog_id="{assigns.dialog_id}">No</button>
              </form>
            </dialog>
            '''
        return t'''
        <div>
          {dialog}
          ... rest of page ...
        </div>
        '''
```

The same minimal hook from Approach C:

```javascript
Hooks.Dialog = {
    mounted() {
        this.handleEvent("show-dialog", () => this.el.showModal());
        this.handleEvent("close-dialog", () => this.el.close());
    }
}
```

**Flow:**

1. Server calls `await self.ask_user(socket, "Delete all items?", "confirm-delete")`
2. Re-render adds the `<dialog>` to the DOM, then `push_event("show-dialog")` fires
3. Hook calls `el.showModal()` — native modal with backdrop, focus trap, escape-to-close
4. User clicks Yes → `phx-click` sends `dialog-response` with `answer="yes"` and `dialog_id="confirm-delete"`
5. `handle_event` clears context → dialog removed from DOM on next render

- `dialog_id` lets one dialog slot serve multiple questions, routed to the right handler
- Question text is fully server-controlled — can be dynamic based on any state
- Same hook reused across all Approach C/D dialogs

## Selection Guide

| Criterion | A (JS) | B (Server) | C (Hook) | D (Question/Answer) |
|---|---|---|---|---|
| Static content, simple confirm | Best | OK | Overkill | Overkill |
| Content depends on server state | No | Best | OK | Best |
| Server must trigger open | No | OK | Best | Best |
| Server asks question, handles answer | No | Partial | No | Best |
| Native focus trapping / escape | No | No | Yes | Yes |
| Minimal round-trips | Yes | No | Partial | No |

## Consequences

- **No shared dialog component yet** — each view implements its own dialog markup. If we accumulate several dialogs, we should extract a reusable `DialogComponent` (LiveComponent) into `bff_engine`.
- **CSS** — dialog backdrop/content styles should be added to the shared CSS in `bff_engine` if multiple views need dialogs.
- **Approach C hooks** — any new hook JS must be registered in the app's hook setup. Keep hook code minimal; business logic stays server-side.