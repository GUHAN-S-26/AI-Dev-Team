"""Safe function schemas exposed to implementation agents.

The model can suggest only these bounded operations.  The Tool Gateway remains
the authority that validates arguments, ownership, locks, and execution.
"""

from __future__ import annotations

from typing import Any


def tool_definitions(allowed_tools: list[str]) -> list[dict[str, Any]]:
    definitions: dict[str, dict[str, Any]] = {
        "read_file": {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read one authorized UTF-8 file in the agent worktree.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string", "minLength": 1, "maxLength": 500}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
        "list_directory": {
            "type": "function",
            "function": {
                "name": "list_directory",
                "description": "List one authorized directory in the agent worktree.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string", "minLength": 1, "maxLength": 500}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
        "create_file": {
            "type": "function",
            "function": {
                "name": "create_file",
                "description": "Create an authorized source or test file with bounded UTF-8 content.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "minLength": 1, "maxLength": 500},
                        "content": {"type": "string", "maxLength": 1000000},
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            },
        },
        "modify_file": {
            "type": "function",
            "function": {
                "name": "modify_file",
                "description": "Replace an authorized source or test file with bounded UTF-8 content.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "minLength": 1, "maxLength": 500},
                        "content": {"type": "string", "maxLength": 1000000},
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            },
        },
        "search_workspace": {
            "type": "function",
            "function": {
                "name": "search_workspace",
                "description": "Search text in authorized files in the agent worktree.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "minLength": 1, "maxLength": 500},
                        "query": {"type": "string", "minLength": 1, "maxLength": 200},
                    },
                    "required": ["path", "query"],
                    "additionalProperties": False,
                },
            },
        },
        "run_formatter": {
            "type": "function",
            "function": {
                "name": "run_formatter",
                "description": "Run the sandboxed Python syntax/format validation command.",
                "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            },
        },
        "run_tests": {
            "type": "function",
            "function": {
                "name": "run_tests",
                "description": "Run the sandboxed pytest suite in the agent worktree.",
                "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            },
        },
        "git_diff": {
            "type": "function",
            "function": {
                "name": "git_diff",
                "description": "Inspect the current worktree diff.",
                "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            },
        },
        "commit_changes": {
            "type": "function",
            "function": {
                "name": "commit_changes",
                "description": "Commit explicitly named authorized changed paths in the worktree.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "paths": {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1},
                        "message": {"type": "string", "minLength": 1, "maxLength": 500},
                    },
                    "required": ["paths", "message"],
                    "additionalProperties": False,
                },
            },
        },
    }
    return [definitions[name] for name in allowed_tools if name in definitions]
