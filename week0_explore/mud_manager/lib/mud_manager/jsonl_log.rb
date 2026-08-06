require "json"
require "fileutils"
require "time"

module MudManager
  # Minimal, dependency-free JSONL writer for the raw command log. Not a
  # shared import from boukensha -- mud_manager has no dependency on that
  # gem/package, so this is a small self-contained twin of the JSONL-line-
  # per-event shape Boukensha::Logger already uses.
  class JsonlLog
    def initialize(path)
      @path = path
      @mutex = Mutex.new
    end

    def write(event)
      return unless @path

      @mutex.synchronize do
        FileUtils.mkdir_p(File.dirname(@path))
        File.open(@path, "a") { |f| f.puts(event.merge(at: Time.now.iso8601(6)).to_json) }
      end
    end
  end
end
