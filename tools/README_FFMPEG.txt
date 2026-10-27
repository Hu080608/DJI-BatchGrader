Bundled FFmpeg
==============

File: ffmpeg.exe
Version: 6.1.1-essentials_build-www.gyan.dev (Windows x86_64)
Purpose: video decoding/encoding and 3D LUT application (lut3d filter).

This project runs FFmpeg as a separate process. It is not linked into the
Python application. FFmpeg is distributed under its own license; see
https://ffmpeg.org/legal.html and the build's GPL configuration.

If this file is replaced, any modern FFmpeg build with libx264/libx265 and the
lut3d filter is suitable. Put it at tools/ffmpeg.exe (Windows) or tools/ffmpeg
(Linux/macOS). The application falls back to PATH and then imageio-ffmpeg.
