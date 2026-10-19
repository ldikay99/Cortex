import importlib
import os
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
        Self Some None Ok Err Default Clone Debug Display Iterator From Into AsRef Send Sync Sized Fn FnMut FnOnce''',
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
    'ruby': '''class to_s to_sym to_i to_f to_a to_h to_str to_proc inspect each each_with_index each_pair map collect
        select filter reject find detect each_with_object inject reduce include? is_a? kind_of? respond_to? send
        public_send freeze frozen? dup clone merge merge! key? fetch keys values push pop shift unshift first last join
        split strip gsub sub length size empty? nil? present? blank? call puts print require require_relative raise
        tap then instance_variable_get instance_variable_set define_method attr_accessor attr_reader attr_writer
        extend include prepend delete compact flatten uniq sort sort_by group_by any? all? none? count sum min max
        times format to_json hash eql? equal? instance_of? method_missing super new delete_if keep_if sort! map! select!
        reject! uniq! compact! flatten! each_key each_value transform_values transform_keys dig slice except union
        upcase downcase capitalize bytesize encoding force_encoding start_with? end_with? match match? scan
        strftime iso8601 httpdate to_date to_time succ pred''',
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


def go_function_name(node, src):
    name = node.child_by_field_name('name')
    receiver = node.child_by_field_name('receiver')
    owner = None
    if receiver is not None:
        types = [x for x in leaves(receiver, src) if x[:1].isupper()] or leaves(receiver, src)[1:]
        owner = types[0] if types else None
    return owner, text(name, src) if name is not None else None


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


def go_imports(node, src):
    path = node.child_by_field_name('path')
    if path is None:
        return []
    alias = node.child_by_field_name('name')
    return [('go', strip_quotes(text(path, src)), text(alias, src) if alias is not None else None)]


def rust_imports(node, src):
    if node.type == 'mod_item':
        if node.child_by_field_name('body') is not None:
            return []
        name = node.child_by_field_name('name')
        return [('rustmod', text(name, src), None)] if name is not None else []
    arg = node.child_by_field_name('argument')
    if arg is None:
        return []
    out = []
    for spec in expand(re.sub(r'\s+', ' ', text(arg, src)), '::'):
        path, alias = split_alias(spec, ' as ')
        segs = [s for s in path.split('::') if s]
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


def ruby_import(node, src):
    method = node.child_by_field_name('method')
    if method is None or node.child_by_field_name('receiver') is not None:
        return []
    kind = text(method, src)
    if kind not in ('require', 'require_relative', 'load'):
        return []
    target = string_value(node.child_by_field_name('arguments') or node, src)
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
    holder = node.parent if node.parent is not None and node.parent.type == 'method_signature' else node
    after = holder.next_named_sibling
    return after if after is not None and after.type == 'function_body' else None


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
        return [('dartpkg', (pkg, path), alias)] if path else []
    return [('relpath', target, alias)]


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
    return out


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


LANGS = {
    'go': dict(
        exts=('.go',), grammar=('tree_sitter_go', 'language'), family='go',
        classes={'type_spec'}, functions={'function_declaration', 'method_declaration'}, fn_name=go_function_name,
        calls={'call_expression': ('function',)}, imports={'import_spec': go_imports}, package={'package_clause'},
        types=({'type_identifier'}, None), refs={'selector_expression'},
    ),
    'rust': dict(
        exts=('.rs',), grammar=('tree_sitter_rust', 'language'), family='rust',
        classes={'struct_item', 'enum_item', 'trait_item', 'union_item'},
        functions={'function_item', 'function_signature_item'}, owner=rust_owner, owner_bases=rust_bases,
        calls={'call_expression': ('function',), 'struct_expression': ('name',)},
        imports={'use_declaration': rust_imports, 'mod_item': rust_imports},
        types=({'type_identifier'}, None), tests=rust_test,
    ),
    'java': dict(
        exts=('.java',), grammar=('tree_sitter_java', 'language'), family='jvm',
        classes={'class_declaration', 'interface_declaration', 'enum_declaration', 'record_declaration',
                 'annotation_type_declaration'},
        functions={'method_declaration'}, bases={'superclass', 'super_interfaces'},
        calls={'method_invocation': ('object', 'name'), 'object_creation_expression': ('type',)},
        imports={'import_declaration': dotted_imports(r'^import (static )?', ' as ', {'*'})},
        package={'package_declaration'}, types=({'type_identifier'}, None),
    ),
    'kotlin': dict(
        exts=('.kt', '.kts'), grammar=('tree_sitter_kotlin', 'language'), family='jvm',
        classes={'class_declaration', 'object_declaration'}, functions={'function_declaration'},
        bases={'delegation_specifiers', 'delegation_specifier'}, calls=CALLS_JVM,
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
                 'enum_declaration'},
        functions={'method_declaration'}, bases={'base_list'},
        calls={'invocation_expression': ('function',), 'object_creation_expression': ('type',)},
        imports={'using_directive': csharp_imports},
        package={'namespace_declaration', 'file_scoped_namespace_declaration'},
        types=({'identifier'}, {'generic_name', 'type_argument_list', 'qualified_name', 'nullable_type', 'array_type',
                               'pointer_type', 'ref_type'}),
    ),
    'php': dict(
        exts=('.php',), grammar=('tree_sitter_php', 'language_php'), family='php',
        classes={'class_declaration', 'interface_declaration', 'trait_declaration', 'enum_declaration'},
        functions={'method_declaration', 'function_definition'}, bases={'base_clause', 'class_interface_clause'},
        calls={'function_call_expression': ('function',), 'member_call_expression': ('object', 'name'),
               'scoped_call_expression': ('scope', 'name'), 'object_creation_expression': (None,)},
        imports={'namespace_use_declaration': php_imports, 'require_expression': php_imports,
                 'require_once_expression': php_imports, 'include_expression': php_imports,
                 'include_once_expression': php_imports},
        package={'namespace_definition'},
    ),
    'ruby': dict(
        exts=('.rb', '.rake', '.gemspec', '.ru', '.podspec', '.jbuilder', '.thor'), grammar=('tree_sitter_ruby', 'language'), family='ruby',
        classes={'class', 'module'}, namespaces={'module'}, functions={'method', 'singleton_method'}, bases={'superclass'},
        calls={'call': ('receiver', 'method')}, imports={'call': ruby_import},
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
        calls={'call_expression': (None,)}, types=({'type_identifier'}, None),
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
                 'extension_type_declaration'}, class_name=first_ident, class_bases=dart_bases,
        functions={'function_signature', 'getter_signature', 'setter_signature', 'constructor_signature',
                   'factory_constructor_signature', 'constant_constructor_signature', 'operator_signature'},
        body=dart_body, calls={'selector': dart_callee, 'new_expression': (None,), 'const_object_expression': (None,)},
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


def parser_for(lang):
    if lang not in _PARSERS:
        module, attr = LANGS[lang]['grammar']
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)
            _PARSERS[lang] = Parser(Language(getattr(importlib.import_module(module), attr)()))
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


class Family:
    def __init__(self):
        self.units = {}
        self.top_by_name = defaultdict(list)
        self.classes_by_name = defaultdict(list)
        self.methods = defaultdict(list)
        self.methods_by_name = defaultdict(list)
        self.by_package = defaultdict(list)
        self.fqn = {}


def read_unit(g, family, rel, lang, src, digest, skip_tests=False):
    spec = LANGS[lang]
    tree = parser_for(lang).parse(src)
    mid = g.node(f'm:{rel}', kind='module', name=rel.rsplit('/', 1)[-1], file=rel, line=1, lang=lang, hash=digest(src))
    u = Unit(rel, lang, src, mid)
    classes, functions = spec['classes'], spec['functions']
    calls, imports, packages = spec['calls'], spec.get('imports', {}), spec.get('package', set())
    bases, namespaces = spec.get('bases', set()), spec.get('namespaces', set())
    owner_of, fn_name, class_name = spec.get('owner'), spec.get('fn_name'), spec.get('class_name')
    class_bases, body_of = spec.get('class_bases'), spec.get('body')
    type_idents, type_parents = spec.get('types', (set(), None))
    refs, is_test = spec.get('refs', set()), spec.get('tests') if skip_tests else None
    spaces, detached = set(), {}

    def declare_method(owner, name, node, cid):
        fid = g.node(f'f:{rel}:{owner}.{name}', kind='method', name=f'{owner}.{name}', file=rel,
                     line=node.start_point[0] + 1, lang=lang, hash=digest(src[node.start_byte:node.end_byte]))
        g.edge(cid or mid, fid, 'contains')
        add(family.methods[(owner, name)], fid)
        add(family.methods_by_name[name], fid)
        return fid

    stack = [(tree.root_node, None, None, mid, False)]
    while stack:
        n, ctx, ctx_id, owner_id, in_fn = stack.pop()
        if n.id in detached:
            ctx, ctx_id, owner_id, in_fn = *detached.pop(n.id), True
        t = n.type
        if is_test and is_test(n, src):
            continue
        if t in type_idents:
            found = type_ref(n, src, type_parents)
            if found:
                u.types.setdefault(found, None)
        if t in refs:
            operand, field = n.child_by_field_name('operand'), n.child_by_field_name('field')
            if operand is not None and field is not None and operand.type == 'identifier':
                u.refs.setdefault((text(operand, src), text(field, src)), None)
        if t in calls:
            u.calls.append((owner_id, ctx, n))
        if t in imports:
            u.imports += imports[t](n, src)
        if t in packages:
            name = package_name(n, src)
            if name:
                u.packages.append(name)
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
            if t in classes:
                name = class_name(n, src) if class_name else last_name(n.child_by_field_name('name'), src)
                if name:
                    cid = g.node(f'c:{rel}:{name}', kind='class', name=name, file=rel, line=n.start_point[0] + 1, lang=lang,
                                 hash=digest(src[n.start_byte:n.end_byte]))
                    g.edge(ctx_id or mid, cid, 'contains')
                    add(family.classes_by_name[name], cid)
                    if t in namespaces:
                        spaces.add(cid)
                    if ctx is None or ctx_id in spaces:
                        u.top.setdefault(name, cid)
                        add(u.top_classes, name)
                    if class_bases:
                        names = class_bases(n, src)
                    else:
                        names = [x for c in n.named_children if c.type in bases for x in base_names(c, src)]
                    if names:
                        u.bases.append((name, cid, names))
                    for c in reversed(n.named_children):
                        stack.append((c, name, cid, cid, False))
                    continue
            if t in functions:
                owner, name = fn_name(n, src) if fn_name else (None, last_name(n.child_by_field_name('name'), src))
                owner = owner or ctx
                if name:
                    if owner:
                        fid = declare_method(owner, name, n, ctx_id if owner == ctx else None)
                    else:
                        fid = g.node(f'f:{rel}:{name}', kind='function', name=name, file=rel, line=n.start_point[0] + 1,
                                     lang=lang, hash=digest(src[n.start_byte:n.end_byte]))
                        g.edge(mid, fid, 'contains')
                        u.top.setdefault(name, fid)
                        add(family.top_by_name[name], fid)
                    body = body_of(n) if body_of else None
                    if body is not None:
                        detached[body.id] = (owner, ctx_id, fid)
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
        self.gomods = self.find_markers('go.mod', r'^module\s+(\S+)')
        self.crates = self.find_markers('Cargo.toml', r'^name\s*=\s*"([^"]+)"')
        self.pubs = None
        self.derived = set()
        self.parents = defaultdict(list)
        self.tails = defaultdict(set)
        for pkg, rels in family.by_package.items():
            self.tails[re.split(r'\.|::', pkg)[-1]].update(rels)
        self.roots = {}
        self.reps = {}

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

    def go_module_dir(self, value):
        best = None
        for d, module in self.gomods.items():
            if module and (value == module or value.startswith(module + '/')) and (best is None or len(module) > len(best[1])):
                best = (d, module)
        return os.path.join(best[0], value[len(best[1]):].strip('/')).strip('/') if best else None

    def representative(self, rels):
        key = tuple(rels)
        if key not in self.reps:
            pool = sorted(rels)
            plain = [r for r in pool if not r.endswith('_test.go')] or pool
            d = os.path.dirname(plain[0])
            names = [p for r in plain if r in self.f.units for p in self.f.units[r].packages] + [os.path.basename(d), 'doc']
            hit = next((c for c in (os.path.join(d, n + '.go') for n in names) if c in plain), None)
            if hit is None:
                hit = min(plain, key=lambda r: (-len(self.f.units[r].top) if r in self.f.units else 0, r))
            self.reps[key] = hit
        return self.reps[key]

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
                    continue
                targets = [r for r in self.by_dir.get(mod_dir, []) if r.endswith('.go') and r != u.rel]
                if targets:
                    declared = [p for r in targets if r in self.f.units for p in self.f.units[r].packages]
                    u.aliases[alias or (declared[0] if declared else value.rsplit('/', 1)[-1])] = ('files', targets)
                    self.touch(u, self.representative(targets))
            elif kind == 'rustmod':
                base, here = self.rust_module(u.rel)
                found = self.rust_file(base, here + [value])
                if found:
                    self.add_explicit(u, found)
                    u.aliases[value] = ('files', [found])
            elif kind in ('rust', 'rustglob'):
                if not value:
                    continue
                found, rest = self.rust_resolve(u, value)
                if not found:
                    if kind == 'rust' and alias != '_' and value[0] not in ('crate', 'self', 'super'):
                        u.foreign.add(alias or value[-1])
                    continue
                self.add_explicit(u, found)
                if kind == 'rustglob':
                    u.wide.add(found)
                elif rest:
                    u.aliases[alias or rest[-1]] = ('item', found, rest[0])
                else:
                    u.aliases[alias or value[-1]] = ('files', [found])
            elif kind == 'fqn':
                target = self.f.fqn.get(value)
                if target:
                    self.add_explicit(u, self.g.nodes[target]['file'])
                    u.aliases[alias or value.rsplit('.', 1)[-1]] = ('def', target)
                elif '.' in value and self.f.fqn.get(value.rsplit('.', 1)[0]):
                    owner = self.f.fqn[value.rsplit('.', 1)[0]]
                    self.add_explicit(u, self.g.nodes[owner]['file'])
                else:
                    hits = self.suffix(value.replace('.', '/'), exts) if u.lang == 'php' else []
                    if len(hits) == 1:
                        self.add_explicit(u, hits[0])
                    elif value not in self.f.by_package and not self.defined(alias or value.rsplit('.', 1)[-1]):
                        u.foreign.add(alias or value.rsplit('.', 1)[-1])
            elif kind == 'open':
                target = self.f.fqn.get(value)
                if target and self.g.nodes[target]['kind'] == 'class':
                    self.add_explicit(u, self.g.nodes[target]['file'])
                    add(u.opened, target)
            elif kind == 'pkg':
                u.wide.update(r for r in self.f.by_package.get(value, ()) if r != u.rel)
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
            elif kind == 'suffix':
                hits = self.suffix(value, family_exts)
                if len(hits) == 1:
                    self.add_explicit(u, hits[0])
                    if alias:
                        u.aliases[alias] = ('files', hits)
            elif kind == 'module':
                hits = sorted(r for r in self.f.by_package.get(value, ()) if r != u.rel)
                if not hits:
                    found = self.suffix(re.sub(r'::|\.', '/', value), family_exts)
                    hits = found if len(found) == 1 else []
                for hit in hits:
                    self.add_explicit(u, hit)
                if hits and alias:
                    u.aliases[alias] = ('files', hits)
            elif kind == 'stem':
                if value in u.top:
                    continue
                hits = [r for r in self.by_stem.get(value.lower(), []) if os.path.splitext(r)[1] in exts and r != u.rel]
                hits = [r for r in hits if os.path.dirname(r) == os.path.dirname(u.rel)] or hits
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
                hit = next((c for c in (os.path.join(d, 'lib', path).lstrip('/') for d in roots) if c in self.files), None)
                self.add_explicit(u, hit)
                if hit and alias:
                    u.aliases[alias] = ('files', [hit])
                elif alias and not hit:
                    u.foreign.add(alias)
            elif kind == 'lua':
                path = value.replace('.', '/')
                hits = self.suffix(path, family_exts) or self.suffix(path + '/init', family_exts)
                if len(hits) == 1:
                    self.add_explicit(u, hits[0])
                    if alias:
                        u.aliases[alias] = ('files', hits)

    def pick(self, cands, rel):
        cands = list(dict.fromkeys(cands))
        if len(cands) == 1:
            return cands[0]
        if not cands:
            return None
        same = [c for c in cands if self.g.nodes[c]['file'] == rel]
        if len(same) == 1:
            return same[0]
        near = [c for c in cands if os.path.dirname(self.g.nodes[c]['file']) == os.path.dirname(rel)]
        return near[0] if len(near) == 1 else None

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
            if ctx and (ctx, name) in self.f.methods and qual != 'super':
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
        if qual[:1].isupper() and (qual, name) in self.f.methods:
            found = self.pick(self.f.methods[(qual, name)], u.rel)
            if found:
                return found, 'global'
        typed = typed or qual in self.f.classes_by_name
        if not typed and qual == (root or qual) and qual[:1].isupper():
            return None, None
        if name in BUILTINS.get(u.family, ()):
            return None, None
        if u.family not in STRICT and len(name) > 3 and len(self.f.methods_by_name.get(name, ())) == 1:
            found = self.f.methods_by_name[name][0]
            if typed or self.reachable(u, self.g.nodes[found]['file']):
                return found, 'global'
        if scoped and u.family not in NO_GLOBAL and len(self.f.top_by_name.get(name, ())) == 1:
            return self.f.top_by_name[name][0], 'global'
        return None, None

    def resolve_call(self, u, owner_id, ctx, node):
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
        name = parts[-1]
        if len(parts) > 1:
            scoped = any(h is not None and h.type in SCOPED for h in heads)
            target, via = self.qualified(u, ctx, parts[-2], name, scoped, parts[0])
        else:
            target, via = self.unqualified(u, ctx, name)
        return target, via, '.'.join(parts[-2:])

    def link_unit(self, u):
        for owner_id, ctx, node in u.calls:
            target, via, _ = self.resolve_call(u, owner_id, ctx, node)
            if target and target != owner_id:
                self.g.edge(owner_id, target, 'call')
                self.derive(u, target, via)

    def link_bases(self, u):
        g = self.g
        for owner, cid, names in u.bases:
            source = cid or self.pick(self.f.classes_by_name.get(owner, []), u.rel)
            if not source:
                continue
            for base in names:
                target, via = self.unqualified(u, None, base)
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
                self.touch(u, self.g.nodes[found]['file'] if found else self.representative(alias[1]))
        for prefix, name in u.types:
            self.touch(u, self.type_file(u, prefix, name))

    def derive(self, u, target, via):
        if via in ('wide', 'alias'):
            self.touch(u, self.g.nodes[target]['file'])


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
        for u in family.units.values():
            linker.link_bases(u)
        for u in family.units.values():
            try:
                linker.link_unit(u)
                linker.link_types(u)
            except RecursionError as exc:
                issues.add(u.rel, describe_failure(exc))
