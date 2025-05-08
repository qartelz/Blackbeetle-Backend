from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField
from ..users.models import User
import uuid
from django.db.models import  Max


class BaseModel(models.Model):
    # id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]
        get_latest_by = "created_at"

class Institution(BaseModel):

    class PlanType(models.TextChoices):
        BASE = 'BASE', _('Base')
        PREMIUM = 'PREMIUM', _('Premium')
        SUPER_PREMIUM = 'SUPER_PREMIUM', _('Super Premium')

    PLAN_USER_LIMITS = {
        PlanType.BASE: 100,
        PlanType.PREMIUM: 500,
        PlanType.SUPER_PREMIUM: 1000,
    }
    name = models.CharField(max_length=255, unique=True,null=False,blank=False)
    code = models.CharField(max_length=10, unique=True, editable=False)
    admin = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="administered_institution",
        limit_choices_to={"user_type": User.UserType.B2B_ADMIN},
    )
    description = models.TextField(blank=True)
    website = models.URLField(blank=True, null=True)
    address = models.TextField(blank=True)
    contact_email = models.EmailField()
    contact_phone = PhoneNumberField()
    max_users = models.PositiveIntegerField(default=100)
    plan_type = models.CharField(
        max_length=20,
        choices=PlanType.choices,
        default=PlanType.BASE,
        null=True,
        blank=True
    )
    is_deleted = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} ({self.code})"

    def clean(self):
        """
        Validation method that checks if the admin is a B2B admin user.

        Raises a ValidationError if the admin is not a B2B admin user.
        """
        if self.admin and self.admin.user_type != User.UserType.B2B_ADMIN:
            raise ValidationError(_("The admin must be a B2B admin user."))

    def get_active_users_count(self):
        return self.users.filter(is_active=True).count()

    def can_add_user(self):
        return self.get_active_users_count() < self.max_users

    def add_user(self, user):
        if not self.can_add_user():
            raise ValidationError(_("Maximum number of users reached for this institution."))
        if user.user_type != User.UserType.B2B_USER:
            raise ValidationError(_("Only B2B users can be added to an institution."))
        InstitutionUser.objects.create(institution=self, user=user)

    def remove_user(self, user):
        InstitutionUser.objects.filter(institution=self, user=user).delete()
        #InstitutionUser.objects.filter(institution=self, user=user).update(is_deleted=True)

    def save(self, *args, **kwargs):

        """
        Override the save method to generate a unique code for the institution if it is not set.

        The code is generated as 'BBI' followed by a 5-digit zero-padded number, which is the next
        number available in the existing codes.

        If the code is already set, it is not changed.

        :param args: The positional arguments to pass to the superclass save method.
        :param kwargs: The keyword arguments to pass to the superclass save method.
        """

        if not self.code:
            last_code = Institution.objects.aggregate(Max('code'))['code__max']
            if last_code:
                last_number = int(last_code[3:])
                new_number = last_number + 1
            else:
                new_number = 1
            self.code = f'BBI{new_number:05d}'
        super().save(*args, **kwargs)

    class Meta(BaseModel.Meta):
        verbose_name = _("Institution")
        verbose_name_plural = _("Institutions")
        permissions = [
            ("manage_institution_users", "Can manage institution users"),
        ]

    # def add_notification(self, title, message, notification_type='INFO', content_object=None):
    #     return Notification.objects.create(
    #         recipient=self.admin,
    #         title=title,
    #         message=message,
    #         notification_type=notification_type,
    #         institution=self,
    #         content_object=content_object
    #     )

class InstitutionUser(BaseModel):
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name='users')
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='institution_memberships', 
        limit_choices_to={'user_type': User.UserType.B2B_USER}
    )
    role = models.CharField(max_length=50, default="MEMBER")
    code = models.CharField(max_length=15, unique=True, editable=False)
    join_date = models.DateField(auto_now_add=True)

    class Meta(BaseModel.Meta):
        unique_together = ('user', 'institution')
        verbose_name = _("Institution User")
        verbose_name_plural = _("Institution Users")
        indexes = [
            models.Index(fields=['user', 'institution']),
            models.Index(fields=['code']),
        ]

    def __str__(self):
        return f"{self.code} - {self.user.phone_number} - {self.institution.name} ({self.role})"

    def clean(self):
        if self.user.user_type != User.UserType.B2B_USER:
            raise ValidationError(_("Only B2B users can be associated with an institution."))
        if not self.institution.can_add_user():
            raise ValidationError(_("Maximum number of users reached for this institution."))

    def save(self, *args, **kwargs):
        if not self.code:
            institution_code = self.institution.code
            last_user = InstitutionUser.objects.filter(institution=self.institution).aggregate(Max('code'))['code__max']
            if last_user:
                last_number = int(last_user.split('U')[1])
                new_number = last_number + 1
            else:
                new_number = 1
            self.code = f"{institution_code}U{new_number:05d}"
        super().save(*args, **kwargs)

    @classmethod
    def create_institution_user(cls, user, institution, role="MEMBER"):
        if not institution.can_add_user():
            raise ValidationError(_("Maximum number of users reached for this institution."))
        return cls.objects.create(user=user, institution=institution, role=role)
