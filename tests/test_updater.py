#!/usr/bin/env python3
"""Unit tests for the standalone updater engine."""
from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from updater_app.core import UpdateEngine, UpdateRequest, format_bytes, format_eta  # noqa: E402


class UpdaterTests(unittest.TestCase):
    def test_formatters(self):
        self.assertEqual(format_bytes(0), "0 B")
        self.assertIn("MB", format_bytes(2 * 1024 * 1024))
        self.assertEqual(format_eta(None), "计算中")
        self.assertIn("秒", format_eta(12))

    def test_install_preserves_user_data(self):
        work = PROJECT_ROOT / "temp" / "updater_unit"
        shutil.rmtree(work, ignore_errors=True)
        app = work / "app"
        stage = work / "stage"
        stage_root = stage / "DJI_DLogM_BatchGrader"
        app.mkdir(parents=True)
        stage_root.mkdir(parents=True)
        (app / "config").mkdir()
        (app / "luts" / "custom").mkdir(parents=True)
        (app / "license").mkdir()
        (app / "DJI_DLogM_BatchGrader.exe").write_bytes(b"old-exe")
        settings = app / "config" / "settings.json"
        settings.write_text('{"user": 1}', encoding="utf-8")
        custom = app / "luts" / "custom" / "user.cube"
        custom.write_text("custom", encoding="utf-8")
        license_file = app / "license" / "license.json"
        license_file.write_text("license", encoding="utf-8")

        (stage_root / "DJI_DLogM_BatchGrader.exe").write_bytes(b"new-exe")
        (stage_root / "config").mkdir()
        (stage_root / "config" / "settings.json").write_text('{"default": 1}', encoding="utf-8")
        (stage_root / "luts" / "custom").mkdir(parents=True)
        (stage_root / "luts" / "custom" / "new.cube").write_text("new", encoding="utf-8")
        (stage_root / "new-file.txt").write_text("payload", encoding="utf-8")

        request_path = work / "updates" / "update_request.json"
        request_path.parent.mkdir(parents=True)
        request = UpdateRequest(
            version="9.9.9",
            current_version="9.9.8",
            url="https://example.invalid/update.zip",
            sha256="0" * 64,
            asset_name="update.zip",
            asset_size=1,
            app_root=str(app),
        )
        engine = UpdateEngine(request, request_path)
        engine._install(stage)

        self.assertEqual((app / "DJI_DLogM_BatchGrader.exe").read_bytes(), b"new-exe")
        self.assertEqual((app / "config" / "settings.json").read_text(encoding="utf-8"), '{"user": 1}')
        self.assertEqual((app / "license" / "license.json").read_text(encoding="utf-8"), "license")
        self.assertTrue((app / "luts" / "custom" / "user.cube").exists())
        self.assertTrue((app / "new-file.txt").exists())
        self.assertFalse((app / "luts" / "custom" / "new.cube").exists())
        shutil.rmtree(work)


if __name__ == "__main__":
    unittest.main(verbosity=2)
