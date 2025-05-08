import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

def validate_phone_number(value):
    """
    Validate phone number format
    """
    if not re.match(r'^\+?1?\d{9,15}$', value):
        raise ValidationError(
            _('Enter a valid phone number.'),
            code='invalid_phone_number'
        )

def validate_strong_password(password):
    """
    Validate password strength
    """
    if len(password) < 8:
        raise ValidationError(_('Password must be at least 8 characters long.'))
    
    if not re.search(r'[A-Z]', password):
        raise ValidationError(_('Password must contain at least one uppercase letter.'))
    
    if not re.search(r'[a-z]', password):
        raise ValidationError(_('Password must contain at least one lowercase letter.'))
    
    if not re.search(r'\d', password):
        raise ValidationError(_('Password must contain at least one number.'))
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        raise ValidationError(_('Password must contain at least one special character.'))