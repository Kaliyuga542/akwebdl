# health_server.py
"""
Simple aiohttp health server for Koyeb.
Use this endpoint with UptimeRobot to keep the app alive 24x7.
"""

import os
from aiohttp import web

# Port provided by Koyeb (defaults to 8000)
PORT = int(os.getenv("PORT", "8000"))

# Optional security token (so random people can’t ping it)
EXPECTED_TOKEN = os.getenv("HEALTH_TOKEN", "secret123")

async def health(request):
    token = request.query.get("token", "")
    if token != EXPECTED_TOKEN:
        return web.Response(text="Forbidden", status=403)
    return web.Response(text="ok", status=200)

async def start_server():
    app = web.Application()
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    print(f"✅ Health server running on 0.0.0.0:{PORT} — token required: {EXPECTED_TOKEN}")
    await site.start()

    # Keep alive forever
    import asyncio
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    import asyncio
    asyncio.run(start_server())
