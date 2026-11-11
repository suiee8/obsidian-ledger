// @vitest-environment jsdom
import { act, fireEvent, render, screen, cleanup } from "@testing-library/react";
import { beforeEach, describe, expect, it, afterEach } from "vitest";

import { EMPTY_FILTERS, useFilters } from "../state/filters";
import { FilterBar } from "./FilterBar";

const OPTIONS = { accounts: [], symbols: ["AAPL", "MSFT"], setups: [], sides: [] };

afterEach(() => cleanup());

describe("FilterBar", () => {
  beforeEach(() => {
    act(() => useFilters.setState({ ...EMPTY_FILTERS }));
  });

  it("adds a symbol from the menu and shows it as a removable chip", () => {
    render(<FilterBar options={OPTIONS} />);
    fireEvent.change(screen.getByLabelText("Add symbol filter"), { target: { value: "AAPL" } });
    expect(useFilters.getState().symbols).toEqual(["AAPL"]);
    expect(screen.getByRole("button", { name: "Remove symbol filter AAPL" })).toBeTruthy();
  });

  it("removes a chip and clears all filters", () => {
    act(() => useFilters.setState({ symbols: ["AAPL", "MSFT"] }));
    render(<FilterBar options={OPTIONS} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove symbol filter MSFT" }));
    expect(useFilters.getState().symbols).toEqual(["AAPL"]);
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(useFilters.getState().symbols).toEqual([]);
  });
});

