import os
from pathlib import Path

from boukensha import (
    Agent,
    Anthropic,
    Client,
    Config,
    Context,
    Gemini,
    Logger,
    Ollama,
    OllamaCloud,
    OpenAI,
    Player,
    PromptBuilder,
    Registry,
)
from boukensha.config import PROMPTS_DIR

os.environ.setdefault(
    "BOUKENSHA_DIR", str((Path(__file__).resolve().parent.parent.parent.parent.parent / ".boukensha"))
)

config = Config()
player_settings = config.tasks("player")
system_prompt = Player.system_prompt(
    player_settings,
    user_prompts_dir=config.user_prompts_dir,
    default_prompts_dir=PROMPTS_DIR,
)
base_dir = Path(__file__).resolve().parent.parent

ctx = Context(task=Player, system=system_prompt)
registry = Registry(ctx)

provider = Player.provider(player_settings)
model = Player.model(player_settings)

if provider == "anthropic":
    backend = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], model=model)
elif provider == "openai":
    backend = OpenAI(api_key=os.environ["OPENAI_API_KEY"], model=model)
elif provider == "gemini":
    backend = Gemini(api_key=os.environ["GEMINI_API_KEY"], model=model)
elif provider == "ollama":
    backend = Ollama(model=model)
elif provider == "ollama_cloud":
    backend = OllamaCloud(api_key=os.environ["OLLAMA_API_KEY"], model=model)
else:
    raise ValueError("Unsupported provider for player task: {}".format(provider))

builder = PromptBuilder(ctx, backend)
client = Client(builder)
# Writes structured JSONL events to .boukensha/sessions/<session-id>.jsonl.
# Call boukensha.debug() to include the full raw API response in those lines.
logger = Logger()
agent = Agent(
    context=ctx,
    registry=registry,
    builder=builder,
    client=client,
    logger=logger,
    task_settings=player_settings,
)

registry.tool(
    "read_file",
    description="Read the contents of a file from disk",
    parameters={"path": {"type": "string", "description": "The file path to read"}},
    block=lambda *, path: (base_dir / path).read_text(),
)

registry.tool(
    "list_directory",
    description="List the files in a directory",
    parameters={"path": {"type": "string", "description": "The directory path to list"}},
    block=lambda *, path: ", ".join(
        f for f in os.listdir(base_dir / path) if not f.startswith(".")
    ),
)

ctx.add_message(
    "user", "Read the README.md file and summarise what this MUD player assistant framework can do."
)

print("=== BOUKENSHA Step 6: The Logger ===")
print()
print("Config: {}".format(config))
print("Provider: {}".format(provider))
print("Model: {}".format(model))
print("Max iterations: {}".format(Player.max_iterations(player_settings)))
print("Max output tokens: {}".format(Player.max_output_tokens(player_settings)))
print()

result = agent.run()

print()
print("=== FINAL RESPONSE ===")
print(result)
