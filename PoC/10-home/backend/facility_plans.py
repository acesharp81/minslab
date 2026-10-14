"""Reviewed opening plans. Dates are plans, never proof that a facility opened."""
import json
from pathlib import Path

CATALOGUE = Path(__file__).with_name('facility_plans.json')


def nearby_plans(latitude, longitude, distance, radius=3500, district_key=None):
    catalogue = json.loads(CATALOGUE.read_text())
    items = []
    for record in catalogue['items']:
        if record.get('latitude') is None or record.get('longitude') is None:
            if district_key and record.get('district_key') == district_key:
                items.append(dict(record, distance_m=None, service_status='PLANNED', category='개원 예정 · 위치 미연계'))
            continue
        metres = distance(latitude, longitude, record['latitude'], record['longitude'])
        if metres <= radius:
            items.append(dict(record, distance_m=metres, service_status='PLANNED',
                              category='개교 예정' if record['kind'] == 'school' else '개원 예정'))
    return sorted(items, key=lambda r: (r['distance_m'] if r['distance_m'] is not None else float('inf'), r['id'])), catalogue['coverage_note']
