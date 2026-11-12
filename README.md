# rogue-legends-bot

A bot that farms **Rogue Legend** (PocketHaven) in **MuMu Player 12** or **Google Play Games Developer Emulator** on Windows. It works only
from the screen: screenshots over ADB, OCR to read them, and taps. No memory reading or network tampering.
It recognizes Portuguese, Spanish and English in-game. Real Portuguese menu captures
are covered by regression tests; full Portuguese combat validation is still pending.
The bot window supports Portuguese (the default), Spanish and English. Change **Idioma / Language**
in the header; the selection is saved independently of the game's language.

**Money rule:** it never uses offers and never spends diamonds. It dismisses popups through their
"tap to close" text, their ✕, or a recognized area outside the offer. Reward videos are watched
(the VIP pass skips them).

## What it does

For the first run, open **Conexão**, select your emulator, and use **Verificar conexão**.
Then select a mode and stage in **Jogar** and press **Iniciar**. **Atividade** shows what the bot is doing.

- **Automatic account reading:** **Ver minha conta → Ler conta no jogo** fills equipment, hero,
  companions, equipped pets, identified mount/sentinel powers, stats and account facts.
  It returns to the Adventure lobby and dismisses recognized startup popups before reading.
  It saves progress and resumes interrupted reads; recent completed scans are reused.
  Strategy suggestions can be enabled separately. See [account reader](docs/account-reader.md).

Guide-based build rules, account settings, history, automatic farming and progression advice are described in [docs/guide-improvements.md](docs/guide-improvements.md). Chaos/Conquest currently inspect access and season status without spending attempts; active combat awaits real-screen validation.

- **Decision monitoring (emulator):** the window shows the recognized screen, next action and reason.
  **Testar leitura / Test recognition** continuously reads an already running emulator,
  without opening levels, collecting resources, closing overlays or writing the skill catalog.
  Skill previews use the selected build without previous picks; shop previews explain the policy
  rather than promise a purchase without its history/balance confirmation.
- **Stable choices:** events, skill offers, shops and results need two compatible reads before acting.
  Unrecognized event options are reread instead of chosen by position. Known risky events use a
  readable exit/refusal; the existing bounded loot and HP-sacrifice policies remain available.
  Five captured event titles also have an image fallback when title OCR is missing; options still
  need to be read. Treasure cards wait for a confirmed flip before another selection.
  See [docs/autoplay-decisions.md](docs/autoplay-decisions.md) for coverage and validation limits.
- **Levels:** normal or elite. Choose **Energia por fase elite**: 5, 10, 15 or Automatic (highest
  affordable cost). A fixed choice is exact: the bot claims available free energy, then stops or
  waits (Keep running) if that cost is still unaffordable; it never silently substitutes a cheaper run.
  Normal mode remains 5 energy. The level can be:
  - the last unlocked level;
  - the last beaten level;
  - a level that still misses stars (star rewards include diamonds);
  - any beaten level N from Desafío de Estrellas.
  Missing-star scans recognize both normal gold stars and elite purple stars, skipping completed
  cards and scrolling toward earlier levels. Unreadable counts are reread instead of treated as 0/3.
- **Party Expedition:** select the event in **Modo** to progress from the current stage through
  **20/20**. The default match limit is 20; choose Striker, Support or Guardian. It forms an online
  party, chooses the role's skills and stat upgrades, keeps x4 when available, and votes toward
  the nearest reachable treasure along visible map connections. Equal treasure routes favor
  normal fights over elites. Other players' votes can change the final route. Wins collect the
  stage reward and advance; defeats retry the same stage while event attempts and the configured
  match limit remain. It stops after winning stage 20, without buying keys or using normal energy.
  Portuguese labels and the completed-event state are supported. See [docs/party-expedition.md](docs/party-expedition.md).
