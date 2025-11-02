"""
Stripe Payment Integration Module
==================================

Handles all Stripe-related functionality:
- Payment intents
- Subscriptions
- Webhooks
- Customer management
- Usage-based billing
"""

import stripe
import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from loguru import logger
from enum import Enum


class SubscriptionTier(str, Enum):
    """Subscription tier definitions"""
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class StripeConfig:
    """Stripe configuration and price IDs"""
    
    def __init__(self):
        self.api_key = os.getenv("STRIPE_SECRET_KEY")
        self.publishable_key = os.getenv("STRIPE_PUBLISHABLE_KEY")
        self.webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
        
        # Price IDs (set these in your .env)
        self.prices = {
            SubscriptionTier.STARTER: os.getenv("STRIPE_PRICE_STARTER"),
            SubscriptionTier.PRO: os.getenv("STRIPE_PRICE_PRO"),
            SubscriptionTier.ENTERPRISE: os.getenv("STRIPE_PRICE_ENTERPRISE"),
        }
        
        # Usage limits per tier
        self.limits = {
            SubscriptionTier.FREE: {
                "discoveries_per_month": 3,
                "competitors_per_discovery": 10,
                "exports_per_month": 5,
            },
            SubscriptionTier.STARTER: {
                "discoveries_per_month": 20,
                "competitors_per_discovery": 50,
                "exports_per_month": 50,
            },
            SubscriptionTier.PRO: {
                "discoveries_per_month": 100,
                "competitors_per_discovery": 200,
                "exports_per_month": 500,
            },
            SubscriptionTier.ENTERPRISE: {
                "discoveries_per_month": -1,  # unlimited
                "competitors_per_discovery": -1,
                "exports_per_month": -1,
            },
        }
        
        if self.api_key:
            stripe.api_key = self.api_key
            logger.info("Stripe initialized successfully")
        else:
            logger.warning("Stripe API key not found - payment features disabled")


