"""Conservative, internal failure classification; no native library loading."""


class SourceChangedError(RuntimeError):
    """The source or its working copy changed during recognition."""


def failure_scope(exc, phase):
    # Only known document failures may reuse the shared GPU engine.
    if isinstance(exc, KeyboardInterrupt):
        return 'interrupted'
    if isinstance(exc, SourceChangedError):
        return 'document'
    if phase == 'source' and isinstance(exc, (FileNotFoundError, PermissionError)):
        return 'document'
    if phase in ('selection', 'render'):
        from docuworks_ctypes.errors import XdwError
        if isinstance(exc, XdwError) and exc.symbol in {
            'XDW_E_BAD_FORMAT', 'XDW_E_NEWFORMAT', 'XDW_E_FILE_NOT_FOUND',
            'XDW_E_ACCESSDENIED', 'XDW_E_SHARING_VIOLATION',
            'XDW_E_INVALID_ACCESS', 'XDW_E_PROTECT_MODULE', 'XDW_E_SIGNATURE_MODULE',
        }:
            return 'document'
    return 'batch'