- **Build:** choose **Linha da build**: fire + critical, pure fire, ice, lightning, shuriken, venom,
  bleed or Automatic. Automatic uses the type order/nature to choose its first element, then commits
  to it for that level. The other profiles have a fixed focus from the start.
  The engine remembers learned families, prefers their upgrades and builds a damage source before
  conditional synergies. Fire + critical adds critical bonuses after establishing fire; it permits
  only one secondary shuriken family, with limited picks, instead of opening a parallel build.
  An ice skill triggered by a critical hit remains ice. Known opposing damage tradeoffs and
  shuriken effects that disable other triggers are avoided in a fire build.
  Shops prioritize affordable skills in the chosen line, then search with the free reroll and
  coin rerolls costing at most **10 per tap**. Other useful skills precede ATK/DEF/Max HP items.
  Earlier shops preserve a premium-skill reserve; shops identified near the final boss spend the
  useful balance. The board's roll counter identifies that final window; unknown progress keeps
  the reserve. Stat stock, reroll effects and coin spending are checked. Emergency healing still
  applies at 25% HP or less. See [docs/shops.md](docs/shops.md) for budgets and detection limits.
  When a mandatory pick has no compatible card after rerolling, neutral utility is preferred to an
  unrelated element. If every card is off-line, one still must be chosen; the main focus stays fixed.
  Preferences persist, and level build history survives connection recovery; each new level starts
  fresh. Skill metadata uses the current offer's rarity and preserves manually reviewed tags.
  Elite previews are read before Start: stage modifiers adjust counters, protection, burst/sustained
  damage and expensive-shop purchases while preserving the chosen element. See
  [docs/elite-builds.md](docs/elite-builds.md) for the observed modifiers and decisions.
