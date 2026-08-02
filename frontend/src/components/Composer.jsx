import { forwardRef, useState, useCallback } from "react";

const EXAMPLES = [
  { label: "Company name", value: "Stripe" },
  { label: "Full URL", value: "https://linear.app" },
  { label: "Bare domain", value: "notion.so" },
];

function validateQuery(q) {
  const trimmed = q.trim();
  if (!trimmed) return "Enter a company name, URL, or domain";
  if (trimmed.length < 2) return "Too short — at least 2 characters";
  if (trimmed.length > 2048) return "Too long — max 2,048 characters";
  return null;
}

const Composer = forwardRef(function Composer(
  { phase, ready, draftQuery, onQueryChange, onSubmit, onToggleSidebar },
  ref,
) {
  const [touched, setTouched] = useState(false);
  const disabled = phase === "researching" || phase === "booting";
  const error = touched ? validateQuery(draftQuery) : null;

  const handleSubmit = useCallback(
    (e) => {
      e.preventDefault();
      setTouched(true);
      if (validateQuery(draftQuery)) return;
      onSubmit();
    },
    [draftQuery, onSubmit],
  );

  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit(e);
      }
    },
    [handleSubmit],
  );

  return (
    <div className="composer-bar">
      <form className="composer-form" onSubmit={handleSubmit}>
        <button
          type="button"
          className="btn-icon sidebar-toggle"
          onClick={onToggleSidebar}
          aria-label="Open settings"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="4" x2="20" y1="12" y2="12"/><line x1="4" x2="20" y1="6" y2="6"/><line x1="4" x2="20" y1="18" y2="18"/></svg>
        </button>

        <div className="composer-input-group">
          <input
            ref={ref}
            type="text"
            className={"input composer-input" + (error ? " input-error" : "")}
            value={draftQuery}
            onChange={(e) => { onQueryChange(e.target.value); setTouched(true); }}
            onKeyDown={handleKeyDown}
            placeholder="Company name, URL, or domain…"
            disabled={disabled}
            aria-label="Research query"
            aria-invalid={!!error}
            autoFocus
          />
          {error && <span className="composer-error" role="alert">{error}</span>}
        </div>

        <button
          type="submit"
          className="btn btn-primary composer-submit"
          disabled={disabled || !draftQuery.trim()}
          aria-label="Start research"
        >
          {phase === "researching" ? (
            <span className="spinner" aria-hidden="true" />
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m5 12 7-7 7 7"/><path d="M12 19V5"/></svg>
          )}
        </button>
      </form>

      {!ready && ready !== undefined && phase === "idle" && (
        <p className="composer-note" role="status">
          Provider credentials are missing — research will fail until the server is configured.
        </p>
      )}

      <div className="composer-examples">
        <span className="composer-examples-label">Try:</span>
        {EXAMPLES.map((ex) => (
          <button
            key={ex.value}
            type="button"
            className="chip"
            disabled={disabled}
            onClick={() => { onQueryChange(ex.value); setTouched(false); }}
          >
            {ex.value}
          </button>
        ))}
      </div>
    </div>
  );
});

export default Composer;
