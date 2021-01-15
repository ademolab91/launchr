from logging import getLogger

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property
from djstripe.exceptions import MultipleSubscriptionException
from djstripe.models import Customer, Plan
from djstripe.models import Subscription

logger = getLogger(__name__)


class User(AbstractUser):
    newsletter = models.BooleanField(
        default=True
    )

    @cached_property
    def customer(self):
        customer, _ = Customer.get_or_create(self)
        return customer

    @cached_property
    def has_active_subscription(self):
        """Checks if a user has an active subscription."""
        try:
            return self.customer.subscription is not None
        except MultipleSubscriptionException:
            return True

    @cached_property
    def invoices(self):
        return self.customer.invoices.all()

    @property
    def is_trialling(self):
        return not self.has_active_subscription and self.trial_ends_at > timezone.now()

    @property
    def trial_ends_at(self):
        return self.date_joined + timezone.timedelta(days=settings.TRIAL_DAYS)

    @cached_property
    def plan(self):
        if self.stripe_plan:
            return self.get_plan_by_stripe_id(
                self.stripe_plan.id
            )
        return None

    @cached_property
    def stripe_plan(self):
        if self.has_active_subscription:
            try:
                return self.customer.subscription.plan
            except MultipleSubscriptionException:
                return self.customer.subscriptions.latest().plan
        if self.is_trialling:
            return Plan.objects.get(
                id=self.get_stripe_plan_id_by_key(settings.TRIAL_PLAN_KEY)
            )
        return None

    def can_use_feature(self, feature_key):
        if self.plan:
            for feature in self.plan.get('features', []):
                if feature['key'] == feature_key:
                    return feature['enabled']
            plan_uuid = self.get_plan_by_stripe_id(self.plan.id)
            raise ImproperlyConfigured(
                f"Unable to find the feature with feature_key '{feature_key}' for the plan \n"
                f"with the uuid '{plan_uuid}'. Make sure to add it to the features list in \n"
                f"your settings.\n"
                f"See: https://getlaunchr.com/docs/subscriptions/#can_use_feature"
            )
        return False

    @staticmethod
    def get_plan_by_stripe_id(stripe_id):
        for plan in settings.PLANS.values():
            if plan['stripe_id'] == stripe_id:
                return plan
        raise ImproperlyConfigured(
            f"Unable to find a configured plan for the stripe_id '{stripe_id}'.\n"
            f"Make sure to add the 'stripe_id' to one of your plans in your settings.\n"
            f"See: https://getlaunchr.com/docs/subscriptions/#get_plan_by_stripe_id"
        )

    @staticmethod
    def get_stripe_plan_id_by_key(plan_key):
        stripe_id = settings.PLANS.get(plan_key, {}).get('stripe_id', None)
        if not stripe_id:
            raise ImproperlyConfigured(
                f"Unable to get the stripe_id for the plan with the key '{plan_key}'.\n"
                f"Make sure to set the 'stripe_id' in your settings correctly.\n"
                f"See: https://getlaunchr.com/docs/subscriptions/#get_stripe_plan_id_by_key"
            )
        return stripe_id