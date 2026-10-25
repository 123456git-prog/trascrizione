"""Errori dell'applicazione con messaggi comprensibili in italiano."""


class AppError(Exception):
    """Errore previsto: il messaggio è pensato per essere mostrato all'utente."""


class AudioError(AppError):
    pass


class TranscriptionError(AppError):
    pass


class AnalysisError(AppError):
    pass


class NotFoundError(AppError):
    pass
