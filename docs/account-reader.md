# Automatic account scanning

On the **Play** tab, open **View my account** and choose **Read account in game**. For pet upgrades, open **Optimize pets → Read pets and generate plan**. The scanner navigates menus and fills the fields it can verify. With the emulator running, it opens the game if needed, dismisses recognized notices and returns to the Adventure tab. Let the scanner finish before using the menus. An adventure in progress requires intervention. **Stop reading** and closing the dialog both cancel a scan started from the dialog.

**Refresh account before starting** scans before handing the configuration to the runner. A scan completed within the last ten minutes can be reused after verifying the account in the lobby. A manual scan requests fresh data and can resume a recent incomplete scan. Manual build settings are retained unless **Adjust strategy based on equipment** is enabled.

Progress is saved by section and after confirmed items, pets and material descriptions. Cancelled or timed-out scans can resume from recent checkpoints for the same account. The normal cache expires after ten minutes. A scan with only the tree left can resume that section for up to 24 hours. When several eligible snapshots exist, the newest is used.

## Observed data

- **Equipment.** The six upper slots are opened to read each item name, rarity and level. The detail page must show **Remove** or **Remover** to establish that the item is equipped.
- **Stats.** The scanner pairs labels with values on the same row in **Stats Details**, including percentages, final values and multipliers. Locked item bonuses are excluded.
- **Hero.** Reads the current hero name, level and visible gold stars. Companion details must identify the hero and show a removal option.
- **Pets.** The green check in the collection must agree with **Unequip** or **Desequipar** in the detail panel. An upgrade arrow indicates availability for an upgrade.
- **Mounts and sentinels.** Reads the deployed power. Confirmed pairs include Dino with Dino Blessing and Stone Sentinel with Colossal Strength. Unknown deployment remains unknown.
- **Bag.** Reads item names and balances shown next to **You own** or **Você possui**. Unidentified materials remain in the observed inventory.
- **Tree.** Opens the zoom with a bounded two-finger pinch when rank labels are too large, anchors the canvas at its lower-left edge, then scans overlapping rows in a serpentine route across both sides and upward. Reads learned skill nodes (one to four ranks); skips the small ten-rank HP/ATK/DEF squares because those bonuses are already in Stats Details. Every visible candidate is considered, without the old six-node limit. Taps scale with the rank text size. Detail rewards still require a confirmed learned rank, and partial scans retain confirmed unlocks.
- **Version and progress.** Reads the game version in Settings and the unlocked chapter from the lobby. The last beaten chapter is one below the unlocked chapter. The scanner restores the original mode after reading Normal and Elite progress.

Unread fields stay unknown. Switching accounts discards the previous account's data during the merge. The history presents account scans separately from actual runs.

Snapshots are stored in `data/account_scan.json`, the last 30 scans in `data/account_scan_history.json` and checkpoints in `data/account_scan_checkpoint.json`. PNG and OCR evidence is stored in `debug/account_scan/`. Git ignores these files.

Tree checkpoints use the actual viewport fingerprint and a versioned route. Cached results from the old vertical-only traversal re-read the tree while retaining the other completed account sections. Coverage stops at detected pan limits or the bounded traversal/scan budget. The tree remains marked partial, so unread unlocks are never treated as proven absent. If Android rejects two-finger input, the scan logs the limitation and continues lateral coverage.

The pinch is sent over the selected ADB connection using the bundled 2 KB `roguebot/assets/tree-gesture.jar`; it uses Android input events without root or an installed APK. The matching Java source and reproducible build script are in `tools/android/TreeGesture.java` and `tools/build_tree_gesture.py`. Rebuilding downloads development tools into ignored `build/tree-gesture`; normal scans do not download Java or modify the host installation. Existing packaged executables must be rebuilt to include this update; `bin/roguebot.cmd` loads the current source and asset.

## Validation

The two-dimensional traversal update passes the full **1,230-test** desktop suite. Regression cases cover both lateral boundaries, overlapping rows, zoom normalization, unsupported zoom fallback, cancellation, skipping attribute squares, more than six skill candidates, old-cache refresh, viewport mapping and the bundled gesture/source checksum. The Java helper compiles to Android DEX and is bundled with the source launcher. A live account scan using these new gestures has not yet been observed.

Emulator inspection confirmed six equipment slots, Lancelot at level 42 with two stars, Rogue as a companion, 27 stats, Dino, Stone Sentinel, and the pets Pyrehorn, Castlepod and Emberin. It observed version 0.631 and energy stayed at 71. The bag and tree were partially read.

After a user report that the scan was repeating, checkpoint and cache regression tests were added using real English account screenshots. The project also has Portuguese recognition fixtures.
