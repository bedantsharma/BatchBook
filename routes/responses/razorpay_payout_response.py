from pydantic import BaseModel


class RazorpayPayoutResponse(BaseModel):
    status: str  # "NOT_CONNECTED" | "CONNECTED" | "NEEDS_RECONNECT"
    key_id: str | None = None
    secret_configured: bool
    webhook_configured: bool = False
