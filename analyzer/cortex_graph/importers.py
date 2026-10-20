import json
import os
import re
from collections import Counter
from datetime import datetime, timezone

MAX_MESSAGES = 20000
MAX_CONVERSATIONS = 5000
MAX_TEXT = 20000
MAX_JSON_BYTES = 600 * 1024 * 1024
MAX_TEXT_FILE = 200 * 1024 * 1024

USER_ROLES = {'user', 'human', 'usuario', 'me', 'yo', 'tu', 'tú', 'you'}
ASSISTANT_ROLES = {'assistant', 'ai', 'bot', 'model', 'asistente', 'gpt'}
MD_ROLE_RE = re.compile(r'^\s*(?:#{1,6}\s*)?(?:[-*>]\s+)?(\*\*|__)?(user|assistant|human|usuario|asistente|you|tú|tu|yo|ai|bot|system)(?:\1)?(:)?(\1)?[ \t]*(.*)$', re.I)
WA_DATE = r'(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})'
WA_TIME = r'(\d{1,2})[:.](\d{2})(?::(\d{2}))?\s*([aApP]\.?\s?[mM]\.?)?'
WA_ANDROID = re.compile(r'^' + WA_DATE + r',?\s+' + WA_TIME + r'\s*[-–]\s(.*)$')
WA_IOS = re.compile(r'^\[' + WA_DATE + r',?\s+' + WA_TIME + r'\]\s?(.*)$')
WA_MEDIA = re.compile(r'^(<(multimedia omitido|media omitted|archivo omitido|attached: [^>]*|adjunto: [^>]*)>|(imagen|video|vídeo|audio|sticker|gif|documento|image|document) (omitid[oa]|omitted)|null|se eliminó este mensaje|this message was deleted|eliminaste este mensaje|you deleted this message|mensaje eliminado)\.?$', re.I)
SRT_TIME = re.compile(r'(\d{1,2}:)?\d{2}:\d{2}[,.]\d{3}\s*-->\s*(\d{1,2}:)?\d{2}:\d{2}[,.]\d{3}')
SPEAKER_RE = re.compile(r'^([^\W\d_][^:\n]{0,40}?):\s+(.*)$', re.S)
VTT_VOICE = re.compile(r'^<v(?:\.[^\s>]+)?\s+([^>]+)>(.*)$', re.S)
TAG_RE = re.compile(r'<[^>]+>')
DAY_FILE = re.compile(r'(^|/)([^/]+)/(\d{4}-\d{2}-\d{2})\.json$')
SLACK_SKIP = {'channel_join', 'channel_leave', 'channel_topic', 'channel_purpose', 'channel_name', 'channel_archive', 'channel_unarchive', 'group_join', 'group_leave'}


def stamp(dt):
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return dt.strftime('%Y-%m-%dT%H:%M:%S')


