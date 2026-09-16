# simple-computer-use

**Give any agent computer use.** One `pip install` + `scu install` and your
agent — Claude Code, Codex, Cursor, Windsurf, Devin, Gemini, OpenCode, or
anything that can run a shell — can see your screens and drive the mouse and
keyboard like a person.

No VM, no harness, no agent framework. The repo is a tool/skill package:
the *agent you already use* is the brain; `scu` is the hands and eyes.

```
┌────────────┐   scu click "the Save button"   ┌─────────────┐
│ your agent │ ──────────────────────────────▶ │  scu tools  │──▶ real GUI
│ (any CLI)  │ ◀────────────── JSON ────────── │  + grounding│
└────────────┘                                  └──────┬──────┘
        ▲                                              │
        │        orange glow + cursor badge            ▼
        └──────────────────────────────────────  all your displays
```

## What you get

- **Per-display screenshots** — every monitor captured at native resolution
- **Grounding** — `"the blue Submit button"` → pixels, via bundled local
  UI-TARS-1.5-7B (MLX, Apple Silicon) or any OpenAI-compatible endpoint
- **Fallbacks that always work** — your agent's own vision via `--at x,y`,
  and OCR text search via `find-text` (tesseract)
- **Actions** — click, type (unicode-safe), scroll, drag, hotkeys, open/focus
  apps
- **Presence UI** — while the agent works, an **orange glow** rims the
  display(s) it's using and a **badge follows the cursor** showing the
  current action ("Clicking 'Save'") — Codex-style transparency
- **Skill + MCP** — installer writes the skill into whichever agent(s) you
  pick, or registers an MCP server where that's the native mechanism

## Install

```bash
git clone https://github.com/simple-techdev/simple-computer-use && cd simple-computer-use
pipx install .        # recommended: isolated env, `scu` on PATH
# or: python3 -m pip install .   (needs a non-Homebrew, non-managed Python)
scu install
```

Requires Python ≥ 3.9 (≥ 3.10 for the bundled local grounding model). On
macOS `brew install python@3.12 pipx` covers everything.

`scu install` walks you through it:

1. **Dependencies** — offers `brew install tesseract` on macOS
2. **Grounding** — pick local bundled model (downloads ~5 GB once),
   remote endpoint, or fallback-only
3. **Permissions** — checks Screen Recording + Accessibility on macOS and
   opens the settings panes if needed
4. **Agents** — detects installed agents and writes the skill in:

   | Agent | How it's wired |
   |---|---|
   | Devin | `~/.config/devin/skills/computer-use/` |
   | Claude Code | `~/.claude/skills/computer-use/` |
   | Codex | `~/.codex/skills/` + `AGENTS.md` |
   | Cursor | MCP server in `~/.cursor/mcp.json` |
   | Windsurf | MCP + `global_rules.md` |
   | Gemini / OpenCode / Amp | `GEMINI.md` / `AGENTS.md` section |
   | Anything else | SKILL.md copied for manual wiring |

Then just ask your agent to do a GUI task — "open Notes and write me a
shopping list" — and it will reach for `scu` on its own.

## How a session looks

```
scu session start           # orange glow on, badge appears at cursor
scu screenshot --screen all # → PNG paths + display geometry
scu click "the Save button" # grounded click, badge says what it's doing
scu type --into "search" "hello" --enter
scu screenshot              # verify it worked
scu session end             # glow off
```

Every command returns one JSON object — `{"ok": true, ...}` or
`{"ok": false, "error": ...}`.

## Commands

| | |
|---|---|
| `scu screenshot [--screen N\|all]` | capture display(s) → PNG paths |
| `scu click "desc" \| --at x,y` | click (+`--clicks`, `--button`, `--hold`) |
| `scu type "text" [--into "desc"] [--overwrite] [--enter]` | type, unicode-safe |
| `scu scroll N [--on "desc"] [--horizontal]` | scroll at element/pointer |
| `scu drag "a" "b" \| --from x,y --to x,y` | drag and drop |
| `scu hotkey cmd shift s` / `scu press return` | keyboard |
| `scu open "App"` / `scu focus "App"` | launch / raise apps |
| `scu find-text "label"` | OCR → coordinates (no model needed) |
| `scu ground "desc"` | resolve without acting |
| `scu status "msg"` | set cursor badge text |
| `scu session start\|end`, `scu glow …` | presence UI |
| `scu doctor` | health check: deps, perms, grounding, overlay |
| `scu ground-server serve\|status` | manage the local model server |
| `scu mcp` | run the MCP stdio server |

## Multi-display

All connected displays are addressable: `--screen N` aims grounding/OCR,
`--at x,y` uses global points that can hit any display. The glow brightens
on whichever display the agent last touched — every screen shows when it's
being worked on.

## Config

`~/.config/simple-computer-use/config.json`, overridable via env:
`SCU_GROUND_PROVIDER`, `SCU_GROUND_URL`, `SCU_GROUND_MODEL`,
`SCU_GROUND_API_KEY`, `SCU_GROUNDING_WIDTH`, `SCU_GROUNDING_HEIGHT`.

## Safety

- Actions run as your user with your permissions — point the agent at a
  screen you're comfortable with it driving.
- The glow/badge exist so automation is never invisible; end any session
  with `scu session end`.
- Moving the pointer to a screen corner aborts the in-flight action
  (pyautogui failsafe).
- The skill doc instructs agents to verify every action with a fresh
  screenshot and to ask before destructive operations.

## Requirements

- macOS (primary, incl. bundled local grounding on Apple Silicon),
  Linux, Windows — core tools work everywhere; the glow overlay is polished
  on macOS with a tkinter fallback elsewhere
- Python ≥ 3.9, `tesseract` for OCR features
- macOS: grant **Screen Recording** and **Accessibility** to your terminal

## Uninstall

```bash
scu uninstall [--agent codex]   # removes skills/MCP entries/rules blocks
pip uninstall simple-computer-use
rm -rf ~/.config/simple-computer-use
```

## Acknowledgements

The grounding approach and several action implementations are adapted from
[Agent-S](https://github.com/simular-ai/Agent-S) by Simular AI (Apache-2.0);
see `NOTICE`. This project keeps the mechanism and drops the harness — the
agent loop is yours.

## License

MIT (see `LICENSE`). Portions adapted from Agent-S remain under Apache-2.0
per `NOTICE`.
