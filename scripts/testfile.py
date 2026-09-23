# test_simple.py
import asyncio
from agentic_rag import agentic

async def main():
    result = await agentic("""can you please write code to say hello owais and run it""",port=53598,iterations=3)  # ← THAT'S IT!
    print(result)
asyncio.run(main())