import zlib

COLOR_PRESETS: dict[str, dict[str, str]] = {
    "indigo": {"primary": "#3730A3", "accent": "#6366F1", "background": "#F5F5FF"},
    "teal": {"primary": "#0F766E", "accent": "#14B8A6", "background": "#F0FDFA"},
    "maroon": {"primary": "#9F1239", "accent": "#E11D48", "background": "#FFF1F2"},
    "forest": {"primary": "#166534", "accent": "#22C55E", "background": "#F0FDF4"},
    "slate": {"primary": "#1E293B", "accent": "#475569", "background": "#F8FAFC"},
    "amber": {"primary": "#92400E", "accent": "#F59E0B", "background": "#FFFBEB"},
    "plum": {"primary": "#6B21A8", "accent": "#A855F7", "background": "#FAF5FF"},
    "ocean": {"primary": "#075985", "accent": "#0EA5E9", "background": "#F0F9FF"},
    "terracotta": {"primary": "#9A3412", "accent": "#EA580C", "background": "#FFF7ED"},
    "charcoal-gold": {"primary": "#292524", "accent": "#CA8A04", "background": "#FAFAF9"},
}

PRESET_NAMES: list[str] = list(COLOR_PRESETS.keys())


def is_valid_color_scheme(name: str) -> bool:
    return name in COLOR_PRESETS


def resolve_color_scheme(slug: str, requested: str | None) -> str:
    """Resolve the color-scheme name to persist for a given slug.

    Raises:
        ValueError: If `requested` is given but isn't one of the fixed presets.
    """
    if requested is not None:
        if not is_valid_color_scheme(requested):
            raise ValueError(
                f"'{requested}' is not a valid color scheme — choose one of {PRESET_NAMES}"
            )
        return requested
    return PRESET_NAMES[zlib.crc32(slug.encode()) % len(PRESET_NAMES)]
