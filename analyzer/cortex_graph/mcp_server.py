import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import context as graph_context
from . import __version__, pipeline, store
from . import query as graph_query
from .errors import CortexError

INSTRUCTIONS = (
    'Córtex is a deterministic knowledge graph of a code repository in any language (no AI): files, classes, functions, '
    'methods, docs, packages, endpoints, environment variables and message topics from 26 languages parsed with real syntax '
    'trees, plus config and infrastructure (Docker, compose, CI, SQL, protobuf, Terraform, Kubernetes), linked by '
    'contains/import/call/inherits/ref/loads/tests/http/rpc/handles/env/data/event/depends/cochange edges and grouped into '
    'communities (subsystems). Nodes carry file:line-end, one-line signatures and docstrings when the language provides them. '
    'Recommended flow for a task: (1) context_for with the task in plain words returns the most relevant symbols with their '
    'code, ranked by text relevance plus graph proximity and fitted to a token budget: call it first instead of grepping. '
    '(2) read_symbol to read the exact code of any symbol by key instead of opening whole files. (3) node_context, '
    'file_context and find_path to follow relationships; search_code for ranked lookups by name, signature, docstring or path. '
    '(4) impact_analysis before editing and review_changes after editing (impact, risk, tests to run). '
    'To orient in an unknown repo use project_overview and architecture (entry points, layers, cycles, hotspots, dead code); '
    'dependencies, endpoints and variables list packages, HTTP/RPC routes and env vars with who uses them. '
    'Node references accept a node key (e.g. "f:app/services.py:create_user"), a symbol name, a file path or a substring. '
    'The project argument is optional and defaults to the most recently analyzed project. Long lists are paginated with '
    'limit/offset. Results cite file:line; secrets in returned code are redacted.'
)

PROJECT = 'Project name; omit to use the most recently analyzed project.'
PAGE = 'Paginate with limit (default 50, max 500) and offset.'
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)


def list_projects() -> dict[str, Any]:
    return {'projects': [{
        'project': p['project'], 'versions': p['versions'], 'last_version': p['last'].get('v'),
        'date': p['last'].get('date'), 'origin': p.get('origin'), 'stats': p['last'].get('stats'),
        'changes': p['last'].get('changes'),
    } for p in store.list_projects()]}


def analyze_project(source: str, name: str | None = None, exclude: list[str] | None = None, include_tests: bool | None = None,
                    scip: str | None = None) -> dict[str, Any]:
    graph = pipeline.analyze_source(source, name, exclude or [], include_tests, scip=scip or None)
    return pipeline.summary(graph)


def project_overview(project: str | None = None) -> dict[str, Any]:
    return graph_query.overview(project)


