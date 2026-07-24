import os
from pathlib import Path

import boukensha

os.environ.setdefault(
    "BOUKENSHA_DIR", str((Path(__file__).resolve().parent.parent.parent.parent.parent / ".boukensha"))
)

# Config is loaded automatically inside boukensha.start_repl — system prompt,
# model, and API key all come from ~/.boukensha (or BOUKENSHA_DIR) by default.

print("Config: {}".format(boukensha.current_config()))
print()

# The base directory tools will operate relative to -- the step 7 folder makes
# a good playground since it already has source files to read.
base_dir = Path(__file__).resolve().parent.parent.parent / "07_the_run_dsl"


def register(dsl):
    dsl.tool(
        "read_file",
        description="Read the contents of a file from disk",
        parameters={"path": {"type": "string", "description": "File path (relative to the working directory)"}},
        block=lambda *, path: (base_dir / path).read_text(),
    )

    dsl.tool(
        "list_directory",
        description="List the files in a directory",
        parameters={"path": {"type": "string", "description": "Directory path (relative to the working directory, or '.' for root)"}},
        block=lambda *, path: ", ".join(
            sorted(f for f in os.listdir(base_dir / path) if not f.startswith("."))
        ),
    )


boukensha.start_repl(register_tools=register)
