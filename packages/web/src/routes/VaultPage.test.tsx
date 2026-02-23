import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { VaultDashboardLayout } from "./VaultPage";

describe("VaultDashboardLayout", () => {
  it("matches the 3-panel layout structure snapshot", () => {
    const markup = renderToStaticMarkup(
      <VaultDashboardLayout
        userName="Alex"
        mobileSidebarOpen={false}
        onToggleSidebar={() => undefined}
        onClearSession={() => undefined}
        sidebar={<div data-test-panel="sidebar">Folders panel</div>}
        list={<div data-test-panel="list">Items panel</div>}
        detail={<div data-test-panel="detail">Detail panel</div>}
      />
    );

    expect(markup).toMatchSnapshot();
  });
});
