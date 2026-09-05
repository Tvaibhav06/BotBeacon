import asyncio
import httpx

async def test():
    async with httpx.AsyncClient() as client:
        response = await client.post("http://localhost:8000/api/demo/buyer-request", json={"intent": "Buy the 8999 Velocity Pro Premium footwear"})
        async for line in response.aiter_lines():
            print(line)

asyncio.run(test())
