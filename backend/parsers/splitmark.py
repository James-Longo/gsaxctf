"""
splitmark.py - spreadsheet results with the mark split over two columns.

Telstar (2010-2011) and Cheverus (2011) posted one sheet per meet and sex:

    Place Athlete                  Team       Event        Min/Ft Sec/Inchs   Points
      1 LaChancee, Patrick          StD     Racewalk            9 04.0          8
      1 Taylor, Zach                MtV     100 Dash                 11.7        8
      1 Torres, Jordan              Lis     400 Dash            0 55.8          8
      1 Bushey,Torres,Grover,Haley  Lis     1600 Relay          3 54.8          8
      3 Kwan, John                  StD     Long Jump          16 04.5          4

The generic parsers took the seconds column for the mark and lost the
minutes and feet ("9 04.0" stored as "04.0"), and read the event column as
names. Here a mark is minutes:seconds (or seconds) for a race and
feet-inches for a field event; empty places ("8   Racewalk") are skipped.
"""

import re

from .base import BaseParser

ROW = re.compile(
    r'^\s*(?P<place>\d{1,3})\s+(?P<name>\S.*?)\s{2,}(?P<team>[A-Za-z.\'&]{1,6})\s+'
    r'(?P<event>(?:\d{2,5}\s+)?[A-Za-z][A-Za-z ]*?)\s+'
    r'(?:(?P<a>\d{1,3})\s+)?(?P<b>\d{1,2}(?:\.\d{1,2})?)(?:\s+(?P<pts>\d{1,2}(?:\.\d{1,2})?))?\s*$')
FIELD = re.compile(r'jump|vault|put|throw|discus|javelin|shot', re.I)
EVENT_NAMES = {
    'racewalk': '1600 Meter Race Walk', 'race walk': '1600 Meter Race Walk',
}


def _event(raw):
    e = re.sub(r'\s+', ' ', raw).strip()
    if e.lower() in EVENT_NAMES:
        return EVENT_NAMES[e.lower()]
    m = re.match(r'(\d{2,5}) (Dash|Run|Hurdles)$', e, re.I)
    if m:
        return f'{m.group(1)} Meter {m.group(2).title()}'
    m = re.match(r'(\d{3,4}) Relay$', e, re.I)
    if m:                       # "1600 Relay" = 4x400
        return f'4x{int(m.group(1)) // 4} Meter Relay'
    return e


class SplitMarkParser(BaseParser):

    @staticmethod
    def matches(text):
        head = re.sub(r'<[^>]+>', ' ', text[:5000])
        return bool(re.search(r'Min\s*/\s*Ft', head, re.I) and re.search(r'Sec\s*/\s*Inch', head, re.I))

    def parse(self, text, meet_url, season_type):
        gender = 'Girls' if re.search(r'girl', meet_url or '', re.I) else \
            'Boys' if re.search(r'boy', meet_url or '', re.I) else ''
        events = {}
        for line in re.sub(r'<[^>]+>', ' ', text).splitlines():
            m = ROW.match(line)
            if not m:
                continue
            ev = _event(m.group('event'))
            a, b = m.group('a'), m.group('b')
            field = bool(FIELD.search(ev))
            if field:
                if a is None:
                    continue
                ins = b if '.' in b else b + '.00'
                mark = f'{int(a)}-{float(ins):05.2f}'
            elif a and int(a) > 0:
                mark = f'{int(a)}:{b if len(b.split(".")[0]) == 2 else "0" + b}'
            else:
                mark = b
            relay = 'Relay' in ev
            name = re.sub(r'\s+', ' ', m.group('name')).strip()
            e = events.setdefault(ev, {'event': ev, 'gender': gender, 'is_relay': relay, 'results': []})
            row = {'school': m.group('team'), 'result': mark, 'type': 'Finals',
                   'place': int(m.group('place'))}
            if m.group('pts'):
                row['points'] = float(m.group('pts'))
            if relay:
                row['athletes'] = [x.strip() for x in name.split(',') if x.strip()]
            else:
                row['athlete'] = name
                row['grade'] = ''
            e['results'].append(row)
        return {'events': list(events.values()), 'date': None, 'team_rankings': []}
