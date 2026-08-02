import ModelInput from "./ModelInput";

export default function Sidebar({
  config,
  configError,
  phase,
  draftModel,
  onModelChange,
  onCancel,
  onNewResearch,
}) {
  const isResearching = phase === "researching";
  const showResult = phase === "complete" || phase === "error";

  return (
    <div className="sidebar-inner">
      <div className="sidebar-brand">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
        <span className="sidebar-title">Research Assistant</span>
      </div>

      <div className="sidebar-actions">
        {isResearching && (
          <button className="btn btn-secondary btn-full" onClick={onCancel}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            Cancel Research
          </button>
        )}
        {showResult && (
          <button className="btn btn-secondary btn-full" onClick={onNewResearch}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="M12 5v14"/></svg>
            New Research
          </button>
        )}
      </div>

      <div className="sidebar-section">
        <label className="sidebar-label" htmlFor="model-input">Model</label>
        <ModelInput
          value={draftModel}
          onChange={onModelChange}
          suggestions={config?.model_suggestions || []}
          disabled={isResearching}
        />
      </div>

      {/* Readiness indicator */}
      <div className="sidebar-section">
        <div className="sidebar-label">Status</div>
        {configError ? (
          <p className="status-badge status-warn">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
            Could not load configuration
          </p>
        ) : config?.ready ? (
          <p className="status-badge status-ok">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
            Providers configured
          </p>
        ) : config ? (
          <p className="status-badge status-warn">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
            Missing provider credentials
          </p>
        ) : (
          <p className="status-badge status-loading">Connecting…</p>
        )}
      </div>

      <div className="sidebar-section sidebar-help">
        <div className="sidebar-label">How it works</div>
        <ol className="howto-list">
          <li>Enter a company name, URL, or domain</li>
          <li>We crawl the site &amp; search public sources</li>
          <li>An AI model synthesizes a structured report</li>
          <li>Download a PDF of the research</li>
        </ol>
      </div>

      <div className="sidebar-footer">
        <p className="cold-start-note">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
          Hosted on Render Free — the service sleeps after 15 min idle and may take ~60 s to wake.
        </p>
      </div>
    </div>
  );
}
