/** Spotter mark: a pitch-shaped "S" with the halfway line and centre circle.
 *  Drawn as a CSS mask so it takes the theme's accent colour in both dark and light mode. */
export default function Logo({ size = 34 }: { size?: number }) {
  return (
    <span
      role="img"
      aria-label="Spotter"
      className="block shrink-0 bg-emerald-300"
      style={{
        width: size,
        height: size,
        WebkitMaskImage: "url(/logo-mask.png)",
        maskImage: "url(/logo-mask.png)",
        WebkitMaskSize: "contain",
        maskSize: "contain",
        WebkitMaskRepeat: "no-repeat",
        maskRepeat: "no-repeat",
        WebkitMaskPosition: "center",
        maskPosition: "center",
      }}
    />
  );
}