- **Rest/healing events:** heal at 25% HP or less. Above that, choose a damage bonus (e.g. Strength
  Potion's +15% ATK), a skill upgrade or maximum HP. Unreadable HP follows the non-healing choice.
  If an elite campfire offers only a central Rest and no alternative, take it even at full HP.
- **Loot/sacrifice events:** recognized goblin huts can be looted up to three times per visit,
  waiting for a coin increase between attempts; at 25% HP or less, leave instead of risking combat.
  An explicit HP-for-legendary-skill option gets one attempt when its readable cost leaves more
  than 25% HP. Unknown costs are skipped. The last 40 event decisions save a PNG and OCR/reason JSON
  under `debug/events`. See [docs/events-and-stars.md](docs/events-and-stars.md).
- **Speed:** advances x1 → x2 → x4 and keeps x4. If x4 is unavailable, restores x2 without buying an unlock.
- **Ad-skip pass:** enable the ad reward checkbox to claim free revives, x2 rewards and other free ad
  rewards immediately through your pass. Revives use only the recognized free yellow button, never
  the diamond-priced option.
- **Activities before stages:** select any of daily VIP-card gems, Arena, Dojo, Tower, Dungeon Dive,
  Crystal Mines and Pet Kingdom. The game store's Daily Rewards claim is no longer automated.
- **Stages:** the bot collects Patrol rewards when due and plays until out of energy, claiming
  free energy (Daily Pack and enabled videos).
- **Loop:** repeats the selected activities and stages after energy recharges.
- **Unattended:**
  - starts MuMu Player, or connects to an already running Google Developer Emulator, and opens the game;
  - resumes an interrupted level;
  - follows the game's forced tutorials;
  - on a freeze, crash or stuck screen it recovers the connection/game (MuMu also restarts). Repeated
    failures stop the run with a diagnostic.

## Setup

1. Python 3.13 with the optional **tcl/tk** feature (python.org installer → Modify).
2. `pip install -r requirements.txt`
3. Either MuMu Player 12 with a portrait 9:16 display (e.g. 1080x1920), or **Google Play Games
   Developer Emulator** with the portrait game centered between black sidebars. Install Rogue Legend
   and finish account setup, permissions and legal agreements manually. Use Portuguese, English or Spanish in-game.

## Usage

```bash
python -m roguebot              # the window: pick the options, press Start
python -m roguebot --dry-run -v # navigate to the level without starting it (no energy spent)
python -m pytest -q             # tests on real screenshots (no emulator needed)
```

On Windows, install the `roguebot` command once from the repository folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\install_command.ps1
```

Open a new CMD window and type `roguebot` from any folder to open the bot window.
The launcher uses this repository's `.venv` and forwards options such as `roguebot -v`.
It adds only the repository's `bin` folder to your user's PATH; administrator access is not needed.
If you move the repository, remove its old `bin` entry from PATH and run the installer again.

Choose **Emulator** in the window. The MuMu folder and Google's bundled ADB are detected when possible.
The **ADB** and **Device** fields override the selected provider's defaults; leave them blank for
automatic settings. Each provider's overrides and your selection are remembered independently.
**Check connection** checks ADB, installation, physical resolution and the detected game viewport
without sending taps or opening the game. Start opens MuMu when needed; open Google's Developer
Emulator manually before Start. Stop ends the run at the next step.

## Google Play Games Developer Emulator

This is Google's **developer emulator**, distinct from the consumer Google Play Games for PC app.
See Google's [developer emulator instructions](https://developer.android.com/games/playgames/pg-emulator)
for prerequisites and installation. The bot discovers `Google\Play Games Developer Emulator\current\emulator\adb.exe`
under Program Files or Local AppData. The default device is `localhost:6520`.

1. Open the Developer Emulator and install/open Rogue Legend.
2. Finish legal agreements/login/permissions yourself; set the game to Portuguese, English or Spanish.
3. Run `python -m roguebot`, select **Google Play Games Developer Emulator**, then **Check connection**.
4. Confirm the game viewport and installation status, pick gameplay options, and press Start.

Read-only validation (saves the raw PNG, normalized PNG, OCR results/confidences and template scores):

```powershell
python -m tools.check_emulator --provider google_play_games --ocr
# Optional overrides:
python -m tools.check_emulator --provider google_play_games --adb 'D:\Emulator\adb.exe' --serial localhost:6520 --ocr
```

Screenshots retain their physical orientation. A shared transform detects black sidebars, checks the
centered 9:16 geometry, crops the game and normalizes it to 1440×2560. Taps, swipes and long presses use
the inverse of that same transform. Bounds are rechecked before input; a resolution change or ambiguous
crop blocks the action. Dark/black landscape frames without reliable edges are rejected safely.

Recovery first reconnects ADB and foregrounds the game; a repeated failure can relaunch **only Rogue
Legend**. Google emulator boot/shutdown/restart stays manual. The bot never kills the shared ADB server
or unrelated Windows processes. MuMu retains its manager-based startup and recovery.

Useful PowerShell 5.1 diagnostics:

```powershell
$adb = 'C:\Program Files\Google\Play Games Developer Emulator\current\emulator\adb.exe'
& $adb devices -l
& $adb connect localhost:6520  # only when disconnected
& $adb -s localhost:6520 get-state
& $adb -s localhost:6520 shell getprop sys.boot_completed
& $adb -s localhost:6520 shell pm list packages com.pockethaven.roguelegend
& $adb -s localhost:6520 shell wm size
& $adb -s localhost:6520 shell screencap -p /sdcard/roguebot_check.png
& $adb -s localhost:6520 pull /sdcard/roguebot_check.png roguebot_check.png
```

Avoid `adb exec-out screencap -p > image.png` in PowerShell 5.1: text redirection can corrupt binary PNGs.
The bot captures bytes directly in Python. If connection fails, open/restart the Developer Emulator,
check the ADB path/serial and retry. If viewport detection fails, foreground the game, wait for visible
content, restore the centered 9:16 layout and run the diagnostic tool. Nonblack borders, a moved game
window and unsupported aspect ratios are deliberately rejected. Legal/setup screens stop automation.

Implementation details, validation status and the remaining live checks are in
[docs/google-play-games.md](docs/google-play-games.md).

See `CLAUDE.md` for how it works inside: architecture, game knowledge, and every screen the bot knows.

The [structural code review](docs/code-quality-review.md) records the maintainability fixes,
regression tests and validation limits from 2026-11-03.
