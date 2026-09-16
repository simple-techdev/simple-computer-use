"""Unit tests for the non-GUI parts: config, state, coord math, agent
registry, grounding response parsing."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from scu import agents, config, state
from scu.screens import Display, fraction_to_point, point_to_fraction


class TestConfig(unittest.TestCase):
    def test_defaults(self):
        cfg = config.load_config()
        self.assertIn("grounding", cfg)
        self.assertEqual(cfg["grounding"]["provider"], "none")

    def test_env_override(self):
        with patch.dict(
            os.environ,
            {"SCU_GROUND_PROVIDER": "remote", "SCU_GROUND_URL": "http://x:1",
             "SCU_GROUNDING_WIDTH": "1000"},
        ):
            cfg = config.load_config()
        self.assertEqual(cfg["grounding"]["provider"], "remote")
        self.assertEqual(cfg["grounding"]["url"], "http://x:1")
        self.assertEqual(cfg["grounding"]["width"], 1000)


class TestState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.patcher = patch.object(
            config, "STATE_PATH", os.path.join(self.tmp, "state.json")
        )
        # state.py imported STATE_PATH directly; patch the module attr too
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_update_and_read(self):
        import scu.state

        with patch.object(scu.state, "STATE_PATH", os.path.join(self.tmp, "s.json")):
            st = scu.state.update(status="Clicking", session=True, screen=42)
            self.assertTrue(st["session"])
            self.assertEqual(st["status"], "Clicking")
            self.assertEqual(st["screens"], {"42": True})
            st2 = scu.state.read()
            self.assertEqual(st2["status"], "Clicking")

    def test_session_end_clears(self):
        import scu.state

        with patch.object(scu.state, "STATE_PATH", os.path.join(self.tmp, "s2.json")):
            scu.state.update(session=True, status="x", screen=1)
            st = scu.state.update(session=False)
            self.assertFalse(st["session"])
            self.assertEqual(st["screens"], {})


class TestCoords(unittest.TestCase):
    def test_fraction_roundtrip(self):
        d = Display(index=1, display_id=7, x=1440, y=0, w=1920, h=1080,
                    scale=2.0, primary=False)
        x, y = fraction_to_point(0.5, 0.25, d)
        self.assertEqual((x, y), (1440 + 960, 270))
        fx, fy = point_to_fraction(x, y, d)
        self.assertAlmostEqual(fx, 0.5, places=3)
        self.assertAlmostEqual(fy, 0.25, places=3)


class TestAgentRegistry(unittest.TestCase):
    def test_unique_ids(self):
        ids = [a.id for a in agents.AGENTS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_kinds_valid(self):
        valid = {"skills", "global_file", "skills+file", "mcp", "mcp+file", "generic"}
        for a in agents.AGENTS:
            self.assertIn(a.kind, valid, a.id)

    def test_skill_source_exists(self):
        self.assertTrue(
            os.path.isfile(os.path.join(agents.skill_source_dir(), "SKILL.md"))
        )

    def test_marker_block_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "AGENTS.md")
            agents._append_marker(path)
            content = open(path).read()
            self.assertIn(agents.MARK_BEGIN, content)
            self.assertIn("scu session start", content)
            # idempotent re-append
            agents._append_marker(path)
            self.assertEqual(open(path).read().count(agents.MARK_BEGIN), 1)
            self.assertTrue(agents._remove_marker(path))
            self.assertNotIn(agents.MARK_BEGIN, open(path).read())


class TestGroundingParse(unittest.TestCase):
    def test_parse_digits(self):
        import re

        for raw, want in [("(920, 340)", (920, 340)), ("[512,100]", (512, 100)),
                          ("click at 640, 480", (640, 480))]:
            nums = re.findall(r"-?\d+\.?\d*", raw)
            self.assertEqual((int(float(nums[0])), int(float(nums[1]))), want)


if __name__ == "__main__":
    unittest.main()