class StripeManager:
    """Main Stripe operations manager"""
    
    def __init__(self, config: StripeConfig):
        self.config = config
        self.enabled = bool(config.api_key)
    
    # =========================================================================
    # CUSTOMER MANAGEMENT
    # =========================================================================
    
    async def create_customer(
        self,
        email: str,
        username: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Create a Stripe customer
        
        Args:
            email: User email
            username: User username
            metadata: Additional metadata
            
        Returns:
            Customer ID or None if failed
        """
        if not self.enabled:
            logger.warning("Stripe not enabled, skipping customer creation")
            return None
        
        try:
            customer = stripe.Customer.create(
                email=email,
                name=username,
                metadata={
                    "username": username,
                    **(metadata or {})
                }
            )
            logger.info(f"Created Stripe customer: {customer.id} for {username}")
            return customer.id
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create Stripe customer: {e}")
            return None
    
    async def get_customer(self, customer_id: str) -> Optional[Dict]:
        """Get customer details"""
        if not self.enabled:
            return None
        
        try:
            customer = stripe.Customer.retrieve(customer_id)
            return customer
        except stripe.error.StripeError as e:
            logger.error(f"Failed to get customer {customer_id}: {e}")
            return None
    
    async def update_customer(
        self,
        customer_id: str,
        **kwargs
    ) -> bool:
        """Update customer information"""
        if not self.enabled:
            return False
        
        try:
            stripe.Customer.modify(customer_id, **kwargs)
            logger.info(f"Updated customer {customer_id}")
            return True
        except stripe.error.StripeError as e:
            logger.error(f"Failed to update customer: {e}")
            return False
    
    # =========================================================================
    # SUBSCRIPTION MANAGEMENT
    # =========================================================================
    
    async def create_checkout_session(
        self,
        customer_id: str,
        tier: SubscriptionTier,
        success_url: str,
        cancel_url: str,
        trial_days: int = 0
    ) -> Optional[str]:
        """
        Create a Stripe Checkout session for subscription
        
        Args:
            customer_id: Stripe customer ID
            tier: Subscription tier
            success_url: URL to redirect on success
            cancel_url: URL to redirect on cancel
            trial_days: Number of trial days (0 = no trial)
            
        Returns:
            Checkout session URL or None
        """
        if not self.enabled:
            logger.warning("Stripe not enabled")
            return None
        
        price_id = self.config.prices.get(tier)
        if not price_id:
            logger.error(f"No price ID configured for tier: {tier}")
            return None
        
        try:
            params = {
                "customer": customer_id,
                "payment_method_types": ["card"],
                "line_items": [{
                    "price": price_id,
                    "quantity": 1,
                }],
                "mode": "subscription",
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": {
                    "tier": tier.value
                }
            }
            
            # Add trial if specified
            if trial_days > 0:
                params["subscription_data"] = {
                    "trial_period_days": trial_days
                }
            
            session = stripe.checkout.Session.create(**params)
            
            logger.info(f"Created checkout session for {customer_id}: {session.id}")
            return session.url
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create checkout session: {e}")
            return None
    
    async def create_subscription(
        self,
        customer_id: str,
        tier: SubscriptionTier,
        trial_days: int = 0
    ) -> Optional[Dict]:
        """
        Create a subscription directly (requires payment method on file)
        
        Returns:
            Subscription object or None
        """
        if not self.enabled:
            return None
        
        price_id = self.config.prices.get(tier)
        if not price_id:
            logger.error(f"No price ID for tier: {tier}")
            return None
        
        try:
            params = {
                "customer": customer_id,
                "items": [{"price": price_id}],
                "metadata": {"tier": tier.value}
            }
            
            if trial_days > 0:
                params["trial_period_days"] = trial_days
            
            subscription = stripe.Subscription.create(**params)
            logger.info(f"Created subscription {subscription.id} for {customer_id}")
            return subscription
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create subscription: {e}")
            return None
    
    async def get_subscription(self, subscription_id: str) -> Optional[Dict]:
        """Get subscription details"""
        if not self.enabled:
            return None
        
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            return subscription
        except stripe.error.StripeError as e:
            logger.error(f"Failed to get subscription: {e}")
            return None
    
    async def cancel_subscription(
        self,
        subscription_id: str,
        immediately: bool = False
    ) -> bool:
        """
        Cancel a subscription
        
        Args:
            subscription_id: Subscription ID
            immediately: If True, cancel immediately. If False, cancel at period end.
        """
        if not self.enabled:
            return False
        
        try:
            if immediately:
                stripe.Subscription.delete(subscription_id)
                logger.info(f"Cancelled subscription immediately: {subscription_id}")
            else:
                stripe.Subscription.modify(
                    subscription_id,
                    cancel_at_period_end=True
                )
                logger.info(f"Scheduled subscription cancellation: {subscription_id}")
            return True
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to cancel subscription: {e}")
            return False
    
    async def update_subscription(
        self,
        subscription_id: str,
        new_tier: SubscriptionTier
    ) -> Optional[Dict]:
        """
        Update subscription to a new tier
        
        Args:
            subscription_id: Current subscription ID
            new_tier: New tier to upgrade/downgrade to
        """
        if not self.enabled:
            return None
        
        price_id = self.config.prices.get(new_tier)
        if not price_id:
            logger.error(f"No price ID for tier: {new_tier}")
            return None
        
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            
            stripe.Subscription.modify(
                subscription_id,
                items=[{
                    "id": subscription["items"]["data"][0].id,
                    "price": price_id,
                }],
                metadata={"tier": new_tier.value}
            )
            
            logger.info(f"Updated subscription {subscription_id} to {new_tier}")
            return subscription
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to update subscription: {e}")
            return None
    
    async def list_customer_subscriptions(
        self,
        customer_id: str
    ) -> List[Dict]:
        """Get all subscriptions for a customer"""
        if not self.enabled:
            return []
        
        try:
            subscriptions = stripe.Subscription.list(
                customer=customer_id,
                status="all"
            )
            return subscriptions.data
        except stripe.error.StripeError as e:
            logger.error(f"Failed to list subscriptions: {e}")
            return []
    
    # =========================================================================
    # USAGE TRACKING (for usage-based billing)
    # =========================================================================
    
    async def report_usage(
        self,
        subscription_item_id: str,
        quantity: int,
        action: str = "increment"
    ) -> bool:
        """
        Report usage for metered billing
        
        Args:
            subscription_item_id: The subscription item ID
            quantity: Usage quantity
            action: "increment" or "set"
        """
        if not self.enabled:
            return False
        
        try:
            stripe.SubscriptionItem.create_usage_record(
                subscription_item_id,
                quantity=quantity,
                action=action,
                timestamp=int(datetime.utcnow().timestamp())
            )
            logger.info(f"Reported usage: {quantity} for item {subscription_item_id}")
            return True
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to report usage: {e}")
            return False
    
    # =========================================================================
    # PAYMENT INTENTS (for one-time payments)
    # =========================================================================
    
    async def create_payment_intent(
        self,
        amount: int,
        currency: str = "usd",
        customer_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        Create a payment intent for one-time payment
        
        Args:
            amount: Amount in cents (e.g., 1000 = $10.00)
            currency: Currency code
            customer_id: Optional Stripe customer ID
            metadata: Additional metadata
        """
        if not self.enabled:
            return None
        
        try:
            params = {
                "amount": amount,
                "currency": currency,
                "metadata": metadata or {}
            }
            
            if customer_id:
                params["customer"] = customer_id
            
            intent = stripe.PaymentIntent.create(**params)
            logger.info(f"Created payment intent: {intent.id} for ${amount/100}")
            return {
                "client_secret": intent.client_secret,
                "id": intent.id
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create payment intent: {e}")
            return None
    
    # =========================================================================
    # BILLING PORTAL
    # =========================================================================
    
    async def create_billing_portal_session(
        self,
        customer_id: str,
        return_url: str
    ) -> Optional[str]:
        """
        Create a billing portal session for customer to manage subscription
        
        Returns:
            Portal URL or None
        """
        if not self.enabled:
            return None
        
        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url
            )
            logger.info(f"Created billing portal for {customer_id}")
            return session.url
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create billing portal: {e}")
            return None
    
    # =========================================================================
    # WEBHOOKS
    # =========================================================================
    
    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str
    ) -> Optional[Dict]:
        """
        Verify webhook signature and parse event
        
        Args:
            payload: Raw request body
            signature: Stripe-Signature header
            
        Returns:
            Parsed event or None if verification fails
        """
        if not self.enabled or not self.config.webhook_secret:
            logger.warning("Webhook secret not configured")
            return None
        
        try:
            event = stripe.Webhook.construct_event(
                payload,
                signature,
                self.config.webhook_secret
            )
            return event
            
        except ValueError as e:
            logger.error(f"Invalid webhook payload: {e}")
            return None
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Invalid webhook signature: {e}")
            return None
    
    async def handle_webhook_event(self, event: Dict) -> Dict[str, Any]:
        """
        Handle Stripe webhook events
        
        Returns:
            Dict with status and any data to update in your DB
        """
        event_type = event["type"]
        data = event["data"]["object"]
        
        logger.info(f"Processing webhook: {event_type}")
        
        result = {
            "status": "success",
            "event_type": event_type,
            "updates": {}
        }
        
        try:
            # Subscription events
            if event_type == "customer.subscription.created":
                result["updates"] = {
                    "subscription_id": data["id"],
                    "customer_id": data["customer"],
                    "status": data["status"],
                    "current_period_end": data["current_period_end"],
                    "tier": data["metadata"].get("tier", "unknown")
                }
                
            elif event_type == "customer.subscription.updated":
                result["updates"] = {
                    "subscription_id": data["id"],
                    "status": data["status"],
                    "current_period_end": data["current_period_end"],
                    "cancel_at_period_end": data["cancel_at_period_end"]
                }
                
            elif event_type == "customer.subscription.deleted":
                result["updates"] = {
                    "subscription_id": data["id"],
                    "status": "cancelled",
                    "cancelled_at": data["canceled_at"]
                }
            
            # Payment events
            elif event_type == "invoice.payment_succeeded":
                result["updates"] = {
                    "subscription_id": data.get("subscription"),
                    "invoice_id": data["id"],
                    "amount_paid": data["amount_paid"],
                    "payment_status": "paid"
                }
                
            elif event_type == "invoice.payment_failed":
                result["updates"] = {
                    "subscription_id": data.get("subscription"),
                    "invoice_id": data["id"],
                    "payment_status": "failed",
                    "attempt_count": data["attempt_count"]
                }
            
            # Customer events
            elif event_type == "customer.created":
                result["updates"] = {
                    "customer_id": data["id"],
                    "email": data["email"]
                }
            
            logger.info(f"Webhook handled: {event_type}")
            
        except Exception as e:
            logger.error(f"Error handling webhook {event_type}: {e}")
            result["status"] = "error"
            result["error"] = str(e)
        
        return result
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def get_tier_limits(self, tier: SubscriptionTier) -> Dict[str, int]:
        """Get usage limits for a tier"""
        return self.config.limits.get(tier, self.config.limits[SubscriptionTier.FREE])
    
    def is_within_limits(
        self,
        tier: SubscriptionTier,
        current_usage: Dict[str, int]
    ) -> Dict[str, bool]:
        """
        Check if current usage is within tier limits
        
        Returns:
            Dict mapping limit names to boolean (True = within limit)
        """
        limits = self.get_tier_limits(tier)
        result = {}
        
        for key, limit in limits.items():
            current = current_usage.get(key, 0)
            # -1 means unlimited
            result[key] = limit == -1 or current < limit
        
        return result


# =========================================================================
# SINGLETON INSTANCE
# =========================================================================

# Initialize config
stripe_config = StripeConfig()

# Initialize manager
stripe_manager = StripeManager(stripe_config)


# =========================================================================
# CONVENIENCE FUNCTIONS
# =========================================================================

async def create_customer(email: str, username: str) -> Optional[str]:
    """Convenience function to create customer"""
    return await stripe_manager.create_customer(email, username)


async def create_checkout_session(
    customer_id: str,
    tier: SubscriptionTier,
    success_url: str,
    cancel_url: str
) -> Optional[str]:
    """Convenience function to create checkout"""
    return await stripe_manager.create_checkout_session(
        customer_id, tier, success_url, cancel_url
    )


async def handle_webhook(payload: bytes, signature: str) -> Optional[Dict]:
    """Convenience function to handle webhook"""
    event = stripe_manager.verify_webhook_signature(payload, signature)
    if event:
        return await stripe_manager.handle_webhook_event(event)
    return None
