require_relative "helper"
require "json"

# MudManager::JsonlLog in isolation: one JSONL line per #write call, correct
# fields, and safe to call with a nil path (logging disabled).
class TestJsonlLog < Minitest::Test
  def setup
    @dir = Dir.mktmpdir
    @path = File.join(@dir, "mud_manager.jsonl")
  end

  def teardown
    FileUtils.remove_entry(@dir)
  end

  def test_write_appends_one_line_with_a_timestamp
    log = MudManager::JsonlLog.new(@path)
    log.write(tool: "look", verb: "look", response: "A room")
    log.write(tool: "move", verb: "north", response: "You walk north.")

    lines = File.readlines(@path)
    assert_equal 2, lines.size

    first = JSON.parse(lines[0])
    assert_equal "look", first["tool"]
    assert_equal "A room", first["response"]
    refute_nil first["at"]
  end

  def test_write_creates_missing_parent_directories
    nested = File.join(@dir, "a", "b", "mud_manager.jsonl")
    log = MudManager::JsonlLog.new(nested)
    log.write(tool: "look")

    assert File.exist?(nested)
  end

  def test_nil_path_is_a_silent_no_op
    log = MudManager::JsonlLog.new(nil)
    log.write(tool: "look") # must not raise
  end
end

# bin/mud-manager's call_tool, exercised end-to-end against a FakeMud --
# asserts it logs exactly once per successful call and once more on each
# rescue path (see docs/plans/capable/logging_monitor.md Design 4 /
# Testing item 3).
class TestCallToolLogging < Minitest::Test
  MUD_MANAGER_BIN = File.expand_path("../bin/mud-manager", __dir__)

  def setup
    @fake = MudManager::FakeMud.new
    @dir = Dir.mktmpdir
    ENV["MUD_HOST"] = "127.0.0.1"
    ENV["MUD_PORT"] = @fake.port.to_s
    ENV["MUD_NAME"] = MudManager::FakeMud::DEFAULT_USERNAME
    ENV["MUD_PASSWORD"] = MudManager::FakeMud::DEFAULT_PASSWORD
    ENV["MUD_MANAGER_LOG_DIR"] = @dir

    load MUD_MANAGER_BIN unless defined?(MudManagerMcp) # constants only defined once; re-loading warns
    MudManagerMcp.instance_variable_set(:@session, nil)
    MudManagerMcp.instance_variable_set(:@mud_log, nil)
  end

  def teardown
    @fake&.stop
    FileUtils.remove_entry(@dir)
  end

  def log_entries
    path = File.join(@dir, "mud_manager.jsonl")
    return [] unless File.exist?(path)

    File.readlines(path).map { |l| JSON.parse(l) }
  end

  def test_successful_call_logs_exactly_once_with_timing
    result = MudManagerMcp.call_tool("look", {})
    refute result[:is_error]

    entries = log_entries
    assert_equal 1, entries.size
    assert_equal "look", entries[0]["tool"]
    assert_equal "look", entries[0]["verb"]
    refute_nil entries[0]["duration_ms"]
    refute entries[0].key?("error_class")
  end

  def test_argument_error_rescue_path_logs_once_with_error_detail
    result = MudManagerMcp.call_tool("move", { "direction" => "not_a_real_direction" })
    assert result[:is_error]
    assert_match(/argument_error/, result[:text])

    entries = log_entries
    assert_equal 1, entries.size
    assert_equal "ArgumentError", entries[0]["error_class"]
    refute_nil entries[0]["backtrace"]
  end

  def test_unknown_tool_does_not_reach_the_session_and_logs_nothing
    result = MudManagerMcp.call_tool("not_a_real_tool", {})
    assert result[:is_error]
    assert_match(/unknown_tool/, result[:text])
    assert_equal [], log_entries
  end
end
