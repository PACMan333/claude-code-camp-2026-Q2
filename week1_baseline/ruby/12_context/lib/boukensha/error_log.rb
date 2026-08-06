require "json"
require "fileutils"
require "time"

module Boukensha
  module ErrorLog
    ERROR_LOG_NAME = "errors.jsonl".freeze

    # Appends one durable, structured entry for `exc` to
    # <dir or Boukensha.config.dir>/errors.jsonl. Never raises -- a broken
    # error logger must not mask the original failure.
    def self.log_error(exc, where:, operation: nil, task: nil, session_id: nil, dir: nil)
      entry = {
        at: Time.now.iso8601(6),
        where: where,
        operation: operation,
        task: task,
        session_id: session_id,
        error_class: exc.class.name,
        error_message: exc.message,
        backtrace: exc.backtrace || []
      }
      root = dir || Boukensha.config.dir
      FileUtils.mkdir_p(root)
      File.open(File.join(root, ERROR_LOG_NAME), "a") { |f| f.puts JSON.generate(entry) }
    rescue StandardError
      nil # logging a failure must never itself raise
    end
  end
end
