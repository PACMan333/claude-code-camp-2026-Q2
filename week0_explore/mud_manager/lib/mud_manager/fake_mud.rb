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

    def initialize(username: DEFAULT_USERNAME, password: DEFAULT_PASSWORD)
      @username = username
      @password = password
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
      name = sock.gets
      return if name.nil?

      sock.write("\r\nPassword: ")
      password = sock.gets&.strip

      if password == @password
        sock.write("\r\nWelcome, #{name.strip}.\r\n")
        sock.gets # blank line: <return> at the main menu
        sock.gets # "1": enter the game
        sock.write("\r\nYou materialize in the fake MUD.\r\n> ")
        echo_loop(sock)
      else
        sock.write("\r\nWrong password.\r\n")
      end
    rescue IOError, Errno::ECONNRESET, Errno::EPIPE
      # client disconnected — nothing to clean up beyond closing the socket
    ensure
      sock.close rescue nil
    end

    def echo_loop(sock)
      loop do
        line = sock.gets
        break if line.nil?

        sock.write("You do: #{line.strip}\r\n> ")
      end
    end
  end
end
