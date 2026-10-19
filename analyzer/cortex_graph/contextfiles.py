import os

from . import query, store
from .errors import InvalidInput, NotFound

START = '<!-- cortex:start -->'
END = '<!-- cortex:end -->'
TARGETS = {
    'agents': 'AGENTS.md',
    'claude': 'CLAUDE.md',
    'llms': 'llms.txt',
    'cursor': '.cursor/rules/cortex.mdc',
    'copilot': '.github/copilot-instructions.md',
}
DEFAULT_TARGETS = tuple(TARGETS)
MARKED = ('Generado por Córtex a partir del grafo de conocimiento del repo. Se regenera con `cortex context-files`; '
          'escribe tus notas fuera de los marcadores cortex.')
WHOLE = 'Generado por Córtex a partir del grafo de conocimiento del repo. Se regenera entero con `cortex context-files`.'
ENTRY_STEMS = ('__main__', 'main', 'cli', 'manage', 'server', 'app', 'index', 'program', 'application', 'wsgi', 'asgi', 'bootstrap')
MAX_COMMUNITIES = 12
MAX_FILES = 10
MAX_ENDPOINTS = 20
MAX_VARIABLES = 15
MAX_PACKAGES = 12
MAX_LAYERS = 8
MAX_HOTSPOTS = 8
TOOLS = (
    ('list_projects', 'proyectos analizados y sus versiones', [('projects', 'cortex projects')]),
    ('analyze_project', 'analizar de nuevo tras cambios grandes', [('analyze', 'cortex analyze <carpeta>')]),
    ('project_overview', 'orientarte: comunidades, nodos centrales, rutas', [('overview', 'cortex overview')]),
    ('context_for', 'contexto acotado y priorizado para una tarea', [('context', 'cortex context "<tarea>"')]),
    ('get_context', 'contexto acotado y priorizado para una tarea', [('context', 'cortex context "<tarea>"')]),
    ('read_symbol', 'leer el código exacto de un símbolo', [('read', 'cortex read <ref>'), ('show', 'cortex show <ref>'), ('code', 'cortex code <ref>')]),
    ('search_code', 'encontrar símbolos, archivos, rutas y documentos', [('search', 'cortex search "<texto>"')]),
    ('node_context', 'quién llama, importa, hereda o menciona un símbolo', [('node', 'cortex node <ref>')]),
    ('file_context', 'símbolos y vecinos de un archivo', [('file', 'cortex file <ruta>')]),
    ('community_context', 'archivos y dependencias de un subsistema', [('community', 'cortex community <número o nombre>')]),
    ('find_path', 'cómo se conectan dos símbolos', [('path', 'cortex path <a> <b>')]),
    ('impact_analysis', 'qué se rompe si cambias algo (antes de editar)', [('impact', 'cortex impact <ref>')]),
    ('review_changes', 'impacto, riesgo y tests afectados por un diff', [('review', 'cortex review')]),
    ('architecture', 'entradas, capas, ciclos, código muerto y puntos críticos', [('architecture', 'cortex architecture'), ('arch', 'cortex arch')]),
    ('dependencies', 'paquetes externos y quién los usa', [('deps', 'cortex deps'), ('dependencies', 'cortex dependencies')]),
    ('endpoints', 'rutas HTTP/RPC, sus handlers y quién las llama', [('endpoints', 'cortex endpoints'), ('routes', 'cortex routes')]),
    ('variables', 'variables de entorno: dónde se definen y se usan', [('vars', 'cortex vars'), ('variables', 'cortex variables'), ('env', 'cortex env')]),
    ('changes', 'qué cambió entre versiones', [('changes', 'cortex changes')]),
    ('get_report', 'reporte Markdown completo del grafo', [('export', 'cortex export -f md')]),
)
CORE_TOOLS = ('list_projects', 'analyze_project', 'project_overview', 'search_code', 'node_context', 'file_context',
              'community_context', 'find_path', 'impact_analysis', 'changes', 'get_report')


def mcp_tools():
    try:
        from .mcp_server import TOOLS as registered
    except ImportError:
        return list(CORE_TOOLS)
    return [t[1] for t in registered]


def cli_commands():
    try:
        from .cli import build_parser
        parser = build_parser()
    except Exception:
        return None
    for action in parser._actions:
        if getattr(action, 'choices', None) and isinstance(action.choices, dict):
            return set(action.choices)
    return None


