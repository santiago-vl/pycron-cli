"""Cron expression parser.

Supported subset:
- "*/N * * * *" -> StartInterval (every N minutes)
- "M H * * DOW" -> StartCalendarInterval
  - M: minute (0-59, single value only)
  - H: hour (single, list, or range with step)
  - DOW: day of week (0-6, single, list, or range)
  - dom and mon MUST be "*"
"""

from dataclasses import dataclass


class CronParseError(Exception):
    pass


@dataclass
class StartInterval:
    seconds: int


@dataclass
class CalendarEntry:
    minute: int
    hour: int
    weekday: int | None = None


@dataclass
class StartCalendarInterval:
    entries: list[CalendarEntry]


ParsedCron = StartInterval | StartCalendarInterval


def _parse_field(field: str, min_val: int, max_val: int, field_name: str) -> list[int]:
    if field == "*":
        return list(range(min_val, max_val + 1))

    if field.startswith("*/"):
        step = int(field[2:])
        if step <= 0:
            raise CronParseError(f"Step must be positive: {field}")
        return list(range(min_val, max_val + 1, step))

    if "/" in field:
        range_part, step_str = field.split("/", 1)
        step = int(step_str)
        if step <= 0:
            raise CronParseError(f"Step must be positive: {field}")
        if "-" not in range_part:
            raise CronParseError(f"Invalid step syntax: {field}")
        start, end = map(int, range_part.split("-", 1))
        if start < min_val or end > max_val or start > end:
            raise CronParseError(f"Range out of bounds: {field}")
        return list(range(start, end + 1, step))

    if "," in field:
        values = []
        for part in field.split(","):
            part = part.strip()
            if "-" in part:
                start, end = map(int, part.split("-", 1))
                if start < min_val or end > max_val or start > end:
                    raise CronParseError(f"Range out of bounds: {part}")
                values.extend(range(start, end + 1))
            else:
                val = int(part)
                if val < min_val or val > max_val:
                    raise CronParseError(f"Value out of bounds: {val}")
                values.append(val)
        return sorted(set(values))

    if "-" in field:
        start, end = map(int, field.split("-", 1))
        if start < min_val or end > max_val or start > end:
            raise CronParseError(f"Range out of bounds: {field}")
        return list(range(start, end + 1))

    val = int(field)
    if val < min_val or val > max_val:
        raise CronParseError(f"Value out of bounds: {val}")
    return [val]


def parse_cron(expression: str) -> ParsedCron:
    parts = expression.split()
    if len(parts) != 5:
        raise CronParseError(f"Expected 5 fields, got {len(parts)}")

    minute_f, hour_f, dom_f, mon_f, dow_f = parts

    if dom_f != "*":
        raise CronParseError("Day of month must be '*'")
    if mon_f != "*":
        raise CronParseError("Month must be '*'")

    # Interval pattern: */N * * * *
    if minute_f.startswith("*/") and hour_f == "*" and dow_f == "*":
        interval = int(minute_f[2:])
        if interval <= 0:
            raise CronParseError("Interval must be positive")
        return StartInterval(seconds=interval * 60)

    # Calendar pattern
    if minute_f == "*" or "," in minute_f or "-" in minute_f or "/" in minute_f:
        raise CronParseError("Minute must be a single value (0-59) for calendar schedules")

    minute = int(minute_f)
    if minute < 0 or minute > 59:
        raise CronParseError(f"Minute must be 0-59, got {minute}")

    hours = _parse_field(hour_f, 0, 23, "hour")
    weekdays: list[int | None] = [None] if dow_f == "*" else _parse_field(dow_f, 0, 6, "dow")  # type: ignore

    entries = [
        CalendarEntry(minute=minute, hour=h, weekday=w)
        for h in hours
        for w in weekdays
    ]
    return StartCalendarInterval(entries=entries)


def format_schedule(parsed: ParsedCron) -> str:
    if isinstance(parsed, StartInterval):
        mins = parsed.seconds // 60
        return "Every minute" if mins == 1 else f"Every {mins} minutes"

    entries = parsed.entries
    if len(entries) == 1:
        e = entries[0]
        time = f"{e.hour:02d}:{e.minute:02d}"
        if e.weekday is None:
            return f"Daily at {time}"
        days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        return f"{days[e.weekday]} at {time}"

    hours = sorted(set(e.hour for e in entries))
    minute = entries[0].minute
    times = ", ".join(f"{h:02d}:{minute:02d}" for h in hours)

    weekdays = set(e.weekday for e in entries)
    if None in weekdays:
        return f"Daily at {times}"

    days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    day_str = ", ".join(days[w] for w in sorted(weekdays) if w is not None)
    return f"At {times} on {day_str}"
