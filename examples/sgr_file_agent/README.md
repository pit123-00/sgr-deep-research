# SGR File Agent

File system agent for SGR Agent Core. This agent specializes in file search, reading, and analysis operations.

## Description

SGR File Agent is a specialized agent that works with the filesystem. It provides read-only operations for:

- Finding files by pattern, size, or modification date
- Reading file contents
- Listing directories
- Searching text within files
- Getting system paths and current directory

## Installation

Make sure you have `sgr-agent-core` installed:

```bash
pip install sgr-agent-core
```

## Configuration

1. Copy `config.yaml.example` and fill in your API keys:

```bash
cp config.yaml.example config.yaml
```

2. Edit `config.yaml` and set:
   - `llm.api_key` - Your OpenAI API key

## Usage

### Running the API Server

To run the SGR Agent Core API server with file agent:

```bash
sgr --config-file examples/sgr_file_agent/config.yaml
```

### Using Python API

```python
import asyncio
from pathlib import Path

from sgr_agent_core.agent_config import GlobalConfig
from sgr_agent_core.agent_factory import AgentFactory

# Load configuration
config_path = Path(__file__).parent / "config.yaml"
config = GlobalConfig.from_yaml(str(config_path))

# Get agent definition
agent_def = config.agents["sgr_file_agent"]


# Create and run agent
async def main():
    agent = await AgentFactory.create(
        agent_def, task="Find all Python files in the project"
    )

    # working_directory is automatically set from config if specified
    print(f"Working directory: {agent.working_directory}")

    async for chunk in agent.stream():
        print(chunk, end="", flush=True)

    result = await agent.execute()
    print(f"\n\nFinal result: {result}")


asyncio.run(main())
```

### Using OpenAI-compatible API

If you're running the SGR Agent Core API service:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8010/v1",
    api_key="dummy",
)

response = client.chat.completions.create(
    model="sgr_file_agent",
    messages=[
        {
            "role": "user",
            "content": "Find all PDF files in my Downloads folder from last week",
        }
    ],
    stream=True,
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

## Available Tools

The file agent includes the following tools:

### File System Tools

- **GetSystemPathsTool** - Get standard system paths (home, documents, downloads, desktop, etc.)
- **ListDirectoryTool** - List directory contents with recursive option (can list current directory when path is not specified)
- **ReadFileTool** - Read file contents with optional line range
- **SearchInFilesTool** - Search text/code within files (grep-like functionality)
- **FindFilesFastTool** - Universal file search using native find command (supports patterns, size, date filters)

### Core Tools

- **ReasoningTool** - Structured reasoning for planning
- **ClarificationTool** - Request clarifications from user
- **FinalAnswerTool** - Provide final answers

## Tool Configuration

Tools are configured in the `tools` section of `config.yaml`. Each tool has a name and optional `base_class`:

```yaml
tools:
  # Core tools (base_class defaults to sgr_agent_core.tools.*)
  reasoning_tool:
    # base_class defaults to sgr_agent_core.tools.ReasoningTool

  # Custom tools with relative imports (relative to config.yaml location)
  read_file_tool:
    base_class: "tools.ReadFileTool"  # Resolves to examples/sgr_file_agent/tools/ReadFileTool

  # Custom tools with absolute imports
  custom_tool:
    base_class: "examples.sgr_file_agent.tools.CustomTool"
```

### Tool Name to Class Name Mapping

If `base_class` is not specified, the system automatically generates:

- `reasoning_tool` → `sgr_agent_core.tools.ReasoningTool`
- `read_file_tool` → `sgr_agent_core.tools.ReadFileTool`
- `web_search_tool` → `sgr_agent_core.tools.WebSearchTool`

### Relative vs Absolute Imports

- **Relative imports** (e.g., `"tools.ReadFileTool"`): Resolved relative to the directory containing `config.yaml`
- **Absolute imports** (e.g., `"examples.sgr_file_agent.tools.ReadFileTool"`): Resolved from Python's sys.path

### Using Tools in Agents

In the `agents` section, reference tools by their names from the `tools` section:

```yaml
agents:
  sgr_file_agent:
    tools:
      - "reasoning_tool"
      - "read_file_tool"
      - "find_files_fast_tool"

    # Agent-specific parameters
    working_directory: "/path/to/work/dir"  # Optional: working directory for file operations
```

### Agent-Specific Parameters

SGR File Agent supports additional parameters that can be set in the config:

- **working_directory** (optional, default: `"."`): The working directory for file operations. Can be an absolute or relative path.

## Notes

- All file operations are read-only for security
- Automatic filtering excludes cache dirs, node_modules, .git, etc.
- Tools use native OS commands for optimal performance
- The agent doesn't use web search (max_searches: 0)
