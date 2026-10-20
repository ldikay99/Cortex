import ctypes
import importlib
import os
import posixpath
import re
import warnings
from collections import defaultdict

from tree_sitter import Language, Parser

IDENT = {
    'identifier', 'simple_identifier', 'field_identifier', 'type_identifier', 'property_identifier', 'name',
    'constant', 'package_identifier', 'namespace_identifier', 'this', 'self', 'super',
    'this_expression', 'self_expression', 'super_expression', 'word', 'variable', 'value_name', 'module_name',
    'class_name', 'method_name', 'type_constructor', 'module_type_name', 'constructor', 'simple_name', 'function_name',
}
SELF_WORDS = {'self', 'this', 'Self', 'static', 'parent', 'super'}
SCOPED = {'qualified_identifier', 'scoped_identifier', 'scope_resolution'}
BASE_TYPES = {
    'user_type', 'scoped_type_identifier', 'scoped_identifier', 'qualified_identifier', 'qualified_name', 'scope_resolution',
    'stable_type_identifier', 'generic_type', 'generic_name', 'template_type', 'user_defined_type', 'simple_type',
}
BASE_SKIP = {'call', 'call_expression'}
NO_GLOBAL = {'go', 'hcl'}
DIR_SCOPE = {'go', 'hcl'}
STRICT = {'elixir', 'haskell', 'ocaml'}
MODULE_NAMES = {'elixir'}
CALLS_JVM = {'call_expression': (None,)}
TYPE_GLOBAL = {'csharp', 'c', 'objc', 'swift'}
QUAL_TYPES = {'qualified_type', 'scoped_type_identifier', 'qualified_identifier', 'user_type', 'stable_type_identifier',
              'qualified_name'}
WRAP_TYPES = {'template_type', 'generic_type', 'generic_name'}
NAMESPACE_HOLDERS = {'using_directive', 'namespace_declaration', 'file_scoped_namespace_declaration'}
BUILD_MARKERS = {'Cargo.toml', 'go.mod', 'package.json', 'pom.xml', 'build.gradle', 'build.gradle.kts', 'Package.swift',
                 'composer.json', 'Gemfile', 'mix.exs', 'pubspec.yaml', 'setup.py', 'pyproject.toml', 'CMakeLists.txt',
                 'Makefile'}
BUILD_SUFFIXES = ('.csproj',)
GO_DECLS = {'short_var_declaration', 'var_spec', 'range_clause', 'parameter_declaration', 'variadic_parameter_declaration',
            'type_switch_statement', 'type_spec', 'const_spec'}
GO_BUILTIN_TYPES = set('''bool byte complex64 complex128 error float32 float64 int int8 int16 int32 int64 rune string uint
    uint8 uint16 uint32 uint64 uintptr any comparable'''.split())
GO_BUILTIN_FUNCS = set('''append cap clear close complex copy delete imag len make max min new panic print println real
    recover'''.split())
GO_LITERALS = {'interpreted_string_literal', 'raw_string_literal', 'int_literal', 'float_literal', 'imaginary_literal',
               'rune_literal', 'true', 'false'}
GO_ENV = {'linux', 'amd64', 'unix', 'gc'}
GO_OS = set('''aix android darwin dragonfly freebsd hurd illumos ios js linux nacl netbsd openbsd plan9 solaris wasip1
    windows zos'''.split())
GO_ARCH = set('''386 amd64 amd64p32 arm armbe arm64 arm64be loong64 mips mipsle mips64 mips64le ppc ppc64 ppc64le riscv
    riscv64 s390 s390x sparc sparc64 wasm'''.split())
GO_TYPE_NODES = {'generic_type', 'qualified_type', 'type_identifier', 'pointer_type', 'array_type', 'slice_type',
                 'map_type', 'function_type', 'interface_type', 'channel_type', 'parenthesized_type'}
GO_SCOPES = {'block', 'if_statement', 'for_statement', 'expression_switch_statement', 'type_switch_statement',
             'select_statement', 'expression_case', 'default_case', 'communication_case', 'type_case', 'func_literal',
             'function_declaration', 'method_declaration'}
PREPROC_RE = re.compile(rb'^(?:\xef\xbb\xbf)?[ \t]*#[ \t]*(if|elif|else|endif)\b([^\r\n]*)', re.M)
BLANK_BYTES = bytes(b if b in (10, 13) else 32 for b in range(256))
FOREIGN = ('?',)
PATH_GROUPS = {'c': ('c', 'objc'), 'objc': ('c', 'objc')}
C_STD_HEADERS = set('''assert.h complex.h ctype.h errno.h fenv.h float.h inttypes.h iso646.h limits.h locale.h math.h
    setjmp.h signal.h stdalign.h stdarg.h stdatomic.h stdbool.h stddef.h stdint.h stdio.h stdlib.h stdnoreturn.h string.h
    tgmath.h threads.h time.h uchar.h wchar.h wctype.h unistd.h pthread.h fcntl.h dirent.h dlfcn.h poll.h sched.h
    strings.h termios.h windows.h winsock2.h io.h malloc.h memory.h'''.split())
RUST_TEST = re.compile(r'^#\[\s*(cfg\s*\(\s*(all\s*\(\s*)?test\b|(\w+::)*test\s*[\](]|bench\s*\])')
STD_ROOTS = {
    'rust': {'std', 'core', 'alloc'},
    'c': {'std', 'boost', '__gnu_cxx'},
    'jvm': {'java', 'javax', 'kotlin', 'kotlinx', 'scala', 'android', 'androidx', 'groovy'},
    'csharp': {'System', 'Microsoft'},
    'swift': {'Foundation', 'Swift', 'UIKit', 'AppKit', 'Dispatch', 'Combine', 'SwiftUI'},
    'objc': {'std'},
    'lua': {'table', 'string', 'math', 'os', 'io', 'coroutine', 'debug', 'utf8', 'vim', 'bit', 'jit', 'ffi'},
    'julia': {'Base', 'Core', 'Main'},
    'solidity': {'abi', 'msg', 'block', 'tx'},
    'zig': {'std', 'builtin'},
    'perl': {'CORE', 'POSIX'},
}
BUILTINS = {family: set(words.split()) for family, words in {
    'rust': '''unwrap expect clone to_string to_owned into from as_ref as_mut iter iter_mut into_iter map and_then ok err
        unwrap_or unwrap_or_else unwrap_or_default len is_empty push pop insert remove get get_mut contains contains_key
        extend collect join split trim starts_with ends_with fmt eq ne cmp partial_cmp hash default drop deref deref_mut
        borrow borrow_mut lock read write flush open close next take filter find any all sort sort_by as_str as_bytes
        chars bytes lines to_vec keys values entry or_insert as_slice is_some is_none is_ok is_err ok_or ok_or_else
        map_err unwrap_err send recv spawn format print println eprintln write_all read_to_string read_to_end
        parent file_name file_stem extension exists is_dir is_file canonicalize display to_path_buf as_os_str to_str
        String Vec Option Result Box Rc Arc HashMap HashSet BTreeMap BTreeSet VecDeque Path PathBuf Cow Mutex RwLock
        Self Some None Ok Err Default Clone Debug Display Iterator From Into AsRef Send Sync Sized Fn FnMut FnOnce
        max_by min_by max_by_key min_by_key or_default sum product fold count last nth position enumerate zip rev skip
        step_by chain cycle flat_map flatten filter_map take_while skip_while peekable fuse inspect partition reduce
        for_each try_fold try_for_each max min cloned copied dedup retain truncate drain reserve resize sort_unstable
        sort_by_key windows chunks split_at swap first''',
    'c': '''begin end size push_back emplace_back push_front emplace insert erase find clear empty data c_str length at
        front back reserve resize swap reset get release lock unlock load store count append substr str first second
        printf sprintf snprintf fprintf vsnprintf puts malloc free calloc realloc memcpy memset memmove memcmp strlen
        strcmp strncmp strcpy strncpy strcat strdup strchr strrchr strstr assert exit abort atoi strtol fopen fclose
        fread fwrite fflush fgets fputs fputc getc open close read write min max move forward make_shared make_unique
        sort to_string use_facet string vector map set list unordered_map shared_ptr unique_ptr size_t uint8_t uint16_t
        uint32_t uint64_t int8_t int16_t int32_t int64_t FILE va_list''',
    'objc': '''alloc init new copy mutableCopy retain release autorelease description length count objectForKey
        setObject setValue valueForKey addObject removeObject removeAllObjects objectAtIndex isEqual isEqualToString
        hash respondsToSelector performSelector class superclass isKindOfClass dealloc stringWithFormat open close
        NSStringFromSelector NSStringFromClass NSSelectorFromString NSClassFromString NSLocalizedString NSLog NSAssert
        NSObject NSString NSArray NSDictionary NSError NSData NSURL NSNumber NSInteger NSUInteger''',
    'jvm': '''toString equals hashCode getClass compareTo get set put add addAll remove contains containsKey size isEmpty
        clear iterator stream map filter collect forEach apply let also run with takeIf takeUnless check require
        checkNotNull requireNotNull error println print format append length substring trim split join close use lazy
        listOf mapOf setOf mutableListOf mutableMapOf mutableSetOf arrayOf emptyList emptyMap emptySet toList toMap
        toSet first last firstOrNull lastOrNull single valueOf of copy name ordinal values keys invoke getValue setValue
        next hasNext println assertEquals assertTrue assertFalse assertNull assertNotNull
        String Object Integer Long Boolean Double Float List Map Set Collection Iterable Optional Exception
        RuntimeException Throwable Any Unit Nothing Int Array MutableList MutableMap Pair Class Type''',
    'csharp': '''ToString Equals GetHashCode GetType Dispose DisposeAsync Add AddRange Remove Contains ContainsKey
        TryGetValue Clear Count Any All Where Select SelectMany First FirstOrDefault Single SingleOrDefault Last
        LastOrDefault ToList ToListAsync ToArray ToArrayAsync ToDictionary OrderBy OrderByDescending ThenBy GroupBy
        Include ThenInclude Join Split Format Trim Substring Replace StartsWith EndsWith Wait ConfigureAwait
        SaveChanges SaveChangesAsync FindAsync AnyAsync FirstOrDefaultAsync SingleOrDefaultAsync CountAsync Max Min
        Sum Average Skip Take Concat Distinct Append Invoke Parse TryParse CompareTo GetValue SetValue AsNoTracking
        Close Read Write WriteLine ReadLine Flush AddScoped AddSingleton AddTransient GetRequiredService GetService
        String Object Task ValueTask List Dictionary IEnumerable IList ICollection IDictionary Exception Action Func
        Guid DateTime DateTimeOffset TimeSpan CancellationToken Type Attribute Enum Nullable IDisposable''',
    'swift': '''append insert remove removeAll removeFirst removeLast contains map flatMap compactMap filter reduce
        forEach first last sorted sort joined split count isEmpty description hash async sync lock unlock
        String Int Double Float Bool Array Dictionary Set Optional Data URL Error Result Void Any AnyObject Never
        Character Date''',
    'go': '''String Error Close Read Write Lock Unlock RLock RUnlock Len Less Swap Done Wait Add Err Unwrap Is As Value
        Deadline Load Store Do Bytes Reset WriteString WriteByte WriteRune Flush Seek Sync Next Scan Get Set Del
        MatchString FindStringSubmatch ReplaceAllString WithLabelValues DeleteLabelValues Inc Dec Observe''',
    'ruby': '''class to_s to_sym to_i to_f to_a to_h to_str to_proc to_ary to_hash has_key? each_key each_value close read write
        rewind gets inspect each each_with_index each_pair map collect
        select filter reject find detect each_with_object inject reduce include? is_a? kind_of? respond_to? send
        public_send freeze frozen? dup clone merge merge! key? fetch keys values push pop shift unshift first last join
        split strip gsub sub length size empty? nil? present? blank? call puts print require require_relative raise
        tap then instance_variable_get instance_variable_set define_method attr_accessor attr_reader attr_writer
        extend include prepend delete compact flatten uniq sort sort_by group_by any? all? none? count sum min max
        times format to_json hash eql? equal? instance_of? method_missing super new delete_if keep_if sort! map! select!
        reject! uniq! compact! flatten! each_key each_value transform_values transform_keys dig slice except union
        upcase downcase capitalize bytesize encoding force_encoding start_with? end_with? match match? scan
        strftime iso8601 httpdate to_date to_time succ pred name update replace clear store concat insert index values_at
        reverse string''',
    'perl': '''reverse join split warn die say print printf sprintf push pop shift unshift keys values each map grep sort
        scalar defined ref bless exists delete length substr index rindex lc uc lcfirst ucfirst chomp chop chr ord
        wantarray local return eval open close binmode sprintf abs int sqrt time localtime gmtime sleep exit
        require do caller croak confess carp''',
    'php': '''count implode explode sprintf printf in_array is_array is_string is_null isset unset empty json_encode
        json_decode strlen str_replace array_map array_merge array_keys array_values array_filter array_key_exists
        method_exists function_exists class_exists get_class trim strtolower strtoupper substr strpos''',
    'dart': '''toString toList toSet map where forEach add addAll remove contains containsKey isEmpty isNotEmpty length
        join split then catchError listen cancel close dispose setState print hashCode
        String int double bool num List Map Set Future Stream Object dynamic Function Iterable Duration DateTime''',
    'lua': '''print pairs ipairs require type tostring tonumber error assert pcall xpcall setmetatable getmetatable
        rawget rawset select unpack next insert format''',
    'shell': '''echo printf cd test read exit return local export set unset shift eval exec source true false''',
    'haskell': '''map filter show print return pure fmap mapM mapM_ forM forM_ when unless error fst snd length concat
        foldr foldl null not id const putStrLn''',
    'elixir': '''is_nil to_string inspect raise length elem put_elem hd tl send self spawn''',
    'julia': '''length push! println print map filter show size getindex setindex! iterate convert string isempty
        haskey get error throw''',
    'solidity': '''require assert revert keccak256 sha256 ripemd160 ecrecover addmod mulmod selfdestruct push pop encode
        encodePacked decode encodeWithSelector encodeWithSignature encodeCall delegatecall staticcall''',
    'zig': '''append appendSlice deinit toOwnedSlice print alloc free create destroy''',
    'fsharp': '''printfn sprintf failwith ignore raise string int Some None''',
}.items()}


def text(node, src):
    return src[node.start_byte:node.end_byte].decode('utf-8', errors='replace')


def leaves(node, src, out=None):
    out = [] if out is None else out
    stack = [node] if node is not None else []
    while stack:
        n = stack.pop()
        if n.type in IDENT and (n.child_count == 0 or n.type.endswith('_expression')):
            out.append(text(n, src).lstrip('$'))
            continue
        stack.extend(c for c in reversed(n.children) if c.is_named and 'argument' not in c.type)
    return out


def add(items, value):
    if value not in items:
        items.append(value)


def last_name(node, src):
    found = leaves(node, src)
    return found[-1] if found else None


def first_ident(node, src):
    named = node.child_by_field_name('name')
    if named is None:
        named = next((c for c in node.named_children if c.type in IDENT), None)
    return last_name(named, src) if named is not None else None


def base_names(node, src):
    out = []
    stack = [node] if node is not None else []
    while stack:
        n = stack.pop()
        if n.type in BASE_SKIP:
            continue
        if n.type in BASE_TYPES:
            name = last_name(n, src)
            if name:
                add(out, name)
            continue
        if n.type in IDENT and (n.child_count == 0 or n.type.endswith('_expression')):
            add(out, text(n, src).lstrip('$'))
            continue
        stack.extend(c for c in reversed(n.named_children) if c.is_named and 'argument' not in c.type)
    return out


def strip_quotes(value):
    return value.strip().strip('\'"`')


def string_value(node, src):
    for c in node.children:
        if 'string' in c.type or c.type in ('encapsed_string', 'interpreted_string_literal', 'raw_string_literal'):
            return strip_quotes(text(c, src))
        found = string_value(c, src) if c.child_count else None
        if found:
            return found
    return None


def expand(spec, sep):
    if '{' not in spec:
        return [spec]
    head = spec.index('{')
    depth, end = 0, len(spec)
    for i in range(head, len(spec)):
        depth += spec[i] == '{'
        depth -= spec[i] == '}'
        if depth == 0:
            end = i
            break
    prefix, inner, rest = spec[:head], spec[head + 1:end], spec[end + 1:]
    parts, depth, cur = [], 0, ''
    for ch in inner:
        depth += ch == '{'
        depth -= ch == '}'
        if ch == ',' and depth == 0:
            parts.append(cur)
            cur = ''
        else:
            cur += ch
    parts.append(cur)
    out = []
    for p in parts:
        p = p.strip()
        if p:
            out += expand(prefix + p + rest, sep)
    return out


def split_alias(spec, marker):
    if marker in spec:
        path, alias = spec.split(marker, 1)
        return path.strip(), alias.strip()
    return spec.strip(), None


def c_function_name(node, src):
    d = node.child_by_field_name('declarator')
    while d is not None and d.type not in ('identifier', 'field_identifier', 'qualified_identifier',
                                            'destructor_name', 'operator_name'):
        d = d.child_by_field_name('declarator') or (d.named_children[0] if d.named_children else None)
    if d is None:
        return None, None
    if d.type == 'qualified_identifier':
        parts = leaves(d, src)
        return (parts[-2] if len(parts) > 1 else None), (parts[-1] if parts else None)
    return None, text(d, src)


def go_core(node):
    while node is not None and node.type in ('pointer_type', 'parenthesized_type', 'generic_type', 'qualified_type'):
        node = node.child_by_field_name('type' if node.type == 'generic_type' else 'name') if node.type in (
            'generic_type', 'qualified_type') else (node.named_children[0] if node.named_children else None)
    return node


def go_function_name(node, src):
    name = node.child_by_field_name('name')
    receiver = node.child_by_field_name('receiver')
    owner = None
    if receiver is not None:
        param = next((c for c in receiver.named_children if c.type == 'parameter_declaration'), None)
        core = go_core(param.child_by_field_name('type')) if param is not None else None
        owner = text(core, src) if core is not None and core.type == 'type_identifier' else None
    return owner, text(name, src) if name is not None else None


def go_collect(u, n, owner_id, in_fn):
    if n.type == 'type_spec':
        name, kind = n.child_by_field_name('name'), n.child_by_field_name('type')
        if not in_fn and name is not None and kind is not None:
            u.gtypes.setdefault(text(name, u.src), kind)
    elif in_fn:
        if n.type != 'const_spec':
            u.decls[owner_id].append(n)
    elif n.type in ('var_spec', 'const_spec'):
        if n.type == 'var_spec':
            u.gvars.append(n)
        u.values.update(text(c, u.src) for c in n.children_by_field_name('name'))


GO_NAMED = {'const_spec', 'var_spec', 'parameter_declaration', 'variadic_parameter_declaration', 'function_declaration',
            'method_declaration', 'type_spec', 'labeled_statement', 'field_declaration', 'import_spec', 'package_clause',
            'method_elem', 'type_parameter_declaration'}


def go_value_ref(node):
    """Identificador que nombra un valor ya declarado (`Run: emptyRun`, `x := Constante`), no uno que se declara."""
    parent = node.parent
    if parent is None or parent.type in GO_NAMED and node in parent.children_by_field_name('name'):
        return False
    if parent.type == 'call_expression' and parent.child_by_field_name('function') == node:
        return False
    if parent.type == 'expression_list' and parent.parent is not None and parent.parent.type in ('short_var_declaration', 'range_clause'):
        return parent.parent.child_by_field_name('left') != parent
    if parent.type == 'literal_element' and parent.parent is not None and parent.parent.type == 'keyed_element':
        return parent.parent.named_children[0] != parent
    return True


def go_shadowed(node, name, src):
    """`name` declarado por un literal de función que rodea a `node` (parámetro o variable de su cuerpo antes de usarse):
    el entorno de las funciones con nombre no cubre las de nivel de paquete (`var f = func(x T) {…}`)."""
    cur = node.parent
    while cur is not None:
        if cur.type == 'func_literal':
            for p in cur.named_children:
                if p.type == 'parameter_list' and any(text(x, src) == name for d in p.named_children for x in d.children_by_field_name('name')):
                    return True
        if cur.type == 'block':
            for stmt in cur.named_children:
                if stmt.start_byte >= node.start_byte:
                    break
                left = stmt.child_by_field_name('left') if stmt.type == 'short_var_declaration' else None
                if left is not None and any(text(x, src) == name for x in left.named_children):
                    return True
        cur = cur.parent
    return False


def go_tag(word):
    return word in GO_ENV or re.fullmatch(r'go1(\.\d+)*', word) is not None


def go_constraint(expr):
    tokens = re.findall(r'&&|\|\||[!()]|[^\s!()&|]+', expr)
    pos = [0]

    def take(tok=None):
        cur = tokens[pos[0]] if pos[0] < len(tokens) else None
        if tok is None or cur == tok:
            pos[0] += 1
            return cur or ''
        return None

    def atom():
        if take('!') is not None:
            return not atom()
        if take('(') is not None:
            value = either()
            take(')')
            return value
        return go_tag(take())

    def both():
        value = atom()
        while take('&&') is not None:
            value = atom() and value
        return value

    def either():
        value = both()
        while take('||') is not None:
            value = both() or value
        return value
    return either() if tokens else True


def go_enabled(rel, src):
    head = src[:max(src.find(b'\npackage '), 0)]
    found = re.search(rb'^//go:build\s+(.+)$', head, re.M)
    expr = found.group(1).decode('utf-8', errors='replace').strip() if found else ''
    parts = os.path.splitext(rel.rsplit('/', 1)[-1])[0].split('_')
    parts = parts[1:-1] if parts[-1] == 'test' else parts[1:]
    tags = [p for p in parts[-2:] if p in GO_OS or p in GO_ARCH]
    return expr, all(t in GO_ENV for t in tags) and go_constraint(expr)


