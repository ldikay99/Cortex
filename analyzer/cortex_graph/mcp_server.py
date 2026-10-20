import json
import os
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from . import brain
from . import context as graph_context
from . import __version__, overlay, pipeline, store
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
    'limit/offset. Results cite file:line; secrets in returned code are redacted. '
    'Córtex is also a private, local second brain about the user: notes, documents and imported chat histories become '
    'conversation, section, person, concept, event and memory nodes. Call profile once at the start of a conversation and '
    'follow its instructions; call recall before answering anything personal (who the user is, their preferences, people, '
    'projects, past decisions); call remember whenever the user states a durable fact, preference, decision, goal or '
    'instruction; call forget when they ask you to forget something. Memory tools default to the project "memoria". '
    'You can also build or complete the graph yourself, for code the analyzer covers poorly (unknown languages, config-driven '
    'flows, business processes) or to add components, flows and summaries: call graph_guide for a worklist, then graph_add in '
    'batches; contributions persist, are versioned and appear in the web like analyzer output (see the build_graph prompt).'
)

PROJECT = 'Project name; omit to use the most recently analyzed project.'
PAGE = 'Paginate with limit (default 50, max 500) and offset.'
MEMORY = 'Memory project name; omit to use the default memory project "memoria".'
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
MEMORY_WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
MEMORY_DELETES = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
GRAPH_WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)


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


def remember(text: str, project: str | None = None, category: str | None = None, about: list[str] | None = None,
             when: str | None = None, subject: str | None = None, attribute: str | None = None, value: str | None = None,
             confidence: float = 1.0) -> dict[str, Any]:
    return brain.remember(text, project, category, about or (), when=when, confidence=confidence, subject=subject,
                          attribute=attribute, value=value, rebuild='background')


def recall(query: str, project: str | None = None, budget: int = 2000, at: str | None = None,
           hints: list[str] | None = None) -> dict[str, Any]:
    return brain.recall(query, project, budget, at, hints=hints)


def forget(ref: str, project: str | None = None) -> dict[str, Any]:
    return brain.forget_and_refresh(ref, project, rebuild='background')


def profile(project: str | None = None, budget: int = 1500) -> dict[str, Any]:
    return brain.profile(project, budget)


def timeline(project: str | None = None, start: str | None = None, end: str | None = None, about: str | None = None,
             limit: int = 100) -> dict[str, Any]:
    return brain.timeline(project, start, end, about, limit)


def import_history(source: str, project: str | None = None, ai: bool = False, batch: bool = False,
                   model: str | None = None) -> dict[str, Any]:
    return brain.import_history(source, project, ai=bool(ai), batch=bool(batch), model=model or None)


def client_of(ctx):
    try:
        info = ctx.session.client_params.clientInfo
        return f'{info.name} {info.version}'.strip() if info.version else info.name
    except Exception:
        return None


def graph_guide(project: str | None = None, limit: int = 40) -> dict[str, Any]:
    return overlay.guide(project, limit)


def graph_add(project: str | None = None, nodes: list[dict[str, Any]] | None = None, edges: list[dict[str, Any]] | None = None,
              annotations: list[dict[str, Any]] | None = None, flows: list[dict[str, Any]] | None = None,
              ctx: Context | None = None) -> dict[str, Any]:
    return overlay.add(project, nodes, edges, annotations, flows, origin='agent', source=client_of(ctx), rebuild='background')


def graph_remove(ids: list[str], project: str | None = None) -> dict[str, Any]:
    return overlay.remove(project, ids, rebuild='background')


