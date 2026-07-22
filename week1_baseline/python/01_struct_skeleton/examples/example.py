import os
from pathlib import Path

from boukensha import Config, Context, Player, Tool

os.environ.setdefault(
    "BOUKENSHA_DIR", str((Path(__file__).resolve().parent.parent.parent.parent.parent / ".boukensha"))
)

config = Config()
player_settings = config.tasks("player")
system_prompt = Player.system_prompt(
    player_settings,
    user_prompts_dir=config.user_prompts_dir,
)

ctx = Context(task=Player, system=system_prompt)

ctx.register_tool(
    Tool(
        "move",
        "Move the player in a direction (north, south, east, west, up, down)",
        {"direction": {"type": "string", "description": "The direction to move"}},
        lambda direction: "You move {} into a torch-lit corridor.".format(direction),
    )
)

ctx.add_message("user", "Explore north and tell me what you find.")
ctx.add_message("assistant", "Sure, let me head north and take a look.")

print("=== Boukensha Step 1: Struct Skeleton ===")
print()
print("Config:   {}".format(config))
print("Context:  {}".format(ctx))
print("Tool:     {}".format(ctx.tools["move"]))
print("Messages:")
for m in ctx.messages:
    print("  {}".format(m))
