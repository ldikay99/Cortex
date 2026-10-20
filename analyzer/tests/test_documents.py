import zipfile

import pytest

from cortex_graph import documents

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def make_docx(path, body, extra=None):
    doc = '<?xml version="1.0"?><w:document %s><w:body>%s</w:body></w:document>' % (W, body)
    styles = '<w:styles %s><w:style w:styleId="Ttulo1"><w:name w:val="heading 1"/></w:style><w:style w:styleId="Heading2"><w:name w:val="heading 2"/></w:style></w:styles>' % W
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('word/document.xml', doc)
        z.writestr('word/styles.xml', styles)
        for k, v in (extra or {}).items():
            z.writestr(k, v)


def para(text, style=None):
    ppr = '<w:pPr><w:pStyle w:val="%s"/></w:pPr>' % style if style else ''
    return '<w:p>%s<w:r><w:t>%s</w:t></w:r></w:p>' % (ppr, text)


def test_supports():
    assert documents.supports('a/b.PDF') and documents.supports('x.mbox') and documents.supports('t.tsv')
    assert not documents.supports('a.md') and not documents.supports('a.py')


def test_txt_and_missing(tmp_path):
    (tmp_path / 'n.txt').write_bytes('\n  Mi nota\nsegunda línea\r\n'.encode('cp1252'))
    r = documents.extract(str(tmp_path), 'n.txt')
    assert r['title'] == 'Mi nota' and 'segunda línea' in r['text']
    assert documents.extract(str(tmp_path), 'nope.txt') is None
    assert documents.extract(str(tmp_path), '../x.txt') is None
    assert documents.extract(str(tmp_path), 'a.xyz') is None


def test_docx(tmp_path):
    body = para('Informe', 'Ttulo1') + para('Intro del informe') + para('Detalle', 'Heading2') + para('Texto detalle') + para('Cierre', 'Ttulo1') + para('Fin')
    core = '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Informe anual</dc:title><dc:creator>Ana</dc:creator><cp:keywords>a, b</cp:keywords></cp:coreProperties>'
    make_docx(tmp_path / 'i.docx', body, {'docProps/core.xml': core})
    r = documents.extract(str(tmp_path), 'i.docx')
    assert r['title'] == 'Informe anual' and r['meta']['author'] == 'Ana' and r['tags'] == ['a', 'b']
    assert r['sections'] == [(1, 'Informe', 1, 4), (2, 'Detalle', 3, 4), (1, 'Cierre', 5, 6)]
    assert r['text'].splitlines()[1] == 'Intro del informe'


def test_docx_rejects_entities_and_bombs(tmp_path, monkeypatch):
    evil = '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x "boom">]><w:document %s><w:body>%s</w:body></w:document>' % (W, para('&x;'))
    with zipfile.ZipFile(tmp_path / 'e.docx', 'w') as z:
        z.writestr('word/document.xml', evil)
    assert documents.extract(str(tmp_path), 'e.docx') is None
    make_docx(tmp_path / 'b.docx', para('x'))
    monkeypatch.setattr(documents, 'MAX_UNZIPPED', 10)
    assert documents.extract(str(tmp_path), 'b.docx') is None
    (tmp_path / 'bad.docx').write_bytes(b'not a zip')
    assert documents.extract(str(tmp_path), 'bad.docx') is None


def test_odt(tmp_path):
    content = (
        '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:xlink="http://www.w3.org/1999/xlink"><office:body><office:text>'
        '<text:h text:outline-level="1">Titulo</text:h><text:p>Hola<text:s text:c="2"/>mundo <text:a xlink:href="http://e.org/x">link</text:a></text:p>'
        '<text:h text:outline-level="2">Sub</text:h><text:p>Cuerpo</text:p></office:text></office:body></office:document-content>'
    )
    with zipfile.ZipFile(tmp_path / 'a.odt', 'w') as z:
        z.writestr('content.xml', content)
    r = documents.extract(str(tmp_path), 'a.odt')
    assert r['title'] == 'Titulo' and r['links'] == ['http://e.org/x']
    assert r['sections'] == [(1, 'Titulo', 1, 4), (2, 'Sub', 3, 4)]
    assert r['text'].splitlines()[1] == 'Hola mundo link'


def test_html(tmp_path):
    html = '<html><head><title>Pagina</title><meta name="keywords" content="x, y"><style>p{}</style></head><body><h1>Uno</h1><p>Texto <a href="b.html">b</a> &amp; mas</p><script>var a=1;</script><h2>Dos</h2><p>Fin</p><a href="javascript:x()">no</a></body></html>'
    (tmp_path / 'p.html').write_text(html, encoding='utf-8')
    r = documents.extract(str(tmp_path), 'p.html')
    assert r['title'] == 'Pagina' and r['links'] == ['b.html'] and r['tags'] == ['x', 'y']
    assert r['sections'] == [(1, 'Uno', 1, 5), (2, 'Dos', 3, 5)]
    assert 'var a' not in r['text'] and 'Texto b & mas' in r['text']


