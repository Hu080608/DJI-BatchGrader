# Privacy and Anonymous Diagnostics

The application processes media locally. It does not upload source footage,
output videos, LUTs, file paths, or user names to a service.

## Local diagnostics

When an unhandled error occurs, a JSON diagnostic file is written to:

```text
logs/diagnostics/crash_YYYYMMDD_HHMMSS_mmm.json
```

It contains only:

- application version
- Windows platform/build string
- Python version
- exception class and sanitized error message
- sanitized traceback (user/profile/project paths are replaced)

## Optional remote reporting

If `telemetry_endpoint` is configured in `config/settings.json` and the user
leaves "匿名诊断" enabled, the same anonymized payload may be POSTed to the
configured endpoint. An empty endpoint means no network transmission.

The user can turn off anonymous diagnostics in the GUI or set:

```json
"telemetry_enabled": false
```

No analytics or advertising SDKs are included.

## Trial and licensing data

The machine-bound license feature stores only:

- a hashed machine code (not raw hardware identifiers);
- for trial licenses, first-seen/last-seen timestamps;
- a signed license file supplied by the user.

Trial state is protected with Windows DPAPI and stored in the application
`license\` folder, `%LOCALAPPDATA%\DJI-BatchGrader\`, and the current user's
registry hive. It is not uploaded. Source media, output media, file paths and
user names are not included in the license state.
