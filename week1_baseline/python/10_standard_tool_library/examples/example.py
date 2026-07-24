import os
from pathlib import Path

# Step 10 -- the agent owns no tools.
#
# There is no register_tools call here, because boukensha has nothing of its
# own to register. Every tool this agent can call arrives from an MCP server
# listed in settings.yaml's `mcp_servers:` block -- the MUD daemon, a
# filesystem server, anything that speaks MCP. Swapping what the agent can do
# is a config edit, not a code change.

os.environ.setdefault(
    "BOUKENSHA_DIR", str((Path(__file__).resolve().parent.parent.parent.parent.parent / ".boukensha"))
)

import boukensha  # noqa: E402

cfg = boukensha.current_config()
print("Config:  {}".format(cfg))
print("Servers: {}".format(", ".join(cfg.mcp_servers().keys())))
print("API key set? {}".format(os.environ.get("ANTHROPIC_API_KEY") is not None))
print()

boukensha.run(
    task="Look at your surroundings, check your score, "
         "then look at the available exits and tell me what you see."
    # system/model/api_key come from config automatically.
    # Tools come from mcp_servers -- there is nothing to wire up here.
)
