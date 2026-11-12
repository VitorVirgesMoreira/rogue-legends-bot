# Emulator decisions and preview

This implementation targets the desktop bot for MuMu and Google Play Games Developer Emulator.

## Events

`event_rules.py` identifies named events and conservative default choices. The live controller in `events.py` applies the bounded policies for Deal with the Devil, Altar of Greed, Abandoned Spoils, Test of Might and Forbidden Knowledge. Options must be readable and enabled. Premium currency mentions block risky choices. Goblin loot and an explicit HP sacrifice for a legendary skill keep their attempt limits and confirmation rules. See [missing stars and events](events-and-stars.md).

In Cursed Fountain, the bot accepts a maximum HP trade for ATK when both percentages are readable, the bonus covers the cost and more than 25% of the old maximum HP would remain after subtracting the whole cost. For +20% ATK and −15% maximum HP, current HP must exceed 40%. If the event stays open after the attempt, the bot waits and then uses Pass.

Unknown choices require another read. A description containing “Leave” does not identify an exit button. Healing and rest retain the 25% threshold and the exception for a sole enabled central Rest option.

The last 40 event records in `debug/events` also include decisions without taps, the recognition source and visual similarity when applicable.

## Confirmation and cards

Events, skills, shops and results require two consecutive compatible reads. The comparison checks content and positions with a small OCR movement tolerance. A changed screen or offer restarts confirmation. Stable events, skills and shops wait three seconds before retrying an ineffective tap. Shop spending has a separate balance and offer check. The countdown revive keeps its immediate recognized free-button path.

A treasure card flip counts when the card no longer appears face down. After three seconds without confirmation, the bot retries that card. Three ineffective attempts produce a diagnostic. The finished grid also has an advance timeout. Returning to the board clears the visit state.

## Visual fallback

The templates in `roguebot/templates/event_titles` come from these fixtures.

- `level_event_rest.png` shows Un Momento de Descanso.
- `level_event_cart.png` shows Carro de Botin Abandonado.
- `en_level_event_disabled_option.png` shows Forbidden Knowledge.
- `en_level_potion_makers_hut.png` shows Potion Maker's Hut.
- `en_level_rest_only.png` shows A Moment To Rest.

The fallback requires the validated reference geometry, an unread title and readable options. Correlation must be at least 0.94 and exceed the next candidate by at least 0.05. The known game language constrains matching. The displayed percentage is similarity. Tests exercise the five titles, unread options, incompatible languages, ambiguity and rejection on unrelated fixtures.

## Window and preview

**Test recognition** shows suggested actions. Stop the preview before choosing **Start**. The preview uses `Provider.connect`, foreground detection and `Device.peek`. It reads the game already on screen and uses the selected build with an empty run history. For shops it describes policy. For Party Expedition it recognizes the main screens. The preview and runner are mutually exclusive. Messages are available in Portuguese, Spanish and English.

Validation uses screenshot fixtures, replays and Tk tests. Spanish captures for the newer named events and live gameplay validation remain pending.
