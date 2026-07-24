import os
from pathlib import Path

import boukensha

os.environ.setdefault(
    "BOUKENSHA_DIR", str((Path(__file__).resolve().parent.parent.parent.parent.parent / ".boukensha"))
)

print("=== BOUKENSHA Step 7: The Boukensha.run DSL ===")
print()
print("Config: {}".format(boukensha.current_config()))
print()

base_dir = Path(__file__).resolve().parent.parent


def register(dsl):
    dsl.tool(
        "read_file",
        description="Read the contents of a file from disk",
        parameters={"path": {"type": "string", "description": "The file path to read"}},
        block=lambda *, path: (base_dir / path).read_text(),
    )

    dsl.tool(
        "list_directory",
        description="List the files in a directory",
        parameters={"path": {"type": "string", "description": "The directory path to list"}},
        block=lambda *, path: ", ".join(
            f for f in os.listdir(base_dir / path) if not f.startswith(".")
        ),
    )


result = boukensha.run(
    task="Read the README.md file and summarise what this MUD player assistant framework can do.",
    register_tools=register,
)

print()
print("=== FINAL RESPONSE ===")
print(result)
