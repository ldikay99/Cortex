import importlib.util
import math
import os
import re
from bisect import bisect_right
from collections import Counter, defaultdict
from email.utils import getaddresses
from pathlib import Path

from . import documents, extract, importers
from .common import digest

CONV_EXTS = {'.json', '.jsonl', '.txt', '.srt', '.vtt', '.md', '.markdown'}
NOTE_EXTS = {'.md', '.mdx', '.markdown', '.rst'}
MD_EXTS = {'.md', '.mdx', '.markdown'}
HEAD_BYTES = 65536
MAX_MENTIONS = 30
SECTION_MENTIONS = 8
MESSAGE_MENTIONS = 10
MAX_RELATED = 8
MAX_CONCEPTS = 1500
MAX_PEOPLE = 3000
MSG_CHARS = 1500
CONV_CHARS = 40000
ASSISTANT_CHARS = 600
FILE_SCAN_BUDGET = 6_000_000
DOC_CHARS = 400000
SECTION_CHARS = 20000
MAIL_CHARS = 3000
MAIL_BUDGET = 3_000_000
DOC_BUDGET = 30_000_000
MIN_SCAN = 20000
LONG_DOC_LINES = 40
LONG_DOC_CHARS = 3000
GENERIC_AUTHORS = {'user', 'usuario', 'human', 'humano', 'assistant', 'asistente', 'system', 'sistema', 'model', 'ai', 'ia',
                   'bot', 'me', 'yo', 'you', 'tu', 'tú', 'unknown', 'desconocido', 'other', 'otro'}
HEADING_RE = re.compile(r'^(#{1,6})[ \t]+(.+?)[ \t#]*$')
FENCE_RE = re.compile(r'^\s*(```|~~~)')
MD_LINK_RE = re.compile(r'(?<!!)\[[^\]\n]*\]\(<?([^)\s>]+)>?(?:\s+"[^"]*")?\)')
LOGSEQ_PROP_RE = re.compile(r'^([A-Za-z][\w-]*)::\s*(.*)$')
FM_KEY_RE = re.compile(r'^([A-Za-z_][\w -]*):\s*(.*)$')
TEMPLATE_RE = re.compile(rb'\{\{|\{%|<%|\bv-(?:if|for|bind)\b|\bng-[a-z]')
OWNER = 'o:'


def ext_of(rel):
    return os.path.splitext(rel)[1].lower()


def read_head(root, rel):
    try:
        with open(os.path.join(root, rel), 'rb') as f:
            return f.read(HEAD_BYTES)
    except OSError:
        return b''


def plain_text(text):
    text = re.sub(r'!?\[\[([^\]|#]*)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]', lambda m: m.group(2) or m.group(1), text)
    text = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'[*_`>#]+', ' ', text)
    return ' '.join(text.split())


def first_paragraph(lines, start, end):
    out = []
    for line in lines[start:end]:
        if FENCE_RE.match(line) or HEADING_RE.match(line):
            if out:
                break
            continue
        if not line.strip():
            if out:
                break
            continue
        out.append(line.strip())
        if sum(len(x) for x in out) > 600:
            break
    return plain_text(' '.join(out))[:500]


def parse_list(value):
    value = value.strip()
    if value.startswith('[') and value.endswith(']'):
        value = value[1:-1]
    items = [v.strip().strip('"\'').strip() for v in re.split(r',', value)]
    return [re.sub(r'^\[\[|\]\]$', '', v).lstrip('#') for v in items if v]


def frontmatter(lines):
    meta = {}
    if lines and lines[0].strip() == '---':
        end = next((i for i in range(1, min(len(lines), 300)) if lines[i].strip() in ('---', '...')), None)
        if end is None:
            return meta, 0
        current = None
        for line in lines[1:end]:
            item = re.match(r'^\s+-\s+(.*)$', line) or re.match(r'^-\s+(.*)$', line)
            if item and current:
                meta.setdefault(current, [])
                if isinstance(meta[current], list):
                    meta[current].extend(parse_list(item.group(1)))
                continue
            m = FM_KEY_RE.match(line)
            if not m:
                continue
            current = m.group(1).strip().lower()
            value = m.group(2).strip()
            if not value:
                meta[current] = []
            elif value.startswith('['):
                meta[current] = parse_list(value)
            else:
                meta[current] = value.strip('"\'')
        return meta, end + 1
    i = 0
    while i < len(lines) and i < 50:
        m = LOGSEQ_PROP_RE.match(lines[i].strip().lstrip('- '))
        if not m:
            break
        meta[m.group(1).lower()] = m.group(2).strip()
        i += 1
    return meta, i


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [v for v in value if v]
    return parse_list(value) if (',' in value or value.startswith('[')) else [value.strip().lstrip('#')] if value.strip() else []