def preprocessor_groups(src):
    """Grupos `#if … #elif … #else … #endif` (también anidados): lista de ramas `(inicio, fin, condición)` en bytes, cada
    una desde su directiva hasta la siguiente, y la posición del `#endif`."""
    groups, stack = [], []
    for m in PREPROC_RE.finditer(src):
        word, cond = m.group(1), m.group(2).strip()
        if word == b'if':
            stack.append([(m.start(), cond)])
        elif not stack:
            continue
        elif word != b'endif':
            stack[-1].append((m.start(), cond if word == b'elif' else b'else'))
        else:
            starts = stack.pop()
            groups.append(([(s, starts[i + 1][0] if i + 1 < len(starts) else m.start(), c) for i, (s, c) in enumerate(starts)],
                           m.start()))
    return groups


def first_branch(branches):
    """Rama que se conserva sin conocer los símbolos definidos: la primera, salvo `#if false`/`#if 0`."""
    if branches[0][2] not in (b'false', b'0'):
        return 0
    return len(branches) - 1 if branches[-1][2] == b'else' else None


DOTNET_TFM = re.compile(r'(NET|NETCOREAPP)(\d+)_(\d+)(_OR_GREATER)?|NETCOREAPP|NETSTANDARD[\w]*|NETFRAMEWORK|NET\d+|NET')
DOTNET_LATEST = (9, 0)
PREPROC_TOKEN = re.compile(r'\s*(\|\||&&|==|!=|!|\(|\)|\w+)')


def dotnet_symbol(word):
    """Valor de un símbolo de marco de destino en el .NET actual (`NET`, `NET8_0_OR_GREATER`, `NETSTANDARD2_0`…), o None
    si no es uno de ellos (símbolo propio del proyecto)."""
    m = DOTNET_TFM.fullmatch(word)
    if not m:
        return None
    if m.group(2):
        version = (int(m.group(2)), int(m.group(3)))
        if m.group(1) == 'NETCOREAPP':
            return version <= (3, 1) if m.group(4) else False
        return version <= DOTNET_LATEST if m.group(4) else version == DOTNET_LATEST
    return word in ('NET', 'NETCOREAPP')


def preproc_value(cond):
    """Evalúa una condición de `#if` con lógica de tres valores (True, False o None si depende de un símbolo propio)."""
    tokens = PREPROC_TOKEN.findall(cond.decode('utf-8', 'replace').split('//')[0])
    pos = [0]

    def peek():
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def atom():
        tok = peek()
        pos[0] += 1
        if tok == '!':
            value = atom()
            return None if value is None else not value
        if tok == '(':
            value = disjunction()
            pos[0] += 1
            return value
        if tok in ('true', 'false') or tok and tok.isdigit():
            return tok not in ('false', '0')
        return dotnet_symbol(tok) if tok else None

    def comparison():
        left = atom()
        while peek() in ('==', '!='):
            op = tokens[pos[0]]
            pos[0] += 1
            right = atom()
            left = None if left is None or right is None else (left == right) == (op == '==')
        return left

    def conjunction():
        value = comparison()
        while peek() == '&&':
            pos[0] += 1
            other = comparison()
            value = False if value is False or other is False else (None if value is None or other is None else True)
        return value

    def disjunction():
        value = conjunction()
        while peek() == '||':
            pos[0] += 1
            other = conjunction()
            value = True if value is True or other is True else (None if value is None or other is None else False)
        return value

    return disjunction() if tokens else None


def dotnet_branch(branches):
    """Rama de C# que se conserva: las condiciones sobre el marco de destino se evalúan para el .NET actual (el código
    de compatibilidad de `#if !NET` o `#if NETFRAMEWORK` no se usa); con un símbolo propio, la primera rama posible."""
    for i, (_, _, cond) in enumerate(branches):
        value = True if cond == b'else' else preproc_value(cond)
        if value is not False:
            return i
    return None


CS_REF_PARTIAL = re.compile(rb'\bref(\s+)partial(\s+)(?=struct\b)')


def csharp_fixups(src):
    """`ref partial struct` (el orden que exige C#) no lo acepta la gramática; `partial ref struct`, de igual longitud, sí."""
    return CS_REF_PARTIAL.sub(lambda m: b'partial' + m.group(1) + b'ref' + m.group(2), src) if b'partial' in src else src


KT_WHERE_STATEMENT = re.compile(rb'(?m)^([ \t]*)[ \t](?=where[ \t]*(?:\?\.|\.|!!|=(?!=)|\[))')
KT_ACCESSOR_ANNOTATION = re.compile(rb'(?m)^[ \t]*((?:@[\w.]+(?:\([^()\n]*\))?[ \t]+)+)(?=(?:(?:private|protected|internal|public)[ \t]+)?'
                                    rb'(?:get|set)\b)')
KT_LINE_BREAKS = (b'{', b';', b'(', b',', b'=', b'.', b'+', b'-', b'*', b'/', b'&', b'|', b'?', b':', b'<', b'>', b'!')


def kotlin_fixups(src):
    """Dos fallos de la gramática de Kotlin que rompen el resto del archivo, corregidos sin mover posiciones:
    `where` (palabra clave suave) usado como variable al principio de una sentencia (`where?.let { … }`), que se
    separa de la sentencia anterior con `;`, y las anotaciones de un accesor (`@Synchronized set(value)`), que se
    vuelven espacios."""
    if b'where' in src:
        def separate(m):
            before = src[:m.start()].rstrip()
            return m.group(1) + (b' ' if before.endswith(KT_LINE_BREAKS) else b';')
        src = KT_WHERE_STATEMENT.sub(separate, src)
    if b'@' in src:
        src = KT_ACCESSOR_ANNOTATION.sub(lambda m: m.group(0)[:m.start(1) - m.start()] + b' ' * len(m.group(1)), src)
    return src


def blank_branches(src, choose=first_branch):
    """Deja una sola rama de cada `#if` (las demás se vuelven espacios, conservando posiciones y saltos de línea):
    una cabecera partida por `#if`/`#else` rompe el árbol sintáctico."""
    if b'#if' not in src:
        return src
    out = bytearray(src)

    def blank(start, end):
        out[start:end] = bytes(out[start:end]).translate(BLANK_BYTES)

    for branches, endif in preprocessor_groups(src):
        keep = choose(branches)
        for i, (start, end, _) in enumerate(branches):
            blank(start, end if i != keep else line_end(src, start))
        blank(endif, line_end(src, endif))
    return bytes(out)


def line_end(src, pos):
    end = src.find(b'\n', pos)
    return len(src) if end < 0 else end


def lua_function_name(node, src):
    name = node.child_by_field_name('name')
    if name is None:
        return None, None
    return None, last_name(name, src)


def c_class_name(node, src):
    if node.child_by_field_name('body') is None:
        return None
    name = node.child_by_field_name('name')
    if name is None and node.parent is not None and node.parent.type == 'type_definition':
        name = node.parent.child_by_field_name('declarator')
    return last_name(name, src) if name is not None else None


def swift_owner(node, src):
    name = node.child_by_field_name('name')
    if node.type == 'class_declaration' and name is not None and name.type == 'user_type':
        return last_name(name, src)
    return None


def rust_owner(node, src):
    if node.type != 'impl_item':
        return None
    return last_name(node.child_by_field_name('type'), src)


def rust_bases(node, src):
    return base_names(node.child_by_field_name('trait'), src)[:1]


def nested_item(lang, node):
    """Declaración con nombre dentro del cuerpo de una función: ítems de Rust (`fn`, `struct`, `impl` locales) y funciones
    locales de Dart (`int inner(x) {…}`). Son definiciones propias, aunque solo se vean en ese bloque."""
    if lang == 'rust':
        return node.type in RUST_NESTED_ITEMS
    if lang == 'dart':
        parent = node.parent
        return node.type == 'function_signature' and parent is not None and parent.type == 'lambda_expression' and \
            parent.parent is not None and parent.parent.type == 'local_function_declaration'
    return False


def rust_supertraits(node, src):
    """`trait A: B + C {}`: los métodos de B y C están disponibles en A."""
    bounds = node.child_by_field_name('bounds') if node.type == 'trait_item' else None
    return [last_name(c, src) for c in (bounds.named_children if bounds is not None else ())
            if c.type in ('type_identifier', 'scoped_type_identifier', 'generic_type') and last_name(c, src)]


def rust_associated(node):
    """`type Item = …;` dentro de un `impl` o `trait`: tipo asociado, no un alias de tipo propio."""
    parent = node.parent
    return node.type == 'type_item' and parent is not None and parent.type == 'declaration_list' and \
        parent.parent is not None and parent.parent.type in ('impl_item', 'trait_item')


def in_macro(node):
    """Dentro de los argumentos de una macro invocada (no en atributos ni en `macro_rules!`)."""
    cur, seen = node.parent, False
    while cur is not None:
        if cur.type in RUST_MACRO_SKIP:
            return False
        seen = seen or cur.type == 'macro_invocation'
        cur = cur.parent
    return seen


def rust_macro_callee(node, src):
    """Llamada escrita como fichas en una macro: `f(…)`, `A::f(…)`, `x.f(…)` (la ficha es el `(…)`)."""
    prev = node.prev_sibling
    if not text(node, src).startswith('(') or prev is None or prev.type != 'identifier' or not in_macro(node):
        return []
    parts, cur = [text(prev, src)], prev.prev_sibling
    while cur is not None and cur.type in ('::', '.'):
        head = cur.prev_sibling
        if head is None or head.type not in ('identifier', 'self', 'crate', 'super'):
            break
        parts.insert(0, text(head, src))
        cur = head.prev_sibling
    return parts


def go_imports(node, src):
    path = node.child_by_field_name('path')
    if path is None:
        return []
    alias = node.child_by_field_name('name')
    return [('go', strip_quotes(text(path, src)), text(alias, src) if alias is not None else None)]


def rust_imports(node, src):
    if node.type == 'extern_crate_declaration':
        name, alias = node.child_by_field_name('name'), node.child_by_field_name('alias')
        return [('rustcrate', [text(name, src)], text(alias, src) if alias is not None else None)] if name is not None else []
    if node.type == 'mod_item':
        if node.child_by_field_name('body') is not None:
            return []
        name = node.child_by_field_name('name')
        return [('rustmod', text(name, src), None)] if name is not None else []
    arg = node.child_by_field_name('argument')
    if arg is None:
        return []
    out = []
    inline, cur = 0, node.parent  # `mod tests { use super::x; }`: `super` es el módulo del archivo, no su padre
    while cur is not None:
        inline += cur.type == 'mod_item' and cur.child_by_field_name('body') is not None
        cur = cur.parent
    for spec in expand(re.sub(r'\s+', ' ', text(arg, src)), '::'):
        path, alias = split_alias(spec, ' as ')
        segs = [s for s in path.split('::') if s]
        lead = next((i for i, x in enumerate(segs) if x != 'super'), len(segs))
        if inline and lead:
            segs = segs[min(lead, inline):] if lead > inline else ['self'] + segs[lead:]
        if segs and segs[-1] == 'self':
            segs = segs[:-1]
        if segs and segs[-1] != '*':
            out.append(('rust', segs, alias))
        elif segs:
            out.append(('rustglob', segs[:-1], None))
    return out


def dotted_imports(prefix_re, alias_marker, wildcards):
    def read(node, src):
        raw = re.sub(r'\s+', ' ', text(node, src)).strip().rstrip(';')
        raw = re.sub(prefix_re, '', raw).strip()
        out = []
        for spec in expand(raw, '.'):
            path, alias = split_alias(spec, alias_marker)
            parts = path.split('.')
            if parts[-1] in wildcards:
                out.append(('pkg', '.'.join(parts[:-1]), None))
            else:
                out.append(('fqn', path, alias))
        return out
    return read


def csharp_imports(node, src):
    raw = re.sub(r'\s+', ' ', text(node, src)).strip().rstrip(';')
    raw = re.sub(r'^(global )?using (static )?', '', raw).strip()
    alias = None
    if '=' in raw:
        alias, raw = (x.strip() for x in raw.split('=', 1))
    return [('fqn', raw, alias), ('pkg', raw, None)]


def kt_class_name(node, src):
    """Nombre de una clase u objeto de Kotlin; en `typealias X = …` el nombre es el primer identificador."""
    name = node.child_by_field_name('name')
    if node.type == 'type_alias':
        name = next((c for c in node.named_children if c.type == 'identifier'), None)
    return last_name(name, src)


def php_bases(node, src):
    """Los traits que la clase incorpora con `use T;` (sus métodos tienen prioridad), luego `extends` e `implements`."""
    names = []
    body = node.child_by_field_name('body')
    for c in (body.named_children if body is not None else ()):
        if c.type == 'use_declaration':
            for x in base_names(c, src):
                add(names, x)
    for c in node.named_children:
        if c.type in ('base_clause', 'class_interface_clause'):
            for x in base_names(c, src):
                add(names, x)
    return names


PHP_MAGIC = re.compile(rb'@method[ \t]+(?:static[ \t]+)?(?:([^\n(]*?)[ \t]+)?(\w+)[ \t]*\(')


def php_magic_methods(node, src):
    """Métodos mágicos que declara el PHPDoc de la clase (`@method Tipo nombre(…)`, servidos por `__call`):
    (nombre, línea, tipo de retorno)."""
    prev = node.prev_named_sibling
    if prev is None or prev.type != 'comment' or not text(prev, src).startswith('/**'):
        return []
    out = []
    for m in PHP_MAGIC.finditer(src, prev.start_byte, prev.end_byte):
        out.append((m.group(2).decode('utf-8', 'replace'), src.count(b'\n', 0, m.start()) + 1,
                    (m.group(1) or b'').decode('utf-8', 'replace') or None))
    return out


def php_imports(node, src):
    if node.type != 'namespace_use_declaration':
        target = string_value(node, src)
        return [('relpath', target, None)] if target else []
    raw = re.sub(r'\s+', ' ', text(node, src)).strip().rstrip(';')
    raw = re.sub(r'^use (function |const )?', '', raw).strip()
    out = []
    for spec in expand(raw, '\\'):
        path, alias = split_alias(spec, ' as ')
        out.append(('fqn', path.strip('\\').replace('\\', '.'), alias))
    return out


def include_imports(node, src):
    path = node.child_by_field_name('path')
    if path is None:
        return []
    if path.type == 'system_lib_string':
        return [('angle', text(path, src).strip().strip('<>').strip(), None)]
    return [('relpath', strip_quotes(text(path, src)), None)]


def cfg_value(pred):
    """Valor de un predicado `cfg(…)` en Linux x86-64 (el entorno de los índices): True, False o None si no se sabe."""
    pred = pred.strip()
    m = re.fullmatch(r'(not|any|all)\s*\((.*)\)', pred, re.S)
    if m:
        parts, depth, cur = [], 0, ''
        for c in m.group(2):
            depth += (c == '(') - (c == ')')
            if c == ',' and depth == 0:
                parts.append(cur)
                cur = ''
            else:
                cur += c
        values = [cfg_value(p) for p in parts + [cur] if p.strip()]
        if m.group(1) == 'not':
            return None if not values or values[0] is None else not values[0]
        if m.group(1) == 'any':
            return True if True in values else None if None in values else False
        return False if False in values else None if None in values else True
    if pred in ('unix', 'target_family = "unix"'):
        return True
    if pred in ('windows', 'target_family = "windows"', 'target_family = "wasm"'):
        return False
    m = re.fullmatch(r'target_os\s*=\s*"(\w+)"', pred)
    return m.group(1) == 'linux' if m else None


def rust_cfg_off(node, src):
    """Ítem con `#[cfg(…)]` que no se compila en Linux (`#[cfg(windows)]`): si tiene un gemelo activo, el nodo es ese."""
    prev = node.prev_named_sibling
    while prev is not None and prev.type in ('attribute_item', 'line_comment', 'block_comment'):
        m = re.fullmatch(r'#\[\s*cfg\s*\((.*)\)\s*\]', text(prev, src).strip(), re.S) if prev.type == 'attribute_item' else None
        if m and cfg_value(m.group(1)) is False:
            return True
        prev = prev.prev_named_sibling
    return False


def rust_test(node, src):
    if node.type not in ('mod_item', 'function_item', 'impl_item'):
        return False
    prev = node.prev_named_sibling
    while prev is not None and prev.type in ('attribute_item', 'line_comment', 'block_comment'):
        if prev.type == 'attribute_item' and RUST_TEST.search(text(prev, src)):
            return True
        prev = prev.prev_named_sibling
    return False


def zig_test(node, src):
    return node.type == 'test_declaration'


def type_prefix(node, src):
    holder, inner = node.parent, node
    if holder is not None and holder.type in WRAP_TYPES and holder.named_children[0].id == node.id:
        holder, inner = holder.parent, holder
    prefix = []
    while holder is not None and holder.type in QUAL_TYPES:
        before = []
        for c in holder.named_children:
            if c.id == inner.id:
                break
            if 'argument' not in c.type:
                before += leaves(c, src)
        prefix = before + prefix
        if holder.parent is None or holder.parent.type != holder.type:
            break
        holder, inner = holder.parent, holder
    return holder, tuple(prefix)


def type_ref(node, src, parents):
    holder = node.parent
    if holder is None:
        return None
    if parents is not None and holder.type not in parents:
        typed = holder.child_by_field_name('type') or holder.child_by_field_name('returns')
        if typed is None or typed.id != node.id:
            return None
    top, prefix = type_prefix(node, src)
    if top is not None and top.type in QUAL_TYPES and top.parent is not None and top.parent.type in NAMESPACE_HOLDERS:
        return None
    return prefix, text(node, src)


def ruby_accessors(node, src):
    return [name for name, _ in ruby_accessor_sites(node, src)]


def ruby_accessor_sites(node, src):
    """(método, línea del símbolo) que declara una llamada en el cuerpo de una clase: `attr_reader :a` (`a`),
    `attr_accessor :a` (`a`, `a=`) y los delegadores de `Forwardable` (`def_delegators :obj, :a, :b`;
    `def_delegator :obj, :m, :alias`). La línea es la del símbolo, que puede ir en otra línea de la llamada."""
    method, args = node.child_by_field_name('method'), node.child_by_field_name('arguments')
    kind = text(method, src) if method is not None and node.child_by_field_name('receiver') is None else ''
    if args is None:
        return []
    if kind in RUBY_DELEGATORS:
        # solo en el cuerpo de la clase (dentro de un bloque cualquiera, `self` es otro objeto)
        holder = node.parent.parent if node.parent is not None and node.parent.type == 'body_statement' else None
        if holder is None or holder.type not in ('class', 'module', 'singleton_class') and \
                not (holder.type == 'do_block' and holder.parent is not None and holder.parent.parent is not None and
                     ruby_struct_class(holder.parent.parent, src)):
            return []
        kids = args.named_children
        if len(kids) < 2 or any(a.type != 'simple_symbol' for a in kids[1:]):
            return []
        names = [(text(a, src)[1:], a.start_point[0] + 1) for a in kids[1:]]
        return names if kind.endswith('s') else names[-1:] if len(names) == 2 else names[:1]
    if kind not in RUBY_ACCESSORS:
        return []
    return [(text(a, src).lstrip(':') + suffix, a.start_point[0] + 1) for a in args.named_children if a.type == 'simple_symbol'
            for suffix in RUBY_ACCESSORS[kind]]


def ruby_struct_class(node, src):
    """`Stub = Struct.new(:host, :path) do … end` (o `Data.define(:a)`): la constante es una clase con un accesor por
    miembro y los métodos del bloque. Devuelve (nombre, accesores, bloque) o None."""
    if node.type != 'assignment':
        return None
    left, right = node.child_by_field_name('left'), node.child_by_field_name('right')
    if left is None or left.type != 'constant' or right is None or right.type != 'call':
        return None
    recv, method = right.child_by_field_name('receiver'), right.child_by_field_name('method')
    if recv is None or method is None:
        return None
    kind = (text(recv, src).removeprefix('::'), text(method, src))
    if kind not in (('Struct', 'new'), ('Data', 'define')):
        return None
    args = right.child_by_field_name('arguments')
    names = [text(a, src)[1:] for a in (args.named_children if args is not None else ()) if a.type == 'simple_symbol']
    block = right.child_by_field_name('block')
    body = block.child_by_field_name('body') if block is not None else None
    own = {text(m.child_by_field_name('name'), src) for m in (body.named_children if body is not None else ())
           if m.type == 'method' and m.child_by_field_name('name') is not None}
    suffixes = ('',) if kind[0] == 'Data' else ('', '=')
    return text(left, src), [n + x for n in names for x in suffixes if n + x not in own], body


def ruby_function_name(node, src):
    """Nombre tal cual: `body=` (escritura), `<=>`, `[]`, `call!`."""
    name = node.child_by_field_name('name')
    return None, (text(name, src) if name is not None and name.type in ('setter', 'operator') else last_name(name, src) if name is not None else None)


def ruby_singleton(node):
    """`def self.x` o un `def` dentro de `class << self`: método de la clase, no de sus instancias."""
    if node.type == 'singleton_method':
        return True
    cur = node.parent
    while cur is not None and cur.type not in ('class', 'module'):
        if cur.type == 'singleton_class':
            return True
        cur = cur.parent
    return False


def ruby_owner_name(node, src):
    cur = node.parent
    while cur is not None and cur.type not in ('class', 'module'):
        cur = cur.parent
    return last_name(cur.child_by_field_name('name'), src) if cur is not None else None


def ruby_instance_methods(root, src):
    """(clase, método) de instancia: un método de clase homónimo (`def self.call` junto a `def call`) es otro nodo."""
    out, stack = set(), [root]
    while stack:
        n = stack.pop()
        stack.extend(n.named_children)
        if n.type == 'method' and not ruby_singleton(n):
            owner, name = ruby_owner_name(n, src), ruby_function_name(n, src)[1]
            if owner and name:
                out.add((owner, name))
    return out


