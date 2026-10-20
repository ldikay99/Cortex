"""Genera un índice SCIP de Java/Kotlin sin Maven ni Gradle.

Compila las carpetas de fuentes indicadas con javac (o kotlinc) y el plugin
SemanticDB, sin procesadores de anotaciones (`-proc:none`) ni plugins del repo,
y convierte el resultado con `scip-java index-semanticdb`. Las dependencias son
coordenadas de Maven Central fijadas en repos.toml; coursier las descarga y
verifica sus sumas, sin ejecutar nada del repo.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

SCIP_JAVA = 'com.sourcegraph:scip-java_2.13:0.12.3'
SEMANTICDB_JAVAC = 'com.sourcegraph:semanticdb-javac:0.12.3'
SEMANTICDB_KOTLINC = 'com.sourcegraph:semanticdb-kotlinc:{}'
EXPORTS = [f'--add-exports=jdk.compiler/com.sun.tools.javac.{p}=ALL-UNNAMED'
           for p in ('api', 'code', 'model', 'tree', 'util')]


def run(cmd, **kw):
    print('+', ' '.join(str(c)[:60] for c in cmd[:4]), '…', flush=True)
    done = subprocess.run(['nice', '-n', '19'] + [str(c) for c in cmd], stdin=subprocess.DEVNULL, **kw)
    if done.returncode:
        sys.exit(f'{Path(str(cmd[0])).name} terminó con código {done.returncode}')


def fetch(coursier, coords, env, transitive=True):
    if not coords:
        return []
    cmd = ['java', '-jar', coursier, 'fetch', '--quiet'] + ([] if transitive else ['--intransitive']) + list(coords)
    out = subprocess.run(cmd, check=True, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL).stdout
    return [line for line in out.split('\n') if line.endswith('.jar')]


def sources(src, roots, exts, exclude):
    out = []
    for root in roots:
        for path in sorted((src / root).rglob('*')):
            if path.suffix in exts and path.is_file() and path.name not in exclude and not path.is_symlink():
                out.append(path)
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--src', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--work', required=True)
    p.add_argument('--tools', required=True)
    p.add_argument('--sources', action='append', required=True, help='carpeta de fuentes relativa a --src')
    p.add_argument('--dep', action='append', default=[], help='coordenada Maven group:artifact:version')
    p.add_argument('--release', default='')
    p.add_argument('--kotlin', default='2.2.0', help='versión de kotlinc (debe casar con semanticdb-kotlinc)')
    p.add_argument('--semanticdb-kotlinc', default='0.6.0')
    p.add_argument('--exclude', action='append', default=['module-info.java', 'package-info.java'])
    args = p.parse_args(argv)
    src, work, tools = Path(args.src).resolve(), Path(args.work).resolve(), Path(args.tools).resolve()
    coursier = tools / 'jvm' / 'coursier.jar'
    env = dict(os.environ, COURSIER_CACHE=str(work / 'caches' / 'coursier'))
    build = work / 'build' / Path(args.output).stem
    shutil.rmtree(build, ignore_errors=True)
    classes, target = build / 'classes', build / 'semanticdb'
    classes.mkdir(parents=True)
    target.mkdir(parents=True)
    java_files = sources(src, args.sources, {'.java'}, set(args.exclude))
    kotlin_files = sources(src, args.sources, {'.kt'}, set(args.exclude))
    stdlib = [f'org.jetbrains.kotlin:kotlin-stdlib:{args.kotlin}'] if kotlin_files else []
    deps = fetch(coursier, args.dep + stdlib, env)
    heap = '-Xmx2g'
    if kotlin_files:
        compiler = fetch(coursier, [f'org.jetbrains.kotlin:kotlin-compiler-embeddable:{args.kotlin}'], env)
        plugin = fetch(coursier, [SEMANTICDB_KOTLINC.format(args.semanticdb_kotlinc)], env, transitive=False)
        argfile = build / 'kotlinc.args'
        argfile.write_text('\n'.join(str(f) for f in kotlin_files + java_files) + '\n')
        run(['java', heap, '-cp', os.pathsep.join(compiler), 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
             '-no-stdlib', '-no-reflect', '-nowarn', '-Xno-call-assertions', '-d', classes,
             '-classpath', os.pathsep.join(deps), f'-Xplugin={plugin[0]}',
             '-P', f'plugin:semanticdb-kotlinc:sourceroot={src}', '-P', f'plugin:semanticdb-kotlinc:targetroot={target}',
             f'@{argfile}'], env=env)
    if java_files:
        plugin = fetch(coursier, [SEMANTICDB_JAVAC], env, transitive=False)
        argfile = build / 'javac.args'
        argfile.write_text('\n'.join(f'"{f}"' for f in java_files) + '\n')
        if shutil.which('javac'):
            javac = ['javac', f'-J{heap}'] + [f'-J{e}' for e in EXPORTS]
        else:
            javac = ['java', heap] + EXPORTS + ['-m', 'jdk.compiler/com.sun.tools.javac.Main']
        run(javac + [
            '-proc:none', '-implicit:none', '-nowarn', '-Xlint:none', '-encoding', 'UTF-8', '-d', classes,
            '-classpath', os.pathsep.join(deps + [str(classes)]), '-processorpath', plugin[0],
            f'-Xplugin:semanticdb -sourceroot:{src} -targetroot:{target}']
            + (['--release', args.release] if args.release else []) + [f'@{argfile}'], env=env)
    scip_java = fetch(coursier, [SCIP_JAVA], env)
    run(['java', heap, '-cp', os.pathsep.join(scip_java), 'com.sourcegraph.scip_java.ScipJava', 'index-semanticdb',
         '--output', Path(args.output).resolve(), target], env=env)
    return 0


if __name__ == '__main__':
    sys.exit(main())
