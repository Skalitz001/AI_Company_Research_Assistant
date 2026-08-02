export default function ReportView({ report, pdfStatus, pdfError, onPdf, onNewResearch }) {
  const { company, summary, products_services, pain_points, competitors, sources, warnings, generated_at, model_id } = report;

  const generatedDate = generated_at
    ? new Date(generated_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
    : null;

  return (
    <article className="report" aria-label="Research report">
      {/* ── Header ── */}
      <header className="report-header">
        <h1 className="report-title">{company.name}</h1>
        {company.website && (
          <a className="report-website" href={company.website} target="_blank" rel="noopener noreferrer">
            {company.website.replace(/^https?:\/\//, "")}
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
          </a>
        )}
        <div className="report-meta">
          {generatedDate && <span>{generatedDate}</span>}
          {model_id && <span className="report-model">Model: {model_id}</span>}
        </div>
      </header>

      {/* ── Warnings ── */}
      {warnings.length > 0 && (
        <section className="report-card report-warnings">
          <h2>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
            Warnings
          </h2>
          <ul>
            {warnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </section>
      )}

      {/* ── Company facts ── */}
      <section className="report-card">
        <h2>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z"/><path d="M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2"/><path d="M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2"/><path d="M10 6h4"/><path d="M10 10h4"/><path d="M10 14h4"/><path d="M10 18h4"/></svg>
          Company Details
        </h2>
        <dl className="fact-grid">
          {company.industry && <><dt>Industry</dt><dd>{company.industry}</dd></>}
          {company.country && <><dt>Country</dt><dd>{company.country}</dd></>}
          <dt>Phone</dt>
          <dd>{company.phone || "Not publicly found"}</dd>
          <dt>Address</dt>
          <dd>{company.address || "Not publicly found"}</dd>
        </dl>
      </section>

      {/* ── Summary ── */}
      <section className="report-card">
        <h2>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/></svg>
          Summary
        </h2>
        <p className="report-summary">{summary}</p>
      </section>

      {/* ── Products & Services ── */}
      {products_services.length > 0 && (
        <section className="report-card">
          <h2>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m7.5 4.27 9 5.15"/><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/></svg>
            Products &amp; Services
          </h2>
          <ul className="tag-list">
            {products_services.map((p, i) => <li key={i} className="tag">{p}</li>)}
          </ul>
        </section>
      )}

      {/* ── Pain Points ── */}
      {pain_points.length > 0 && (
        <section className="report-card report-pain-points">
          <h2>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/></svg>
            AI-Inferred Pain Points
          </h2>
          <p className="pain-points-disclaimer">
            These are AI-generated hypotheses based on available evidence, not confirmed company statements.
          </p>
          <ul>
            {pain_points.map((p, i) => <li key={i}>{p}</li>)}
          </ul>
        </section>
      )}

      {/* ── Competitors ── */}
      {competitors.length > 0 && (
        <section className="report-card">
          <h2>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
            Competitors
          </h2>
          <div className="competitor-list">
            {competitors.map((c, i) => (
              <div key={i} className="competitor-item">
                <div className="competitor-name">
                  <strong>{c.name}</strong>
                  <a href={c.website} target="_blank" rel="noopener noreferrer" className="competitor-link">
                    {c.website.replace(/^https?:\/\//, "")}
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                  </a>
                </div>
                {c.fit && <p className="competitor-fit">{c.fit}</p>}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Sources ── */}
      {sources.length > 0 && (
        <section className="report-card">
          <h2>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
            Sources
          </h2>
          <ul className="source-list">
            {sources.map((s, i) => (
              <li key={i} className="source-item">
                <a href={s.url} target="_blank" rel="noopener noreferrer">
                  {s.title}
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                </a>
                <span className="source-type">{s.source_type}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ── Actions ── */}
      <div className="report-actions">
        <button
          className="btn btn-primary"
          onClick={onPdf}
          disabled={pdfStatus === "loading"}
        >
          {pdfStatus === "loading" ? (
            <><span className="spinner" aria-hidden="true" /> Generating PDF…</>
          ) : pdfStatus === "done" ? (
            <>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
              Download PDF Again
            </>
          ) : (
            <>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              Download PDF
            </>
          )}
        </button>
        <button className="btn btn-secondary" onClick={onNewResearch}>
          New Research
        </button>
      </div>

      {pdfError && (
        <p className="pdf-error" role="alert">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg>
          PDF failed: {pdfError}
        </p>
      )}
    </article>
  );
}
