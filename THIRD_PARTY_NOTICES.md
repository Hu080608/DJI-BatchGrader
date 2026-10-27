# Third-Party Notices

## DJI D-Log M Batch Grader

The project source is proprietary commercial software. See `LICENSE.txt` and
`COPYRIGHT.md` for evaluation and paid-use terms.

This project distributes or uses the following third-party components:

## FFmpeg

- Project: https://ffmpeg.org/
- Bundled binary: `tools/ffmpeg.exe`
- The bundled Gyan.dev "essentials" build is configured with GPL components
  including `libx264` and `libx265`.
- FFmpeg is a separate executable invoked by this application.
- FFmpeg license and source information: https://ffmpeg.org/legal.html
- Anyone redistributing this application must comply with the applicable
  FFmpeg license, including source-offer/notice requirements where required.

## Python packages

- NumPy — BSD-3-Clause — https://numpy.org/
- Pillow — HPND — https://python-pillow.org/
- CustomTkinter — MIT — https://github.com/TomSchimansky/CustomTkinter
- Cryptography — Apache-2.0 OR BSD-3-Clause — https://cryptography.io/
- rawpy — MIT — https://github.com/letmaik/rawpy
- LibRaw (bundled by rawpy) — LGPL-2.1/CDDL — https://www.libraw.org/
- tifffile — BSD-3-Clause — https://www.cgohlke.com
- Nuitka (build-time only) — Apache-2.0 — https://nuitka.net/
- ziglang (build-time only) — MIT — https://ziglang.org/

## DJI LUT files

DJI D-Log / D-Log M LUT files are published by DJI for download. This project
ships 56 DJI official 3D LUT files downloaded from official DJI CDN links
(25 device/series, including normalization and official color-grading packs).
The complete URL list is in `luts/SOURCES.md` and machine-readable metadata is
in `luts/manifest.json`.

This project does not claim ownership of DJI LUTs and is not affiliated with
DJI. Users and redistributors are responsible for complying with DJI's current
terms of use. LUT files can also be imported from the user's own `luts/`
directory.

## DJI trademarks

DJI, D-Log, D-Log M, Osmo, Mavic, Action and related marks are trademarks of
DJI. This application is an independent tool and is not endorsed by DJI.
