import pytest

from cortex_graph import scip
from cortex_graph.common import Graph
from cortex_graph.errors import CortexError

PKG = 'scip-python python demo 1.0 `demo'


def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7f
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def field(num, payload):
    if isinstance(payload, int):
        return varint(num << 3) + varint(payload)
    if isinstance(payload, str):
        payload = payload.encode()
    return varint(num << 3 | 2) + varint(len(payload)) + payload


def packed(num, values):
    return field(num, b''.join(varint(v) for v in values))


def occ(rng, sym, roles=0, enclosing=None, unpacked=False):
    body = b''.join(field(1, v) for v in rng) if unpacked else packed(1, rng)
    body += field(2, sym) + (field(3, roles) if roles else b'')
    if enclosing:
        body += packed(7, enclosing)
    return body


def doc(path, occs, symbols=()):
    return field(1, path) + field(4, 'python') + b''.join(field(2, o) for o in occs) + b''.join(field(3, s) for s in symbols)


def index(tmp_path, docs, name='index.scip'):
    path = tmp_path / name
    path.write_bytes(field(1, field(1, 0)) + b''.join(field(2, d) for d in docs))
    return path


def write(tmp_path, files):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


SOURCES = {
    'pkg/a.py': 'from pkg.b import helper, Thing\n\n\ndef run():\n    helper()\n    return Thing\n',
    'pkg/b.py': 'class Thing:\n    pass\n\n\ndef helper():\n    return 1\n',
}


def demo_graph():
    g = Graph()
    for rel in SOURCES:
        g.node(f'm:{rel}', kind='module', name=rel, file=rel, line=1)
    g.node('f:pkg/a.py:run', kind='function', name='run', file='pkg/a.py', line=4, end=6)
    g.node('c:pkg/b.py:Thing', kind='class', name='Thing', file='pkg/b.py', line=1, end=2)
    g.node('f:pkg/b.py:helper', kind='function', name='helper', file='pkg/b.py', line=5, end=6)
    return g


def demo_docs():
    helper, thing, run = f'{PKG}.b`/helper().', f'{PKG}.b`/Thing#', f'{PKG}.a`/run().'
    a = doc('pkg/a.py', [
        occ([0, 18, 24], helper), occ([0, 26, 31], thing),
        occ([3, 4, 7], run, roles=1, enclosing=[3, 0, 5, 16]),
        occ([4, 4, 10], helper), occ([5, 11, 16], thing),
        occ([4, 4, 10], 'local 0'),
    ])
    b = doc('pkg/b.py', [
        occ([0, 6, 11], thing, roles=1, enclosing=[0, 0, 1, 8]),
        occ([4, 4, 10], helper, roles=1, enclosing=[4, 0, 5, 12]),
    ])
    return [a, b]


def test_decoder_reads_documents_ranges_roles_and_relationships(tmp_path):
    rel = field(1, f'{PKG}.b`/Iface#') + field(3, 1)
    info = field(1, f'{PKG}.b`/Impl#') + field(4, rel)
    path = index(tmp_path, [
        doc('./x/y.py', [occ([2, 1, 4, 3], 'sym.', roles=1, enclosing=[1, 0, 9, 0]), occ([7, 2, 5], 'other().', unpacked=True)], [info]),
    ])
    (d,) = scip.read_index(path)
    assert d['path'] == 'x/y.py'
    assert d['occurrences'][0] == ([2, 1, 4, 3], 'sym.', 1, [1, 0, 9, 0])
    assert d['occurrences'][1] == ([7, 2, 5], 'other().', 0, [])
    assert d['implements'] == {f'{PKG}.b`/Impl#': [f'{PKG}.b`/Iface#']}
    assert scip.span([7, 2, 5]) == (7, 2, 7, 5)
    assert [scip.kind_of(s) for s in ('a().', 'A#', 'm/__init__:', 'p/', 'x.', 'local 3')] == ['callable', 'type', 'module', 'namespace', 'term', None]
    assert scip.name_of(f'{PKG}.b`/Thing#run().') == 'run'
    assert scip.qualified(f'{PKG}.b`/Thing#run().') == 'Thing.run'
    assert scip.qualified(f'{PKG}.b`/outer().inner().') is None


