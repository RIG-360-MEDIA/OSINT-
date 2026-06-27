/**
 * Parallax — translates its children vertically as they cross the viewport,
 * giving "objects" (mockup cards, grids) depth against the scrolling page.
 *
 * `offset` is the px of travel: the element drifts from +offset (entering,
 * below) to -offset (leaving, above), neutral when centred. Honours
 * prefers-reduced-motion (stays still).
 */
import { motion, useTransform, useReducedMotion } from 'framer-motion';
import useViewportProgress from './useViewportProgress';

/**
 * @param {{ children: React.ReactNode, offset?: number, className?: string }} props
 */
export default function Parallax({ children, offset = 44, className }) {
  const reduce = useReducedMotion();
  const { ref, progress } = useViewportProgress();
  const y = useTransform(progress, [0, 1], [offset, -offset]);
  return (
    <motion.div ref={ref} className={className} style={{ y: reduce ? 0 : y, willChange: 'transform' }}>
      {children}
    </motion.div>
  );
}
