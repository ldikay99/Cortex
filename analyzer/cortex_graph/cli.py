import argparse
import json
import logging
import os
import sys

from . import __version__, pipeline, query, store
from .analyze import KIND_ES, export_json, export_markdown
from .errors import CortexError, NotFound


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, f'error: {message}\n')


def kind_es(kind):
    return KIND_ES.get(kind, kind)


def where(n):
    return f"{n['file']}:{n['line']}"


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
    print(f"comunidad: {r['community']['name']} · estado: {r['status']}")
    if r['parent']:
        print(f"dentro de: {describe(r['parent'])}")
    labels = (('children', 'contiene'), ('imports', 'importa'), ('imported_by', 'lo importan'), ('calls', 'llama a'),
              ('called_by', 'lo llaman'), ('inherits', 'hereda de'), ('inherited_by', 'lo heredan'), ('refs', 'menciona'),
              ('referenced_by', 'lo mencionan'), ('loads', 'carga'), ('loaded_by', 'lo cargan'))
    for key, title in labels:
        print_list(title, r[key], describe)


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
    p.add_argument('--tests', action='store_true', help='incluye los tests')
    p.set_defaults(run=lambda a: pipeline.summary(pipeline.analyze_source(a.source, a.name, a.exclude, a.tests)), show=show_summary)

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
    p.set_defaults(run=lambda a: query.search(a.query, a.project, a.kind, a.limit), show=show_search)

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
    try:
        result = args.run(args)
        if result is not None:
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
