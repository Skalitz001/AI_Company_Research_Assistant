/**
 * Application state machine.
 *
 * Phases: booting → idle → researching → complete | error
 *              ↑         ↓                ↓
 *              └─────────┘←───────────────┘
 */

const EMPTY_DISCORD_SETTINGS = {
  applicant_name: "",
  applicant_email: "",
  bot_token: "",
  channel_id: "",
};

function loadDiscordSettings() {
  if (typeof sessionStorage === "undefined") return { ...EMPTY_DISCORD_SETTINGS };
  try {
    const saved = JSON.parse(sessionStorage.getItem("cra-discord-settings") || "{}");
    return { ...EMPTY_DISCORD_SETTINGS, ...saved };
  } catch {
    return { ...EMPTY_DISCORD_SETTINGS };
  }
}

export function hasDiscordSettings(settings) {
  return Boolean(
    settings?.applicant_name?.trim()
    && settings?.applicant_email?.trim()
    && settings?.bot_token?.trim()
    && settings?.channel_id?.trim(),
  );
}

/** @type {import('./state').AppState} */
export const initialState = {
  /* lifecycle */
  phase: "booting",       // booting | idle | researching | complete | error

  /* config from backend */
  config: null,           // { ready, default_model, model_suggestions, discord_enabled }
  configError: null,

  /* draft inputs */
  draftQuery: "",
  draftModel: "",

  /* submitted (frozen at submit time) */
  submittedQuery: "",
  submittedModel: "",

  /* research stream */
  stages: [],             // [{ stage, percent, message, status }]
  report: null,
  researchError: null,

  /* pdf */
  pdfStatus: "idle",      // idle | loading | done | error
  pdfError: null,

  /* Discord — token exists only in this tab's session state */
  discordSettings: loadDiscordSettings(),
  discordStatus: "idle",  // idle | sending | sent | error
  discordError: null,

  /* ui */
  sidebarOpen: false,
};

/** Ordered canonical stages */
const STAGE_ORDER = ["resolving", "crawling", "searching", "analyzing", "finalizing"];

export function reducer(state, action) {
  switch (action.type) {
    /* ── Boot ── */
    case "CONFIG_LOADED":
      return {
        ...state,
        phase: "idle",
        config: action.config,
        draftModel: action.config.default_model,
        configError: null,
      };

    case "CONFIG_ERROR":
      return {
        ...state,
        phase: "idle",
        configError: action.message,
      };

    /* ── Draft ── */
    case "SET_DRAFT_QUERY":
      return { ...state, draftQuery: action.value };

    case "SET_DRAFT_MODEL":
      return { ...state, draftModel: action.value };
    case "SET_DISCORD_SETTING":
      if (!Object.prototype.hasOwnProperty.call(EMPTY_DISCORD_SETTINGS, action.field)) return state;
      return {
        ...state,
        discordSettings: { ...state.discordSettings, [action.field]: action.value },
        discordStatus: "idle",
        discordError: null,
      };


    /* ── Research ── */
    case "SUBMIT": {
      const stages = STAGE_ORDER.map((s) => ({
        stage: s,
        percent: 0,
        message: "",
        status: "pending",  // pending | active | done
      }));
      return {
        ...state,
        phase: "researching",
        submittedQuery: state.draftQuery.trim(),
        submittedModel: state.draftModel.trim(),
        stages,
        report: null,
        researchError: null,
        pdfStatus: "idle",
        pdfError: null,
        discordStatus: "idle",
        discordError: null,
      };
    }

    case "PROGRESS": {
      const { stage, percent, message } = action;
      const stages = state.stages.map((s) => {
        if (s.stage === stage) return { ...s, percent, message, status: "active" };
        /* Mark earlier stages as done */
        const idx = STAGE_ORDER.indexOf(s.stage);
        const currentIdx = STAGE_ORDER.indexOf(stage);
        if (idx < currentIdx && s.status !== "done") return { ...s, status: "done", percent: 100 };
        return s;
      });
      return { ...state, stages };
    }

    case "RESULT":
      return {
        ...state,
        phase: "complete",
        report: action.report,
        stages: state.stages.map((s) => ({ ...s, status: "done", percent: 100 })),
      };

    case "RESEARCH_ERROR":
      return {
        ...state,
        phase: "error",
        researchError: action.error,
      };

    case "CANCEL":
      return {
        ...state,
        phase: "idle",
        stages: [],
        report: null,
        researchError: null,
      };

    case "NEW_RESEARCH":
      return {
        ...initialState,
        phase: "idle",
        config: state.config,
        draftModel: state.config?.default_model || "",
        discordSettings: state.discordSettings,
      };

    case "RETRY":
      /* Re-submit with saved query/model — caller triggers the actual fetch */
      return {
        ...state,
        draftQuery: state.submittedQuery,
        draftModel: state.submittedModel,
      };
    /* ── Discord ── */
    case "DISCORD_SEND_START":
      return { ...state, discordStatus: "sending", discordError: null };

    case "DISCORD_SEND_SUCCESS":
      return { ...state, discordStatus: "sent", discordError: null };

    case "DISCORD_SEND_ERROR":
      return { ...state, discordStatus: "error", discordError: action.message };


    /* ── PDF ── */
    case "PDF_LOADING":
      return { ...state, pdfStatus: "loading", pdfError: null };

    case "PDF_DONE":
      return { ...state, pdfStatus: "done" };

    case "PDF_ERROR":
      return { ...state, pdfStatus: "error", pdfError: action.message };

    /* ── UI ── */
    case "TOGGLE_SIDEBAR":
      return { ...state, sidebarOpen: !state.sidebarOpen };

    case "CLOSE_SIDEBAR":
      return { ...state, sidebarOpen: false };

    default:
      return state;
  }
}