def ruby_alias(node, src):
    """`alias nuevo viejo` o `alias_method :nuevo, :viejo`: (nuevo, viejo)."""
    if node.type == 'alias':
        names = [text(c, src).lstrip(':') for c in node.named_children]
        return tuple(names) if len(names) == 2 else None
    method, args = node.child_by_field_name('method'), node.child_by_field_name('arguments')
    if method is None or text(method, src) != 'alias_method' or args is None or node.child_by_field_name('receiver') is not None:
        return None
    names = [text(a, src).lstrip(':').strip('\'"') for a in args.named_children if a.type in ('simple_symbol', 'string')]
    return tuple(names) if len(names) == 2 else None


def ruby_mixins(node, src):
    """`include M`, `extend M`, `prepend M` en el cuerpo de una clase: M aporta métodos como una base."""
    method, args = node.child_by_field_name('method'), node.child_by_field_name('arguments')
    if node.type != 'call' or method is None or args is None or node.child_by_field_name('receiver') is not None or \
            text(method, src) not in ('include', 'extend', 'prepend'):
        return []
    return [last_name(a, src) for a in args.named_children if a.type in ('constant', 'scope_resolution') and last_name(a, src)]


def ruby_locals(scope, src):
    key = (id(src), scope.start_byte, scope.end_byte)
    if RUBY_LOCALS.get('src') is not src:
        RUBY_LOCALS.clear()
        RUBY_LOCALS['src'] = src
    if key not in RUBY_LOCALS:
        found, stack = set(), list(scope.named_children)
        while stack:
            n = stack.pop()
            if n.type in RUBY_BOUNDARIES or n.type in RUBY_BLOCKS:
                if n.type in RUBY_BLOCKS:
                    params = n.child_by_field_name('parameters')
                    stack += [params] if params is not None and n is not scope else []
                continue
            if n.type in RUBY_BINDERS:
                targets = [n.child_by_field_name('left')] if n.type in ('assignment', 'operator_assignment') else [n]
                for target in targets:
                    if target is not None and target.type in ('element_reference', 'call'):
                        stack.append(target)
                    elif target is not None and target.type == 'identifier':
                        found.add(text(target, src))
                    elif target is not None:
                        found.update(text(x, src) for x in target.named_children if x.type == 'identifier')
                        stack += [x for x in target.named_children if x.type != 'identifier']
            stack += n.named_children
        params = scope.child_by_field_name('parameters')
        if params is not None:
            found.update(text(x, src) for x in params.named_children if x.type == 'identifier')
            found.update(text(x.child_by_field_name('name'), src) for x in params.named_children if x.child_by_field_name('name') is not None)
        RUBY_LOCALS[key] = found
    return RUBY_LOCALS[key]


def ruby_bare(node, src):
    if RUBY_BARE.get('src') is not src:
        RUBY_BARE.clear()
        RUBY_BARE['src'] = src
    key = (node.start_byte, node.end_byte)
    if key not in RUBY_BARE:
        RUBY_BARE[key] = ruby_bare_name(node, src)
    return list(RUBY_BARE[key])


def ruby_bare_name(node, src):
    parent = node.parent
    default = parent is not None and parent.type in ('optional_parameter', 'keyword_parameter', 'pair') and \
        parent.child_by_field_name('value') == node
    if parent is None or parent.type in RUBY_NOT_CALLS and not default or parent.type == 'call' and parent.child_by_field_name('method') == node:
        return []
    if parent.type in ('assignment', 'operator_assignment') and parent.child_by_field_name('left') == node:
        return []
    name, scope = text(node, src), parent
    while scope is not None:
        if (scope.type in RUBY_BLOCKS or scope.type in RUBY_BOUNDARIES) and name in ruby_locals(scope, src):
            return []
        if scope.type in RUBY_BOUNDARIES:
            break
        scope = scope.parent
    return [name]


def ruby_struct_members(node, src):
    """Accesores que genera `class X < Struct.new(:a, :b)` (o `Data.define(:a)`): no son nodos, pero un método del
    proyecto con ese nombre deja de ser el único candidato para un receptor sin tipo."""
    sup = node.child_by_field_name('superclass')
    call = sup.named_children[0] if sup is not None and sup.named_children else None
    head = (call.child_by_field_name('receiver'), call.child_by_field_name('method')) if call is not None and call.type == 'call' else ()
    if None in head or tuple(text(x, src) for x in head) not in (('Struct', 'new'), ('Data', 'define')):
        return set()
    args = call.child_by_field_name('arguments')
    names = {text(a, src).lstrip(':') for a in (args.named_children if args is not None else ()) if a.type == 'simple_symbol'}
    return names | {x + '=' for x in names}


def ruby_index(node, src):
    """`self[k]` y `self[k] = v` llaman a los métodos `[]` y `[]=` de la propia clase."""
    obj, parent = node.child_by_field_name('object'), node.parent
    if obj is None or obj.type != 'self':
        return []
    write = parent is not None and parent.type in ('assignment', 'operator_assignment') and parent.child_by_field_name('left') == node
    return ['self', '[]=' if write else '[]']


def ruby_import(node, src):
    method = node.child_by_field_name('method')
    if method is None or node.child_by_field_name('receiver') is not None:
        return []
    kind = text(method, src)
    if kind not in ('require', 'require_relative', 'load', 'autoload'):
        return []
    args = node.child_by_field_name('arguments')
    if kind == 'autoload':
        found = [a for a in args.named_children if a.type == 'string'] if args is not None else []
        target = strip_quotes(text(found[-1], src)) if found else None
    else:
        target = string_value(args or node, src)
    if not target:
        return []
    return [('relpath' if kind != 'require' else 'suffix', target, None)]


def lua_import(node, src):
    name = node.child_by_field_name('name')
    if name is None or text(name, src) != 'require':
        return []
    target = string_value(node.child_by_field_name('arguments') or node, src)
    if not target:
        return []
    alias = None
    holder = node.parent.parent if node.parent is not None else None
    if holder is not None and holder.type == 'assignment_statement':
        names = holder.child_by_field_name('variable_list') or (holder.named_children[0] if holder.named_children else None)
        alias = last_name(names, src) if names is not None else None
    return [('lua', target, alias)]


def bash_import(node, src):
    name = node.child_by_field_name('name')
    arg = node.child_by_field_name('argument')
    if name is None or arg is None or text(name, src) not in ('source', '.'):
        return []
    target = re.split(r'[})]/|\$\w+/', strip_quotes(text(arg, src)))[-1]
    return [('relpath', target, None)] if target and not re.search(r'[$\s()<>]', target) else []


def dart_body(node):
    """Cuerpo de la función y, en un constructor, su lista de inicialización (`: _x = Scanner(s), super(…)`)."""
    holder = node.parent if node.parent is not None and node.parent.type in ('method_signature', 'declaration') else node
    after = holder.next_named_sibling if holder.type != 'declaration' else None
    parts = [after] if after is not None and after.type == 'function_body' else []
    return parts + [c for c in (holder.named_children if holder is not node else ()) if c.type in ('initializers', 'redirection')]


def dart_invokes(node):
    return node.type == 'selector' and bool(node.named_children) and node.named_children[0].type == 'argument_part'


def dart_callee(node, src):
    if not dart_invokes(node):
        return []
    parts, prev = [], node.prev_named_sibling
    while prev is not None and prev.type.endswith('selector') and not dart_invokes(prev):
        found = leaves(prev, src)
        if not found:
            return []
        parts.insert(0, found[-1])
        prev = prev.prev_named_sibling
    if prev is not None and prev.type.endswith('selector'):
        parts.insert(0, '')
    elif prev is not None and prev.type in IDENT:
        parts.insert(0, text(prev, src))
    return parts[-2:]


def dart_generic_parts(node, src):
    """`Caja<T>(x)`, `Caja<T>(a: x).m()` o `Clase.crear<T>(x)`: la gramática de Dart lo lee como dos comparaciones
    (`Caja < T > (x)`); escrito sin espacios y con un nombre de clase (o un miembro de una clase), es la llamada
    genérica. Devuelve (partes del nombre, nodo de los argumentos) o None."""
    kids = node.named_children
    if len(kids) < 3 or kids[1].type != 'relational_operator' or text(kids[1], src) != '>' or \
            kids[2].type not in ('parenthesized_expression', 'record_literal') or kids[1].end_byte != kids[2].start_byte or \
            kids[0].type != 'relational_expression' or any(k.type != 'selector' for k in kids[3:]):
        return None
    inner = kids[0].named_children
    if len(inner) < 3 or inner[0].type != 'identifier' or inner[-2].type != 'relational_operator' or \
            text(inner[-2], src) != '<' or inner[-3].end_byte != inner[-2].start_byte or \
            inner[-1].start_byte != inner[-2].end_byte or inner[-1].type not in ('identifier', 'type_identifier') or \
            kids[1].start_byte != inner[-1].end_byte:
        return None
    parts = [text(inner[0], src)]
    for sel in inner[1:-2]:
        found = leaves(sel, src) if sel.type == 'selector' and not dart_invokes(sel) else None
        if not found:
            return None
        parts.append(found[-1])
    if len(parts) > 2 or not parts[0].lstrip('_')[:1].isupper():
        return None
    return parts, kids[2]


def dart_generic_call(node, src):
    found = dart_generic_parts(node, src)
    return found[0] if found else []


def dart_constructor_call(node, src):
    """`_Wrapper<T>.seeded(x)`: constructor con nombre de una clase genérica (`constructor_invocation`)."""
    tid = next((c for c in node.named_children if c.type == 'type_identifier'), None)
    name = next((c for c in node.named_children if c.type == 'identifier'), None)
    return [text(tid, src), text(name, src)] if tid is not None and name is not None else []


def dart_delegation(node, src):
    """`: super._(…)` o `: this._(…)` en un constructor: llamada al constructor con nombre de la base o de la propia clase."""
    head = node.named_children[0] if node.named_children else None
    name = next((c for c in node.named_children if c.type == 'identifier'), None)
    if head is None or head.type not in ('super', 'this') or name is None or not any(c.type == 'arguments' for c in node.named_children):
        return []
    return [head.type, text(name, src)]


def dart_cascade(node, src):
    """`..metodo(…)` de una cascada: llamada sobre el receptor de la cascada."""
    sel = next((c for c in node.named_children if c.type == 'cascade_selector'), None)
    if sel is None or not any(c.type == 'argument_part' for c in node.named_children):
        return []
    name = next((c for c in sel.named_children if c.type == 'identifier'), None)
    return ['', text(name, src)] if name is not None else []


def dart_function_name(node, src):
    """Los constructores con nombre (`A.empty(…)`, `factory A.from(…)`) se llaman como su segunda parte."""
    if node.type in ('constructor_signature', 'factory_constructor_signature', 'constant_constructor_signature'):
        idents = [c for c in node.named_children if c.type == 'identifier']
        return None, text(idents[-1], src) if idents else None
    if node.type == 'operator_signature':
        params = node.child_by_field_name('parameters') or next((c for c in node.named_children if c.type == 'formal_parameter_list'), None)
        head = src[node.start_byte:params.start_byte if params is not None else node.end_byte].decode('utf-8', 'replace')
        return None, head.rsplit('operator', 1)[-1].strip() or None
    return None, last_name(node.child_by_field_name('name'), src)


def dart_bases(node, src):
    kinds = {'superclass', 'interfaces', 'mixins'} | ({'type_identifier'} if node.type == 'mixin_declaration' else set())
    return [x for c in node.named_children if c.type in kinds for x in base_names(c, src)]


def dart_import(node, src):
    target = string_value(node, src)
    if not target or target.startswith('dart:'):
        return []
    alias = next((text(c, src) for c in node.named_children if c.type == 'identifier'), None)
    if target.startswith('package:'):
        pkg, _, path = target[len('package:'):].partition('/')
        out = [('dartpkg', (pkg, path), alias)] if path else []
    else:
        out = [('relpath', target, alias)]
    shown = tuple(text(i, src) for c in node.named_children if c.type == 'combinator' and text(c, src).startswith('show')
                  for i in c.named_children if i.type == 'identifier')
    # la clase de directiva (import, export, part, part of) y los nombres de `show`, para `Linker.dart_scopes`
    return out + [('dartdir', (node.type,) + out[0][:2], shown)] if out else []


EX_DEFS = {'def', 'defp', 'defmacro', 'defmacrop', 'defguard', 'defguardp', 'defdelegate', 'defn', 'defnp'}
EX_MODULES = {'defmodule', 'defprotocol', 'defimpl'}
EX_IMPORTS = {'alias', 'import', 'use', 'require'}


def ex_target(node, src):
    target = node.child_by_field_name('target')
    return text(target, src) if target is not None and target.type == 'identifier' else None


def ex_args(node):
    args = next((c for c in node.named_children if c.type == 'arguments'), None)
    return args.named_children if args is not None else []


def ex_keyword(node, src, key):
    for c in ex_args(node):
        if c.type == 'keywords':
            for pair in c.named_children:
                k, v = pair.child_by_field_name('key'), pair.child_by_field_name('value')
                if k is not None and v is not None and text(k, src).strip().rstrip(':') == key:
                    return text(v, src)
    return None


def ex_module_name(node, src):
    kind = ex_target(node, src)
    if kind not in EX_MODULES:
        return None
    args = ex_args(node)
    if not args or args[0].type != 'alias':
        return None
    name = text(args[0], src)
    holder = node.parent
    while holder is not None and not (holder.type == 'call' and ex_target(holder, src) == 'defmodule'):
        holder = holder.parent
    outer = ex_module_name(holder, src) if holder is not None else None
    if kind == 'defimpl':
        target = ex_keyword(node, src, 'for') or outer
        return f'{name}.{target}' if target else name
    return f'{outer}.{name}' if outer else name


def ex_bases(node, src):
    if ex_target(node, src) == 'defimpl':
        args = ex_args(node)
        return [text(args[0], src)] if args and args[0].type == 'alias' else []
    out = []
    block = next((c for c in node.named_children if c.type == 'do_block'), None)
    for c in block.named_children if block is not None else []:
        inner = c.child_by_field_name('operand') if c.type == 'unary_operator' else None
        if inner is not None and inner.type == 'call' and ex_target(inner, src) == 'behaviour':
            out += [text(a, src) for a in ex_args(inner) if a.type == 'alias']
    return out


def ex_function_name(node, src):
    if ex_target(node, src) not in EX_DEFS:
        return None, None
    args = ex_args(node)
    head = args[0] if args else None
    if head is not None and head.type == 'binary_operator':
        op = head.child_by_field_name('operator')
        head = head.child_by_field_name('left') if op is not None and text(op, src) == 'when' else None
    if head is not None and head.type == 'call':
        head = head.child_by_field_name('target')
    return None, text(head, src) if head is not None and head.type == 'identifier' else None


def ex_callee(node, src):
    target = node.child_by_field_name('target')
    if target is None:
        return []
    if target.type == 'identifier':
        name = text(target, src)
        return [] if name in EX_DEFS | EX_MODULES | EX_IMPORTS else [name]
    left, right = target.child_by_field_name('left'), target.child_by_field_name('right')
    if target.type != 'dot' or left is None or right is None or right.type != 'identifier' or left.type not in ('alias', 'identifier'):
        return []
    qual = text(left, src)
    return ['self' if qual == '__MODULE__' else qual, text(right, src)]


def ex_import(node, src):
    kind = ex_target(node, src)
    args = ex_args(node)
    if kind not in EX_IMPORTS or not args or args[0].type not in ('alias', 'dot'):
        return []
    specs = expand(re.sub(r'\s+', '', text(args[0], src)), '.')
    alias = ex_keyword(node, src, 'as') if kind == 'alias' and len(specs) == 1 else None
    return [('open' if kind == 'import' else 'fqn', spec, alias) for spec in specs if not spec.startswith('__MODULE__')]


def hs_owner(node, src):
    if node.type != 'instance':
        return None
    found = leaves(node.child_by_field_name('patterns'), src)
    return found[0] if found else None


def hs_bases(node, src):
    return base_names(node.child_by_field_name('name'), src)


def hs_import(node, src):
    module, alias = node.child_by_field_name('module'), node.child_by_field_name('alias')
    if module is None:
        return []
    name = text(module, src)
    return [('module', name, text(alias, src) if alias is not None else name)]


def hs_callee(node, src):
    head = node.child_by_field_name('function')
    if head is None:
        return []
    if head.type == 'qualified':
        module, name = head.child_by_field_name('module'), head.child_by_field_name('id')
        return [text(module, src).rstrip('.'), text(name, src)] if module is not None and name is not None else []
    return [text(head, src)] if head.type in ('variable', 'constructor') else []


def zig_class_name(node, src):
    holder = node.parent
    if holder is None or holder.type != 'variable_declaration':
        return None
    return next((text(c, src) for c in holder.named_children if c.type == 'identifier'), None)


def zig_import(node, src):
    head = node.named_children[0] if node.named_children else None
    if head is None or text(head, src) != '@import':
        return []
    target = string_value(node, src)
    if not target or not target.endswith('.zig'):
        return []
    holder = node.parent
    alias = zig_class_name(node, src) if holder is not None and holder.type == 'variable_declaration' else None
    return [('relpath', target, alias)]


def ml_class_name(node, src):
    body = node.child_by_field_name('body')
    if node.type == 'module_binding' and body is not None and body.type in ('module_path', 'extended_module_path'):
        return None
    return first_ident(node, src)


def ml_function_name(node, src):
    if node.type != 'let_binding':
        return None, first_ident(node, src)
    pattern, body = node.child_by_field_name('pattern'), node.child_by_field_name('body')
    if pattern is None or pattern.type != 'value_name':
        return None, None
    params = any(c.type == 'parameter' for c in node.named_children)
    if not params and (body is None or body.type not in ('fun_expression', 'function_expression')):
        return None, None
    return None, text(pattern, src)


def ml_bases(node, src):
    body = node.child_by_field_name('body')
    out = []
    for c in body.named_children if body is not None else []:
        cls = c.child_by_field_name('class') if c.type == 'inheritance_definition' else None
        if cls is not None and cls.type == 'class_application':
            cls = cls.child_by_field_name('class')
        name = last_name(cls, src) if cls is not None else None
        if name:
            out.append(name)
    return out


def ml_import(node, src):
    holder = node.parent
    if holder is None or holder.type == 'module_path':
        return []
    found = leaves(node, src)
    if not found:
        return []
    if holder.type in ('open_module', 'include_module', 'open_expression'):
        return [('stem', found[0], None)]
    alias = first_ident(holder, src) if holder.type == 'module_binding' else found[0]
    return [('stem', found[0], alias or found[0])]


def jl_call_of(node):
    while node is not None and node.type in ('signature', 'typed_expression', 'where_expression'):
        node = node.named_children[0] if node.named_children else None
    return node if node is not None and node.type == 'call_expression' else None


def jl_function_name(node, src):
    call = jl_call_of(node.named_children[0] if node.named_children else None)
    if call is None or not call.named_children:
        return None, None
    found = leaves(call.named_children[0], src)
    return None, '.'.join(found) if found else None


def jl_head(node):
    return next((c for c in node.named_children if c.type == 'type_head'), None)


def jl_class_name(node, src):
    found = leaves(jl_head(node), src)
    return found[0] if found else None


def jl_bases(node, src):
    head = jl_head(node)
    pair = head.named_children[0] if head is not None and head.named_children else None
    if pair is None or pair.type != 'binary_expression':
        return []
    found = leaves(pair.named_children[-1], src)
    return found[:1]


def jl_import(node, src):
    if node.type == 'call_expression':
        head = node.named_children[0] if node.named_children else None
        target = string_value(node, src) if head is not None and text(head, src) == 'include' else None
        return [('relpath', target, None)] if target else []
    out = []
    for c in node.named_children:
        item = c.named_children[0] if c.type == 'selected_import' and c.named_children else c
        found = leaves(item, src)
        if found:
            out.append(('module', found[-1], found[-1]))
    return out


def objc_function_name(node, src):
    if node.type == 'function_definition':
        return c_function_name(node, src)
    return None, first_ident(node, src)


def objc_bases(node, src):
    sup = node.child_by_field_name('superclass')
    out = [text(sup, src)] if sup is not None else []
    for c in node.named_children:
        if c.type in ('parameterized_arguments', 'protocol_reference_list'):
            out += [x for x in base_names(c, src) if x not in out]
    return out


def objc_callee(node, src):
    receiver, method = node.child_by_field_name('receiver'), node.child_by_field_name('method')
    if method is None:
        return []
    if receiver is not None and receiver.type == 'message_expression':
        inner, sent = receiver.child_by_field_name('receiver'), receiver.child_by_field_name('method')
        if inner is not None and inner.type in IDENT and sent is not None and text(sent, src) in ('alloc', 'new'):
            receiver = inner
    return [text(receiver, src) if receiver is not None and receiver.type in IDENT else '', text(method, src)]


def objc_import(node, src):
    found = include_imports(node, src)
    return found + [('relpath', v[:-2] + '.m', None) for _, v, _ in found if v.endswith('.h')]


HCL_DEFS = {'resource': '{0}.{1}', 'data': 'data.{0}.{1}', 'module': 'module.{0}', 'variable': 'var.{0}',
            'output': 'output.{0}'}
HCL_SKIP = {'each', 'count', 'self', 'path', 'terraform', 'local', 'output'}


def hcl_kind(node, src):
    head = node.named_children[0] if node.named_children else None
    return text(head, src) if head is not None and head.type == 'identifier' else None


def hcl_class_name(node, src):
    holder = node.parent.parent if node.parent is not None else None
    pattern = HCL_DEFS.get(hcl_kind(node, src)) if holder is not None and holder.type == 'config_file' else None
    if pattern is None:
        return None
    labels = [strip_quotes(text(c, src)) for c in node.named_children[1:] if c.type in ('string_lit', 'identifier')]
    return pattern.format(*labels) if len(labels) >= pattern.count('{') else None


def hcl_callee(node, src):
    head = node.named_children[0] if node.named_children else None
    if head is None or head.type != 'variable_expr':
        return []
    root, attrs = text(head, src), []
    for c in node.named_children[1:]:
        if c.type != 'get_attr':
            break
        attrs.append(last_name(c, src))
    need = 2 if root == 'data' else 1
    if root in HCL_SKIP or len(attrs) < need or not all(attrs[:need]):
        return []
    return ['.'.join([root] + attrs[:need])]


