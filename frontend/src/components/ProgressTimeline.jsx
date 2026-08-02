const STAGE_LABELS = {
  resolving: "Finding official website",
  crawling: "Crawling website pages",
  searching: "Searching public sources",
  analyzing: "Generating AI analysis",
  finalizing: "Validating report",
};

function StageIcon({ status }) {
  if (status === "done") {
    return (
      <svg className="stage-icon stage-icon-done" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    );
  }
  if (status === "active") {
    return <span className="spinner stage-spinner" aria-hidden="true" />;
  }
  return (
    <svg className="stage-icon stage-icon-pending" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/></svg>
  );
}

export default function ProgressTimeline({ stages }) {
  return (
    <div className="progress-timeline" aria-live="polite" aria-label="Research progress">
      <h2 className="progress-heading">Researching…</h2>
      <ol className="progress-stages">
        {stages.map((s) => (
          <li
            key={s.stage}
            className={`progress-stage progress-stage-${s.status}`}
          >
            <StageIcon status={s.status} />
            <div className="progress-stage-text">
              <span className="progress-stage-label">{STAGE_LABELS[s.stage] || s.stage}</span>
              {s.message && s.status === "active" && (
                <span className="progress-stage-msg">{s.message}</span>
              )}
            </div>
            {s.status === "active" && (
              <span className="progress-percent" aria-label={`${s.percent}% complete`}>{s.percent}%</span>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
