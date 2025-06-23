###############################################################
##  Bypasses Keycloak authentication for specific GET paths  ##
###############################################################
class BypassKeycloakForGetPaths:
    # Add GET paths to bypass authentication
    ALLOWED_PATHS = {
        "/",
        "/api",
        "/docs",
        "/api/docs",
        "/openapi.json",
        "/api/openapi.json"
    }

    def __init__(self, app, keycloak_middleware):
        self.inner_app = app
        self.keycloak_middleware = keycloak_middleware
        self.allowed_get_paths = self.ALLOWED_PATHS

    async def __call__(self, scope, receive, send):
        if (
            scope["method"] == "GET"
            and scope["path"] in self.allowed_get_paths
        ):
            await self.inner_app(scope, receive, send)
        else:
            await self.keycloak_middleware(scope, receive, send)
