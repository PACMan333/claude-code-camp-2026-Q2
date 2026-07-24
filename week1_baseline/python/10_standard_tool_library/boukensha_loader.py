"""boukensha_loader resolves which step folder and config directory to use,
then boots the REPL.

Each setting is resolved independently in this order:
  1. BOUKENSHA_PATH / BOUKENSHA_DIR environment variable
  2. boukensha_path / boukensha_dir in ~/.boukensharc
  3. The bundled package / ~/.boukensha default

~/.boukensharc is YAML:
  boukensha_path: ~/Sites/boukensha/10_standard_tool_library
  boukensha_dir: ~/projects/mybot/.boukensha
A bare single-line path (the pre-step-9 format) is still accepted and is
treated as boukensha_path.

Examples:
  boukensha                                                    # uses bundled package + ~/.boukensha
  BOUKENSHA_PATH=~/Sites/boukensha/04_api_client boukensha      # loads step 4
  BOUKENSHA_DIR=~/projects/mybot/.boukensha boukensha            # custom config dir
"""
import os
import sys
from pathlib import Path

import yaml

# This step's own directory (contains the bundled `boukensha` package).
BUNDLED_LIB = Path(__file__).resolve().parent


def rc_file() -> Path:
    return Path("~/.boukensharc").expanduser()


def load_rc():
    path = rc_file()
    if not path.exists():
        return {}

    try:
        parsed = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        sys.exit("boukensha: invalid YAML in {}: {}".format(path, e))

    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, str):
        # Backward compatibility with the original single-path format.
        return {"boukensha_path": parsed}
    if parsed is None:
        return {}
    sys.exit("boukensha: {} must contain a YAML mapping".format(path))


def expand_rc_path(path):
    if not isinstance(path, str):
        return None
    if not path.strip():
        return None

    expanded = Path(path).expanduser()
    if not expanded.is_absolute():
        expanded = rc_file().parent / expanded
    return str(expanded.resolve())


def resolve() -> Path:
    rc = load_rc()

    # Apply this before importing the selected implementation. An explicit
    # environment variable always wins over the rc file.
    rc_config_dir = expand_rc_path(rc.get("boukensha_dir"))
    if not os.environ.get("BOUKENSHA_DIR") and rc_config_dir:
        os.environ["BOUKENSHA_DIR"] = rc_config_dir

    source = os.environ.get("BOUKENSHA_PATH") or expand_rc_path(rc.get("boukensha_path"))
    if not source:
        return BUNDLED_LIB

    step_dir = Path(source).expanduser().resolve()
    if (step_dir / "boukensha" / "__init__.py").exists():
        return step_dir

    sys.exit(
        "boukensha: no boukensha package found at:\n"
        "       {}\n"
        "       Check BOUKENSHA_PATH or {}.".format(step_dir, rc_file())
    )


def load_and_start_repl() -> None:
    step_dir = resolve()

    if os.environ.get("BOUKENSHA_DEBUG"):
        print("[boukensha] loading from: {}".format(step_dir))

    # Prepend the resolved step directory and drop any previously-imported
    # boukensha (or boukensha.*) module so the fresh import comes from here,
    # not from whatever was already on sys.path/cached in sys.modules.
    sys.path.insert(0, str(step_dir))
    for name in list(sys.modules):
        if name == "boukensha" or name.startswith("boukensha."):
            del sys.modules[name]

    import boukensha

    if not hasattr(boukensha, "start_repl"):
        sys.exit(
            "boukensha: the step at {}\n"
            "       does not support the interactive REPL (added in step 7).\n"
            "       Run its examples directly, e.g.:\n"
            "         python {}/examples/example.py\n"
            "       Or point BOUKENSHA_PATH at step 7 or later.".format(step_dir, step_dir)
        )

    # Nothing to pass: the agent's tools all come from settings.yaml's
    # `mcp_servers:` block, so there is no MUD -- or any other tool -- to
    # configure here.
    boukensha.start_repl()


def main() -> None:
    load_and_start_repl()


if __name__ == "__main__":
    main()
