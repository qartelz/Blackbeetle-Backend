from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField
from django.utils import timezone
import uuid
# from ..notifications.models import Notification
class CustomUserManager(BaseUserManager):
    def create_user(self, phone_number, email, password=None, **extra_fields):
        if not phone_number:
            raise ValueError(_("The Phone Number field must be set"))
        if not email:
            raise ValueError(_("The Email field must be set"))
        
        email = self.normalize_email(email)
        user = self.model(phone_number=phone_number, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        # this is the new update 
        #  subscription = self.create_free_subscription(user)
        return user

    def create_superuser(self, phone_number, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("user_type", User.UserType.ADMIN)
        extra_fields.setdefault("is_verified", True)
        
        return self.create_user(phone_number, email, password, **extra_fields)
    
     # this is the new update 

    # def create_free_subscription(self, user):
    #     free_plan = Plan.objects.get(name='FREE')
    #     subscription = Subscription.objects.create(
    #         user=user,
    #         plan=free_plan,
    #         start_date=timezone.now(),
    #         end_date=timezone.now() + timezone.timedelta(days=3),
    #         is_active=True
    #     )
    #     return subscription

class User(AbstractUser):
    class UserType(models.TextChoices):
        ADMIN = 'ADMIN', _('Superuser Admin')
        B2B_ADMIN = 'B2B_ADMIN', _('Institute Admin')
        B2B_USER = 'B2B_USER', _('Institute User')
        B2C = 'B2C', _('Business to Consumer')

    class UserStatus(models.TextChoices):
        ACTIVE = 'ACTIVE', _('Active')
        INACTIVE = 'INACTIVE', _('Inactive')
        SUSPENDED = 'SUSPENDED', _('Suspended')
        DELETED = 'DELETED', _('Deleted')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    phone_number = PhoneNumberField(unique=True, db_index=True)
    email = models.EmailField(_('email address'), unique=True, db_index=True)#null=True
    user_type = models.CharField(
        max_length=10,
        choices=UserType.choices,
        default=UserType.B2C,
        db_index=True
    )
    status = models.CharField(
        max_length=10,
        choices=UserStatus.choices,
        default=UserStatus.ACTIVE,
        db_index=True
    )
    is_verified = models.BooleanField(default=False, db_index=True)
    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)
    date_of_birth = models.DateField(null=True, blank=True)
    profile_picture = models.ImageField(upload_to='profile_pictures/', null=True, blank=True)
    bio = models.TextField(blank=True)#null=True
    address = models.TextField(blank=True)#null=True
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    
    # Security and tracking fields
    failed_login_attempts = models.PositiveIntegerField(default=0)
    last_failed_login = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    last_login_device = models.CharField(max_length=255, null=True, blank=True)
    force_password_change = models.BooleanField(default=False)
    password_changed_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = ['email']

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user_type', 'status', 'created_at']),
            models.Index(fields=['phone_number', 'email']),
        ]

    def __str__(self):
        return f"{self.phone_number} - {self.get_user_type_display()}"

    def clean(self):
        super().clean()
        self.email = self.email.lower()

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def get_full_name(self):
        
        return f"{self.first_name} {self.last_name}".strip() or str(self.phone_number)

    def get_short_name(self):
        return self.first_name or str(self.phone_number)

    @property
    def is_admin(self):
        return self.user_type == self.UserType.ADMIN

    @property
    def is_b2b_admin(self):
        return self.user_type == self.UserType.B2B_ADMIN

    @property
    def is_b2b_user(self):
        
        return self.user_type == self.UserType.B2B_USER

    @property
    def is_b2c_user(self):
        return self.user_type == self.UserType.B2C

    def has_perm(self, perm, obj=None):
        """
        Check if user has a specific permission.
        
        Args:
            perm (str): permission string
            obj (object): object to check permission against
        
        Returns:
            bool: True if permission is granted, False otherwise
        """
        if self.is_admin:
            return True
        return super().has_perm(perm, obj)

    def has_module_perms(self, app_label):
        """
        Determines if the user has permissions for a specific app.

        Args:
            app_label (str): The label of the app to check permissions for.

        Returns:
            bool: True if the user has the necessary permissions, False if not.
            Automatically returns True if the user is an admin.
        """
        if self.is_admin:
            return True
        return super().has_module_perms(app_label)

    # def add_b2b_notification(self, title, message, notification_type='INFO', institution=None, content_object=None):
    #     """
    #     Create a notification for the user.

    #     Args:
    #         title (str): Title of the notification
    #         message (str): Message of the notification
    #         notification_type (str): Type of the notification
    #         institution (Institution): Institution of the notification
    #         content_object (object): Object associated with the notification

    #     Returns:
    #         Notification: The created notification
    #     """
    #     if self.user_type in [self.UserType.B2B_ADMIN, self.UserType.B2B_USER]:
    #         notification = Notification.objects.create(
    #             recipient=self,
    #             title=title,
    #             message=message,
    #             notification_type=notification_type,
    #             institution=institution or self.institution_memberships.first().institution,
    #             content_object=content_object
    #         )
    #         return notification
    #     return None

    # def add_b2c_notification(self, title, message, notification_type='INFO', content_object=None):
    #     """
    #     Create a notification for B2C users.
    #     """
    #     if self.user_type == self.UserType.B2C:
    #         notification = Notification.objects.create(
    #             recipient=self,
    #             title=title,
    #             message=message,
    #             notification_type=notification_type,
    #             content_object=content_object
    #         )
    #         return notification
    #     return None

    # def get_unread_notifications(self):
    #     """
    #     Get all unread notifications for the user.
    #     """
    #     return Notification.objects.filter(recipient=self, is_read=False)

    # def mark_notification_as_read(self, notification_id):
    #     """
    #     Mark a specific notification as read.
        
    #     Args:
    #         notification_id: ID of the notification to mark as read
            
    #     Returns:
    #         bool: True if notification was marked as read, False otherwise
    #     """
    #     notification = Notification.objects.filter(id=notification_id, recipient=self).first()
    #     if notification:
    #         notification.is_read = True
    #         notification.save()
    #         return True
    #     return False

class LoginAttempt(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='login_attempts')
    timestamp = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    device_type = models.CharField(max_length=50, null=True, blank=True)
    browser = models.CharField(max_length=100, null=True, blank=True)
    os = models.CharField(max_length=100, null=True, blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    region = models.CharField(max_length=100, null=True, blank=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp', 'success']),
            models.Index(fields=['ip_address', 'timestamp']),
        ]