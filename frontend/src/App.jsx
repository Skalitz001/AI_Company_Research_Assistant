import { useReducer, useEffect, useRef, useCallback } from "react";
import { fetchConfig, streamResearch, fetchPdf, downloadBlob } from "./api";
import { initialState, reducer } from "./state";
import AppShell from "./components/AppShell";
import Sidebar from "./components/Sidebar";
import ChatThread from "./components/ChatThread";
import Composer from "./components/Composer";

export default function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const abortRef = useRef(null);
  const composerRef = useRef(null);

  /* ── Boot: fetch config ── */
  useEffect(() => {
    let cancelled = false;
    fetchConfig()
      .then((config) => {
        if (!cancelled) dispatch({ type: "CONFIG_LOADED", config });
      })
      .catch((err) => {
        if (!cancelled) dispatch({ type: "CONFIG_ERROR", message: err.message });
      });
    return () => { cancelled = true; };
  }, []);

  /* ── Research submit ── */
  const handleSubmit = useCallback(() => {
    if (state.phase === "researching") return;
    const query = state.draftQuery.trim();
    const model = state.draftModel.trim();
    if (!query) return;
    if (!model || !model.includes("/")) return;

    dispatch({ type: "SUBMIT" });

    const controller = new AbortController();
    abortRef.current = controller;

    streamResearch(
      { query, model_id: model },
      controller.signal,
      (event) => {
        switch (event.type) {
          case "progress":
            dispatch({ type: "PROGRESS", stage: event.stage, percent: event.percent, message: event.message });
            break;
          case "result":
            dispatch({ type: "RESULT", report: event.report });
            break;
          case "error":
            dispatch({ type: "RESEARCH_ERROR", error: event.error });
            break;
          case "heartbeat":
            /* No UI update needed — keeps connection alive */
            break;
        }
      },
    ).catch((err) => {
      if (err.name === "AbortError") return;
      dispatch({ type: "RESEARCH_ERROR", error: { code: "NETWORK_ERROR", message: err.message, retryable: true } });
    }).finally(() => {
      abortRef.current = null;
    });
  }, [state.phase, state.draftQuery, state.draftModel]);

  /* ── Cancel ── */
  const handleCancel = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
    abortRef.current = null;
    dispatch({ type: "CANCEL" });
    setTimeout(() => composerRef.current?.focus(), 0);
  }, []);

  /* ── New research ── */
  const handleNewResearch = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
    abortRef.current = null;
    dispatch({ type: "NEW_RESEARCH" });
    setTimeout(() => composerRef.current?.focus(), 0);
  }, []);

  /* ── Retry ── */
  const handleRetry = useCallback(() => {
    dispatch({ type: "RETRY" });
    /* Trigger submit on next tick after state is restored */
    setTimeout(() => {
      /* The retry restores draft fields; we need to re-submit */
    }, 0);
  }, []);

  /* Effect: auto-submit after RETRY restores the draft fields */
  const retryPendingRef = useRef(false);
  const actualRetry = useCallback(() => {
    dispatch({ type: "RETRY" });
    retryPendingRef.current = true;
  }, []);
  useEffect(() => {
    if (retryPendingRef.current && state.phase !== "researching") {
      retryPendingRef.current = false;
      handleSubmit();
    }
  }, [state.draftQuery, state.draftModel, state.phase, handleSubmit]);

  /* ── PDF download ── */
  const handlePdf = useCallback(async () => {
    if (!state.report) return;
    dispatch({ type: "PDF_LOADING" });
    try {
      const blob = await fetchPdf(state.report);
      const safeName = (state.report.company?.name || "company")
        .replace(/[^a-zA-Z0-9_-]/g, "_")
        .substring(0, 60);
      downloadBlob(blob, `${safeName}-research-report.pdf`);
      dispatch({ type: "PDF_DONE" });
    } catch (err) {
      dispatch({ type: "PDF_ERROR", message: err.message });
    }
  }, [state.report]);

  const closeSidebar = useCallback(() => dispatch({ type: "CLOSE_SIDEBAR" }), []);

  return (
    <AppShell
      sidebarOpen={state.sidebarOpen}
      onCloseSidebar={closeSidebar}
      sidebar={
        <Sidebar
          config={state.config}
          configError={state.configError}
          phase={state.phase}
          draftModel={state.draftModel}
          onModelChange={(v) => dispatch({ type: "SET_DRAFT_MODEL", value: v })}
          onCancel={handleCancel}
          onNewResearch={handleNewResearch}
        />
      }
    >
      <div className="thread-area">
        <ChatThread
          phase={state.phase}
          stages={state.stages}
          report={state.report}
          error={state.researchError}
          config={state.config}
          configError={state.configError}
          pdfStatus={state.pdfStatus}
          pdfError={state.pdfError}
          onRetry={actualRetry}
          onNewResearch={handleNewResearch}
          onPdf={handlePdf}
        />
        <Composer
          ref={composerRef}
          phase={state.phase}
          ready={state.config?.ready}
          draftQuery={state.draftQuery}
          onQueryChange={(v) => dispatch({ type: "SET_DRAFT_QUERY", value: v })}
          onSubmit={handleSubmit}
          onToggleSidebar={() => dispatch({ type: "TOGGLE_SIDEBAR" })}
        />
      </div>
    </AppShell>
  );
}
