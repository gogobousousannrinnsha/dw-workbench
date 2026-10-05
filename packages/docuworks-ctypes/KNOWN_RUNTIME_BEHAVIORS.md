# Known runtime behaviors

Scope: Windows x64, Python 3.11, installed System32 XDWAPI 10.1.1.

- User 0-byte setter accepts non-NULL/size 0. Three getter buffer forms return
  `XDW_E_UNEXPECTED` immediately and after save/reopen. It is not counted as
  retrievable persistence.
- DateFormat `yy.mm.dd` is accepted and persisted; `yy.MM.dd` is rejected with
  `0x80070057`. The registry continues to follow the XDWAPI 3.1 lowercase form.
- TopField Japanese 7 characters and ASCII 13 characters were accepted by this
  runtime, but strict validation continues to follow the documented byte limit.
- ASCII text remained MULTIBYTE and document nVersion remained 7 before and
  after save/reopen. Japanese and emoji text were persisted as Unicode.

## Simple and distribution limitations

- Simple does not create new date stamps. Existing date stamps remain
  enumerable and editable through supported generic operations or Core.
- Custom DATE is exposed as a raw signed 32-bit value; no `datetime.date`
  conversion is promised.
- Windows x64 is the only supported platform. XDWAPI and a compatible
  DocuWorks installation are external prerequisites and are not distributed.
- `save()` is explicit. Closing a context without saving discards changes.
- XDWAPI 10.1.1 is the Full Verified runtime baseline. SDK 10.0 is smoke
  verified; SDK 9.1.7 is ABI verified but cannot open documents against the
  current installed product runtime (`XDW_E_NOT_INSTALLED`).
