import { useRef } from "react";

export const LiquidButton = ({ children, ghost, as = "button", className = "", ...props }) => {
  const ref = useRef(null);
  const onMove = (e) => {
    const g = ref.current?.querySelector(".glow");
    if (!g) return;
    const r = e.currentTarget.getBoundingClientRect();
    g.style.left = `${e.clientX - r.left}px`;
    g.style.top = `${e.clientY - r.top}px`;
  };
  const Tag = as;
  return (
    <Tag ref={ref} onMouseMove={onMove} className={`btn ${ghost ? "btn-ghost" : ""} ${className}`} {...props}>
      {!ghost && <span className="liquid" />}
      {!ghost && <span className="glow" />}
      {children}
    </Tag>
  );
};
