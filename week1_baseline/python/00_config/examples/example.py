import os
from pathlib import Path

from boukensha import PROMPTS_DIR, Config, Player

# Override the config directory so the example works from the repo root.
# In real usage a user's ~/.boukensha is picked up automatically.
os.environ.setdefault(
    "BOUKENSHA_DIR", str((Path(__file__).resolve().parent.parent.parent.parent.parent / ".boukensha"))
)

config = Config()
player_settings = config.tasks("player")

print("=== Boukensha Step 0: Configuration ===")
print()
print("Config dir:     {}".format(config.dir))
print("Tasks:          {}".format(", ".join(config.tasks().keys())))
print()
print("-- player task --")
print("Provider:       {}".format(Player.provider(player_settings)))
print("Model:          {}".format(Player.model(player_settings)))
print("Prompt override?{}".format(Player.prompt_override(player_settings, "system")))
system_prompt = Player.system_prompt(
    player_settings,
    user_prompts_dir=config.user_prompts_dir,
    default_prompts_dir=PROMPTS_DIR,
)
print("System prompt:  {}...".format((system_prompt or "")[:60]))
print()
print("MUD host:       {}:{}".format(config.mud_host(), config.mud_port()))
print("MUD user:       {}".format(config.mud_username()))
print()
print("API key set?    {}".format(os.environ.get("ANTHROPIC_API_KEY") is not None))
print()
print(repr(config))
