"""Five K Sport archive checks (no network, no browser, no archive files).

Run:  python3 backend/tests/test_fiveksport.py      (or pytest, if installed)

Fixtures are synthetic copies of the Five K Sport sheet layout; names are
made up. Each test names the failure it pins down.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from backend.fiveksport import check_complete, content_sha, read_results, text_chars  # noqa: E402

HEAD = """\
               Sample High School Boys Cross Country Meet

                     Cumberland, Maine 10/10/25 4:30PM

      Timing and Finish Line Management by 5K Sports Race Management

    207-865-4501  FiveKsport@aol.com  Fiveksport.com  Running4Free.com

Place TmPl No.  Name               Yr  School               Time

===== ==== ==== ================== === ==================== =====
"""


def _rows(a, b):
    return ''.join(f'   {k:2d}   {k:2d}  7{k:02d} Runner Number{k:<5d}     Falmouth             1{k % 10}:{k:02d}\n\n'
                   for k in range(a, b + 1))


PAGE1 = HEAD + '\n' + _rows(1, 30)
PAGE2 = '                                                                      Page 2\n\n' + HEAD + '\n' + _rows(31, 40)


def test_multipage_header_is_not_a_row():
    # Page 2 repeats the header block; the phone-number line once sliced into
    # place 20 / bib "-4501" / time "g4Free.com".
    rows = read_results(PAGE1 + '\n\n' + PAGE2)
    assert [r['place'] for r in rows] == list(range(1, 41)), [r['place'] for r in rows]


def test_truncated_extraction_is_refused():
    # The viewer reported "Page 1 of 1" for a 2-page file before laying out
    # page 2; the archive kept 43 of 62 finishers. Word's own count catches it.
    full = PAGE1 + '\n\n' + PAGE2
    stats = {'chars_nospace': text_chars(full)}
    check_complete(full, {'doc_stats': stats, 'rendered_pages': 2})
    try:
        check_complete(PAGE1, {'doc_stats': stats, 'rendered_pages': 1})
    except ValueError:
        pass
    else:
        raise AssertionError('page 1 alone passed the completeness check')
    # one missing row (25+ characters) is also refused
    try:
        check_complete(PAGE1 + '\n\n' + PAGE2.rsplit('   40', 1)[0], {'doc_stats': stats, 'rendered_pages': 2})
    except ValueError:
        pass
    else:
        raise AssertionError('a missing row passed the completeness check')


def test_page_number_field_is_not_a_change():
    # Word renders the "Page 1" header field on some loads and not others:
    # 5 characters short is allowed, and the document identity is unchanged.
    with_field = '                                                                      Page 1\n\n' + PAGE1
    stats = {'chars_nospace': text_chars(with_field)}
    check_complete(PAGE1, {'doc_stats': stats, 'rendered_pages': 1})
    assert content_sha(with_field) == content_sha(PAGE1)
    assert content_sha(PAGE1 + '\n\nPage Break\n') == content_sha(PAGE1)
    assert content_sha(PAGE1.replace('Runner Number1 ', 'Runner Numbr1  ')) != content_sha(PAGE1)


if __name__ == '__main__':
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
                print('PASS', name)
            except Exception as e:  # noqa: BLE001
                failed += 1
                import traceback
                traceback.print_exc()
                print('FAIL', name, e)
    sys.exit(1 if failed else 0)
