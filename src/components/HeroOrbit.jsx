export default function HeroOrbit() {
  const dots = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven"];

  return (
    <div className="hero-orbit" aria-hidden="true">
      {dots.map((dot) => <span key={dot} className={`orbit-dot dot-${dot}`} />)}
      <span className="orbit-ring ring-one" />
      <span className="orbit-ring ring-two" />
      <span className="orbit-ring ring-three" />
      <span className="orbit-center">₹</span>
    </div>
  );
}
