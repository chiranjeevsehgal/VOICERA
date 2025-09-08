from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse
from services.auth import get_current_user
import re
import logging

logger = logging.getLogger(__name__)

class UserStatusMiddleware(BaseHTTPMiddleware):
    # Routes that should be excluded from user status checking
    EXCLUDED_ROUTES = [
        r'^/$',  # Root endpoint
        r'^/health.*',  # Health check endpoints
        r'^/api/auth/login.*',  # Login endpoints
        r'^/api/auth/google-login.*',  # OAuth endpoints
        r'^/api/auth/register.*',  # Registration endpoints
        r'^/api/send-email.*',  # Send email endpoints
    ]
    
    async def dispatch(self, request: Request, call_next):
        # Skip status check for excluded routes
        if self._is_route_excluded(request.url.path):
            return await call_next(request)
        
        # Extract and validate token
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            # No token provided - let the endpoint handle authentication
            return await call_next(request)
        
        token = auth_header.replace("Bearer ", "")
        
        try:
            # Get user from database
            user = await get_current_user(token)
            if not user:
                return JSONResponse(
                    status_code=401,
                    content={
                        "status": False,
                        "detail": "Invalid or expired token",
                        "code": "INVALID_TOKEN"
                    }
                )
            
            # Check if user is inactive - BLOCK IMMEDIATELY
            user_status = user.get("status", "active").lower()
            if user_status == "inactive":
                logger.warning(f"Inactive user attempted access: {user.get('email', 'unknown')}")
                return JSONResponse(
                    status_code=403,
                    content={
                        "status": False,
                        "detail": "Your account is inactive. Please contact support for assistance.",
                        "code": "ACCOUNT_INACTIVE",
                        "action": "FORCE_LOGOUT"
                    },
                    headers={
                        "Content-Type": "application/json"
                    }
                )
            
            # Add user info to request state for use in endpoints
            request.state.user = user
            request.state.user_id = user.get("id") or user.get("user_id")
            
        except Exception as e:
            logger.error(f"Error in UserStatusMiddleware: {str(e)}")
        
        return await call_next(request)
    
    def _is_route_excluded(self, path: str) -> bool:
        """Check if the route should be excluded from user status checking"""
        for pattern in self.EXCLUDED_ROUTES:
            if re.match(pattern, path):
                return True
        return False