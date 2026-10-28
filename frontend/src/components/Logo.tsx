/** Spotter mark: a football with broadcast waves — the booth "on air" over the match. */
export default function Logo({ size = 34 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      <defs>
        <radialGradient id="logoBall" cx="0.38" cy="0.32" r="0.8">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="1" stopColor="#cfd8dc" />
        </radialGradient>
      </defs>
      <rect width="40" height="40" rx="10" fill="#0f2a20" />
      <circle cx="17" cy="21" r="10" fill="url(#logoBall)" />
      <polygon points="17,16.2 21.6,19.5 19.8,24.9 14.2,24.9 12.4,19.5" fill="#0f2a20" />
      <path
        d="M17 11v5.2M21.6 19.5l5.2-1.8M19.8 24.9l3.2 4.4M14.2 24.9l-3.2 4.4M12.4 19.5l-5.2-1.8"
        stroke="#0f2a20"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
      <path d="M29 12.5a9 9 0 0 1 0 11" fill="none" stroke="#34d399" strokeWidth="2.2" strokeLinecap="round" />
      <path d="M32.6 9a14 14 0 0 1 0 18" fill="none" stroke="#34d399" strokeOpacity="0.55" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}
