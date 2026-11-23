import re
from typing import List, Dict, Any, Tuple, Optional

def parse_time_minutes(t_str: str) -> Optional[int]:
    """Parses HH:MM string to integer minutes from midnight."""
    if not t_str:
        return None
    t_str = t_str.strip()
    m = re.match(r"^(\d{1,2}):(\d{2})", t_str)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        return h * 60 + mn
    return None

def minutes_to_hhmm(mins: int) -> str:
    """Formats minutes from midnight to HH:MM (supports 24:00)."""
    if mins == 1440:
        return "24:00"
    h = (mins // 60) % 24
    mn = mins % 60
    return f"{h:02d}:{mn:02d}"

def calculate_duration(t_from: str, t_to: str) -> float:
    """Calculates duration in decimal hours between two time strings."""
    m_from = parse_time_minutes(t_from)
    m_to = 1440 if t_to in ("24:00", "24") else parse_time_minutes(t_to)
    
    if m_from is None or m_to is None:
        return 0.0
    
    if m_to < m_from:
        # Crosses midnight (e.g. 23:00 to 01:00)
        m_to += 1440
        
    diff = m_to - m_from
    return round(diff / 60.0, 2)

def parse_raw_timeline(text: str) -> Dict[str, Any]:
    """
    MASTER CHRONOLOGY & 24H RECONCILIATION ENGINE
    (Agent: chronology-time-reconciliation-auditor)
    
    Intelligently audits and reconciles petroleum operational timelines:
    1. Interval Mode: 'HH:MM - HH:MM: Operation' or multi-line under 'HH:MM - HH:MM'
    2. Sequential Point-in-Time Mode: 'HH:MM Operation' where end time is the start of next activity!
    3. Multi-line consolidation: Groups subsequent notes and bullets under their active hour block.
    4. Chronological Gap Detection: Identifies unaccounted dead hours between activities.
    5. 24.0h Balance Verification: Checks if full 24h operational day is closed.
    """
    lines = text.strip().split("\n")
    
    interval_regex = re.compile(r"^(\d{1,2}:\d{2})\s*(?:[-–]|a|to)\s*(\d{1,2}:\d{2})[:\s]*(.*)$", re.IGNORECASE)
    single_time_regex = re.compile(r"^(\d{1,2}:\d{2})[:\s]*(.*)$")
    
    raw_blocks: List[Dict[str, Any]] = []
    current_block: Optional[Dict[str, Any]] = None
    
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.upper().startswith("DATE") or line.upper().startswith("FROM"):
            continue
            
        m_int = interval_regex.match(line)
        if m_int:
            t_start, t_end, rest = m_int.groups()
            current_block = {
                "type": "interval",
                "start": t_start,
                "end": t_end,
                "lines": [rest.strip()] if rest.strip() else []
            }
            raw_blocks.append(current_block)
            continue
            
        m_single = single_time_regex.match(line)
        if m_single:
            t_start, rest = m_single.groups()
            current_block = {
                "type": "single",
                "start": t_start,
                "end": None,
                "lines": [rest.strip()] if rest.strip() else []
            }
            raw_blocks.append(current_block)
            continue
            
        # Multiline notes belonging to current block
        if current_block:
            current_block["lines"].append(line)
        else:
            # Content before any timestamp! (e.g. "Personal toma de alimentos")
            current_block = {
                "type": "no_time",
                "start": "00:00",
                "end": None,
                "lines": [line]
            }
            raw_blocks.append(current_block)
            
    # Process blocks, infer missing end times, calculate durations and detect gaps
    events = []
    total_duration = 0.0
    gaps = []
    
    for i, b in enumerate(raw_blocks):
        t_start = b["start"]
        t_end = b.get("end")
        desc = " ".join([l for l in b["lines"] if l]).strip()
        
        # If no end time, infer from the next activity's start time!
        if not t_end:
            if i + 1 < len(raw_blocks):
                t_end = raw_blocks[i + 1]["start"]
            else:
                # Last event of shift
                t_end = "24:00"
                
        dur = calculate_duration(t_start, t_end)
        total_duration += dur
        
        events.append({
            "id": i + 1,
            "from": t_start,
            "to": t_end,
            "duration": dur,
            "description": desc,
            "raw": f"{t_start} - {t_end}: {desc}"
        })
        
        # Detect gaps between current end time and next start time
        if i + 1 < len(raw_blocks):
            next_start = raw_blocks[i + 1]["start"]
            m_curr_end = 1440 if t_end == "24:00" else parse_time_minutes(t_end)
            m_next_start = parse_time_minutes(next_start)
            if m_curr_end is not None and m_next_start is not None and m_next_start > m_curr_end:
                gap_hrs = round((m_next_start - m_curr_end) / 60.0, 2)
                gaps.append({
                    "from": t_end,
                    "to": next_start,
                    "gap_hours": gap_hrs
                })

    is_24_closed = abs(total_duration - 24.0) < 0.15
    balance_status = "BALANCED" if is_24_closed else ("UNDER" if total_duration < 24.0 else "OVER")
    
    # Reconstruct standard IADC formatted narrative
    reconstructed_lines = []
    for ev in events:
        if ev["description"]:
            reconstructed_lines.append(f"{ev['from']} - {ev['to']}: {ev['description']}")
            
    reconstructed_narrative = "\n".join(reconstructed_lines)

    return {
        "events": events,
        "total_duration": round(total_duration, 2),
        "is_24_closed": is_24_closed,
        "balance_status": balance_status,
        "variance_hours": round(24.0 - total_duration, 2),
        "gaps": gaps,
        "mode": "sequential_inferred" if any(b["type"] == "single" for b in raw_blocks) else "interval_explicit",
        "reconstructed_narrative": reconstructed_narrative
    }
