from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from pydantic import Field

from sgr_agent_core.agent_definition import AgentConfig
from sgr_agent_core.base_tool import BaseTool

from .file_filters import (
    MAX_DIRECTORY_ITEMS,
    filter_paths,
)

if TYPE_CHECKING:
    from sgr_agent_core.models import AgentContext

logger = logging.getLogger(__name__)


class ListDirectoryTool(BaseTool):
    """List files and directories in a given path. Use this tool to explore
    directory structure and discover available files.

    Usage:
        - Provide directory path to list contents (or omit to list current directory)
        - Returns files and subdirectories
        - Use to navigate and understand project structure
        - Can list current working directory when path is not specified
    """

    reasoning: str = Field(description="Why you need to list this directory and what you're looking for")
    directory_path: Optional[str] = Field(
        default=None,
        description=(
            "Path to directory to list (absolute or relative). " "If not specified, lists current working directory."
        ),
    )
    recursive: bool = Field(default=False, description="List subdirectories recursively")

    async def __call__(self, context: AgentContext, config: AgentConfig, **kwargs) -> str:
        """List directory contents."""

        # Use current directory if path is not specified
        if self.directory_path is None:
            dir_path = Path.cwd()
            display_path = str(dir_path.absolute())
            logger.info(f"📁 Listing current directory: {display_path}")
        else:
            dir_path = Path(self.directory_path)
            display_path = self.directory_path
            logger.info(f"📁 Listing directory: {display_path}")

        try:
            if not dir_path.exists():
                return f"Error: Directory not found: {display_path}"

            if not dir_path.is_dir():
                return f"Error: Path is not a directory: {display_path}"

            result = f"Directory: {display_path}\n\n"

            # Add current directory context if listing current directory
            if self.directory_path is None:
                result += f"Absolute path: {dir_path.absolute()}\n"
                result += f"Directory name: {dir_path.name}\n"
                if dir_path.parent != dir_path:
                    result += f"Parent directory: {dir_path.parent}\n"
                result += "\n"

            if self.recursive:
                items = sorted(dir_path.rglob("*"))
                result += "Contents (recursive, filtered):\n"
            else:
                items = sorted(dir_path.iterdir())
                result += "Contents (filtered):\n"

            # Filter out ignored directories and files
            items = filter_paths(items)

            # Limit results
            if len(items) > MAX_DIRECTORY_ITEMS:
                result += f"Note: Showing first {MAX_DIRECTORY_ITEMS} of {len(items)} items\n\n"
                items = items[:MAX_DIRECTORY_ITEMS]

            dirs = []
            files = []

            for item in items:
                relative_path = item.relative_to(dir_path) if self.recursive else item.name
                if item.is_dir():
                    dirs.append(f"📁 {relative_path}/")
                else:
                    size = item.stat().st_size
                    files.append(f"📄 {relative_path} ({size} bytes)")

            if dirs:
                result += "\nDirectories:\n" + "\n".join(dirs) + "\n"
            if files:
                result += "\nFiles:\n" + "\n".join(files) + "\n"

            result += f"\nTotal: {len(dirs)} directories, {len(files)} files"

            logger.debug(f"Listed {len(items)} items in {display_path}")
            return result

        except Exception as e:
            logger.error(f"Error listing directory {display_path}: {e}")
            return f"Error listing directory: {str(e)}"
