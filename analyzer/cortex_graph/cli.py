import argparse
import json
import logging
import os
import sys

from . import __version__, context, pipeline, query, store
from .analyze import KIND_ES, export_json, export_markdown
from .errors import CortexError, InvalidInput, NotFound


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, f'error: {message}\n')


def kind_es(kind):
    return KIND_ES.get(kind, kind)


def where(n):
    end = n.get('end')
    return f"{n['file']}:{n['line']}" + (f'-{end}' if end and end > n['line'] else '')


def describe(n):
    extra = ''.join(f' · {n[k]}' for k in ('route', 'table') if n.get(k))
    status = {'new': ' · nuevo', 'changed': ' · modificado'}.get(n.get('status'), '')
    return f"{kind_es(n['kind'])} {n['name']} · {where(n)} · {n['deg']} conexiones{extra}{status}"


def print_list(title, items, render, limit=15):
    if not items:
        return
    print(f'{title} ({len(items)}):')
    for item in items[:limit]:
        print(f'  - {render(item)}')
    if len(items) > limit:
        print(f'  … y {len(items) - limit} más')


def show_summary(result):
    st = result['stats']
    ch = result['changes']
    if result.get('unchanged'):
        print(f"{result['project']} v{result['version']}: sin cambios desde el último análisis · {st.get('seconds')} s")
        return
    print(f"{result['project']} v{result['version']}: {st['files']} archivos · {st['nodes']} nodos · {st['edges']} relaciones · "
          f"{st['communities']} comunidades · {st['seconds']} s")
    print(f"cambios: {ch.get('added', 0)} nuevos · {ch.get('modified', 0)} modificados · {ch.get('removed', 0)} eliminados")
    if st.get('warnings_total'):
        print(f"avisos: {st['warnings_total']} archivos no se pudieron analizar")
        for w in result['warnings']:
            print(f"  - {w['file']}: {w['error']}")
    print(f"reporte: {result['report']}")


def show_projects(result):
    if not result['projects']:
        print('todavía no hay proyectos analizados')
        return
    for p in result['projects']:
        last = p['last']
        origin = (p.get('origin') or {})
        source = origin.get('url') or origin.get('path') or origin.get('type') or '—'
        count = f"{p['versions']} versión" if p['versions'] == 1 else f"{p['versions']} versiones"
        print(f"{p['project']} · {count} · v{last['v']} del {last['date'][:16].replace('T', ' ')} · "
              f"{last['stats']['nodes']} nodos · {source}")


def show_overview(r):
    st = r['stats']
    print(f"{r['project']} v{r['version']} · {st['files']} archivos · {st['nodes']} nodos · {st['edges']} relaciones · {st['communities']} comunidades")
    print('comunidades:')
    for c in r['communities']:
        links = ', '.join(x['name'] for x in c['connected_to']) or '—'
        print(f"  {c['id']:>2} {c['name']} · {c['size']} nodos · {c['files']} archivos · centro {c['hub']} · se conecta con {links}")
    print_list('nodos más conectados', r['top_nodes'], describe, 20)
    print_list('rutas de la API', r['routes'], lambda n: f"{n['route']} → {n['name']} · {where(n)}", 30)
    print_list('tablas', r['tables'], lambda n: f"{n['table']} → {n['name']} · {where(n)}", 30)


def show_search(r):
    if not r['results']:
        print(f"sin resultados para «{r['query']}»")
        return
    print(f"{r['total']} resultados para «{r['query']}»:")
    for n in r['results']:
        print(f'  - {describe(n)}')