def graph_overlay(project: str | None = None, limit: int = 200, offset: int = 0) -> dict[str, Any]:
    return overlay.listing(project, limit, offset)


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
     'items as structured data and related tests. On notes, documents or memory projects (no code) it ranks sections, '
     'conversations, memories, people and concepts instead; for questions about the user prefer recall. ' + PROJECT),
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
    (remember, 'remember', MEMORY_WRITES,
     'Save a durable fact about the user (or about someone/something in their life) in their private local memory. Call it '
     'whenever the user states something worth knowing in future conversations: identity (name, city, job), a preference, a '
     'goal, a decision, a relationship, a habit, a skill, an event, or an instruction for assistants ("always answer in '
     'Spanish"). Write text as one self-contained sentence in the user\'s words. Optional: category (identity|preference|goal|'
     'decision|event|relationship|skill|habit|project|fact|instruction, inferred if omitted), about (names of people or topics), '
     'when (ISO date the fact refers to), subject/attribute/value (e.g. user/location/Madrid). Duplicates are detected; a new '
     'value for the same subject+attribute supersedes the old one, which is kept as history. Secrets (keys, tokens, passwords) '
     'are never stored in clear: they are redacted and the memory is marked sensitive. Returns status new|duplicate|updated '
     'and the ids it superseded; the graph is refreshed in the background. ' + MEMORY),
    (recall, 'recall', READ_ONLY,
     'Answer-oriented retrieval from the user\'s memory. Call it BEFORE answering anything personal or that depends on the user\'s '
     'past: who they are, where they live or work, preferences, people in their life, projects, what they decided or said '
     'before. Give the question in plain words (Spanish or English). Returns Markdown fitted to budget tokens (default 2000, '
     '200-20000): matching memories first (dense facts with dates, category and confidence; "probable" = low confidence), '
     'each with a short excerpt of the conversation it came from, then the most relevant individual chat messages grouped by '
     'conversation in time order (date and time, author, text) and document sections. Ranking: local BM25 with English/Spanish '
     'stemming and synonyms, speaker and date awareness, personalized PageRank over the graph, and optional local embeddings. '
     'Superseded facts are excluded unless the question is about the past ("where did I live before", "last month") or at '
     '(ISO date: what was true then) is given. hints (optional, recommended): up to 30 short extra search terms that you add '
     'from your own knowledge, weighted below the question: synonyms, translations (Spanish/English), paraphrases, related '
     'concepts and likely answer words. Examples: for "what instruments does she play?" pass ["violin", "piano", "guitar", '
     '"clarinete", "music"]; for "where did he travel last summer?" pass ["trip", "vacation", "viaje", "flight", "beach"]. '
     + MEMORY),
    (forget, 'forget', MEMORY_DELETES,
     'Forget one memory when the user asks you to (or a stored fact is wrong). ref: the memory id (r:... or the 12-hex id from '
     'recall/profile) or its text (closest match with at least 90% similarity). The text is erased from the memory log and '
     'the fact will not be re-extracted from imported histories. ' + MEMORY),
    (profile, 'profile', READ_ONLY,
     'Compact Markdown profile of the user to embed in a system prompt: who they are, instructions for assistants, '
     'preferences, goals, active projects, key people, habits, skills, recent decisions and events, with dates and memory '
     'refs; only currently valid, non-sensitive memories, ordered by confidence and recency, fitted to budget tokens '
     '(default 1500). Call it once at the start of a conversation and follow its instructions section. ' + MEMORY),
    (timeline, 'timeline', READ_ONLY,
     'Chronological history of the user: dated memories (including superseded ones), calendar events and imported '
     'conversations. Filter with start/end (ISO dates, inclusive) and about (a person, topic or word); limit 1-1000 '
     '(default 100; without start the most recent items are kept). Use it for "what happened when" questions. ' + MEMORY),
    (import_history, 'import_history', WRITES,
     'Import chat histories, notes or documents into a memory project and analyze them locally: source is a folder or a file '
     '(as seen by this server): ChatGPT or Claude exports (conversations.json), Claude Code transcripts (.jsonl), WhatsApp, '
     'Telegram, Slack and Discord exports, subtitles, Markdown notes, PDF/DOCX/HTML/email/calendar files. Locally it creates '
     'conversation, person, concept, section and event nodes plus rule-based memories. ai=true ADDITIONALLY sends the text '
     'of the conversations (secrets redacted first) to the Claude API (Anthropic cloud) to extract memories; it requires '
     'ANTHROPIC_API_KEY in the server environment, has a cost, and must only be used when the user explicitly agrees to send '
     'their history to the cloud. batch=true uses the cheaper Message Batches API (slower); model overrides the default. '
     'Runs synchronously. Importing a file adds it to the project (earlier imported files are kept); importing a folder makes that folder the project source. ' + MEMORY),
    (graph_guide, 'graph_guide', READ_ONLY,
     'Start here to build or complete the knowledge graph yourself. Returns the procedure and a concrete worklist for the project: '
     'files the analyzer could not parse or that produced no symbols (unknown languages, configs, scripts), communities with no '
     'component describing them, the most connected modules without a summary, endpoints/topics/variables with no detected '
     'counterpart (no handler, no client, no producer, no definition), and counts of what agents already contributed. Works for '
     'a project that is only a folder of arbitrary files (analyze it first with analyze_project). limit caps each list (5-500, '
     'default 40). ' + PROJECT),
    (graph_add, 'graph_add', GRAPH_WRITES,
     'Add your own knowledge to the graph in one validated batch (max 500 items); it persists in an append-only log, triggers a '
     'background refresh that saves a new version, and shows in the web, search, node_context, file_context and context_for. '
     'nodes: [{name, kind, summary?, tags?, file?, line?, end?, parent?, contains?, community_hint?, id?}] where kind is '
     '"component" (logical part: service, screen, layer, subsystem, datastore, external system), "flow" (named process) or an '
     'analyzer kind (module, class, function, method, doc, package, variable, endpoint, topic, concept, person, event); id '
     'defaults to a:<slug of name> and reusing a name or id updates the node; giving the id of an existing analyzer node '
     'annotates it instead of duplicating; contains lists node refs the new node groups (files, symbols); parent is the node '
     'that contains it; community_hint is a community name, file or node key to sit next to. edges: [{a, b, kind, label?, '
     'order?}] with kind "uses" (default; dependency between components) or call, import, http, rpc, data, event, env, ref, '
     'depends, related, contains (only from your nodes). annotations: [{id, summary?, tags?}] attach a summary and tags to any '
     'node. flows: [{name, summary?, tags?, steps: [node refs in order]}] create or redefine a flow with ordered step edges. '
     'Refs accept node keys (best), exact names or file paths. Secrets are redacted. Returns created/updated/annotated ids, edge '
     'ids (rel:...), rejected items with reasons, and whether a refresh was scheduled. ' + PROJECT),
    (graph_remove, 'graph_remove', MEMORY_DELETES,
     'Undo agent contributions: ids of nodes you created (their edges go too), edge ids (rel:...) or ids of nodes you annotated '
     '(removes the annotation). Analyzer nodes are never deleted. Triggers a background refresh. ' + PROJECT),
    (graph_overlay, 'graph_overlay', READ_ONLY,
     'List what agents contributed to a project: nodes, edges and annotations with origin (agent or ai), client, date and '
     'status (in the graph, pending refresh, or dropped because an endpoint no longer exists), counts, and the merge issues of '
     'the last version. Use it to verify a graph_add. limit (1-1000, default 200)/offset page each list. ' + PROJECT),
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