def hcl_import(node, src):
    key = node.named_children[0] if node.named_children else None
    block = node.parent.parent if node.parent is not None else None
    if key is None or text(key, src) != 'source' or block is None or block.type != 'block' or hcl_kind(block, src) != 'module':
        return []
    target = string_value(node, src)
    return [('relpath', target, None)] if target and target.startswith('.') else []


def gradle_apply(node, src):
    key, value = node.child_by_field_name('key'), node.child_by_field_name('value')
    if key is None or value is None or text(key, src) != 'from':
        return []
    target = strip_quotes(text(value, src))
    return [('relpath', target, None)] if target.endswith(('.gradle', '.groovy')) else []


def pl_package(node, src):
    name = node.child_by_field_name('name')
    return text(name, src) if name is not None else None


def pl_strings(node, src):
    out = []
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type == 'string_content':
            out += text(n, src).split()
        stack.extend(n.named_children)
    return out


def pl_scope(node):
    block = next((c for c in node.named_children if c.type == 'block'), None)
    if block is not None:
        return block.named_children
    out, nxt = [], node.next_named_sibling
    while nxt is not None and nxt.type not in ('package_statement', 'class_statement'):
        out.append(nxt)
        nxt = nxt.next_named_sibling
    return out


def pl_parent_use(module):
    return module in ('parent', 'base') or module.endswith('::Base')


def pl_bases(node, src):
    out = []
    attrs = node.child_by_field_name('attributes')
    for attr in attrs.named_children if attrs is not None else []:
        name, value = attr.child_by_field_name('name'), attr.child_by_field_name('value')
        if name is not None and value is not None and text(name, src) == 'isa':
            out += text(value, src).split()[:1]
    for item in pl_scope(node):
        module = item.child_by_field_name('module') if item.type == 'use_statement' else None
        if module is not None and pl_parent_use(text(module, src)):
            out += [s for s in pl_strings(item, src) if s not in out]
        elif item.type == 'expression_statement' and re.match(r'\s*((our\s+)?@ISA\s*=|extends\b)', text(item, src)):
            out += [s for s in pl_strings(item, src) if s not in out]
    return out


def pl_function_name(node, src):
    name = node.child_by_field_name('name')
    return None, text(name, src).split('::')[-1] if name is not None else None


def pl_callee(node, src):
    if node.type == 'method_call_expression':
        method, invocant = node.child_by_field_name('method'), node.child_by_field_name('invocant')
        if method is None or invocant is None:
            return []
        who = text(invocant, src).lstrip('$')
        if who in ('self', 'class', 'this', '__PACKAGE__'):
            return [text(method, src)]
        return [who, text(method, src)] if invocant.type == 'bareword' else []
    function = node.child_by_field_name('function')
    if function is None:
        return []
    parts = text(function, src).lstrip('&').split('::')
    return ['::'.join(parts[:-1]), parts[-1]] if len(parts) > 1 else parts


def pl_import(node, src):
    if node.type == 'require_expression':
        target = string_value(node, src)
        if target:
            return [('relpath', target, None)]
        found = next((text(c, src) for c in node.named_children if c.type == 'bareword'), None)
        return [('module', found, found)] if found else []
    module = node.child_by_field_name('module')
    name = text(module, src) if module is not None else ''
    found = [('module', s, s) for s in pl_strings(node, src)] if pl_parent_use(name) else []
    return found + ([('module', name, name)] if name[:1].isupper() else [])


def fs_class_name(node, src):
    if node.type == 'module_defn':
        return first_ident(node, src)
    head = next((c for c in node.named_children if c.type == 'type_name'), None)
    return last_name(head.child_by_field_name('type_name') or head, src) if head is not None else None


def fs_bases(node, src):
    out = []
    for c in node.named_children:
        items = c.named_children if c.type == 'type_extension_elements' else [c]
        for item in items:
            if item.type in ('class_inherits_decl', 'interface_implementation') and item.named_children:
                out += [x for x in base_names(item.named_children[0], src) if x not in out]
    return out


def fs_function_name(node, src):
    if node.type == 'method_or_prop_defn':
        name = node.child_by_field_name('name')
        method = name.child_by_field_name('method') if name is not None else None
        return None, last_name(method or name, src) if name is not None else None
    left = node.named_children[0] if node.named_children else None
    body = node.child_by_field_name('body')
    if left is not None and left.type == 'function_declaration_left':
        return None, first_ident(left, src)
    if left is not None and left.type == 'value_declaration_left' and body is not None and body.type == 'fun_expression':
        return None, last_name(left, src)
    return None, None


def fs_callee(node, src):
    head = node.named_children[0] if node.named_children else None
    if head is None or head.type not in ('long_identifier_or_op', 'long_identifier', 'identifier'):
        return []
    found = leaves(head, src)
    return ['.'.join(found[:-1]), found[-1]] if len(found) > 1 else found


def fs_import(node, src):
    target = node.named_children[0] if node.named_children else None
    if target is None:
        return []
    name = re.sub(r'\s+', '', text(target, src))
    return [('open', name, None), ('pkg', name, None)]


def sol_function_name(node, src):
    if node.type == 'constructor_definition':
        return None, 'constructor'
    if node.type == 'fallback_receive_definition':
        found = re.match(r'\s*(fallback|receive)', text(node, src))
        return None, found.group(1) if found else None
    return None, last_name(node.child_by_field_name('name'), src)


def sol_import(node, src):
    source = node.child_by_field_name('source')
    if source is None:
        return []
    target = strip_quotes(text(source, src))
    named = node.child_by_field_name('import_name') is not None
    alias = node.child_by_field_name('alias')
    alias = text(alias, src) if alias is not None and not named else None
    out = [('relpath', target, alias)]
    if not target.startswith('.') and '/' in target:
        out.append(('suffix', target.split('/', 1)[1], alias))
        out.append(('extern', target, None))
    return out


def swift_import(node, src):
    name = next((c for c in node.named_children if c.type == 'identifier'), None)
    return [('extern', re.sub(r'\s+', '', text(name, src)), None)] if name is not None else []


def ps_bases(node, src):
    return [text(c, src) for c in node.named_children if c.type == 'simple_name'][1:]


def ps_function_name(node, src):
    return None, first_ident(node, src)


def ps_callee(node, src):
    if node.type == 'command':
        name = node.child_by_field_name('command_name')
        return [text(name, src)] if name is not None and name.type == 'command_name' else []
    return leaves(node, src)[-2:]


def ps_import(node, src):
    name = node.child_by_field_name('command_name')
    if name is None:
        return []
    elements = node.child_by_field_name('command_elements')
    words = [text(c, src) for c in elements.named_children if c.type != 'command_argument_sep'] if elements is not None else []
    head = text(name, src).lower()
    if name.type == 'command_name_expr':
        target = text(name, src)
    elif head == 'import-module' and words:
        target = words[-1]
    elif head == 'using' and len(words) > 1 and words[0].lower() == 'module':
        target = words[-1]
    else:
        return []
    target = re.sub(r'^\$PSScriptRoot[\\/]?', '', strip_quotes(target), flags=re.I).replace('\\', '/')
    if not target or '$' in target or target.startswith('-'):
        return []
    if '/' in target or target.lower().endswith(('.ps1', '.psm1')):
        return [('relpath', target, None)]
    return [('suffix', target, None)]


BODY_TYPES = {
    'block', 'compound_statement', 'class_body', 'declaration_list', 'function_body', 'field_declaration_list',
    'enum_variant_list', 'interface_body', 'enum_body', 'body_statement', 'do_block', 'protocol_body', 'enum_class_body',
    'template_body', 'contract_body', 'script_block', 'block_start', 'class_declarations', 'match',
    'implementation_definition', 'method_declaration', 'property_declaration', 'instance_variables',
    'annotation_type_body', 'struct_body', 'object_body',
}
HEAD_TYPES = {'signature', 'type_head'}
SIG_ANCHORS = {'template_declaration', 'type_definition', 'value_definition', 'module_definition', 'variable_declaration',
               'member_defn', 'method_signature'}
SIG_CUTS = {'fsharp': {'{', '='}, 'julia': {'{', 'operator'}}
END_LANGS = {'ruby', 'lua', 'julia', 'elixir'}
SIG_TAIL = re.compile(r'(\s*(=>|[={;,:]))+$')
END_TAIL = re.compile(r'(\s*(\bend\b|;))+$')
SIG_MAX = 300
DOC_MAX = 500
SLASH_DOC = (('///',), ('/**',), '*/')
C_DOC = (('//',), ('/*',), '*/')
HASH_DOC = (('#',), (), '')
ML_DOC = ((), ('(**',), '*)')
BLOCK_OPEN = {'*/': '/*', '*)': '(*', '-}': '{-', '#>': '<#'}
DOC_STYLE = {
    'go': C_DOC, 'rust': SLASH_DOC, 'java': SLASH_DOC, 'kotlin': SLASH_DOC, 'scala': SLASH_DOC, 'groovy': SLASH_DOC,
    'csharp': SLASH_DOC, 'php': SLASH_DOC, 'swift': SLASH_DOC, 'dart': SLASH_DOC, 'solidity': SLASH_DOC,
    'c': C_DOC, 'cpp': C_DOC, 'objc': C_DOC, 'ruby': HASH_DOC, 'bash': HASH_DOC, 'perl': HASH_DOC, 'elixir': HASH_DOC,
    'julia': HASH_DOC, 'lua': (('--',), (), ''), 'haskell': (('--',), ('{-|',), '-}'), 'zig': (('///',), (), ''),
    'ocaml': ML_DOC, 'ocaml_interface': ML_DOC, 'hcl': (('#', '//'), ('/*',), '*/'), 'fsharp': (('///',), ('(**',), '*)'),
    'powershell': (('#',), ('<#',), '#>'),
}
DOC_SKIP = re.compile(r'^(#!?\[|@\w|\[|//go:|//line |//nolint|//\s*\+build|//export |#!|#\s*(frozen_string_literal|rubocop|typed|-\*-))')
DOC_SKIP_HASH = re.compile(r'^(#!|#\s*(frozen_string_literal|rubocop|typed|-\*-))')
DOC_STOP = re.compile(r'^([@\\](param|return|returns|throws|exception|see|since|author|deprecated|example|var|type|'
                      r'property|method|todo|link|inheritdoc|api|package|license|copyright|custom|tparam|raise|raises|'
                      r'yield|yields|option|note|warning)\b|:(param|return|raises)\b|<p>|```)')
DOC_TAGS = re.compile(r'^[@\\](brief|summary|title|notice|dev|file|class|fn|struct|description|abstract)\b\s*')
ANNOTATED = {'java', 'kotlin', 'scala', 'groovy', 'dart', 'swift'}
MOD_TYPES = {'modifiers', 'modifier', 'visibility_modifier', 'access_modifier', 'storage_class_specifier', 'visibility'}
MOD_WORDS = {'pub', 'public', 'private', 'protected', 'internal', 'static', 'local', 'open', 'fileprivate', 'external'}
EX_PRIVATE = {'defp', 'defmacrop', 'defguardp', 'defnp'}
RUBY_LOCALS = {}
RUBY_BARE = {}
RUBY_BLOCKS = {'block', 'do_block', 'lambda'}
RUBY_BOUNDARIES = {'method', 'singleton_method', 'class', 'module', 'singleton_class', 'program'}
RUBY_BINDERS = {'assignment', 'operator_assignment', 'exception_variable', 'for', 'block_parameters', 'lambda_parameters',
                'method_parameters'}
RUBY_NOT_CALLS = {'method', 'singleton_method', 'method_parameters', 'block_parameters', 'lambda_parameters', 'keyword_parameter',
                  'optional_parameter', 'splat_parameter', 'hash_splat_parameter', 'block_parameter', 'left_assignment_list',
                  'rest_assignment', 'exception_variable', 'for', 'alias', 'undef', 'destructured_left_assignment',
                  'destructured_parameter', 'pair', 'block_argument', 'setter'}
RUBY_ACCESSORS = {'attr_reader': ('',), 'attr_writer': ('=',), 'attr_accessor': ('', '=')}
RUBY_DELEGATORS = {'def_delegators', 'def_instance_delegators', 'def_delegator', 'def_instance_delegator'}
RUBY_SECTIONS = {'private', 'protected', 'public', 'module_function', 'private_class_method'}
JAVA_DEFAULT = {'java': 'internal'}
TYPED_LANGS = {'java', 'kotlin', 'rust', 'dart', 'php', 'csharp', 'ruby'}
RUST_NESTED_ITEMS = {'function_item', 'struct_item', 'enum_item', 'union_item', 'trait_item', 'impl_item', 'type_item'}
RUST_MACRO_SKIP = {'attribute_item', 'inner_attribute_item', 'attribute', 'macro_definition', 'macro_rule'}
CALLS_KOTLIN = {'call_expression': (None,), 'constructor_invocation': (None,), 'constructor_delegation_call': (None,)}
C_SYSTEM = ('sys/', 'bits/', 'linux/', 'arpa/', 'netinet/', 'net/', 'mach/', 'mach-o/', 'asm/', 'machine/')
EXTERN_STD = {
    'swift': STD_ROOTS['swift'] | {'XCTest', 'Darwin', 'Glibc', 'os', 'CoreGraphics', 'CoreData', 'CoreFoundation',
                                   'Security', 'ObjectiveC', 'QuartzCore', 'CoreLocation', 'MapKit', 'WebKit', 'Network',
                                   'CryptoKit', 'AVFoundation', 'CoreImage', 'Observation', 'Testing', 'WatchKit'},
    'objc': {'Foundation', 'UIKit', 'AppKit', 'CoreFoundation', 'CoreGraphics', 'QuartzCore', 'Security', 'objc'},
    'lua': STD_ROOTS['lua'],
    'julia': STD_ROOTS['julia'] | set('''LinearAlgebra Statistics Random Test Dates Printf Distributed SparseArrays Pkg
        InteractiveUtils Serialization Sockets Markdown Logging Unicode UUIDs Libdl SHA TOML DelimitedFiles Mmap
        SharedArrays Profile REPL FileWatching Base64 CRC32c LibGit2 Downloads Tar ArgTools NetworkOptions'''.split()),
    'perl': STD_ROOTS['perl'] | {'Exporter', 'Carp', 'Data::Dumper', 'Scalar::Util', 'List::Util', 'File::Spec',
                                 'File::Basename', 'File::Path', 'File::Temp', 'Getopt::Long', 'Time::HiRes', 'Encode',
                                 'Storable', 'IO::File', 'IO::Handle', 'FindBin', 'Cwd', 'Test::More'},
    'haskell': {'Prelude'},
    'elixir': {'Kernel', 'Enum', 'String', 'Map', 'List', 'Keyword', 'Process', 'Agent', 'Task', 'GenServer',
               'Supervisor', 'Application', 'Logger', 'IO', 'File', 'Path', 'System', 'Integer', 'Float', 'Atom',
               'Tuple', 'Bitwise', 'Record', 'Registry', 'ExUnit', 'ExUnit.Case', 'Mix', 'Mix.Project', 'Code', 'Macro',
               'Module', 'Stream', 'Regex', 'URI', 'Base', 'DateTime', 'Date', 'Time', 'NaiveDateTime', 'Access',
               'Protocol', 'Inspect', 'Exception', 'MapSet', 'Range', 'Port', 'Node', 'DynamicSupervisor'},
}


def collapse(value, limit):
    value = ' '.join(value.split())
    return value if len(value) <= limit else value[:limit - 1].rstrip() + '…'


def sig_anchor(node):
    holder = node.parent
    if holder is not None and holder.type in SIG_ANCHORS and sum(c.type == node.type for c in holder.named_children) == 1:
        return holder
    return node


def hs_signature(node, src, name):
    prev = node.prev_named_sibling
    if node.type == 'function' and prev is not None and prev.type == 'signature':
        named = prev.child_by_field_name('name')
        if named is not None and text(named, src) == name:
            return prev
    return None


def header_end(node, lang):
    body = node.child_by_field_name('body')
    cuts = SIG_CUTS.get(lang, ('{',))
    for i, c in enumerate(node.children):
        if body is not None and c.start_byte >= body.start_byte:
            return body.start_byte
        if c.type in BODY_TYPES or c.type in cuts or (i and 'comment' in c.type):
            return c.start_byte
        if c.type in HEAD_TYPES:
            return c.end_byte
    if lang == 'elixir':
        for c in ex_args(node):
            if c.type == 'keywords':
                return c.start_byte
    return node.end_byte


def decorated(node):
    return 'annotation' in node.type or 'attribute' in node.type or 'comment' in node.type


def header_anchor(node):
    """Primer elemento de la declaración tras sus anotaciones o atributos (`@Deprecated(…)`, `[Attr]`)."""
    skipped = False
    for c in node.children:
        if c.type in ('modifiers', 'modifier') and c.child_count:
            inner = next((x for x in c.children if not decorated(x)), None)
            if inner is not None:
                return inner if inner.start_byte > c.start_byte else (c if skipped else node)
            skipped = True
            continue
        if not decorated(c):
            return c if skipped else node
        skipped = True
    return node


def header_start(node):
    return header_anchor(node).start_byte


def decl_line(node):
    """Línea de una definición: la de su declaración, sin las anotaciones o atributos que la preceden (como el `def` de
    Python tras sus decoradores); un bloque de anotaciones largo no aleja la definición de su nombre."""
    return header_anchor(node).start_point[0] + 1


def placed(node, line=None):
    """Posición de un nodo: `line` es su primera línea, con las anotaciones o atributos (`@Query("…")`, que los puentes
    leen dentro del rango del nodo), y `decl` la de la declaración cuando es otra."""
    start = line or node.start_point[0] + 1
    decl = line or decl_line(node)
    return {'line': start, 'decl': decl} if decl != start else {'line': start}


def signature(node, src, lang, anchor):
    end = header_end(node, lang)
    start = header_start(anchor)
    head = src[start if start < end else anchor.start_byte:end][:SIG_MAX * 6].decode('utf-8', errors='replace')
    if lang == 'go' and node.type == 'type_spec':
        head = 'type ' + head.split('{', 1)[0]
    head = ' '.join(head.split())
    head = SIG_TAIL.sub('', head)
    if lang in END_LANGS:
        head = END_TAIL.sub('', head)
    return collapse(head, SIG_MAX) if head else None


def line_above(src, pos):
    begin = src.rfind(b'\n', 0, pos - 1) + 1
    return begin, src[begin:pos - 1].decode('utf-8', errors='replace').strip()


def comment_lines(src, start, lang):
    style = DOC_STYLE.get(lang)
    if style is None:
        return []
    prefixes, openers, closer = style
    marker = BLOCK_OPEN.get(closer)
    skip = DOC_SKIP_HASH if '#' in prefixes else DOC_SKIP
    pos = src.rfind(b'\n', 0, start) + 1
    out = []
    while pos > 0 and len(out) < 200:
        pos, line = line_above(src, pos)
        if not line:
            break
        if closer and line.endswith(closer):
            if out:
                break
            block = [line]
            while marker not in line and pos > 0 and len(block) < 200:
                pos, line = line_above(src, pos)
                block.append(line)
            return block[::-1] if line.startswith(openers) else []
        if skip.match(line) and (lang in ANNOTATED or not line.startswith('@')):
            if out:
                break
            continue
        if prefixes and line.startswith(prefixes):
            out.append(line)
            continue
        break
    out.reverse()
    if lang == 'haskell' and out and not re.match(r'--\s*\|', out[0]):
        return []
    return out


def doc_paragraph(lines, lang):
    lines = [re.sub(r'^\s*(?:/\*+!?|\(\*+|\{-\||<#)', '', line) for line in lines]
    lines = [re.sub(r'(?:\*+/|\*+\)|-\}|#>)\s*$', '', line) for line in lines]
    lines = [re.sub(r'^\s*(?://[/!]?|--+\s*\|?|#+|\*(?![*/]))\s?', '', line).strip() for line in lines]
    if lang in ('csharp', 'fsharp') and any('<' in line for line in lines):
        joined = '\n'.join(lines)
        found = re.search(r'<summary>(.*?)</summary>', joined, re.S)
        joined = found.group(1) if found else joined
        joined = re.sub(r'<(?:see|seealso|paramref|typeparamref)\s+\w+="([^"]*)"\s*/>', lambda m: m.group(1).split(':')[-1], joined)
        lines = [re.sub(r'<[^>]+>', '', line).strip() for line in joined.split('\n')]
    out = []
    for line in lines:
        if not line or DOC_STOP.match(line) or (lang == 'powershell' and re.match(r'\.[A-Z]+\b', line)):
            if out:
                break
            continue
        line = DOC_TAGS.sub('', line)
        parts = re.split(r'\s[@\\](?:param|returns?|throws|exception|see)\b', re.sub(r'\{@\w+\s+([^}]*)\}', r'\1', line))
        if parts[0]:
            out.append(parts[0])
        if len(parts) > 1:
            break
    return collapse(' '.join(out), DOC_MAX) if out else None


def string_doc(raw):
    raw = re.sub(r'^~[sS]', '', raw.strip())
    quote = '"""' if raw.startswith('"""') else '"' if raw.startswith('"') else None
    if quote is None:
        return None
    raw = raw[len(quote):]
    raw = raw[:-len(quote)] if raw.endswith(quote) else raw
    lines = raw.split('\n')
    while lines and not lines[0].strip():
        lines.pop(0)
    indent = min((len(x) - len(x.lstrip()) for x in lines if x.strip()), default=0)
    lines = [x[indent:] for x in lines]
    if lines and lines[0].startswith('    '):
        while lines and lines[0].strip():
            lines.pop(0)
    out = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith(('## ', '# ', '```')):
            if out:
                break
            continue
        out.append(line)
    return collapse(' '.join(out), DOC_MAX) if out else None


