from fastapi import Depends, HTTPException, status
from fastapi_keycloak_middleware import FastApiUser, MatchStrategy, get_auth, get_user


class BluecoreCheckPermissions:
    def __init__(
        self,
        required_role: str | list[str],
        forbidden_role: str | list[str],
        required_strategy: MatchStrategy = MatchStrategy.AND,
        forbidden_strategy: MatchStrategy = MatchStrategy.OR,
    ):
        self.required_roles = self._normalize_roles(required_role)
        self.forbidden_roles = self._normalize_roles(forbidden_role)
        self.required_strategy = required_strategy
        self.forbidden_strategy = forbidden_strategy

    @staticmethod
    def _normalize_roles(roles: str | list[str]) -> list[str]:
        if isinstance(roles, str):
            return [roles]
        return roles

    @staticmethod
    def _check_roles(
        user_roles: list[str], roles_to_check: list[str], strategy: MatchStrategy
    ) -> bool:
        if strategy == MatchStrategy.AND:
            return all(role in user_roles for role in roles_to_check)
        elif strategy == MatchStrategy.OR:
            return any(role in user_roles for role in roles_to_check)
        else:
            raise ValueError(f"Unsupported match strategy: {strategy}")

    async def __call__(
        self,
        user: FastApiUser = Depends(get_user),
        auth: list[str] | None = Depends(get_auth),
    ) -> FastApiUser:
        # Ensure the user is authenticated
        if not user or not user.is_authenticated:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )

        # Roles are resolved by keycloak middleware + scope_mapper
        user_roles = auth or []

        # Verify the inclusion and exclusion conditions
        has_required = self._check_roles(
            user_roles, self.required_roles, self.required_strategy
        )
        has_forbidden = self._check_roles(
            user_roles, self.forbidden_roles, self.forbidden_strategy
        )

        if not has_required or has_forbidden:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=("Access denied."),
            )

        return user