def iso(value):
    if value is None or value == '' or isinstance(value, bool):
        return None
    try:
        if isinstance(value, str):
            text = value.strip()
            if re.fullmatch(r'-?\d+(\.\d+)?', text):
                value = float(text)
            else:
                return stamp(datetime.fromisoformat(text.replace('Z', '+00:00')))
        if isinstance(value, (int, float)):
            if value > 1e11:
                value = value / 1000.0
            return datetime.fromtimestamp(value, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    except (ValueError, OverflowError, OSError):
        return None
    return None


def role_of(value):
    key = str(value or '').strip().casefold()
    if key in USER_ROLES:
        return 'user'
    if key in ASSISTANT_ROLES:
        return 'assistant'
    return 'other'


def clip(text, limit=MAX_TEXT):
    text = (text or '').strip()
    return text[:limit] if len(text) > limit else text


def make_message(i, role, author, time, text, line=0):
    return {'i': i, 'role': role, 'author': author or '', 'time': time, 'text': text, 'line': line}


def make_conv(cid, source, title, messages, started=None, ended=None):
    times = sorted(m['time'] for m in messages if m['time'])
    if started is None and times:
        started = times[0]
    if ended is None and times:
        ended = times[-1]
    if not title:
        first = next((m['text'] for m in messages if m['role'] == 'user'), '') or next((m['text'] for m in messages), '')
        title = ' '.join(first.split())[:80]
    return {
        'id': str(cid),
        'source': source,
        'title': title or str(cid),
        'started': started,
        'ended': ended,
        'participants': sorted({m['author'] for m in messages if m['author']}),
        'messages': messages,
    }


def decode(data):
    if data[:3] == b'\xef\xbb\xbf':
        data = data[3:]
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        return data.decode('cp1252', errors='replace')


def read_text(path, limit=MAX_TEXT_FILE):
    with open(path, 'rb') as f:
        return decode(f.read(limit))


def read_json(path):
    if os.path.getsize(path) > MAX_JSON_BYTES:
        return None
    try:
        with open(path, 'rb') as f:
            return json.loads(decode(f.read()))
    except (ValueError, OSError):
        return None


def head_lines(head):
    text = decode(head)
    lines = text.splitlines()
    if lines and len(head) >= 65536:
        lines = lines[:-1]
    return lines


def parse_json_lines(lines, limit=12):
    out = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except ValueError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
        if len(out) >= limit:
            break
    return out


def detect_whatsapp(lines):
    hits = 0
    for line in lines[:60]:
        line = line.lstrip('‎‏﻿')
        if WA_ANDROID.match(line) or WA_IOS.match(line):
            hits += 1
    return hits >= 2 or (hits >= 1 and len([x for x in lines if x.strip()]) <= 3)


def md_turn(line):
    m = MD_ROLE_RE.match(line)
    if not m:
        return None
    name, colon, rest = m.group(2), m.group(3), m.group(5)
    if colon:
        return name, rest
    if line.lstrip().startswith('#') and not rest.strip():
        return name, ''
    return None


def detect_markdown(lines):
    roles = set()
    for line in lines[:400]:
        turn = md_turn(line)
        if turn:
            roles.add(role_of(turn[0]))
    return 'user' in roles and 'assistant' in roles


def detect(rel, head):
    name = rel.replace('\\', '/').lower()
    base = name.rsplit('/', 1)[-1]
    ext = os.path.splitext(base)[1]
    if ext == '.json':
        if base == 'channels.json':
            return 'slack'
        text = decode(head)
        if DAY_FILE.search(name) and re.search(r'"ts"\s*:', text) and re.search(r'"(text|user|type)"\s*:', text):
            return 'slack'
        if '"chat_messages"' in text:
            return 'claude'
        if '"mapping"' in text and ('"current_node"' in text or '"message"' in text):
            return 'chatgpt'
        if '"messages"' in text and '"author"' in text and '"timestamp"' in text and ('"guild"' in text or '"channel"' in text):
            return 'discord'
        if '"messages"' in text and ('"from_id"' in text or '"date_unixtime"' in text or re.search(r'"type"\s*:\s*"(personal_chat|private_group|public_channel|private_supergroup|saved_messages|bot_chat|private_channel|public_supergroup)"', text)):
            return 'telegram'
        if re.search(r'"(role|sender|author|speaker)"\s*:', text) and re.search(r'"(content|text|message|body)"\s*:', text):
            return 'generic'
        return None
    if ext == '.jsonl':
        objs = parse_json_lines(head_lines(head))
        for obj in objs:
            if obj.get('type') in ('user', 'assistant') and isinstance(obj.get('message'), dict) and ('sessionId' in obj or 'cwd' in obj or 'uuid' in obj):
                return 'claude-code'
        for obj in objs:
            if ('role' in obj and 'content' in obj) or (('author' in obj or 'sender' in obj) and ('text' in obj or 'content' in obj)):
                return 'generic'
        return None
    if ext == '.srt':
        return 'srt' if SRT_TIME.search(decode(head)) else None
    if ext == '.vtt':
        return 'vtt' if decode(head).lstrip('﻿').startswith('WEBVTT') else None
    if ext in ('.txt', '.md', '.markdown', ''):
        lines = head_lines(head)
        if ext in ('.txt', '') and detect_whatsapp(lines):
            return 'whatsapp'
        if detect_markdown(lines):
            return 'generic'
    return None


def walk_chatgpt(conv):
    mapping = conv.get('mapping')
    if not isinstance(mapping, dict) or not mapping:
        return []
    node = conv.get('current_node')
    if node not in mapping:
        leaves = [k for k, v in mapping.items() if isinstance(v, dict) and not v.get('children')]
        def stamp_of(k):
            msg = mapping[k].get('message') or {}
            return (msg.get('create_time') or 0, k)
        node = max(leaves, key=stamp_of) if leaves else sorted(mapping)[-1]
    chain = []
    seen = set()
    while node is not None and node in mapping and node not in seen and len(chain) <= 200000:
        seen.add(node)
        chain.append(mapping[node])
        node = mapping[node].get('parent')
    chain.reverse()
    return chain


def chatgpt_text(content):
    if not isinstance(content, dict):
        return clip(content) if isinstance(content, str) else ''
    ctype = content.get('content_type')
    if ctype in ('thoughts', 'reasoning_recap', 'system_error', 'user_editable_context', 'model_editable_context'):
        return ''
    out = []
    parts = content.get('parts')
    if isinstance(parts, list):
        for part in parts:
            if isinstance(part, str):
                if part.strip():
                    out.append(part)
            elif isinstance(part, dict):
                value = part.get('text')
                if isinstance(value, str) and value.strip():
                    out.append(value)
    elif isinstance(content.get('text'), str):
        out.append(content['text'])
    return clip('\n'.join(out))


def load_chatgpt(path):
    data = read_json(path)
    if isinstance(data, dict):
        data = data.get('conversations') or [data]
    out = []
    for n, conv in enumerate(data if isinstance(data, list) else []):
        if len(out) >= MAX_CONVERSATIONS:
            break
        if not isinstance(conv, dict):
            continue
        messages = []
        for node in walk_chatgpt(conv):
            msg = node.get('message') if isinstance(node, dict) else None
            if not isinstance(msg, dict):
                continue
            role = (msg.get('author') or {}).get('role')
            if role not in ('user', 'assistant'):
                continue
            meta = msg.get('metadata') or {}
            if meta.get('is_visually_hidden_from_conversation'):
                continue
            text = chatgpt_text(msg.get('content'))
            if not text:
                continue
            if len(messages) >= MAX_MESSAGES:
                break
            messages.append(make_message(len(messages), role, role, iso(msg.get('create_time')), text))
        if not messages:
            continue
        cid = conv.get('conversation_id') or conv.get('id') or n
        out.append(make_conv(cid, 'chatgpt', (conv.get('title') or '').strip(), messages, iso(conv.get('create_time')), iso(conv.get('update_time'))))
    return out


def blocks_text(blocks):
    out = []
    for block in blocks or []:
        if isinstance(block, str):
            out.append(block)
        elif isinstance(block, dict):
            if block.get('type', 'text') == 'text' and isinstance(block.get('text'), str):
                out.append(block['text'])
    return '\n'.join(x for x in out if x.strip())


def load_claude(path):
    data = read_json(path)
    if isinstance(data, dict):
        data = data.get('conversations') or [data]
    out = []
    for n, conv in enumerate(data if isinstance(data, list) else []):
        if len(out) >= MAX_CONVERSATIONS:
            break
        if not isinstance(conv, dict):
            continue
        messages = []
        for msg in conv.get('chat_messages') or []:
            if not isinstance(msg, dict) or len(messages) >= MAX_MESSAGES:
                continue
            role = role_of(msg.get('sender') or msg.get('role'))
            text = blocks_text(msg.get('content')) if isinstance(msg.get('content'), list) else ''
            if not text:
                text = msg.get('text') if isinstance(msg.get('text'), str) else ''
            text = clip(text)
            if not text:
                continue
            author = role if role != 'other' else str(msg.get('sender') or '')
            messages.append(make_message(len(messages), role, author, iso(msg.get('created_at')), text))
        if not messages:
            continue
        cid = conv.get('uuid') or conv.get('id') or n
        out.append(make_conv(cid, 'claude', (conv.get('name') or conv.get('title') or '').strip(), messages, iso(conv.get('created_at')), iso(conv.get('updated_at'))))
    return out


def load_claude_code(path, rel):
    messages = []
    session = None
    with open(path, 'rb') as f:
        for lineno, raw in enumerate(f, 1):
            if len(messages) >= MAX_MESSAGES:
                break
            raw = raw.strip()
            if not raw or raw[:1] != b'{':
                continue
            try:
                obj = json.loads(raw.decode('utf-8', errors='replace'))
            except ValueError:
                continue
            if not isinstance(obj, dict):
                continue
            kind = obj.get('type')
            if kind not in ('user', 'assistant') or obj.get('isMeta') or obj.get('isSidechain'):
                continue
            msg = obj.get('message')
            if not isinstance(msg, dict):
                continue
            content = msg.get('content')
            text = content if isinstance(content, str) else blocks_text(content) if isinstance(content, list) else ''
            text = clip(text)
            if not text or text.startswith('<local-command') or text.startswith('<command-'):
                continue
            session = session or obj.get('sessionId')
            messages.append(make_message(len(messages), kind, kind, iso(obj.get('timestamp')), text, lineno))
    if not messages:
        return []
    return [make_conv(session or os.path.splitext(os.path.basename(rel))[0], 'claude-code', '', messages)]


def wa_clean(line):
    return line.lstrip('‎‏﻿').replace(' ', ' ').replace(' ', ' ')


def wa_header(line):
    m = WA_ANDROID.match(line) or WA_IOS.match(line)
    return m.groups() if m else None


def wa_datetime(g, order):
    a, b, year, hh, mm, ss, ampm = g[:7]
    a, b, hh, mm, ss = int(a), int(b), int(hh), int(mm), int(ss or 0)
    day, month = (a, b) if order == 'dmy' else (b, a)
    year = int(year)
    if year < 100:
        year += 2000
    if ampm:
        pm = ampm.strip().lower().startswith('p')
        hh = hh % 12 + (12 if pm else 0)
    try:
        return datetime(year, month, day, hh, mm, ss).strftime('%Y-%m-%dT%H:%M:%S')
    except ValueError:
        return None


def load_whatsapp(path, rel):
    entries = []
    order_votes = Counter()
    with open(path, 'rb') as f:
        for lineno, raw in enumerate(f, 1):
            line = wa_clean(raw.decode('utf-8', errors='replace').rstrip('\r\n'))
            g = wa_header(line)
            if g:
                if int(g[0]) > 12:
                    order_votes['dmy'] += 1
                elif int(g[1]) > 12:
                    order_votes['mdy'] += 1
                entries.append([g, g[-1], lineno])
            elif entries:
                if len(entries[-1][1]) < MAX_TEXT:
                    entries[-1][1] += '\n' + line
            if len(entries) > MAX_MESSAGES * 4:
                break
    order = 'mdy' if order_votes['mdy'] > order_votes['dmy'] else 'dmy'
    messages = []
    for g, body, lineno in entries:
        if ': ' not in body:
            continue
        author, text = body.split(': ', 1)
        author = author.strip().lstrip('~ ').strip()
        text = text.strip('\u200e\u200f \t\r\n')
        if not text or not author or WA_MEDIA.match(text):
            continue
        if len(messages) >= MAX_MESSAGES:
            break
        messages.append(make_message(len(messages), 'other', author, wa_datetime(g, order), clip(text), lineno))
    if not messages:
        return []
    stem = os.path.splitext(os.path.basename(rel))[0]
    return [make_conv('0', 'whatsapp', stem, messages)]


def flatten_telegram(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ''.join(x if isinstance(x, str) else str(x.get('text', '')) if isinstance(x, dict) else '' for x in value)
    return ''


def telegram_chat(chat, n):
    messages = []
    for msg in chat.get('messages') or []:
        if not isinstance(msg, dict) or msg.get('type', 'message') != 'message':
            continue
        text = clip(flatten_telegram(msg.get('text')))
        if not text:
            continue
        if len(messages) >= MAX_MESSAGES:
            break
        time = iso(msg.get('date')) or iso(msg.get('date_unixtime'))
        messages.append(make_message(len(messages), 'other', str(msg.get('from') or msg.get('actor') or ''), time, text))
    if not messages:
        return None
    return make_conv(chat.get('id', n), 'telegram', str(chat.get('name') or '').strip(), messages)


def load_telegram(path):
    data = read_json(path)
    if not isinstance(data, dict):
        return []
    chats = data.get('chats')
    chats = chats.get('list') if isinstance(chats, dict) else None
    if not isinstance(chats, list):
        chats = [data]
    out = []
    for n, chat in enumerate(chats):
        if len(out) >= MAX_CONVERSATIONS:
            break
        conv = telegram_chat(chat, n) if isinstance(chat, dict) else None
        if conv:
            out.append(conv)
    return out


def load_discord(path):
    data = read_json(path)
    if isinstance(data, list):
        data = {'messages': data}
    if not isinstance(data, dict):
        return []
    messages = []
    for msg in data.get('messages') or []:
        if not isinstance(msg, dict) or len(messages) >= MAX_MESSAGES:
            continue
        text = clip(msg.get('content') if isinstance(msg.get('content'), str) else '')
        if not text:
            continue
        author = msg.get('author') if isinstance(msg.get('author'), dict) else {}
        name = author.get('nickname') or author.get('name') or ''
        messages.append(make_message(len(messages), 'other', str(name), iso(msg.get('timestamp')), text))
    if not messages:
        return []
    channel = data.get('channel') if isinstance(data.get('channel'), dict) else {}
    guild = data.get('guild') if isinstance(data.get('guild'), dict) else {}
    title = str(channel.get('name') or '').strip()
    if title and guild.get('name'):
        title = '%s / %s' % (guild['name'], title)
    return [make_conv(channel.get('id') or '0', 'discord', title, messages)]


def split_speaker(text):
    m = VTT_VOICE.match(text)
    if m:
        return m.group(1).strip(), TAG_RE.sub('', m.group(2)).strip()
    text = TAG_RE.sub('', text).strip()
    m = SPEAKER_RE.match(text)
    if m and len(m.group(1).split()) <= 4:
        return m.group(1).strip(), m.group(2).strip()
    return '', text


def load_subtitles(path, rel, fmt):
    lines = read_text(path).splitlines()
    messages = []
    i = 0
    n = len(lines)
    while i < n and len(messages) < MAX_MESSAGES:
        if not SRT_TIME.search(lines[i]):
            i += 1
            continue
        start = i - 1 if i > 0 and lines[i - 1].strip() else i
        j = i + 1
        body = []
        while j < n and lines[j].strip():
            body.append(lines[j].strip())
            j += 1
        voice = ''
        parts = []
        for piece in body:
            who, text = split_speaker(piece)
            voice = voice or who
            parts.append(text)
        text = clip(' '.join(x for x in parts if x))
        if text:
            messages.append(make_message(len(messages), 'other', voice, None, text, start + 1))
        i = j
    if not messages:
        return []
    stem = os.path.splitext(os.path.basename(rel))[0]
    return [make_conv('0', fmt, stem, messages)]


def slack_users(folder):
    names = {}
    data = read_json(os.path.join(folder, 'users.json')) if os.path.isfile(os.path.join(folder, 'users.json')) else None
    for user in data if isinstance(data, list) else []:
        if isinstance(user, dict) and user.get('id'):
            profile = user.get('profile') or {}
            names[user['id']] = user.get('real_name') or profile.get('real_name') or profile.get('display_name') or user.get('name') or user['id']
    return names


def slack_channel(folder, channel, users):
    cdir = os.path.join(folder, channel)
    if not os.path.isdir(cdir):
        return None
    mention = re.compile(r'<@([A-Z0-9]+)>')
    messages = []
    for fname in sorted(os.listdir(cdir)):
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}\.json', fname) or len(messages) >= MAX_MESSAGES:
            continue
        data = read_json(os.path.join(cdir, fname))
        for msg in data if isinstance(data, list) else []:
            if not isinstance(msg, dict) or msg.get('subtype') in SLACK_SKIP or len(messages) >= MAX_MESSAGES:
                continue
            text = msg.get('text') if isinstance(msg.get('text'), str) else ''
            text = clip(mention.sub(lambda m: '@' + users.get(m.group(1), m.group(1)), text))
            if not text:
                continue
            profile = msg.get('user_profile') if isinstance(msg.get('user_profile'), dict) else {}
            uid = msg.get('user') or msg.get('username') or msg.get('bot_id') or ''
            author = users.get(uid) or profile.get('real_name') or profile.get('display_name') or uid
            messages.append(make_message(len(messages), 'other', str(author), iso(msg.get('ts')), text))
    if not messages:
        return None
    return make_conv(channel, 'slack', '#' + channel, messages)


def load_slack(root, rel):
    path = os.path.join(root, rel)
    folder = os.path.dirname(path)
    users = slack_users(folder)
    if os.path.basename(rel).lower() == 'channels.json':
        data = read_json(path)
        names = [c.get('name') for c in data if isinstance(c, dict) and c.get('name')] if isinstance(data, list) else []
        out = []
        for name in sorted(set(names)):
            if len(out) >= MAX_CONVERSATIONS:
                break
            conv = slack_channel(folder, name, users)
            if conv:
                out.append(conv)
        return out
    parent = os.path.dirname(folder)
    if os.path.isfile(os.path.join(parent, 'channels.json')):
        return []
    users = slack_users(parent)
    conv = slack_channel(parent, os.path.basename(folder), users)
    return [conv] if conv else []


def generic_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return blocks_text(value)
    if isinstance(value, dict):
        for key in ('text', 'content', 'parts'):
            if key in value:
                return generic_text(value[key])
    return ''


def generic_message(obj, index, line=0):
    if not isinstance(obj, dict):
        return None
    raw_role = obj.get('role') or obj.get('sender') or obj.get('author') or obj.get('from') or obj.get('speaker') or obj.get('name')
    if isinstance(raw_role, dict):
        raw_role = raw_role.get('role') or raw_role.get('name')
    text = ''
    for key in ('content', 'text', 'message', 'body'):
        if key in obj:
            text = generic_text(obj[key])
            if text.strip():
                break
    text = clip(text)
    if not text:
        return None
    role = role_of(raw_role)
    author = str(raw_role or '')
    if role != 'other':
        author = role
    time = None
    for key in ('timestamp', 'time', 'created_at', 'date', 'ts', 'created', 'create_time'):
        if key in obj:
            time = iso(obj[key])
            if time:
                break
    return make_message(index, role, author, time, text, line)


def generic_conv(obj, n):
    items = obj.get('messages') or obj.get('chat_messages') or obj.get('conversation') or obj.get('turns')
    if not isinstance(items, list):
        return None
    messages = []
    for item in items:
        if len(messages) >= MAX_MESSAGES:
            break
        msg = generic_message(item, len(messages))
        if msg:
            messages.append(msg)
    if not messages:
        return None
    return make_conv(obj.get('id') or obj.get('uuid') or n, 'generic', str(obj.get('title') or obj.get('name') or '').strip(), messages)


def load_generic_jsonl(path, rel):
    messages = []
    with open(path, 'rb') as f:
        for lineno, raw in enumerate(f, 1):
            if len(messages) >= MAX_MESSAGES:
                break
            raw = raw.strip()
            if not raw or raw[:1] != b'{':
                continue
            try:
                obj = json.loads(raw.decode('utf-8', errors='replace'))
            except ValueError:
                continue
            msg = generic_message(obj, len(messages), lineno)
            if msg:
                messages.append(msg)
    if not messages:
        return []
    return [make_conv('0', 'generic', os.path.splitext(os.path.basename(rel))[0], messages)]


def load_generic_json(path, rel):
    data = read_json(path)
    if isinstance(data, dict):
        if any(k in data for k in ('messages', 'chat_messages', 'turns', 'conversation')):
            conv = generic_conv(data, 0)
            return [conv] if conv else []
        if isinstance(data.get('conversations'), list):
            data = data['conversations']
        else:
            data = [data]
    if not isinstance(data, list):
        return []
    if data and all(isinstance(x, dict) and any(k in x for k in ('messages', 'chat_messages', 'turns')) for x in data):
        out = []
        for n, obj in enumerate(data):
            if len(out) >= MAX_CONVERSATIONS:
                break
            conv = generic_conv(obj, n)
            if conv:
                out.append(conv)
        return out
    messages = []
    for item in data:
        if len(messages) >= MAX_MESSAGES:
            break
        msg = generic_message(item, len(messages))
        if msg:
            messages.append(msg)
    if not messages:
        return []
    return [make_conv('0', 'generic', os.path.splitext(os.path.basename(rel))[0], messages)]


def load_markdown(path, rel):
    messages = []
    current = None
    with open(path, 'rb') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.decode('utf-8', errors='replace').rstrip('\r\n')
            turn = md_turn(line)
            if turn:
                if current:
                    messages.append(current)
                if len(messages) >= MAX_MESSAGES:
                    current = None
                    break
                role = role_of(turn[0])
                author = role if role != 'other' else turn[0]
                current = [role, author, turn[1], lineno]
            elif current and len(current[2]) < MAX_TEXT:
                current[2] += '\n' + line
    if current:
        messages.append(current)
    out = []
    for role, author, text, lineno in messages:
        text = clip(text)
        if text and author.casefold() != 'system':
            out.append(make_message(len(out), role, author, None, text, lineno))
    if not out:
        return []
    return [make_conv('0', 'generic', os.path.splitext(os.path.basename(rel))[0], out)]


def load(root, rel, fmt=None):
    path = os.path.join(root, rel)
    if fmt is None:
        try:
            with open(path, 'rb') as f:
                fmt = detect(rel, f.read(65536))
        except OSError:
            return []
    try:
        if fmt == 'chatgpt':
            return load_chatgpt(path)
        if fmt == 'claude':
            return load_claude(path)
        if fmt == 'claude-code':
            return load_claude_code(path, rel)
        if fmt == 'whatsapp':
            return load_whatsapp(path, rel)
        if fmt == 'telegram':
            return load_telegram(path)
        if fmt == 'slack':
            return load_slack(root, rel)
        if fmt == 'discord':
            return load_discord(path)
        if fmt in ('srt', 'vtt'):
            return load_subtitles(path, rel, fmt)
        if fmt == 'generic':
            ext = os.path.splitext(rel)[1].lower()
            if ext == '.jsonl':
                return load_generic_jsonl(path, rel)
            if ext == '.json':
                return load_generic_json(path, rel)
            return load_markdown(path, rel)
    except OSError:
        return []
    return []


def user_names(conversations):
    names = set()
    for conv in conversations:
        authors = Counter()
        has_user = False
        for msg in conv['messages']:
            if msg['author']:
                authors[msg['author']] += 1
            if msg['role'] == 'user':
                has_user = True
                if msg['author']:
                    names.add(msg['author'])
        if not has_user and len(authors) == 2:
            top = sorted(authors.items(), key=lambda kv: (-kv[1], kv[0]))
            names.add(top[0][0])
    return names
