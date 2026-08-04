require "socket"

module MudManager
  # A minimal fake CircleMUD server for offline testing: no real game state,
  # just enough of the telnet/login surface for MudManager::Session#login to
  # succeed, followed by a trivial echo ("You do: <line>") for everything a
  # session sends afterward. This is what lets bin/mud-manager (and its test
  # suite) be exercised without a real MUD to connect to.
  class FakeMud
    DEFAULT_USERNAME = "Gandalf".freeze
    DEFAULT_PASSWORD = "secret".freeze

    # Canned `look` text keyed by room vnum, for exercising `teleport`
    # end-to-end offline (see week3_capable/bin/reset's dry test). Any vnum
    # not listed here falls back to a generic description.
    ROOM_DESCRIPTIONS = Hash.new("A featureless void.").merge(
      "3001" => "The Temple Of Midgaard\r\nA huge open area with roads leading in all directions.",
    ).freeze

    def initialize(username: nil, password: nil, accounts: nil)
      @accounts = accounts || {(username || DEFAULT_USERNAME) => (password || DEFAULT_PASSWORD)}
      @rooms     = Hash.new("0") # username -> room vnum, shared across sessions
      @rooms_mu  = Mutex.new
      @active    = {} # username -> socket currently logged in as that name
      @active_mu = Mutex.new
      @server = TCPServer.new("127.0.0.1", 0)
      @threads = []
      @accept_thread = Thread.new { accept_loop }
      @accept_thread.report_on_exception = false
    end

    def port
      @server.addr[1]
    end

    def stop
      @accept_thread&.kill
      @server&.close
      @threads.each { |t| t.kill }
    rescue StandardError
      # best-effort cleanup
    end

    private

    def accept_loop
      loop do
        socket = @server.accept
        thread = Thread.new(socket) { |sock| handle_client(sock) }
        thread.report_on_exception = false
        @threads << thread
      end
    rescue IOError, Errno::EBADF
      # server closed — exit cleanly
    end

    def handle_client(sock)
      sock.write("By what name do you wish to be known? ")
      raw_name = sock.gets
      return if raw_name.nil?
      name = raw_name.strip

      sock.write("\r\nPassword: ")
      password = sock.gets&.strip

      if @accounts[name] == password
        # A second login for a name that's already connected kicks the old
        # connection, same as real CircleMUD's "already in use" takeover --
        # this is what lets an offline test exercise the same
        # already-connected/hijack path MudManager::Session#login and
        # week3_capable/bin/reset's login() both watch for.
        previous = @active_mu.synchronize { @active[name] }
        if previous
          begin
            previous.write("\r\nYou take over your own body, already in use!\r\n")
            previous.close
          rescue IOError, Errno::ECONNRESET, Errno::EPIPE
            # already gone — fine
          end
          sock.write("\r\nReconnecting. You take over your own body, already in use!\r\nYou materialize in the fake MUD.\r\n> ")
        else
          sock.write("\r\nWelcome, #{name}.\r\n")
          sock.gets # blank line: <return> at the main menu
          sock.gets # "1": enter the game
          sock.write("\r\nYou materialize in the fake MUD.\r\n> ")
        end
        @active_mu.synchronize { @active[name] = sock }
        echo_loop(sock, name)
      else
        sock.write("\r\nWrong password.\r\n")
      end
    rescue IOError, Errno::ECONNRESET, Errno::EPIPE
      # client disconnected — nothing to clean up beyond closing the socket
    ensure
      @active_mu.synchronize { @active.delete(name) if name && @active[name].equal?(sock) }
      sock.close rescue nil
    end

    def echo_loop(sock, name)
      loop do
        line = sock.gets
        break if line.nil?
        line = line.strip

        case line
        when /\Ateleport\s+(\S+)\s+(\S+)/i
          target, room = $1, $2
          @rooms_mu.synchronize { @rooms[target] = room }
          sock.write("Okay.\r\n> ")
        when /\Alook/i
          room = @rooms_mu.synchronize { @rooms[name] }
          sock.write("\r\n#{ROOM_DESCRIPTIONS[room]}\r\n> ")
        else
          sock.write("You do: #{line}\r\n> ")
        end
      end
    end
  end
end
