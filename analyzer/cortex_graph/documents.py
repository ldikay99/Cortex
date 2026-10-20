import csv
import email
import email.policy
import logging
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

EXTS = {'.txt', '.pdf', '.docx', '.odt', '.html', '.htm', '.eml', '.mbox', '.ics', '.csv', '.tsv', '.rtf'}
MAX_FILE = 200 * 1024 * 1024
MAX_UNZIPPED = 50 * 1024 * 1024
MAX_TEXT = 2 * 1024 * 1024
MAX_PDF_PAGES = 500
MAX_MESSAGES = 5000
MAX_MESSAGE_BYTES = 4 * 1024 * 1024
CSV_ROWS = 200
CSV_COUNT = 100000
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
TEXT_NS = '{urn:oasis:names:tc:opendocument:xmlns:text:1.0}'
XLINK = '{http://www.w3.org/1999/xlink}href'
URL_RE = re.compile(r'https?://[^\s<>"\')\]]+')
BLOCK_TAGS = {'p', 'div', 'br', 'li', 'tr', 'table', 'ul', 'ol', 'section', 'article', 'header', 'footer', 'blockquote', 'pre', 'hr', 'dd', 'dt', 'dl', 'nav', 'aside', 'main', 'form', 'figure', 'figcaption', 'td', 'th'}
SKIP_TAGS = {'script', 'style', 'head', 'noscript', 'template', 'svg'}
RTF_SKIP = {'fonttbl', 'colortbl', 'stylesheet', 'info', 'pict', 'header', 'footer', 'generator', 'themedata', 'colorschememapping', 'latentstyles', 'datastore', 'listtable', 'listoverridetable', 'rsidtbl', 'xmlnstbl', 'object', 'fldinst'}
RTF_TOKEN = re.compile(r"\\([a-zA-Z]+)(-?\d+)? ?|\\'([0-9a-fA-F]{2})|\\([\\{}])|(\\\*)|([{}])|([^\\{}]+)")


def supports(rel):
    return os.path.splitext(rel)[1].lower() in EXTS


def decode(data):
    if data[:3] == b'\xef\xbb\xbf':
        data = data[3:]
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        return data.decode('cp1252', errors='replace')


def read_bytes(path, limit=MAX_FILE):
    if os.path.getsize(path) > limit:
        return None
    with open(path, 'rb') as f:
        return f.read()


def result(title, text, meta=None, links=(), tags=(), sections=(), messages=(), events=()):
    return {
        'title': (title or '').strip()[:200],
        'text': text[:MAX_TEXT],
        'meta': dict(meta or {}),
        'links': sorted(set(links)),
        'tags': sorted(set(t for t in tags if t)),
        'sections': list(sections),
        'messages': list(messages),
        'events': list(events),
    }


def first_line(text, fallback):
    for line in text.splitlines():
        line = ' '.join(line.split())
        if line:
            return line[:120]
    return fallback


def render(blocks):
    lines = []
    heads = []
    for level, text in blocks:
        text = ' '.join(text.split()) if level else re.sub(r'[ \t]+', ' ', text.strip())
        if not text:
            continue
        pieces = text.split('\n')
        if level:
            heads.append((level, text, len(lines) + 1))
        lines.extend(pieces)
    total = len(lines)
    sections = []
    for k, (level, text, line) in enumerate(heads):
        end = total
        for later in heads[k + 1:]:
            if later[0] <= level:
                end = later[2] - 1
                break
        sections.append((level, text, line, max(end, line)))
    return '\n'.join(lines), sections


def safe_xml(raw):
    head = raw[:8192].lower()
    if b'<!doctype' in head or b'<!entity' in head:
        return None
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        return None


def zip_member(zf, name):
    try:
        info = zf.getinfo(name)
    except KeyError:
        return None
    if info.file_size > MAX_UNZIPPED:
        return None
    with zf.open(info) as f:
        return f.read(MAX_UNZIPPED + 1)


def open_zip(path):
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        return None
    if sum(i.file_size for i in zf.infolist()) > MAX_UNZIPPED:
        zf.close()
        return None
    return zf


def heading_level(style, names):
    if not style:
        return 0
    key = names.get(style, style).casefold().replace(' ', '')
    if key in ('title', 'titulo', 'título'):
        return 1
    m = re.match(r'^(?:heading|ttulo|título|titulo)(\d)$', key)
    if m:
        return max(1, min(6, int(m.group(1))))
    return 0


def docx_para_text(p):
    out = []
    for el in p.iter():
        if el.tag == W + 't' and el.text:
            out.append(el.text)
        elif el.tag == W + 'tab':
            out.append('\t')
        elif el.tag in (W + 'br', W + 'cr'):
            out.append('\n')
    return ''.join(out)


