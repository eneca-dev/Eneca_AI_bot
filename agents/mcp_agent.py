"""MCP Agent for project management via external MCP server"""
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import httpx
from agents.base import BaseAgent
from core.config import settings
from loguru import logger


class MCPAgent(BaseAgent):
    """Agent for interacting with MCP server via JSON-RPC 2.0"""

    # Request timeout in seconds
    REQUEST_TIMEOUT = 30.0

    def __init__(
        self,
        model: str = None,
        temperature: float = None,
        mcp_url: str = None
    ):
        """
        Initialize MCP agent

        Args:
            model: OpenAI model name (defaults to orchestrator model)
            temperature: Response temperature (defaults to 0.3 for precise tool selection)
            mcp_url: MCP server URL
        """
        model = model or settings.orchestrator_model
        temperature = temperature if temperature is not None else 0.3

        super().__init__(model=model, temperature=temperature)

        self.mcp_url = mcp_url or settings.mcp_server_url
        self._request_id = 0
        self._tools_cache: Optional[List[Dict]] = None

        logger.info(f"MCPAgent initialized with model {model}, MCP URL: {self.mcp_url}")

    def _get_default_prompt(self) -> str:
        """Load system prompt from prompts/mcp_agent.md"""
        prompt_path = Path(__file__).parent.parent / "prompts" / "mcp_agent.md"

        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt = f.read()
            logger.debug(f"Loaded MCP agent prompt from {prompt_path}")
            return prompt
        except FileNotFoundError:
            logger.warning(f"Prompt file not found at {prompt_path}, using default")
            return (
                "Ты - агент для управления проектами через MCP сервер. "
                "Твоя задача - определить нужный инструмент и его параметры "
                "на основе запроса пользователя."
            )

    def _get_next_request_id(self) -> int:
        """Get next JSON-RPC request ID"""
        self._request_id += 1
        return self._request_id

    def _make_jsonrpc_request(
        self,
        method: str,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Make JSON-RPC 2.0 request to MCP server

        Args:
            method: JSON-RPC method name
            params: Method parameters

        Returns:
            Response dict with 'result' or 'error'
        """
        payload = {
            "jsonrpc": "2.0",
            "id": self._get_next_request_id(),
            "method": method,
            "params": params or {}
        }

        try:
            with httpx.Client(timeout=self.REQUEST_TIMEOUT) as client:
                response = client.post(
                    self.mcp_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                return response.json()

        except httpx.TimeoutException:
            logger.error(f"Timeout calling MCP server: {method}")
            return {
                "error": {
                    "code": -32000,
                    "message": "Превышено время ожидания ответа от сервера"
                }
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from MCP server: {e}")
            return {
                "error": {
                    "code": -32001,
                    "message": f"Ошибка HTTP: {e.response.status_code}"
                }
            }
        except Exception as e:
            logger.error(f"Error calling MCP server: {e}")
            return {
                "error": {
                    "code": -32002,
                    "message": f"Ошибка соединения: {str(e)}"
                }
            }

    def get_available_tools(self) -> List[Dict]:
        """
        Get list of available tools from MCP server

        Returns:
            List of tool definitions with name, description, inputSchema
        """
        if self._tools_cache is not None:
            return self._tools_cache

        response = self._make_jsonrpc_request("tools/list")

        if "error" in response:
            logger.error(f"Error getting tools list: {response['error']}")
            return []

        tools = response.get("result", {}).get("tools", [])
        self._tools_cache = tools
        logger.info(f"Loaded {len(tools)} tools from MCP server")
        return tools

    def _call_mcp_tool(self, tool_name: str, arguments: Dict) -> Dict:
        """
        Call specific MCP tool

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool response or error
        """
        logger.info(f"Calling MCP tool: {tool_name} with args: {arguments}")

        response = self._make_jsonrpc_request(
            "tools/call",
            {"name": tool_name, "arguments": arguments}
        )

        if "error" in response:
            logger.error(f"MCP tool error: {response['error']}")
        else:
            logger.info(f"MCP tool {tool_name} completed successfully")

        return response

    def _build_tools_description(self) -> str:
        """Build tools description for LLM prompt"""
        tools = self.get_available_tools()

        if not tools:
            return "Нет доступных инструментов."

        description = "Доступные инструменты MCP:\n\n"

        for tool in tools:
            name = tool.get("name", "unknown")
            desc = tool.get("description", "Без описания")
            schema = tool.get("inputSchema", {})
            properties = schema.get("properties", {})
            required = schema.get("required", [])

            description += f"### {name}\n"
            description += f"{desc}\n"

            if properties:
                description += "Параметры:\n"
                for prop_name, prop_info in properties.items():
                    prop_type = prop_info.get("type", "any")
                    prop_desc = prop_info.get("description", "")
                    is_required = "(обязательный)" if prop_name in required else "(опционально)"
                    description += f"  - {prop_name} ({prop_type}) {is_required}: {prop_desc}\n"

            description += "\n"

        return description

    def _parse_tool_call(self, user_message: str) -> Optional[Dict]:
        """
        Use LLM to parse user message into tool call

        Args:
            user_message: User's natural language request

        Returns:
            Dict with 'tool_name' and 'arguments' or None if can't parse
        """
        tools_description = self._build_tools_description()

        parse_prompt = f"""Ты - помощник для парсинга запросов пользователя в вызовы MCP инструментов.

{tools_description}

Проанализируй запрос пользователя и определи:
1. Какой инструмент нужно вызвать
2. Какие аргументы передать

ВАЖНО:
- Выбери ОДИН наиболее подходящий инструмент
- Извлеки все параметры из запроса пользователя
- Если параметр не указан явно, НЕ добавляй его
- Если запрос непонятен или не подходит ни под один инструмент, верни null

Запрос пользователя: {user_message}

Ответь ТОЛЬКО в формате JSON без markdown:
{{"tool_name": "название_инструмента", "arguments": {{"param1": "value1"}}}}

Или если запрос не подходит:
null
"""

        try:
            response = self.invoke(parse_prompt)
            response = response.strip()

            # Clean up potential markdown formatting
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
                response = response.strip()

            if response.lower() == "null" or response == "":
                return None

            result = json.loads(response)

            if not isinstance(result, dict):
                return None

            if "tool_name" not in result:
                return None

            return result

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing tool call: {e}")
            return None

    def _format_response(self, mcp_response: Dict, tool_name: str) -> str:
        """
        Format MCP response for user

        Args:
            mcp_response: Raw MCP response
            tool_name: Name of the called tool

        Returns:
            Formatted Russian response
        """
        if "error" in mcp_response:
            error = mcp_response["error"]
            error_message = error.get("message", "Неизвестная ошибка")
            return f"Ошибка при выполнении операции: {error_message}"

        result = mcp_response.get("result", {})

        # Handle different result types
        if isinstance(result, str):
            return result

        if isinstance(result, dict):
            # Check for content array (common MCP pattern)
            content = result.get("content", [])
            if content and isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                if text_parts:
                    return "\n".join(text_parts)

            # Check for data field
            if "data" in result:
                return self._format_data(result["data"], tool_name)

            # Return raw result as formatted JSON
            return f"Результат операции {tool_name}:\n```json\n{json.dumps(result, ensure_ascii=False, indent=2)}\n```"

        if isinstance(result, list):
            return self._format_list(result, tool_name)

        return f"Операция {tool_name} выполнена успешно."

    def _format_data(self, data: Any, tool_name: str) -> str:
        """Format data field from MCP response"""
        if isinstance(data, list):
            return self._format_list(data, tool_name)
        elif isinstance(data, dict):
            return f"```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```"
        else:
            return str(data)

    def _format_list(self, items: List, tool_name: str) -> str:
        """Format list of items from MCP response"""
        if not items:
            return "Ничего не найдено."

        result = f"Найдено элементов: {len(items)}\n\n"

        for i, item in enumerate(items, 1):
            if isinstance(item, dict):
                name = item.get("name") or item.get("title") or item.get("id", f"#{i}")
                result += f"{i}. **{name}**\n"

                # Add relevant fields
                for key, value in item.items():
                    if key not in ["name", "title", "id"] and value:
                        if isinstance(value, (str, int, float, bool)):
                            result += f"   - {key}: {value}\n"
            else:
                result += f"{i}. {item}\n"

            result += "\n"

        return result.strip()

    def process_message(self, user_message: str) -> str:
        """
        Process user message and execute MCP tool

        Args:
            user_message: User's natural language request

        Returns:
            Formatted response
        """
        logger.info(f"MCPAgent processing message: {user_message[:100]}...")

        # Parse user request into tool call
        tool_call = self._parse_tool_call(user_message)

        if tool_call is None:
            logger.warning("Could not parse user request into MCP tool call")
            return (
                "Не удалось определить нужную операцию. "
                "Пожалуйста, уточните запрос. Например:\n"
                "- 'Покажи все проекты'\n"
                "- 'Найди сотрудника Иванов'\n"
                "- 'Создай проект Тест'"
            )

        tool_name = tool_call.get("tool_name")
        arguments = tool_call.get("arguments", {})

        logger.info(f"Parsed tool call: {tool_name} with {arguments}")

        # Call MCP tool
        mcp_response = self._call_mcp_tool(tool_name, arguments)

        # Format and return response
        return self._format_response(mcp_response, tool_name)

    def answer_question(self, question: str) -> str:
        """
        Alias for process_message (for compatibility with agent registry)

        Args:
            question: User's question/request

        Returns:
            Formatted response
        """
        return self.process_message(question)
