"""Test script for MCP agent integration"""
from agents.orchestrator import OrchestratorAgent
from loguru import logger
import sys

# Configure logger for console output
logger.remove()
logger.add(sys.stderr, level="INFO")

def test_mcp_integration():
    """Test MCP agent registration and basic functionality"""

    logger.info("=" * 60)
    logger.info("Starting MCP Integration Test")
    logger.info("=" * 60)

    # Initialize orchestrator
    logger.info("\n1. Initializing OrchestratorAgent...")
    orchestrator = OrchestratorAgent()

    # Check registered agents
    from core.agent_registry import agent_registry
    logger.info("\n2. Checking registered agents:")
    for name, config in agent_registry._agents.items():
        logger.info(f"   - {name}: enabled={config.enabled}, priority={config.priority}")

    # Check available tools
    logger.info("\n3. Checking available tools:")
    tools = orchestrator.tools
    for tool in tools:
        logger.info(f"   - {tool.name}: {tool.description[:80]}...")

    # Test simple query (should not use MCP)
    logger.info("\n4. Testing simple query (no tool needed):")
    response = orchestrator.process_message("Привет!", thread_id="test_thread_1")
    logger.info(f"   Response: {response[:100]}...")

    # Test MCP query
    logger.info("\n5. Testing MCP query (should use mcp_tools):")
    response = orchestrator.process_message(
        "Покажи проекты Александры Бирило",
        thread_id="test_thread_2"
    )
    logger.info(f"   Response: {response[:200]}...")

    logger.info("\n" + "=" * 60)
    logger.info("MCP Integration Test Completed")
    logger.info("=" * 60)

if __name__ == "__main__":
    test_mcp_integration()
