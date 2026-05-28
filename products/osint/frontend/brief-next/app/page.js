import { Providers } from './providers.jsx';
import App from '../components/app.jsx';
// image-slot.js (Web Component) intentionally NOT imported — nothing in boss's
// app.jsx uses the <image-slot> custom element, and the file references
// HTMLElement which doesn't exist during Next.js SSR.

export default function HomePage() {
  return (
    <Providers>
      <App />
    </Providers>
  );
}
