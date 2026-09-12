class U1McpError(Exception):
    """Base error for snapmaker-u1-mcp."""


class ConfigurationError(U1McpError):
    """Invalid or missing local configuration."""


class SlicerError(U1McpError):
    """Snapmaker Orca command failed or is unavailable."""


class ProfileError(U1McpError):
    """Profile discovery or validation failed."""
