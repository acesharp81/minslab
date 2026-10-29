from datetime import date
def parse_notice_date(value):
    try:
        parts=value.split("-")
        return date(*map(int,parts)).isoformat()
    except Exception:
        return None

