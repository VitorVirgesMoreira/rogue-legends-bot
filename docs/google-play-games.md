# Google Play Games Developer Emulator integration

## Architecture

- `roguebot/providers/base.py` defines the lifecycle contract (`connect`, `start`, `recover`).
- `providers/mumu.py` adapts the existing `emulator.Emulator`. Registry/folder discovery, both MuMu 12
  layouts, manager startup, app launch, shutdown and PID-scoped recovery remain intact.
- `providers/google_play_games.py` discovers Google's ADB, targets an explicit serial, reconnects,
  waits for Android boot, verifies the exact game package and foregrounds it with Android's launcher.
  It has no dependency on a MuMu installation or manager. Starting/restarting Google's Windows
  emulator remains manual; its shutdown method deliberately does nothing to running processes.
- `providers.create_provider` selects from the persisted `RunRequest.provider`, defaulting to `mumu`
  for older settings. `adb_path` and `device_serial` are optional overrides for either provider.
- The runner keeps its progress across retries. First Google recovery reconnects/foregrounds; a
  repeated failure may force-stop only the game before the next start. A new Device then reinitializes
  capture/watchdog/viewport state. Launch status is preserved so game loading gets its full timeout.
- `diagnostics.py` supplies the GUI's read-only connection check. `tools.check_emulator` saves PNGs
  and a JSON report without input, game launch, overlay closing or gameplay.
- The game engine, build selection, shopping safeguards, OCR labels and all daily modes are shared.
  One live-discovered result bug was corrected: skipping x2 rewards now records victory/defeat before
  Continue leaves the result screen.
  The phone implementation is unchanged. Legal, account and Android permission prompts in navigation
  stop the run for manual completion. Premium currency rules remain unchanged.

## Geometry and input safety

`Viewport` is the only conversion between physical screenshot pixels and 1440×2560 reference
coordinates. It crops before OCR and maps every tap and both swipe/hold endpoints back through the
same rectangle. Coordinates round consistently and clamp the far boundary to the last actual pixel;
out-of-range reference coordinates are rejected.

Portrait 9:16 uses the complete image. Landscape requires full-height, centered portrait content:
both measured edges must agree with the aspect-derived bounds within two pixels, and outside columns
must be nearly black. The detector does not crop to arbitrary bright game content. Fully dark or
ambiguous landscape images fail safely. During a newly launched game's startup, navigation waits
without input for a valid viewport, bounded by `GAME_LOAD_TIMEOUT`, rather than restarting the game
on its normal black loading screen. During a level, including Dungeon Dive depth changes, `Player`
waits up to `VIEWPORT_TRANSITION_TIMEOUT` (20 seconds) for valid geometry without sending input.
The same player, build, pending choices and autoplay state survive this wait. Once the viewport is
visible, recognition resumes; continuous invalid frames still reach normal bounded recovery, and
ADB failures are not treated as loading. Input preflight continues to reject invalid geometry.
This conservative strategy intentionally does not support
nonblack sidebars, off-center windows, Android bars reducing the game's full-height rectangle, or a
different game aspect ratio. The logged confidence is geometry validation confidence, not a learned
probability.

`ViewportTracker` caches the rectangle and cheaply rechecks sampled border pixels each frame. Changes
in size/borders trigger detection; failed detection invalidates the old mapping. Before each gesture,
another binary capture checks that geometry still matches the recognized frame. A changed rectangle
blocks that gesture, requiring a new recognition cycle. This adds one screencap per gesture. It avoids
the previous `window_size(landscape=False)` assumption, which rotates Google's physical geometry.

Do not run `wm size` to force a resolution: the bot preserves the user's emulator layout.

