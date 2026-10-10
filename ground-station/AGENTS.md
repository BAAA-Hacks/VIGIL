<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## Ground-station UI conventions

- Use TypeScript TSX components and Tailwind utility classes for future UI changes.
- Keep component appearance in TSX; keep custom CSS minimal, limited to shared browser defaults, imports, and cases utilities cannot reasonably cover.
- Use reusable components for repeated UI patterns.
- Keep complete Tailwind class names statically discoverable. Use dynamic inline values for runtime measurements such as detection-box coordinates instead of generating utility names from numbers.

- Define all authored UI color values as named CSS custom properties in `src/app/globals.css` under `:root`. Reference those variables from Tailwind classes in TSX, including status colors, shadows, gradients, and focus styles. Avoid literal color values and default palette color utilities in components.

- Keep the UI palette to six root colors: paper, ink, blue, pink, yellow, and peach. Use opacity or color-mix with transparency for tints, borders, shadows, and overlays. Do not add one-off colors or aliases for each component. Transparent is permitted as the absence of a color.

- Keep the dashboard light and restrained: off-white surfaces, charcoal text, subtle borders, and small color accents. Use blue for low-temperature indicators, pink/peach for high-temperature indicators, and reserve yellow for occasional status emphasis. Keep text charcoal for contrast; avoid decorative gradients, glow effects, and oversized cards.

- Keep light mode with charcoal navigation and map controls, neutral panel headings, and restrained colored indicators. Do not show Demo data or Simulated badges in the mission UI. Allow wheel/trackpad map zoom; inset promotion controls must not cover the interactive map.
