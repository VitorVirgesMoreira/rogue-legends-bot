# Guide-based improvements

The reference snapshot uses [28 Rogue HQ guides](https://rogue.desoware.com/guides) and public build previews consulted on November 3, 2026. The primary snapshot covers **0.630**. Some hero, companion and raid guides describe earlier versions.

| Area | Behavior |
| --- | --- |
| Skills | Covers 201 canonical families, including 24 from Party Expedition. Ten numbered upgrades share their base families. Card level, tree requirements, exclusions, drawbacks and triggers are stored independently of OCR. Reviewed catalog tags with `auto=false` are retained. |
| Sources | Distinguishes Bolt from Bolts, Shuriken sources, weapon attacks, ultimates, received damage and status effects. Avoids amplifiers without a known source and swaps that remove a build's main trigger. |
| Builds | Includes fire and critical hit, burn, combo, counter, slash, pet, ultimate and skill strategies informed by equipment. Catalog lookups use the current card version. |
| Modes | Dojo avoids skills that depend on taking hits or fighting a boss. Raid accounts for true damage and ineffective defense. Both avoid kill-dependent skills. |
| Shop | Prioritizes compatibility before value per coin, confirms spending, saves for future offers and permits emergency healing. |
| Account | Shows equipment, strategy, history and progression. Stores the observed or entered loadout, stats and game version. |
| Party | Considers prior role choices, healing or shields before Generosity, explicit team state and reachable campfires when HP is low. A completed expedition ends matchmaking. |
| History | Stores up to 2,000 local runs with duration, result, choices, modifiers and equipment. It separates different configurations and uses observed reward samples. |
| Farming | The explicit farm option requires three comparable runs with at least an 80% win rate for a recommendation. It steps down after two losses on one stage and stops if stage 1 remains unwinnable. |
| Routine | Revisits activities at observed deadlines while waiting for energy. Claims eligible rewards on recognized quest, carnival and album pages. |
| Progression | Recommends unlocks, trees, global milestones, awakenings, runes, equipment, companions, mounts, sentinels, artifacts and pet builds with known costs and balances. |

Reference pages include [skills](https://rogue.desoware.com/guide/skills), [skill links](https://rogue.desoware.com/guide/skill-links), [damage types](https://rogue.desoware.com/guide/damage-types), [triggers](https://rogue.desoware.com/guide/definitions), the [damage formula](https://rogue.desoware.com/guide/damage-formula), [Dojo](https://rogue.desoware.com/guide/dojo) and [Guild Raid](https://rogue.desoware.com/guide/guild-raid).

## Portuguese recognition and validation

Game and window languages are independent. Portuguese game labels cover navigation, combat, skill choices, shops, energy, events and routine activities. Skill aliases resolve to the same canonical families.

Real screenshots cover the Elite lobby, star list, modes, daily login, Expedition menus and completion, three Skill Codex tabs, and Conquest outside its season. They include line wraps, **Estelar**, **Torre de Desafios**, **Parear** and the observed skill names. Live Portuguese combat validation remains pending.

The original implementation passed 1,061 tests covering OCR, triggers, versions, economics, farming and persistence. Menu inspection kept energy at 71. Tk tests covered window creation, layout structure and persistence.

## Limits

- Chaos Realm and Guild Conquest are inspection modes. Their tested path, modifier and target policies need real active screens before automatic fights can be enabled. The observed Conquest screen showed **Temporada Encerrada**. See [Chaos Realm](https://rogue.desoware.com/guide/chaos-realm) and [Guild Conquest](https://rogue.desoware.com/guide/guild-conquest).
- Enter the actual game version in Equipment. Inference from the guide snapshot uses the versioned effects in the reference data. Only explicitly recorded values contribute to numeric estimates.
- Use equipment names from the guides. Other items accept values such as `Name:epic` and `Name:legendary`. Enter rates as fractions such as `combo_rate=0.3`. Leave unknown values blank.
- Journal farming uses comparable observed rewards. With insufficient samples it starts from the last beaten stage and tracks losses.
- The collector visits recognized, visible reward entries. These guide features belong to the desktop emulator implementation.
