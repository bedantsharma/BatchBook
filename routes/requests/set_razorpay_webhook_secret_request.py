from pydantic import BaseModel, Field


class SetRazorpayWebhookSecretRequest(BaseModel):
    razorpay_webhook_secret: str = Field(min_length=1, max_length=500)
