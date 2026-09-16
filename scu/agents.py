"""Agent detection and skill-installation adapters.

Each known agent gets installed differently depending on what it reads:

  skills      -> copy the SKILL.md folder into the agent's skills directory
  global_file -> append a marker-delimited section to the agent's global
                 instructions file (AGENTS.md / GEMINI.md / global rules)
  mcp         -> register the `scu mcp` stdio server in the agent's MCP config
  combo       -> several of the above
  generic     -> copy SKILL.md into ~/.config/simple-computer-use and print
                 paste-it-yourself instructions
"""

import json
import os
import shutil
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from scu import config

MARK_BEGIN = "<!-- BEGIN SIMPLE-COMPUTER-USE -->"
MARK_END = "<!-- END SIMPLE-COMPUTER-USE -->"

MCP_ENTRY = {"command": "scu", "args": ["mcp"]}


@dataclass
class AgentSpec:
    id: str
    name: str
    bins: List[str] = field(default_factory=list)
    dirs: List[str] = field(default_factory=list)
    kind: str = "generic"  # skills | global_file | skills+file | mcp | mcp+file | generic
    skills_dir: Optional[str] = None      # skill folder destination
    global_file: Optional[str] = None     # file to receive the marker block
    mcp_config: Optional[str] = None      # MCP json config path
    note: str = ""

    def expand(self, p):
        return os.path.expanduser(p) if p else p

    def detected(self) -> bool:
        for b in self.bins:
            if shutil.which(b):
                return True
        for d in self.dirs:
            if os.path.isdir(self.expand(d)):
                return True
        return False


AGENTS: List[AgentSpec] = [
    AgentSpec(
        id="devin",
        name="Devin",
        bins=["devin"],
        dirs=["~/.config/devin"],
        kind="skills",
        skills_dir="~/.config/devin/skills/computer-use",
        note="skills dir",
    ),
    AgentSpec(
        id="claude-code",
        name="Claude Code",
        bins=["claude"],
        dirs=["~/.claude"],
        kind="skills",
        skills_dir="~/.claude/skills/computer-use",
        note="skills dir",
    ),
    AgentSpec(
        id="codex",
        name="OpenAI Codex CLI",
        bins=["codex"],
        dirs=["~/.codex"],
        kind="skills+file",
        skills_dir="~/.codex/skills/computer-use",
        global_file="~/.codex/AGENTS.md",
        note="skills dir + AGENTS.md pointer",
    ),
    AgentSpec(
        id="cursor",
        name="Cursor",
        bins=["cursor"],
        dirs=["~/.cursor"],
        kind="mcp",
        mcp_config="~/.cursor/mcp.json",
        note="MCP server",
    ),
    AgentSpec(
        id="windsurf",
        name="Windsurf",
        bins=["windsurf"],
        dirs=["~/.codeium/windsurf"],
        kind="mcp+file",
        mcp_config="~/.codeium/windsurf/mcp_config.json",
        global_file="~/.codeium/windsurf/memories/global_rules.md",
        note="MCP server + global rules",
    ),
    AgentSpec(
        id="gemini",
        name="Gemini CLI",
        bins=["gemini"],
        dirs=["~/.gemini"],
        kind="global_file",
        global_file="~/.gemini/GEMINI.md",
        note="GEMINI.md",
    ),
    AgentSpec(
        id="opencode",
        name="OpenCode",
        bins=["opencode"],
        dirs=["~/.config/opencode"],
        kind="global_file",
        global_file="~/.config/opencode/AGENTS.md",
        note="AGENTS.md",
    ),
    AgentSpec(
        id="amp",
        name="Sourcegraph Amp",
        bins=["amp"],
        dirs=["~/.config/amp"],
        kind="global_file",
        global_file="~/.config/amp/AGENTS.md",
        note="AGENTS.md",
    ),
    AgentSpec(
        id="generic",
        name="Any other agent",
        kind="generic",
        note="copy SKILL.md and wire it in manually",
    ),
]


