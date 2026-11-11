"""State-meet entrants with no qualifying mark on file: evidence of missing data.

usage: python3 -m backend.track_qualifiers [--season Outdoor] [--list YEAR] [--min N]

An MPA state entry needs a mark in that event earlier the same season, so a
state entrant (or relay team) with no such mark in the store means a meet is
missing, or the athlete's marks sit under another name or event. Each case
is classed:

  equivalent event    no mark in the event, one in its yard/metric twin (the
                      2005-13 leagues ran 40 yd, 45 yd hurdles, 300/600 yd,
                      4x220/4x880 yd; the state meet the metric events):
                      not a gap
  no season marks     the athlete has no marks at all before the state meet
  other events only   marks this season, none in this event
  marks dated after   the event's marks are dated after the state meet
  split identity      the same name in another catalog id has the mark
  entrant not matched the state row joined no catalog id
  team no relay mark  the school has no time in this relay before the meet

The summary prints the share of entrants without a mark per season year;
`--list YEAR` names the schools with the most gaps (the meets to look for).
Reads the track postseason store (backend/data/track_cache).
"""
import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend import track_postseason as tp  # noqa: E402


# state event -> the regular-season events that show the same ability
EQUIV = {
    '55 Meter Dash': ('40 Yard Dash', '45 Yard Dash', '50 Yard Dash', '55 Yard Dash', '60 Yard Dash',
                      '50 Meter Dash', '60 Meter Dash'),
    '55 Meter Hurdles': ('45 Yard Hurdles', '50 Yard Hurdles', '55 Yard Hurdles', '60 Yard Hurdles',
                         '60 Meter Hurdles'),
    '200 Meter Dash': ('150 Yard Dash', '200 Yard Dash', '220 Yard Dash', '240 Yard Dash'),
    '400 Meter Dash': ('300 Yard Dash', '400 Yard Dash', '440 Yard Dash', '300 Meter Dash'),
    '800 Meter Run': ('600 Yard Dash', '600 Meter Run', '880 Yard Run', '1000 Yard Run', '1000 Meter Run'),
    '1 Mile Run': ('1600 Meter Run', '1500 Meter Run'),
    '1600 Meter Run': ('1 Mile Run', '1500 Meter Run'),
    '2 Mile Run': ('3200 Meter Run', '3000 Meter Run'),
    '3200 Meter Run': ('2 Mile Run', '3000 Meter Run'),
    '4x200 Meter Relay': ('4x140 Yard Relay', '4x200 Yard Relay', '4x210 Yard Relay', '4x220 Yard Relay',
                          '4x280 Yard Relay'),
    '4x400 Meter Relay': ('4x400 Yard Relay', '4x410 Yard Relay', '4x440 Yard Relay'),
    '4x800 Meter Relay': ('4x880 Yard Relay',),
    '1600 Meter Race Walk': ('1 Mile Race Walk', '1600 Yard Race Walk'),
    '1 Mile Race Walk': ('1600 Meter Race Walk', '1600 Yard Race Walk'),
}


def _before(dates, d):
    return any(x < d for x in dates)


def _equiv(b, alt, ev, d):
    """A mark before d in an equivalent event, from the FAMILY marks b or the other events alt."""
    return any(_before(b.get(e, ([],))[0], d) or _before(alt.get(e, []), d) for e in EQUIV.get(ev, ()))


def gaps(store, champs, truth):
    """[row] for every state entrant, with its class ('ok' when a mark is on file)."""
    by_name = collections.defaultdict(set)
    for aid, nm in store.name.items():
        by_name[(tp.name_key(nm), store.gender.get(aid))].add(aid)
    out = []
    for c in champs:
        if c.get('kind') != 'state':
            continue
        blk = (tp.ay_of(c['year'], c['season']), tp.SEASON_OF[c['season']])
        d = c['date']
        for ev, rs in truth[c['id']]['events'].items():
            relay = tp.is_relay_event(ev)
            for place, r in enumerate(rs, 1):
                rec = dict(champ=c['id'], year=c['year'], season=c['season'], gender=c['gender'],
                           event=ev, place=place, unit=r['unit'], name=r['name'], mark=r['mark'], relay=relay)
                if relay:
                    b = store.relays.get((r['unit'], c['gender']), {}).get(blk, {})
                    alt = store.alt_relays.get((r['unit'], c['gender']), {}).get(blk, {})
                    rec['cls'] = ('ok' if _before(b.get(ev, ([],))[0], d) else
                                  'equivalent event' if _equiv(b, alt, ev, d) else 'team no relay mark')
                elif r['aid'] is None:
                    rec['cls'] = 'entrant not matched'
                else:
                    aid = r['aid']
                    b = store.marks.get(aid, {}).get(blk, {})
                    dates = b.get(ev, ([],))[0]
                    alt = store.alt.get(aid, {}).get(blk, {})
                    if _before(dates, d):
                        rec['cls'] = 'ok'
                    elif _equiv(b, alt, ev, d):
                        rec['cls'] = 'equivalent event'
                    elif any(a != aid and any(x < d for x in store.marks.get(a, {}).get(blk, {}).get(ev, ([],))[0])
                             for a in by_name[(tp.name_key(store.name.get(aid)), c['gender'])]):
                        rec['cls'] = 'split identity'
                    elif any(x > d for x in dates):
                        rec['cls'] = 'marks dated after'
                    elif any(_before(v[0], d) for v in b.values()) or any(_before(v, d) for v in alt.values()):
                        rec['cls'] = 'other events only'
                    else:
                        rec['cls'] = 'no season marks'
                out.append(rec)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--season', choices=('Indoor', 'Outdoor'))
    ap.add_argument('--list', type=int, metavar='YEAR', help='schools with gaps in one season year')
    ap.add_argument('--min', type=int, default=3, help='--list: schools with at least this many gaps')
    a = ap.parse_args()
    store = tp.load_store(quiet=True)
    champs = tp.load_champs()
    rows = gaps(store, champs, tp.truths(store, champs))
    if a.season:
        rows = [r for r in rows if r['season'] == a.season]
    if a.list:
        rows = [r for r in rows if r['year'] == a.list]
        for season in ('Indoor', 'Outdoor'):
            bad = [r for r in rows if r['season'] == season and r['cls'] not in ('ok', 'equivalent event')]
            if not bad:
                continue
            print(f'{a.list} {season}: {len(bad)} entrants without a mark')
            by = collections.defaultdict(list)
            for r in bad:
                by[r['unit']].append(r)
            for unit, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
                if len(rs) < a.min:
                    continue
                cls = collections.Counter(r['cls'] for r in rs)
                print(f'  {len(rs):4d} {unit}: ' + ', '.join(f'{k} {v}' for k, v in cls.most_common()))
        return
    tab = collections.defaultdict(collections.Counter)
    for r in rows:
        tab[(r['season'], r['year'])][r['cls']] += 1
    classes = ['equivalent event', 'no season marks', 'other events only', 'marks dated after', 'split identity',
               'entrant not matched', 'team no relay mark']
    print(f"{'season':8s}{'year':>5s}{'entrants':>9s}{'gap%':>6s} " + ' '.join(f'{c[:10]:>10s}' for c in classes))
    for (season, year), cnt in sorted(tab.items()):
        n = sum(cnt.values())
        miss = n - cnt['ok'] - cnt['equivalent event']
        print(f'{season:8s}{year:5d}{n:9d}{100 * miss / n:6.1f} ' + ' '.join(f'{cnt[c]:10d}' for c in classes))


if __name__ == '__main__':
    main()
