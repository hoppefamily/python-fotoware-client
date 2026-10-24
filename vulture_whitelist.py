"""Names vulture cannot see being used. Meant to stay short.

Every entry is a promise that the name *is* used, just not in a way an AST
scan can follow -- a string annotation under `if TYPE_CHECKING`, a `Protocol`
method's parameters, the arguments Python passes to `__exit__`. Each entry
should say who does the using, because an entry that stops being true hides a
dead symbol for good.

The file is never imported; vulture reads it as a list of usages. Regenerate
candidates with `vulture --make-whitelist`, then keep only what you can
justify.
"""
