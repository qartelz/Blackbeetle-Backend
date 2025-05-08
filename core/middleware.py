from channels.middleware import BaseMiddleware
from asgiref.sync import sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken, TokenError
from django.contrib.auth import get_user_model
from urllib.parse import parse_qs

User = get_user_model()

class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        # Extract token from headers or query string
        token = await self._extract_token(scope)

        # Authenticate the user
        scope['user'] = await self._get_user_from_token(token)
        
        # Call the next middleware or application
        return await super().__call__(scope, receive, send)

    async def _extract_token(self, scope):
        # Try to extract token from headers first
        headers = dict(scope.get('headers', []))
        
        # Check Authorization header
        auth_header = headers.get(b'authorization', b'').decode('utf-8')
        if auth_header.startswith('Bearer '):
            return auth_header.split('Bearer ')[1].strip()
        
        # Fallback to query string
        query_string = scope.get('query_string', b'').decode()
        try:
            parsed_qs = parse_qs(query_string)
            tokens = parsed_qs.get('access_token', [])
            return tokens[0] if tokens else None
        except Exception:
            return None

    @sync_to_async
    def _get_user_from_token(self, token):
        try:
            if token:
                # Use specific token validation exceptions
                access_token = AccessToken(token)
                user_id = access_token.get('user_id')
                
                # Additional validation
                if user_id:
                    return User.objects.get(id=user_id)
        except (TokenError, User.DoesNotExist):
            pass
        
        return AnonymousUser()