def extract_docx(path, rel):
    zf = open_zip(path)
    if zf is None:
        return None
    with zf:
        raw = zip_member(zf, 'word/document.xml')
        root = safe_xml(raw) if raw else None
        if root is None:
            return None
        names = {}
        styles = zip_member(zf, 'word/styles.xml')
        sroot = safe_xml(styles) if styles else None
        if sroot is not None:
            for st in sroot.iter(W + 'style'):
                nm = st.find(W + 'name')
                if nm is not None:
                    names[st.get(W + 'styleId', '')] = nm.get(W + 'val', '')
        links = []
        rels = zip_member(zf, 'word/_rels/document.xml.rels')
        rroot = safe_xml(rels) if rels else None
        if rroot is not None:
            for r in rroot:
                if r.get('TargetMode') == 'External' and r.get('Type', '').endswith('/hyperlink'):
                    links.append(r.get('Target', ''))
        core = zip_member(zf, 'docProps/core.xml')
        croot = safe_xml(core) if core else None
    meta = {}
    tags = []
    title = ''
    if croot is not None:
        for el in croot:
            name = el.tag.rsplit('}', 1)[-1]
            value = (el.text or '').strip()
            if not value:
                continue
            if name == 'title':
                title = value
            elif name == 'creator':
                meta['author'] = value
            elif name == 'created':
                meta['created'] = value
            elif name == 'keywords':
                tags = [t.strip() for t in re.split(r'[,;]', value)]
    blocks = []
    body = root.find(W + 'body')
    for p in (body if body is not None else root).iter(W + 'p'):
        ppr = p.find(W + 'pPr')
        style = None
        if ppr is not None:
            ps = ppr.find(W + 'pStyle')
            style = ps.get(W + 'val') if ps is not None else None
        blocks.append((heading_level(style, names), docx_para_text(p)))
    text, sections = render(blocks)
    if not title:
        title = sections[0][1] if sections else first_line(text, os.path.splitext(os.path.basename(rel))[0])
    return result(title, text, meta, [x for x in links if x], tags, sections)


def odt_inline(el, links):
    out = []
    if el.text:
        out.append(el.text)
    for c in el:
        tag = c.tag
        if tag == TEXT_NS + 's':
            out.append(' ' * int(c.get(TEXT_NS + 'c', '1') or 1))
        elif tag == TEXT_NS + 'tab':
            out.append('\t')
        elif tag == TEXT_NS + 'line-break':
            out.append('\n')
        elif tag in (TEXT_NS + 'p', TEXT_NS + 'h'):
            pass
        else:
            if tag == TEXT_NS + 'a' and c.get(XLINK):
                links.append(c.get(XLINK))
            out.append(odt_inline(c, links))
        if c.tail:
            out.append(c.tail)
    return ''.join(out)


def extract_odt(path, rel):
    zf = open_zip(path)
    if zf is None:
        return None
    with zf:
        raw = zip_member(zf, 'content.xml')
        root = safe_xml(raw) if raw else None
        if root is None:
            return None
        metaraw = zip_member(zf, 'meta.xml')
        mroot = safe_xml(metaraw) if metaraw else None
    blocks = []
    links = []

    def walk(el):
        if el.tag == TEXT_NS + 'h':
            level = int(el.get(TEXT_NS + 'outline-level', '1') or 1)
            blocks.append((max(1, min(6, level)), odt_inline(el, links)))
        elif el.tag == TEXT_NS + 'p':
            blocks.append((0, odt_inline(el, links)))
        else:
            for c in el:
                walk(c)

    walk(root)
    meta = {}
    title = ''
    tags = []
    if mroot is not None:
        for el in mroot.iter():
            name = el.tag.rsplit('}', 1)[-1]
            value = (el.text or '').strip()
            if not value:
                continue
            if name == 'title':
                title = value
            elif name == 'initial-creator':
                meta['author'] = value
            elif name == 'creation-date':
                meta['created'] = value
            elif name == 'keyword':
                tags.append(value)
    text, sections = render(blocks)
    if not title:
        title = sections[0][1] if sections else first_line(text, os.path.splitext(os.path.basename(rel))[0])
    return result(title, text, meta, links, tags, sections)