def md_headings(lines, start):
    out, fenced = [], False
    for i in range(start, len(lines)):
        line = lines[i]
        if FENCE_RE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        m = HEADING_RE.match(line)
        if m:
            title = plain_text(m.group(2)).strip()
            if title:
                out.append((len(m.group(1)), title, i + 1))
    return out


def iso_date(value):
    if not value:
        return None
    value = str(value).strip()
    m = re.match(r'(\d{4}-\d{2}-\d{2})', value)
    if m:
        return m.group(1)
    found = extract.find_dates(value)
    return found[0] if found else None


class Union:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            if rb < ra:
                ra, rb = rb, ra
            self.parent[rb] = ra


class Linker:
    def __init__(self, root, files, g, issues, read_source, now):
        self.root = str(root)
        self.root_path = Path(root)
        self.owner_tokens = set()
        self.budget = DOC_BUDGET
        self.files = sorted(files)
        self.g = g
        self.issues = issues
        self.read_source = read_source
        self.now = now
        self.file_nodes = {}
        for nid, meta in g.nodes.items():
            if meta.get('kind') in ('module', 'doc') and meta.get('file'):
                rel = meta['file']
                if rel not in self.file_nodes or nid.startswith('d:') and not self.file_nodes[rel].startswith('d:'):
                    self.file_nodes[rel] = nid
        self.by_base = defaultdict(list)
        for rel in self.files:
            self.by_base[rel.rsplit('/', 1)[-1].lower()].append(rel)
        self.sources = []
        self.names = Counter()
        self.surfaces = defaultdict(Counter)
        self.emails = defaultdict(Counter)
        self.first_seen = {}
        self.union = Union()
        self.participants = []
        self.attends = []
        self.links = set()
        self.owner_votes = Counter()
        self.owner_files = 0
        self.records = {}
        self.sections = {}
        self.aliases = {}

    def take(self, text, limit):
        size = min(limit, max(MIN_SCAN, self.budget))
        self.budget -= min(len(text), size)
        return text[:size]

    def file_node(self, rel, title='', end=None, hashed=''):
        nid = self.file_nodes.get(rel)
        if nid:
            return nid
        nid = f'd:{rel}'
        self.g.node(nid, kind='doc', name=rel.rsplit('/', 1)[-1], file=rel, line=1, lang=ext_of(rel).lstrip('.') or 'txt',
                    doc=(title or '')[:200], end=end or 1, hash=digest(hashed or rel))
        self.file_nodes[rel] = nid
        return nid

    def seen(self, token, rel, line):
        spot = (rel, line or 1)
        if token not in self.first_seen or spot < self.first_seen[token]:
            self.first_seen[token] = spot

    def person(self, name, email=None, rel='', line=1, weight=1):
        name = ' '.join((name or '').replace('"', ' ').split()).strip(" '<>")
        email = (email or '').strip().lower() or None
        if email and '@' not in email:
            email = None
        nkey = extract.key(name) if name and '@' not in name else ''
        if not nkey and not email:
            return None
        token = f'n:{nkey}' if nkey else f'e:{email}'
        if nkey:
            self.names[nkey] += weight
            self.surfaces[nkey][name] += weight
            self.seen(token, rel, line)
        if email:
            self.union.union(token, f'e:{email}')
            self.emails[token][email] += weight
            self.seen(f'e:{email}', rel, line)
        self.union.find(token)
        return token

    def address(self, value, rel, line):
        if value and '@' not in value:
            token = self.person(value, None, rel, line)
            return [token] if token else []
        out = []
        for name, email in getaddresses([value or '']):
            token = self.person(name, email, rel, line)
            if token:
                out.append(token)
        return out

    def add_source(self, sid, rel, line, found, explicit=(), parent=None, limit=None, people_lines=None):
        people = {}
        for k, (name, count, pos) in found['people'].items():
            pline = people_lines(pos) if people_lines else line
            token = self.person(name, None, rel, pline, count)
            if token:
                people[token] = people.get(token, 0) + count
        concepts = Counter()
        displays = {}
        forced = set()
        for ck, display, score, n in found['concepts']:
            concepts[ck] += n
            displays.setdefault(ck, display)
        for ck, (display, n, pos) in found['tags'].items():
            concepts[ck] += n
            displays[ck] = display
            forced.add(ck)
        email_tokens = Counter()
        for email, n in found['emails'].items():
            email_tokens[f'e:{email}'] += n
        self.sources.append({
            'id': sid, 'rel': rel, 'line': line, 'people': people, 'concepts': concepts, 'displays': displays,
            'forced': forced, 'tags': set(found['tags']), 'emails': email_tokens, 'explicit': Counter(explicit),
            'parent': parent, 'limit': limit or MAX_MENTIONS, 'wiki': {}, 'direct': Counter(),
        })
        return self.sources[-1]

    def conversation_file(self, rel, fmt):
        try:
            convs = importers.load(self.root, rel, fmt)
        except (OSError, ValueError, RecursionError):
            self.issues.add(rel, 'no se pudo leer el historial de conversaciones')
            return
        if not convs:
            return
        if len(convs) >= getattr(importers, 'MAX_CONVERSATIONS', 5000):
            self.issues.add(rel, f'se importaron solo las primeras {len(convs)} conversaciones')
        limit = getattr(importers, 'MAX_MESSAGES', 20000)
        if any(len(c.get('messages') or ()) >= limit for c in convs):
            self.issues.add(rel, f'algunas conversaciones tienen más de {limit} mensajes: se truncaron')
        owners = {n for n in importers.user_names(convs) if n}
        real = {n for n in owners if n.casefold() not in GENERIC_AUTHORS}
        if real:
            self.owner_files += 1
            for n in sorted(real):
                self.owner_votes[n] += 1
        fnode = self.file_node(rel, '1 conversación' if len(convs) == 1 else f'{len(convs)} conversaciones', hashed='|'.join(f"{c['id']}:{len(c['messages'])}" for c in convs))
        ids = set()
        budget = max(1500, min(CONV_CHARS, FILE_SCAN_BUDGET // len(convs)))
        for conv in convs:
            cid = f"k:{rel}#{conv['id']}"
            if cid in ids or cid in self.g.nodes:
                continue
            ids.add(cid)
            self.conversation(rel, fnode, cid, conv, owners, budget)

    def conversation(self, rel, fnode, cid, conv, owners, budget=CONV_CHARS):
        msgs = conv.get('messages') or []
        assistants = {m['author'] for m in msgs if m.get('role') == 'assistant' and m.get('author')}
        humans = {m['author'] for m in msgs if m.get('role') != 'assistant' and m.get('author')}
        first_user = (next((m['text'] for m in msgs if m.get('role') == 'user' and m.get('text')), '') or
            next((m['text'] for m in msgs if m.get('text')), ''))[:2000]
        lines = [m['line'] for m in msgs if m.get('line')]
        line = min(lines) if lines else 1
        title = (conv.get('title') or '').strip() or ' '.join(first_user.split())[:80] or str(conv.get('id'))
        meta = {'kind': 'conversation', 'name': title[:80], 'file': rel, 'line': line, 'end': max(lines) if lines else line,
                'source': conv.get('source') or 'generic', 'count': len(msgs), 'doc': ' '.join(first_user.split())[:500],
                'hash': digest(f"{cid}|{len(msgs)}|{conv.get('ended')}|{sum(len(m.get('text') or '') for m in msgs)}")}
        for k in ('started', 'ended'):
            if conv.get(k):
                meta[k] = conv[k]
        self.g.node(cid, **meta)
        self.g.edge(fnode, cid, 'contains')
        for name in conv.get('participants') or []:
            if name in assistants and name not in humans:
                continue
            is_owner = name in owners or name.casefold() in ('user', 'usuario', 'human', 'humano', 'yo', 'me')
            if name.casefold() in GENERIC_AUTHORS and not is_owner:
                continue
            if is_owner and name.casefold() in GENERIC_AUTHORS:
                self.participants.append((cid, OWNER))
                self.union.find(OWNER)
                self.seen(OWNER, rel, line)
                continue
            token = self.person(name, None, rel, line, 1)
            if token:
                self.participants.append((cid, token))
        people_parts, offsets, msg_lines, extra = [], [], [], []
        total = 0
        for m in msgs:
            if m.get('role') == 'assistant' or not m.get('text') or total > budget:
                continue
            text = m['text'][:MSG_CHARS]
            offsets.append(total)
            msg_lines.append(m.get('line') or line)
            people_parts.append(text)
            total += len(text) + 1
        for m in msgs:
            if m.get('role') != 'assistant' or not m.get('text') or total > budget:
                continue
            text = m['text'][:ASSISTANT_CHARS]
            extra.append(text)
            total += len(text) + 1
        people_text = '\n'.join(people_parts)
        found = extract.scan(people_text + '\n' + '\n'.join(extra), people_text=people_text)

        def people_lines(pos):
            i = bisect_right(offsets, pos) - 1
            return msg_lines[i] if 0 <= i < len(msg_lines) else line

        self.add_source(cid, rel, line, found, people_lines=people_lines)
        conv = dict(conv, node=cid)
        for rec in extract.facts(conv, owners, self.now):
            rec['source'] = cid
            old = self.records.get(rec['id'])
            if old is None:
                rec['seen'] = 1
                self.records[rec['id']] = rec
                continue
            old['seen'] += 1
            old['confidence'] = round(min(0.8, old['confidence'] + 0.05), 2)
            if (rec.get('valid_from') or '') < (old.get('valid_from') or '') and rec.get('valid_from'):
                rec['seen'], rec['confidence'] = old['seen'], old['confidence']
                self.records[rec['id']] = rec

    def note(self, rel):
        nid = f'd:{rel}'
        raw = self.read_source(self.root_path, rel, self.issues)
        if raw is None:
            return None
        text = raw.decode('utf-8', errors='replace')
        lines = text.split('\n')
        meta, body = frontmatter(lines) if ext_of(rel) in MD_EXTS else ({}, 0)
        heads = md_headings(lines, body) if ext_of(rel) in MD_EXTS else []
        node = self.g.nodes[nid]
        tags = sorted({t for t in as_list(meta.get('tags') or meta.get('tag') or meta.get('keywords')) if t})
        aliases = sorted({a for a in as_list(meta.get('aliases') or meta.get('alias')) if a})
        when = iso_date(meta.get('date') or meta.get('created') or meta.get('fecha'))
        if tags:
            node['tags'] = tags
        if aliases:
            node['aliases'] = aliases
        if when:
            node['when'] = when
        title = meta.get('title') or meta.get('titulo')
        if isinstance(title, str) and title:
            node['doc'] = title[:200]
        stem = os.path.splitext(rel.rsplit('/', 1)[-1])[0].lower()
        for name in [stem] + [a.lower() for a in aliases]:
            self.aliases.setdefault(name, []).append(rel)
        self.aliases.setdefault(os.path.splitext(rel)[0].lower(), []).append(rel)
        return {'rel': rel, 'nid': nid, 'text': text, 'lines': lines, 'tags': tags, 'body': body, 'heads': heads}

    def sections_for(self, rel, parent, heads, lines, text_len):
        out = []
        if not heads or len(lines) < LONG_DOC_LINES and text_len < LONG_DOC_CHARS:
            return out
        heads = [h for h in heads if h[0] <= 3]
        if sum(1 for h in heads if h[0] == 1) == 1 and heads and heads[0][0] == 1:
            heads = heads[1:]
        used = set()
        stack = []
        for i, (level, title, line) in enumerate(heads):
            end = next((h[2] - 1 for h in heads[i + 1:] if h[0] <= level), len(lines))
            base = extract.slug(title)
            s = base
            n = 2
            while s in used:
                s = f'{base}-{n}'
                n += 1
            used.add(s)
            sid = f's:{rel}#{s}'
            body = '\n'.join(lines[line:end])
            self.g.node(sid, kind='section', name=title[:120], file=rel, line=line, end=end,
                        doc=first_paragraph(lines, line, end), hash=digest(f'{sid}|{body}'))
            while stack and stack[-1][0] >= level:
                stack.pop()
            self.g.edge(stack[-1][1] if stack else parent, sid, 'contains')
            stack.append((level, sid))
            self.sections.setdefault((rel, base), sid)
            out.append((sid, line, body))
        return out

    def resolve(self, target, rel):
        t = target.strip().replace('\\', '/')
        if not t:
            return None
        low = t.lower()
        for cand in (low, re.sub(r'\.(md|mdx|markdown)$', '', low)):
            hits = self.aliases.get(cand)
            if hits:
                return sorted(hits)[0]
        nearby = os.path.normpath(os.path.join(os.path.dirname(rel), t)).replace(os.sep, '/')
        for cand in (t, nearby, t + '.md', nearby + '.md'):
            if cand in self.file_nodes:
                return cand
        same = self.by_base.get(low.rsplit('/', 1)[-1], [])
        if len(same) == 1 and same[0] in self.file_nodes:
            return same[0]
        return None

    def link_path(self, src, rel, target):
        if re.match(r'^[a-z][\w+.-]*:', target, re.I) or target.startswith('#'):
            return
        target = re.sub(r'%20', ' ', target.split('#', 1)[0].split('?', 1)[0])
        if not target:
            return
        nearby = os.path.normpath(os.path.join(os.path.dirname(rel), target)).replace(os.sep, '/')
        for cand in (nearby, target.lstrip('./')):
            if cand in self.file_nodes and cand != rel:
                self.links.add((src, self.file_nodes[cand]))
                return

    def note_links(self, info):
        rel, nid, text = info['rel'], info['nid'], info['text']
        found = extract.scan(self.take(text, DOC_CHARS))
        wiki = {}
        explicit = Counter()
        for target, heading, alias, pos in found['wikilinks']:
            if not target:
                continue
            hit = self.resolve(target, rel)
            if hit and hit != rel:
                tnode = self.file_nodes[hit]
                if heading:
                    tnode = self.sections.get((hit, extract.slug(heading)), tnode)
                self.links.add((nid, tnode))
            elif not hit:
                ck = extract.concept_key(target)
                if ck:
                    wiki.setdefault(ck, [target, 0, set()])
                    wiki[ck][1] += 1
                    if alias:
                        wiki[ck][2].add(alias)
        for m in MD_LINK_RE.finditer(text[:DOC_CHARS]):
            self.link_path(nid, rel, m.group(1))
        for t in info['tags']:
            ck = extract.concept_key(t)
            if ck:
                found['tags'].setdefault(ck, (t, 1, 0))
        src = self.add_source(nid, rel, 1, found, explicit, people_lines=lambda pos: text.count('\n', 0, pos) + 1)
        src['wiki'] = wiki
        for ck, (target, n, aliases) in wiki.items():
            src['concepts'][ck] += n
            src['displays'].setdefault(ck, target)
            src['forced'].add(ck)
        self.section_sources(rel, info['sections'])

    def section_sources(self, rel, sections):
        for sid, line, body in sections:
            found = extract.scan(self.take(body, SECTION_CHARS), limit=SECTION_MENTIONS)
            self.add_source(sid, rel, line, found, parent=True, limit=SECTION_MENTIONS,
                            people_lines=lambda pos, b=body, ln=line: ln + b.count('\n', 0, pos))

    def document(self, rel):
        ext = ext_of(rel)
        existing = self.file_nodes.get(rel)
        if existing and self.g.nodes[existing].get('kind') == 'module':
            if ext not in ('.html', '.htm') or TEMPLATE_RE.search(read_head(self.root, rel)):
                return
        data = documents.extract(self.root, rel)
        if data is None:
            if ext == '.pdf' and importlib.util.find_spec('pypdf') is None:
                self.issues.add(rel, 'instala cortex-graph[docs] para leer PDF')
            elif ext in ('.pdf', '.docx', '.odt', '.rtf', '.eml', '.mbox', '.ics'):
                self.issues.add(rel, 'no se pudo leer el documento')
            return
        text = data.get('text') or ''
        lines = text.split('\n')
        title = data.get('title') or ''
        fnode = self.file_node(rel, title, len(lines), hashed=text)
        node = self.g.nodes[fnode]
        if node.get('kind') == 'doc':
            node.setdefault('end', len(lines))
            if not node.get('doc'):
                node['doc'] = title[:200]
        meta = data.get('meta') or {}
        when = iso_date(meta.get('date') or meta.get('created'))
        if when and node.get('kind') == 'doc':
            node['when'] = when
        for target in data.get('links') or ():
            self.link_path(fnode, rel, target)
        messages = data.get('messages') or []
        events = data.get('events') or []
        if events:
            self.calendar(rel, fnode, events)
        if len(messages) > 1:
            self.mailbox(rel, fnode, messages, lines)
            return
        explicit = []
        for m in messages:
            explicit += self.address(m.get('from'), rel, m.get('line') or 1)
            explicit += self.address(m.get('to'), rel, m.get('line') or 1)
        found = extract.scan(self.take(text, DOC_CHARS))
        for t in data.get('tags') or ():
            ck = extract.concept_key(t)
            if ck:
                found['tags'].setdefault(ck, (t, 1, 0))
        self.add_source(fnode, rel, 1, found, explicit, people_lines=lambda pos: text.count('\n', 0, pos) + 1)
        heads = [(lvl, t, ln) for lvl, t, ln, *_ in data.get('sections') or () if t]
        self.section_sources(rel, self.sections_for(rel, fnode, heads, lines, len(text)))

    def mailbox(self, rel, fnode, messages, lines):
        budget = MAIL_BUDGET
        for n, m in enumerate(messages, 1):
            mid = f'd:{rel}#{n}'
            line = m.get('line') or 1
            nxt = messages[n].get('line') if n < len(messages) else None
            subject = (m.get('subject') or '').strip() or '(sin asunto)'
            body = m.get('text') or ''
            self.g.node(mid, kind='doc', name=subject[:120], file=rel, line=line, end=(nxt - 1) if nxt else line,
                        doc=' '.join(body.split())[:500], hash=digest(f"{mid}|{subject}|{len(body)}"), lang='mbox',
                        **({'when': iso_date(m['date'])} if iso_date(m.get('date')) else {}))
            self.g.edge(fnode, mid, 'contains')
            explicit = self.address(m.get('from'), rel, line) + self.address(m.get('to'), rel, line)
            chunk = body[:MAIL_CHARS] if budget > 0 else ''
            budget -= len(chunk)
            found = extract.scan(chunk, limit=6) if chunk else extract.scan('')
            self.add_source(mid, rel, line, found, explicit, limit=MESSAGE_MENTIONS)

    def calendar(self, rel, fnode, events):
        used = set()
        for ev in events:
            when = iso_date(ev.get('when'))
            if not when:
                continue
            title = (ev.get('title') or '').strip() or '(sin título)'
            base = f'w:{when}:{extract.slug(title)[:40]}'
            eid, n = base, 2
            while eid in used or eid in self.g.nodes:
                eid = f'{base}-{n}'
                n += 1
            used.add(eid)
            meta = {'kind': 'event', 'name': title[:120], 'file': rel, 'line': ev.get('line') or 1, 'when': ev.get('when') or when,
                    'doc': (ev.get('where') or '')[:500], 'hash': digest(f"{eid}|{ev.get('when')}|{ev.get('until')}")}
            if ev.get('until'):
                meta['until'] = ev['until']
            self.g.node(eid, **meta)
            self.g.edge(fnode, eid, 'contains')
            for who in ev.get('attendees') or ():
                for token in self.address(who, rel, meta['line']):
                    self.attends.append((token, eid))

    def run(self):
        notes = []
        for rel in self.files:
            ext = ext_of(rel)
            fmt = None
            if ext in CONV_EXTS:
                head = read_head(self.root, rel)
                try:
                    fmt = importers.detect(rel, head) if head else None
                except (ValueError, RecursionError):
                    fmt = None
            if fmt:
                self.conversation_file(rel, fmt)
            elif ext in NOTE_EXTS and f'd:{rel}' in self.g.nodes:
                info = self.note(rel)
                if info:
                    notes.append(info)
            elif documents.supports(rel):
                self.document(rel)
        for info in notes:
            info['sections'] = self.sections_for(info['rel'], info['nid'], info['heads'], info['lines'], len(info['text']))
        for info in notes:
            self.note_links(info)
            info.clear()
        return self.emit()

    def owners(self):
        if not self.owner_votes:
            return set()
        top = max(self.owner_votes.values())
        chosen = {n for n, v in self.owner_votes.items() if v == top or v >= 2}
        if top == 1 and self.owner_files > 1 and len(chosen) > 1:
            return set()
        return chosen

    def resolve_people(self):
        for name in sorted(self.owners()):
            token = self.person(name, None, *self.first_seen.get(f'n:{extract.key(name)}', ('', 1)), weight=0)
            if token:
                self.owner_tokens.add(token)
        for token in sorted(self.owner_tokens):
            self.union.union(token, OWNER)
        singles = defaultdict(list)
        for k in self.names:
            if '-' in k:
                singles[k.split('-', 1)[0]].append(k)
        for k in sorted(self.names):
            if '-' not in k and len(singles.get(k, ())) == 1:
                self.union.union(f'n:{k}', f'n:{singles[k][0]}')
        groups = defaultdict(list)
        for token in sorted(self.union.parent):
            groups[self.union.find(token)].append(token)
        canon = {}
        people = {}
        for root, tokens in sorted(groups.items()):
            names = [t[2:] for t in tokens if t.startswith('n:')]
            emails = Counter()
            for t in tokens:
                emails.update(self.emails.get(t, {}))
                if t.startswith('e:'):
                    emails[t[2:]] += 0
            is_owner = OWNER in tokens
            ranked = sorted(names, key=lambda k: ('-' not in k, -self.names[k], k))
            if is_owner:
                real = [k for k in ranked if k not in GENERIC_AUTHORS]
                pkey = real[0] if real else 'user'
            else:
                pkey = ranked[0] if ranked else sorted(emails, key=lambda e: (-emails[e], e))[0]
            surfaces = Counter()
            for k in names:
                surfaces.update(self.surfaces.get(k, {}))
            if is_owner:
                display = min(((s, n) for s, n in surfaces.items() if extract.key(s) not in GENERIC_AUTHORS),
                              key=lambda kv: (-kv[1], kv[0]), default=('Yo', 0))[0]
            elif surfaces:
                display = min(surfaces.items(), key=lambda kv: (len(kv[0].split()) < 2, -kv[1], kv[0]))[0]
            else:
                display = pkey
            spots = [self.first_seen[t] for t in tokens if t in self.first_seen]
            rel, line = min(spots) if spots else ('', 1)
            weight = sum(self.names[k] for k in names) + sum(emails.values())
            nid = f'u:{pkey}'
            aliases = sorted(set(surfaces) | ({'user'} if is_owner else set()))
            meta = {'kind': 'person', 'name': display[:120], 'file': rel, 'line': line or 1, 'aliases': aliases}
            if emails:
                meta['email'] = sorted(emails, key=lambda e: (-emails[e], e))[0]
                if len(emails) > 1:
                    meta['emails'] = sorted(emails)
            if is_owner:
                meta['owner'] = True
            people[nid] = (meta, weight, is_owner)
            for t in tokens:
                canon[t] = nid
        return canon, people

    def emit(self):
        canon, people = self.resolve_people()
        participant_ids = {canon.get(t) for _, t in self.participants} | {canon.get(t) for t, _ in self.attends}
        explicit_ids = set(participant_ids)
        for src in self.sources:
            for t in src['explicit']:
                explicit_ids.add(canon.get(t))
        ranked = sorted(people, key=lambda nid: (not people[nid][2], nid not in explicit_ids, -people[nid][1], nid))
        keep_people = set(ranked[:MAX_PEOPLE])
        person_concepts = {extract.concept_key(m['name']) for nid, (m, _, _) in people.items() if nid in keep_people}
        person_keys = {nid[2:]: nid for nid in keep_people}
        for src in self.sources:
            for ck in list(src['wiki']):
                pid = person_keys.get(extract.key(src['wiki'][ck][0]))
                if pid:
                    src['direct'][pid] += src['wiki'][ck][1]
                    src['concepts'].pop(ck, None)
                    src['forced'].discard(ck)
        spread = Counter()
        total = Counter()
        forced = set()
        tagged = set()
        displays = defaultdict(Counter)
        best_spot = {}
        aliases = defaultdict(set)
        for src in self.sources:
            for ck, n in src['concepts'].items():
                if ck in person_concepts:
                    continue
                spread[ck] += 1
                total[ck] += n
                displays[ck][src['displays'].get(ck, ck)] += n
                spot = (-n, src['rel'], src['line'])
                if ck not in best_spot or spot < best_spot[ck]:
                    best_spot[ck] = spot
            forced |= src['forced'] - person_concepts
            tagged |= src['tags'] - person_concepts
            for ck, (target, n, al) in src['wiki'].items():
                aliases[ck] |= al
        tops = sum(1 for s in self.sources if not s['parent'])
        need = max(2, math.ceil(tops / 400))
        chosen = [ck for ck in spread if ck in forced or spread[ck] >= need]
        chosen.sort(key=lambda ck: (ck not in forced, -spread[ck], -total[ck], ck))
        concepts = set(chosen[:MAX_CONCEPTS])
        for nid in sorted(keep_people):
            self.g.node(nid, **people[nid][0])
        for ck in sorted(concepts):
            names = displays[ck]
            display = min(names.items(), key=lambda kv: (-kv[1], kv[0]))[0]
            _, rel, line = best_spot[ck]
            al = sorted((set(names) | aliases[ck]) - {display})[:10]
            meta = {'kind': 'concept', 'name': display[:120], 'file': rel, 'line': line or 1, 'aliases': al}
            if ck in tagged:
                meta['tag'] = True
            self.g.node(f'x:{ck}', **meta)
        pairs = Counter()
        for src in self.sources:
            targets = Counter()
            prio = set()
            for t, n in src['people'].items():
                pid = canon.get(t)
                if pid in keep_people:
                    targets[pid] += n
            for pid, n in src['direct'].items():
                targets[pid] += n
                prio.add(pid)
            for t, n in list(src['emails'].items()) + list(src['explicit'].items()):
                pid = canon.get(t)
                if pid in keep_people:
                    targets[pid] += n
                    if t in src['explicit']:
                        prio.add(pid)
            mine = []
            for ck, n in src['concepts'].items():
                if ck in concepts:
                    targets[f'x:{ck}'] += n
                    mine.append((-n, ck))
                    if ck in src['forced']:
                        prio.add(f'x:{ck}')
            order = sorted(targets, key=lambda t: (t not in prio, -targets[t], t))[:src['limit']]
            for t in order:
                self.g.edge(src['id'], t, 'mentions')
            if not src['parent']:
                top = [ck for _, ck in sorted(mine)[:extract.TOP_CONCEPTS]]
                top.sort()
                for i, a in enumerate(top):
                    for b in top[i + 1:]:
                        pairs[(a, b)] += 1
        degree = Counter()
        for (a, b), n in sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0])):
            if n < 2:
                break
            if degree[a] < MAX_RELATED and degree[b] < MAX_RELATED:
                self.g.edge(f'x:{a}', f'x:{b}', 'related')
                degree[a] += 1
                degree[b] += 1
        for cid, t in sorted(self.participants):
            if canon.get(t) in keep_people:
                self.g.edge(cid, canon[t], 'participant')
        for t, eid in sorted(self.attends):
            if canon.get(t) in keep_people:
                self.g.edge(canon[t], eid, 'attends')
        for a, b in sorted(self.links):
            self.g.edge(a, b, 'links')
        records = sorted(self.records.values(), key=lambda r: (r.get('valid_from') or '', r['id']))
        self.resolve_about(records, people, keep_people)
        return extract.supersede(records)

    def resolve_about(self, records, people, keep_people):
        index = defaultdict(set)
        for nid in keep_people:
            meta, _, is_owner = people[nid]
            if is_owner or '@' in nid:
                continue
            index[nid[2:].split('-', 1)[0]].add(nid)
            for alias in meta.get('aliases') or ():
                index[extract.key(alias)].add(nid)
        for rec in records:
            about = []
            for name in rec.get('about') or ():
                k = extract.key(name)
                hits = index.get(k, ()) if '-' not in k else ()
                if len(hits) != 1:
                    about.append(name)
                    continue
                meta = self.g.nodes[next(iter(hits))]
                full = meta['name']
                if name not in meta['aliases']:
                    meta['aliases'] = sorted(set(meta['aliases']) | {name})
                about.append(full)
                if rec.get('value') == name:
                    rec['value'] = full
                    role = rec.get('role')
                    if role and rec['attribute'].count(':') == 2:
                        rec['attribute'] = f'relationship:{role}:{extract.key(full)}'
            rec['about'] = about


def link_content(root, files, g, issues, read_source, now=None):
    return Linker(root, files, g, issues, read_source, now).run()
