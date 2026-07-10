export function Background() {
  return (
    <div className="pointer-events-none fixed inset-0 overflow-hidden -z-10">
      <div
        className="glow-orb"
        style={{
          width: 520,
          height: 520,
          top: -120,
          left: -80,
          background: "oklch(0.82 0.18 290)",
          opacity: 0.7,
        }}
      />
      <div
        className="glow-orb"
        style={{
          width: 600,
          height: 600,
          top: 120,
          right: -160,
          background: "oklch(0.85 0.15 200)",
          opacity: 0.7,
        }}
      />
      <div
        className="glow-orb"
        style={{
          width: 480,
          height: 480,
          bottom: -120,
          left: "30%",
          background: "oklch(0.86 0.14 330)",
          opacity: 0.7,
        }}
      />
    </div>
  );
}
