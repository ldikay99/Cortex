import pytest

from cortex_graph import config
from cortex_graph.analyze import analyze
from cortex_graph.errors import CortexError


def matcher(*lines):
    return {'ignore': config.compile_patterns(lines)}


def test_defaults_without_files(tmp_path):
    cfg = config.load(tmp_path)
    assert cfg['name'] is None and cfg['exclude'] == [] and cfg['roots'] == []
    assert cfg['include_tests'] is None and cfg['git'] is True and cfg['ignore'] == []
    assert not config.ignored(cfg, 'a/b.py')


def test_toml_keys(tmp_path):
    (tmp_path / '.cortex.toml').write_text(
        'name = "mi-app"\nexclude = ["legacy/", " docs "]\nignore = ["*.gen.py"]\n'
        'include_tests = true\nroots = ["../shared"]\ngit = false\n', encoding='utf-8')
    (tmp_path / '.cortexignore').write_text('# comentario\nbuild_out/\n', encoding='utf-8')
    cfg = config.load(tmp_path)
    assert cfg['name'] == 'mi-app' and cfg['exclude'] == ['legacy', 'docs'] and cfg['roots'] == ['../shared']
    assert cfg['include_tests'] is True and cfg['git'] is False
    assert cfg['ignore_patterns'] == ['# comentario', 'build_out/', '*.gen.py']
    assert config.ignored(cfg, 'app/models.gen.py') and config.ignored(cfg, 'build_out/x.py')
    assert not config.ignored(cfg, 'app/models.py')


def test_cortex_table_is_accepted(tmp_path):
    (tmp_path / '.cortex.toml').write_text('[cortex]\nname = "otro"\n', encoding='utf-8')
    assert config.load(tmp_path)['name'] == 'otro'


@pytest.mark.parametrize('text, needle', [
    ('name = [', 'no es TOML válido'),
    ('exclude = "a"\nexclude = "b"', 'no es TOML válido'),
    ('exclude = [1, 2]', '«exclude» debe ser una lista de textos'),
    ('git = "yes"', '«git» debe ser true o false'),
    ('include_tests = 1', '«include_tests» debe ser true o false'),
    ('name = ""', '«name» debe ser un texto no vacío'),
])
def test_invalid_toml_raises_spanish_error(tmp_path, text, needle):
    (tmp_path / '.cortex.toml').write_text(text, encoding='utf-8')
    with pytest.raises(CortexError) as exc:
        config.load(tmp_path)
    assert needle in exc.value.message and '.cortex.toml' in exc.value.message


@pytest.mark.parametrize('lines, yes, no', [
    (['*.log'], ['a.log', 'x/y/a.log'], ['a.logx', 'log']),
    (['/root.py'], ['root.py'], ['sub/root.py']),
    (['docs/*.md'], ['docs/a.md'], ['docs/x/a.md', 'other/docs/a.md']),
    (['build/'], ['build/a.py', 'src/build/b.py'], ['build', 'builder/a.py']),
    (['**/gen'], ['gen', 'a/gen', 'a/b/gen/c.py'], ['agen', 'gen2']),
    (['a/**/z.py'], ['a/z.py', 'a/b/z.py', 'a/b/c/z.py'], ['b/a/z.py', 'a/z.pyc']),
    (['lib/**'], ['lib/a.py', 'lib/x/y.py'], ['lib', 'src/lib/a.py']),
    (['file?.py'], ['file1.py', 'x/fileA.py'], ['file10.py', 'file.py', 'file/.py']),
    (['[abc].py'], ['a.py', 'c.py'], ['d.py', 'ab.py']),
    (['[!abc].py'], ['d.py'], ['a.py']),
    (['[a-c]x.py'], ['bx.py'], ['dx.py']),
    (['*.py', '!keep.py'], ['a.py'], ['keep.py', 'x/keep.py']),
    (['secret/', '!secret/ok.py'], ['secret/ok.py', 'secret/no.py'], ['ok.py']),
    (['\\#notcomment'], ['#notcomment'], ['notcomment']),
    (['\\!bang'], ['!bang'], ['bang']),
    (['# comment', '', '   '], [], ['# comment', 'comment']),
    (['trail   '], ['trail'], ['trail   ']),
    (['sp\\ '], ['sp '], ['sp']),
    (['a\\*b'], ['a*b'], ['axb']),
    (['foo**bar'], ['fooxbar'], ['foo/x/bar']),
    (['**'], ['a', 'a/b.py'], []),
])
def test_gitignore_matcher(lines, yes, no):
    cfg = matcher(*lines)
    for rel in yes:
        assert config.ignored(cfg, rel), (lines, rel)
    for rel in no:
        assert not config.ignored(cfg, rel), (lines, rel)


def test_negation_cannot_reinclude_inside_ignored_dir():
    cfg = matcher('logs/', '!logs/keep.txt')
    assert config.ignored(cfg, 'logs/keep.txt')
    cfg = matcher('logs/*', '!logs/keep.txt')
    assert not config.ignored(cfg, 'logs/keep.txt') and config.ignored(cfg, 'logs/other.txt')


def test_paths_are_normalized():
    cfg = matcher('/app/gen/')
    assert config.ignored(cfg, 'app\\gen\\x.py') and config.ignored(cfg, './app/gen/x.py')


def test_analyze_honors_config(repo):
    (repo / '.cortexignore').write_text('app/utils.py\nweb/\n', encoding='utf-8')
    (repo / '.cortex.toml').write_text('exclude = ["docs"]\n', encoding='utf-8')
    files = {n['file'] for n in analyze(repo, 'demo')['nodes'] if n['kind'] in ('module', 'doc')}
    assert 'app/services.py' in files
    assert not any(f == 'app/utils.py' or f.startswith(('web/', 'docs/')) for f in files)
