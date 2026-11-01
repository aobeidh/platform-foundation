import { useEffect, useRef, useState } from 'react';

/** The element's real pixel width, so visuals draw at size instead of scaling a fixed viewBox. */
export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.round(e.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

/** True once the element has been at least a quarter in view. Entry animations wait for it, and play once. */
export function useInView<T extends Element>(threshold = 0.25) {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(() => typeof IntersectionObserver === 'undefined');
  useEffect(() => {
    if (!ref.current || inView) return;
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setInView(true); io.disconnect(); } }, { threshold });
    io.observe(ref.current);
    return () => io.disconnect();
  }, [inView, threshold]);
  return [ref, inView] as const;
}

export const delay = (ms: number) => ({ '--d': `${ms}ms` }) as React.CSSProperties;
