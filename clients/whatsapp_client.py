import httpx

from config import get_settings

GRAPH_API_VERSION = "v23.0"


async def send_template_message(
    to: str,
    template_name: str,
    language: str = "en",
    components: list | None = None,
) -> dict:
    settings = get_settings()
    if not settings.meta_whatsapp_token or not settings.meta_whatsapp_phone_number_id:
        raise RuntimeError(
            "Meta WhatsApp credentials not configured — "
            "set META_WHATSAPP_TOKEN and META_WHATSAPP_PHONE_NUMBER_ID in .env"
        )

    url = (
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/"
        f"{settings.meta_whatsapp_phone_number_id}/messages"
    )
    template: dict = {"name": template_name, "language": {"code": language}}
    if components:
        template["components"] = components

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": template,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {settings.meta_whatsapp_token}"},
            json=payload,
            timeout=10.0,
        )
    response.raise_for_status()
    return response.json()
