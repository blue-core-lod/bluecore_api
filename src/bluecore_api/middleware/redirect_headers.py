from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class RedirectLocationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        if "location" in response.headers and not response.headers[
            "location"
        ].startswith("http://localhost"):
            response.headers["location"] = response.headers["location"].replace(
                "http://", "https://"
            )

        return response