class HtmlText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.buf = []
        self.level = 0
        self.skip = 0
        self.title = []
        self.in_title = False
        self.links = []
        self.meta = {}
        self.tags = []

    def flush(self):
        text = ''.join(self.buf)
        self.buf = []
        if text.strip():
            self.blocks.append((self.level, text))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'title':
            self.in_title = True
        if tag in SKIP_TAGS and tag != 'head':
            self.skip += 1
        if tag == 'meta':
            name = (attrs.get('name') or attrs.get('property') or '').casefold()
            content = (attrs.get('content') or '').strip()
            if name == 'keywords' and content:
                self.tags = [t.strip() for t in re.split(r'[,;]', content)]
            elif name in ('description', 'author', 'og:title') and content:
                self.meta[name.replace('og:', '')] = content
        if self.skip:
            return
        if re.fullmatch(r'h[1-6]', tag):
            self.flush()
            self.level = int(tag[1])
        elif tag in BLOCK_TAGS:
            self.flush()
        if tag == 'a':
            href = (attrs.get('href') or '').strip()
            if href and not href.lower().startswith(('javascript:', 'mailto:', 'tel:', 'data:')):
                self.links.append(href)

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        if tag in SKIP_TAGS and tag != 'head':
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if re.fullmatch(r'h[1-6]', tag):
            self.flush()
            self.level = 0
        elif tag in BLOCK_TAGS:
            self.flush()

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        elif not self.skip:
            self.buf.append(data)

    def finish(self):
        self.flush()


def html_to_blocks(source):
    parser = HtmlText()
    parser.feed(source)
    parser.close()
    parser.finish()
    return parser


def extract_html(path, rel):
    data = read_bytes(path)
    if data is None:
        return None
    parser = html_to_blocks(decode(data))
    text, sections = render(parser.blocks)
    title = ' '.join(''.join(parser.title).split())
    if not title:
        title = parser.meta.get('title') or (sections[0][1] if sections else first_line(text, os.path.splitext(os.path.basename(rel))[0]))
    meta = {k: v for k, v in parser.meta.items() if k in ('description', 'author')}
    return result(title, text, meta, parser.links, parser.tags, sections)


def iso_date(value):
    try:
        dt = parsedate_to_datetime(str(value))
    except (TypeError, ValueError, IndexError):
        return str(value or '')
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return dt.strftime('%Y-%m-%dT%H:%M:%S')


def message_body(msg):
    body = None
    try:
        body = msg.get_body(preferencelist=('plain', 'html'))
    except (KeyError, ValueError, LookupError):
        body = None
    if body is None:
        if msg.is_multipart():
            return '', []
        body = msg
    try:
        content = body.get_content()
    except (KeyError, ValueError, LookupError):
        payload = body.get_payload(decode=True) or b''
        content = decode(payload) if isinstance(payload, bytes) else str(payload)
    if not isinstance(content, str):
        return '', []
    links = []
    if body.get_content_type() == 'text/html':
        parser = html_to_blocks(content)
        links = parser.links
        content = '\n'.join(' '.join(t.split()) for _, t in parser.blocks if t.strip())
    return content.strip(), links


def build_message(raw, line):
    try:
        msg = email.message_from_bytes(raw, policy=email.policy.default)
        text, links = message_body(msg)
        entry = {
            'subject': str(msg.get('subject') or '').strip(),
            'from': str(msg.get('from') or '').strip(),
            'to': str(msg.get('to') or '').strip(),
            'date': iso_date(msg.get('date')) if msg.get('date') else '',
            'text': text,
            'line': line,
        }
    except (ValueError, LookupError, AttributeError, TypeError):
        return None, []
    return entry, links


def messages_result(entries, links, rel, fmt):
    parts = []
    for m in entries:
        head = ['Asunto: ' + m['subject'], 'De: ' + m['from']]
        if m['to']:
            head.append('Para: ' + m['to'])
        if m['date']:
            head.append('Fecha: ' + m['date'])
        parts.append('\n'.join(head) + '\n\n' + m['text'])
    title = entries[0]['subject'] if len(entries) == 1 else ''
    stem = os.path.splitext(os.path.basename(rel))[0]
    return result(title or stem, '\n\n'.join(parts), {'format': fmt, 'messages': len(entries)}, links, (), (), entries)


def extract_eml(path, rel):
    data = read_bytes(path, MAX_MESSAGE_BYTES * 4)
    if data is None:
        return None
    entry, links = build_message(data, 1)
    if entry is None:
        return None
    return messages_result([entry], links, rel, 'eml')


