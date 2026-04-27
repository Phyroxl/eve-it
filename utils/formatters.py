from datetime import timedelta

def format_isk(v, short=False):
    v = int(v)
    if short:
        if v >= 1e9: return f"{v/1e9:.2f}B"
        if v >= 1e6: return f"{v/1e6:.2f}M"
        if v >= 1e3: return f"{v/1e3:.1f}K"
    return f"{v:,}"

def format_duration(td):
    if td is None: return "00:00:00"
    s = int(td.total_seconds())
    s = max(0, s)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"