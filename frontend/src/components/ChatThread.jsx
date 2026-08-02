import ProgressTimeline from "./ProgressTimeline";
import ReportView from "./ReportView";

export default function ChatThread({
  phase,
  stages,
  report,
  error,
  config,
  configError,
  pdfStatus,
  pdfError,
  onRetry,
  onNewResearch,
  onPdf,
  discordEnabled,
  discordConfigured,
  discordStatus,
  discordError,
  onDiscord,
}) {
  /* ── Booting ── */
  if (phase === "booting") {
    return (
      <div className="thread-empty" role="status">
        <div className="thread-waking">
          <span className="spinner spinner-lg" aria-hidden="true" />
          <h2>Waking research service…</h2>
          <p>This may take up to 60 seconds on a cold start.</p>
        </div>
      </div>
    );
  }

  /* ── Idle / empty ── */
  if (phase === "idle") {
    return (
      <div className="thread-empty">
        <div className="thread-hero">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--c-primary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
          <h1 className="thread-hero-title">Company Research</h1>
          <p className="thread-hero-sub">
            Enter a company name, website URL, or bare domain below to generate an AI-powered research report.
          </p>
          {configError && (
            <p className="thread-config-warn" role="alert">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
              {configError}
            </p>
          )}
        </div>
      </div>
    );
  }

  /* ── Researching ── */
  if (phase === "researching") {
    return (
      <div className="thread-research" aria-busy="true">
        <ProgressTimeline stages={stages} />
      </div>
    );
  }

  /* ── Error ── */
  if (phase === "error" && error) {
    return (
      <div className="thread-error">
        <div className="error-card" role="alert">
          <div className="error-icon">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg>
          </div>
          <h2>Research Failed</h2>
          <p className="error-code">{error.code}</p>
          <p className="error-message">{error.message}</p>
          <div className="error-actions">
            {error.retryable && (
              <button className="btn btn-primary" onClick={onRetry}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/></svg>
                Retry
              </button>
            )}
            <button className="btn btn-secondary" onClick={onNewResearch}>
              New Research
            </button>
          </div>
        </div>
      </div>
    );
  }

  /* ── Complete ── */
  if (phase === "complete" && report) {
    return (
      <div className="thread-complete">
        <ReportView
          report={report}
          pdfStatus={pdfStatus}
          pdfError={pdfError}
          onPdf={onPdf}
          onNewResearch={onNewResearch}
          discordEnabled={discordEnabled}
          discordConfigured={discordConfigured}
          discordStatus={discordStatus}
          discordError={discordError}
          onDiscord={onDiscord}
        />
      </div>
    );
  }

  return null;
}
