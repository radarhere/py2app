import argparse
import pathlib
import sys
import typing

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

from . import __version__, _builder, _config, _progress

DESCRIPTION = """\
Build macOS executable bundles, in particular ".app" bundles.

By default this will build fully standalone bundles, that is
applications that can be used on different machines without
installing dependencies.
"""


def parse_arguments(
    argv: typing.List[str],
) -> typing.Tuple[bool, _config.Py2appConfiguration]:
    parser = argparse.ArgumentParser(
        prog=f"{sys.executable} -mpy2app",
        description=DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    """
    Parse command-line arguments, return if the build should
    be verbose and the parsed configuration.
    """

    parser.add_argument(
        "--pyproject-toml",
        "-c",
        dest="pyproject",
        default="./pyproject.toml",
        metavar="FILE",
        type=pathlib.Path,
        help="path to pyproject.toml (default: %(default)s)",
    )
    parser.add_argument(
        "--alias",
        "-A",
        dest="build_type",
        default=_config.BuildType.STANDALONE,
        action="store_const",
        const=_config.BuildType.ALIAS,
        help="build an alias bundle.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="print more information while building.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    #
    # Experimental or internal options (can be documented,
    # but should not be present in command-line help)
    #

    parser.add_argument(
        "--x-debug-macho-usage",
        dest="debug_macho_usage",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args(argv)

    try:
        with open(args.pyproject, "rb") as stream:
            contents = tomllib.load(stream)
    except OSError as exc:
        print(f"Cannot open {str(args.pyproject)!r}: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        config = _config.parse_pyproject(contents, args.pyproject.parent)
    except _config.ConfigurationError as exc:
        print(f"{args.pyproject}: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.build_type is not None:
        config.build_type = args.build_type

    if args.debug_macho_usage:
        config.debug_macho_usage = True

    return args.verbose, config


def main() -> int:
    """
    Main function for ``python -m py2app``, returns 0 if
    there are no errors and 1 if there are.
    """
    verbose, config = parse_arguments(sys.argv[1:])

    progress = _progress.Progress(level=2 if verbose else 1)
    task_id = progress.add_task("Processing bundles", len(config.bundles))

    for bundle in config.bundles:
        # XXX: Sort bundles to ensure nested bundles get build
        #      after their enclosing bundle.
        # XXX: This needs additional configuration!
        progress.update(
            task_id,
            current=f"{bundle.build_type.value} {'plugin' if bundle.plugin else 'application'} {bundle.name!r}",
        )
        _builder.build_bundle(config, bundle, progress)
        progress.step_task(task_id)
    progress.update(task_id, current="")

    if progress.have_error:
        progress.print("")
        progress.print(
            ":stop_sign: [red]Build failed (see earlier messages for details)[/red]"
        )
    progress._progress.stop()

    return 1 if progress.have_error else 0


if __name__ == "__main__":
    sys.exit(main())
