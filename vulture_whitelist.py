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

# Python passes these to __exit__ (FotoWareClient, OAuthAuthenticator).
exc_type
exc_val
exc_tb
tb

# urllib3 reads these on the Retry subclass (retry.ObservedRetry).
RETRY_AFTER_STATUS_CODES
get_backoff_time

# The public API: called by the library's users, not by the library.
from_env
cost_snapshot
get_api_descriptor
get_archives
get_archive
get_metadata_editor
search
get_page
get_asset
request_rendition
get_rendition_task
# The extensions (fotoware_client.extensions).
list_archives
field_labels
iter_search
Rendition
url
write_to
read
save
invalidate
get_field
get_field_values
doctype