def test_eml(tmp_path):
    eml = 'From: Ana <ana@x.org>\nTo: luis@x.org\nSubject: Reunion\nDate: Tue, 12 Mar 2024 10:00:00 +0100\nMIME-Version: 1.0\nContent-Type: text/html; charset=utf-8\n\n<p>Hola <b>Luis</b></p><p>Nos vemos</p>\n'
    (tmp_path / 'm.eml').write_text(eml, encoding='utf-8')
    r = documents.extract(str(tmp_path), 'm.eml')
    m = r['messages'][0]
    assert r['title'] == 'Reunion' and m['subject'] == 'Reunion' and m['date'] == '2024-03-12T09:00:00Z'
    assert 'ana@x.org' in m['from'] and m['text'] == 'Hola Luis\nNos vemos'


def test_mbox(tmp_path):
    box = (
        'From a@x.org Mon Mar 11 10:00:00 2024\nFrom: a@x.org\nSubject: Uno\n\nprimero\n\n'
        'From b@x.org Mon Mar 11 11:00:00 2024\nFrom: b@x.org\nSubject: Dos\n\nsegundo\n>From aqui\n'
    )
    (tmp_path / 'b.mbox').write_text(box, encoding='utf-8')
    r = documents.extract(str(tmp_path), 'b.mbox')
    assert [(m['subject'], m['line'], m['text']) for m in r['messages']] == [('Uno', 1, 'primero'), ('Dos', 7, 'segundo\n>From aqui')]
    assert r['meta']['messages'] == 2


def test_ics(tmp_path):
    ics = (
        'BEGIN:VCALENDAR\r\nX-WR-CALNAME:Trabajo\r\nBEGIN:VEVENT\r\nSUMMARY:Reunion de\r\n  equipo\r\nDTSTART:20250312T100000Z\r\nDTEND:20250312T110000Z\r\n'
        'LOCATION:Sala 1\\, piso 2\r\nATTENDEE;CN="Ana Gomez":mailto:ana@x.org\r\nATTENDEE:mailto:luis@x.org\r\nEND:VEVENT\r\n'
        'BEGIN:VEVENT\r\nSUMMARY:Cumple\r\nDTSTART;VALUE=DATE:20250401\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n'
    )
    (tmp_path / 'c.ics').write_text(ics, encoding='utf-8')
    r = documents.extract(str(tmp_path), 'c.ics')
    assert r['title'] == 'Trabajo'
    e0, e1 = r['events']
    assert e0 == {'title': 'Reunion de equipo', 'when': '2025-03-12T10:00:00Z', 'until': '2025-03-12T11:00:00Z', 'where': 'Sala 1, piso 2', 'attendees': ['Ana Gomez', 'luis@x.org'], 'line': 3}
    assert e1['when'] == '2025-04-01' and e1['line'] == 12


def test_csv_tsv(tmp_path):
    rows = ['nombre,edad'] + ['p%d,%d' % (i, i) for i in range(300)]
    (tmp_path / 'g.csv').write_text('\n'.join(rows), encoding='utf-8')
    r = documents.extract(str(tmp_path), 'g.csv')
    lines = r['text'].splitlines()
    assert lines[0] == 'nombre | edad' and len(lines) == 201
    assert r['meta']['rows'] == 300 and r['meta']['columns'] == ['nombre', 'edad']
    (tmp_path / 't.tsv').write_text('a\tb\n1\t2\n', encoding='utf-8')
    assert documents.extract(str(tmp_path), 't.tsv')['text'] == 'a | b\n1 | 2'


def test_rtf(tmp_path):
    rtf = r"{\rtf1\ansi{\fonttbl{\f0 Arial;}}{\*\generator x;}\pard Hola \b mundo\b0\par Camin\'f3 \u241?a\par}"
    (tmp_path / 'r.rtf').write_text(rtf, encoding='latin-1')
    r = documents.extract(str(tmp_path), 'r.rtf')
    assert r['text'] == 'Hola mundo\nCaminó ña'
    (tmp_path / 'x.rtf').write_text('plain', encoding='utf-8')
    assert documents.extract(str(tmp_path), 'x.rtf') is None


def test_pdf(tmp_path):
    pypdf = pytest.importorskip('pypdf')
    w = pypdf.PdfWriter()
    w.add_blank_page(200, 200)
    w.add_metadata({'/Title': 'Doc PDF'})
    with open(tmp_path / 'd.pdf', 'wb') as f:
        w.write(f)
    r = documents.extract(str(tmp_path), 'd.pdf')
    assert r['title'] == 'Doc PDF' and r['meta']['pages'] == 1
    (tmp_path / 'junk.pdf').write_bytes(b'%PDF-garbage')
    assert documents.extract(str(tmp_path), 'junk.pdf') is None


def test_pdf_without_pypdf(tmp_path, monkeypatch):
    import builtins
    real = builtins.__import__

    def fake(name, *a, **k):
        if name == 'pypdf':
            raise ImportError(name)
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, '__import__', fake)
    (tmp_path / 'd.pdf').write_bytes(b'%PDF-1.4')
    assert documents.extract(str(tmp_path), 'd.pdf') is None
