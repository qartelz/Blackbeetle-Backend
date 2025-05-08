import hashlib
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
from ..users.models import LoginAttempt
from ..institutions.models import Institution, InstitutionUser
from ..subscriptions.models import Subscription
from .serializers import (
    UserSerializer, LoginSerializer, B2CRegistrationSerializer,
    B2BUserRegistrationSerializer, B2BAdminRegistrationSerializer,
    InstitutionSerializer, SubscriptionSerializer, UserListSerializer,
    UserActionSerializer, LoginAttemptSerializer, UserProfileEditSerializer
)
from core.permissions import IsB2BAdmin, IsB2BUser, IsB2CUser
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from django.db.models import Q
from django.core.paginator import Paginator
from user_agents import parse
import geoip2.database
from django.conf import settings
import redis
from .serializers import UserProfileSerializer
from django.core.mail import send_mail
from django.contrib.auth.hashers import make_password
from .utils import OTPManager
import logging
import django.utils.timezone as timezone
from phonenumbers import PhoneNumber  # For handling PhoneNumber objects

User = get_user_model()

# Initialize Redis connection
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)

# Initialize logger
logger = logging.getLogger(__name__)

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def get_device_identifier(self, request):
        ip_address = self.get_client_ip(request)
        user_agent_string = request.META.get('HTTP_USER_AGENT', '')
        user_agent_hash = hashlib.md5(user_agent_string.encode()).hexdigest()[:10]
        device_identifier = f"{ip_address}_{user_agent_hash}"
        return device_identifier

    def get_device_type(self, user_agent_string):
        user_agent = parse(user_agent_string)
        if user_agent.is_mobile:
            return "mobile"
        elif user_agent.is_pc:
            return "desktop"
        return "unknown"

    def get_client_ip(self, request):
        try:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ips = [ip.strip() for ip in x_forwarded_for.split(',')]
                ip = ips[0]
            else:
                ip = request.META.get('REMOTE_ADDR', '')
            return ip
        except Exception as e:
            logger.error(f"Error extracting client IP: {str(e)}")
            return "0.0.0.0"

    def log_login_attempt(self, request, user, success):
        try:
            ip_address = self.get_client_ip(request)
            user_agent_string = request.META.get('HTTP_USER_AGENT', '')
            user_agent = parse(user_agent_string)

            country = city = region = "Unknown"
            geoip_db_path = getattr(settings, 'GEOIP_DB_PATH', None)
            if geoip_db_path:
                try:
                    reader = geoip2.database.Reader(geoip_db_path)
                    geo_data = reader.city(ip_address)
                    country = geo_data.country.name
                    city = geo_data.city.name
                    region = geo_data.subdivisions.most_specific.name
                    reader.close()
                except FileNotFoundError:
                    logger.warning(f"GeoIP database not found at {geoip_db_path}")
                except Exception as e:
                    logger.error(f"Error during GeoIP lookup: {str(e)}")

            login_attempt = LoginAttempt.objects.create(
                user=user,
                success=success,
                ip_address=ip_address,
                user_agent=user_agent_string,
                device_type=user_agent.device.family,
                browser=user_agent.browser.family,
                os=user_agent.os.family,
                country=country,
                city=city,
                region=region
            )

            if user and success:
                user.last_login_ip = ip_address
                user.last_login_device = f"{user_agent.device.family} - {user_agent.os.family} - {user_agent.browser.family}"
                user.save()

        except Exception as e:
            logger.error(f"Error logging login attempt: {str(e)}")

    def handle_new_device_login(self, request, user, device_identifier, device_type):
        # Convert PhoneNumber to string if necessary
        phone_number_str = str(user.phone_number) if isinstance(user.phone_number, PhoneNumber) else user.phone_number
        
        secret_key = OTPManager.generate_secret_key(phone_number_str)
        otp = OTPManager.generate_otp(secret_key)
        email = user.email
        if not email:
            return Response(
                {'error': 'No email associated with this account.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        subject = "New Device Login OTP"
        message = f"Your OTP for logging in from a new device is: {otp}. It is valid for 5 minutes."
        from_email = settings.EMAIL_HOST_USER
        recipient_list = [email]

        try:
            send_mail(subject, message, from_email, recipient_list)
            redis_client.set(f"new_device_otp:{user.id}", secret_key, ex=300)
            redis_client.set(f"new_device_info:{user.id}", f"{device_identifier}:{device_type}", ex=300)
            return Response(
                {'message': 'An OTP has been sent to your email for new device login verification.'},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error sending OTP: {str(e)}")
            return Response(
                {'error': 'Failed to send OTP. Please try again later.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        try:
            phone_number = request.data.get('phone_number')
            password = request.data.get('password')

            if not phone_number or not password:
                return Response(
                    {'error': 'Both phone number and password are required.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                user = User.objects.get(phone_number=phone_number)
            except User.DoesNotExist:
                return Response(
                    {'error': 'The phone number you entered does not exist.'},
                    status=status.HTTP_404_NOT_FOUND
                )

            ip_address = self.get_client_ip(request)
            key = f"login_attempts:{ip_address}"
            attempts = redis_client.get(key)
            attempts = int(attempts) if attempts else 0
            if attempts >= 5:
                ttl = redis_client.ttl(key)
                minutes, seconds = divmod(ttl, 60)
                time_remaining = f"{minutes} minute(s) and {seconds} second(s)"
                return Response(
                    {'error': f'Too many login attempts. Please try again after {time_remaining}.'},
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )

            authenticated_user = authenticate(phone_number=phone_number, password=password)
            if authenticated_user:
                device_identifier = self.get_device_identifier(request)
                user_agent_string = request.META.get('HTTP_USER_AGENT', '')
                device_type = self.get_device_type(user_agent_string)
                session_key = f"user_session:{authenticated_user.id}"
                device_key = f"{session_key}:devices"

                current_devices = redis_client.hgetall(device_key)
                current_devices = {k.decode(): v.decode() for k, v in current_devices.items()}

                mobile_count = sum(1 for dt in current_devices.values() if dt == "mobile")
                desktop_count = sum(1 for dt in current_devices.values() if dt == "desktop")

                if (device_type == "mobile" and mobile_count >= 1) or \
                   (device_type == "desktop" and desktop_count >= 1) or \
                   (len(current_devices) >= 2 and device_identifier not in current_devices):
                    return self.handle_new_device_login(request, authenticated_user, device_identifier, device_type)

                self.log_login_attempt(request, authenticated_user, success=True)
                redis_client.hset(device_key, device_identifier, device_type)
                refresh_token_lifetime = settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME']
                expiration_time = int(refresh_token_lifetime.total_seconds())
                redis_client.expire(device_key, expiration_time)

                refresh = RefreshToken.for_user(authenticated_user)
                refresh['user_type'] = authenticated_user.user_type
                refresh['user_id'] = str(authenticated_user.id)

                return Response({
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                    'user': UserSerializer(authenticated_user).data,
                    'user_type': authenticated_user.user_type
                }, status=status.HTTP_200_OK)

            self.log_login_attempt(request, None, success=False)
            redis_client.incr(key)
            redis_client.expire(key, 300)
            return Response(
                {'error': 'The password you entered is incorrect.'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        except redis.RedisError as e:
            logger.error(f"Redis error: {str(e)}")
            return Response(
                {'error': 'An unexpected error occurred while processing your request.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return Response(
                {'error': 'An unexpected error occurred. Please try again later.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



class VerifyNewDeviceOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        phone_number = request.data.get('phone_number')
        otp = request.data.get('otp')

        if not phone_number or not otp:
            return Response(
                {'error': 'Phone number and OTP are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            return Response(
                {'error': 'The phone number you entered does not exist.'},
                status=status.HTTP_404_NOT_FOUND
            )

        secret_key = redis_client.get(f"new_device_otp:{user.id}")
        if not secret_key:
            return Response(
                {'error': 'OTP expired or invalid.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not OTPManager.verify_otp(secret_key.decode(), otp):
            return Response(
                {'error': 'Invalid OTP.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        device_info = redis_client.get(f"new_device_info:{user.id}")
        if not device_info:
            return Response(
                {'error': 'Device information expired.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        device_identifier, device_type = device_info.decode().split(':')

        session_key = f"user_session:{user.id}"
        device_key = f"{session_key}:devices"
        redis_client.delete(device_key)

        outstanding_tokens = OutstandingToken.objects.filter(user=user)
        for token_obj in outstanding_tokens:
            try:
                RefreshToken(token_obj.token).blacklist()
            except TokenError:
                pass

        redis_client.hset(device_key, device_identifier, device_type)
        refresh_token_lifetime = settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME']
        expiration_time = int(refresh_token_lifetime.total_seconds())
        redis_client.expire(device_key, expiration_time)

        refresh = RefreshToken.for_user(user)
        refresh['user_type'] = user.user_type
        refresh['user_id'] = str(user.id)

        redis_client.delete(f"new_device_otp:{user.id}")
        redis_client.delete(f"new_device_info:{user.id}")

        LoginView().log_login_attempt(request, user, success=True)

        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserSerializer(user).data,
            'user_type': user.user_type
        }, status=status.HTTP_200_OK)

class B2CRegistrationView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = B2CRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class B2BUserRegistrationView(APIView):
    permission_classes = [IsB2BAdmin]

    def post(self, request):
        serializer = B2BUserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            institution = request.user.administered_institution
            if not institution:
                return Response({"error": "B2B Admin is not associated with any institution"}, status=status.HTTP_400_BAD_REQUEST)
            user = serializer.save(institution_code=institution.code)
            return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class B2BAdminRegistrationView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        serializer = B2BAdminRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def put(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_device_identifier(self, request):
        ip_address = self.get_client_ip(request)
        user_agent_string = request.META.get('HTTP_USER_AGENT', '')
        user_agent_hash = hashlib.md5(user_agent_string.encode()).hexdigest()[:10]
        device_identifier = f"{ip_address}_{user_agent_hash}"
        return device_identifier

    def get_client_ip(self, request):
        try:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ips = [ip.strip() for ip in x_forwarded_for.split(',')]
                ip = ips[0]  # Use the first IP in the list
            else:
                ip = request.META.get('REMOTE_ADDR', '')
            return ip
        except Exception as e:
            logger.error(f"Error extracting client IP: {str(e)}")
            return "0.0.0.0"  # Fallback IP address

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response(
                    {"error": "Refresh token is required."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validate and blacklist the refresh token
            token = RefreshToken(refresh_token)
            user = request.user
            device_identifier = self.get_device_identifier(request)
            session_key = f"user_session:{user.id}"
            device_key = f"{session_key}:devices"

            # Remove the specific device from the tracked devices
            if redis_client.hexists(device_key, device_identifier):
                redis_client.hdel(device_key, device_identifier)
                logger.info(f"Device {device_identifier} removed from user {user.id}'s active devices.")

            # If no devices remain, clean up the session
            if not redis_client.hlen(device_key):
                redis_client.delete(device_key)
                logger.info(f"All devices logged out for user {user.id}. Session cleaned up.")

            # Blacklist the token
            token.blacklist()

            return Response(
                {"detail": "Successfully logged out from this device."},
                status=status.HTTP_200_OK
            )

        except TokenError as e:
            logger.error(f"Token error during logout: {str(e)}")
            return Response(
                {"error": "Invalid or expired token."},
                status=status.HTTP_400_BAD_REQUEST
            )
        except redis.RedisError as e:
            logger.error(f"Redis error during logout: {str(e)}")
            return Response(
                {"error": "An error occurred while processing your logout request."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"Unexpected error during logout: {str(e)}")
            return Response(
                {"error": "An unexpected error occurred. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class B2BAdminDashboardView(APIView):
    permission_classes = [IsB2BAdmin]

    def get(self, request):
        user = request.user
        institution = user.administered_institution
        if not institution:
            return Response({"error": "No associated institution found"}, status=status.HTTP_404_NOT_FOUND)
        
        institution_data = InstitutionSerializer(institution).data
        institution_users = InstitutionUser.objects.filter(institution=institution)
        
        return Response({
            "user": UserSerializer(user).data,
            "institution": institution_data,
            "total_users": institution_users.count(),
            "active_users": institution_users.filter(is_active=True).count(),
        })

class B2BUserDashboardView(APIView):
    permission_classes = [IsB2BUser]

    def get(self, request):
        user = request.user
        institution_user = InstitutionUser.objects.filter(user=user).first()
        if not institution_user:
            return Response({"error": "No associated institution found"}, status=status.HTTP_404_NOT_FOUND)
        
        return Response({
            "user": UserSerializer(user).data,
            "institution": InstitutionSerializer(institution_user.institution).data,
            "role": institution_user.role,
            "join_date": institution_user.join_date,
        })

class B2CDashboardView(APIView):
    permission_classes = [IsB2CUser]

    def get(self, request):
        user = request.user
        subscription = Subscription.objects.filter(user=user, is_active=True).first()
        
        return Response({
            "user": UserSerializer(user).data,
            "subscription": SubscriptionSerializer(subscription).data if subscription else None,
        })

class AdminDashboardView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        total_users = User.objects.count()
        total_institutions = Institution.objects.count()
        total_subscriptions = Subscription.objects.filter(is_active=True).count()
        
        return Response({
            "total_users": total_users,
            "total_institutions": total_institutions,
            "active_subscriptions": total_subscriptions,
        })

class SubscriptionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        subscription = Subscription.objects.filter(user=request.user, is_active=True).first()
        if subscription:
            return Response(SubscriptionSerializer(subscription).data)
        return Response({"detail": "No active subscription found."}, status=status.HTTP_404_NOT_FOUND)

class CustomTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(e.args[0])

        return Response(serializer.validated_data, status=status.HTTP_200_OK)

class UserListView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = 5
        search = request.query_params.get('search', '')
        user_type = request.query_params.get('user_type', 'all')
        status = request.query_params.get('status', 'all')

        queryset = User.objects.exclude(user_type__in=[User.UserType.ADMIN])

        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone_number__icontains=search) |
                Q(institution_memberships__institution__name__icontains=search)
            ).distinct()

        if user_type != 'all':
            queryset = queryset.filter(user_type=user_type)

        if status == 'verified':
            queryset = queryset.filter(is_verified=True)
        elif status == 'unverified':
            queryset = queryset.filter(is_verified=False)

        total_count = queryset.count()
        start = (page - 1) * page_size
        end = start + page_size
        users = queryset[start:end]

        serializer = UserListSerializer(users, many=True)

        return Response({
            'results': serializer.data,
            'count': total_count,
        })

class UserActionView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        action = request.data.get('action')
        
        if action == 'toggle_active':
            user.is_active = not user.is_active
            user.save()
            return Response({"status": "success", "is_active": user.is_active})
        
        elif action == 'toggle_verified':
            user.is_verified = not user.is_verified
            user.save()
            return Response({"status": "success", "is_verified": user.is_verified})
        
        else:
            return Response({"error": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)

class UserStatsView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        total_users = User.objects.exclude(user_type=User.UserType.ADMIN).count()
        b2b_admins = User.objects.filter(user_type=User.UserType.B2B_ADMIN).count()
        b2b_users = User.objects.filter(user_type=User.UserType.B2B_USER).count()
        b2c_users = User.objects.filter(user_type=User.UserType.B2C).count()

        return Response({
            'totalUsers': total_users,
            'b2bAdmins': b2b_admins,
            'b2bUsers': b2b_users,
            'b2cUsers': b2c_users
        })

class LoginAttemptView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        login_attempts = LoginAttempt.objects.filter(user=user).order_by('-timestamp')[:10]
        serializer = LoginAttemptSerializer(login_attempts, many=True)
        return Response(serializer.data)


class InstitutionUserManagementView(APIView):
    permission_classes = [IsB2BAdmin]

    def get(self, request):
        institution = request.user.administered_institution
        if not institution:
            return Response(
                {"error": "No institution found for this admin"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        # Get query parameters
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 10))
        search = request.query_params.get('search', '')
        status_filter = request.query_params.get('status', 'all')
        verification_status = request.query_params.get('verification', 'all')
        include_deleted = request.query_params.get('include_deleted', 'false').lower() == 'true'

        # Base queryset - exclude deleted users by default
        queryset = User.objects.filter(
            institution_memberships__institution=institution,
            user_type=User.UserType.B2B_USER
        )
        
        if not include_deleted:
            queryset = queryset.exclude(status=User.UserStatus.DELETED)
            queryset = queryset.filter(institution_memberships__is_active=True)

        # Apply search filter
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone_number__icontains=search)
            ).distinct()

        # Apply status filter
        if status_filter != 'all':
            if status_filter == 'active':
                queryset = queryset.filter(is_active=True)
            elif status_filter == 'inactive':
                queryset = queryset.filter(is_active=False)
            elif status_filter == 'deleted':
                queryset = queryset.filter(status=User.UserStatus.DELETED)

        # Apply verification filter
        if verification_status != 'all':
            if verification_status == 'verified':
                queryset = queryset.filter(is_verified=True)
            elif verification_status == 'unverified':
                queryset = queryset.filter(is_verified=False)

        # Count active users
        active_count = queryset.filter(
            is_active=True,
            status=User.UserStatus.ACTIVE
        ).count()

        # Apply pagination
        total_count = queryset.count()
        start = (page - 1) * page_size
        end = start + page_size
        users = queryset[start:end]

        serializer = UserListSerializer(users, many=True)

        return Response({
            'results': serializer.data,
            'count': total_count,
            'total_pages': (total_count + page_size - 1) // page_size,
            'current_page': page,
            'institution_stats': {
                'active_users': active_count,
                'total_users': total_count,
                'max_users': institution.max_users,
                'available_slots': institution.max_users - active_count
            }
        })

    def delete(self, request, user_id):
        institution = request.user.administered_institution
        if not institution:
            return Response(
                {"error": "No institution found for this admin"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            # Get user and their institution membership
            user = User.objects.get(
                id=user_id,
                user_type=User.UserType.B2B_USER,
                institution_memberships__institution=institution
            )
            institution_user = InstitutionUser.objects.get(
                user=user,
                institution=institution
            )
        except (User.DoesNotExist, InstitutionUser.DoesNotExist):
            return Response(
                {"error": "User not found in your institution"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        # Implement soft delete
        current_time = timezone.now()

        # Update User status
        user.status = User.UserStatus.DELETED
        user.is_active = False
        user.deleted_at = current_time
        user.save()

        # Update InstitutionUser status
        institution_user.is_active = False
        institution_user.updated_at = current_time
        institution_user.save()

        # Optional: Add a notification or log the deletion
        user.add_b2b_notification(
            title="Account Deactivated",
            message=f"Your account in {institution.name} has been deactivated by the administrator.",
            notification_type="WARNING",
            institution=institution
        )

        return Response({
            "status": "success",
            "message": "User has been deactivated and marked as deleted",
            "details": {
                "user_id": str(user.id),
                "deleted_at": current_time.isoformat(),
                "institution": institution.name
            }
        })

    # Optionally add a restore method
    def patch(self, request, user_id):
        institution = request.user.administered_institution
        if not institution:
            return Response(
                {"error": "No institution found for this admin"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        action = request.data.get('action')
        if action != 'restore':
            return Response(
                {"error": "Invalid action"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Get user and their institution membership
            user = User.objects.get(
                id=user_id,
                user_type=User.UserType.B2B_USER,
                institution_memberships__institution=institution,
                status=User.UserStatus.DELETED
            )
            institution_user = InstitutionUser.objects.get(
                user=user,
                institution=institution
            )
        except (User.DoesNotExist, InstitutionUser.DoesNotExist):
            return Response(
                {"error": "Deleted user not found in your institution"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if restoring would exceed user limit
        active_users_count = institution.get_active_users_count()
        if active_users_count >= institution.max_users:
            return Response({
                "error": "Cannot restore user. Institution user limit reached."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Restore user
        user.status = User.UserStatus.ACTIVE
        user.is_active = True
        user.deleted_at = None
        user.save()

        # Restore institution membership
        institution_user.is_active = True
        institution_user.save()

        # Notify user of restoration
        user.add_b2b_notification(
            title="Account Restored",
            message=f"Your account in {institution.name} has been restored by the administrator.",
            notification_type="INFO",
            institution=institution
        )

        return Response({
            "status": "success",
            "message": "User has been restored successfully",
            "details": {
                "user_id": str(user.id),
                "restored_at": timezone.now().isoformat(),
                "institution": institution.name
            }
        })
    


class UserProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user

        # Serialize user profile details
        user_serializer = UserProfileSerializer(user)

        # Return the serialized response
        return Response(user_serializer.data)
    






class RequestPasswordResetView(APIView):
    permission_classes = []

    def post(self, request):
        phone_number = request.data.get('phone_number')

        if not phone_number:
            return Response(
                {"error": "Phone number is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            return Response(
                {"error": "The phone number you entered does not exist."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Retrieve the user's email
        email = user.email
        if not email:
            return Response(
                {"error": "No email associated with this phone number."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Generate a secret key and OTP
        secret_key = OTPManager.generate_secret_key(phone_number)
        otp = OTPManager.generate_otp(secret_key)

        # Send OTP via email
        subject = "Your Password Reset OTP"
        message = f"Your OTP for password reset is: {otp}. It is valid for 5 minutes."
        from_email = settings.EMAIL_HOST_USER
        recipient_list = [email]
        print(otp,'ddddddddddddddddddddddddddddddddd')

        try:
            send_mail(subject, message, from_email, recipient_list)
        except Exception as e:
            return Response(
                {"error": "Failed to send OTP. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Store the secret key temporarily in cache (e.g., Redis)
        redis_client.set(f"reset_password:{phone_number}", secret_key, ex=300)  # Expires in 5 minutes

        return Response(
            {"message": "An OTP has been sent to your email address."},
            status=status.HTTP_200_OK,
        )


class VerifyOTPView(APIView):
    permission_classes = []

    def post(self, request):
        phone_number = request.data.get('phone_number')
        otp = request.data.get('otp')

        if not phone_number or not otp:
            return Response(
                {"error": "Phone number and OTP are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Retrieve the secret key from cache
        secret_key = redis_client.get(f"reset_password:{phone_number}")
        if not secret_key:
            return Response(
                {"error": "OTP expired or invalid."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify the OTP
        if not OTPManager.verify_otp(secret_key.decode(), otp):
            return Response(
                {"error": "Invalid OTP."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Mark the OTP as verified in cache
        redis_client.set(f"reset_password_verified:{phone_number}", "true", ex=300)  # Expires in 5 minutes

        return Response(
            {"message": "OTP verified successfully."},
            status=status.HTTP_200_OK,
        )


class ResetPasswordView(APIView):
    permission_classes = []

    def post(self, request):
        phone_number = request.data.get('phone_number')
        new_password = request.data.get('new_password')

        if not phone_number or not new_password:
            return Response(
                {"error": "Phone number and new password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if OTP was verified
        is_verified = redis_client.get(f"reset_password_verified:{phone_number}")
        if not is_verified or is_verified.decode() != "true":
            return Response(
                {"error": "OTP verification is required before resetting the password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            return Response(
                {"error": "The phone number you entered does not exist."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Update the user's password
        user.password = make_password(new_password)
        user.save()

        # Clear the cache
        redis_client.delete(f"reset_password:{phone_number}")
        redis_client.delete(f"reset_password_verified:{phone_number}")

        return Response(
            {"message": "Your password has been reset successfully."},
            status=status.HTTP_200_OK,
        )


class UserProfileEditView(APIView):
    """
    API View to edit user profile (profile picture, username, and email).
    """
    permission_classes = [permissions.IsAuthenticated]
    # parser_classes = [MultiPartParser, FormParser]  # Handles file uploads

    def patch(self, request, *args, **kwargs):
        user = request.user
        serializer = UserProfileEditSerializer(user, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Profile updated successfully", "data": serializer.data}, status=200)

        return Response(serializer.errors, status=400)