def ex_attribute(node, src):
    if node is None or node.type != 'unary_operator':
        return None, None
    operand = node.child_by_field_name('operand')
    if operand is None or operand.type != 'call':
        return None, None
    args = ex_args(operand)
    return ex_target(operand, src), args[0] if args else None


def ex_doc(node, src, kind):
    if kind == 'class':
        block = next((c for c in node.named_children if c.type == 'do_block'), None)
        for c in block.named_children[:12] if block is not None else []:
            name, value = ex_attribute(c, src)
            if name == 'moduledoc':
                return string_doc(text(value, src)) if value is not None else None
        return None
    prev = node.prev_named_sibling
    while prev is not None and prev.type == 'unary_operator':
        name, value = ex_attribute(prev, src)
        if name == 'doc':
            return string_doc(text(value, src)) if value is not None else None
        prev = prev.prev_named_sibling
    return False


def jl_doc(node, src):
    prev = node.prev_named_sibling
    if prev is not None and prev.type == 'string_literal' and prev.end_point[0] >= node.start_point[0] - 1:
        return string_doc(text(prev, src))
    return False


def documentation(node, src, lang, kind, anchor):
    found = False
    if lang == 'elixir':
        found = ex_doc(node, src, kind)
    elif lang == 'julia':
        found = jl_doc(node, src)
    if found is not False:
        return found
    return doc_paragraph(comment_lines(src, anchor.start_byte, lang), lang)


def module_doc(src, lang):
    if lang != 'rust':
        return None
    found = re.match(rb'\s*((?:[ \t]*//![^\n]*\n?)+)', src)
    if not found:
        return None
    return doc_paragraph(found.group(1).decode('utf-8', errors='replace').split('\n'), lang)


def modifier_words(node, src):
    words = set()
    for c in node.children:
        if c.type in MOD_TYPES:
            parts = c.children if c.type == 'modifiers' and c.child_count else [c]
            for p in parts:
                if 'annotation' not in p.type and 'attribute' not in p.type:
                    words.update(re.findall(r'[a-z]+', text(p, src)))
        elif not c.is_named and c.type in MOD_WORDS:
            words.add(c.type)
    return words


def enclosing(node, classes):
    holder = node.parent
    while holder is not None:
        if holder.type in classes:
            return holder
        holder = holder.parent
    return None


def ruby_visibility(node, src):
    if node.type == 'singleton_method':
        return 'public'
    holder = node.parent
    if holder is not None and holder.type == 'argument_list' and holder.parent is not None and holder.parent.type == 'call':
        method = holder.parent.child_by_field_name('method')
        word = text(method, src) if method is not None else ''
        if word in ('private', 'protected', 'public'):
            return word
    prev = node.prev_named_sibling
    while prev is not None:
        if prev.type == 'identifier' and text(prev, src) in RUBY_SECTIONS:
            word = text(prev, src)
            return word if word in ('private', 'protected') else 'public'
        if prev.type in ('class', 'module'):
            break
        prev = prev.prev_named_sibling
    return 'public'


def cpp_visibility(node, src, words):
    holder = node.parent
    if holder is not None and holder.type == 'field_declaration_list':
        prev = node.prev_named_sibling
        while prev is not None:
            if prev.type == 'access_specifier':
                return re.sub(r'\W', '', text(prev, src))
            prev = prev.prev_named_sibling
        owner = holder.parent
        return 'private' if owner is not None and owner.type == 'class_specifier' else 'public'
    if 'static' in words:
        return 'private'
    while holder is not None:
        if holder.type == 'namespace_definition' and holder.child_by_field_name('name') is None:
            return 'private'
        holder = holder.parent
    return 'public'


def visibility(node, src, lang, name, anchor):
    short = (name or '').rsplit('.', 1)[-1]
    if lang == 'go':
        return 'public' if short[:1].isupper() else 'private'
    if lang in ('dart', 'perl', 'julia'):
        return 'private' if short.startswith('_') else 'public'
    if lang == 'elixir':
        return 'private' if ex_target(node, src) in EX_PRIVATE else 'public'
    if lang == 'ruby':
        return ruby_visibility(node, src) if node.type in ('method', 'singleton_method') else 'public'
    words = modifier_words(node, src)
    if anchor is not node:
        words |= modifier_words(anchor, src)
    if lang == 'fsharp' and node.named_children:
        words |= modifier_words(node.named_children[0], src)
    if lang in ('c', 'cpp', 'objc'):
        return cpp_visibility(node, src, words)
    if lang == 'lua':
        return 'private' if 'local' in words else 'public'
    if lang == 'rust':
        vis = next((c for c in node.children if c.type == 'visibility_modifier'), None)
        if vis is not None:
            return 'public' if text(vis, src).strip() == 'pub' else 'internal'
        holder = enclosing(node, {'trait_item', 'impl_item', 'source_file', 'mod_item'})
        if holder is not None and (holder.type == 'trait_item' or (holder.type == 'impl_item' and holder.child_by_field_name('trait') is not None)):
            return 'public'
        return 'private'
    if lang == 'zig':
        return 'public' if 'pub' in words else 'private'
    for word, vis in (('protected', 'protected'), ('private', 'private'), ('fileprivate', 'private'), ('internal', 'internal'),
                      ('public', 'public'), ('open', 'public'), ('external', 'public')):
        if word in words:
            return vis
    if lang in ('java', 'csharp', 'groovy', 'kotlin', 'swift', 'scala', 'php'):
        holder = enclosing(node, LANGS[lang]['classes'])
        if lang == 'swift' and holder is not None and holder.type == 'protocol_declaration':
            return visibility(holder, src, lang, '', holder)
        if holder is not None and holder.type in ('interface_declaration', 'protocol_declaration', 'annotation_type_declaration'):
            return 'public'
        if lang == 'csharp':
            return 'private' if holder is not None else 'internal'
        if lang == 'swift':
            return 'internal'
        return JAVA_DEFAULT.get(lang, 'public')
    return 'public'


def describe(node, src, lang, kind, name):
    anchor = sig_anchor(node)
    head = hs_signature(node, src, name) if lang == 'haskell' else None
    end = node.end_point[0] + (0 if node.end_point[1] == 0 and node.end_point[0] > node.start_point[0] else 1)
    return dict(
        sig=collapse(text(head, src), SIG_MAX) if head is not None else signature(node, src, lang, anchor),
        doc=documentation(node, src, lang, kind, head or anchor), end=end, vis=visibility(node, src, lang, name, anchor),
    )


def line_count(src):
    return src.count(b'\n') + (1 if src and not src.endswith(b'\n') else 0)


LANGS = {
    'go': dict(
        exts=('.go',), grammar=('tree_sitter_go', 'language'), family='go',
        classes={'type_spec'}, functions={'function_declaration', 'method_declaration'}, fn_name=go_function_name,
        calls={'call_expression': ('function',)}, imports={'import_spec': go_imports}, package={'package_clause'},
        types=({'type_identifier'}, None), refs={'selector_expression'}, collect=(GO_DECLS, go_collect),
    ),
    'rust': dict(
        exts=('.rs',), grammar=('tree_sitter_rust', 'language'), family='rust',
        classes={'struct_item', 'enum_item', 'trait_item', 'union_item', 'type_item'}, class_bases=rust_supertraits,
        functions={'function_item', 'function_signature_item'}, owner=rust_owner, owner_bases=rust_bases,
        calls={'call_expression': ('function',), 'struct_expression': ('name',), 'token_tree': rust_macro_callee},
        imports={'use_declaration': rust_imports, 'mod_item': rust_imports, 'extern_crate_declaration': rust_imports},
        types=({'type_identifier'}, None), tests=rust_test,
    ),
    'java': dict(
        exts=('.java',), grammar=('tree_sitter_java', 'language'), family='jvm',
        classes={'class_declaration', 'interface_declaration', 'enum_declaration', 'record_declaration',
                 'annotation_type_declaration'},
        functions={'method_declaration'}, bases={'superclass', 'super_interfaces'},
        calls={'method_invocation': ('object', 'name'), 'object_creation_expression': ('type',),
               'explicit_constructor_invocation': ('constructor',)},
        anonymous={'enum_constant', 'object_creation_expression'},
        imports={'import_declaration': dotted_imports(r'^import (static )?', ' as ', {'*'})},
        package={'package_declaration'}, types=({'type_identifier'}, None),
    ),
    'kotlin': dict(
        exts=('.kt', '.kts'), grammar=('tree_sitter_kotlin', 'language'), family='jvm',
        classes={'class_declaration', 'object_declaration', 'companion_object', 'type_alias'}, functions={'function_declaration'},
        class_name=kt_class_name, bases={'delegation_specifiers', 'delegation_specifier'}, calls=CALLS_KOTLIN,
        anonymous={'object_literal'},
        imports={'import': dotted_imports(r'^import ', ' as ', {'*'})}, package={'package_header'},
        types=({'identifier'}, {'user_type'}),
    ),
    'scala': dict(
        exts=('.scala', '.sc'), grammar=('tree_sitter_scala', 'language'), family='jvm',
        classes={'class_definition', 'object_definition', 'trait_definition', 'enum_definition'},
        functions={'function_definition', 'function_declaration'}, bases={'extends_clause'},
        calls={'call_expression': ('function',)},
        imports={'import_declaration': dotted_imports(r'^import ', ' => ', {'_', '*'})}, package={'package_clause'},
        types=({'type_identifier'}, None),
    ),
    'csharp': dict(
        exts=('.cs',), grammar=('tree_sitter_c_sharp', 'language'), family='csharp',
        classes={'class_declaration', 'interface_declaration', 'struct_declaration', 'record_declaration',
                 'enum_declaration', 'delegate_declaration'},
        functions={'method_declaration'}, bases={'base_list'},
        calls={'invocation_expression': ('function',), 'object_creation_expression': ('type',),
               'constructor_initializer': (None,), 'attribute': ('name',)},
        imports={'using_directive': csharp_imports},
        package={'namespace_declaration', 'file_scoped_namespace_declaration'},
        types=({'identifier'}, {'generic_name', 'type_argument_list', 'qualified_name', 'nullable_type', 'array_type',
                               'pointer_type', 'ref_type'}),
    ),
    'php': dict(
        exts=('.php',), grammar=('tree_sitter_php', 'language_php'), family='php',
        classes={'class_declaration', 'interface_declaration', 'trait_declaration', 'enum_declaration'},
        functions={'method_declaration', 'function_definition'}, class_bases=php_bases,
        calls={'function_call_expression': ('function',), 'member_call_expression': ('object', 'name'),
               'nullsafe_member_call_expression': ('object', 'name'), 'scoped_call_expression': ('scope', 'name'),
               'object_creation_expression': (None,), 'attribute': (None,)},
        imports={'namespace_use_declaration': php_imports, 'require_expression': php_imports,
                 'require_once_expression': php_imports, 'include_expression': php_imports,
                 'include_once_expression': php_imports},
        package={'namespace_definition'},
    ),
    'ruby': dict(
        exts=('.rb', '.rake', '.gemspec', '.ru', '.podspec', '.jbuilder', '.thor'), grammar=('tree_sitter_ruby', 'language'), family='ruby',
        classes={'class', 'module'}, namespaces={'module'}, functions={'method', 'singleton_method'}, bases={'superclass'},
        fn_name=ruby_function_name,
        calls={'call': ('receiver', 'method'), 'identifier': ruby_bare, 'element_reference': ruby_index}, imports={'call': ruby_import},
    ),
    'c': dict(
        exts=('.c',), grammar=('tree_sitter_c', 'language'), family='c',
        classes={'struct_specifier', 'union_specifier', 'enum_specifier'}, class_name=c_class_name,
        functions={'function_definition'}, fn_name=c_function_name,
        calls={'call_expression': ('function',)}, imports={'preproc_include': include_imports},
        types=({'type_identifier'}, None),
    ),
    'cpp': dict(
        exts=('.cc', '.cpp', '.cxx', '.c++', '.h', '.hh', '.hpp', '.hxx', '.ipp'), grammar=('tree_sitter_cpp', 'language'),
        family='c', classes={'class_specifier', 'struct_specifier', 'union_specifier', 'enum_specifier'},
        class_name=c_class_name, functions={'function_definition'}, fn_name=c_function_name, bases={'base_class_clause'},
        calls={'call_expression': ('function',), 'new_expression': ('type',)},
        imports={'preproc_include': include_imports}, types=({'type_identifier'}, None),
    ),
    'swift': dict(
        exts=('.swift',), grammar=('tree_sitter_swift', 'language'), family='swift',
        classes={'class_declaration', 'protocol_declaration'}, owner=swift_owner,
        functions={'function_declaration', 'protocol_function_declaration'}, bases={'inheritance_specifier'},
        calls={'call_expression': (None,)}, imports={'import_declaration': swift_import},
        types=({'type_identifier'}, None),
    ),
    'lua': dict(
        exts=('.lua',), grammar=('tree_sitter_lua', 'language'), family='lua',
        classes=set(), functions={'function_declaration'}, fn_name=lua_function_name,
        calls={'function_call': ('name',)}, imports={'function_call': lua_import},
    ),
    'bash': dict(
        exts=('.sh', '.bash', '.zsh'), grammar=('tree_sitter_bash', 'language'), family='shell',
        classes=set(), functions={'function_definition'}, calls={'command': ('name',)}, imports={'command': bash_import},
    ),
    'dart': dict(
        exts=('.dart',), grammar=('tree_sitter_dart', 'language'), family='dart',
        classes={'class_definition', 'mixin_declaration', 'enum_declaration', 'extension_declaration',
                 'extension_type_declaration', 'type_alias'}, class_name=first_ident, class_bases=dart_bases,
        functions={'function_signature', 'getter_signature', 'setter_signature', 'constructor_signature',
                   'factory_constructor_signature', 'constant_constructor_signature', 'operator_signature'},
        fn_name=dart_function_name, body=dart_body,
        calls={'selector': dart_callee, 'new_expression': (None,), 'const_object_expression': (None,),
               'cascade_section': dart_cascade, 'initializer_list_entry': dart_delegation, 'redirection': dart_delegation,
               'relational_expression': dart_generic_call, 'constructor_invocation': dart_constructor_call},
        imports={'import_specification': dart_import, 'library_export': dart_import, 'part_directive': dart_import,
                 'part_of_directive': dart_import},
        types=({'type_identifier'}, None),
    ),
    'elixir': dict(
        exts=('.ex', '.exs'), grammar=('tree_sitter_elixir', 'language'), family='elixir',
        classes={'call'}, class_name=ex_module_name, class_bases=ex_bases, namespaces={'call'},
        functions={'call'}, fn_name=ex_function_name, calls={'call': ex_callee}, imports={'call': ex_import},
    ),
    'haskell': dict(
        exts=('.hs',), grammar=('tree_sitter_haskell', 'language'), family='haskell',
        classes={'data_type', 'newtype', 'class', 'type_family', 'data_family'}, owner=hs_owner, owner_bases=hs_bases,
        functions={'function', 'bind'}, calls={'apply': hs_callee}, imports={'import': hs_import}, package={'header'},
    ),
    'zig': dict(
        exts=('.zig',), grammar=('tree_sitter_zig', 'language'), family='zig',
        classes={'struct_declaration', 'enum_declaration', 'union_declaration', 'opaque_declaration'},
        class_name=zig_class_name, functions={'function_declaration'}, calls={'call_expression': ('function',)},
        imports={'builtin_function': zig_import}, tests=zig_test,
    ),
    'ocaml': dict(
        exts=('.ml',), grammar=('tree_sitter_ocaml', 'language_ocaml'), family='ocaml',
        classes={'module_binding', 'type_binding', 'module_type_definition', 'class_binding'}, class_name=ml_class_name,
        class_bases=ml_bases, functions={'let_binding', 'method_definition'}, fn_name=ml_function_name,
        calls={'application_expression': ('function',), 'method_invocation': (None,), 'new_expression': (None,)},
        imports={'module_path': ml_import},
    ),
    'ocaml_interface': dict(
        exts=('.mli',), grammar=('tree_sitter_ocaml', 'language_ocaml_interface'), family='ocaml_interface',
        classes={'module_binding', 'type_binding', 'module_type_definition', 'class_binding'}, class_name=ml_class_name,
        functions={'value_specification'}, fn_name=ml_function_name, calls={}, imports={'module_path': ml_import},
    ),
    'julia': dict(
        exts=('.jl',), grammar=('tree_sitter_julia', 'language'), family='julia',
        classes={'struct_definition', 'abstract_definition', 'primitive_definition'}, class_name=jl_class_name,
        class_bases=jl_bases, functions={'function_definition', 'macro_definition', 'assignment'}, fn_name=jl_function_name,
        calls={'call_expression': (None,)},
        imports={'using_statement': jl_import, 'import_statement': jl_import, 'call_expression': jl_import},
        package={'module_definition'},
    ),
    'objc': dict(
        exts=('.m', '.mm'), grammar=('tree_sitter_objc', 'language'), family='objc',
        classes={'class_interface', 'class_implementation', 'protocol_declaration'}, class_name=first_ident,
        class_bases=objc_bases, functions={'method_definition', 'method_declaration', 'function_definition'},
        fn_name=objc_function_name, calls={'message_expression': objc_callee, 'call_expression': ('function',)},
        imports={'preproc_include': objc_import}, types=({'type_identifier'}, None),
    ),
    'hcl': dict(
        exts=('.tf', '.hcl'), grammar=('tree_sitter_hcl', 'language'), family='hcl',
        classes={'block'}, class_name=hcl_class_name, functions=set(), calls={'expression': hcl_callee},
        imports={'attribute': hcl_import},
    ),
    'groovy': dict(
        exts=('.groovy', '.gradle'), grammar=('tree_sitter_groovy', 'language'), family='jvm',
        classes={'class_declaration', 'interface_declaration', 'enum_declaration', 'record_declaration',
                 'annotation_type_declaration'},
        functions={'method_declaration', 'function_definition'}, bases={'superclass', 'super_interfaces'},
        calls={'method_invocation': ('object', 'name'), 'object_creation_expression': ('type',),
               'juxt_function_call': ('name',)},
        imports={'import_declaration': dotted_imports(r'^import (static )?', ' as ', {'*'}), 'map_item': gradle_apply},
        package={'package_declaration'}, types=({'type_identifier'}, None),
    ),
    'perl': dict(
        exts=('.pl', '.pm'), grammar=('tree_sitter_perl', 'language'), family='perl',
        classes={'package_statement', 'class_statement'}, class_name=pl_package, class_bases=pl_bases,
        functions={'subroutine_declaration_statement', 'method_declaration_statement'}, fn_name=pl_function_name,
        calls={'function_call_expression': pl_callee, 'ambiguous_function_call_expression': pl_callee,
               'method_call_expression': pl_callee},
        imports={'use_statement': pl_import, 'require_expression': pl_import},
        package={'package_statement', 'class_statement'},
    ),
    'fsharp': dict(
        exts=('.fs', '.fsx'), grammar=('tree_sitter_fsharp', 'language'), family='fsharp',
        classes={'anon_type_defn', 'union_type_defn', 'record_type_defn', 'interface_type_defn', 'enum_type_defn',
                 'delegate_type_defn', 'module_defn'}, class_name=fs_class_name, class_bases=fs_bases,
        functions={'method_or_prop_defn', 'function_or_value_defn'}, fn_name=fs_function_name,
        calls={'application_expression': fs_callee}, imports={'import_decl': fs_import},
        package={'namespace', 'named_module'},
    ),
    'solidity': dict(
        exts=('.sol',), grammar=('tree_sitter_solidity', 'language'), family='solidity',
        classes={'contract_declaration', 'interface_declaration', 'library_declaration', 'struct_declaration',
                 'enum_declaration'},
        functions={'function_definition', 'modifier_definition', 'constructor_definition', 'fallback_receive_definition'},
        fn_name=sol_function_name, bases={'inheritance_specifier'},
        calls={'call_expression': ('function',), 'modifier_invocation': (None,)},
        imports={'import_directive': sol_import},
    ),
    'powershell': dict(
        exts=('.ps1', '.psm1'), grammar=('tree_sitter_powershell', 'language'), family='powershell',
        classes={'class_statement', 'enum_statement'}, class_name=first_ident, class_bases=ps_bases,
        functions={'function_statement', 'class_method_definition'}, fn_name=ps_function_name,
        calls={'command': ps_callee, 'invokation_expression': ps_callee}, imports={'command': ps_import},
    ),
}

EXT_LANG = {ext: lang for lang, spec in LANGS.items() for ext in spec['exts']}
EXTS = set(EXT_LANG)
NAME_LANG = {
    'Gemfile': 'ruby', 'Rakefile': 'ruby', 'Vagrantfile': 'ruby', 'Podfile': 'ruby', 'Brewfile': 'ruby',
    'Guardfile': 'ruby', 'Capfile': 'ruby', 'Fastfile': 'ruby', 'Appfile': 'ruby', 'Dangerfile': 'ruby',
    'Berksfile': 'ruby', 'Thorfile': 'ruby', 'Jenkinsfile': 'groovy',
}
SHEBANG_LANG = {
    'ruby': 'ruby', 'bash': 'bash', 'sh': 'bash', 'zsh': 'bash', 'ksh': 'bash', 'dash': 'bash', 'perl': 'perl',
    'php': 'php', 'lua': 'lua', 'luajit': 'lua', 'pwsh': 'powershell', 'groovy': 'groovy', 'elixir': 'elixir',
    'julia': 'julia', 'dart': 'dart', 'kotlin': 'kotlin', 'scala': 'scala', 'swift': 'swift',
}


def lang_of(rel):
    name = rel.rsplit('/', 1)[-1]
    return NAME_LANG.get(name) or EXT_LANG.get(os.path.splitext(name)[1])
_PARSERS = {}


def capsule(pointer):
    if not isinstance(pointer, int):
        return pointer
    new = ctypes.pythonapi.PyCapsule_New
    new.restype = ctypes.py_object
    new.argtypes = (ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p)
    return new(pointer, b'tree_sitter.Language', None)


