export default function DiscordSettings({ enabled, settings, status, error, onChange }) {
  if (!enabled) return null;

  return (
    <details className="discord-settings">
      <summary className="discord-summary">
        <span>
          <strong>Send to Discord</strong>
          <small>Optional report delivery</small>
        </span>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9" /></svg>
      </summary>
      <div className="discord-form">
        <p className="input-hint">
          Credentials stay in this browser session and are sent only when a report is delivered. They are not stored by the server.
        </p>
        <label className="discord-field" htmlFor="discord-applicant-name">
          <span>Applicant name</span>
          <input
            id="discord-applicant-name"
            className="input"
            type="text"
            value={settings.applicant_name}
            onChange={(event) => onChange("applicant_name", event.target.value)}
            maxLength={160}
            autoComplete="name"
            placeholder="Your name"
          />
        </label>
        <label className="discord-field" htmlFor="discord-applicant-email">
          <span>Applicant email</span>
          <input
            id="discord-applicant-email"
            className="input"
            type="email"
            value={settings.applicant_email}
            onChange={(event) => onChange("applicant_email", event.target.value)}
            maxLength={254}
            autoComplete="email"
            placeholder="you@example.com"
          />
        </label>
        <label className="discord-field" htmlFor="discord-bot-token">
          <span>Bot token</span>
          <input
            id="discord-bot-token"
            className="input"
            type="password"
            value={settings.bot_token}
            onChange={(event) => onChange("bot_token", event.target.value)}
            maxLength={256}
            autoComplete="new-password"
            placeholder="Discord bot token"
          />
        </label>
        <label className="discord-field" htmlFor="discord-channel-id">
          <span>Channel ID</span>
          <input
            id="discord-channel-id"
            className="input"
            type="text"
            inputMode="numeric"
            value={settings.channel_id}
            onChange={(event) => onChange("channel_id", event.target.value)}
            maxLength={32}
            placeholder="Numeric channel ID"
          />
        </label>
        {status === "sending" && <p className="status-badge status-loading"><span className="spinner" aria-hidden="true" /> Sending report…</p>}
        {status === "sent" && <p className="status-badge status-ok">Report sent to Discord.</p>}
        {error && <p className="discord-error" role="alert">{error}</p>}
      </div>
    </details>
  );
}
