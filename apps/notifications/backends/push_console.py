import logging

logger = logging.getLogger(__name__)


class ConsolePushBackend:
    """Dev backend: logs the push instead of sending it."""

    def send(self, tokens, title, body, data):
        logger.info("[PUSH x%d] %s | %s | %s", len(tokens), title, body, data)
