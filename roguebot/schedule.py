"""Routine deadlines from observed availability, not guessed server resets."""

from dataclasses import dataclass, field
import re


def refresh_seconds(texts) -> int | None:
    for text in texts:
        if not re.search(r"refreshes in|se actualiza en|opens in|abre en|atualiza em|renova em|abre em", text.norm):
            continue
        parts = re.findall(r"(\d+)\s*([dhms])", text.norm)
        if parts:
            return sum(int(n) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit] for n, unit in parts)
    return None


@dataclass
class RoutineSchedule:
    due_at: dict[str, float] = field(default_factory=dict)
    default_poll: float = 1800.

    def observe(self, part: str, now: float, *, count=None, cap=None, refresh=None, available=True):
        if not available:
            self.due_at[part] = now + 6 * 3600
        elif count is not None and count > 0:
            self.due_at[part] = now  # full counters remain urgent
        else:
            self.due_at[part] = now + (refresh if refresh is not None else self.default_poll)

    def due(self, now: float) -> tuple[str, ...]:
        return tuple(name for name, deadline in self.due_at.items() if deadline <= now)