def parser_for(lang):
    if lang not in _PARSERS:
        module, attr = LANGS[lang]['grammar']
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)
            _PARSERS[lang] = Parser(Language(capsule(getattr(importlib.import_module(module), attr)())))
    return _PARSERS[lang]


def package_name(node, src):
    named = node.child_by_field_name('name')
    if named is None:
        named = next((c for c in node.named_children if c.type not in ('comment',)), None)
    if named is None:
        return None
    return re.sub(r'\s+', '', text(named, src)).replace('\\', '.') or None


class Unit:
    def __init__(self, rel, lang, src, mid):
        self.rel = rel
        self.lang = lang
        self.family = LANGS[lang]['family']
        self.src = src
        self.mid = mid
        self.top = {}
        self.top_classes = []
        self.calls = []
        self.bases = []
        self.imports = []
        self.packages = []
        self.aliases = {}
        self.opened = []
        self.explicit = set()
        self.scope = set()
        self.wide = set()
        self.types = {}
        self.refs = {}
        self.foreign = set()
        self.fnodes = {}
        self.decls = defaultdict(list)
        self.values = set()
        self.selectors = []
        self.gtypes = {}
        self.gvars = []
        self.idents = []
        self.build = None
        self.enabled = True
        self.class_ctx = {}
        self.class_keys = {}


class Family:
    def __init__(self):
        self.units = {}
        self.top_by_name = defaultdict(list)
        self.classes_by_name = defaultdict(list)
        self.methods = defaultdict(list)
        self.methods_by_name = defaultdict(list)
        self.by_package = defaultdict(list)
        self.fqn = {}
        self.method_aliases = []
        self.ruby_roots = set()
        self.dynamic = set()


def read_unit(g, family, rel, lang, src, digest, skip_tests=False):
    spec = LANGS[lang]
    raw = src
    if b'\0' in src:
        src = src.replace(b'\0', b' ')  # tree-sitter corta el análisis en un byte NUL (aunque esté en un comentario)
    if lang == 'csharp':
        src = csharp_fixups(blank_branches(src, dotnet_branch))
    elif lang == 'kotlin':
        src = kotlin_fixups(src)
    tree = parser_for(lang).parse(src)
    mid = g.node(f'm:{rel}', kind='module', name=rel.rsplit('/', 1)[-1], file=rel, line=1, lang=lang, hash=digest(raw))
    g.nodes[mid].setdefault('end', line_count(src))
    found = module_doc(src, lang)
    if found:
        g.nodes[mid].setdefault('doc', found)
    u = Unit(rel, lang, src, mid)
    if lang == 'ruby':
        u.tree = tree
    classes, functions = spec['classes'], spec['functions']
    calls, imports, packages = spec['calls'], spec.get('imports', {}), spec.get('package', set())
    bases, namespaces = spec.get('bases', set()), spec.get('namespaces', set())
    owner_of, fn_name, class_name = spec.get('owner'), spec.get('fn_name'), spec.get('class_name')
    class_bases, body_of = spec.get('class_bases'), spec.get('body')
    type_idents, type_parents = spec.get('types', (set(), None))
    refs, is_test = spec.get('refs', set()), spec.get('tests') if skip_tests else None
    collect_types, collect = spec.get('collect', (set(), None))
    anonymous = spec.get('anonymous', set())
    spaces, detached = set(), {}
    shadowed = ruby_instance_methods(tree.root_node, src) if lang == 'ruby' else set()
    if lang == 'go':
        u.build, u.enabled = go_enabled(rel, src)

    def declare_method(owner, name, node, cid, line=None):
        key = f'{owner}.self.{name}' if lang == 'ruby' and (owner, name) in shadowed and ruby_singleton(node) else f'{owner}.{name}'
        fid = g.node(f'f:{rel}:{key}', kind='method', name=key, file=rel,
                     **placed(node, line), lang=lang, hash=digest(src[node.start_byte:node.end_byte]),
                     **describe(node, src, lang, 'method', name))
        g.edge(cid or mid, fid, 'contains')
        add(family.methods[(owner, name)], fid)
        add(family.methods_by_name[name], fid)
        return fid

    stack, later = [(tree.root_node, None, None, mid, False)], [] if lang == 'rust' else None
    while stack or later:
        if not stack:
            stack, later = later[::-1], None
        n, ctx, ctx_id, owner_id, in_fn = stack.pop()
        if later is not None and n.type in RUST_NESTED_ITEMS and rust_cfg_off(n, src):
            later.append((n, ctx, ctx_id, owner_id, in_fn))
            continue
        if n.id in detached:
            ctx, ctx_id, owner_id, in_fn = *detached.pop(n.id), True
        t = n.type
        if is_test and is_test(n, src):
            continue
        if in_fn and nested_item(lang, n):
            ctx, ctx_id, in_fn = None, None, False
        if t in type_idents:
            found = type_ref(n, src, type_parents)
            if found:
                u.types.setdefault(found, None)
        if t in refs:
            operand, field = n.child_by_field_name('operand'), n.child_by_field_name('field')
            if operand is not None and field is not None and operand.type == 'identifier':
                u.refs.setdefault((text(operand, src), text(field, src)), None)
            if lang == 'go' and in_fn and not (n.parent is not None and n.parent.type == 'call_expression' and
                                               n.parent.child_by_field_name('function') == n):
                u.selectors.append((owner_id, n))
        if t in calls:
            u.calls.append((owner_id, ctx, n))
        if lang == 'go' and t == 'identifier' and go_value_ref(n):
            u.idents.append((owner_id, n))
        if t in collect_types:
            collect(u, n, owner_id, in_fn)
        if t in imports:
            u.imports += imports[t](n, src)
        if t in packages:
            name = package_name(n, src)
            if name:
                u.packages.append(name)
            if lang in ('go', 'haskell') and 'doc' not in g.nodes[mid]:
                found = doc_paragraph(comment_lines(src, n.start_byte, lang), lang)
                if found:
                    g.nodes[mid]['doc'] = found
        if not in_fn and lang == 'ruby' and t in ('call', 'alias') and ctx:
            for name, line in ruby_accessor_sites(n, src):
                declare_method(ctx, name, n, ctx_id, line)
            pair = ruby_alias(n, src)
            if pair:
                family.method_aliases.append((ctx, *pair))
            mixins = ruby_mixins(n, src)
            if mixins:
                u.bases.append((ctx, ctx_id, mixins))
        if not in_fn and t in anonymous:
            for c in reversed(n.named_children):
                stack.append((c, ctx, ctx_id, owner_id, True))
            continue
        if not in_fn:
            owner = owner_of(n, src) if owner_of else None
            if owner:
                found = spec.get('owner_bases')
                names = found(n, src) if found else [x for c in n.named_children if c.type in bases for x in base_names(c, src)]
                if names:
                    u.bases.append((owner, None, names))
                for c in reversed(n.named_children):
                    stack.append((c, owner, None, owner_id, False))
                continue
            struct = ruby_struct_class(n, src) if lang == 'ruby' and t == 'assignment' else None
            if struct:
                name, accessors, body = struct
                key = name if u.class_ctx.setdefault(name, ctx) == ctx else f'{ctx}.{name}'
                u.class_keys[n.start_byte] = key
                cid = g.node(f'c:{rel}:{key}', kind='class', name=name, file=rel, **placed(n), lang=lang,
                             hash=digest(src[n.start_byte:n.end_byte]), **describe(n, src, lang, 'class', name))
                g.edge(ctx_id or mid, cid, 'contains')
                add(family.classes_by_name[name], cid)
                if ctx is None:
                    family.ruby_roots.add(name)
                if ctx is None or ctx_id in spaces:
                    u.top.setdefault(name, cid)
                    add(u.top_classes, name)
                for accessor in accessors:
                    declare_method(key, accessor, n, cid)
                # nombres de datos genéricos (`query`, `host`): no son el único candidato para un receptor sin tipo
                family.dynamic.update(accessors)
                for c in reversed(body.named_children if body is not None else ()):
                    stack.append((c, key, cid, cid, False))
                continue
            if t in classes and not (lang == 'rust' and rust_associated(n)):
                name = class_name(n, src) if class_name else last_name(n.child_by_field_name('name'), src)
                if name:
                    key = name
                    if lang == 'ruby':
                        key = name if u.class_ctx.setdefault(name, ctx) == ctx else f'{ctx}.{name}'
                        u.class_keys[n.start_byte] = key
                        family.dynamic.update(ruby_struct_members(n, src))
                    cid = g.node(f'c:{rel}:{key}', kind='class', name=name, file=rel, **placed(n), lang=lang,
                                 hash=digest(src[n.start_byte:n.end_byte]), **describe(n, src, lang, 'class', name))
                    g.edge(ctx_id or mid, cid, 'contains')
                    add(family.classes_by_name[name], cid)
                    if ctx is None:
                        family.ruby_roots.add(name)
                    if t in namespaces:
                        spaces.add(cid)
                    if ctx is None or ctx_id in spaces:
                        u.top.setdefault(name, cid)
                        add(u.top_classes, name)
                    if lang == 'php':
                        body = n.child_by_field_name('body')
                        real = {text(m.child_by_field_name('name'), src) for m in (body.named_children if body is not None else ())
                                if m.type == 'method_declaration' and m.child_by_field_name('name') is not None}
                        for magic, line, _ in php_magic_methods(n, src):
                            if magic not in real:
                                fid = g.node(f'f:{rel}:{name}.{magic}', kind='method', name=f'{name}.{magic}', file=rel, line=line,
                                             end=line, lang=lang, hash=digest(magic.encode()), vis='public')
                                g.edge(cid, fid, 'contains')
                                add(family.methods[(name, magic)], fid)
                                add(family.methods_by_name[magic], fid)
                    if class_bases:
                        names = class_bases(n, src)
                    else:
                        names = [x for c in n.named_children if c.type in bases for x in base_names(c, src)]
                    if names:
                        u.bases.append((name, cid, names))
                    for c in reversed(n.named_children):
                        stack.append((c, key, cid, cid, False))
                    continue
            if t in functions:
                owner, name = fn_name(n, src) if fn_name else (None, last_name(n.child_by_field_name('name'), src))
                owner = owner or ctx
                if name:
                    if owner:
                        fid = declare_method(owner, name, n, ctx_id if owner == ctx else None)
                    else:
                        fid = g.node(f'f:{rel}:{name}', kind='function', name=name, file=rel, **placed(n),
                                     lang=lang, hash=digest(src[n.start_byte:n.end_byte]),
                                     **describe(n, src, lang, 'function', name))
                        g.edge(mid, fid, 'contains')
                        u.top.setdefault(name, fid)
                        add(family.top_by_name[name], fid)
                    u.fnodes.setdefault(fid, n)
                    bodies = list(body_of(n) or ()) if body_of else []
                    for body in bodies:
                        detached[body.id] = (owner, ctx_id, fid)
                    last = max(bodies, key=lambda b: b.end_byte) if bodies else None
                    if last is not None and last.end_byte > n.end_byte:
                        # Dart: el cuerpo es hermano de la firma; el rango y el hash del nodo lo incluyen
                        g.nodes[fid]['end'] = max(g.nodes[fid].get('end') or 0, last.end_point[0] + 1)
                        g.nodes[fid]['hash'] = digest(src[n.start_byte:last.end_byte])
                    for c in reversed(n.named_children):
                        stack.append((c, owner, ctx_id, fid, True))
                    continue
        for c in reversed(n.named_children):
            stack.append((c, ctx, ctx_id, owner_id, in_fn))
    for name in u.top_classes:
        add(family.top_by_name[name], u.top[name])
    return u


