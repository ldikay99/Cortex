"""Genera un índice SCIP de C# con scip-dotnet sin evaluar el MSBuild del repo.

El repo no aporta ningún archivo de proyecto: se copian sus `.cs` (con las mismas rutas relativas) a una carpeta
fuera del clon y se escribe un `.csproj` propio que solo compila esas copias. Los paquetes NuGet que se pidan con
`--package` (los `PackageReference` del proyecto original, con versión fijada) entran solo con sus ensamblados de
referencia: sin `build/*.props|targets`, analizadores ni generadores, cosa que se comprueba tras `restore`; un marco
compartido (`--framework-ref Microsoft.AspNetCore.App`) sale de los paquetes de referencia instalados con el SDK. Junto a él
hay `Directory.Build.props/.targets`, `Directory.Packages.props` y `NuGet.config` propios para que MSBuild y NuGet
no suban a buscar otros. `dotnet restore` se ejecuta solo sobre ese proyecto y scip-dotnet se lanza con
`--skip-dotnet-restore` y el directorio de trabajo en la carpeta del proyecto propio: nunca evalúa los `.csproj`,
`.sln` ni `Directory.Build.*` del repo.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

PROJECT = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>{framework}</TargetFramework>
    <OutputType>Library</OutputType>
    <AssemblyName>{name}</AssemblyName>
    <EnableDefaultItems>false</EnableDefaultItems>
    <ImplicitUsings>{implicit}</ImplicitUsings>
    <Nullable>{nullable}</Nullable>
    <LangVersion>latest</LangVersion>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks>
    <DefineConstants>$(DefineConstants){defines}</DefineConstants>
    <TreatWarningsAsErrors>false</TreatWarningsAsErrors>
    <NoWarn>$(NoWarn);CS1591</NoWarn>
    <RunAnalyzers>false</RunAnalyzers>
    <EnableNETAnalyzers>false</EnableNETAnalyzers>
    <GenerateAssemblyInfo>false</GenerateAssemblyInfo>
    <GenerateDocumentationFile>false</GenerateDocumentationFile>
  </PropertyGroup>
  <ItemGroup>
{items}
  </ItemGroup>
  <ItemGroup>
{usings}
  </ItemGroup>
  <ItemGroup>
{refs}
  </ItemGroup>
  <!-- de los paquetes solo se usan los ensamblados de referencia: ni analizadores ni generadores de código -->
  <Target Name="BenchDropPackageAnalyzers" AfterTargets="ResolvePackageAssets;ResolveLockFileAnalyzers" BeforeTargets="CoreCompile">
    <ItemGroup>
      <Analyzer Remove="@(Analyzer)" Condition="$([System.String]::Copy('%(Analyzer.FullPath)').StartsWith('$(NuGetPackageRoot)'))" />
    </ItemGroup>
  </Target>
</Project>
"""
EMPTY = '<Project>\n</Project>\n'
NUGET = """<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <packageSources>
    <clear />
    <add key="nuget.org" value="https://api.nuget.org/v3/index.json" />
  </packageSources>
</configuration>
"""


def run(cmd, cwd, env):
    print('+', ' '.join(str(c)[:60] for c in cmd[:3]), '…', flush=True)
    done = subprocess.run(['nice', '-n', '19'] + [str(c) for c in cmd], cwd=cwd, env=env, stdin=subprocess.DEVNULL)
    if done.returncode:
        sys.exit(f'{Path(str(cmd[0])).name} terminó con código {done.returncode}')


