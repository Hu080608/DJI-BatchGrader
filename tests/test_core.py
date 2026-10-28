#!/usr/bin/env python3
"""Fast unit tests for core modules (no video encoding)."""
from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dlog_grader.config import AppConfig  # noqa: E402
from dlog_grader.gui import GraderGUI  # noqa: E402
from dlog_grader.diagnostics import record_exception  # noqa: E402
from dlog_grader.encoders import choose_encoder  # noqa: E402
from dlog_grader.ffmpeg_tools import build_video_command  # noqa: E402
from dlog_grader.formats import OUTPUT_PROFILES, QUALITY_PRESETS, get_output_profile  # noqa: E402
from dlog_grader.jobs import JOB_STATUS_LABELS, JOB_STATUS_ORDER, JobRecord, QueueStore, format_duration_hms  # noqa: E402
from dlog_grader.updater import extract_update_summary  # noqa: E402
from dlog_grader.lut import CubeLUT  # noqa: E402
from dlog_grader.lut_library import scan_lut_library  # noqa: E402
from dlog_grader._license_guard import LicenseError, LicenseManager, canonical_payload  # noqa: E402
from dlog_grader.lut_updater import parse_official_catalog  # noqa: E402
from dlog_grader.processor import SCOPE_ALL, SCOPE_VIDEO_ONLY, SCOPE_VIDEO_RAW, is_ext_in_scope  # noqa: E402
from dlog_grader.presets import TEMPLATES  # noqa: E402
from dlog_grader.updater import check_for_update  # noqa: E402
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


