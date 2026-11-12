# Structural code review

## November 5, 2026

- **Shop decisions.** One typed action now carries the price, target and item. The executor uses a single dispatch and confirmation path. Each core skill is scored once, and the neutral utility search runs only after core skills and rerolls are exhausted. Visit state changes after confirmation.
- **Recovery and scheduling.** A campaign simulation stops at an existing adventure instead of playing it. Each routine activity starts with fresh timer evidence. Exhausted retries receive a new deadline.
- **Account and history.** The scanner chooses the newest eligible snapshot for the verified account and refreshes the timestamp at each checkpoint. Reusing a completed scan does not duplicate its history entry. Reward totals keep their matching time and energy samples together. The history tolerates malformed optional reward data and the window recognizes Party Expedition entries.
- **Policy boundaries.** Premium currency mentions block named event choices, shop rerolls and nearby reward claims. A farm loss streak belongs to one stage. Numeric form inputs use a shared decoder so malformed values keep their translated errors.
- **Desktop structure.** The activity panel owns its widgets, log buffer and changelog. It appends each batch of log messages with one widget update and renders only the latest observation. The player replay tests now have their own module.
- **Language.** Source diagnostics, internal decision reasons and technical documentation use English. Localized UI messages, game labels, fixture text and observed skill aliases retain their source languages.

The full Python suite passed 1,183 tests, including 10 new regression cases. The Windows build completed and its main window opened from an empty working directory. The smoke test stopped after startup. Android and Flutter tests require a separate SDK environment.

## November 3, 2026

- Run orchestration moved to `runner.py`. Typed progress records retain routine and expedition state across recovery.
- A selected skill becomes pending when dispatched and is recorded after a recognized transition away from the offer.
- Settings and catalogs use atomic JSON replacement. The desktop and Android implementations preserve existing data if a write fails.
- Tk workers publish results through a queue. The main thread updates widgets and drains a bounded log queue.
- Providers share cancellable polling. MuMu verifies the focused package exactly, and Stop interrupts waits after input.
- Capture and recognition diagnostics use public device methods and obtain text and confidence from one OCR pass.
- The Android catalog uses the current offer's rarity while preserving reviewed tags. Android also retains the victory or defeat result when leaving a double-reward screen.

The November 3 review passed 1,017 Python tests and built the Windows executable. Its command-line smoke test succeeded from an empty working directory. Computer Use authorization expired before visual inspection. Android and Flutter tests were unavailable in that environment.
