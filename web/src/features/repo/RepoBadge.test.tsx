import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { server } from "@/test/server";
import { RepoBadge } from "./RepoBadge";

describe("RepoBadge", () => {
  it("shows the application and counts", async () => {
    renderAt(<RepoBadge />);

    const badge = await screen.findByTestId("repo-badge");
    expect(badge).toHaveTextContent("P77_RISK_ENGINE");
    expect(badge).toHaveTextContent("2 folders · 9 jobs");
    expect(badge).toHaveTextContent("test · uat · bench · prod");
  });

  it("says when the API is unreachable", async () => {
    server.use(http.get("/api/repo", () => HttpResponse.error()));
    renderAt(<RepoBadge />);

    expect(await screen.findByText("API unreachable")).toBeInTheDocument();
  });
});