## Automated validation

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -n 4 -q
```

Coverage includes old MuMu start/shutdown behavior; provider selection and configuration; missing ADB,
package and emulator; explicit serials with multiple devices; disconnected/booting Android; foreground
launch and recovery; bounded failed recoveries; binary PNG decoding; portrait/landscape crops at
different resolutions; dark scenes, invalid/asymmetric borders; mapping round trips and screen edges;
all gestures; resolution changes; Tk selection/persistence/status; legal/setup refusal; existing
gameplay tests; and a real Google landscape screenshot fixture.

Final automated run: **657 passed in 15.66 seconds**, using Python 3.12.14 and the repository's pinned
dependencies in `.venv`. Tk tests ran successfully on the local Windows desktop. `git diff --check`
also passed.

Two original zero-delay retry tests exposed coarse Windows `monotonic()` ticks: `elapsed > 0` can be
false over consecutive reads. Retry deadlines now use `>=` in navigation/routine, preserving the
configured four-second delay and the existing test expectations. No gameplay policy changed.

## Live validation on 2026-11-03

Read-only phases A–C succeeded against the local Developer Emulator:

- Google's bundled ADB detected `localhost:6520` with Android boot complete and the exact Rogue Legend
  package installed/foreground.
- Physical display: 1920×1080. Detected rectangle: left 656, top 0, width 608, height 1080.
  Normalized output: 1440×2560. Bounds were measured from the captured image, not hardcoded.
- After the user selected English, the existing parser recognized the normal lobby, level
  `38. Runelight Caverns VI`, energy 81, the START button, Star Challenge and the footer.
- Sample OCR confidence: mean 0.990875, minimum 0.89292. Absent close/back/tutorial templates scored
  0.626 / 0.640 / 0.599, below the action thresholds; no spurious close/tutorial action was identified.
- Repeating `adb connect` on the healthy Google transport briefly made it offline. Device now checks
  `get-state` first and connects/waits only when necessary. Real capture then succeeded through adbutils.
  During recovery, connect is issued once and state is polled; repeatedly issuing connect would reset
  Google's pending transport handshake.
- Reproducible artifacts: ignored `captures/emulator_check/raw.png`, `normalized.png`, `report.json`.
  Generate fresh evidence with `python -m tools.check_emulator --provider google_play_games --ocr`.

After two separate user authorizations, two normal level-37 attempts were played (5 energy each,
81 → 76 → 71) with no routine, patrol, ads or repetition. The second reached a visibly confirmed
VICTORY after 30 rolls. Live actions exercised the safe Adventure tap, star-list navigation, dice
hold/auto-play, skill priorities, coin shops, events, card flips and dice duels. Navigation restored
the lobby after both attempts. Diamonds remained at 1920.

Both original attempts exposed an existing ads-off bug: the x2 reward branch pressed Continue but
did not return the already recognized victory, so Player waited on the star list and reported an
unknown screen. `play.py` now preserves the result in that branch. Regression tests replay the exact
Google victory capture (plus defeat and exhausted-ad variants) and verify that the result is returned
with one Continue and no further screenshot. A third energy-spending run after this correction was
not authorized/executed; final result handling is verified against the recorded real screen.

A controlled recovery at the lobby disconnected only `localhost:6520`, reconnected it, force-stopped
only Rogue Legend, relaunched it through the provider and returned to the lobby with energy 71 and
diamonds 1920. Google's emulator stayed running. The real restart exposed about a minute of black
Unity loading; startup now waits safely for its viewport instead of restarting repeatedly.

Local ignored evidence is in `captures/live_gameplay/`, `captures/live_gameplay_trace/` (including
`candidate_009_double_reward.png`) and `captures/live_recovery/`. MuMu is covered by the existing
mock/fixture suite; a real MuMu installation, every daily mode and a complete post-fix farming cycle
have not been exercised live.

| Completion criterion | Evidence/status |
| --- | --- |
| GUI provider selection and persistence | Tk tests passed; native window rendered locally |
| Google connection without MuMu | Live ADB, screenshots, input and recovery passed |
| Game installation/launch | Live package check and targeted relaunch passed |
| Cropping and normalization | Live 608×1080 crop → 1440×2560; multi-resolution tests passed |
| Tap/swipe/hold coordinates | Mapping tests plus live navigation, list scrolling and dice hold |
| Shared gameplay engine | Two live attempts, confirmed victory; final result fix replayed from real capture |
| Provider-aware recovery | Live reconnect, game relaunch and return to lobby; bounded-failure tests |
| MuMu compatibility | Existing discovery/start/shutdown/recovery tests passed; live MuMu untested |
| Automated tests | 657 passed |
| Documentation | README, CLAUDE and this guide updated |

## Manual verification

1. Open the Developer Emulator and finish all initial setup manually. Leave Rogue Legend's English
   or Spanish main menu visible. Avoid using the emulator concurrently with the bot.
2. Launch `python -m roguebot`, select the Google provider and press **Check connection**. Confirm
   connected serial, package, physical display and portrait game viewport. Close/reopen the window
   to check persistence. Switch providers to confirm MuMu's folder/overrides are retained.
3. Run the read-only tool above. Inspect both PNGs and JSON; the normalized frame should have no
   sidebars and OCR boxes should match its reference coordinates.
4. When authorized, tap a recognized safe footer tab, verify its physical target from the transform,
   then return to Adventure. Check an ordinary swipe on a safe list and Android Back.
5. With separate permission to spend normal level energy, run one beaten normal level with ads off
   and repeat/loop disabled in a controlled runner. Observe dice hold/auto-play, a skill choice,
   completion and return to the lobby. Do not use a continuous GUI farming run for this limited test.
6. For recovery, interrupt only the selected device's ADB connection during a controlled run, restore
   it and verify that the runner rechecks readiness/viewport and resumes. Do not kill the shared ADB
   server when other devices are in use. A stopped emulator should end with the manual-restart error
   after bounded retries; Google recovery must never invoke MuMuManager or terminate Windows processes.

## File inventory

Created:

- `roguebot/providers/__init__.py`, `base.py`, `mumu.py`, `google_play_games.py`
- `roguebot/viewport.py`, `diagnostics.py`, `setup_guard.py`
- `tools/check_emulator.py`
- `tests/test_providers.py`, `test_viewport.py`, `test_device.py`, `test_setup_guard.py`,
  `test_diagnostics.py`, `test_play_result.py`
- `tests/fixtures/google_lobby_landscape.png`, `en_google_level_victory_x2.png`
- `docs/google-play-games.md`

Updated:

- `roguebot/emulator.py`, `device.py`, `__main__.py`, `config.py`, `request.py`
- `roguebot/ui.py`, `i18n.py`, `settings.py`
- `roguebot/navigation.py` (setup guard, safe startup wait and retry deadline), `routine.py` (retry deadline)
- `roguebot/play.py` (preserve the known result when skipping/exhausting x2 rewards)
- `tests/test_main.py`, `tests/test_ui.py`
- `README.md`, `CLAUDE.md`

No dependency or phone implementation changes. Diagnostic captures and the authorized one-level
validation script/logs are local ignored artifacts under `captures/`.
