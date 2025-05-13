from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.db import transaction
from model_utils import FieldTracker
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class InstrumentType(models.TextChoices):
    EQUITY = 'EQUITY', 'Equity'
    FUTURE = 'FNO_FUT', 'F&O Future'
    CALL_OPTION = 'FNO_CE', 'Call Option'
    PUT_OPTION = 'FNO_PE', 'Put Option'
   

    @classmethod
    def get_segment(cls, value):
        segments = {
            cls.EQUITY: 'EQUITY',
            cls.FUTURE: 'FNO',
            cls.CALL_OPTION: 'FNO',
            cls.PUT_OPTION: 'FNO',
        }
        return segments.get(value)

    @classmethod
    def get_fno_type(cls, value):
        fno_types = {
            cls.FUTURE: 'FUTURE',
            cls.CALL_OPTION: 'OPTION',
            cls.PUT_OPTION: 'OPTION',
        }
        return fno_types.get(value)

    @classmethod
    def get_option_type(cls, value):
        option_types = {
            cls.CALL_OPTION: 'CE',
            cls.PUT_OPTION: 'PE',
        }
        return option_types.get(value)

class Company(models.Model):
    token_id = models.PositiveIntegerField(
        unique=True, 
        db_index=True,
        help_text="Unique identifier for the trading instrument"
    )
    exchange = models.CharField(
        max_length=10, 
        db_index=True,
        help_text="Stock exchange where the instrument is traded"
    )
    trading_symbol = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Trading symbol used on the exchange"
    )
    script_name = models.CharField(
        max_length=100,
        help_text="Full name of the trading instrument"
    )
    expiry_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Expiry date for F&O instruments"
    )
    display_name = models.CharField(
        max_length=255,
        help_text="User-friendly display name"
    )
    instrument_type = models.CharField(
        max_length=20,
        choices=InstrumentType.choices,
        default=InstrumentType.EQUITY,
        db_index=True,
        help_text="Type of trading instrument"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether the instrument is currently tradeable"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Companies"
        indexes = [
            models.Index(fields=['trading_symbol', 'exchange', 'instrument_type']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['trading_symbol', 'exchange', 'instrument_type', 'expiry_date'],
                name='unique_trading_instrument'
            )
        ]

    def __str__(self):
        return f"{self.exchange}:{self.trading_symbol}"

    @property
    def segment(self):
        return InstrumentType.get_segment(self.instrument_type)

    @property
    def fno_type(self):
        return InstrumentType.get_fno_type(self.instrument_type)

    @property
    def option_type(self):
        return InstrumentType.get_option_type(self.instrument_type)

    def clean(self):
        super().clean()
        if self.instrument_type in [InstrumentType.FUTURE, InstrumentType.CALL_OPTION, InstrumentType.PUT_OPTION]:
            if not self.expiry_date:
                raise ValidationError("Expiry date is required for F&O instruments")
            if self.expiry_date < timezone.now().date():
                raise ValidationError("Expiry date cannot be in the past")

class Trade(models.Model):
    class TradeType(models.TextChoices):
        INTRADAY = 'INTRADAY', 'Intraday'
        POSITIONAL = 'POSITIONAL', 'Positional'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        ACTIVE = 'ACTIVE', 'Active'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    class PlanType(models.TextChoices):
        BASIC = 'BASIC', 'Basic'
        PREMIUM = 'PREMIUM', 'Premium'
        SUPER_PREMIUM = 'SUPER_PREMIUM', 'Super Premium'

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name='trades'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='trades'
    )
    trade_type = models.CharField(
        max_length=20,
        choices=TradeType.choices,
        db_index=True,
        help_text="Type of trade (Intraday/Positional)"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        help_text="Current status of the trade"
    )
    plan_type = models.CharField(
        max_length=15,
        choices=PlanType.choices,
        default=PlanType.BASIC,
        help_text="Subscription plan type for this trade"
    )

    warzone = models.DecimalField(
        max_digits=10,  
        decimal_places=2,
        default=0.0,
        help_text="Risk level indicator for the trade"
    )
    warzone_history = models.JSONField(
        default=list,
        blank=True,
        null=True,
        help_text="History of warzone changes"
    )
    is_free_call = models.BooleanField(
        default=False,
        help_text="Indicates if this is a free trading signal"
    )
    image = models.ImageField(
        upload_to='trade_images/%Y/%m/',
        null=True,
        blank=True,
        help_text="Technical analysis chart or related image"
    )
    tracker = FieldTracker(fields=['status', 'image', 'warzone'])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the trade was completed or cancelled"
    )

    class Meta:
        indexes = [
            models.Index(fields=['status', 'trade_type', 'plan_type']),
            models.Index(fields=['created_at', 'user']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.company} - {self.trade_type} - {self.status}"

    def clean(self):
        super().clean()
        
        # Get existing active trades for the same company token_id
        existing_trades = Trade.objects.filter(
            company__token_id=self.company.token_id,
            status__in=[self.Status.PENDING, self.Status.ACTIVE]
        ).exclude(pk=self.pk)  # Exclude current trade when updating
        print(existing_trades,'---------------------------------------------existing_trades-----------------------------------------')
        if existing_trades.exists():
            existing_trade_type = existing_trades.first().trade_type
            if existing_trade_type == self.trade_type and self.status == self.Status.ACTIVE:
                raise ValidationError(
                    f"A {self.trade_type.lower()} trade already exists for this company. "
                    f"Only one {self.trade_type.lower()} trade is allowed per company."
                )
            elif len(existing_trades) >= 2:
                raise ValidationError(
                    "Maximum limit of trades reached for this company. "
                    "Only one intraday and one positional trade are allowed."
                )

    def save(self, *args, **kwargs):
        """Override save to handle trade status changes and notifications."""
        is_new = self.pk is None
        old_status = None
        
        if not is_new:
            old_instance = Trade.objects.get(pk=self.pk)
            old_status = old_instance.status

        self.clean()  # Run validation before saving
        
        if self.status in [self.Status.COMPLETED, self.Status.CANCELLED]:
            self.completed_at = timezone.now()
            
        super().save(*args, **kwargs)
        
        # Handle status changes and notifications
        if not is_new and old_status != self.status:
            from django.db.models.signals import post_save
            post_save.send(sender=self.__class__, instance=self, created=False)

    @classmethod
    def get_available_trade_types(cls, company_token_id):
        """
        Returns available trade types for a given company token ID.
        """
        existing_trades = cls.objects.filter(
            company__token_id=company_token_id,
            status__in=[cls.Status.PENDING, cls.Status.ACTIVE]
        )
        print(existing_trades,'------------------------------existing_trades------------------------------------------')
        all_types = set(cls.TradeType.values)
        print(all_types,'------------------------------all_types------------------------------------------')
        used_types = set(existing_trades.values_list('trade_type', flat=True))
        print(used_types,'------------------------------used_types------------------------------------------')
        
        return list(all_types - used_types)
    
    def update_warzone(self, new_value):
        # Store current value in history before updating
        current_history = self.warzone_history or []
        
        # Limit history to 20 entries
        if len(current_history) >= 20:
            current_history.pop(0)  # Remove oldest entry
        
        # Add new change to history
        current_history.append({
            'value': float(new_value),
            'changed_at': timezone.now().isoformat()
        })
        
        # Update warzone and history
        self.warzone = new_value
        self.warzone_history = current_history
        self.save()

    @classmethod
    def get_trades_for_subscription(cls, user, subscription):
        """
        Get trades based on subscription level and user's subscription date.
        Returns appropriate number of previous and new trades.
        """
        if not subscription or not subscription.is_active:
            logger.warning(f"No active subscription found for user {user.id}")
            return cls.objects.none()

        subscription_date = subscription.start_date
        now = timezone.now()
        logger.info(f"Getting trades for user {user.id} with {subscription.plan.name} subscription")

        # Get allowed plan types based on subscription
        allowed_plan_types = cls._get_allowed_plan_types(subscription.plan.name)
        logger.info(f"Allowed plan types for {subscription.plan.name}: {allowed_plan_types}")

        # Base query for all trades
        base_query = cls.objects.filter(
            plan_type__in=allowed_plan_types,
            created_at__lte=now
        ).select_related('company', 'analysis')

        # Get active trades
        active_trades = base_query.filter(
            status=cls.Status.ACTIVE
        ).order_by('-created_at')

        # Get completed trades after subscription
        completed_trades = base_query.filter(
            status=cls.Status.COMPLETED,
            completed_at__gte=subscription_date
        ).order_by('-created_at')

        # Get previous trades (before subscription)
        previous_trades = base_query.filter(
            created_at__lt=subscription_date,
            status__in=[cls.Status.COMPLETED, cls.Status.CANCELLED]
        ).order_by('-created_at')

        # Apply subscription-based limits
        if subscription.plan.name == 'BASIC':
            # Get 6 previous trades
            previous = previous_trades[:6]
            # Get 6 newest trades (active or completed after subscription)
            newest = (active_trades | completed_trades).distinct().order_by('-created_at')[:6]
            result = (previous | newest).distinct().order_by('-created_at')
            logger.info(f"BASIC plan: returning {result.count()} trades")
            return result
        elif subscription.plan.name == 'PREMIUM':
            # Get 6 previous trades
            previous = previous_trades[:6]
            # Get 9 newest trades
            newest = (active_trades | completed_trades).distinct().order_by('-created_at')[:9]
            result = (previous | newest).distinct().order_by('-created_at')
            logger.info(f"PREMIUM plan: returning {result.count()} trades")
            return result
        else:  # SUPER_PREMIUM or FREE_TRIAL
            result = (active_trades | completed_trades | previous_trades).distinct().order_by('-created_at')
            logger.info(f"SUPER_PREMIUM plan: returning {result.count()} trades")
            return result

    @property
    def is_accessible_to_user(self, user):
        """
        Check if a trade is accessible to a user based on their subscription.
        """
        if not user.is_authenticated:
            return False

        subscription = user.get_active_subscription()
        if not subscription:
            return False

        # Free trial users get same access as SUPER_PREMIUM
        if subscription.plan.name == 'FREE_TRIAL':
            return True

        # Check if trade was created after user's subscription
        if self.created_at < subscription.start_date:
            return False

        # Check plan type access
        if subscription.plan.name == 'BASIC':
            return self.plan_type in ['BASIC', 'PREMIUM', 'SUPER_PREMIUM']
        elif subscription.plan.name == 'PREMIUM':
            return self.plan_type in ['PREMIUM', 'SUPER_PREMIUM']
        elif subscription.plan.name == 'SUPER_PREMIUM':
            return self.plan_type == 'SUPER_PREMIUM'

        return False

class TradeHistory(models.Model):
    trade = models.ForeignKey(
        Trade,
        on_delete=models.CASCADE,
        related_name='history'
    )
    buy = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Entry price point"
    )
    target = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Target price for the trade"
    )
    sl = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="Stop Loss",
        help_text="Stop loss price point"
    )
    tracker = FieldTracker(fields=['buy', 'target', 'sl'])
    timestamp = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Trade histories"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['trade', 'timestamp']),
        ]
        get_latest_by = 'timestamp'  # Specify which field to use for latest()

    def __str__(self):
        return f"{self.trade} - {self.timestamp}"

    def clean(self):
        super().clean()
        if self.sl >= self.buy:
            raise ValidationError("Stop loss must be lower than buy price")
        if self.target <= self.buy:
            raise ValidationError("Target must be higher than buy price")

    # @property
    # def risk_reward_ratio(self):
    #     potential_profit = abs(self.target - self.buy)
    #     potential_loss = abs(self.buy - self.sl)
    #     return round(potential_profit / potential_loss, 2) if potential_loss else None

    # @property
    # def potential_profit_percentage(self):
    #     return round(((self.target - self.buy) / self.buy * 100), 2) if self.buy else None

    # @property
    # def stop_loss_percentage(self):
    #     return round(((self.buy - self.sl) / self.buy * 100), 2) if self.buy else None

    @property
    def risk_reward_ratio(self):
        potential_profit = abs(self.target - self.buy)
        potential_loss = abs(self.buy - self.sl)
        return abs(potential_profit / potential_loss) if potential_loss else None

    @property
    def potential_profit_percentage(self):
        return abs((self.target - self.buy) / self.buy * 100) if self.buy else None

    @property
    def stop_loss_percentage(self):
        return abs((self.buy - self.sl) / self.buy * 100) if self.buy else None