def skill_source_dir() -> str:
    """Bundled skills/ dir inside the installed package."""
    return os.path.join(os.path.dirname(__file__), "skills", "computer-use")


def _copy_skill(dst_dir: str) -> str:
    src = skill_source_dir()
    dst_dir = os.path.expanduser(dst_dir)
    os.makedirs(dst_dir, exist_ok=True)
    for name in os.listdir(src):
        shutil.copy2(os.path.join(src, name), os.path.join(dst_dir, name))
    return dst_dir


def _marker_block() -> str:
    return f"""{MARK_BEGIN}
## Computer use — `scu` (simple-computer-use)

This machine has the `scu` CLI installed, giving you computer use: see the
screen, point at UI elements, click, type, scroll, drag, and open apps.

- Start of a GUI task: `scu session start` (orange glow + cursor badge show
  the user what you're doing). End with `scu session end`.
- Loop: `scu screenshot` -> read the PNG -> act -> `scu screenshot` to verify.
- Act on elements by description (`scu click "the Save button"`), by pixel
  (`scu click --at 840,512`), or by text (`scu find-text "Save"`).
- All output is JSON. Full reference: run `scu --help`, or read the bundled
  skill at {os.path.join(skill_source_dir(), 'SKILL.md')}.
{MARK_END}"""


def _append_marker(path: str) -> str:
    path = os.path.expanduser(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    block = _marker_block()
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        content = ""
    if MARK_BEGIN in content:
        pre = content.split(MARK_BEGIN)[0].rstrip()
        post = content.split(MARK_END, 1)[1] if MARK_END in content else ""
        new = (pre + "\n\n" + block + post).strip() + "\n"
    else:
        new = content.rstrip() + ("\n\n" if content.strip() else "") + block + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    return path


def _remove_marker(path: str) -> bool:
    path = os.path.expanduser(path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return False
    if MARK_BEGIN not in content:
        return False
    pre = content.split(MARK_BEGIN)[0].rstrip()
    post = content.split(MARK_END, 1)[1] if MARK_END in content else ""
    with open(path, "w", encoding="utf-8") as f:
        f.write((pre + post).strip() + "\n")
    return True


def _install_mcp(path: str) -> str:
    path = os.path.expanduser(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cfg = {}
    cfg.setdefault("mcpServers", {})["simple-computer-use"] = MCP_ENTRY
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    return path


def _uninstall_mcp(path: str) -> bool:
    path = os.path.expanduser(path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return False
    if cfg.get("mcpServers", {}).pop("simple-computer-use", None) is None:
        return False
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    return True


def install(agent: AgentSpec) -> List[str]:
    """Install the skill into one agent. Returns list of what was done."""
    done = []
    if agent.kind in ("skills", "skills+file"):
        done.append(f"skill copied to {_copy_skill(agent.skills_dir)}")
    if agent.kind in ("global_file", "skills+file", "mcp+file"):
        done.append(f"instructions added to {_append_marker(agent.global_file)}")
    if agent.kind in ("mcp", "mcp+file"):
        done.append(f"MCP server registered in {_install_mcp(agent.mcp_config)}")
    if agent.kind == "generic":
        dst = _copy_skill(os.path.join(config.BASE_DIR, "skill"))
        done.append(f"SKILL.md copied to {dst} — point your agent at it")
    return done


def uninstall(agent: AgentSpec) -> List[str]:
    done = []
    if agent.skills_dir:
        dst = os.path.expanduser(agent.skills_dir)
        if os.path.isdir(dst):
            shutil.rmtree(dst)
            done.append(f"removed {dst}")
    if agent.global_file and _remove_marker(agent.global_file):
        done.append(f"marker removed from {agent.global_file}")
    if agent.mcp_config and _uninstall_mcp(agent.mcp_config):
        done.append(f"MCP entry removed from {agent.mcp_config}")
    return done


def detect_all() -> List[Dict]:
    return [
        {
            "id": a.id,
            "name": a.name,
            "detected": a.detected() if a.id != "generic" else True,
            "via": a.note,
        }
        for a in AGENTS
    ]
