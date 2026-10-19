import codecs
import os
import subprocess
from collections import Counter, defaultdict

MAX_COMMITS = 2000
MAX_COMMIT_FILES = 30
MIN_COCHANGE = 3
MAX_PAIRS = 2000
TIMEOUT = 60


def git(root, *args, timeout=TIMEOUT):
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0', 'LC_ALL': 'C'}
    try:
        res = subprocess.run(['git', '-C', str(root), '-c', 'core.quotepath=off', *args], capture_output=True,
                             timeout=timeout, env=env, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    return res.stdout.decode('utf-8', errors='replace')


def repo_info(root):
    out = git(root, 'rev-parse', '--is-inside-work-tree', '--is-shallow-repository', '--show-prefix', timeout=15)
    if out is None:
        return None
    lines = out.split('\n') + ['', '', '']
    if lines[0].strip() != 'true':
        return None
    return {'shallow': lines[1].strip() == 'true', 'prefix': lines[2].strip()}


def unquote(path):
    if len(path) >= 2 and path[0] == '"' and path[-1] == '"':
        try:
            return codecs.escape_decode(path[1:-1].encode('utf-8'))[0].decode('utf-8', errors='replace')
        except (ValueError, UnicodeError):
            return path[1:-1]
    return path


def parse_log(text, prefix='', shallow=False):
    commits = []
    for chunk in text.split('\0'):
        head, _, body = chunk.partition('\n')
        parts = head.split('\x1f')
        if len(parts) < 4 or (shallow and not parts[3].strip()):
            continue
        every = {unquote(line.strip()) for line in body.split('\n') if line.strip()}
        paths = sorted(p[len(prefix):] for p in every if p.startswith(prefix))
        commits.append((parts[1].strip(), parts[2].strip().lower(), paths, len(every)))
    return commits


def summarize(commits, files):
    wanted = set(files)
    churn, last, authors, pairs = Counter(), {}, defaultdict(set), Counter()
    for date, author, paths, total in commits:
        mine = [p for p in paths if p in wanted]
        for p in mine:
            churn[p] += 1
            if date > last.get(p, ''):
                last[p] = date
            authors[p].add(author)
        if len(mine) >= 2 and total <= MAX_COMMIT_FILES:
            for i, a in enumerate(mine):
                for b in mine[i + 1:]:
                    pairs[(a, b)] += 1
    stats = {p: {'churn': churn[p], 'last': last[p], 'authors': len(authors[p])} for p in sorted(churn)}
    strong = sorted(((a, b, n) for (a, b), n in pairs.items() if n >= MIN_COCHANGE), key=lambda x: (-x[2], x[0], x[1]))
    return {'files': stats, 'cochange': strong[:MAX_PAIRS]}


def collect(root, files):
    if not files:
        return None
    repo = repo_info(root)
    if repo is None:
        return None
    out = git(root, 'log', '--no-merges', '--full-history', '--no-renames', '--name-only', '--date=short', '--format=%x00%H%x1f%ad%x1f%aE%x1f%P',
              '-n', str(MAX_COMMITS))
    if out is None:
        return None
    commits = parse_log(out, repo['prefix'], repo['shallow'])
    return {**summarize(commits, files), 'commits': len(commits), 'shallow': repo['shallow']}
