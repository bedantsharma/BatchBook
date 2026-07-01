from pydantic import BaseModel, Field


class UpdateRazorpayCredentialsRequest(BaseModel):
    razorpay_key_id: str = Field(min_length=1, max_length=200)
    razorpay_key_secret: str = Field(min_length=1, max_length=500)
