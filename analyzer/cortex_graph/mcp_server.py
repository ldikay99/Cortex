from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import pipeline, store
from . import query as graph_query

INSTRUCTIONS = (
    'Córtex is a deterministic knowledge graph of a code repository (no AI): modules, classes, functions, methods and '
    'Markdown docs, linked by contains/import/call/inherits/ref/loads edges and grouped into communities (subsystems). '
    'Typical flow: list_projects or project_overview to orient, search_code to find symbols, node_context and '
    'file_context to read relationships, impact_analysis before editing, changes to see what moved between versions. '
    'Node references accept a node key (e.g. "f:app/services.py:create_user"), a symbol name, a file path or a substring. '
    'The project argument is optional and defaults to the most recently analyzed project. Results cite file:line.'
)

PROJECT = 'Project name; omit to use the most recently analyzed project.'
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)


def list_projects() -> dict[str, Any]:
    return {'projects': [{
        'project': p['project'], 'versions': p['versions'], 'last_version': p['last'].get('v'),
        'date': p['last'].get('date'), 'origin': p.get('origin'), 'stats': p['last'].get('stats'),
        'changes': p['last'].get('changes'),
    } for p in store.list_projects()]}


def analyze_project(source: str, name: str | None = None, exclude: list[str] | None = None, include_tests: bool = False) -> dict[str, Any]:
    graph = pipeline.analyze_source(source, name, exclude or [], include_tests)
    return pipeline.summary(graph)


def project_overview(project: str | None = None) -> dict[str, Any]:
    return graph_query.overview(project)


def search_code(query: str, project: str | None = None, kind: str | None = None, limit: int = 20) -> dict[str, Any]:
    return graph_query.search(query, project, kind, limit)


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


TOOLS = [
    (list_projects, 'list_projects', READ_ONLY,
     'List analyzed projects with version count, last analysis date, origin (local path, GitHub URL, upload) and size stats.'),
    (analyze_project, 'analyze_project', WRITES,
     'Analyze a repository and save it as a new version. source: local directory path (as seen by this server) or '
     'https://github.com/owner/repo (cloned shallowly; uses GITHUB_TOKEN if set). name: project name (default: folder or repo name). '
     'exclude: relative paths to skip. include_tests: also analyze test files. Runs synchronously (seconds to a few minutes); '
     'returns stats, communities and counts of added/modified/removed nodes versus the previous version.'),
    (project_overview, 'project_overview', READ_ONLY,
     'Start here. Summary of a project: stats, communities (size, hub file, most connected communities), the 20 most '
     'connected nodes, API routes and database tables. ' + PROJECT),
    (search_code, 'search_code', READ_ONLY,
     'Find symbols, files or docs by name. All words must match the name, file path, key, route or table; exact name matches rank first, '
     'then by connectivity. kind filters to module|class|function|method|doc. limit: 1-200 (default 20). ' + PROJECT),
    (node_context, 'node_context', READ_ONLY,
     'Everything about one node: location, community, parent and children, imports/imported_by, calls/called_by, '
     'inherits/inherited_by, refs/referenced_by (docs), loads, and change status (new/changed/unchanged). ' + PROJECT),
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
     'What may break if a node changes: reverse dependents through import, call, inherits and ref edges, grouped by '
     'distance up to depth (1-10, default 3). For a file or class, its contained symbols are included as targets. ' + PROJECT),
    (changes, 'changes', READ_ONLY,
     'Nodes added, modified (code hash changed) and removed between the latest version and since_version '
     '(default: the previous version). ' + PROJECT),
    (get_report, 'get_report', READ_ONLY,
     'Full Markdown report of the latest version (communities, hubs, dependencies, routes, tables, docs, per-file symbols). '
     'Large; prefer the targeted tools first. ' + PROJECT),
]


def build_server():
    server = FastMCP('cortex', instructions=INSTRUCTIONS, log_level='WARNING')
    for fn, name, annotations, description in TOOLS:
        server.add_tool(fn, name=name, description=description, annotations=annotations)
    return server


def main():
    build_server().run('stdio')