def show_node(r):
    print(describe(r['node']))
    if r['node'].get('sig'):
        print(r['node']['sig'])
    if r['node'].get('doc'):
        print(f"> {r['node']['doc']}")
    print(f"comunidad: {r['community']['name']} · estado: {r['status']}")
    if r['parent']:
        print(f"dentro de: {describe(r['parent'])}")
    labels = (('children', 'contiene'), ('imports', 'importa'), ('imported_by', 'lo importan'), ('calls', 'llama a'),
              ('called_by', 'lo llaman'), ('inherits', 'hereda de'), ('inherited_by', 'lo heredan'), ('refs', 'menciona'),
              ('referenced_by', 'lo mencionan'), ('loads', 'carga'), ('loaded_by', 'lo cargan'), ('tests', 'prueba'),
              ('tested_by', 'lo prueban'), ('handled_by', 'lo atiende'), ('handles', 'atiende'), ('http_calls', 'llama por HTTP a'),
              ('http_callers', 'lo llaman por HTTP'), ('rpc_calls', 'llama por RPC a'), ('rpc_callers', 'lo llaman por RPC'),
              ('env_vars', 'variables que usa'), ('env_users', 'la usan'), ('data', 'tablas que usa'), ('data_users', 'la usan'),
              ('emits', 'emite'), ('receives', 'recibe'), ('depends_on', 'depende de'), ('dependents', 'dependen de él'))
    for key, title in labels:
        print_list(title, r.get(key) or [], describe)
    print_list('cambia junto con', r.get('co_changes') or [], lambda x: f"{x['file']} ({x['weight']})")


def show_file(r):
    print(f"{r['file']} · comunidad {r['community']['name']} · {r['node']['deg']} conexiones")
    print_list('símbolos', r['symbols'], lambda s: f"{kind_es(s['kind'])} {s['name']} · línea {s['line']} · {s['deg']} conexiones", 60)
    print_list('importa', r['imports'], str, 30)
    print_list('lo importan', r['imported_by'], str, 30)
    print_list('llama a archivos', r['calls_into'], lambda x: f"{x['file']} ({x['weight']})")
    print_list('lo llaman desde', r['called_from'], lambda x: f"{x['file']} ({x['weight']})")
    print_list('documentos que lo mencionan', r['docs'], str)


def show_community(r):
    c = r['community']
    print(f"comunidad {c['id']} · {c['name']} · {c['size']} nodos · {c['files']} archivos · centro {c['hub']}")
    print_list('archivos', r['files'], lambda f: f"{f['file']} · {f['deg']} conexiones · {f['symbols']} símbolos", 30)
    print_list('nodos centrales', r['hubs'], describe, 10)
    print_list('depende de', r['depends_on'], lambda x: f"{x['name']} ({x['weight']})")
    print_list('la usan', r['used_by'], lambda x: f"{x['name']} ({x['weight']})")
    print_list('archivos externos que más usa', r['external_files'], lambda x: f"{x['file']} ({x['weight']})", 20)


def show_path(r):
    if not r['found']:
        print(r['message'])
        return
    print(f"camino de {r['length']} pasos:")
    for step in r['steps']:
        via = step['via']
        arrow = '' if via is None else (f"  --{via['kind']}--> " if via['direction'] == 'forward' else f"  <--{via['kind']}-- ")
        print(f"{arrow}{describe(step['node'])}")


def show_impact(r):
    print(f"impacto de cambiar {describe(r['target'])}")
    if not r['total']:
        print('nada depende de este nodo')
        return
    print(f"{r['total']} nodos dependen de él (hasta {r['depth']} saltos) en {len(r['files'])} archivos")
    for level in r['levels']:
        print_list(f"a {level['distance']} salto{'s' if level['distance'] > 1 else ''}", level['nodes'],
                   lambda n: f"{describe(n)} · por {n['via']} de {n['depends_on']}", 20)


def show_changes(r):
    if r['from_version'] is None:
        print(r['message'])
        return
    c = r['counts']
    print(f"{r['project']} v{r['from_version']} → v{r['to_version']}: {c['added']} nuevos · {c['modified']} modificados · {c['removed']} eliminados")
    print_list('nuevos', r['added'], describe, 40)
    print_list('modificados', r['modified'], describe, 40)
    print_list('eliminados', r['removed'], lambda n: f"{kind_es(n['kind'])} {n['name']} · {n['file']}", 40)


