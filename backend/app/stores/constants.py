STORE_THEMES = ("runway", "minimal")

DEFAULT_THEME = "runway"

# Subdomains no brand may claim: platform hosts and common infrastructure names.
RESERVED_SUBDOMAINS = frozenset(
    {
        "www", "api", "admin", "app", "dashboard", "platform", "studio", "static",
        "media", "cdn", "assets", "mail", "smtp", "ftp", "status", "help", "support",
        "docs", "blog", "auth", "login", "signup", "billing", "webhooks", "minio",
    }
)
