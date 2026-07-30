"""Memory tools — save and recall long-term memories and behavioral rules."""

import logging

logger = logging.getLogger(__name__)


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "recall_memory",
                "description": "Recall everything Raphael knows about the user from long-term memory. Returns all stored information across all categories.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "save_memory",
                "description": "Save a specific key-value fact about the user to long-term memory (e.g. name, preferences, project details).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "The category of memory (e.g., 'identity', 'preferences', 'daily_task_memory', 'feature_memory', 'notes').",
                        },
                        "key": {
                            "type": "string",
                            "description": "Unique key identifier for the fact.",
                        },
                        "value": {
                            "type": "string",
                            "description": "The value or details to remember.",
                        },
                    },
                    "required": ["category", "key", "value"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "learn_from_feedback",
                "description": "Save a behavioral rule or preference Raphael learned from the user (e.g. 'dont open browser for simple lookups', 'use bullet points for lists'). Call this when the user corrects your behavior or gives you a rule to follow. It persists across conversations.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "rule": {
                            "type": "string",
                            "description": "The specific behavioral rule or preference to remember.",
                        },
                        "condition": {
                            "type": "string",
                            "description": "When this rule applies (e.g. query pattern, context).",
                        },
                    },
                    "required": ["rule", "condition"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "flush_memory",
                "description": "Flush and clear all long-term memory categories (e.g. daily tasks, chat memories, capability memories, preferences) except for the core user_memory (which stores the user's name, profile, job, and location).",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_memory_entry",
                "description": "Delete a specific key-value entry from any memory category.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "The category of memory (e.g. 'daily_task_memory', 'chat_memory', 'feature_memory', 'user_memory').",
                        },
                        "key": {
                            "type": "string",
                            "description": "The unique key identifier for the fact to delete.",
                        },
                    },
                    "required": ["category", "key"],
                },
            },
        },
    ]


def save_memory(category: str, key: str, value: str) -> str:
    """Save a fact about the user to long-term memory."""
    from memory.memory_manager import remember
    return remember(key, value, category)


def recall_memory() -> str:
    """Retrieve everything Raphael knows from long-term memory."""
    from memory.memory_manager import format_memory_for_prompt, load_memory
    memory = load_memory()
    formatted = format_memory_for_prompt(memory)
    return formatted if formatted else "No long-term memories stored yet."


def learn_from_feedback(rule: str, condition: str) -> str:
    """
    Save a behavioral rule for Raphael based on user feedback.
    This ensures Raphael remembers the rule across conversations.
    """
    try:
        from memory.agent_memory import process_correction
        # Save as a correction for Raphael's evolution memory
        process_correction("raphael", condition, rule)
        return f"Learned: when '{condition}' -> {rule}"
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Failed to save feedback: %s", e)
        return f"Failed to save feedback: {e}"


def flush_memory() -> str:
    """Clear all long-term memory categories except 'user_memory'."""
    try:
        from memory.memory_manager import flush_all_except_user_memory
        return flush_all_except_user_memory()
    except Exception as e:
        logger.error("Failed to flush memory: %s", e)
        return f"Failed to flush memory: {e}"


def delete_memory_entry(category: str, key: str) -> str:
    """Delete a specific key-value entry from a memory category."""
    try:
        from memory.memory_manager import delete_memory_key
        return delete_memory_key(category, key)
    except Exception as e:
        logger.error("Failed to delete memory entry: %s", e)
        return f"Failed to delete memory entry: {e}"

