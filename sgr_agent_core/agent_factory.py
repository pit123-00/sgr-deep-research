"""Agent Factory for dynamic agent creation from definitions."""

import logging
from typing import Type, TypeVar

import httpx
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from sgr_agent_core.agent_config import GlobalConfig
from sgr_agent_core.agent_definition import AgentDefinition, LLMConfig
from sgr_agent_core.base_agent import BaseAgent
from sgr_agent_core.base_tool import BaseTool
from sgr_agent_core.services import AgentRegistry, MCP2ToolConverter, ToolRegistry

logger = logging.getLogger(__name__)

Agent = TypeVar("Agent", bound=BaseAgent)


class AgentFactory:
    """Factory for creating agent instances from definitions.

    Use AgentRegistry and ToolRegistry to look up agent classes by name
    and create instances with the appropriate configuration.
    """

    @classmethod
    def _create_client(cls, llm_config: LLMConfig) -> AsyncOpenAI:
        """Create OpenAI client from configuration.

        Args:
            llm_config: LLM configuration

        Returns:
            Configured AsyncOpenAI client
        """
        client_kwargs = {"base_url": llm_config.base_url, "api_key": llm_config.api_key}
        if llm_config.proxy:
            client_kwargs["http_client"] = httpx.AsyncClient(proxy=llm_config.proxy)

        return AsyncOpenAI(**client_kwargs)

    @classmethod
    async def create(cls, agent_def: AgentDefinition, task_messages: list[ChatCompletionMessageParam]) -> Agent:
        """Create an agent instance from a definition.

        Args:
            agent_def: Agent definition with configuration (classes already resolved)
            task_messages: Task messages in OpenAI ChatCompletionMessageParam format

        Returns:
            Created agent instance

        Raises:
            ValueError: If agent creation fails
        """
        # Resolve base_class (can be string, ImportString, or class)
        BaseClass: Type[Agent] | None = None

        if isinstance(agent_def.base_class, str):
            # Try import string resolution first (for relative/absolute imports)
            if "." in agent_def.base_class:
                # Import string - resolve dynamically
                try:
                    module_parts = agent_def.base_class.split(".")
                    if len(module_parts) >= 2:
                        module_path = ".".join(module_parts[:-1])
                        class_name = module_parts[-1]
                        module = __import__(module_path, fromlist=[class_name])
                        BaseClass = getattr(module, class_name)
                        logger.debug(f"Imported agent class '{class_name}' from '{module_path}'")
                except (ImportError, AttributeError) as e:
                    logger.warning(
                        f"Failed to import agent '{agent_def.base_class}' from import string: {e}. "
                        f"Trying registry..."
                    )
                    # Fall through to try registry

            # If not resolved yet, try registry
            if BaseClass is None:
                BaseClass = AgentRegistry.get(agent_def.base_class)
        elif isinstance(agent_def.base_class, type):
            # Already a class
            BaseClass = agent_def.base_class

        if BaseClass is None:
            error_msg = (
                f"Agent base class '{agent_def.base_class}' not found.\n"
                f"Available base classes in registry: {', '.join([c.__name__ for c in AgentRegistry.list_items()])}\n"
                f"To fix this issue:\n"
                f"  - Check that '{agent_def.base_class}' is spelled correctly in your configuration\n"
                f"  - If using import string (e.g., 'sgr_file_agent.SGRFileAgent'), ensure the module is in sys.path\n"
                f"  - If using class name, ensure the custom agent classes are imported before creating agents "
                f"(otherwise they won't be registered)"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        mcp_tools: list = await MCP2ToolConverter.build_tools_from_mcp(agent_def.mcp)

        tools = [*mcp_tools]
        config = GlobalConfig()

        for tool_name in agent_def.tools:
            tool_class = None

            # If tool_name is already a class, use it directly
            if isinstance(tool_name, type):
                if not issubclass(tool_name, BaseTool):
                    raise TypeError(f"Tool class '{tool_name.__name__}' must be a subclass of BaseTool")
                tools.append(tool_name)
                continue

            # First, try to find tool in config.tools
            if tool_name in config.tools:
                tool_def = config.tools[tool_name]
                base_class = tool_def.base_class

                if base_class is None:
                    # Generate default path: sgr_agent_core.tools.{ToolName}
                    # Convert tool_name to ToolName (capitalize first letter, handle underscores)
                    tool_class_name = "".join(word.capitalize() for word in tool_name.split("_"))
                    base_class = f"sgr_agent_core.tools.{tool_class_name}"

                # Resolve base_class (can be string, ImportString, or class)
                if isinstance(base_class, str):
                    # Try import string resolution
                    if "." in base_class:
                        # Relative import - resolve relative to config file location
                        # This is handled by sys.path in agent_config.from_yaml
                        try:
                            module_parts = base_class.split(".")
                            if len(module_parts) >= 2:
                                module_path = ".".join(module_parts[:-1])
                                class_name = module_parts[-1]
                                module = __import__(module_path, fromlist=[class_name])
                                tool_class = getattr(module, class_name)
                        except (ImportError, AttributeError) as e:
                            logger.warning(
                                f"Failed to import tool '{tool_name}' from '{base_class}': {e}. " f"Trying registry..."
                            )
                    else:
                        # Try registry
                        tool_class = ToolRegistry.get(base_class)
                elif isinstance(base_class, type):
                    # Validate it's a BaseTool subclass
                    if not issubclass(base_class, BaseTool):
                        raise TypeError(f"Tool '{tool_name}' base_class must be a subclass of BaseTool")
                    tool_class = base_class
                else:
                    # ImportString - should be resolved by pydantic
                    tool_class = base_class
            else:
                # Tool not in config.tools, try registry
                tool_class = ToolRegistry.get(tool_name)

            # If still not found, try as import string
            if tool_class is None:
                if "." in tool_name:
                    try:
                        module_parts = tool_name.split(".")
                        if len(module_parts) >= 2:
                            module_path = ".".join(module_parts[:-1])
                            class_name = module_parts[-1]
                            module = __import__(module_path, fromlist=[class_name])
                            tool_class = getattr(module, class_name)
                    except (ImportError, AttributeError) as e:
                        error_msg = (
                            f"Tool '{tool_name}' not found in config.tools, registry, or failed to import.\n"
                            f"Available tools in config: {', '.join(config.tools.keys())}\n"
                            f"Available tools in registry: "
                            f"{', '.join([c.__name__ for c in ToolRegistry.list_items()])}\n"
                            f"Import error: {e}\n"
                            f"  - Check that the tool name is correct\n"
                            f"  - Define the tool in the 'tools' section of your config\n"
                            f"  - Or ensure the tool is registered in ToolRegistry"
                        )
                        logger.error(error_msg)
                        raise ValueError(error_msg) from e

            if tool_class is None:
                error_msg = (
                    f"Tool '{tool_name}' not found.\n"
                    f"Available tools in config: {', '.join(config.tools.keys())}\n"
                    f"Available tools in registry: {', '.join([c.__name__ for c in ToolRegistry.list_items()])}\n"
                    f"  - Define the tool in the 'tools' section of your config\n"
                    f"  - Or ensure the tool is registered in ToolRegistry"
                )
                logger.error(error_msg)
                raise ValueError(error_msg)

            tools.append(tool_class)

        try:
            # Extract agent-specific parameters from agent_def (e.g., working_directory)
            # These are fields that are not part of standard AgentConfig but are allowed via extra="allow"
            agent_kwargs = {}
            standard_fields = {"llm", "search", "execution", "prompts", "mcp", "name", "base_class", "tools"}
            for key, value in agent_def.model_dump().items():
                if key not in standard_fields:
                    agent_kwargs[key] = value

            agent = BaseClass(
                task_messages=task_messages,
                def_name=agent_def.name,
                toolkit=tools,
                openai_client=cls._create_client(agent_def.llm),
                agent_config=agent_def,
                **agent_kwargs,
            )
            logger.info(
                f"Created agent '{agent_def.name}' "
                f"using base class '{BaseClass.__name__}' "
                f"with {len(agent.toolkit)} tools"
            )
            return agent
        except Exception as e:
            logger.error(f"Failed to create agent '{agent_def.name}': {e}", exc_info=True)
            raise ValueError(f"Failed to create agent: {e}") from e

    @classmethod
    def get_definitions_list(cls) -> list[AgentDefinition]:
        """Get all agent definitions from config.

        Returns:
            List of agent definitions from config
        """
        config = GlobalConfig()
        return list(config.agents.values())
