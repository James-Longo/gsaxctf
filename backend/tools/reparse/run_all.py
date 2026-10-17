"""Parse every Indoor/Outdoor archive file with the repo's current code into
<outdir>/<year>/<season>/<stem>.json (nothing in the repo is written)."""
import multiprocessing as mp, os, sys, glob, time
REPO = '/home/james-longo/Projects/gsaxctf'
sys.path.insert(0, REPO); os.chdir(REPO)
from backend import scraper_v2 as sv

def job(f):
    y, s = f.split('/')[-3:-1]
    out = os.path.join(OUT, y, s, os.path.splitext(os.path.basename(f))[0] + '.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    try:
        return sv._parse_one_file((f, out, s))
    except Exception as e:  # noqa
        return (f, 0, repr(e))

OUT = sys.argv[1]
if __name__ == '__main__':
    files = sorted(f for s in ('Indoor', 'Outdoor') for f in glob.glob(f'backend/data/sub5_archive/*/{s}/*')
                   if os.path.isfile(f))
    t = time.time()
    with mp.Pool(max(2, os.cpu_count() - 2)) as p:
        res = p.map(job, files, chunksize=8)
    errs = [r for r in res if r[2]]
    print(len(files), 'files', round(time.time() - t), 's;', len(errs), 'errors')
    for r in errs[:10]: print('  ', r)
