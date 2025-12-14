"""
Test script to detect memory leak in MemoryManager

This script creates multiple MemoryManager instances to check if
SqliteSaver context managers are properly closed.
"""
import tracemalloc
import time
import sys
from loguru import logger

# Configure logger
logger.remove()
logger.add(sys.stderr, level="INFO")

def test_memory_leak():
    """Test for memory leaks in MemoryManager initialization"""

    # Start memory tracking
    tracemalloc.start()

    logger.info("=" * 60)
    logger.info("Memory Leak Detection Test")
    logger.info("=" * 60)

    logger.info("\nCreating 100 MemoryManager instances...")
    logger.info("(This simulates multiple bot restarts)\n")

    managers = []

    for i in range(100):
        from core.memory import MemoryManager
        manager = MemoryManager()
        managers.append(manager)

        if i % 10 == 0:
            current, peak = tracemalloc.get_traced_memory()
            logger.info(
                f"Iteration {i:3d}: "
                f"Current={current/1024/1024:6.1f}MB, "
                f"Peak={peak/1024/1024:6.1f}MB"
            )
            time.sleep(0.1)

    logger.info("\n" + "=" * 60)
    logger.info("Final Memory Snapshot")
    logger.info("=" * 60)

    current, peak = tracemalloc.get_traced_memory()
    logger.info(f"Current memory: {current/1024/1024:.1f} MB")
    logger.info(f"Peak memory:    {peak/1024/1024:.1f} MB")

    # Get top memory allocations
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics('lineno')

    logger.info("\n" + "=" * 60)
    logger.info("Top 10 Memory Allocations")
    logger.info("=" * 60)

    for i, stat in enumerate(top_stats[:10], 1):
        logger.info(f"{i}. {stat}")

    tracemalloc.stop()

    logger.info("\n" + "=" * 60)
    logger.info("Analysis")
    logger.info("=" * 60)

    if peak > 50 * 1024 * 1024:  # More than 50MB for 100 instances
        logger.warning("⚠️  POTENTIAL MEMORY LEAK DETECTED!")
        logger.warning(f"   Peak memory usage ({peak/1024/1024:.1f}MB) is unusually high")
        logger.warning("   Expected: <50MB for 100 MemoryManager instances")
    else:
        logger.success("✅ No obvious memory leak detected")
        logger.success(f"   Peak memory usage ({peak/1024/1024:.1f}MB) is within normal range")

    logger.info("\n" + "=" * 60)

if __name__ == "__main__":
    test_memory_leak()