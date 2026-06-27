/**
 * Reveal — scroll-triggered entrance used across the landing sections.
 *
 * One grammar for the whole page: content rises a few pixels, un-blurs and
 * fades in once when it enters the viewport (never repeats, so scrolling back
 * up stays calm). framer-motion already respects prefers-reduced-motion via
 * MotionConfig at the app root; here we also pass a reduced fallback.
 *
 * `RevealGroup` staggers its `Reveal` children for lists (the desk cards).
 */
import { motion } from 'framer-motion';

const EASE = [0.16, 0.84, 0.28, 1];

const item = {
  hidden: { opacity: 0, y: 22, filter: 'blur(6px)' },
  show: { opacity: 1, y: 0, filter: 'blur(0px)', transition: { duration: 0.7, ease: EASE } },
};

/**
 * @param {{ children: React.ReactNode, as?: any, delay?: number, className?: string, style?: object }} props
 * Extra props (e.g. `data-tone`, `id`) are spread onto the motion element.
 */
export function Reveal({ children, as = 'div', delay = 0, className, style, ...rest }) {
  const M = motion[as] || motion.div;
  return (
    <M
      {...rest}
      className={className}
      style={style}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: '-12% 0px -12% 0px' }}
      variants={{
        hidden: item.hidden,
        show: { ...item.show, transition: { ...item.show.transition, delay } },
      }}
    >
      {children}
    </M>
  );
}

/**
 * @param {{ children: React.ReactNode, stagger?: number, className?: string }} props
 */
export function RevealGroup({ children, stagger = 0.12, className }) {
  return (
    <motion.div
      className={className}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: '-10% 0px -10% 0px' }}
      variants={{ show: { transition: { staggerChildren: stagger } } }}
    >
      {children}
    </motion.div>
  );
}

/** A child of RevealGroup — inherits the group's stagger timing. */
export function RevealItem({ children, className }) {
  return (
    <motion.div className={className} variants={item}>
      {children}
    </motion.div>
  );
}
