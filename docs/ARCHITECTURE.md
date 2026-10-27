# Architecture

## Processing flow

```text
GUI (CustomTkinter)
  -> drop/file selection
  -> Validation + LUT resolution
  -> BatchProcessor (producer)
       -> collect_media(scope=all/video_raw/video_only)
       -> JobRecord[] + QueueStore snapshot
       -> video ThreadPool / photo ThreadPool
            -> encoders.choose_encoder()
            -> ffmpeg_tools.transcode_video()
            -> photo.process_photo()
            -> photo.process_raw_photo()
       -> per-job progress/status callbacks
       -> QueueStore report (JSON + CSV)
  -> GUI queue table + log
```

## Key modules

| Module | Responsibility |
|---|---|
| `dlog_grader/gui.py` | GUI state, drag/drop, settings, queue table, watch integration |
| `dlog_grader/processor.py` | discovery, scope filtering, validation, concurrency, job state transitions |
| `dlog_grader/ffmpeg_tools.py` | ffmpeg probing, command construction, hardware/audio fallback, tetrahedral LUT / software decode fast path |
| `dlog_grader/encoders.py` | real one-frame encoder probing and cache |
| `dlog_grader/formats.py` | H.264/HEVC/ProRes output profiles |
| `dlog_grader/photo.py` | chunked photo LUT processing; Pillow C `Color3DLUT` fast path; rawpy/libraw RAW decode to 16-bit TIFF |
| `dlog_grader/lut.py` | .cube parse + trilinear interpolation |
| `dlog_grader/lut_library.py` | recursive LUT scan + manifest metadata |
| `dlog_grader/lut_updater.py` | official DJI catalog polling and incremental LUT installation |
| `dlog_grader/jobs.py` | job records, queue persistence, reports, HH:MM:SS duration formatting |
| `dlog_grader/dnd.py` | native Windows drag/drop without WndProc on the whole window |
| `dlog_grader/watcher.py` | watch-folder polling |
| `dlog_grader/diagnostics.py` | anonymized crash diagnostics |
| `dlog_grader/updater.py` | GitHub Releases update check/download/install |
| `dlog_grader/_license_guard` | Compiled native offline license guard: embedded Ed25519 public key, machine binding, trial state and signed license verification |
| `dlog_grader/license_dialog.py` | activation, machine-code copy, license import UI |

## Reliability rules

- Source files are never opened for writing.
- Each job cleans its own temporary LUT/FFmpeg work directory.
- Queue reports are written atomically.
- Partial outputs are removed when an FFmpeg attempt is cancelled or all attempts fail.
- UI updates from worker threads go through `queue.Queue` only.
- Native drop callbacks never call Tk directly.
