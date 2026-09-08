/* A tab-session warning, not an idempotency key or a recoverable receipt.
 * Only a constant marker crosses refresh. Credentials, payloads, file names
 * and capability URLs must never enter this record. A remaining marker means
 * "unconfirmed", not failed, free, still running, or safely retryable. */
export function createPaidReceipts(storage = () => globalThis.sessionStorage) {
  const key = "paid-request-unconfirmed-v1";
  const active = new Set();
  let uncertain = false;
  let unavailable = false;
  let listener = () => {};
  try {
    // Even malformed/old values require acknowledgement. Parsing an unknown
    // marker as an empty history would turn unreadable evidence into a pass.
    uncertain = storage().getItem(key) !== null;
  } catch {
    // Preserve the existing memory-only browser mode, but do not claim that
    // its prior document could be inspected or that refresh is protected.
    unavailable = true;
  }

  function persist() {
    try {
      if (uncertain || active.size) storage().setItem(key, "unconfirmed");
      else storage().removeItem(key);
    } catch {
      unavailable = true;
    }
  }

  return {
    state: () => ({ uncertain, active: active.size, unavailable }),
    subscribe(callback) { listener = callback; },
    begin() {
      if (uncertain) {
        const error = new Error("A previous paid request has an unconfirmed outcome.");
        error.code = "paid_receipt_pending";
        throw error;
      }
      const token = {};
      active.add(token);
      // Write before dispatch, not after await fetch: the latter is exactly
      // the refresh window this marker is intended to cover.
      persist();
      listener();
      return (confirmed = false) => {
        // Different resume parents may overlap. A late/double settlement
        // must not release another request or erase an earlier uncertainty.
        if (!active.delete(token)) return;
        if (!confirmed) uncertain = true;
        persist();
        listener();
      };
    },
    acknowledge() {
      // Acknowledgement is a user's risk decision, never a cancellation of a
      // live fetch. Old callbacks must not unlock a new request through it.
      if (active.size) return false;
      uncertain = false;
      persist();
      listener();
      return true;
    },
  };
}
