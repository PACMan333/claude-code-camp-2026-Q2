import os
from pathlib import Path

from boukensha import Config, Context, Player, Registry, UnknownToolError

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
registry = Registry(ctx)

registry.tool(
    "move",
    description="Move the player in a direction (north, south, east, west, up, down)",
    parameters={"direction": {"type": "string"}},
    block=lambda *, direction: "You move {} into a torch-lit corridor.".format(direction),
)

registry.tool(
    "shout",
    description="Shout a message so everyone in the zone can hear it",
    parameters={"message": {"type": "string"}},
    block=lambda *, message: message.upper(),
)

print("=== BOUKENSHA Step 2: Tool Registry ===")
print()
print("Config:  {}".format(config))
print("Context: {}".format(ctx))
print("Tools:")
for t in ctx.tools.values():
    print("  {}".format(t))
print()

print("Dispatching 'shout' with message='dragon spotted'...")
result = registry.dispatch("shout", {"message": "dragon spotted"})
print("Result: {}".format(result))
print()

print("Dispatching 'move' with direction='north'...")
result = registry.dispatch("move", {"direction": "north"})
print("Result: {}".format(result))
print()

try:
    registry.dispatch("flee")
except UnknownToolError as e:
    print("UnknownToolError caught: {}".format(e))
