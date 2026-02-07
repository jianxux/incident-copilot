"""Maintenance Windows - Scheduler with RRULE support and iCal export"""
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
from dataclasses import dataclass
from .models import MaintenanceWindow, MaintenanceSchedule, MaintenanceStatus, ScopeType


@dataclass
class RecurrenceInstance:
    parent_id: UUID
    start_time: datetime
    end_time: datetime
    instance_number: int


class MaintenanceScheduler:
    """Scheduler for recurring maintenance windows using RRULE patterns."""
    
    def parse_rrule(self, rrule: str) -> dict:
        parts = {}
        for component in rrule.replace("RRULE:", "").split(";"):
            if "=" in component:
                k, v = component.split("=", 1)
                parts[k.upper()] = v
        return parts
    
    def get_next_occurrences(self, schedule: MaintenanceSchedule, from_time: Optional[datetime] = None, count: int = 10) -> list[RecurrenceInstance]:
        if not schedule.is_recurring or not schedule.rrule:
            return []
        from_time = from_time or datetime.utcnow()
        duration, occurrences = schedule.duration, []
        parts = self.parse_rrule(schedule.rrule)
        freq, interval = parts.get("FREQ", "WEEKLY"), int(parts.get("INTERVAL", "1"))
        byday = parts.get("BYDAY", "").split(",") if "BYDAY" in parts else []
        count_limit = int(parts.get("COUNT", "999"))
        until = datetime.strptime(parts["UNTIL"][:8], "%Y%m%d") if "UNTIL" in parts else schedule.recurrence_end
        
        current, inst = schedule.start_time, 0
        while len(occurrences) < count and inst < count_limit:
            if until and current > until:
                break
            if self._match_byday(current, byday) and current >= from_time:
                occurrences.append(RecurrenceInstance(UUID(int=0), current, current + duration, inst))
            current = self._advance(current, freq, interval)
            inst += 1
            if inst > 1000:
                break
        return occurrences
    
    def _match_byday(self, dt: datetime, byday: list[str]) -> bool:
        if not byday or byday == [""]:
            return True
        weekdays = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
        return weekdays[dt.weekday()] in byday
    
    def _advance(self, dt: datetime, freq: str, interval: int) -> datetime:
        if freq == "DAILY":
            return dt + timedelta(days=interval)
        elif freq == "WEEKLY":
            return dt + timedelta(weeks=interval)
        elif freq == "MONTHLY":
            y, m = dt.year, dt.month + interval
            while m > 12:
                m, y = m - 12, y + 1
            try:
                return dt.replace(year=y, month=m)
            except ValueError:
                return dt.replace(year=y, month=m, day=28)
        return dt + timedelta(days=interval)
    
    def get_occurrence_at(self, schedule: MaintenanceSchedule, target: datetime) -> Optional[RecurrenceInstance]:
        if not schedule.is_recurring:
            if schedule.start_time <= target <= schedule.end_time:
                return RecurrenceInstance(UUID(int=0), schedule.start_time, schedule.end_time, 0)
            return None
        for occ in self.get_next_occurrences(schedule, target - schedule.duration - timedelta(days=1), 5):
            if occ.start_time <= target <= occ.end_time:
                return occ
        return None
    
    def generate_ical_event(self, window: MaintenanceWindow) -> str:
        esc = lambda t: t.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")
        lines = [
            "BEGIN:VEVENT", f"UID:{window.id}@maintenance",
            f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART:{window.schedule.start_time.strftime('%Y%m%dT%H%M%SZ')}",
            f"DTEND:{window.schedule.end_time.strftime('%Y%m%dT%H%M%SZ')}",
            f"SUMMARY:{esc(window.title)}",
        ]
        if window.description:
            lines.append(f"DESCRIPTION:{esc(window.description)}")
        if window.schedule.is_recurring and window.schedule.rrule:
            lines.append(f"RRULE:{window.schedule.rrule}")
        lines.append("END:VEVENT")
        return "\r\n".join(lines)
    
    def generate_ical_calendar(self, windows: list[MaintenanceWindow]) -> str:
        header = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Incident Copilot//Maintenance//EN",
                  "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Maintenance Windows"]
        return "\r\n".join(header + [self.generate_ical_event(w) for w in windows] + ["END:VCALENDAR"])
    
    def validate_schedule(self, schedule: MaintenanceSchedule) -> list[str]:
        warnings = []
        if schedule.duration > timedelta(hours=24):
            warnings.append("Window exceeds 24 hours")
        if schedule.duration < timedelta(minutes=5):
            warnings.append("Window less than 5 minutes")
        if schedule.start_time < datetime.utcnow():
            warnings.append("Start time in past")
        if schedule.is_recurring:
            if not schedule.rrule:
                warnings.append("Missing RRULE")
            elif "FREQ" not in self.parse_rrule(schedule.rrule):
                warnings.append("RRULE missing FREQ")
            if "COUNT" not in (self.parse_rrule(schedule.rrule) if schedule.rrule else {}) and not schedule.recurrence_end:
                warnings.append("Recurring has no end")
        return warnings
    
    def next_maintenance_for(self, windows: list[MaintenanceWindow], scope_type: Optional[str] = None, 
                              identifier: Optional[str] = None) -> Optional[tuple[MaintenanceWindow, datetime]]:
        now, result = datetime.utcnow(), None
        for w in windows:
            if w.status in (MaintenanceStatus.CANCELLED, MaintenanceStatus.COMPLETED):
                continue
            if scope_type and identifier and not w.scope.matches(ScopeType(scope_type), identifier):
                continue
            start = self.get_next_occurrences(w.schedule, now, 1)[0].start_time if w.schedule.is_recurring else w.schedule.start_time
            if start < now:
                continue
            if not result or start < result[1]:
                result = (w, start)
        return result
