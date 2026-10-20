import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / 'analyzer'))

COMMIT = '3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376'
URL = f'https://raw.githubusercontent.com/snap-research/locomo/{COMMIT}/data/locomo10.json'
BUDGETS = (1000, 2000, 4000)
CATEGORIES = {4: 'una sola pista', 1: 'varias pistas', 2: 'temporal', 3: 'dominio abierto'}
ORDER = (4, 1, 2, 3)
MODEL = os.environ.get('CORTEX_EMBED_MODEL', '').strip() if os.environ.get('CORTEX_EMBED_MODEL', '').strip().lower() not in ('', 'off', 'none', '0') else ''
SPLITS = {'todas': range(0, 10), 'ajuste': range(0, 5), 'control': range(5, 10)}
DIA = re.compile(r'D(\d+):(\d+)')
SESSION = re.compile(r'^session_(\d+)$')
DATE = re.compile(r'(\d{1,2}):(\d{2})\s*(am|pm)\s+on\s+(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})', re.I)
MATCH_CHARS = 48


def download(cache):
    cache = Path(cache).expanduser()
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f'locomo10-{COMMIT[:8]}.json'
    if not path.is_file():
        tmp = path.with_suffix('.part')
        with urllib.request.urlopen(URL, timeout=60) as r, open(tmp, 'wb') as f:
            shutil.copyfileobj(r, f)
        tmp.replace(path)
    return json.loads(path.read_text(encoding='utf-8'))


def parse_date(text):
    m = DATE.search(text or '')
    if not m:
        return datetime(2023, 1, 1)
    hour, minute, ampm, day, month, year = m.groups()
    hour = int(hour) % 12 + (12 if ampm.lower() == 'pm' else 0)
    return datetime.strptime(f'{day} {month[:3].title()} {year}', '%d %b %Y').replace(hour=hour, minute=int(minute))


def message_text(turn):
    text = ' '.join(str(turn.get('text') or '').split())
    caption = turn.get('blip_caption')
    return f'{text} [comparte una foto: {caption}]' if caption else text


def convert(sample, folder):
    conv = sample['conversation']
    speaker_a = conv.get('speaker_a')
    sessions = sorted((int(m.group(1)), key) for key in conv if (m := SESSION.match(key)))
    index = {}
    last = datetime(2023, 1, 1)
    for number, key in sessions:
        start = parse_date(conv.get(f'{key}_date_time'))
        last = max(last, start)
        name = f'sesion-{number:02d}.jsonl'
        lines = []
        for i, turn in enumerate(conv[key]):
            when = (start + timedelta(minutes=i)).strftime('%Y-%m-%dT%H:%M:00')
            role = 'user' if turn.get('speaker') == speaker_a else turn.get('speaker') or 'other'
            lines.append(json.dumps({'role': role, 'content': message_text(turn), 'time': when}, ensure_ascii=False))
            text = ' '.join(message_text(turn).split())
            index[turn['dia_id']] = (number, when[:16].replace('T', ' ') + ': ' + text[:MATCH_CHARS], name, i + 1)
        (folder / name).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return index, last + timedelta(days=1)


def retrieved(result, index):
    lines = {(entry[2], entry[3]): dia for dia, entry in index.items()}
    found = set()
    for item in result['items']:
        for ref in item.get('messages') or ():
            dia = lines.get((ref.get('file'), ref.get('line')))
            if dia:
                found.add(dia)
    markdown = ' '.join(result['markdown'].split())
    for dia, entry in index.items():
        if dia not in found and entry[1] in markdown:
            found.add(dia)
    return found


def evidence_of(qa):
    out = []
    for e in qa.get('evidence') or []:
        for m in DIA.finditer(e):
            out.append(f'D{int(m.group(1))}:{int(m.group(2))}')
    return sorted(set(out))


def evaluate(samples, work):
    from cortex_graph import brain, pipeline
    rows = []
    for n, sample in samples:
        folder = work / 'src' / f'locomo-{n}'
        folder.mkdir(parents=True)
        index, now = convert(sample, folder)
        t0 = time.time()
        pipeline.analyze_source(str(folder), name=f'locomo-{n}')
        print(f'muestra {n}: analizada en {time.time() - t0:.1f}s', file=sys.stderr, flush=True)
        for qa in sample['qa']:
            cat = qa.get('category')
            evidence = [e for e in evidence_of(qa) if e in index]
            if cat not in CATEGORIES or not evidence:
                continue
            for budget in BUDGETS:
                t = time.perf_counter()
                result = brain.recall(qa['question'], f'locomo-{n}', budget=budget, now=now)
                ms = (time.perf_counter() - t) * 1000
                found = retrieved(result, index)
                sessions = {index[e][0] for e in evidence}
                hit_sessions = {index[e][0] for e in found}
                rows.append({'sample': n, 'category': cat, 'budget': budget, 'recall': sum(e in found for e in evidence) / len(evidence),
                             'all': all(e in found for e in evidence), 'session': len(sessions & hit_sessions) / len(sessions),
                             'ms': ms, 'tokens': result['tokens'], 'items': len(result['items']), 'question': qa['question'], 'evidence': evidence})
    return rows


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def table(rows):
    lines = ['| categoría | preguntas | presupuesto | recall evidencia | todas halladas | acierto sesión | tokens medios | ms medios |', '|---|---|---|---|---|---|---|---|']
    groups = [(CATEGORIES[c], lambda r, c=c: r['category'] == c) for c in ORDER] + [('**global**', lambda r: True)]
    for label, pick in groups:
        for budget in BUDGETS:
            sel = [r for r in rows if r['budget'] == budget and pick(r)]
            if not sel:
                continue
            lines.append(f"| {label} | {len(sel)} | {budget} | {mean(r['recall'] for r in sel):.3f} | {mean(r['all'] for r in sel):.3f} | "
                         f"{mean(r['session'] for r in sel):.3f} | {mean(r['tokens'] for r in sel):.0f} | {mean(r['ms'] for r in sel):.0f} |")
    return '\n'.join(lines)


