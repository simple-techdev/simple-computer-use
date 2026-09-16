---
name: computer-use
description: See and control this machine's screens — screenshot, ground elements to pixels, click, type, scroll, drag, hotkeys, open apps — via the `scu` CLI. Use for any task that needs GUI interaction on the user's real desktop (no API, no per-app scripting). Works across all connected displays.
---

# Computer use via `scu`

You can operate the user's real desktop like a person: look at the screen,
decide what to do, act with mouse and keyboard, verify the result. All of it
goes through the `scu` command-line tool; every command prints one JSON
object to stdout (`{"ok": true, ...}` or `{"ok": false, "error": ...}`).

## Golden rule: show your work

**Always run `scu session start` before the first action** and
`scu session end` when the task is finished. Sessions turn on the orange
screen glow and the cursor badge so the user can see you working and what
you're doing. While working, keep the badge honest with
`scu status "Saving the document"`.

## The loop

```
scu session start
repeat:
  scu screenshot --screen all     (or a single display index)
  read the PNG file(s) it returns
  choose ONE action
  run it via scu
  scu screenshot again to VERIFY the action did what you expected
scu session end
```

Never assume an action worked — verify with a fresh screenshot. If an action
failed, adjust (different target, hotkey instead of click, scroll into view
first) instead of repeating the same thing.

## Commands

| Command | What it does |
|---|---|
| `scu screenshot [--screen N\|all] [--out DIR]` | Capture display(s); returns PNG paths + geometry |
| `scu ground "desc" [--screen N]` | Description → `{x, y}` without acting |
| `scu click "desc"` / `scu click --at x,y` | Click element; `--clicks 2`, `--button right`, `--hold shift,cmd` |
| `scu type "text" [--into "desc"\|--at x,y] [--overwrite] [--enter]` | Type; unicode handled via clipboard |
| `scu scroll N [--on "desc"\|--at x,y] [--horizontal]` | +N up, -N down |
| `scu drag "from" "to"` / `--from x,y --to x,y` | Drag and drop |
| `scu hotkey cmd shift s` | Key combo |
| `scu press return` | Single key |
| `scu open "Safari"` / `scu focus "Notes"` | Launch / bring to front |
| `scu find-text "Submit" [--screen all]` | OCR text search → coordinates |
| `scu wait 2` | Pause for loads/animations |
| `scu status "..."` | Update the cursor badge text |
| `scu session start\|end` | Glow + badge on/off |
| `scu doctor` | Diagnose permissions/grounding if anything misbehaves |

## Finding targets — three ways, in order of preference

1. **Description** — `scu click "the blue Save button top-right"`. Uses the
   grounding model; write detailed, unambiguous descriptions (what + where).
2. **Your own eyes** — `scu screenshot`, look at the PNG yourself, then
   `scu click --at x,y` using the display's global coordinates. Always
   available, even with no grounding model.
3. **Visible text** — `scu find-text "Submit"` then click the returned
   `x,y`. Great for buttons, menu items, and links when you know the label.

If a description fails to ground, don't retry the same string — screenshot,
find the element yourself, and use `--at`.

## Displays

`scu screenshot` and `scu displays` show every connected display with its
global bounds. Pass `--screen N` to aim grounding/OCR at a specific display;
`--at x,y` is always in the global space, so it can hit any display. The
orange glow brightens on the display you're currently using.

## Fieldcraft

- Prefer hotkeys and menu commands over pixel clicks when they exist
  (`scu hotkey cmd s` beats finding the Save menu item).
- After `scu open`/`scu focus`, `scu wait 2-3` before acting — apps need a
  moment.
- `scu type --overwrite` selects all then retypes; use it for fields with
  existing content.
- For menus/context menus: click to open, screenshot, then click the item.
- Don't use `cmd+tab` on macOS — `scu focus "App"` instead.
- One action per command. Chain by running commands in sequence, verifying
  between steps.
- Keep the user informed through the badge (`scu status`) on long tasks.

## Safety

- You are driving the user's real machine. Ask before destructive or
  irreversible actions (deleting files, sending messages, purchases).
- The user can always take the mouse/keyboard back; if the screen doesn't
  match your expectations, screenshot and re-orient.
- Moving the pointer to a screen corner aborts the in-flight action
  (pyautogui failsafe) — it's the user's panic button, don't fight it.

## If something's wrong

`scu doctor` checks permissions (Screen Recording, Accessibility on macOS),
the grounding endpoint, OCR, and the overlay. Run it first when a command
errors.
