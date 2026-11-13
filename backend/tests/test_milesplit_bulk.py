"""MileSplit bulk staging: when a track meet is one we already hold.

Run:  python3 backend/tests/test_milesplit_bulk.py      (or pytest, if installed)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from backend import milesplit_bulk as mb  # noqa: E402


def _ev(gender, event, rows, relay=False):
    return dict(gender=gender, event=f'{gender} {event}', is_relay=relay,
                results=[dict(athlete=a, school=s, result=m) for a, s, m in rows])


def test_same_marks_across_sources_match():
    """MileSplit's 'Discus Throw' at '125-03' is sub5's 'Discus' at '125-03.00'."""
    a = mb._mark_keys(dict(events=[_ev('Boys', 'Discus Throw', [('Walker, Isaac', 'GNG', '125-03')])]))
    b = mb._mark_keys(dict(events=[_ev('Boys', 'Discus', [('Isaac Walker', 'Gray New Gloucester', '125-03.00')])]))
    assert a == b and a


def test_throwers_meet_two_days_later_is_new():
    """2025 GNG throwers meet (6/2): the WMC schools and throwers of the 5/31 championship, other marks."""
    held = {k: 'WMC-boys-1' for k in mb._mark_keys(dict(events=[
        _ev('Boys', 'Shot Put', [('A One', 'X', '40-01'), ('B Two', 'Y', '39-00'), ('C Three', 'Z', '38-02')])]))}
    mb._SEASON_MARKS[(1999, 'Outdoor')] = held
    new = dict(events=[_ev('Boys', 'Shot Put', [('A One', 'X', '41-05'), ('B Two', 'Y', '38-07'), ('C Three', 'Z', '37-11')])])
    assert mb.track_event_homes(new, 1999, 'Outdoor') == [None]


def test_partly_held_meet_keeps_new_events_and_drops_held_relay():
    """A meet whose shot put we hold (and one of its two relay teams) keeps only its new event."""
    held_doc = dict(events=[
        _ev('Girls', 'Shot Put', [('D Four', 'X', '30-01'), ('E Five', 'Y', '29-00'), ('F Six', 'Z', '28-02')]),
        _ev('Girls', '4x400 Meter Relay', [('', 'Yarmouth High School', '4:20.11')], relay=True)])
    mb._SEASON_MARKS[(1998, 'Outdoor')] = {k: 'held' for k in mb._mark_keys(held_doc)}
    new = dict(events=[
        held_doc['events'][0],
        _ev('Girls', '4x400 Meter Relay', [('', 'Yarmouth', '4:20.11'), ('', 'York', '4:31.00')], relay=True),
        _ev('Girls', 'Long Jump', [('D Four', 'X', '15-01'), ('E Five', 'Y', '14-00'), ('F Six', 'Z', '13-02')])])
    assert mb.track_event_homes(new, 1998, 'Outdoor') == ['held', 'held', None]


def test_entries_and_converted_pages_are_not_results():
    """2011 SMAA Southwesterns: the Boys Entries list (seed marks) and the Converted postings were read as results."""
    from backend.milesplit import NOT_RESULTS
    for t in ('SMAA Southwestern Championship 2011 - Boys Entries (Raw)', 'Girls Coverted (Raw)',
              'Converted Boys', 'Meet Program', 'Psych Sheet'):
        assert NOT_RESULTS.search(t), t
    for t in ('SMAA Southwestern Championship 2011 - Boys (Raw)', 'Results', 'Girls Results', 'Boys Varsity'):
        assert not NOT_RESULTS.search(t), t


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok', name)


def test_date_conflict_cleared_by_the_runners_year():
    # a 2026 meet posted with a reused file's title 'GRAY - 5/10/2024': its runners first appear in 2026
    from backend import milesplit_bulk as mb
    names = [f'Runner {i}' for i in range(30)]
    idx = {n.lower(): {2026} for n in names[:20]}
    idx.update({n.lower(): {2025, 2026} for n in names[20:29]})
    idx[names[29].lower()] = {2024}   # one gone before
    mb._RUNNER_YEARS[('Outdoor', 2026)] = idx
    doc = {'events': [{'is_relay': False, 'results': [{'athlete': n} for n in names]}],
           'date_conflict': 'result sheet dated 2024, MileSplit lists 2026-05-08'}
    why = [w for w in mb.check(doc, 'Outdoor', 2026) if 'dated' in w]
    assert not why and 'date_conflict' not in doc and '20 of its 30 runners first appear' in doc['notes']
    mb._RUNNER_YEARS[('Outdoor', 2025)] = {n.lower(): {2021, 2022} for n in names}   # all gone: the conflict stands
    doc = {'events': [{'is_relay': False, 'results': [{'athlete': n} for n in names]}], 'date_conflict': 'x'}
    assert 'x' in mb.check(doc, 'Outdoor', 2025)