class Analysis(models.Model):
    """
    Provides detailed analysis for a trade including bull/bear scenarios.
    """
    class Sentiment(models.TextChoices):
        BEARISH = 'BEARISH', 'Bearish'
        BULLISH = 'BULLISH', 'Bullish'
        NEUTRAL = 'NEUTRAL', 'Neutral'

    trade = models.OneToOneField(
        Trade,
        on_delete=models.CASCADE,
        related_name='analysis'
    )
    bull_scenario = models.TextField(
        help_text="Analysis of potential bullish outcomes",
        null=True,
        blank=True,
        
    )
    bear_scenario = models.TextField(
        help_text="Analysis of potential bearish outcomes",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Sentiment.choices,
        default=Sentiment.NEUTRAL,
        help_text="Current market sentiment"
    )
    tracker = FieldTracker(fields=['bull_scenario', 'bear_scenario', 'status'])
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the analysis was completed"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Analyses"

    def __str__(self):
        return f"Analysis for {self.trade}"

    def mark_complete(self):
        """Mark the analysis as complete with current timestamp."""
        self.completed_at = timezone.now()
        self.save()


class Insight(models.Model):
    """
    Captures the outcome, accuracy of trade predictions and detailed analysis results.
    """
    class AnalysisSection(models.TextChoices):
        OVERVIEW = 'OVERVIEW', 'Overview'
        TECHNICAL = 'TECHNICAL', 'Technical Analysis'
        FUNDAMENTAL = 'FUNDAMENTAL', 'Fundamental Analysis'
        RISK = 'RISK', 'Risk Analysis'
        RECOMMENDATION = 'RECOMMENDATION', 'Recommendation'
        OTHER = 'OTHER', 'Other Insights'

    class ParagraphType(models.TextChoices):
        SUMMARY = 'SUMMARY', 'Summary'
        KEY_POINTS = 'KEY_POINTS', 'Key Points'
        DETAILS = 'DETAILS', 'Detailed Analysis'
        CONCLUSION = 'CONCLUSION', 'Conclusion'

    trade = models.OneToOneField(
        Trade,
        on_delete=models.CASCADE,
        related_name='insight'
    )
    prediction_image = models.ImageField(
        upload_to='trade_insights/predictions/',
        help_text="Technical analysis prediction chart"
        
    )
    actual_image = models.ImageField(
        upload_to='trade_insights/actuals/',
        null=True,
        blank=True,
        help_text="Actual outcome chart"
    )
    prediction_description = models.TextField(
        help_text="Detailed description of the predicted outcome"
    )
    actual_description = models.TextField(
        null=True,
        blank=True,
        help_text="Description of the actual outcome"
    )
    accuracy_score = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percentage accuracy of the prediction"
    )
    analysis_result = models.JSONField(
        null=True,
        blank=True,
        help_text="Structured analysis result with sections and paragraphs",
        default=dict
    )
    tracker = FieldTracker(fields=['prediction_description', 'actual_description', 'accuracy_score'])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Insight for {self.trade}"

    def clean(self):
        super().clean()
        
        # Check if the associated trade is completed
        if self.trade.status != Trade.Status.COMPLETED:
            raise ValidationError(
                "The Prediction vs Actual analysis Result will be updated once the trade has expired."
                f"Current trade status: {self.trade.get_status_display()}"
            )

    def save(self, *args, **kwargs):
        self.clean()  # Run validation before saving
        super().save(*args, **kwargs)

    @property
    def is_accurate(self):
        """Determine if the prediction was accurate (>80% accuracy score)."""
        return self.accuracy_score and self.accuracy_score >= 80

    def add_paragraph(self, section_type, paragraph_type, content, order=None):
        """
        Add or update a paragraph in a section
        """
        if not self.analysis_result:
            self.analysis_result = {'sections': {}}

        if section_type not in self.AnalysisSection.values:
            raise ValidationError(f"Invalid section type: {section_type}")

        if paragraph_type not in self.ParagraphType.values:
            raise ValidationError(f"Invalid paragraph type: {paragraph_type}")

        if section_type not in self.analysis_result['sections']:
            self.analysis_result['sections'][section_type] = {
                'paragraphs': [],
                'last_updated': timezone.now().isoformat()
            }

        paragraph_data = {
            'type': paragraph_type,
            'content': content,
            'order': order if order is not None else len(self.analysis_result['sections'][section_type]['paragraphs']) + 1,
            'last_updated': timezone.now().isoformat()
        }

        section = self.analysis_result['sections'][section_type]
        updated = False
        for i, para in enumerate(section['paragraphs']):
            if para['type'] == paragraph_type:
                section['paragraphs'][i] = paragraph_data
                updated = True
                break

        if not updated:
            section['paragraphs'].append(paragraph_data)

        section['paragraphs'].sort(key=lambda x: x['order'])
        section['last_updated'] = timezone.now().isoformat()
        self.save()

    def get_section_paragraphs(self, section_type):
        """
        Get all paragraphs from a specific section
        """
        if not self.analysis_result or 'sections' not in self.analysis_result:
            return None
            
        section = self.analysis_result['sections'].get(section_type)
        return section['paragraphs'] if section else None

    def get_paragraph(self, section_type, paragraph_type):
        """
        Get a specific paragraph from a section
        """
        paragraphs = self.get_section_paragraphs(section_type)
        if not paragraphs:
            return None
            
        for para in paragraphs:
            if para['type'] == paragraph_type:
                return para['content']
        return None

    def get_formatted_analysis(self, include_metadata=False):
        """
        Get the complete analysis in a formatted string
        """
        if not self.analysis_result or 'sections' not in self.analysis_result:
            return "No analysis available"

        formatted_text = []
        for section_type, section_data in self.analysis_result['sections'].items():
            section_title = dict(self.AnalysisSection.choices)[section_type]
            formatted_text.append(f"\n## {section_title}")
            
            if include_metadata:
                formatted_text.append(f"Last Updated: {section_data['last_updated']}\n")

            for para in section_data['paragraphs']:
                para_title = dict(self.ParagraphType.choices)[para['type']]
                formatted_text.append(f"### {para_title}")
                formatted_text.append(para['content'])
                formatted_text.append("")  # Empty line between paragraphs

        return "\n".join(formatted_text)

    def calculate_accuracy(self):
        """
        Calculate accuracy based on predicted vs actual outcome.
        Should be implemented based on specific business logic.
        """
        # Placeholder for accuracy calculation logic
        pass










