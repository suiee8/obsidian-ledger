// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";

import { initialBackgroundPaused } from "../shader/white";
import { BACKGROUND_PAUSED_KEY, useUi } from "./ui";

describe("Pause background toggle", () => {
  beforeEach(() => {
    window.localStorage.clear();
    useUi.setState({ backgroundPaused: false });
  });

  it("starts on unless the OS asks for reduced motion", () => {
    expect(initialBackgroundPaused(null, false)).toBe(false);
    expect(initialBackgroundPaused(null, true)).toBe(true);
  });

  it("lets a saved choice win over the OS setting", () => {
    expect(initialBackgroundPaused("false", true)).toBe(false);
    expect(initialBackgroundPaused("true", false)).toBe(true);
  });

  it("toggles, saves the choice locally and marks the document", () => {
    useUi.getState().toggleBackgroundPaused();
    expect(useUi.getState().backgroundPaused).toBe(true);
    expect(window.localStorage.getItem(BACKGROUND_PAUSED_KEY)).toBe("true");
    expect(document.documentElement.dataset.background).toBe("paused");

    useUi.getState().toggleBackgroundPaused();
    expect(useUi.getState().backgroundPaused).toBe(false);
    expect(window.localStorage.getItem(BACKGROUND_PAUSED_KEY)).toBe("false");
    expect(document.documentElement.dataset.background).toBe("on");
  });
});