class Linker:
    def __init__(self, root, g, family, files, paths=None):
        self.root = root
        self.g = g
        self.f = family
        self.paths = sorted(set(paths or files))
        self.files = set(self.paths)
        self.by_dir = defaultdict(list)
        self.by_name = defaultdict(list)
        self.by_stem = defaultdict(list)
        for rel in self.paths:
            base = rel.rsplit('/', 1)[-1]
            self.by_dir[os.path.dirname(rel)].append(rel)
            self.by_name[base.lower()].append(rel)
            self.by_stem[os.path.splitext(base)[0].lower()].append(rel)
        self.gomods = {d: m.strip('"`') for d, m in self.find_markers('go.mod', r'^module\s+(\S+)').items()}
        self.crates = self.find_markers('Cargo.toml', r'^name\s*=\s*"([^"]+)"')
        self.pubs = None
        self.derived = set()
        self.packages_used = []
        self.resolved = set()
        self.parents = defaultdict(list)
        self.tails = defaultdict(set)
        for pkg, rels in family.by_package.items():
            self.tails[re.split(r'\.|::', pkg)[-1]].update(rels)
        self.roots = {}
        self.reps = {}
        self.prefixes = None
        self.dirnames = None
        self.gotypes = None
        self.go_package_names = {}
        self.govars = None
        self.envs = {}
        self.memo = {}
        self.typer = None

    def find_markers(self, filename, pattern):
        found = {}
        seen = set()
        for d in sorted({os.path.dirname(r) for r in self.paths}):
            while True:
                if d not in seen:
                    seen.add(d)
                    path = self.root / d / filename
                    if path.is_file():
                        try:
                            match = re.search(pattern, path.read_text(encoding='utf-8', errors='replace'), re.M)
                        except OSError:
                            match = None
                        found[d] = match.group(1) if match else ''
                if not d:
                    break
                d = os.path.dirname(d)
        return dict(sorted(found.items()))

    def nearest(self, markers, rel):
        d = os.path.dirname(rel)
        while True:
            if d in markers:
                return d
            if not d:
                return None
            d = os.path.dirname(d)

    def has_marker(self, d):
        try:
            names = os.listdir(self.root / d)
        except OSError:
            return False
        return any(n in BUILD_MARKERS or n.endswith(BUILD_SUFFIXES) for n in names)

    def build_root(self, rel):
        cur, chain = os.path.dirname(rel), []
        while cur not in self.roots:
            chain.append(cur)
            if self.has_marker(cur):
                self.roots[cur] = cur
                break
            if not cur:
                self.roots[cur] = None
                break
            cur = os.path.dirname(cur)
        found = self.roots[cur]
        for d in chain:
            self.roots[d] = found
        return found

    def reachable(self, u, rel):
        return rel in u.explicit or rel in u.scope or rel in u.wide or self.build_root(rel) == self.build_root(u.rel)

    def suffix(self, path, exts):
        path = re.sub(r'^(\.{1,2}/)+', '', path.strip('/')).lower()
        base = path.rsplit('/', 1)[-1]
        if os.path.splitext(path)[1] in exts:
            pool, key = self.by_name.get(base, []), lambda r: r.lower()
        else:
            pool, key = self.by_stem.get(base, []), lambda r: os.path.splitext(r)[0].lower()
        return [r for r in pool if os.path.splitext(r)[1] in exts and (key(r) == path or key(r).endswith('/' + path))]

    def norm(self, rel, target):
        return os.path.normpath(os.path.join(os.path.dirname(rel), target)).replace(os.sep, '/')

    def rust_module(self, rel):
        crate = self.nearest(self.crates, rel)
        base = (crate + '/src' if crate else 'src') if crate is not None else os.path.dirname(rel)
        base = base.lstrip('/')
        if base and not rel.startswith(base + '/'):
            base = self.rust_root(rel) or base
        inner = rel[len(base) + 1:] if base and rel.startswith(base + '/') else rel
        segs = inner[:-3].split('/')
        if segs[-1] in ('mod', 'lib', 'main'):
            segs = segs[:-1]
        return base, segs

    def rust_root(self, rel):
        d = os.path.dirname(rel)
        while d:
            if f'{d}/lib.rs' in self.files or f'{d}/main.rs' in self.files:
                return d
            d = os.path.dirname(d)
        return None

    def rust_file(self, base, segs):
        stem = '/'.join(([base] if base else []) + segs)
        extra = (stem + '/lib.rs', stem + '/main.rs') if base and not segs else ()
        for cand in (stem + '.rs', stem + '/mod.rs') + extra:
            if cand in self.files:
                return cand
        return None

    def rust_resolve(self, u, segs):
        base, here = self.rust_module(u.rel)
        segs = list(segs)
        if segs[0] == 'crate':
            start, segs = [], segs[1:]
        elif segs[0] == 'self':
            start, segs = here, segs[1:]
        elif segs[0] == 'super':
            start = here
            while segs and segs[0] == 'super':
                start, segs = start[:-1], segs[1:]
        else:
            crate_dir = next((d for d, name in self.crates.items() if name.replace('-', '_') == segs[0]), None)
            if crate_dir is not None:
                base, start, segs = (crate_dir + '/src').lstrip('/'), [], segs[1:]
            else:
                start = here
        for k in range(len(segs), -1, -1):
            found = self.rust_file(base, start + segs[:k])
            if found and found != u.rel and (k or start or segs):
                return found, segs[k:]
        return None, segs

    def rust_follow(self, u, segs):
        """Como `rust_resolve`, pero atraviesa reexportaciones (`pub use x as y;`, `pub use m::*;`) del archivo hallado."""
        found, rest = self.rust_resolve(u, segs)
        for _ in range(4):
            unit = self.f.units.get(found) if found else None
            if unit is None or not rest or rest[0] in unit.top or re.search(
                    rb'\b(fn|struct|enum|trait|type|union|const|static|mod)\s+' + re.escape(rest[0].encode()) + rb'\b', unit.src):
                break
            hop = next((v + rest[1:] for kind, v, alias in unit.imports
                        if kind in ('rust', 'rustcrate') and v and (alias or v[-1]) == rest[0]), None)
            hops = [hop] if hop else [v + rest for kind, v, _ in unit.imports if kind == 'rustglob' and v]
            nxt = next(((f, r) for f, r in (self.rust_resolve(unit, h) for h in hops) if f and f != found), None)
            if nxt is None:
                break
            found, rest = nxt
        return found, rest

    def go_module_dir(self, value):
        best = None
        for d, module in self.gomods.items():
            if module and (value == module or value.startswith(module + '/')) and (best is None or len(module) > len(best[1])):
                best = (d, module)
        return posixpath.join(best[0], value[len(best[1]):].strip('/')).strip('/') if best else None

    def representative(self, rels):
        key = tuple(rels)
        if key not in self.reps:
            pool = sorted(rels)
            plain = [r for r in pool if not r.endswith('_test.go')] or pool
            d = os.path.dirname(plain[0])
            names = [p for r in plain if r in self.f.units for p in self.f.units[r].packages] + [os.path.basename(d), 'doc']
            hit = next((c for c in (posixpath.join(d, n + '.go') for n in names) if c in plain), None)
            if hit is None:
                hit = min(plain, key=lambda r: (-len(self.f.units[r].top) if r in self.f.units else 0, r))
            self.reps[key] = hit
        return self.reps[key]

    def prune_packages(self):
        if not self.packages_used:
            return
        used = defaultdict(set)
        for (a, b, kind) in self.g.edges:
            if kind not in ('import', 'contains', 'cochange'):
                used[self.g.nodes[a].get('file')].add(self.g.nodes[b].get('file'))
        for rel, rep, targets in self.packages_used:
            if rep not in used[rel] and (rel, rep) not in self.resolved and any(r in used[rel] or (rel, r) in self.resolved for r in targets):
                self.g.edges.pop((f'm:{rel}', f'm:{rep}', 'import'), None)

    def add_explicit(self, u, rel):
        if rel and rel != u.rel:
            u.explicit.add(rel)
            self.g.edge(u.mid, f'm:{rel}', 'import')

    def touch(self, u, rel):
        if rel and rel != u.rel and rel not in u.explicit and (u.rel, rel) not in self.derived:
            self.derived.add((u.rel, rel))
            self.g.edge(u.mid, f'm:{rel}', 'import')

    def defined(self, name):
        return name in self.f.classes_by_name or name in self.f.top_by_name

    def known(self, word):
        return self.defined(word) or word in self.f.by_package or word in self.tails

    def foreign(self, u, words):
        roots = STD_ROOTS.get(u.family, ())
        return any(w in u.foreign or (w in roots and w not in u.aliases and not self.known(w)) for w in words if w)

    def internal(self, u, value):
        if self.prefixes is None:
            self.prefixes = set()
            for name in list(self.f.by_package) + list(self.f.fqn):
                parts = re.split(r'\.|::', name)
                self.prefixes.update('.'.join(parts[:i]) for i in range(1, len(parts) + 1))
        owner = value.rsplit('.', 1)[0]
        return (value in self.prefixes or owner in self.f.by_package or owner in self.f.fqn
                or (u.family in MODULE_NAMES and owner in self.prefixes))

    def external(self, u, value):
        roots = EXTERN_STD.get(u.lang) or EXTERN_STD.get(u.family, ())
        if value and value not in roots and re.split(r'\.|::|/', value)[0] not in roots:
            self.g.external(u.mid, value, u.lang)

    def local_dir(self, value):
        if self.dirnames is None:
            self.dirnames = {os.path.basename(d).lower() for d in self.by_dir}
        return value.lower() in self.dirnames

    def global_ok(self, u, name):
        return u.family not in NO_GLOBAL and name not in u.foreign and name not in BUILTINS.get(u.family, ())

    def link_imports(self, u):
        exts = LANGS[u.lang]['exts']
        group = PATH_GROUPS.get(u.family, (u.family,))
        family_exts = {e for spec in LANGS.values() if spec['family'] in group for e in spec['exts']}
        for imp in u.imports:
            kind, value, alias = imp
            if kind == 'go':
                mod_dir = self.go_module_dir(value)
                if mod_dir is None:
                    if alias not in ('_', '.'):
                        u.foreign.add(alias or go_package(value))
                    self.external(u, value)
                    continue
                targets = [r for r in self.by_dir.get(mod_dir, []) if r.endswith('.go') and r != u.rel]
                if targets:
                    declared = [p for r in targets if r in self.f.units for p in self.f.units[r].packages]
                    u.aliases[alias or (declared[0] if declared else value.rsplit('/', 1)[-1])] = ('files', targets)
                    rep = self.representative(targets)
                    if rep not in u.explicit and (u.rel, rep) not in self.derived:
                        self.packages_used.append((u.rel, rep, targets))
                    self.touch(u, rep)
            elif kind == 'rustmod':
                base, here = self.rust_module(u.rel)
                found = self.rust_file(base, here + [value])
                if found:
                    self.add_explicit(u, found)
                    u.aliases[value] = ('files', [found])
            elif kind in ('rust', 'rustglob'):
                if not value:
                    continue
                found, rest = self.rust_follow(u, value)
                if not found:
                    if kind == 'rust' and alias != '_' and value[0] not in ('crate', 'self', 'super'):
                        u.foreign.add(alias or value[-1])
                    if value[0] not in ('crate', 'self', 'super') and value[0] not in u.top and not self.defined(value[0]):
                        self.external(u, '::'.join(value))
                    continue
                self.add_explicit(u, found)
                if kind == 'rustglob':
                    u.wide.add(found)
                elif rest:
                    u.aliases[alias or value[-1]] = ('item', found, rest[0])
                else:
                    u.aliases[alias or value[-1]] = ('files', [found])
            elif kind == 'fqn':
                target = self.f.fqn.get(value)
                if target:
                    self.add_explicit(u, self.g.nodes[target]['file'])
                    u.aliases[alias or value.rsplit('.', 1)[-1]] = ('def', target)
                elif '.' in value and self.fqn_owner(value):
                    self.add_explicit(u, self.g.nodes[self.fqn_owner(value)]['file'])
                else:
                    hits = self.suffix(value.replace('.', '/'), exts) if u.lang == 'php' else []
                    if u.lang == 'php' and '.' not in value:
                        hits = [h for h in hits if h in self.f.units and not self.f.units[h].packages]
                        if not hits:
                            u.foreign.add(alias or value)
                    if len(hits) == 1:
                        self.add_explicit(u, hits[0])
                    elif value not in self.f.by_package and (not self.defined(alias or value.rsplit('.', 1)[-1]) or
                                                             u.lang == 'php' and not hits and not self.internal(u, value)):
                        # `use GuzzleHttp\Psr7\Request;` tapa la clase `Request` del proyecto en ese archivo
                        u.foreign.add(alias or value.rsplit('.', 1)[-1])
                    if not hits and not self.internal(u, value):
                        self.external(u, value.replace('.', '\\') if u.lang == 'php' else value)
            elif kind == 'open':
                target = self.f.fqn.get(value)
                if target and self.g.nodes[target]['kind'] == 'class':
                    self.add_explicit(u, self.g.nodes[target]['file'])
                    add(u.opened, target)
                elif not target and not self.internal(u, value):
                    self.external(u, value)
            elif kind == 'pkg':
                u.wide.update(r for r in self.f.by_package.get(value, ()) if r != u.rel)
                if not self.internal(u, value):
                    self.external(u, value)
            elif kind == 'relpath':
                cands = [self.norm(u.rel, value.lstrip('/')) if value.startswith('/') else self.norm(u.rel, value)]
                cands.append(cands[0] + '.rb')
                hit = next((c for c in cands if c in self.files), None)
                if hit is None and cands[0] in self.by_dir:
                    hits = sorted(self.by_dir[cands[0]])
                else:
                    if hit is None:
                        found = self.suffix(value, family_exts)
                        hit = found[0] if len(found) == 1 else None
                    hits = [hit] if hit else []
                for hit in hits:
                    self.add_explicit(u, hit)
                if hits and alias:
                    u.aliases[alias] = ('files', hits)
            elif kind == 'angle':
                if os.path.splitext(value)[1].lower() not in family_exts:
                    continue
                if '/' not in value and value.lower() in C_STD_HEADERS:
                    continue
                hits = self.suffix(value, family_exts)
                if len(hits) == 1:
                    self.add_explicit(u, hits[0])
                elif not hits and not value.startswith(C_SYSTEM):
                    self.external(u, value)
            elif kind == 'suffix':
                hits = self.suffix(value, family_exts)
                if len(hits) == 1:
                    self.add_explicit(u, hits[0])
                    if alias:
                        u.aliases[alias] = ('files', hits)
                elif not hits and u.lang in ('ruby', 'powershell'):
                    self.external(u, value)
            elif kind == 'extern':
                tail = value.split('/', 1)[-1]
                if not (self.suffix(value, family_exts) or self.suffix(tail, family_exts) or self.local_dir(value.split('.')[0])):
                    self.external(u, value)
            elif kind == 'module':
                hits = sorted(r for r in self.f.by_package.get(value, ()) if r != u.rel)
                if not hits:
                    found = self.suffix(re.sub(r'::|\.', '/', value), family_exts)
                    hits = found if len(found) == 1 else []
                for hit in hits:
                    self.add_explicit(u, hit)
                if hits and alias:
                    u.aliases[alias] = ('files', hits)
                if not hits and not self.internal(u, value):
                    self.external(u, value)
            elif kind == 'stem':
                if value in u.top:
                    continue
                hits = [r for r in self.by_stem.get(value.lower(), []) if os.path.splitext(r)[1] in exts and r != u.rel]
                hits = [r for r in hits if os.path.dirname(r) == os.path.dirname(u.rel)] or hits
                if not hits and alias is None and not self.defined(value):
                    self.external(u, value)
                if len(hits) != 1:
                    continue
                if alias is None:
                    self.add_explicit(u, hits[0])
                    continue
                u.aliases.setdefault(alias, ('files', hits))
                self.touch(u, hits[0])
            elif kind == 'dartpkg':
                if self.pubs is None:
                    self.pubs = self.find_markers('pubspec.yaml', r'^name:\s*([\w-]+)')
                pkg, path = value
                roots = sorted(d for d, name in self.pubs.items() if name == pkg)
                hit = next((c for c in (posixpath.join(d, 'lib', path).lstrip('/') for d in roots) if c in self.files), None)
                self.add_explicit(u, hit)
                if hit and alias:
                    u.aliases[alias] = ('files', [hit])
                elif alias and not hit:
                    u.foreign.add(alias)
                if not roots:
                    self.external(u, f'package:{pkg}/{path}')
            elif kind == 'lua':
                path = value.replace('.', '/')
                hits = self.suffix(path, family_exts) or self.suffix(path + '/init', family_exts)
                if len(hits) == 1:
                    self.add_explicit(u, hits[0])
                    if alias:
                        u.aliases[alias] = ('files', hits)
                elif not hits:
                    self.external(u, value)

    def dart_target(self, u, kind, value):
        if kind == 'relpath':
            rel = self.norm(u.rel, value)
            return rel if rel in self.files else None
        if self.pubs is None:
            self.pubs = self.find_markers('pubspec.yaml', r'^name:\s*([\w-]+)')
        pkg, path = value
        roots = sorted(d for d, name in self.pubs.items() if name == pkg)
        return next((c for c in (posixpath.join(d, 'lib', path).lstrip('/') for d in roots) if c in self.files), None)

    def dart_scopes(self):
        """Ámbito de Dart: un archivo ve lo que reexportan (`export`, en cadena) las bibliotecas que importa; una parte
        (`part of 'x.dart'`) comparte los imports y prefijos de su biblioteca; y los nombres de `show` son referencias a
        sus definiciones (dependencia hacia el archivo que las define, aunque llegue a través de un barril)."""
        units = {u.rel: u for u in self.f.units.values() if u.lang == 'dart'}
        dirs = {}
        for rel, u in units.items():
            # cada directiva deja (relpath|dartpkg, valor, prefijo) seguido de su ('dartdir', (clase, …), nombres de show)
            dirs[rel] = [(d[1][0], self.dart_target(u, d[1][1], d[1][2]), d[2], prev[2])
                         for prev, d in zip(u.imports, u.imports[1:]) if d[0] == 'dartdir']
        memo = {}

        def closure(rel):
            """[(archivo, nombres visibles o None)] de lo que exporta `rel`, en cadena, con los filtros `show`."""
            if rel not in memo:
                memo[rel], seen, queue = [], set(), [(rel, None)]
                while queue:
                    cur, names = queue.pop(0)
                    if (cur, names) in seen or cur not in units or len(seen) > 400:
                        continue
                    seen.add((cur, names))
                    memo[rel].append((cur, names))
                    for kind, t, shown, _ in dirs[cur]:
                        if kind == 'library_export' and t:
                            limit = frozenset(shown) if shown else None
                            queue.append((t, limit if names is None else names & limit if limit is not None else names))
            return memo[rel]

        for rel, u in units.items():
            lib = next((t for kind, t, _, _ in dirs[rel] if kind == 'part_of_directive' and t in units), None)
            imports = [d for d in dirs[rel] + (dirs[lib] if lib else []) if d[0] == 'import_specification' and d[1]]
            for kind, target, shown, alias in imports:
                reach = closure(target)
                if alias:
                    if u.aliases.get(alias) in (None, ('files', [target])):
                        u.aliases[alias] = ('files', [f for f, names in reach if names is None])
                    continue
                for f, names in reach:
                    if f == rel or f in u.explicit:
                        continue
                    if names is None:
                        # al ámbito, no a `explicit`: no hay arista de import hasta que se use un nombre suyo
                        u.scope.add(f)
                    else:
                        for name in names:
                            if name in self.f.units[f].top:
                                u.aliases.setdefault(name, ('def', self.f.units[f].top[name]))
            for kind, target, shown, alias in dirs[rel]:
                for name in shown if target and kind in ('import_specification', 'library_export') else ():
                    self.add_explicit(u, next((f for f, names in closure(target) if (names is None or name in names) and
                                               name in self.f.units[f].top), None))
            if lib:
                u.scope.update(f for f in [lib] + [t for kind, t, _, _ in dirs[lib] if kind == 'part_directive' and t]
                               if f != rel and f not in u.explicit)
                for alias, spec in units[lib].aliases.items():
                    u.aliases.setdefault(alias, spec)

    def fqn_owner(self, value):
        """Declaración del proyecto que contiene a `value` (import de un miembro anidado: `a.B.Companion.C`)."""
        parts = value.split('.')
        for i in range(len(parts) - 1, 0, -1):
            found = self.f.fqn.get('.'.join(parts[:i]))
            if found:
                return found
        return None

    def unit_of(self, nid):
        return self.f.units.get(self.g.nodes[nid]['file'])

    def pick(self, cands, rel):
        cands = list(dict.fromkeys(cands))
        if len(cands) > 1:
            cands = [c for c in cands if getattr(self.unit_of(c), 'enabled', True)] or cands
        if len(cands) == 1:
            return cands[0]
        if not cands:
            return None
        same = [c for c in cands if self.g.nodes[c]['file'] == rel]
        if len(same) == 1:
            return same[0]
        partial = self.partial_parts(cands)
        if partial:
            return partial
        near = [c for c in cands if os.path.dirname(self.g.nodes[c]['file']) == os.path.dirname(rel)]
        if len(near) == 1:
            return near[0]
        return self.twin(near or cands)

    def partial_parts(self, cands):
        """Las partes de una misma clase parcial de C# (`partial class X` en varios archivos del mismo espacio de nombres)
        son un solo tipo: una referencia a él depende de una de ellas (la del primer archivo)."""
        units = [self.unit_of(c) for c in cands]
        if any(x is None or x.lang != 'csharp' for x in units) or len({str(self.g.nodes[c]['name']) for c in cands}) != 1 or \
                len({tuple(x.packages[:1]) for x in units}) != 1 or \
                not all(re.search(r'\bpartial\b', str(self.g.nodes[c].get('sig', ''))) for c in cands):
            return None
        return min(cands, key=lambda c: (self.g.nodes[c]['file'], c))

    def twin(self, cands):
        units = [self.unit_of(c) for c in cands]
        if any(x is None or x.build is None for x in units) or len({os.path.dirname(x.rel) for x in units}) != 1:
            return None
        return min(cands, key=lambda c: (bool(self.unit_of(c).build), self.g.nodes[c]['file'], c))

    def in_files(self, name, rels):
        return sorted(self.f.units[r].top[name] for r in rels if r in self.f.units and name in self.f.units[r].top)

    def classes_in(self, name, rels):
        return [x for x in self.in_files(name, rels) if self.g.nodes[x]['kind'] == 'class']

    def inherited(self, ctx, name, rel):
        start = self.pick(self.f.classes_by_name.get(ctx, []), rel)
        queue, seen = [start] if start else [], set()
        while queue:
            cid = queue.pop(0)
            if cid in seen:
                continue
            seen.add(cid)
            for base in self.parents.get(cid, ()):
                found = self.class_method(base, name, rel)
                if found:
                    return found
                queue.append(base)
        return None

    def unqualified(self, u, ctx, name):
        if ctx and (ctx, name) in self.f.methods:
            found = self.pick(self.f.methods[(ctx, name)], u.rel)
            if found:
                return found, 'local'
        found = self.inherited(ctx, name, u.rel) if ctx else None
        if found:
            return found, 'local'
        if name in u.top:
            return u.top[name], 'local'
        alias = u.aliases.get(name)
        if alias and alias[0] == 'def':
            return alias[1], 'alias'
        if alias and alias[0] == 'item':
            unit = self.f.units.get(alias[1])
            if unit and alias[2] in unit.top:
                return unit.top[alias[2]], 'alias'
        for scope, via in ((u.explicit, 'explicit'), (u.scope, 'scope'), (u.wide, 'wide')):
            found = self.pick(self.in_files(name, scope), u.rel)
            if found:
                return found, via
        for cid in u.opened:
            found = self.class_method(cid, name, u.rel)
            if found:
                return found, 'explicit'
        if self.global_ok(u, name) and len(name) > 2 and len(self.f.top_by_name.get(name, ())) == 1:
            return self.f.top_by_name[name][0], 'global'
        return None, None

    def class_method(self, cid, name, rel):
        owner = self.g.nodes[cid]['name']
        return self.pick(self.f.methods.get((owner, name), []), self.g.nodes[cid]['file']) or self.pick(
            self.f.methods.get((owner, name), []), rel)

    def qualified(self, u, ctx, qual, name, scoped, root=None):
        if qual in SELF_WORDS:
            if ctx and (ctx, name) in self.f.methods and qual not in ('super', 'parent'):
                return self.pick(self.f.methods[(ctx, name)], u.rel), 'local'
            found = self.inherited(ctx, name, u.rel) if ctx else None
            return (found, 'local') if found else (None, None)
        alias = u.aliases.get(qual)
        if alias and alias[0] == 'files':
            found = self.pick(self.in_files(name, alias[1]), u.rel)
            if found:
                return found, 'wide'
        if self.foreign(u, (qual, root)):
            return None, None
        if u.family not in NO_GLOBAL and (qual[:1].isupper() or '.' in qual or '::' in qual):
            found = self.pick(self.in_files(name, sorted(self.f.by_package.get(qual) or self.tails.get(qual, ()))), u.rel)
            if found:
                return found, 'wide'
        target, via = self.unqualified(u, None, qual)
        typed = bool(target) and self.g.nodes[target]['kind'] == 'class'
        if typed:
            found = self.class_method(target, name, u.rel)
            if found:
                return found, via
            if name == 'new' and u.family == 'ruby':
                return target, via
        if qual[:1].isupper() and (qual, name) in self.f.methods:
            found = self.pick(self.f.methods[(qual, name)], u.rel)
            if found:
                return found, 'global'
        typed = typed or qual in self.f.classes_by_name
        if not typed and qual == (root or qual) and qual[:1].isupper():
            return None, None
        if u.family == 'ruby' and name == 'new' and qual in self.f.classes_by_name:
            found = self.pick(self.f.classes_by_name[qual], u.rel)
            if found:
                return found, 'wide'
        if name in BUILTINS.get(u.family, ()):
            return None, None
        # Ruby: un receptor sin tipo no se enlaza por nombre único (ronda 7: en los 7 repos de Ruby medidos, 12 aciertos
        # frente a 47 errores, `File.mtime(path)` → `StaticFile#mtime`, `.order(…)` de ActiveRecord → `Search#order`)
        if u.family not in STRICT and u.family != 'ruby' and len(name) > 3 and len(self.f.methods_by_name.get(name, ())) == 1 and \
                name not in self.f.dynamic:
            found = self.f.methods_by_name[name][0]
            if typed or self.reachable(u, self.g.nodes[found]['file']):
                return found, 'global'
        if scoped and u.family not in NO_GLOBAL and len(self.f.top_by_name.get(name, ())) == 1:
            return self.f.top_by_name[name][0], 'global'
        return None, None

    def resolve_call(self, u, owner_id, ctx, node):
        if u.family == 'go' and node.type == 'call_expression':
            kind, value, via = self.go_callee(u, self.go_env(u, owner_id), node.child_by_field_name('function'), 0)
            if kind == 'func':
                return value, via, ''
            if kind == 'type':
                return self.go_class(value), 'conv' if via == 'ref' else 'typed', ''
            if kind not in ('unknown', 'iface'):
                return None, None, ''
        if u.lang in TYPED_LANGS:
            target, _ = self.typed(u).call(u, node)
            if target is False:
                return None, None, ''
            if target:
                return target, 'typed', ''
        fields = LANGS[u.lang]['calls'][node.type]
        parts = []
        if callable(fields):
            heads = []
            parts = fields(node, u.src)
        elif fields[0] is None:
            heads = [node.named_children[0]] if node.named_children else []
        else:
            heads = [node.child_by_field_name(field) for field in fields]
        for head in heads:
            leaves(head, u.src, parts)
        if not parts:
            return None, None, ''
        if u.family == 'ruby' and node.type == 'call':
            receiver = node.child_by_field_name('receiver')
            if receiver is not None and receiver.type != 'self' and len(parts) == 1:
                return None, None, ''
            if receiver is not None and receiver.type == 'scope_resolution' and receiver.child_by_field_name('scope') is None and \
                    parts[0] not in self.f.ruby_roots:
                return None, None, ''
            if receiver is not None and text(receiver, u.src) == 'self.class' and ctx:
                found = self.ruby_same_level(u, None, ctx, parts[-1], True)
                if found:
                    return found, 'local', parts[-1]
            if node.parent is not None and node.parent.type == 'assignment' and node.parent.child_by_field_name('left') == node:
                parts[-1] += '='
        name = parts[-1]
        if u.family == 'ruby' and len(parts) == 1 and ctx:
            found = self.ruby_same_level(u, owner_id, ctx, name)
            if found:
                return found, 'local', name
        if len(parts) > 1:
            scoped = any(h is not None and h.type in SCOPED for h in heads)
            target, via = self.qualified(u, ctx, parts[-2], name, scoped, parts[0])
        else:
            target, via = self.unqualified(u, ctx, name)
        return target, via, '.'.join(parts[-2:])

    def ruby_same_level(self, u, owner_id, ctx, name, level=None):
        """Entre `def x` y `def self.x` de la misma clase, una llamada sin receptor va al del mismo nivel que el llamador
        (el cuerpo de la clase cuenta como nivel de clase)."""
        cands = [c for c in self.f.methods.get((ctx, name), ()) if self.g.nodes[c]['file'] == u.rel]
        if len(cands) < 2:
            return None
        if level is None:
            level = ruby_singleton(u.fnodes[owner_id]) if owner_id in u.fnodes else True
        same = [c for c in cands if (ruby_singleton(u.fnodes[c]) if c in u.fnodes else False) == level]
        return same[0] if len(same) == 1 else None

    def link_unit(self, u):
        for owner_id, ctx, node in u.calls:
            target, via, _ = self.resolve_call(u, owner_id, ctx, node)
            if target and target != owner_id:
                self.g.edge(owner_id, target, 'ref' if via == 'conv' else 'call')
                self.derive(u, target, via)
        for owner_id, node in u.selectors:
            target = self.go_selector(u, owner_id, node)
            if target and target != owner_id:
                self.g.edge(owner_id, target, 'ref')
        for owner_id, node in u.idents:
            target = self.go_ident(u, owner_id, node)
            if target and target != owner_id:
                self.g.edge(owner_id, target, 'ref')

    def go_ident(self, u, owner_id, node):
        """Constante, variable o función de otro archivo del mismo paquete usada como valor."""
        name = text(node, u.src)
        if name in u.top or name in u.values or name == '_' or not u.scope:
            return None
        key = os.path.dirname(u.rel)
        if key not in self.go_package_names:
            names = self.go_package_names[key] = defaultdict(set)
            for r in u.scope | {u.rel}:
                other = self.f.units.get(r)
                for word in (set(other.top) | other.values) if other is not None else ():
                    names[word].add(r)
        if not self.go_package_names[key].get(name, set()) - {u.rel}:
            return None
        funcs = self.in_files(name, u.scope)
        homes = [r for r in sorted(u.scope) if r in self.f.units and name in self.f.units[r].values] if not funcs else []
        if not funcs and not homes:
            return None
        if owner_id in u.fnodes and self.go_local(self.go_env(u, owner_id), name, node.start_byte) or go_shadowed(node, name, u.src):
            return None
        if funcs:
            return self.pick(funcs, u.rel)
        live = [r for r in homes if self.f.units[r].enabled] or homes
        return f'm:{live[0]}'

    def go_selector(self, u, owner_id, node):
        env = self.go_env(u, owner_id)
        kind, value, _ = self.go_callee(u, env, node, 0)
        if kind == 'func':
            return value
        operand, field = node.child_by_field_name('operand'), node.child_by_field_name('field')
        if operand is None or field is None or kind != 'unknown' and kind != 'none':
            return None
        return self.go_field_owner(self.go_expr(u, env, operand, 1), text(field, u.src))

    def go_field_owner(self, typ, name, depth=0):
        if not typ or typ == FOREIGN or depth > 3:
            return None
        found, node, info = self.go_struct(typ)
        if found is None or node.type != 'struct_type':
            return None
        if name in info[0]:
            return self.go_class(typ)
        for kind in info[1]:
            owner = self.go_field_owner(self.go_type(found, kind), name, depth + 1)
            if owner:
                return owner
        return None

    def link_bases(self, u):
        g = self.g
        if u.lang == 'ruby':
            for source, target in self.typed(u).bases(u):
                g.edge(source, target, 'inherits')
                add(self.parents[source], target)
            return
        for owner, cid, names in u.bases:
            source = cid or self.pick(self.f.classes_by_name.get(owner, []), u.rel)
            if not source:
                continue
            for base in names:
                if u.lang == 'php' and base in u.foreign:
                    continue  # `use Exception;` importa la clase global, no la homónima del espacio de nombres
                local = [c for c in self.f.classes_by_name.get(base, ()) if self.g.nodes[c]['file'] == u.rel and c != source]
                target, via = (local[0], 'local') if len(local) == 1 else self.unqualified(u, None, base)
                if target and target != source and g.nodes[target]['kind'] == 'class':
                    g.edge(source, target, 'inherits')
                    add(self.parents[source], target)
                    self.derive(u, target, via)

    def type_target(self, u, name):
        if name in u.top:
            found = u.top[name]
            return found if self.g.nodes[found]['kind'] == 'class' else None
        alias = u.aliases.get(name)
        found = None
        if alias and alias[0] == 'def':
            found = alias[1]
        elif alias and alias[0] == 'item' and alias[1] in self.f.units:
            found = self.f.units[alias[1]].top.get(alias[2])
        if found:
            return found if self.g.nodes[found]['kind'] == 'class' else None
        for scope in (u.explicit, u.scope, u.wide):
            found = self.pick(self.classes_in(name, scope), u.rel)
            if found:
                return found
        if u.family in TYPE_GLOBAL and len(name) > 2 and self.global_ok(u, name):
            return self.pick(self.f.classes_by_name.get(name, []), u.rel)
        return None

    def type_file(self, u, prefix, name):
        if prefix:
            qual, root = prefix[-1], prefix[0]
            alias = u.aliases.get(qual)
            if alias and alias[0] == 'files':
                found = self.pick(self.classes_in(name, alias[1]), u.rel)
                return self.g.nodes[found]['file'] if found else self.representative(alias[1])
            if self.foreign(u, (qual, root)):
                return None
            hits = self.f.by_package.get('.'.join(prefix)) or self.f.by_package.get(qual) or self.tails.get(qual)
            found = self.pick(self.classes_in(name, sorted(hits)), u.rel) if hits else None
            outer = None if found else self.type_target(u, qual)
            if found or outer:
                return self.g.nodes[found or outer]['file']
            if qual[:1].isupper():
                return None
        if name in u.foreign:
            return None
        found = self.type_target(u, name)
        return self.g.nodes[found]['file'] if found else None

    def link_types(self, u):
        for qual, name in u.refs:
            alias = u.aliases.get(qual)
            if alias and alias[0] == 'files':
                found = self.pick(self.in_files(name, alias[1]), u.rel)
                rel = self.g.nodes[found]['file'] if found else self.value_file(name, alias[1])
                self.resolved.add((u.rel, rel))
                self.touch(u, rel or self.representative(alias[1]))
        for prefix, name in u.types:
            rel = self.type_file(u, prefix, name)
            self.resolved.add((u.rel, rel))
            self.touch(u, rel)
        if u.lang in TYPED_LANGS:
            for rel in self.typed(u).members(u):
                self.touch(u, rel)

    def typed(self, u):
        """Tipador estático del lenguaje de `u` (Java/Kotlin comparten familia; Rust, Dart y PHP tienen el suyo)."""
        if self.typer is None:
            self.typer = {}
        kind = u.lang if u.lang in ('rust', 'dart', 'php', 'csharp', 'ruby') else 'jvm'
        if kind not in self.typer:
            if kind == 'ruby':
                from .rubytyped import RubyTypes
                self.typer[kind] = RubyTypes(self)
            elif kind == 'csharp':
                from .cstyped import CSharpTypes
                self.typer[kind] = CSharpTypes(self)
            elif kind == 'rust':
                from .rusttyped import RustTypes
                self.typer[kind] = RustTypes(self)
            elif kind == 'dart':
                from .darttyped import DartTypes
                self.typer[kind] = DartTypes(self)
            elif kind == 'php':
                from .phptyped import PhpTypes
                self.typer[kind] = PhpTypes(self)
            else:
                from .typed import JvmTypes
                self.typer[kind] = JvmTypes(self)
        return self.typer[kind]

    def value_file(self, name, rels):
        return next((r for r in sorted(rels) if r in self.f.units and name in self.f.units[r].values), None)

    def derive(self, u, target, via):
        if via in ('wide', 'alias'):
            self.touch(u, self.g.nodes[target]['file'])

    def go_setup(self):
        self.gotypes, self.govars, self.anon = {}, defaultdict(list), {}
        for rel in sorted(self.f.units):
            u = self.f.units[rel]
            d = os.path.dirname(rel)
            for name, node in u.gtypes.items():
                held = self.gotypes.get((d, name))
                if held is None or (u.enabled and not held[0].enabled):
                    self.gotypes[(d, name)] = (u, node)
            for spec in u.gvars:
                for name, entry, _ in self.go_entries(u, spec):
                    self.govars[(d, name)].append((u, entry))

    def go_entries(self, u, n):
        t, out, start = n.type, [], n.end_byte
        if t in ('parameter_declaration', 'variadic_parameter_declaration'):
            kind, start = n.child_by_field_name('type'), 0
            out = [(x, ('type', kind, t != 'parameter_declaration')) for x in n.children_by_field_name('name')]
        elif t == 'var_spec':
            names, kind, value = n.children_by_field_name('name'), n.child_by_field_name('type'), n.child_by_field_name('value')
            values = value.named_children if value is not None else []
            for i, x in enumerate(names):
                if kind is not None:
                    out.append((x, ('type', kind, False)))
                elif len(values) == len(names):
                    out.append((x, ('expr', values[i], 0)))
                elif len(values) == 1:
                    out.append((x, ('expr', values[0], i)))
        elif t in ('short_var_declaration', 'range_clause'):
            left, right = n.child_by_field_name('left'), n.child_by_field_name('right')
            names = left.named_children if left is not None else []
            values = right.named_children if right is not None and right.type == 'expression_list' else [right]
            for i, x in enumerate(names):
                if t == 'range_clause':
                    out.append((x, ('range', right, i)))
                elif len(values) == len(names):
                    out.append((x, ('expr', values[i], 0)))
                elif len(values) == 1:
                    out.append((x, ('expr', values[0], i)))
        elif t == 'type_switch_statement':
            alias = n.child_by_field_name('alias')
            out = [(x, ('none',)) for x in (alias.named_children if alias is not None else [])]
            start = alias.end_byte if alias is not None else start
        return [(text(x, u.src), e, start) for x, e in out if x.type == 'identifier' and text(x, u.src) != '_']

    def go_env(self, u, fid):
        if self.gotypes is None:
            self.go_setup()
        env = self.envs.get(fid)
        if env is None:
            env = self.envs[fid] = defaultdict(list)
            for n in u.decls.get(fid, ()):
                scope = n.parent
                while scope is not None and scope.type not in GO_SCOPES:
                    scope = scope.parent
                if scope is None:
                    continue
                for name, entry, start in self.go_entries(u, n):
                    env[name].append((scope.start_byte, scope.end_byte, max(start, scope.start_byte), entry))
        return env

    def go_local(self, env, name, pos):
        seen = [x for x in env.get(name, ()) if x[0] <= pos < x[1] and x[2] <= pos]
        inner = max((x[0] for x in seen), default=None)
        return [x[3] for x in seen if x[0] == inner]

    def go_named(self, u, name):
        if name in GO_BUILTIN_TYPES:
            return FOREIGN
        key = (os.path.dirname(u.rel), name)
        return ('t',) + key if key in self.gotypes else None

    def go_pkg_type(self, u, pkg, name):
        alias = u.aliases.get(pkg)
        if alias and alias[0] == 'files':
            key = (os.path.dirname(alias[1][0]), name)
            return ('t',) + key if key in self.gotypes else None
        return FOREIGN if pkg in u.foreign else None

    def go_type(self, u, node, depth=0):
        while node is not None and node.type in ('pointer_type', 'parenthesized_type', 'parenthesized_expression'):
            node = node.named_children[0] if node.named_children else None
        if node is None or depth > 6:
            return None
        t = node.type
        if t in ('type_identifier', 'identifier'):
            return self.go_named(u, text(node, u.src))
        if t == 'generic_type':
            return self.go_type(u, node.child_by_field_name('type'), depth + 1)
        if t in ('qualified_type', 'selector_expression'):
            pkg = node.child_by_field_name('package' if t == 'qualified_type' else 'operand')
            name = node.child_by_field_name('name' if t == 'qualified_type' else 'field')
            if pkg is None or name is None or pkg.type not in ('package_identifier', 'identifier'):
                return None
            return self.go_pkg_type(u, text(pkg, u.src), text(name, u.src))
        if t in ('slice_type', 'array_type', 'implicit_length_array_type'):
            return ('e', self.go_type(u, node.child_by_field_name('element'), depth + 1))
        if t in ('map_type', 'channel_type'):
            return ('e', self.go_type(u, node.child_by_field_name('value'), depth + 1))
        if t in ('struct_type', 'interface_type', 'function_type'):
            self.anon[(u.rel, node.start_byte)] = (u, node)
            return ('s', u.rel, node.start_byte)
        if t == 'unary_expression' and text(node, u.src).startswith('*'):
            return self.go_type(u, node.child_by_field_name('operand'), depth + 1)
        return None

    def go_class(self, typ):
        found = self.gotypes.get(typ[1:]) if typ and typ[0] == 't' else None
        return found[0].top.get(typ[2]) if found else None

    def go_struct(self, typ):
        found = (self.gotypes if typ[0] == 't' else self.anon).get(typ[1:]) if typ and typ[0] in 'ts' else None
        if found is None:
            return None, None, None
        u, node = found
        fields, embeds = {}, []
        if node.type == 'struct_type':
            body = next((c for c in node.named_children if c.type == 'field_declaration_list'), None)
            for fd in body.named_children if body is not None else []:
                kind = fd.child_by_field_name('type')
                names = fd.children_by_field_name('name')
                for x in names:
                    fields.setdefault(text(x, u.src), kind)
                if not names and kind is not None:
                    embeds.append(kind)
        elif node.type == 'interface_type':
            for c in node.named_children:
                if c.type == 'method_elem':
                    name = c.child_by_field_name('name')
                    if name is not None:
                        fields.setdefault(text(name, u.src), c)
                elif c.type == 'type_elem':
                    embeds.append(c.named_children[0] if len(c.named_children) == 1 else None)
        return u, node, (fields, embeds)

    def go_field(self, typ, name, depth=0):
        if typ == FOREIGN:
            return FOREIGN
        u, node, info = self.go_struct(typ)
        if u is None or depth > 3 or node.type != 'struct_type':
            return None
        fields, embeds = info
        if name in fields:
            return self.go_type(u, fields[name])
        for kind in embeds:
            inner = self.go_type(u, kind)
            core = go_core(kind)
            if core is not None and text(core, u.src) == name:
                return inner
            found = self.go_field(inner, name, depth + 1)
            if found:
                return found
        return None

    def go_method(self, typ, name, depth=0):
        if typ == FOREIGN or (typ and typ[0] == 'e'):
            return None, True, None
        if not typ or depth > 3:
            return None, False, None
        if typ[0] == 't':
            d, owner = typ[1], typ[2]
            cands = [f for f in self.f.methods.get((owner, name), ()) if os.path.dirname(self.g.nodes[f]['file']) == d]
            if cands:
                return self.pick(cands, self.g.nodes[cands[0]]['file']), True, None
        u, node, info = self.go_struct(typ)
        if u is None:
            return None, False, None
        if node.type == 'interface_type' and name in info[0]:
            return None, False, (u, info[0][name])
        if node.type not in ('struct_type', 'interface_type'):
            return None, node.type not in ('type_identifier', 'qualified_type', 'generic_type'), None
        sure = True
        for kind in info[1]:
            found, known, decl = self.go_method(self.go_type(u, kind), name, depth + 1)
            if found or decl:
                return found, known, decl
            sure = sure and known
        return None, sure, None

    def go_elem(self, typ):
        if typ == FOREIGN:
            return FOREIGN
        if typ and typ[0] == 'e':
            return typ[1]
        u, node, _ = self.go_struct(typ)
        if node is not None and node.type in ('slice_type', 'array_type', 'map_type'):
            return self.go_type(u, node.child_by_field_name('value' if node.type == 'map_type' else 'element'))
        return None

    def go_results(self, u, node):
        result = node.child_by_field_name('result') if node is not None else None
        if result is None:
            return []
        if result.type != 'parameter_list':
            return [self.go_type(u, result)]
        out = []
        for p in result.named_children:
            if p.type in ('parameter_declaration', 'variadic_parameter_declaration'):
                out += [self.go_type(u, p.child_by_field_name('type'))] * max(1, len(p.children_by_field_name('name')))
        return out

    def go_var(self, u, env, name, depth, pos):
        entries = [(u, e) for e in self.go_local(env, name, pos)] or self.govars.get((os.path.dirname(u.rel), name), [])
        return self.go_merge(u, env, entries, depth)

    def go_pkg_var(self, files, name, depth):
        return self.go_merge(None, {}, self.govars.get((os.path.dirname(files[0]), name), []), depth)

    def go_merge(self, u, env, entries, depth):
        found = {self.go_entry(owner, env if owner is u else {}, e, depth) for owner, e in entries} - {None}
        return found.pop() if len(found) == 1 else None

    def go_entry(self, u, env, entry, depth):
        if entry[0] == 'type':
            found = self.go_type(u, entry[1])
            return ('e', found) if entry[2] else found
        if entry[0] == 'expr':
            return self.go_expr(u, env, entry[1], depth + 1, entry[2])
        if entry[0] == 'range':
            outer = self.go_expr(u, env, entry[1], depth + 1)
            return self.go_elem(outer) if entry[2] == 1 else None
        return None

    def go_expr(self, u, env, node, depth=0, idx=0):
        if node is None or depth > 12:
            return None
        key = (u.rel, node.id, idx)
        if key not in self.memo:
            self.memo[key] = None
            self.memo[key] = self.go_infer(u, env, node, depth, idx)
        return self.memo[key]

    def go_infer(self, u, env, node, depth, idx):
        t = node.type
        if t == 'parenthesized_expression':
            return self.go_expr(u, env, node.named_children[0] if node.named_children else None, depth + 1, idx)
        if t in GO_LITERALS:
            return FOREIGN
        if t == 'type_assertion_expression':
            return self.go_type(u, node.child_by_field_name('type')) if idx == 0 else FOREIGN
        if idx and t != 'call_expression':
            return FOREIGN if t == 'index_expression' else None
        if t == 'identifier':
            return self.go_var(u, env, text(node, u.src), depth, node.start_byte)
        if t == 'unary_expression':
            op = text(node, u.src)[:2]
            inner = self.go_expr(u, env, node.child_by_field_name('operand'), depth + 1)
            return inner if op[:1] in '&*' else self.go_elem(inner) if op == '<-' else None
        if t in ('composite_literal', 'type_conversion_expression'):
            return self.go_type(u, node.child_by_field_name('type'))
        if t == 'selector_expression':
            operand, field = node.child_by_field_name('operand'), node.child_by_field_name('field')
            if operand is None or field is None:
                return None
            name = text(operand, u.src)
            if operand.type == 'identifier' and not self.go_local(env, name, operand.start_byte):
                alias = u.aliases.get(name)
                if alias and alias[0] == 'files':
                    return self.go_pkg_var(alias[1], text(field, u.src), depth)
                if name in u.foreign:
                    return FOREIGN
            return self.go_field(self.go_expr(u, env, operand, depth + 1), text(field, u.src))
        if t == 'index_expression':
            return self.go_elem(self.go_expr(u, env, node.child_by_field_name('operand'), depth + 1))
        if t == 'slice_expression':
            return self.go_expr(u, env, node.child_by_field_name('operand'), depth + 1)
        if t == 'call_expression':
            fn = node.child_by_field_name('function')
            word = text(fn, u.src) if fn is not None and fn.type == 'identifier' else None
            if word in ('new', 'make') and not self.go_local(env, word, fn.start_byte):
                args = node.child_by_field_name('arguments')
                return self.go_type(u, args.named_children[0] if args is not None and args.named_children else None)
            kind, value, _ = self.go_callee(u, env, fn, depth + 1)
            if kind == 'type':
                return value if idx == 0 else FOREIGN
            if kind == 'foreign':
                return FOREIGN
            if kind == 'none' and fn is not None and fn.type in ('identifier', 'selector_expression'):
                kind, value = 'iface', self.go_struct(self.go_expr(u, env, fn, depth + 1))[:2]
            if kind in ('func', 'iface'):
                owner, decl = (self.unit_of(value), None) if kind == 'func' else value
                results = self.go_results(owner, decl or (owner.fnodes.get(value) if owner is not None else None))
                return results[idx] if idx < len(results) else None
        return None

    def go_callee(self, u, env, fn, depth):
        if fn is None or depth > 12:
            return 'none', None, None
        t = fn.type
        if t == 'identifier':
            name = text(fn, u.src)
            if self.go_local(env, name, fn.start_byte):
                return 'none', None, None
            target, via = self.unqualified(u, None, name)
            if target:
                if self.g.nodes[target]['kind'] == 'class':
                    return 'type', self.go_named(u, name), None
                return 'func', target, via
            return ('type', FOREIGN, None) if name in GO_BUILTIN_TYPES else ('none', None, None)
        if t == 'selector_expression':
            operand, field = fn.child_by_field_name('operand'), fn.child_by_field_name('field')
            if operand is None or field is None:
                return 'none', None, None
            name, method = text(operand, u.src), text(field, u.src)
            if operand.type == 'identifier' and not self.go_local(env, name, operand.start_byte):
                alias = u.aliases.get(name)
                if alias and alias[0] == 'files':
                    target = self.pick(self.in_files(method, alias[1]), u.rel)
                    if target and self.g.nodes[target]['kind'] == 'class':
                        return 'type', self.go_pkg_type(u, name, method), None
                    return ('func', target, 'wide') if target else ('none', None, None)
                if name in u.foreign:
                    return 'foreign', None, None
            base = self.go_expr(u, env, operand, depth + 1)
            if base == FOREIGN:
                return 'foreign', None, None
            target, sure, decl = self.go_method(base, method)
            if target:
                return 'func', target, 'typed'
            if decl:
                return 'iface', decl, None
            return ('none' if sure else 'unknown'), None, None
        if t == 'parenthesized_expression':
            inner = fn.named_children[0] if fn.named_children else None
            if inner is not None and text(inner, u.src).startswith('*'):
                found = self.go_type(u, inner)
                if found:
                    return 'type', found, 'ref'
            return 'none', None, None
        if t == 'index_expression':
            kind, value, via = self.go_callee(u, env, fn.child_by_field_name('operand'), depth + 1)
            return (kind, value, via) if kind in ('func', 'type') else ('none', None, None)
        if t in GO_TYPE_NODES:
            found = self.go_type(u, fn)
            return ('type', found, None) if found else ('none', None, None)
        return 'none', None, None


