""""""

from ..errors import DiscordException

class ApplicationCommandError(DiscordException):
    r"""The base exception type for all application command related errors.
    This inherits from :exc:`discord.DiscordException`.
    This exception and exceptions inherited from it are handled
    in a special way as they are caught and passed into a special event
    from :class:`.Bot`\, :func:`.on_command_error`.
    """
    pass

class CheckFailure(ApplicationCommandError):
    """Exception raised when the predicates in :attr:`.Command.checks` have failed.
    This inherits from :exc:`ApplicationCommandError`
    """
    pass

class ApplicationCommandInvokeError(ApplicationCommandError):
    """Exception raised when the command being invoked raised an exception.
    This inherits from :exc:`ApplicationCommandError`
    Attributes
    -----------
    original: :exc:`Exception`
        The original exception that was raised. You can also get this via
        the ``__cause__`` attribute.
    """
    def __init__(self, e: Exception) -> None:
        self.original: Exception = e
        super().__init__(f'Application Command raised an exception: {e.__class__.__name__}: {e}')