def extract_mbox(path, rel):
    entries = []
    links = []
    chunk = []
    size = 0
    start = 1

    def finish():
        if not chunk:
            return
        entry, found = build_message(b''.join(chunk), start)
        if entry is not None:
            entries.append(entry)
            links.extend(found)

    with open(path, 'rb') as f:
        prev_blank = True
        for lineno, raw in enumerate(f, 1):
            if raw.startswith(b'From ') and prev_blank:
                finish()
                if len(entries) >= MAX_MESSAGES:
                    chunk = []
                    break
                chunk = []
                size = 0
                start = lineno
            elif size < MAX_MESSAGE_BYTES:
                chunk.append(raw)
                size += len(raw)
            prev_blank = not raw.strip()
        else:
            finish()
    if not entries:
        return None
    return messages_result(entries, links, rel, 'mbox')


def unfold_ics(text):
    out = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        if raw[:1] in (' ', '\t') and out:
            out[-1][1] += raw[1:]
        else:
            out.append([lineno, raw])
    return out


def ics_unescape(value):
    return value.replace('\\n', '\n').replace('\\N', '\n').replace('\\,', ',').replace('\\;', ';').replace('\\\\', '\\')


def ics_date(value):
    value = (value or '').strip()
    m = re.fullmatch(r'(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})?(Z)?)?', value)
    if not m:
        return value
    y, mo, d, hh, mm, ss, z = m.groups()
    if hh is None:
        return '%s-%s-%s' % (y, mo, d)
    return '%s-%s-%sT%s:%s:%s%s' % (y, mo, d, hh, mm, ss or '00', 'Z' if z else '')


def ics_prop(line):
    in_quote = False
    for k, ch in enumerate(line):
        if ch == '"':
            in_quote = not in_quote
        elif ch == ':' and not in_quote:
            head, value = line[:k], line[k + 1:]
            break
    else:
        return None
    parts = re.split(r';(?=(?:[^"]*"[^"]*")*[^"]*$)', head)
    params = {}
    for p in parts[1:]:
        if '=' in p:
            key, val = p.split('=', 1)
            params[key.upper()] = val.strip('"')
    return parts[0].upper(), params, value


def extract_ics(path, rel):
    data = read_bytes(path)
    if data is None:
        return None
    lines = unfold_ics(decode(data))
    events = []
    current = None
    calname = ''
    for lineno, raw in lines:
        upper = raw.strip().upper()
        if upper == 'BEGIN:VEVENT':
            current = {'title': '', 'when': '', 'until': '', 'where': '', 'attendees': [], 'line': lineno, 'description': ''}
            continue
        if upper == 'END:VEVENT':
            if current is not None and len(events) < MAX_MESSAGES:
                events.append(current)
            current = None
            continue
        prop = ics_prop(raw)
        if prop is None:
            continue
        name, params, value = prop
        if current is None:
            if name == 'X-WR-CALNAME':
                calname = ics_unescape(value).strip()
            continue
        if name == 'SUMMARY':
            current['title'] = ics_unescape(value).strip()
        elif name == 'DTSTART':
            current['when'] = ics_date(value)
        elif name == 'DTEND':
            current['until'] = ics_date(value)
        elif name == 'LOCATION':
            current['where'] = ics_unescape(value).strip()
        elif name == 'DESCRIPTION':
            current['description'] = ics_unescape(value).strip()
        elif name == 'ATTENDEE':
            who = params.get('CN') or re.sub(r'^mailto:', '', value.strip(), flags=re.I)
            if who:
                current['attendees'].append(who)
    if not events and 'BEGIN:VCALENDAR' not in decode(data[:4096]).upper():
        return None
    parts = []
    out_events = []
    for ev in events:
        desc = ev.pop('description')
        row = [ev['title'] or '(sin título)', ev['when']]
        if ev['until']:
            row.append('hasta ' + ev['until'])
        if ev['where']:
            row.append(ev['where'])
        if ev['attendees']:
            row.append(', '.join(ev['attendees']))
        parts.append(' — '.join(x for x in row if x) + ('\n' + desc if desc else ''))
        out_events.append(ev)
    stem = os.path.splitext(os.path.basename(rel))[0]
    return result(calname or stem, '\n\n'.join(parts), {'events': len(out_events)}, (), (), (), (), out_events)


