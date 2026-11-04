// The design system has no media glyphs. These follow its grid: 24 by 24, 1.75px round strokes, currentColor.
const base = { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true } as const;

export const PlayGlyph = () => <svg {...base}><path d="M7 4.5v15l12-7.5z" fill="currentColor" /></svg>;
export const PauseGlyph = () => <svg {...base}><path d="M8 5v14M16 5v14" strokeWidth={3} /></svg>;
export const RestartGlyph = () => <svg {...base}><path d="M4.5 12a7.5 7.5 0 1 0 2.4-5.5M4.5 4.5v4.2h4.2" /></svg>;
export const EndGlyph = () => <svg {...base}><path d="M5.5 5.5v13l9.5-6.5zM18.5 5v14" /></svg>;