def search_code(query: str, project: str | None = None, kind: str | None = None, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    return graph_query.search(query, project, kind, limit, offset)


def node_context(node: str, project: str | None = None) -> dict[str, Any]:
    return graph_query.node(node, project)


def file_context(path: str, project: str | None = None) -> dict[str, Any]:
    return graph_query.file(path, project)


def community_context(community: str, project: str | None = None) -> dict[str, Any]:
    return graph_query.community(community, project)


def find_path(source: str, target: str, project: str | None = None) -> dict[str, Any]:
    return graph_query.path(source, target, project)


def impact_analysis(node: str, project: str | None = None, depth: int = 3) -> dict[str, Any]:
    return graph_query.impact(node, project, depth)


def changes(project: str | None = None, since_version: int | None = None) -> dict[str, Any]:
    return graph_query.changes(project, since_version)


def get_report(project: str | None = None) -> str:
    return graph_query.report(project)


def read_symbol(node: str, project: str | None = None, context: int = 0) -> dict[str, Any]:
    return graph_context.read_symbol(node, project, context)


def context_for(query: str, project: str | None = None, budget: int = 8000) -> dict[str, Any]:
    result = graph_context.context_for(query, project, budget)
    return {k: result[k] for k in ('project', 'version', 'query', 'budget', 'tokens_used', 'source', 'markdown', 'items', 'tests')}


def architecture(project: str | None = None, section: str | None = None, limit: int | None = None, offset: int = 0) -> dict[str, Any]:
    return graph_query.architecture(project, section, limit, offset)


def dependencies(project: str | None = None, name: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    return graph_query.dependencies(project, name, limit, offset)


def endpoints(project: str | None = None, method: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    return graph_query.endpoints(project, limit, offset, method)


def variables(project: str | None = None, name: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    return graph_query.variables(project, name, limit, offset)


def run_review(base='HEAD~1', head='HEAD', project=None, root=None, diff=None):
    try:
        from . import review as review_module
    except ImportError as exc:
        raise CortexError('la revisión de cambios no está disponible en esta instalación') from exc
    try:
        if project in (None, '') and root in (None, ''):
            project = graph_query.resolve_project(None)
        return review_module.review(root, base or 'HEAD~1', head or 'HEAD', project, diff)
    except NotImplementedError as exc:
        raise CortexError('la revisión de cambios todavía no está implementada') from exc


def review_changes(base: str = 'HEAD~1', head: str = 'HEAD', project: str | None = None, root: str | None = None,
                   diff: str | None = None) -> dict[str, Any]:
    return run_review(base, head, project, root, diff)


TOOLS = [
    (list_projects, 'list_projects', READ_ONLY,
     'List analyzed projects with version count, last analysis date, origin (local path, GitHub URL, upload) and size stats.'),
    (analyze_project, 'analyze_project', WRITES,
     'Analyze a repository and save it as a new version. source: local directory path (as seen by this server) or '
     'https://github.com/owner/repo (cloned shallowly; uses GITHUB_TOKEN if set). name: project name (default: folder or repo name). '
     'exclude: relative paths to skip. include_tests: also analyze test files (default: .cortex.toml, else false). scip: path '
     '(as seen by this server) to a SCIP index for compiler-precise call/ref/import edges. Runs synchronously '
     '(seconds to a few minutes); returns stats, communities and counts of added/modified/removed nodes versus the previous version.'),
    (project_overview, 'project_overview', READ_ONLY,
     'Summary of a project: stats, communities (size, hub file, most connected communities), the 20 most '
     'connected nodes, API routes and database tables (first 100 of each, with totals). ' + PROJECT),
    (context_for, 'context_for', READ_ONLY,
     'Start here for any task or question about the code. Give the task in plain words (e.g. "how does binding validate a '
     'request", "add rate limiting to login"); returns Markdown with the most relevant symbols ranked by BM25 text search '
     'plus personalized PageRank over the dependency graph: for each one kind, file:line-end, signature, docstring, callers '
     'and callees, and the exact code of the top ones, fitted to budget tokens (default 8000, 500-60000). Also returns the '
     'items as structured data and related tests. ' + PROJECT),
    (read_symbol, 'read_symbol', READ_ONLY,
     'Exact source code of one symbol (function, method, class, module, endpoint...) from its first to its last line, '
     'plus context lines around it (0-50). Use it instead of opening whole files. Max 400 lines (marked when truncated); '
     'secrets such as API keys, tokens and passwords are redacted. Warns when the file changed after the analysis. ' + PROJECT),
    (search_code, 'search_code', READ_ONLY,
     'Ranked search (BM25) over symbol names split into words (camelCase, snake_case), signatures, docstrings, file paths, '
     'routes and tables; exact and prefix name matches rank first. Each result has a score. kind filters to '
     'module|class|function|method|doc|package|variable|endpoint|topic. limit 1-200 (default 20), offset for paging. ' + PROJECT),
    (node_context, 'node_context', READ_ONLY,
     'Everything about one node: location, signature, docstring, community, parent and children, imports/imported_by, '
     'calls/called_by, inherits/inherited_by, refs/referenced_by, loads, tests/tested_by, http/rpc callers, handles/handled_by, '
     'env vars, data (tables), events, package dependencies, files that change together, and change status. ' + PROJECT),
    (file_context, 'file_context', READ_ONLY,
     'Map of one file: its symbols with line numbers, files it imports, files importing it, cross-file call traffic, '
     'and docs that mention it. path may be a full relative path or a unique suffix. ' + PROJECT),
    (community_context, 'community_context', READ_ONLY,
     'Describe a community (subsystem) by numeric id or name: files sorted by connectivity, hub nodes, communities it '
     'depends on or is used by, and the external files it relies on most. ' + PROJECT),
    (find_path, 'find_path', READ_ONLY,
     'Shortest connection between two nodes over all edge kinds (undirected, max 12 steps). Each step gives the edge kind '
     'and direction (forward = previous node points to this one). ' + PROJECT),
    (impact_analysis, 'impact_analysis', READ_ONLY,
     'What may break if a node changes: reverse dependents through import, call, inherits, ref, tests, http, rpc, handles, '
     'env, data, event and depends edges, grouped by distance up to depth (1-10, default 3). For a file or class, its '
     'contained symbols are included as targets. ' + PROJECT),
    (review_changes, 'review_changes', READ_ONLY,
     'Review a code change between two git revisions (base default HEAD~1, head default HEAD; use base="HEAD", '
     'head="WORKTREE" for uncommitted changes) or a unified diff passed in diff: changed files and symbols, direct and transitive '
     'dependents, a 0-100 risk score with reasons, and the tests to run. root: git checkout path (default: the analyzed '
     'source of the project). ' + PROJECT),
    (architecture, 'architecture', READ_ONLY,
     'Structural analysis: entry points (main functions, package.json bin/main, pyproject/setup.cfg scripts, Cargo bins), '
     'endpoints with handlers, public API without tests, import cycles between files, dead-code candidates with confidence, '
     'hotspots (fan-in x git churn) and layers (community dependency order, level 0 = foundation). Pass section '
     '(entry_points|endpoints|untested_public|cycles|dead_code|hotspots|layers) with limit/offset to page one section. ' + PROJECT),
    (dependencies, 'dependencies', READ_ONLY,
     'Third-party packages declared in manifests or imported in code (npm, PyPI, Go, Cargo, Maven, NuGet, Composer, RubyGems...) '
     'with version, ecosystem and how many files use them. With name, the files that use that package. ' + PAGE + ' ' + PROJECT),
    (endpoints, 'endpoints', READ_ONLY,
     'HTTP routes and RPC methods declared in the code: method, path (params as :name), handler functions with signatures '
     'and the client code calling them. method filters (GET, POST...). ' + PAGE + ' ' + PROJECT),
    (variables, 'variables', READ_ONLY,
     'Environment and config variables: where each is defined (.env files, compose, Kubernetes, Dockerfile, CI) and which '
     'symbols read it. name filters by substring. ' + PAGE + ' ' + PROJECT),
    (changes, 'changes', READ_ONLY,
     'Nodes added, modified (code hash changed) and removed between the latest version and since_version '
     '(default: the previous version). ' + PROJECT),
    (get_report, 'get_report', READ_ONLY,
     'Full Markdown report of the latest version (communities, hubs, dependencies, routes, tables, docs, per-file symbols). '
     'Large; prefer context_for and the targeted tools first. ' + PROJECT),
]


def as_json(data):
    return json.dumps(data, ensure_ascii=False, indent=1)


def resource_projects():
    return as_json(list_projects())


def resource_overview(project):
    return as_json(graph_query.overview(project))


def resource_report(project):
    index = graph_query.load_index(project)
    path = os.path.join(store.data_dir(), store.slug(index.project), 'grafo.md')
    try:
        with open(path, encoding='utf-8') as f:
            return f.read()
    except OSError:
        return graph_query.report(index.project)


def resource_community(project, id):
    return as_json(graph_query.community(id, project))


RESOURCES = [
    ('cortex://projects', resource_projects, 'projects', 'Analyzed projects with versions, origin and stats.', 'application/json'),
    ('cortex://{project}/overview', resource_overview, 'overview', 'Overview of one project: stats, communities, hubs, routes, tables.', 'application/json'),
    ('cortex://{project}/report', resource_report, 'report', 'Full Markdown report (grafo.md) of the latest version of a project.', 'text/markdown'),
    ('cortex://{project}/community/{id}', resource_community, 'community', 'One community (subsystem) of a project by numeric id.', 'application/json'),
]


def prompt_orient(project: str | None = None) -> str:
    target = f' «{project}»' if project else ''
    return (f'Orient me in the repository{target} using the Córtex tools. Call project_overview and architecture'
            f'{" with project=" + repr(project) if project else ""}, then summarize in a few short sections: what the project does, '
            'its main subsystems (communities) and how they depend on each other (layers), the entry points and endpoints, '
            'the hotspots I should be careful with, and import cycles or dead code worth knowing. Cite file:line for every claim. '
            'Use read_symbol only when a summary needs to confirm what a symbol does.')


def prompt_plan_change(change: str, project: str | None = None) -> str:
    scope = f' in project «{project}»' if project else ''
    return (f'Plan a safe change{scope}: {change}\n\n'
            'Steps: (1) call context_for with the change description to find the relevant symbols and read their code; '
            '(2) for each symbol you would modify, call impact_analysis (depth 2-3) and node_context to see callers, tests '
            '(tested_by) and endpoints; (3) produce a plan listing the files and symbols to edit with file:line, the dependents '
            'that may break, the tests to update or add, and the risks. Do not edit anything yet.')


def prompt_review(base: str = 'HEAD~1', head: str = 'HEAD', project: str | None = None) -> str:
    scope = f', project «{project}»' if project else ''
    return (f'Review the changes between {base} and {head}{scope}. Call review_changes(base={base!r}, head={head!r}) and then, '
            'for the riskiest changed symbols, read_symbol and impact_analysis. Report: what changed and why it matters, '
            'dependents that may break, missing or affected tests to run, and concrete issues found, each with file:line.')


def prompt_explain(symbol: str, project: str | None = None) -> str:
    scope = f' (project «{project}»)' if project else ''
    return (f'Explain the symbol «{symbol}»{scope}. Call read_symbol for its code and node_context for its callers, callees, '
            'tests and community; read the code of one or two key callees if needed. Explain what it does, its inputs and '
            'outputs, side effects, who uses it and how it is tested, citing file:line.')


PROMPTS = [
    (prompt_orient, 'orient', 'Orient me in this repository: purpose, subsystems, layers, entry points, hotspots.'),
    (prompt_plan_change, 'plan_change', 'Plan a safe change: relevant code, impact on dependents and the tests to touch.'),
    (prompt_review, 'review', 'Review the changes between two git revisions: impact, risk and tests to run.'),
    (prompt_explain, 'explain', 'Explain one symbol: what it does, who uses it and how it is tested.'),
]


def build_server():
    server = FastMCP('cortex', instructions=INSTRUCTIONS, log_level='WARNING')
    server._mcp_server.version = __version__
    for fn, name, annotations, description in TOOLS:
        server.add_tool(fn, name=name, description=description, annotations=annotations)
    for uri, fn, name, description, mime in RESOURCES:
        server.resource(uri, name=name, description=description, mime_type=mime)(fn)
    for fn, name, description in PROMPTS:
        server.prompt(name=name, description=description)(fn)
    return server


def main():
    build_server().run('stdio')
