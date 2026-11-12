# Missing stars and events

**Missing stars** looks for beaten stages with fewer than three stars. The search starts at the end of the list and moves toward earlier stages once the visible stages are complete. After each run it checks the stars again, so an incomplete stage can be selected repeatedly.

Earned stars are gold in Normal and purple in Elite. The older reader missed purple stars and reported Elite 23 as 0/3. Both colors now count as earned, and grey stars count as missing. Unreadable counts are checked again. A failed scan leaves completion unknown.

Menu validation passed completed Elite stages 22 and 23, found **stage 21 with 2/3 stars**, and opened its preview. Start was blocked during that check and energy stayed at **86**.

## Recognized events

- **Goblin hut.** Attempt loot up to three times per visit. Confirm that the coin balance increased before trying again. Leave after five seconds without confirmation. At 25% HP or less, avoid an additional fight.
- **HP for a legendary skill.** Attempt once per visit when the reward and HP cost are readable and more than 25% HP would remain. Use current HP as the base when the option says so explicitly. Otherwise use maximum HP. An unreadable cost or a premium currency mention makes the bot leave.
- **Healing and rest.** Heal at 25% HP or less when alternatives are available. Rest when it is the only enabled option at a campfire with training disabled.

Two events reported at 16:07 had no saved screenshots. Replay tests cover repeated attempts, disabled options and low HP. The exact text and costs in those menus await another sighting.

The last **40 event decisions** are saved in `debug/events`. Each includes a PNG and a JSON record with the title, OCR text, HP, chosen point and reason. The log records the capture path before the tap. Older records are removed to bound disk use.