def go_package(path):
    segs = path.split('/')
    last = segs[-2] if len(segs) > 1 and re.fullmatch(r'v\d+', segs[-1]) else segs[-1]
    return re.sub(r'^go-|[.-]go$|\.v\d+$', '', last)


def objc_header(rel, src, objc_dirs):
    return os.path.dirname(rel) in objc_dirs or re.search(rb'^\s*(@interface|@protocol|#import)\b', src, re.M) is not None


def analyze_languages(root, files, g, issues, read_source, describe_failure, digest, overrides=None, skip_tests=False):
    families = defaultdict(Family)
    by_family = defaultdict(list)
    objc_dirs = {os.path.dirname(f) for f in files if f.endswith(('.m', '.mm'))}
    for rel in files:
        lang = (overrides or {}).get(rel) or lang_of(rel)
        if not lang:
            continue
        src = read_source(root, rel, issues)
        if src is None:
            continue
        if lang == 'cpp' and rel.endswith('.h') and objc_header(rel, src, objc_dirs):
            lang = 'objc'
        family = families[LANGS[lang]['family']]
        try:
            family.units[rel] = read_unit(g, family, rel, lang, src, digest, skip_tests)
            by_family[LANGS[lang]['family']].append(rel)
        except (RecursionError, ValueError, MemoryError) as exc:
            issues.add(rel, describe_failure(exc))
    for name, family in families.items():
        for owner, new, old in family.method_aliases:
            if (owner, new) not in family.methods and (owner, old) in family.methods:
                family.methods[(owner, new)] = list(family.methods[(owner, old)])
        dirs = defaultdict(list)
        for u in family.units.values():
            dirs[os.path.dirname(u.rel)].append(u.rel)
            for pkg in dict.fromkeys(u.packages):
                family.by_package[pkg].append(u.rel)
                for top in u.top:
                    family.fqn.setdefault(f'{pkg}.{top}', u.top[top])
        if name in MODULE_NAMES:
            for cname, cids in family.classes_by_name.items():
                family.fqn.setdefault(cname, cids[0])
        for u in family.units.values():
            if u.family in DIR_SCOPE:
                u.scope = {r for r in dirs[os.path.dirname(u.rel)] if r != u.rel}
            else:
                u.scope = {r for pkg in u.packages for r in family.by_package[pkg] if r != u.rel}
        paths = [r for member in PATH_GROUPS.get(name, (name,)) for r in by_family[member]]
        linker = Linker(root, g, family, by_family[name], paths)
        for u in family.units.values():
            linker.link_imports(u)
        if name == 'dart':
            linker.dart_scopes()
        for u in family.units.values():
            linker.link_bases(u)
        for u in family.units.values():
            try:
                linker.link_unit(u)
                linker.link_types(u)
            except RecursionError as exc:
                issues.add(u.rel, describe_failure(exc))
        linker.prune_packages()