def extract_csv(path, rel):
    data = read_bytes(path)
    if data is None:
        return None
    text = decode(data)
    sample = text[:4096]
    delim = '\t' if os.path.splitext(rel)[1].lower() == '.tsv' else ','
    if delim == ',':
        try:
            delim = csv.Sniffer().sniff(sample, delimiters=',;\t|').delimiter
        except csv.Error:
            delim = ','
    csv.field_size_limit(1 << 20)
    rows = []
    count = 0
    header = None
    try:
        for row in csv.reader(text.splitlines(), delimiter=delim):
            if header is None:
                header = row
                continue
            count += 1
            if len(rows) < CSV_ROWS:
                rows.append(row)
            if count >= CSV_COUNT:
                break
    except csv.Error:
        pass
    if header is None:
        return None
    def line(cells):
        return ' | '.join(c.strip()[:500] for c in cells)
    out = [line(header)] + [line(r) for r in rows]
    meta = {'columns': [c.strip() for c in header][:200], 'rows': count}
    if count >= CSV_COUNT:
        meta['truncated'] = True
    return result(os.path.splitext(os.path.basename(rel))[0], '\n'.join(out), meta)


def rtf_to_text(source):
    out = []
    stack = []
    ignore = False
    skip_chars = 0
    uc = 1
    for m in RTF_TOKEN.finditer(source):
        word, num, hexa, esc, star, brace, plain = m.groups()
        if brace == '{':
            stack.append((ignore, uc))
        elif brace == '}':
            if stack:
                ignore, uc = stack.pop()
        elif star:
            ignore = True
        elif word:
            if word in RTF_SKIP:
                ignore = True
            elif word == 'uc' and num:
                uc = int(num)
            elif ignore:
                continue
            elif word in ('par', 'line', 'row', 'sect', 'page'):
                out.append('\n')
            elif word in ('tab', 'cell'):
                out.append('\t')
            elif word == 'u' and num:
                code = int(num)
                out.append(chr(code + 65536 if code < 0 else code))
                skip_chars = uc
            elif word == 'emdash':
                out.append('—')
            elif word == 'endash':
                out.append('–')
        elif hexa:
            if not ignore:
                if skip_chars:
                    skip_chars -= 1
                else:
                    out.append(bytes([int(hexa, 16)]).decode('cp1252', errors='replace'))
        elif esc:
            if not ignore:
                out.append(esc)
        elif plain and not ignore:
            plain = plain.replace('\r', '').replace('\n', '')
            if skip_chars:
                cut = min(skip_chars, len(plain))
                plain = plain[cut:]
                skip_chars -= cut
            out.append(plain)
    text = ''.join(out)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def extract_rtf(path, rel):
    data = read_bytes(path, MAX_UNZIPPED)
    if data is None or not data.lstrip().startswith(b'{\\rtf'):
        return None
    text = rtf_to_text(data.decode('latin-1'))
    return result(first_line(text, os.path.splitext(os.path.basename(rel))[0]), text)


def extract_txt(path, rel):
    data = read_bytes(path)
    if data is None:
        return None
    text = decode(data[:MAX_TEXT * 2]).replace('\r\n', '\n').replace('\r', '\n')
    return result(first_line(text, os.path.splitext(os.path.basename(rel))[0]), text)


def extract_pdf(path, rel):
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    logging.getLogger('pypdf').setLevel(logging.ERROR)  # avisos de fuentes y codificación de PDFs ajenos, no del análisis
    if os.path.getsize(path) > MAX_FILE:
        return None
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            if not reader.decrypt(''):
                return None
        pages = []
        total = len(reader.pages)
        for page in reader.pages[:MAX_PDF_PAGES]:
            try:
                pages.append((page.extract_text() or '').strip())
            except Exception:
                pages.append('')
            if sum(len(p) for p in pages) > MAX_TEXT:
                break
        info = reader.metadata
    except Exception:
        return None
    meta = {'pages': total}
    title = ''
    if info:
        title = str(info.get('/Title') or '').strip()
        if info.get('/Author'):
            meta['author'] = str(info.get('/Author')).strip()
    text = '\n\n'.join(p for p in pages if p)
    return result(title or first_line(text, os.path.splitext(os.path.basename(rel))[0]), text, meta)


HANDLERS = {
    '.txt': extract_txt,
    '.pdf': extract_pdf,
    '.docx': extract_docx,
    '.odt': extract_odt,
    '.html': extract_html,
    '.htm': extract_html,
    '.eml': extract_eml,
    '.mbox': extract_mbox,
    '.ics': extract_ics,
    '.csv': extract_csv,
    '.tsv': extract_csv,
    '.rtf': extract_rtf,
}


def extract(root, rel):
    handler = HANDLERS.get(os.path.splitext(rel)[1].lower())
    if handler is None:
        return None
    base = os.path.realpath(root)
    path = os.path.realpath(os.path.join(base, rel))
    if path != base and not path.startswith(base + os.sep):
        return None
    if not os.path.isfile(path):
        return None
    try:
        return handler(path, rel)
    except (OSError, ValueError, UnicodeError, zipfile.BadZipFile, KeyError, RecursionError):
        return None