def mini(n):
    return f"{kind_es(n['kind'])} {n['name']} · {where(n)}"


def show_read(r):
    n = r['node']
    span = f"{r['start']}-{r['end']}" if r['end'] and r['end'] != r['start'] else str(r['start'])
    print(f"{kind_es(n['kind'])} {n['name']} · {r['file']}:{span}" + (f" · {n['sig']}" if n.get('sig') else ''))
    if r.get('redacted'):
        print(f"({r['redacted']} secretos redactados)")
    if r.get('note'):
        print(f"aviso: {r['note']}")
    width = len(str(r['end'] or 1))
    for k, text in enumerate(r['code'].split('\n')):
        number = r['start'] + k
        print(f'{number:>{width}} │ {text}' if number <= r['end'] else f"{'':>{width}} │ {text}")


def show_context(r):
    print(r['markdown'].rstrip('\n'))
    print(f"\n({r['tokens_used']} de {r['budget']} tokens · {r.get('seconds', 0)} s)", file=sys.stderr)


def show_architecture(r):
    sections = (
        ('entry_points', 'puntos de entrada', lambda x: f"{x['kind']} {x['name']} → " + (where(x['node']) if x.get('node') else x['target'])),
        ('endpoints', 'endpoints', lambda x: f"{x['route']} → " + (', '.join(mini(h) for h in x['handlers']) or '—')),
        ('layers', 'capas (0 = base)', lambda x: f"nivel {x['level']}: " + ', '.join(c['name'] for c in x['communities'])),
        ('cycles', 'ciclos de imports', lambda x: f"{x['size']} archivos: " + ' → '.join(x['example'] or x['files'])),
        ('hotspots', 'puntos calientes', lambda x: f"{x['file']} · {x['fan_in']} archivos dependen" + (f" · {x['churn']} commits" if x.get('churn') else '')),
        ('dead_code', 'posible código muerto', lambda x: f"{mini(x)} · {x['confidence']} · {x['lines']} líneas"),
        ('untested_public', 'API pública sin tests', lambda x: f"{mini(x)} · {x['fan_in']} archivos lo usan"),
    )
    print(f"{r['project']} v{r['version']} · arquitectura")
    for key, title, render in sections:
        part = r.get(key)
        if not part:
            continue
        print(f"{title}: {part['total']}" + (f" ({part['note']})" if part.get('note') else ''))
        for item in part['items'][:part.get('limit') or 15]:
            print(f'  - {render(item)}')


def show_deps(r):
    if r.get('note'):
        print(r['note'])
    if 'package' in r:
        p = r['package']
        print(f"{p['name']} {p['version'] or '(sin versión)'} · {p['ecosystem']} · {p['file']}:{p['line']} · {p['users']} archivos la usan")
        for row in r['used_by']['items']:
            print(f"  - {row['file']}" + (f" · {row['community']}" if row.get('community') else ''))
        return
    page = r['packages']
    print(f"{page['total']} dependencias · " + ', '.join(f'{k} {v}' for k, v in r['ecosystems'].items()))
    for p in page['items']:
        print(f"  - {p['name']} {p['version'] or '—'} · {p['ecosystem']} · {p['users']} archivos" + ('' if p['declared'] else ' · sin declarar'))


def show_endpoints(r):
    page = r['endpoints']
    print(f"{page['total']} endpoints")
    for e in page['items']:
        handlers = ', '.join(mini(h) for h in e['handlers']) or '—'
        print(f"  - {e['route']} → {handlers}" + (f" · {e['callers_total']} llamadas" if e['callers_total'] else ''))


def show_vars(r):
    if r.get('note'):
        print(r['note'])
    page = r['variables']
    print(f"{page['total']} variables")
    for v in page['items']:
        defined = ', '.join(f"{d['file']}:{d['line']}" for d in v['defined_in'][:3])
        print(f"  - {v['name']} · definida en {defined} · {v['used_by_total']} usos")