class FreeCallTrade(models.Model):
    TRADE_TYPE_CHOICES = [
        ('INTRADAY', 'Intraday'),
        ('POSITIONAL', 'Positional'),
    ]
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]
    SENTIMENT_CHOICES = [
        ('BEARISH', 'Bearish'),
        ('BULLISH', 'Bullish'),
        ('NEUTRAL', 'Neutral'),
    ]

    company = models.ForeignKey('Company', on_delete=models.CASCADE, related_name='free_call_trades')
   # company = models.CharField(max_length=20,default="NIFTY 50")
    trade_type = models.CharField(max_length=20, choices=TRADE_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    sentiment = models.CharField(max_length=20, choices=SENTIMENT_CHOICES, default='NEUTRAL')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_free_calls')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    def clean(self):
        # if not self.company.trading_symbol.startswith('NIFTY'):
        #     raise ValidationError("Only NIFTY stocks can be given as free calls.")
        
        # Check if there's already an active trade of the same type for this company
        existing_active_trade = FreeCallTrade.objects.filter(
            company=self.company,
            trade_type=self.trade_type,
            status='ACTIVE'
        ).exclude(pk=self.pk).first()
        
        if existing_active_trade:
            raise ValidationError(
                f"An active {self.trade_type.lower()} trade already exists for {self.company.trading_symbol}. "
                f"Only one active trade per type (intraday/positional) is allowed per company."
            )

    def save(self, *args, **kwargs):
        try:
            self.full_clean()  # This will run validation before saving
            if self.status == 'ACTIVE':
                # Set all other companies' active trades to completed
                with transaction.atomic():
                    FreeCallTrade.objects.filter(
                        status='ACTIVE',
                        is_deleted=False
                    ).exclude(
                        pk=self.pk
                    ).exclude(
                        company__id=self.company_id
                    ).update(
                        status='COMPLETED'
                    )
                    super().save(*args, **kwargs)
            else:
                super().save(*args, **kwargs)
        except ValidationError as e:
            raise ValidationError(e.message_dict)

class FreeCallTradeHistory(models.Model):
    trade = models.ForeignKey(FreeCallTrade, on_delete=models.CASCADE, related_name='history')
    buy = models.DecimalField(max_digits=10, decimal_places=2)
    target = models.DecimalField(max_digits=10, decimal_places=2)
    sl = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Stop Loss")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        get_latest_by = 'timestamp'
    @property
    def risk_reward_ratio(self):
        potential_profit = abs(self.target - self.buy)
        potential_loss = abs(self.buy - self.sl)
        return round(potential_profit / potential_loss, 2) if potential_loss else None

    @property
    def potential_profit_percentage(self):
        return round(((self.target - self.buy) / self.buy * 100), 2) if self.buy else None

    @property
    def stop_loss_percentage(self):
        return round(((self.buy - self.sl) / self.buy * 100), 2) if self.buy else None

class TradeNotification(models.Model):
    """Model for storing trade-related notifications."""
    
    class NotificationType(models.TextChoices):
        TRADE_UPDATE = 'TRADE_UPDATE', 'Trade Update'
        TRADE_COMPLETED = 'TRADE_COMPLETED', 'Trade Completed'
        TRADE_CANCELLED = 'TRADE_CANCELLED', 'Trade Cancelled'
        TRADE_ACTIVATED = 'TRADE_ACTIVATED', 'Trade Activated'

    class Priority(models.TextChoices):
        LOW = 'LOW', 'Low'
        NORMAL = 'NORMAL', 'Normal'
        HIGH = 'HIGH', 'High'
        URGENT = 'URGENT', 'Urgent'

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='trades_trade_notifications'
    )
    trade = models.ForeignKey(
        'Trade',
        on_delete=models.CASCADE,
        related_name='trades_notifications'
    )
    notification_type = models.CharField(
        max_length=20,
        choices=NotificationType.choices,
        help_text="Type of notification"
    )
    message = models.TextField(
        help_text="Notification message"
    )
    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.NORMAL,
        help_text="Notification priority level"
    )
    is_read = models.BooleanField(
        default=False,
        help_text="Whether the notification has been read"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['created_at']),
        ]
        app_label = 'trades'

    def __str__(self):
        return f"{self.notification_type} - {self.user.username}"

    @classmethod
    def create_trade_notification(cls, user, trade, notification_type, message, priority=Priority.NORMAL):
        """Create a new trade notification."""
        return cls.objects.create(
            user=user,
            trade=trade,
            notification_type=notification_type,
            message=message,
            priority=priority
        )
