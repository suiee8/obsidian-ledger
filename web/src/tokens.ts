export const palette = {
  background: "#0B0D11",
  surface1: "#11141A",
  surface2: "#171B23",
  surface3: "#1E232D",
  border: "#262C38",
  borderSubtle: "#1D222C",
  ink: "#E8ECF4",
  muted: "#9AA4B8",
  dim: "#6B7488",
  royal300: "#94ADF6",
  royal400: "#6384EE",
  royal500: "#4169E1",
  royal600: "#3454C0",
  royal700: "#27409A",
  ice: "#C9D6FF",
  profit: "#3DDC97",
  loss: "#FF5C6C",
  warning: "#F5B84B",
} as const;

export const glow = "rgba(65,105,225,0.35)";

export const swatches: readonly { name: string; value: string }[] = [
  { name: "Background", value: palette.background },
  { name: "Surface 1", value: palette.surface1 },
  { name: "Surface 2", value: palette.surface2 },
  { name: "Surface 3", value: palette.surface3 },
  { name: "Border", value: palette.border },
  { name: "Ink", value: palette.ink },
  { name: "Muted", value: palette.muted },
  { name: "Royal 500", value: palette.royal500 },
  { name: "Royal 300", value: palette.royal300 },
  { name: "Ice", value: palette.ice },
  { name: "Profit", value: palette.profit },
  { name: "Loss", value: palette.loss },
  { name: "Warning", value: palette.warning },
];
