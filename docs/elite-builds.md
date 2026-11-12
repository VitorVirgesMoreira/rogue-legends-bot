# Elite stage builds

The bot reads **Level Modifiers** in the preview before tapping Start. The selected build stays the basis for skill decisions, with tactical responses based on the cards shown for the current stage.

| Modifier | Decision |
| --- | --- |
| Vampiric Monsters | Take legendary or mythic Dispel as soon as it appears to counter enemy healing. |
| Unkillable | Take legendary or mythic Dispel as soon as it appears to counter enemy shields. |
| Anti-Heal | Prefer shields, DEF and maximum HP to passive healing for support. Direct healing remains an emergency action at 25% HP or less. |
| Weakpoints | Add protection after establishing the primary damage source. |
| No Time To Rest | Look for protection or passive recovery. |
| No Time To Study | Choose Rest if it is the only enabled central option, even at full HP. Upgrade through cards and shops. |
| Adaptive Armor | Favor critical hit and ATK bonuses after establishing the build. Avoid opening a secondary Shuriken family that adds many small hits. |
| Hard Shell | Prefer recurring damage over effects that only apply when combat opens. |
| Berserk Enemies / Rising Omen | Favor immediate damage over slow growth or delayed activation. |
| Inflated Prices | Keep skills ahead of stats and increase the early reserve. Release it near the final boss. See the [shop policy](shops.md). |
| Narrow Minded | Read the actual card count and keep the build focused with smaller offers. |
| Prison Lockdown | Recognize the board effect and retain the current build. |
| Stronger Monsters! | Recognize the higher difficulty and keep the responses to the specific effects. |

Legendary or mythic Dispel can take priority from the first choice when an enemy has healing or shields. It can use the early shop reserve and ranks ahead of other skills, rerolls and stats. Emergency healing still comes first. After acquiring that response the bot returns to the main build. A previously learned common version does not satisfy the legendary or mythic counter.

Other support responses come after two main-line choices. One skill family per tactical priority is enough before returning to damage upgrades. The periodic support setting still applies. A mandatory off-line pick can fill an offer without changing the build's focus.

Modifier rules survive recovery of an interrupted run and reset for the next stage. A resumed Elite run can open the board's **Level Modifiers** icon if it missed the preview. Unknown cards are logged without assigning an effect. Known names tolerate joined words and hyphen variations in OCR.

## Validation

Elite previews 18–23 were inspected in the emulator alongside user-supplied screenshots. The game returned to the Normal lobby with energy at **36/36**. Fixtures cover all three modifier cards, consecutive choices, support limits, shops, recovery and a campfire with training disabled. The combat effect of the heuristics awaits live runs.

Party Expedition uses its own role policy. Its result reader recognizes the reward screen with OCR text `Stage 19cleared!`, claims the reward and allows stage 20 to proceed. A replay exercises that captured screen.