def show_review(r):
    s = r.get('summary') or {}
    risk = r.get('risk') or {}
    print(f"{r.get('project')} · {r.get('base')} → {r.get('head')}: {s.get('files', 0)} archivos · +{s.get('added', 0)} −{s.get('removed', 0)} · "
          f"{s.get('symbols', 0)} símbolos · {s.get('dependents', 0)} dependientes · riesgo {risk.get('score', '—')}")
    for reason in (risk.get('reasons') or [])[:8]:
        if isinstance(reason, dict):
            reason = f"{reason.get('detail') or reason.get('factor')}" + (f" (+{reason['points']})" if reason.get('points') else '')
        print(f'  · {reason}')
    print_list('símbolos cambiados', r.get('symbols') or [], lambda n: f"{describe(n)} · {n.get('change', '')}", 30)
    tests = r.get('tests') or {}
    print_list('tests a ejecutar', tests.get('files') or [], lambda t: t['file'], 20)
    print_list('sin tests', tests.get('missing') or [], str, 20)
    for w in r.get('warnings') or []:
        print(f'aviso: {w}')


def show_context_files(r):
    verb = 'escrito' if r.get('written') else 'generado (sin escribir)'
    print(f"{r['project']} v{r['version']} · {verb} en {r['root']}")
    for f in r['files']:
        print(f"  - {f['path']} · {f['lines']} líneas" + ('' if f.get('changed') else ' · sin cambios'))


def show_mcp_config(r):
    if 'clients' in r:
        for item in r['clients']:
            show_mcp_config(item)
            print()
        return
    if r.get('installed'):
        print(f"configuración de {r.get('label') or r['client']} guardada en {r['installed']}")
        return
    print(f"# {r.get('label') or r['client']} · {r['path']} ({r['format']})")
    print(r['content'].rstrip('\n'))
    if r.get('cli'):
        print(f"\n# o bien:\n{r['cli']}")


def show_hook(r):
    paths = r['paths']
    if not paths:
        print('no había ganchos de Córtex que quitar')
        return
    print(('ganchos instalados' if r['action'] == 'install' else 'ganchos quitados') + ':')
    for p in paths:
        print(f'  - {p}')


def show_watch(r):
    if r:
        show_summary(r)


def command_review(args):
    from .mcp_server import run_review
    diff = None
    if args.diff_file:
        try:
            with open(args.diff_file, encoding='utf-8', errors='replace') as f:
                diff = f.read()
        except OSError as exc:
            raise CortexError(f'no se pudo leer «{args.diff_file}»: {exc.strerror or exc}') from exc
    base, head = args.base, args.head
    if args.worktree:
        base, head = base or 'HEAD', 'WORKTREE'
    return run_review(base or 'HEAD~1', head or 'HEAD', args.project, args.root, diff)


def command_watch(args):
    from . import watch
    return watch.run(args.source, args.name, args.debounce, args.tests, args.once)


def command_hook(args):
    from . import watch
    if args.action == 'install':
        return {'action': 'install', 'paths': [str(watch.install_hook(args.repo, args.name))]}
    return {'action': 'uninstall', 'paths': [str(p) for p in watch.uninstall_hook(args.repo)]}


def command_context_files(args):
    from . import contextfiles
    return contextfiles.generate(args.project, args.targets or contextfiles.DEFAULT_TARGETS, args.out, not args.dry_run)


def command_mcp_config(args):
    from . import clients
    client = args.client_option or args.client
    if not client:
        if args.install:
            raise InvalidInput('indica el cliente para --install (por ejemplo: cortex mcp-config claude-code --install)')
        return {'clients': clients.snippets(args.mode)}
    if args.install:
        path = clients.install(client, args.mode, args.scope or 'project', args.root)
        result = clients.snippet(client, args.mode, args.scope)
        return {**result, 'installed': str(path)}
    return clients.snippet(client, args.mode, args.scope)


