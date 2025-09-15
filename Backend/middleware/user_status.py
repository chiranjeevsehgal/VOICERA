from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse
from services.auth import get_current_user
import re
import logging
logger = logging.getLogger(__name__)

class UserStatusMiddleware(BaseHTTPMiddleware):
    EXCLUDED_ROUTES = ['^/$', '^/health.*', '^/api/auth/login.*', '^/api/auth/google-login.*', '^/api/auth/register.*', '^/api/send-email.*']

    async def dispatch(self, request: Request, call_next):
        if self._is_route_excluded(request.url.path) or request.method == 'OPTIONS':
            return await call_next(request)
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return await call_next(request)
        token = auth_header.replace('Bearer ', '')
        try:
            user = await get_current_user(token)
            if not user:
                return JSONResponse(status_code=401, content={'status': False, 'detail': 'Invalid or expired token', 'code': 'INVALID_TOKEN'})
            user_status = user.get('status', 'active').lower()
            if user_status == 'inactive':
                logger.warning(f"Inactive user attempted access: {user.get('email', 'unknown')}")
                return JSONResponse(status_code=403, content={'status': False, 'detail': 'Your account is inactive. Please contact support for assistance.', 'code': 'ACCOUNT_INACTIVE', 'action': 'FORCE_LOGOUT'}, headers={'Content-Type': 'application/json'})
            request.state.user = user
            request.state.user_id = user.get('id') or user.get('user_id')
        except Exception as e:
            logger.error(f'Error in UserStatusMiddleware: {str(e)}')
        return await call_next(request)

    def _is_route_excluded(self, path: str) -> bool:
        """Check if the route should be excluded from user status checking"""
        for pattern in self.EXCLUDED_ROUTES:
            if re.match(pattern, path):
                return True
        return False