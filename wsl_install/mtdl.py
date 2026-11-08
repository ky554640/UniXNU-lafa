#!/usr/bin/env python3
"""Multi-threaded range downloader for GitHub release assets."""
import os
import sys
import threading
import time
import urllib.request

URL = sys.argv[1]
DST = sys.argv[2]
THREADS = int(sys.argv[3]) if len(sys.argv) > 3 else 16

chunk_dir = DST + '.parts'
os.makedirs(chunk_dir, exist_ok=True)

req = urllib.request.Request(URL, method='HEAD', headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=30) as r:
    total = int(r.headers['Content-Length'])
    accept_ranges = r.headers.get('Accept-Ranges', 'none')
print(f'total={total/1048576:.1f} MB  accept-ranges={accept_ranges}')

part = (total + THREADS - 1) // THREADS
done = [0] * THREADS
lock = threading.Lock()


def worker(idx):
    start = idx * part
    end = min(start + part - 1, total - 1)
    if start > end:
        return
    path = os.path.join(chunk_dir, f'{idx:03d}')
    have = os.path.getsize(path) if os.path.exists(path) else 0
    if have == end - start + 1:
        done[idx] = have
        return
    start += have
    if start > end:
        done[idx] = have
        return
    req = urllib.request.Request(URL, headers={
        'Range': f'bytes={start}-{end}',
        'User-Agent': 'Mozilla/5.0',
    })
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r, open(path, 'ab') as f:
                while True:
                    buf = r.read(262144)
                    if not buf:
                        break
                    f.write(buf)
                    with lock:
                        done[idx] += len(buf)
            break
        except Exception as e:
            time.sleep(2 + attempt * 2)
    with lock:
        done[idx] = os.path.getsize(path) if os.path.exists(path) else 0


threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(THREADS)]
for t in threads:
    t.start()

t0 = time.time()
while any(t.is_alive() for t in threads):
    time.sleep(3)
    cur = sum(done)
    el = time.time() - t0
    print(f'  {cur/1048576:7.1f} / {total/1048576:.1f} MB  {cur/1024/el:6.0f} KB/s', flush=True)

for t in threads:
    t.join()

with open(DST, 'wb') as out:
    for i in range(THREADS):
        p = os.path.join(chunk_dir, f'{i:03d}')
        if os.path.exists(p):
            with open(p, 'rb') as f:
                out.write(f.read())

size = os.path.getsize(DST)
print(f'done: {size/1048576:.1f} MB  expected {total/1048576:.1f} MB  ok={size==total}')
