// Shared design tokens for Plotly charts (must be concrete hex/rgba — no CSS vars)

export const C = {
  base: '#07080f',
  surface: 'rgba(255, 255, 255, 0.042)',
  border: 'rgba(255, 255, 255, 0.085)',
  textBright: '#e2e6f0',
  text: '#7a8199',
  textDim: '#3e4560',
  green: '#00d4a0',
  red: '#ff3d55',
  blue: '#4d9fff',
  amber: '#f5a623',
  purple: '#a78bfa',
  cyan: '#06d6d4',
} as const

export const PALETTE = [
  C.blue, C.green, C.amber, C.red, C.purple, C.cyan,
] as const

const GRID = 'rgba(255, 255, 255, 0.055)'
const AXIS = '#3e4560'
const FONT = { color: C.text, size: 11, family: "'DM Sans', system-ui, sans-serif" }

export const DARK_LAYOUT: Partial<Plotly.Layout> = {
  paper_bgcolor: 'transparent',
  plot_bgcolor: 'rgba(255, 255, 255, 0.018)',
  font: FONT,
  margin: { t: 10, r: 10, b: 40, l: 65 },
  xaxis: { gridcolor: GRID, color: AXIS, zerolinecolor: GRID },
  yaxis: { gridcolor: GRID, color: AXIS, zerolinecolor: GRID },
  legend: { bgcolor: 'transparent', font: { size: 10, color: C.text } },
  autosize: true,
}

export const DARK_LAYOUT_DATE: Partial<Plotly.Layout> = {
  ...DARK_LAYOUT,
  xaxis: { ...DARK_LAYOUT.xaxis, type: 'date' },
}
