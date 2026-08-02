import { useEffect, useCallback } from "react";

export default function AppShell({ sidebarOpen, onCloseSidebar, sidebar, children }) {
  /* Close drawer on Escape */
  useEffect(() => {
    if (!sidebarOpen) return;
    function onKey(e) {
      if (e.key === "Escape") onCloseSidebar();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sidebarOpen, onCloseSidebar]);

  const handleBackdrop = useCallback((e) => {
    if (e.target === e.currentTarget) onCloseSidebar();
  }, [onCloseSidebar]);

  return (
    <div className="app-shell">
      {/* Desktop sidebar — always visible ≥900px */}
      <aside className="sidebar-desktop" aria-label="Research settings">
        {sidebar}
      </aside>

      {/* Mobile drawer overlay — below 900px */}
      {sidebarOpen && (
        <div
          className="drawer-backdrop"
          onClick={handleBackdrop}
          role="presentation"
        >
          <aside className="drawer-panel" aria-label="Research settings" role="dialog" aria-modal="true">
            <button className="drawer-close" onClick={onCloseSidebar} aria-label="Close settings">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
            {sidebar}
          </aside>
        </div>
      )}

      <main className="main-content">
        {children}
      </main>
    </div>
  );
}