def tool_rows():
    known = {t[0]: t for t in TOOLS}
    commands = cli_commands()
    rows = []
    for name in mcp_tools():
        _, purpose, candidates = known.get(name, (name, '—', []))
        usable = [usage for command, usage in candidates if commands is None or command in commands]
        rows.append((name, purpose, usable[0] if usable else '—'))
    return rows


def repo_root(index):
    entry = next((h for h in index.history if h.get('v') == index.version), {})
    origin = entry.get('origin') or {}
    hist = store.load_history(index.project)
    origin = origin or hist.get('origin') or {}
    if origin.get('type') == 'local' and origin.get('path'):
        return origin['path']
    source = os.path.join(store.data_dir(), store.slug(index.project), 'fuente')
    return source if os.path.isdir(source) else None


def files_of(index):
    return sorted((n for n in index.file_node.values() if not n.get('test')), key=lambda n: (-n['deg'], n['file']))


def ask(index, method, *args):
    try:
        result = getattr(index, method)(*args)
    except (AttributeError, TypeError, KeyError):
        return None
    return result if isinstance(result, dict) else None


def items_of(part):
    if not isinstance(part, dict):
        return [], 0
    items = part.get('items') or []
    return items, max(0, (part.get('total') or len(items)) - len(items))


def heuristic_entries(index):
    found = []
    for n in index.file_node.values():
        if n['kind'] != 'module' or n.get('test'):
            continue
        stem = os.path.splitext(os.path.basename(n['file']))[0].lower()
        if stem in ENTRY_STEMS:
            found.append((n['file'].count('/'), ENTRY_STEMS.index(stem), -n['deg'], n['file']))
    return [f'- `{f[3]}`' for f in sorted(found)[:MAX_FILES]]


def entry_lines(index, arch):
    if arch is None:
        return heuristic_entries(index)
    items, _ = items_of(arch.get('entry_points'))
    lines = []
    for item in items[:MAX_FILES]:
        node = item.get('node') or {}
        target = item.get('target') or ''
        where = f"{node['file']}:{node['line']}" if node.get('file') else ''
        shown = f'`{target}`' if target and target not in (item.get('name'), where) else ''
        detail = ' · '.join(x for x in (shown, where) if x)
        lines.append(f"- `{item.get('name')}` ({item.get('kind')})" + (f' → {detail}' if detail else ''))
    return lines


def communities(index):
    members = {}
    for n in files_of(index):
        members.setdefault(n['c'], []).append(n['file'])
    overview = {c['id']: c for c in index.overview()['communities']}
    ranked = sorted(index.graph['communities'], key=lambda c: (-c['size'], c['id']))
    rows = []
    for c in ranked[:MAX_COMMUNITIES]:
        files = members.get(c['id'], [])
        if not files:
            continue
        links = [x['name'] for x in overview.get(c['id'], {}).get('connected_to', []) if x.get('name')]
        rows.append((c['name'], len(files), files[:4], links[:3]))
    return rows, max(0, len(ranked) - MAX_COMMUNITIES)


def layer_lines(arch):
    levels, _ = items_of((arch or {}).get('layers'))
    if len(levels) < 2:
        return []
    lines = []
    for level in levels[:MAX_LAYERS]:
        names = [c.get('name') for c in level.get('communities') or [] if c.get('name')]
        if not names:
            continue
        label = 'base' if level.get('level') == 0 else f"nivel {level.get('level')}"
        lines.append(f"- **{label}:** {', '.join(names[:6])}" + (f' … y {len(names) - 6} más' if len(names) > 6 else ''))
    return lines


def critical_lines(index, arch):
    if arch is not None:
        items, _ = items_of(arch.get('hotspots'))
        lines = []
        for item in items[:MAX_HOTSPOTS]:
            churn = f" · {plural(item['churn'], 'commit', 'commits')}" if item.get('churn') else ''
            lines.append(f"- `{item['file']}` · usado por {plural(item['fan_in'], 'archivo', 'archivos')}{churn}")
        if lines:
            return lines
    central = [n for n in files_of(index) if n['kind'] == 'module' and n['deg'] > 0][:MAX_FILES]
    return [f"- `{n['file']}` · {plural(n['deg'], 'conexión', 'conexiones')}" for n in central]


def cycle_lines(arch):
    items, hidden = items_of((arch or {}).get('cycles'))
    lines = []
    for item in items[:3]:
        example = item.get('example') or item.get('files') or []
        lines.append(f"- {plural(item.get('size', len(example)), 'archivo', 'archivos')}: " + ' → '.join(f'`{f}`' for f in example[:8])
                     + (' → …' if len(example) > 8 else ''))
    return lines + more(len(items) - 3 + hidden)


