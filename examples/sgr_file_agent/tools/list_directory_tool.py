from __future__ import annotations

import logging
import os
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
            "Path to directory to list (absolute or relative). If not specified, lists current working directory."
        ),
    )
    recursive: bool = Field(default=False, description="List subdirectories recursively")

    async def __call__(self, context: AgentContext, config: AgentConfig, **kwargs) -> str:
        """List directory contents."""

        # Convert to Path object and use current directory if path is not specified
        directory_path = Path(self.directory_path) if self.directory_path else Path.cwd()

        if not directory_path.exists():
            return f"Error: Directory not found: {directory_path}"

        if not directory_path.is_dir():
            return f"Error: Path is not a directory: {directory_path}"

        if not os.access(directory_path, os.R_OK):
            return f"Error: Cannot access directory {directory_path}: Permission denied"

        result = f"Directory: {directory_path}\n\n"

        # Add current directory context if listing current directory
        if self.directory_path is None:
            result += f"Absolute path: {directory_path.absolute()}\n"
            result += f"Directory name: {directory_path.name}\n"
            result += "\n"

        # Get directory items
        if self.recursive:
            items = sorted(directory_path.rglob("*"))
            result += "Contents (recursive, filtered):\n"
        else:
            items = sorted(directory_path.iterdir())
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
            try:
                if self.recursive:
                    relative_path = item.relative_to(directory_path)
                else:
                    relative_path = item.name

                if item.is_dir():
                    dirs.append(f"📁 {relative_path}/")
                else:
                    try:
                        size = item.stat().st_size
                        files.append(f"📄 {relative_path} ({size} bytes)")
                    except (OSError, PermissionError):
                        # Skip files that cannot be accessed
                        files.append(f"📄 {relative_path} (size unknown)")
            except ValueError:
                # Skip items that cannot be relativized (shouldn't happen, but just in case)
                logger.warning(f"Cannot get relative path for {item}")
                continue

        if dirs:
            result += "\nDirectories:\n" + "\n".join(dirs) + "\n"
        if files:
            result += "\nFiles:\n" + "\n".join(files) + "\n"

        result += f"\nTotal: {len(dirs)} directories, {len(files)} files"

        logger.debug(f"Listed {len(items)} items in {directory_path}")
        return result