def check_restore(stage):
    """Ningún paquete aporta `build/*.props|targets` (MSBuild los importaría) ni analizadores o generadores (Roslyn los
    ejecutaría): si el grafo de NuGet trae alguno, también de una dependencia transitiva, se para antes de indexar.
    Con `IncludeAssets="compile"` NuGet solo deja los marcadores vacíos `_._`."""
    obj = stage / 'obj'
    for name in ('Bench.csproj.nuget.g.props', 'Bench.csproj.nuget.g.targets'):
        path = obj / name
        if path.is_file() and '<Import ' in path.read_text(encoding='utf-8', errors='replace'):
            sys.exit(f'{name} importa archivos de paquetes')
    assets = obj / 'project.assets.json'
    data = json.loads(assets.read_text(encoding='utf-8')) if assets.is_file() else {}
    for target in data.get('targets', {}).values():
        for pkg, info in target.items():
            real = [f for k in ('build', 'buildMultiTargeting', 'analyzers') for f in info.get(k, {}) if not f.endswith('/_._') and f != '_._']
            if real:
                sys.exit(f'{pkg} aportaría {real[0]}')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--src', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--work', required=True)
    p.add_argument('--tools', required=True)
    p.add_argument('--sources', action='append', required=True, help='carpeta de fuentes relativa a --src')
    p.add_argument('--define', action='append', default=[])
    p.add_argument('--framework', default='net9.0')
    p.add_argument('--nullable', default='enable')
    p.add_argument('--implicit-usings', default='disable', choices=('enable', 'disable'),
                   help='`global using` implícitos del SDK (como `<ImplicitUsings>` del proyecto original)')
    p.add_argument('--using', action='append', default=[],
                   help='`global using` del proyecto original (`<Using Include="X" />`); `-X` lo quita (`<Using Remove="X" />`)')
    p.add_argument('--framework-ref', action='append', default=[],
                   help='marco compartido del SDK (`Microsoft.AspNetCore.App`, el `<FrameworkReference>` implícito de '
                        '`Microsoft.NET.Sdk.Web`); sale de los paquetes de referencia ya instalados con el SDK')
    p.add_argument('--package', action='append', default=[],
                   help='`Id@Versión` de NuGet (los `<PackageReference>` del proyecto original): solo ensamblados de '
                        'referencia (`IncludeAssets="compile"`), sin `build/*.props`, analizadores ni generadores')
    args = p.parse_args(argv)
    src, work, tools = Path(args.src).resolve(), Path(args.work).resolve(), Path(args.tools).resolve()
    stage = work / 'build' / Path(args.output).stem
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    for folder in args.sources:
        for path in sorted((src / folder).rglob('*.cs')):
            rel = path.relative_to(src)
            if path.is_symlink() or not path.is_file() or {'obj', 'bin'} & set(rel.parts):
                continue
            (stage / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, stage / rel)
    items = '\n'.join(f'    <Compile Include="{escape(s)}/**/*.cs" />' for s in args.sources)
    defines = ''.join(f';{d}' for d in args.define)
    usings = '\n'.join(f'    <Using Remove="{escape(u[1:])}" />' if u.startswith('-') else f'    <Using Include="{escape(u)}" />'
                       for u in args.using)
    refs = [f'    <FrameworkReference Include="{escape(f)}" />' for f in args.framework_ref]
    for spec in args.package:
        pkg, _, version = spec.partition('@')
        if not pkg or not version:
            sys.exit(f'--package necesita Id@Versión: {spec}')
        refs.append(f'    <PackageReference Include="{escape(pkg)}" Version="{escape(version)}" IncludeAssets="compile" '
                    'ExcludeAssets="runtime;build;buildTransitive;native;contentFiles;analyzers" PrivateAssets="all" />')
    (stage / 'Bench.csproj').write_text(PROJECT.format(framework=args.framework, name=Path(args.output).stem, nullable=args.nullable,
                                                        implicit=args.implicit_usings, refs='\n'.join(refs),
                                                        defines=defines, items=items, usings=usings), encoding='utf-8')
    for name in ('Directory.Build.props', 'Directory.Build.targets', 'Directory.Packages.props'):
        (stage / name).write_text(EMPTY, encoding='utf-8')
    (stage / 'NuGet.config').write_text(NUGET, encoding='utf-8')
    sdk = tools / 'dotnet' / 'sdk'
    env = dict(os.environ, DOTNET_ROOT=str(sdk), DOTNET_CLI_HOME=str(tools / 'dotnet' / 'home'), NUGET_PACKAGES=str(work / 'caches' / 'nuget'),
               DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1',
               DOTNET_GENERATE_ASPNET_CERTIFICATE='false', MSBUILDDISABLENODEREUSE='1', TMPDIR=str(work / 'tmp'),
               PATH=os.pathsep.join([str(sdk), os.environ.get('PATH', '')]))
    run([sdk / 'dotnet', 'restore', stage / 'Bench.csproj', '--configfile', stage / 'NuGet.config'], stage, env)
    check_restore(stage)
    run([tools / 'dotnet' / 'tools' / 'scip-dotnet', 'index', stage / 'Bench.csproj', '--skip-dotnet-restore',
         '--working-directory', stage, '--output', Path(args.output).resolve()], stage, env)
    return 0


if __name__ == '__main__':
    sys.exit(main())
