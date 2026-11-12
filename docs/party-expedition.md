# Party Expedition

Open the bot with `roguebot` and choose **Party Expedition** under **Modo**. The goal is **20/20**,
starting at the game's current stage. If it says **10/20**, stages 1–9 are not replayed. A victory
advances to the next stage; a defeat retries the same one while attempts remain.

Choose **Função preferida** and **Limite de partidas**. The default limit is 20 matches for this
Start action, including defeat retries. The limit is a bound, not a target: winning stage 20 stops
the bot earlier. Running out of event attempts also stops it. Normal energy, elite cost, patrol,
the full routine and energy waiting do not apply to this mode. Existing normal/elite preferences
are retained when switching back. The game recognition and the bot window support Portuguese,
Spanish and English independently. Real Portuguese event menus and Codex names have regression
captures; full Portuguese combat validation remains pending. An event showing all stages cleared
stops without pressing Match again. See [guide improvements](guide-improvements.md).

## Online party and route votes

The bot opens the right-hand Party Expedition event icon, then the castle's center-bottom expedition
icon, reads the stage and key counter, and presses **Match** once. It waits for matchmaking, handles
the timed four-card role offer and subsequent upgrades, and waits through fights and campfires.
An expedition already running can be resumed without pressing Match again. An unrecognized screen
saves `debug/party_*.png` and stops; it does not force-stop an online match or blindly requeue.
After a result, incomplete/loading frames and temporarily missing Match text are reread inside the
event. They do not trigger generic Back navigation. Only the centered fight title counts as combat;
the lobby's Expedition icon and promotional popups never count as an active online match.
First-clear rewards also accept joined OCR words such as `Stage 19cleared!`. The reward is claimed
before the next team's Match button becomes eligible; a missing claim prompt waits instead of requeuing.

Room meanings, supplied by the user:

| Room | Effect |
| --- | --- |
| Treasure | Choose a skill |
| Campfire | Recover health automatically |
| Battle | Easier normal fight |
| Elite Battle | Harder fight followed by a stat upgrade |

Only bright purple room hexagons are selectable. Completed/current rooms and distant rooms are not
voted for. The planner follows the dashed connections between visible rows, prioritizing the nearest
reachable treasure, then further treasures and fewer elite fights. It can choose a normal or elite
room because that path leads to a later chest. If no future chest is visible, easier alternatives
break ties. It votes once per room selection, tolerates OCR coordinate jitter, and lets the party's
automatic timer proceed when no selectable room is recognized. Votes from other online players can
override the bot's preference; hidden parts of the map are not inferred as established connections.

## Skills

The event's 24 Codex skills have their own role preferences, independent of elemental build selection:

- **Atacante / Striker:** critical scaling, ATK and lower aggro, preferring Lethality and Quelling
  Strikes when offered. Flat stat choices prefer ATK, then maximum HP, then DEF.
- **Suporte / Support:** establish recurring healing/shields before amplifiers, with Combat Medic,
  Medica and Divine Caress ahead of Generosity. ATK upgrades support attack-based healing.
- **Guardião / Guardian:** survival, threat and team protection, preferring Unyielding, Provoke and
  Inspiration. Flat stat choices prefer DEF, then maximum HP, then ATK.

When an offer has none of the preferred role's skills, a mandatory alternative is chosen while
avoiding additional aggro/healing penalties when possible. Timed choices are reread, bounded retries
handle a missed tap, and transient black Unity frames are waited out without sending input.

## Validation

The user authorized one online match for development. It started at stage 9 with three keys and ended
in victory, advancing the account to **10/20**. Captures cover matchmaking, the initial role offer,
automatic x4 combat, route maps, elite stat choices, campfire, victory and the first-clear reward.
The new controller was also checked live in dry-run mode at 10/20 without starting another match.

Fixture and simulated tests cover the full captured flow, progression from 10 through 20, defeat
retry, zero attempts, stale victory/team frames, reward collection, role selection, visible route
connections, stage-20 stopping, UI persistence and ensuring normal-energy actions are not invoked.
Stages 10–20 have not been played live by the developer agent.
