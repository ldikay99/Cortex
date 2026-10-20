"""Genera un índice SCIP de PHP con scip-php sin ejecutar código del repo.

1. `composer install --no-dev --no-scripts --no-plugins`: descarga dependencias sin ejecutar scripts ni plugins.
2. scip-php hace `require vendor/autoload.php` del proyecto, que incluiría los archivos `autoload.files` de cada
   paquete (y del propio repo). Antes de indexar se vacían esas listas en el autoloader generado por Composer, de
   modo que el `require` solo registra el cargador de clases de Composer.
3. scip-php lee `composer.lock`; si el repo no lo versiona se escribe a partir de `vendor/composer/installed.json`.
4. scip-php analiza las fuentes con nikic/php-parser y escribe `index.scip`.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

FILES_STATIC = re.compile(r'(public static \$files = )array \((?:[^;]|\n)*?\);', re.S)


def run(cmd, cwd, env):
    print('+', ' '.join(str(c)[:60] for c in cmd[:4]), '…', flush=True)
    done = subprocess.run(['nice', '-n', '19'] + [str(c) for c in cmd], cwd=cwd, env=env, stdin=subprocess.DEVNULL)
    if done.returncode:
        sys.exit(f'{Path(str(cmd[0])).name} terminó con código {done.returncode}')


def neutralize(vendor):
    composer = vendor / 'composer'
    files = composer / 'autoload_files.php'
    if files.is_file():
        files.write_text("<?php\n\nreturn array();\n")
    static = composer / 'autoload_static.php'
    if static.is_file():
        text = static.read_text(encoding='utf-8')
        static.write_text(FILES_STATIC.sub(r'\1array ();', text), encoding='utf-8')
    left = static.read_text(encoding='utf-8') if static.is_file() else ''
    if re.search(r'public static \$files = array \(\s*[^)\s]', left):
        sys.exit('no se pudo vaciar autoload.files')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--src', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--work', required=True)
    p.add_argument('--tools', required=True)
    p.add_argument('--root-version', default='', help='versión del paquete raíz (el checkout está en HEAD separado)')
    args = p.parse_args(argv)
    src, work, tools = Path(args.src).resolve(), Path(args.work).resolve(), Path(args.tools).resolve()
    php = tools / 'php' / 'bin' / 'php'
    env = dict(os.environ, COMPOSER_HOME=str(tools / 'php' / 'composer-home'), COMPOSER_CACHE_DIR=str(work / 'caches' / 'composer'),
               COMPOSER_ALLOW_SUPERUSER='0', COMPOSER_NO_INTERACTION='1', TMPDIR=str(work / 'tmp'))
    if args.root_version:
        env['COMPOSER_ROOT_VERSION'] = args.root_version
    run([php, tools / 'php' / 'bin' / 'composer.phar', 'install', '--no-dev', '--no-scripts', '--no-plugins',
         '--no-progress', '--prefer-dist', '--ignore-platform-reqs'], src, env)
    neutralize(src / 'vendor')
    lock = src / 'composer.lock'
    if not lock.is_file():
        installed = json.loads((src / 'vendor' / 'composer' / 'installed.json').read_text(encoding='utf-8'))
        lock.write_text(json.dumps({'packages': installed.get('packages', [])}), encoding='utf-8')
    out = src / 'index.scip'
    out.unlink(missing_ok=True)
    run([php, '-d', 'error_reporting=E_ALL&~E_DEPRECATED', tools / 'php' / 'scip-php' / 'bin' / 'scip-php',
         '--memory-limit=2G'], src, env)
    shutil.move(str(out), args.output)
    return 0


if __name__ == '__main__':
    sys.exit(main())