def heuristic_endpoints(index):
    seen, rows = set(), []
    for n in sorted(index.nodes, key=lambda n: ((n.get('route') or '').split(' ', 1)[-1], n.get('route') or '', n['file'], n['line'])):
        route = n.get('route')
        if not route or (route, n['file']) in seen:
            continue
        seen.add((route, n['file']))
        handler = n['name'] if n['kind'] != 'endpoint' else None
        if n['kind'] == 'endpoint':
            target = next((index.nodes[b] for b, _ in index.out['handles'].get(n['id'], [])), None)
            handler = target['name'] if target else None
        rows.append((route, handler, f"{n['file']}:{n['line']}"))
    return rows, 0


def endpoint_rows(index, arch):
    if arch is None or 'endpoints' not in arch:
        return heuristic_endpoints(index)
    items, hidden = items_of(arch.get('endpoints'))
    rows = [(x['route'], (x.get('handlers') or [{}])[0].get('name'), f"{x['file']}:{x['line']}") for x in items]
    return rows, hidden


def ranked(index, kind, limit):
    nodes = sorted((n for n in index.nodes if n['kind'] == kind), key=lambda n: (-n['deg'], n['name']))
    return nodes, max(0, len(nodes) - limit)


def variable_names(index):
    result = ask(index, 'variables', None, MAX_VARIABLES, 0)
    if result is None:
        nodes, hidden = ranked(index, 'variable', MAX_VARIABLES)
        return [n['name'] for n in nodes[:MAX_VARIABLES]], hidden
    items, hidden = items_of(result.get('variables'))
    return [x['name'] for x in items[:MAX_VARIABLES]], hidden + max(0, len(items) - MAX_VARIABLES)


def package_names(index):
    result = ask(index, 'dependencies', None, MAX_PACKAGES, 0)
    if result is None:
        nodes, hidden = ranked(index, 'package', MAX_PACKAGES)
        items = [{'name': n['name'], 'version': n.get('version')} for n in nodes[:MAX_PACKAGES]]
    else:
        items, hidden = items_of(result.get('packages'))
        hidden += max(0, len(items) - MAX_PACKAGES)
        items = items[:MAX_PACKAGES]
    return [package_label(x['name'], x.get('version')) for x in items], hidden


def package_label(name, version):
    if version and version[0] in '=<>~^!':
        return f'`{name}{version}`'
    return f'`{name}`' + (f' {version}' if version else '')


def more(count):
    return [f'- … y {count} más'] if count > 0 else []


def plural(count, one, many):
    return f'{count} {one if count == 1 else many}'


def inline(names, hidden):
    return ', '.join(names) + (f' … y {hidden} más' if hidden else '')


def block(lines, title, rows):
    if rows:
        lines += ['', title, ''] + rows


def body(index, project, heading='##', note=MARKED):
    st = index.graph['stats']
    kinds = st.get('kinds') or {}
    symbols = sum(v for k, v in kinds.items() if k in ('class', 'function', 'method'))
    langs = ', '.join(f'{k} ({v})' for k, v in list((st.get('languages') or {}).items())[:8])
    sub = heading + '#'
    arch = ask(index, 'architecture')
    lines = [
        f'{heading} Córtex: mapa de «{index.project}»',
        '',
        note,
        '',
        f"**Tamaño:** {plural(st.get('files', 0), 'archivo', 'archivos')} · {plural(symbols, 'símbolo', 'símbolos')} · "
        f"{plural(st.get('edges', 0), 'relación', 'relaciones')} · {plural(st.get('communities', 0), 'subsistema', 'subsistemas')}.",
    ]
    if langs:
        lines.append(f'**Lenguajes:** {langs}.')
    rows, hidden = communities(index)
    block(lines, f'{sub} Subsistemas (comunidades)', [
        f"- **{name}** ({plural(count, 'archivo', 'archivos')}): {', '.join(f'`{f}`' for f in files)}"
        + (f" · se conecta con {', '.join(links)}" if links else '') for name, count, files, links in rows] + more(hidden))
    block(lines, f'{sub} Capas (de la base hacia arriba)', layer_lines(arch))
    block(lines, f'{sub} Puntos de entrada', entry_lines(index, arch))
    block(lines, f'{sub} Archivos críticos (cambiarlos afecta a muchos)', critical_lines(index, arch))
    block(lines, f'{sub} Ciclos de importación', cycle_lines(arch))
    routes, hidden = endpoint_rows(index, arch)
    block(lines, f'{sub} Endpoints', [f"- `{r}`" + (f' → `{h}`' if h else '') + f' · {w}' for r, h, w in routes[:MAX_ENDPOINTS]]
          + more(len(routes) - MAX_ENDPOINTS + hidden))
    names, hidden = variable_names(index)
    if names:
        block(lines, f'{sub} Variables de entorno', [inline([f'`{n}`' for n in names], hidden)])
    names, hidden = package_names(index)
    if names:
        block(lines, f'{sub} Dependencias más usadas', [inline(names, hidden)])
    lines += [
        '', f'{sub} Cómo consultar este repo con Córtex', '',
        f'Antes de abrir archivos a ciegas, pregunta al grafo. Servidor MCP `cortex` (proyecto `{index.project}`); '
        f'en la CLI añade `--json` para salida estructurada y `--project {index.project}` si hay varios proyectos.',
        '',
        '| Para | MCP | CLI |',
        '| --- | --- | --- |',
    ]
    lines += [f'| {purpose} | `{name}` | ' + (f'`{cli}`' if cli != '—' else cli) + ' |' for name, purpose, cli in tool_rows()]
    lines += [
        '',
        'Flujo: `context_for` con la tarea para recibir el contexto justo → `read_symbol` en vez de abrir archivos completos → '
        '`node_context` / `find_path` para seguir vínculos → `impact_analysis` o `review_changes` antes y después de cambiar algo. '
        'Las referencias aceptan una clave (`f:ruta:nombre`), un nombre, una ruta o un fragmento.',
    ]
    return '\n'.join(lines) + '\n'


