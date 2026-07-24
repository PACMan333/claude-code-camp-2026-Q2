Gem::Specification.new do |spec|
  spec.name        = "mud_manager"
  spec.version     = "0.1.0"
  spec.summary     = "MudManager — CircleMUD session management and command primitives"
  spec.description = "Provides MudManager::Session (a long-lived telnet connection with " \
                     "background buffering and IAC stripping) and MudManager::Primitives " \
                     "(a stateless library of typed CircleMUD command builders)."
  spec.authors     = ["Andrew Brown"]
  spec.email       = ["andrew@exampro.co"]
  spec.license     = "MIT"

  spec.required_ruby_version = ">= 3.0"

  spec.files = Dir["lib/**/*.rb"] + ["bin/mud-manager"]

  # `mud-manager --mcp` is the cross-language interface: a long-lived MCP
  # server (stdio, JSON-RPC 2.0) that any language can spawn and drive. See
  # README.md ("The MCP interface"). Installing the gem puts `mud-manager`
  # on the PATH.
  spec.bindir      = "bin"
  spec.executables = ["mud-manager"]

  # No external dependencies — socket, thread, json, and open3 are stdlib.
end
