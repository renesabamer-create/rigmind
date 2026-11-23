import re
from datetime import datetime, timedelta

def parse_time_str(t_str: str):
    """Parses HH:MM or HH:MM:SS string to minutes from midnight."""
    t_str = t_str.strip()
    parts = t_str.split(":")
    if len(parts) >= 2:
        h = int(parts[0])
        m = int(parts[1])
        return h * 60 + m
    return None

def format_minutes_to_time(minutes: int) -> str:
    """Formats minutes from midnight to HH:MM."""
    h = (minutes // 60) % 24
    m = minutes % 60
    return f"{h:02d}:{m:02d}"

def parse_raw_timeline(text: str):
    """
    Parses field text lines. Supports formats like:
    - DATE \\t FROM \\t TO \\t DUR \\t OPERATION
    - HH:MM - HH:MM: OPERATION
    - HH:MM \\t HH:MM \\t OPERATION
    """
    lines = text.strip().split("\n")
    events = []
    total_duration = 0.0
    
    # Pattern 1: Tab-separated table (DATE, FROM, TO, DUR, OPERATION)
    tab_pattern = re.compile(r"^(\d{1,2}/\d{1,2}/\d{4})?\s*(\d{1,2}:\d{2}(?::\d{2})?)\s+(\d{1,2}:\d{2}(?::\d{2})?)\s+([\d.]+)?\s*(.*)$")
    # Pattern 2: Interval with dash (07:00 - 08:30: Description)
    dash_pattern = re.compile(r"^(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})[:\s]*(.*)$")
    
    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line or line.upper().startswith("DATE") or line.upper().startswith("FROM"):
            continue
            
        m_dash = dash_pattern.match(line)
        if m_dash:
            t_from, t_to, desc = m_dash.groups()
            dur = calculate_duration(t_from, t_to)
            events.append({
                "id": idx + 1,
                "from": t_from,
                "to": t_to,
                "duration": dur,
                "description": desc.strip(),
                "raw": line
            })
            total_duration += dur
            continue
            
        # Try tab or multi-space splitting
        parts = [p.strip() for p in re.split(r"\t+|\s{2,}", line) if p.strip()]
        if len(parts) >= 3:
            # Check if first or second is a time
            date_part = ""
            start_idx = 0
            if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", parts[0]):
                date_part = parts[0]
                start_idx = 1
                
            if len(parts) > start_idx + 1 and re.match(r"^\d{1,2}:\d{2}", parts[start_idx]) and re.match(r"^\d{1,2}:\d{2}", parts[start_idx+1]):
                t_from = parts[start_idx]
                t_to = parts[start_idx+1]
                dur_val = None
                desc = ""
                if len(parts) > start_idx + 2:
                    try:
                        dur_val = float(parts[start_idx+2].replace(",", "."))
                        desc = " ".join(parts[start_idx+3:]) if len(parts) > start_idx + 3 else ""
                    except ValueError:
                        desc = " ".join(parts[start_idx+2:])
                        dur_val = calculate_duration(t_from, t_to)
                else:
                    dur_val = calculate_duration(t_from, t_to)
                    
                events.append({
                    "id": idx + 1,
                    "date": date_part,
                    "from": t_from,
                    "to": t_to,
                    "duration": dur_val,
                    "description": desc,
                    "raw": line
                })
                total_duration += dur_val
                continue

        # Fallback: line without explicit time tags
        events.append({
            "id": idx + 1,
            "from": "",
            "to": "",
            "duration": 0.0,
            "description": line,
            "raw": line
        })

    is_24_closed = abs(total_duration - 24.0) < 0.15
    balance_status = "BALANCED" if is_24_closed else ("UNDER" if total_duration < 24.0 else "OVER")

    return {
        "events": events,
        "total_duration": round(total_duration, 2),
        "is_24_closed": is_24_closed,
        "balance_status": balance_status,
        "variance_hours": round(24.0 - total_duration, 2)
    }

def calculate_duration(t_from: str, t_to: str) -> float:
    """Calculates duration in decimal hours between two time strings."""
    m_from = parse_time_str(t_from)
    m_to = parse_time_str(t_to)
    if m_from is None or m_to is None:
        return 0.0
    
    if m_to == 0 and m_from > 0:
        # e.g., 23:00 to 0:00 or 24:00
        m_to = 24 * 60
    elif m_to < m_from:
        # Passes midnight
        m_to += 24 * 60
        
    diff = m_to - m_from
    return round(diff / 60.0, 2)