def section(text):
    return f'{START}\n{text}{END}\n'


def splice(existing, block):
    if not existing:
        return block
    start = existing.find(START)
    end = existing.find(END, start + len(START)) if start >= 0 else -1
    if start >= 0 and end >= 0:
        tail = existing[end + len(END):]
        return existing[:start] + block + tail.removeprefix('\n')
    return existing.rstrip('\n') + '\n\n' + block


def llms_text(index, project):
    st = index.graph['stats']
    summary = (f"> Repositorio de {plural(st.get('files', 0), 'archivo', 'archivos')} y {plural(st.get('communities', 0), 'subsistema', 'subsistemas')}, "
               'descrito por Córtex a partir de su grafo de conocimiento.')
    return f'# {index.project}\n\n{summary}\n\n' + body(index, project)


def cursor_text(index, project):
    return ('---\ndescription: Mapa del repositorio generado por Córtex y cómo consultarlo por MCP o CLI\nalwaysApply: true\n---\n\n'
            + body(index, project, '#', WHOLE))


def render(target, index, project, existing):
    if target == 'cursor':
        return cursor_text(index, project)
    if target == 'llms':
        return splice(existing, section(llms_text(index, project)))
    return splice(existing, section(body(index, project)))


def read_text(path):
    try:
        with open(path, encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return None


def parse_targets(targets):
    if targets in (None, '', ()):
        return list(DEFAULT_TARGETS)
    if isinstance(targets, str):
        targets = [t for t in targets.replace(' ', ',').split(',') if t]
    wanted = []
    for t in targets:
        t = str(t).strip().lower()
        if t == 'all':
            return list(DEFAULT_TARGETS)
        if t not in TARGETS:
            raise InvalidInput(f'destino desconocido «{t}»: usa {", ".join(TARGETS)}')
        if t not in wanted:
            wanted.append(t)
    return wanted


def generate(project=None, targets=DEFAULT_TARGETS, out_dir=None, write=True):
    wanted = parse_targets(targets)
    index = query.load_index(project)
    root = out_dir or repo_root(index)
    if not root:
        raise NotFound(f'no sé dónde está el código de «{index.project}»: indica la carpeta de salida')
    root = os.path.abspath(os.path.expanduser(root))
    if not os.path.isdir(root):
        raise NotFound(f'no existe la carpeta «{root}»: indica la carpeta de salida')
    files = []
    for target in wanted:
        path = os.path.join(root, *TARGETS[target].split('/'))
        existing = read_text(path)
        text = render(target, index, index.project, existing)
        changed = text != existing
        if write and changed:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            store.write_atomic(path, text)
        item = {'target': target, 'path': path, 'bytes': len(text.encode('utf-8')), 'lines': text.count('\n'), 'changed': changed}
        if not write:
            item['content'] = text
        files.append(item)
    return {'project': index.project, 'version': index.version, 'root': root, 'written': bool(write), 'files': files}
