export default function ModelInput({ value, onChange, suggestions, disabled }) {
  const listId = "model-suggestions";
  return (
    <div className="model-input-wrap">
      <input
        id="model-input"
        type="text"
        className="input"
        list={listId}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        placeholder="e.g. openrouter/auto"
        autoComplete="off"
        spellCheck={false}
        aria-label="Model ID"
      />
      <datalist id={listId}>
        {suggestions.map((s) => (
          <option key={s} value={s} />
        ))}
      </datalist>
      <p className="input-hint">
        Exact <a href="https://openrouter.ai/models" target="_blank" rel="noopener noreferrer">OpenRouter model ID</a> — must contain a <code>/</code>
      </p>
    </div>
  );
}