def resource_profile(project):
    return brain.profile(project)['markdown']


RESOURCES = [
    ('cortex://projects', resource_projects, 'projects', 'Analyzed projects with versions, origin and stats.', 'application/json'),
    ('cortex://{project}/overview', resource_overview, 'overview', 'Overview of one project: stats, communities, hubs, routes, tables.', 'application/json'),
    ('cortex://{project}/report', resource_report, 'report', 'Full Markdown report (grafo.md) of the latest version of a project.', 'text/markdown'),
    ('cortex://{project}/community/{id}', resource_community, 'community', 'One community (subsystem) of a project by numeric id.', 'application/json'),
    ('cortex://profile/{project}', resource_profile, 'profile', 'Markdown profile of the user from a memory project, ready to embed in a system prompt.', 'text/markdown'),
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


def prompt_build_graph(project: str | None = None, focus: str | None = None) -> str:
    scope = f' «{project}»' if project else ''
    arg = f'project={project!r}' if project else ''
    extra = f' Focus on: {focus}.' if focus else ''
    return (f'Build or complete the Córtex knowledge graph of the project{scope} with your own understanding of the code.{extra}\n\n'
            f'1. Call graph_guide({arg}) and read the procedure and the worklist. If the project does not exist yet, call '
            'analyze_project on its folder first (it works even when no language is supported).\n'
            '2. For each item, read the real content with read_symbol (any key, including m:<path> for whole files) or file_context; '
            'use community_context and node_context to see how parts connect. Never invent files or behavior.\n'
            '3. Call graph_add in batches of up to 500 items: components for the logical parts (with summary, contains and '
            'community_hint), flows with ordered steps for the important processes, edges of kind uses between components, and '
            'annotations with a one-sentence summary for important modules, endpoints and files the analyzer could not parse.\n'
            '4. Check the response: fix rejected items (usually an unknown ref: search_code gives the right key) and resend.\n'
            '5. Verify with graph_overlay and node_context on a few new nodes once the refresh has finished; repeat graph_guide '
            'until the worklist is short. Finish with a brief summary of what you added.')


PROMPTS = [
    (prompt_orient, 'orient', 'Orient me in this repository: purpose, subsystems, layers, entry points, hotspots.'),
    (prompt_plan_change, 'plan_change', 'Plan a safe change: relevant code, impact on dependents and the tests to touch.'),
    (prompt_review, 'review', 'Review the changes between two git revisions: impact, risk and tests to run.'),
    (prompt_explain, 'explain', 'Explain one symbol: what it does, who uses it and how it is tested.'),
    (prompt_build_graph, 'build_graph', 'Build or complete the project graph yourself: components, flows, edges and summaries.'),
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
