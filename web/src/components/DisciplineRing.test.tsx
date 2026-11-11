// @vitest-environment jsdom
import { render, screen, cleanup } from "@testing-library/react";
import { describe, expect, it, afterEach } from "vitest";

import { DisciplineRing } from "./DisciplineRing";

afterEach(() => cleanup());

describe("DisciplineRing", () => {
  it("states the score and how many components produced it", () => {
    render(
      <DisciplineRing score={70} componentsUsed={5} componentsTotal={5} formula="weights" />,
    );
    expect(screen.getByRole("img", { name: "Discipline score 70 of 100" })).toBeTruthy();
    expect(screen.getByText("5 of 5 components")).toBeTruthy();
  });

  it("shows a dash when there is no score yet", () => {
    render(<DisciplineRing score={null} componentsUsed={0} componentsTotal={5} formula="weights" />);
    expect(screen.getByRole("img", { name: "Discipline score not available" })).toBeTruthy();
  });
});