def worst(rows, budget=2000, limit=15):
    sel = sorted((r for r in rows if r['budget'] == budget and r['recall'] == 0), key=lambda r: (r['sample'], r['question']))
    lines = [f"- [{CATEGORIES[r['category']]}] muestra {r['sample']}: {r['question']} (evidencia {', '.join(r['evidence'])})" for r in sel[:limit]]
    return '\n'.join(lines)


def run_mode(data, mode):
    from cortex_graph import semantic
    if mode == 'lexico':
        os.environ['CORTEX_EMBED_MODEL'] = 'off'
    else:
        os.environ['CORTEX_EMBED_MODEL'] = MODEL or semantic.DEFAULT_MODEL
        enc = semantic.encoder()
        if enc is None:
            return None, None, 0.0
    work = Path(tempfile.mkdtemp(prefix='cortex-bench-memory-'))
    os.environ['CORTEX_DATA'] = str(work / 'data')
    try:
        t0 = time.time()
        rows = evaluate(data, work)
        total = time.time() - t0
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return rows, None if mode == 'lexico' else enc.name, total


def section(title, rows, split, total):
    out = [f'## {title}', '', f'Tiempo total {total:.0f}s (análisis e índice incluidos).', '', table(rows), '']
    parts = [(label, [r for r in rows if r['sample'] in SPLITS[key]]) for key, label in (('ajuste', 'Ajuste (muestras 0-4)'), ('control', 'Control (muestras 5-9, no usadas para afinar)'))]
    if split == 'todas' and all(sel for _, sel in parts):
        for label, sel in parts:
            out += [f'### {label}', '', table(sel), '']
    return out


def main():
    ap = argparse.ArgumentParser(description='Benchmark de memoria de Córtex sobre LoCoMo')
    ap.add_argument('--samples', type=int, default=10)
    ap.add_argument('--cache', default=os.environ.get('CORTEX_BENCH_WORK', '~/.cache/cortex-bench'))
    ap.add_argument('--split', choices=sorted(SPLITS), default='todas',
                    help='ajuste: muestras 0-4 (para afinar), control: 5-9 (validación), todas: 0-9')
    ap.add_argument('--mode', choices=('lexico', 'semantico', 'ambos'), default='ambos',
                    help='lexico: sin modelos; semantico: con embeddings locales (extra semantic); ambos (por defecto)')
    ap.add_argument('--out', default=str(HERE / 'results' / 'RESULTS.md'))
    args = ap.parse_args()
    data = [(n, s) for n, s in enumerate(download(args.cache)[:max(1, args.samples)]) if n in SPLITS[args.split]]
    out, last = [], None
    for mode in (('lexico', 'semantico') if args.mode == 'ambos' else (args.mode,)):
        rows, name, total = run_mode(data, mode)
        if rows is None:
            out += ['## Léxico + embeddings locales', '', 'No disponible: instala el extra `semantic` (`pip install "cortex-graph[semantic]"`) '
                    'y deja que el modelo se descargue la primera vez.', '']
            continue
        title = 'Léxico (por defecto, sin modelos)' if mode == 'lexico' else f'Léxico + embeddings locales (`{name}`)'
        out += section(title, rows, args.split, total)
        last = rows
    questions = sum(r['budget'] == BUDGETS[0] for r in last or ())
    out = ['# Benchmark de memoria (LoCoMo)', '',
           f'Conjunto: snap-research/locomo `{COMMIT[:8]}`, {len(data)} conversaciones (muestras {", ".join(str(n) for n, _ in data)}), '
           f'{questions} preguntas (sin adversariales), todo local: sin IA ni tokens de API.', ''] + out
    if last:
        out += ['## Preguntas sin ninguna evidencia recuperada (presupuesto 2000, último modo)', '', worst(last), '']
    text = '\n'.join(out)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
