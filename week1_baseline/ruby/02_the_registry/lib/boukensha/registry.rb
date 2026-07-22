require_relative "tool"
require_relative "errors"

module Boukensha
  class Registry
    def initialize(context)
      @context = context
    end

    def tool(name, description:, parameters: {}, &block)
      @context.register_tool(Tool.new(name, description, parameters, block))
    end

    def dispatch(name, args = {})
      tool = @context.tools[name]
      raise UnknownToolError, "No tool registered as '#{name}'" unless tool

      symbol_args = args.transform_keys(&:to_sym)
      tool.block.call(**symbol_args)
    end
  end
end
