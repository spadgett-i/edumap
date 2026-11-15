// Iconos de trazo (24x24) incluidos en el código para no depender de librerías externas.
const PATHS = {
  home: 'M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10',
  plus: 'M12 5v14M5 12h14',
  minus: 'M5 12h14',
  folder: 'M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z',
  file: 'M7 3h7l5 5v13H7zM14 3v5h5',
  upload: 'M12 16V4M7 9l5-5 5 5M4 16v4h16v-4',
  save: 'M5 3h12l4 4v14H5zM8 3v6h8V3M8 21v-7h8v7',
  reset: 'M4 12a8 8 0 108-8H7M7 4L4 7l3 3',
  back: 'M10 6l-6 6 6 6M4 12h16',
  trash: 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6',
  fit: 'M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5',
  expand: 'M12 4v16M4 12h16',
  collapse: 'M5 12h14',
  check: 'M5 13l4 4L19 7',
  x: 'M6 6l12 12M18 6L6 18',
  alert: 'M12 4l9 16H3L12 4zM12 10v4M12 17v.5',
  branch: 'M6 4v8a4 4 0 004 4h8M6 4a2 2 0 100 .01M18 16a2 2 0 100 .01',
  link: 'M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1',
} as const

export type IconName = keyof typeof PATHS

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={PATHS[name]} />
    </svg>
  )
}

export function Logo({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="#FFFFFF" fillOpacity="0.12" />
      <g stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round"><path d="M16 9v6M16 15l-7 8M16 15l7 8" /></g>
      <circle cx="16" cy="9" r="3.4" fill="#FFFFFF" />
      <circle cx="9" cy="23" r="3" fill="#FFFFFF" />
      <circle cx="23" cy="23" r="3" fill="#A7152E" />
    </svg>
  )
}