def command_serve(args):
    from .server import serve
    serve(args.port)


def command_mcp(args):
    from .mcp_server import main
    logging.getLogger().setLevel(logging.WARNING)
    main()


def command_export(args):
    index = query.load_index(args.project)
    graph = index.graph
    if args.format == 'md':
        text = export_markdown(graph)
    elif args.format == 'json':
        text = json.dumps(export_json(graph), ensure_ascii=False)
    else:
        text = json.dumps(graph, ensure_ascii=False)
    if not args.output:
        sys.stdout.write(text if text.endswith('\n') else text + '\n')
        return None
    try:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(text)
    except OSError as exc:
        raise CortexError(f'no se pudo escribir «{args.output}»: {exc.strerror or exc}') from exc
    print(f'exportado {index.project} v{index.version} en {os.path.abspath(args.output)}', file=sys.stderr)
    return None


def project_option(parser):
    parser.add_argument('--project', '-p', help='proyecto (por defecto, el analizado más recientemente)')


def build_parser():
    common = Parser(add_help=False)
    common.add_argument('--json', action='store_true', help='salida JSON para máquinas')
    parser = Parser(prog='cortex', description='Córtex: grafo de conocimiento determinista de un repositorio, sin IA.')
    parser.add_argument('--version', action='version', version=f'cortex-graph {__version__}')
    sub = parser.add_subparsers(dest='command', required=True, metavar='comando', parser_class=Parser)

    p = sub.add_parser('serve', help='servidor HTTP para la web de Córtex', parents=[common])
    p.add_argument('--port', type=int, default=None, help='puerto (por defecto 8000 o $PORT)')
    p.set_defaults(run=command_serve)

    p = sub.add_parser('mcp', help='servidor MCP por stdio para asistentes', parents=[common])
    p.set_defaults(run=command_mcp)

    p = sub.add_parser('analyze', help='analiza una carpeta o un repo de GitHub y guarda una versión', parents=[common])
    p.add_argument('source', help='carpeta local o https://github.com/usuario/repo')
    p.add_argument('--name', help='nombre del proyecto')
    p.add_argument('--exclude', nargs='*', default=[], help='carpetas o archivos que se omiten')
    p.add_argument('--tests', action='store_true', default=None, help='incluye los tests (por defecto, lo que diga .cortex.toml)')
    p.add_argument('--quiet', '-q', action='store_true', help='no imprime nada (para ganchos de git)')
    p.add_argument('--scip', metavar='RUTA', help='índice SCIP para aristas precisas')
    p.set_defaults(run=lambda a: pipeline.summary(pipeline.analyze_source(a.source, a.name, a.exclude, a.tests, scip=a.scip)), show=show_summary)

    p = sub.add_parser('projects', help='proyectos guardados', parents=[common])
    p.set_defaults(run=lambda a: {'projects': store.list_projects()}, show=show_projects)

    p = sub.add_parser('overview', help='resumen de un proyecto', parents=[common])
    p.add_argument('project', nargs='?', default=None)
    p.set_defaults(run=lambda a: query.overview(a.project), show=show_overview)

    p = sub.add_parser('search', help='busca símbolos, archivos y documentos', parents=[common])
    p.add_argument('query')
    project_option(p)
    p.add_argument('--kind', choices=query.KINDS)
    p.add_argument('--limit', type=int, default=20)
    p.add_argument('--offset', type=int, default=0)
    p.set_defaults(run=lambda a: query.search(a.query, a.project, a.kind, a.limit, a.offset), show=show_search)

    p = sub.add_parser('read', help='código exacto de un símbolo', parents=[common])
    p.add_argument('ref', help='clave, nombre o ruta')
    project_option(p)
    p.add_argument('--context', '-C', type=int, default=0, help='líneas de contexto alrededor (0-50)')
    p.set_defaults(run=lambda a: context.read_symbol(a.ref, a.project, a.context), show=show_read)

    p = sub.add_parser('context', help='contexto relevante para una tarea, ajustado a un presupuesto de tokens', parents=[common])
    p.add_argument('query', help='la tarea o pregunta en palabras normales')
    project_option(p)
    p.add_argument('--budget', '-b', type=int, default=8000, help='tokens como máximo (500-60000)')
    p.set_defaults(run=lambda a: context.context_for(a.query, a.project, a.budget), show=show_context)

    p = sub.add_parser('architecture', help='entradas, capas, ciclos, puntos calientes y código muerto', parents=[common])
    project_option(p)
    p.add_argument('--section', choices=query.SECTIONS, help='solo una sección, paginada')
    p.add_argument('--limit', type=int, default=None)
    p.add_argument('--offset', type=int, default=0)
    p.set_defaults(run=lambda a: query.architecture(a.project, a.section, a.limit, a.offset), show=show_architecture)

    p = sub.add_parser('deps', help='dependencias externas y quién las usa', parents=[common])
    p.add_argument('name', nargs='?', default=None, help='una dependencia concreta')
    project_option(p)
    p.add_argument('--limit', type=int, default=50)
    p.add_argument('--offset', type=int, default=0)
    p.set_defaults(run=lambda a: query.dependencies(a.project, a.name, a.limit, a.offset), show=show_deps)

    p = sub.add_parser('endpoints', help='rutas HTTP y métodos RPC con sus manejadores', parents=[common])
    project_option(p)
    p.add_argument('--method', help='GET, POST…')
    p.add_argument('--limit', type=int, default=50)
    p.add_argument('--offset', type=int, default=0)
    p.set_defaults(run=lambda a: query.endpoints(a.project, a.limit, a.offset, a.method), show=show_endpoints)

    p = sub.add_parser('vars', help='variables de entorno y configuración', parents=[common])
    p.add_argument('name', nargs='?', default=None, help='filtra por nombre')
    project_option(p)
    p.add_argument('--limit', type=int, default=50)
    p.add_argument('--offset', type=int, default=0)
    p.set_defaults(run=lambda a: query.variables(a.project, a.name, a.limit, a.offset), show=show_vars)

    p = sub.add_parser('review', help='impacto, riesgo y tests de los cambios entre dos revisiones', parents=[common])
    project_option(p)
    p.add_argument('--base', default=None, help='revisión base (por defecto HEAD~1, o HEAD con --worktree)')
    group = p.add_mutually_exclusive_group()
    group.add_argument('--head', default=None, help='revisión final (por defecto HEAD)')
    group.add_argument('--worktree', '-w', action='store_true', help='revisa los cambios sin confirmar')
    p.add_argument('--diff-file', help='lee un diff unificado de un archivo en vez de usar git')
    p.add_argument('--root', help='carpeta del repositorio (por defecto, la fuente analizada)')
    p.set_defaults(run=command_review, show=show_review)

    p = sub.add_parser('watch', help='vuelve a analizar cuando cambian los archivos', parents=[common])
    p.add_argument('source', nargs='?', default='.', help='carpeta del repositorio')
    p.add_argument('--name', help='nombre del proyecto')
    p.add_argument('--debounce', type=float, default=1.5, help='segundos de calma antes de analizar')
    p.add_argument('--tests', action='store_true', default=None, help='incluye los tests')
    p.add_argument('--once', action='store_true', help='analiza una vez y termina')
    p.set_defaults(run=command_watch, show=show_watch)

    p = sub.add_parser('hook', help='instala o quita los ganchos de git que analizan tras cada commit', parents=[common])
    p.add_argument('action', choices=('install', 'uninstall'))
    p.add_argument('repo', nargs='?', default='.', help='repositorio git')
    p.add_argument('--name', help='nombre del proyecto')
    p.set_defaults(run=command_hook, show=show_hook)

    p = sub.add_parser('context-files', help='escribe AGENTS.md, CLAUDE.md, llms.txt y reglas para asistentes', parents=[common])
    project_option(p)
    p.add_argument('--targets', nargs='*', help='agents, claude, llms, cursor, copilot (por defecto, todos)')
    p.add_argument('--out', help='carpeta de salida (por defecto, la raíz del repositorio analizado)')
    p.add_argument('--dry-run', action='store_true', help='genera sin escribir')
    p.set_defaults(run=command_context_files, show=show_context_files)

    p = sub.add_parser('mcp-config', help='configuración MCP para un cliente (Claude Code, Cursor, VS Code…)', parents=[common])
    p.add_argument('client', nargs='?', default=None,
                   help='claude-code, claude-desktop, cursor, vscode, windsurf, zed, codex, gemini-cli, continue, cline (sin cliente: todos)')
    p.add_argument('--client', dest='client_option', default=None, help='igual que el argumento posicional')
    p.add_argument('--mode', choices=('docker', 'uvx', 'local'), default='docker')
    p.add_argument('--scope', choices=('project', 'user'), default=None)
    p.add_argument('--install', action='store_true', help='la añade al archivo de configuración del cliente')
    p.add_argument('--root', default='.', help='carpeta del proyecto para --scope project')
    p.set_defaults(run=command_mcp_config, show=show_mcp_config)

    p = sub.add_parser('node', help='contexto de un nodo', parents=[common])
    p.add_argument('ref', help='clave, nombre o ruta')
    project_option(p)
    p.set_defaults(run=lambda a: query.node(a.ref, a.project), show=show_node)

    p = sub.add_parser('file', help='contexto de un archivo', parents=[common])
    p.add_argument('path')
    project_option(p)
    p.set_defaults(run=lambda a: query.file(a.path, a.project), show=show_file)

    p = sub.add_parser('community', help='contexto de una comunidad', parents=[common])
    p.add_argument('ref', help='número o nombre')
    project_option(p)
    p.set_defaults(run=lambda a: query.community(a.ref, a.project), show=show_community)

    p = sub.add_parser('path', help='camino más corto entre dos nodos', parents=[common])
    p.add_argument('a')
    p.add_argument('b')
    project_option(p)
    p.set_defaults(run=lambda a: query.path(a.a, a.b, a.project), show=show_path)

    p = sub.add_parser('impact', help='qué depende de un nodo', parents=[common])
    p.add_argument('ref')
    project_option(p)
    p.add_argument('--depth', type=int, default=3)
    p.set_defaults(run=lambda a: query.impact(a.ref, a.project, a.depth), show=show_impact)

    p = sub.add_parser('changes', help='cambios entre versiones', parents=[common])
    project_option(p)
    p.add_argument('--since', help='versión de referencia (por defecto, la anterior)')
    p.set_defaults(run=lambda a: query.changes(a.project, a.since), show=show_changes)

    p = sub.add_parser('export', help='exporta la última versión', parents=[common])
    project_option(p)
    p.add_argument('--format', '-f', choices=('md', 'json', 'cortex'), required=True)
    p.add_argument('-o', '--output', help='archivo de salida (por defecto, la salida estándar)')
    p.set_defaults(run=command_export)
    return parser


def main(argv=None):
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format='[cortex] %(message)s')
    args = build_parser().parse_args(argv)
    quiet = getattr(args, 'quiet', False)
    if quiet:
        logging.getLogger().setLevel(logging.WARNING)
    try:
        result = args.run(args)
        if result is not None and not quiet:
            if args.json or not getattr(args, 'show', None):
                print(json.dumps(result, ensure_ascii=False, indent=1))
            else:
                args.show(result)
            sys.stdout.flush()
        return 0
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    except CortexError as exc:
        print(f'error: {exc.message}', file=sys.stderr)
        return 3 if isinstance(exc, NotFound) else 1
    except OSError as exc:
        print(f'error: no se pudo leer o escribir «{exc.filename or store.data_dir()}»: {exc.strerror or exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('interrumpido', file=sys.stderr)
        return 130
