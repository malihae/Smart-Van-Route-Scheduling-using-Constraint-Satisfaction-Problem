"""
model.py
--------
Data model for the "Smart Van & Route Scheduling using CSP" project.

A route must be assigned a (van, driver, start_time) triple such that:
  - the van's capacity covers the route's passengers
  - the van's fuel range covers the route's distance
  - the start_time (+ duration) fits inside the route's allowed time window
  - the assigned driver is available at that time
  - (checked globally, not per-value) no van/driver double-books overlapping
    routes, and no driver exceeds their daily working-hour limit
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Dict


@dataclass
class Van:
    id: str
    capacity: int
    fuel_range_km: int


@dataclass
class Driver:
    id: str
    max_hours_per_day: float          # in hours
    available_from: int               # minutes after midnight
    available_to: int                 # minutes after midnight


@dataclass
class Route:
    id: str
    passengers: int
    distance_km: int
    duration_min: int
    window_start: int                 # earliest allowed start (minutes)
    window_end: int                   # latest allowed finish (minutes)
    # candidate start times inside the window, e.g. every 15 minutes
    time_step: int = 15

    def candidate_start_times(self) -> List[int]:
        times = []
        t = self.window_start
        while t + self.duration_min <= self.window_end:
            times.append(t)
            t += self.time_step
        return times


Assignment = Tuple[str, str, int]  # (van_id, driver_id, start_time)


def overlaps(start1: int, dur1: int, start2: int, dur2: int) -> bool:
    end1, end2 = start1 + dur1, start2 + dur2
    return start1 < end2 and start2 < end1


def minutes_to_hhmm(m: int) -> str:
    h, mm = divmod(m, 60)
    period = "AM" if h < 12 else "PM"
    h12 = h % 12
    if h12 == 0:
        h12 = 12
    return f"{h12:02d}:{mm:02d} {period}"
