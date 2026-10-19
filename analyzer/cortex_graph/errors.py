class CortexError(Exception):
    status = 400

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class InvalidInput(CortexError):
    status = 400


class NotFound(CortexError):
    status = 404


class Conflict(CortexError):
    status = 409


class TooLarge(CortexError):
    status = 413
