class ConsoleSMSBackend:
    """Dev backend: prints the SMS instead of calling a real gateway."""

    def send(self, to: str, message: str) -> None:
        print(f"[SMS -> {to}] {message}")