class CoreTests(unittest.TestCase):
    def test_lut_parser_and_transform(self):
        from dlog_grader.config import load_config
        lut = CubeLUT.from_file(load_config().lut_path)
        self.assertEqual(lut.size, 33)
        import numpy as np
        out = lut.transform(np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32))
        self.assertEqual(out.shape, (2, 3))
        self.assertTrue((out >= 0).all() and (out <= 1).all())

    def test_photo_pillow_fast_path_matches_numpy(self):
        import numpy as np
        from PIL import Image
        from dlog_grader.config import load_config
        from dlog_grader.lut import apply_lut_to_rgb_array
        lut = CubeLUT.from_file(load_config().lut_path)
        rng = np.random.default_rng(7)
        arr = rng.integers(0, 256, size=(24, 32, 3), dtype=np.uint8)
        expected = apply_lut_to_rgb_array(lut, arr).astype(np.int16)
        actual = np.asarray(Image.fromarray(arr, "RGB").filter(lut.pillow_filter())).astype(np.int16)
        self.assertLessEqual(float(np.abs(expected - actual).mean()), 1.0)

    def test_duration_format_hms(self):
        self.assertEqual(format_duration_hms(0), "00:00:00")
        self.assertEqual(format_duration_hms(5.4), "00:00:05")
        self.assertEqual(format_duration_hms(3661), "01:01:01")

    def test_lut_strength_and_style_templates(self):
        lut = CubeLUT.from_file(PROJECT_ROOT / "luts" / "DJI Air 3S" / "Normalization" / "DJI Air 3s DJI D-Log M to Rec.709.cube")
        points = np.array([[0.2, 0.4, 0.6], [0.8, 0.1, 0.9]], dtype=np.float32)
        identity = lut.blended(0.0).transform(points)
        full = lut.blended(1.0).transform(points)
        self.assertTrue(np.allclose(identity, points, atol=1e-5))
        self.assertTrue(np.allclose(full, lut.transform(points), atol=1e-5))
        self.assertGreaterEqual(len(TEMPLATES), 8)
        for template in TEMPLATES:
            self.assertTrue(template.path.exists(), f"模板 LUT 不存在：{template.path}")
        cfg = AppConfig(lut_strength=0.65, ui_mode="simple")
        self.assertEqual(cfg.validate(), [])

    def test_output_profiles(self):
        for key, profile in OUTPUT_PROFILES.items():
            self.assertEqual(profile.key, key)
            self.assertTrue(profile.extension.startswith("."))
            self.assertGreaterEqual(profile.bit_depth, 8)
        self.assertEqual(get_output_profile("missing").key, "h264_mp4")

    def test_cpu_encoder_choice(self):
        ffmpeg = PROJECT_ROOT / "tools" / "ffmpeg.exe"
        if not ffmpeg.exists():
            self.skipTest("bundled ffmpeg absent")
        profile = get_output_profile("h264_mp4")
        choice = choose_encoder(ffmpeg, profile, "cpu")
        self.assertEqual(choice.name, "libx264")
        self.assertFalse(choice.hardware)

    def test_command_builder_keeps_audio_map_and_rec709(self):
        ffmpeg = PROJECT_ROOT / "tools" / "ffmpeg.exe"
        profile = get_output_profile("h264_mp4")
        cmd = build_video_command(
            ffmpeg=ffmpeg, input_path=Path("in.mp4"), output_path=Path("out.mp4"),
            filter_graph="lut3d=file=luts/a.cube", profile=profile,
            encoder_name="libx264", audio_mode="copy", crf=18,
            preset="medium", audio_bitrate="192k", hardware_bitrate="80M",
        )
        self.assertIn("0:a?", cmd)
        self.assertIn("-map_metadata", cmd)
        self.assertIn("copy", cmd)
        self.assertIn("bt709", cmd)

    def test_update_summary_is_short(self):
        notes = (
            "<!-- UPDATE_SUMMARY_START -->" + chr(10)
            + "- 修复 A" + chr(10) + "- 新增 B" + chr(10)
            + "<!-- UPDATE_SUMMARY_END -->" + chr(10)
            + "## 完整发布说明" + chr(10) + "这里是很长的大段内容。"
        )
        summary = extract_update_summary(notes)
        self.assertIn("修复 A", summary)
        self.assertIn("新增 B", summary)
        self.assertNotIn("完整发布说明", summary)

    def test_queue_clear_state_roundtrip(self):
        work = PROJECT_ROOT / "temp" / "queue_clear_unit"
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        store = QueueStore(work / "queue.json")
        store.save_state([], status="empty", strict=True)
        status, jobs = store.load_state()
        self.assertEqual(status, "empty")
        self.assertEqual(jobs, [])
        self.assertTrue(set(JOB_STATUS_ORDER).issubset(JOB_STATUS_LABELS))
        shutil.rmtree(work)

    def test_queue_store_roundtrip_and_report(self):
        work = PROJECT_ROOT / "temp" / "unit_queue"
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        store = QueueStore(work / "queue.json")
        job = JobRecord(1, "in.mp4", "in.mp4", "out.mp4", "video", status="failed", error="test")
        store.save_state([job])
        status, loaded = store.load_state()
        self.assertEqual(status, "running")
        self.assertEqual(loaded[0].status, "failed")
        json_path, csv_path = store.write_report(
            loaded, input_dir=work, output_dir=work, started_at="now", cancelled=False
        )
        self.assertTrue(json_path.exists() and csv_path.exists())
        shutil.rmtree(work)

    def test_github_release_update_parser(self):
        from unittest import mock
        release = {
            "tag_name": "v9.9.9",
            "body": "release notes",
            "html_url": "https://github.com/Hu080608/DJI-BatchGrader/releases/tag/v9.9.9",
            "assets": [{
                "name": "DJI_DLogM_BatchGrader_Windows_x64_v9.9.9.zip",
                "browser_download_url": "https://example.com/update.zip",
                "size": 123,
                "digest": "sha256:" + "a" * 64,
            }],
        }
        with mock.patch("dlog_grader.updater._read_json", return_value=release):
            info = check_for_update()
        self.assertIsNotNone(info)
        self.assertEqual(info.version, "9.9.9")
        self.assertTrue(info.url.endswith("update.zip"))
        self.assertEqual(info.sha256, "a" * 64)
        with mock.patch("dlog_grader.updater._read_json", return_value={**release, "tag_name": "v0.0.1"}):
            self.assertIsNone(check_for_update())

    def test_automatic_seven_day_trial(self):
        from datetime import datetime, timedelta, timezone
        work = PROJECT_ROOT / "temp" / "unit_auto_trial"
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        class Clock:
            def __init__(self): self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
            def __call__(self): return self.now
        clock = Clock()
        manager = LicenseManager(
            license_file=work / "license.json",
            state_paths=(work / "state.bin",),
            use_registry=False,
            now_fn=clock,
        )
        first = manager.evaluate()
        self.assertTrue(first.is_trial and first.can_run)
        self.assertEqual(first.days_left, 7)
        self.assertTrue(first.is_new)
        self.assertFalse((work / "license.json").exists())
        clock.now += timedelta(days=3)
        self.assertEqual(manager.evaluate().days_left, 4)
        clock.now += timedelta(days=4)
        expired = manager.evaluate()
        self.assertFalse(expired.can_run)
        self.assertEqual(expired.kind, "expired")
        shutil.rmtree(work)

    def test_automatic_trial_time_rollback(self):
        from datetime import datetime, timedelta, timezone
        work = PROJECT_ROOT / "temp" / "unit_auto_trial_rollback"
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        class Clock:
            def __init__(self): self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
            def __call__(self): return self.now
        clock = Clock()
        manager = LicenseManager(
            license_file=work / "license.json",
            state_paths=(work / "state.bin",),
            use_registry=False,
            now_fn=clock,
        )
        self.assertTrue(manager.evaluate().can_run)
        clock.now += timedelta(days=3)
        self.assertTrue(manager.evaluate().can_run)
        clock.now -= timedelta(days=10)
        blocked = manager.evaluate()
        self.assertFalse(blocked.can_run)
        self.assertEqual(blocked.kind, "blocked")
        shutil.rmtree(work)

    def test_signed_trial_license_and_time_rollback(self):
        import base64
        from datetime import datetime, timedelta, timezone
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        work = PROJECT_ROOT / "temp" / "unit_license_trial"
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        private = Ed25519PrivateKey.generate()
        public_raw = private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        class Clock:
            def __init__(self): self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
            def __call__(self): return self.now
        clock = Clock()
        manager = LicenseManager(
            license_file=work / "license.json",
            state_paths=(work / "state.bin",),
            use_registry=False,
            now_fn=clock,
            _public_key_bytes=public_raw,
        )
        payload = {
            "version": 1, "license_id": "trial-unit", "type": "trial",
            "edition": "trial", "customer": "Unit Test",
            "machine_code": manager.machine_code,
            "issued_at": clock.now.isoformat(),
            "expires_at": (clock.now + timedelta(days=7)).isoformat(),
            "features": ["all"],
        }
        trial_file = work / "trial.json"
        trial_file.write_text(json.dumps({
            "payload": payload,
            "signature": base64.b64encode(private.sign(canonical_payload(payload))).decode("ascii"),
        }), encoding="utf-8")
        status = manager.activate_license_file(trial_file)
        self.assertTrue(status.is_trial and status.can_run)
        self.assertEqual(status.days_left, 7)
        clock.now += timedelta(days=3)
        self.assertEqual(manager.evaluate().days_left, 4)
        clock.now -= timedelta(days=10)
        blocked = manager.evaluate()
        self.assertFalse(blocked.can_run)
        self.assertIn(blocked.kind, ("blocked", "expired"))
        shutil.rmtree(work)

    def test_signed_commercial_license(self):
        import base64
        from datetime import datetime, timezone
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        work = PROJECT_ROOT / "temp" / "unit_license_signed"
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        private = Ed25519PrivateKey.generate()
        public_raw = private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        manager = LicenseManager(
            license_file=work / "license.json",
            state_paths=(work / "state.bin",),
            use_registry=False,
            now_fn=lambda: now,
            _public_key_bytes=public_raw,
        )
        payload = {
            "version": 1, "license_id": "unit", "type": "commercial",
            "edition": "personal", "customer": "Unit Test",
            "machine_code": manager.machine_code,
            "issued_at": now.isoformat(), "expires_at": None, "features": ["all"],
        }
        license_file = work / "issued.json"
        license_file.write_text(json.dumps({
            "payload": payload,
            "signature": base64.b64encode(private.sign(canonical_payload(payload))).decode("ascii"),
        }), encoding="utf-8")
        status = manager.activate_license_file(license_file)
        self.assertTrue(status.is_commercial and status.can_run)
        payload["machine_code"] = "0000-0000-0000-0000-0000-0000"
        license_file.write_text(json.dumps({
            "payload": payload,
            "signature": base64.b64encode(private.sign(canonical_payload(payload))).decode("ascii"),
        }), encoding="utf-8")
        with self.assertRaises(LicenseError):
            manager.activate_license_file(license_file)
        shutil.rmtree(work)

    def test_official_catalog_parser(self):
        html = (
            '<script>{"slug":"new-lut","name":"DJI New Device D-Log M to Rec.709",'
            '"sub_category":"transcoding","products":[{"title":"DJI New Device"}],'
            '"windows":{"version":"v1.0","release_at":"2026-10-01",'
            '"links":[{"url":"https://example.com/New.cube","category":".cube"}]}}</script>'
        )
        sources = parse_official_catalog(html)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["device"], "DJI New Device")
        self.assertEqual(sources[0]["format"], ".cube")

    def test_lut_library_manifest(self):
        entries, default = scan_lut_library(PROJECT_ROOT / "luts")
        self.assertGreaterEqual(len(entries), 50)
        self.assertGreaterEqual(len({e.device for e in entries}), 20)
        self.assertTrue(default and default.exists())
        self.assertTrue(any(e.device == "DJI Air 3S" for e in entries))
        self.assertTrue(all(e.origin == "默认" for e in entries))
        custom_dir = PROJECT_ROOT / "luts" / "custom"
        custom_dir.mkdir(parents=True, exist_ok=True)
        sample = next(e.path for e in entries if "Air 3S" in e.device)
        custom_file = custom_dir / "_unit_test_custom.cube"
        shutil.copy2(sample, custom_file)
        try:
            entries2, _ = scan_lut_library(PROJECT_ROOT / "luts")
            custom_entries = [e for e in entries2 if e.path.resolve() == custom_file.resolve()]
            self.assertTrue(custom_entries and custom_entries[0].origin == "自定义")
        finally:
            custom_file.unlink(missing_ok=True)

    def test_config_defaults_validate(self):
        cfg = AppConfig()
        self.assertEqual(cfg.validate(), [])
        self.assertIn(cfg.quality_preset, QUALITY_PRESETS)

    def test_gui_folder_scan_worker_does_not_stall(self):
        import queue
        class FakeGUI:
            pass
        fake = FakeGUI()
        fake.events = queue.Queue()
        input_dir = PROJECT_ROOT / "test_media" / "input"
        GraderGUI._scan_import_folder(
            fake, input_dir, 99, True,
            PROJECT_ROOT / "test_media" / "output", "video_only",
        )
        event = fake.events.get(timeout=2)
        self.assertEqual(event[0], "preview_import_done")
        self.assertEqual(event[1], 99)
        self.assertIsInstance(event[2], list)
        self.assertEqual(event[4], "")
        self.assertTrue(all(p.suffix.lower() == ".mp4" for p in event[2]))

    def test_import_scope_filters_extensions(self):
        self.assertTrue(is_ext_in_scope(".mp4", SCOPE_VIDEO_ONLY))
        self.assertFalse(is_ext_in_scope(".jpg", SCOPE_VIDEO_ONLY))
        self.assertFalse(is_ext_in_scope(".dng", SCOPE_VIDEO_ONLY))
        self.assertTrue(is_ext_in_scope(".mp4", SCOPE_VIDEO_RAW))
        self.assertTrue(is_ext_in_scope(".nef", SCOPE_VIDEO_RAW))
        self.assertFalse(is_ext_in_scope(".jpg", SCOPE_VIDEO_RAW))
        self.assertTrue(is_ext_in_scope(".jpg", SCOPE_ALL))
        self.assertTrue(is_ext_in_scope(".dng", SCOPE_ALL))

    def test_all_bundled_luts_validate_and_hashes_match(self):
        import hashlib
        manifest = json.loads((PROJECT_ROOT / "luts" / "manifest.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(manifest["count"], 50)
        for entry in manifest["entries"]:
            path = PROJECT_ROOT / "luts" / entry["file"]
            self.assertTrue(path.exists(), entry["file"])
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(digest, entry["sha256"], entry["file"])
            CubeLUT.from_file(path)

    def test_anonymous_diagnostic_sanitizes_user_paths(self):
        try:
            raise RuntimeError("failure in " + chr(67) + ":" + chr(92) + "Users" + chr(92) + "Someone" + chr(92) + "clip.mp4")
        except Exception as exc:
            path = record_exception(type(exc), exc, exc.__traceback__, enabled=True, endpoint="")
        self.assertIsNotNone(path)
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("Someone", text)
        self.assertTrue(text.find("<user>") >= 0)
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
