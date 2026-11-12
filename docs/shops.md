# Shop purchases

The shop evaluates actions in this order.

1. Emergency healing at 25% HP or less.
2. Skills that support the current build or counter stage modifiers.
3. A free reroll, then paid rerolls costing at most **10 coins per tap**, when no build skill is affordable.
4. Other compatible damage or survival skills.
5. ATK, DEF or maximum HP upgrades.

Inflated Prices keeps skills ahead of stats. Legendary or mythic rarity alone does not make a foreign element useful. With Vampiric Monsters or Unkillable, legendary or mythic Dispel takes priority over other skills and can use the reserve. After learning it, the build returns to its main line.

The bot reads the price before each reroll and uses each price once per visit. A free → 5 → 10 → 20 sequence stops at 10. Paid rerolls must leave enough for a plausible skill. Unreadable prices and premium currency mentions block rerolls.

Purchases and paid rerolls require a matching balance drop. With Inflated Prices, a purchase may differ by one coin if two reads confirm the same lower balance. A free reroll requires the same balance and a change to the offer or readable reroll price. The bot waits for up to five reads and exits the visit if the action remains unconfirmed. A new offer can contain an upgrade to a skill already purchased in that visit.

## Reserve and final boss

Earlier shops use only the amount above the reserve for optional skills and stats. The starting reserve is **190 coins**, or **285** with Inflated Prices. A higher observed legendary or mythic price raises the reserve for later shops. Core skills and emergency healing can use that balance.

Near the final boss, the bot releases the reserve for useful purchases. It uses the board's roll counter, including a reading just before the shop opened. For a 30-roll stage, the final window starts at **25/30**. At 9/30 and 19/30 the reserve stays in place. An unreadable counter also keeps the reserve. The log records the progress and recovery keeps it for the current run.

## Validation

Fixtures cover the free and 10-coin prices and the board counter. Replays cover purchase order, rerolls, savings for rare cards, final-window spending, stock, delayed readings and unconfirmed actions. Live validation of the final shopping window remains pending.
