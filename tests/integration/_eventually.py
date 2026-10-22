"""Wait for Hardcover's reads to catch up with a write.

Hardcover's reads can lag its writes by a few seconds, so a step that reads back what the
previous step wrote (or a tool that looks up the current state before writing) may see the
old state. Tests poll with ``eventually`` instead of asserting on the first read.
"""

import asyncio
from collections.abc import Awaitable, Callable


async def eventually[T](
    check: Callable[[], Awaitable[T]], *, timeout: float = 15.0, interval: float = 1.0
) -> T:
    """Await ``check()`` until it returns something truthy or ``timeout`` seconds pass.

    Returns the last result, so ``assert await eventually(...)`` fails with the stale value.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    result = await check()
    while not result and loop.time() < deadline:
        await asyncio.sleep(interval)
        result = await check()
    return result