def test_apply_scip_adds_precise_edges_between_existing_nodes(tmp_path):
    write(tmp_path, SOURCES)
    g = demo_graph()
    before = set(g.nodes)
    added = scip.apply_scip(g, tmp_path, index(tmp_path, demo_docs()))
    assert set(g.nodes) == before
    assert added == {'call': 1, 'import': 1, 'ref': 1}
    assert g.edges[('f:pkg/a.py:run', 'f:pkg/b.py:helper', 'call')] == 1
    assert g.edges[('f:pkg/a.py:run', 'c:pkg/b.py:Thing', 'ref')] == 1
    assert g.edges[('m:pkg/a.py', 'm:pkg/b.py', 'import')] == 4
    assert not any(a == 'm:pkg/a.py' and k in ('call', 'ref') for a, _, k in g.edges)


def test_existing_edges_are_kept_and_not_reweighted(tmp_path):
    write(tmp_path, SOURCES)
    g = demo_graph()
    g.edge('f:pkg/a.py:run', 'f:pkg/b.py:helper', 'call')
    g.edge('m:pkg/a.py', 'm:pkg/b.py', 'import')
    added = scip.apply_scip(g, tmp_path, index(tmp_path, demo_docs()))
    assert added == {'ref': 1}
    assert g.edges[('f:pkg/a.py:run', 'f:pkg/b.py:helper', 'call')] == 1
    assert g.edges[('m:pkg/a.py', 'm:pkg/b.py', 'import')] == 1


def test_tests_edge_blocks_duplicate_call(tmp_path):
    write(tmp_path, SOURCES)
    g = demo_graph()
    g.edge('f:pkg/a.py:run', 'f:pkg/b.py:helper', 'tests')
    scip.apply_scip(g, tmp_path, index(tmp_path, demo_docs()))
    assert ('f:pkg/a.py:run', 'f:pkg/b.py:helper', 'call') not in g.edges


def test_nearest_preceding_symbol_without_end(tmp_path):
    write(tmp_path, SOURCES)
    g = demo_graph()
    for meta in g.nodes.values():
        meta.pop('end', None)
    scip.apply_scip(g, tmp_path, index(tmp_path, demo_docs()))
    assert ('f:pkg/a.py:run', 'f:pkg/b.py:helper', 'call') in g.edges


def test_definition_lines_are_not_calls(tmp_path):
    write(tmp_path, {'m.py': 'def go():\n    pass\n\n\ndef go(x):\n    return go(x)\n'})
    lines = (tmp_path / 'm.py').read_text().split('\n')
    assert not scip.called(lines, (4, 4, 4, 6))
    assert scip.called(lines, (5, 11, 5, 13))


def test_index_built_from_a_parent_folder_is_aligned_by_suffix(tmp_path):
    write(tmp_path, SOURCES)
    g = demo_graph()
    docs = demo_docs()
    moved = [d.replace(field(1, rel), field(1, 'repo/' + rel)) for d, rel in zip(docs, SOURCES)]
    added = scip.apply_scip(g, tmp_path, index(tmp_path, moved))
    assert added.get('call') == 1


def test_partial_and_corrupt_indexes_are_tolerated(tmp_path):
    write(tmp_path, SOURCES)
    data = index(tmp_path, demo_docs()).read_bytes()
    first = field(2, demo_docs()[0])
    cut = tmp_path / 'cut.scip'
    cut.write_bytes(data[:len(field(1, field(1, 0))) + len(first) + 7])
    docs = scip.read_index(cut)
    assert [d['path'] for d in docs] == ['pkg/a.py']
    g = demo_graph()
    assert scip.apply_scip(g, tmp_path, cut) == {}
    junk = tmp_path / 'junk.scip'
    junk.write_bytes(b'\xff\xff\xff')
    assert scip.read_index(junk) == []
    unknown = tmp_path / 'unknown.scip'
    unknown.write_bytes(field(2, doc('nope/zzz.py', [occ([0, 0, 1], f'{PKG}.b`/helper().')])))
    assert scip.apply_scip(demo_graph(), tmp_path, unknown) == {}
    with pytest.raises(CortexError):
        scip.apply_scip(demo_graph(), tmp_path, tmp_path / 'missing.scip')


def test_output_is_deterministic(tmp_path):
    write(tmp_path, SOURCES)
    path = index(tmp_path, demo_docs())
    runs = []
    for _ in range(2):
        g = demo_graph()
        scip.apply_scip(g, tmp_path, path)
        runs.append(list(g.edges.items()))
    assert runs[0] == runs[1]
