---
trigger: model_decision
description: Enterprise UI, Design System, and Production Frontend Standards
---

# Enterprise Frontend Design & Engineering Standards

When creating, refactoring, or designing frontend interfaces:

## 1. Design Tokens & Styling
- **Zero Raw Hex/RGB Values**: Always use standardized CSS custom properties (`var(--bg-primary)`, `var(--bg-card)`, `var(--text-primary)`, `var(--text-secondary)`, `var(--border-subtle)`, `var(--accent)`, `var(--radius-md)`).
- **Consistent Elevation & Depth**: Cards and floating panels must use curated border-subtle and ambient box shadows, avoiding harsh flat borders.
- **Typography Hierarchy**: Use proportional typography for labels/headings, and strict monospace (`var(--font-mono)`) for identifiers, hashes, UUIDs, throughput (QPS), latencies (ms), and numerical metrics.

## 2. Layout Stability & Zero CLS
- **Matching Skeleton Placeholders**: Never allow layout shift while fetching data. Skeletons must match the exact dimensions and geometric flow of the final loaded component.
- **No Flashing Default State**: Never display temporary fallback or mock data before actual API responses load.

## 3. Component Architecture & Accessibility (a11y)
- **Headless Accessible Primitives**: Use Radix UI primitives (`@radix-ui/react-dialog`, `@radix-ui/react-dropdown-menu`, `@radix-ui/react-tooltip`, `@radix-ui/react-popover`) for all modals, popovers, and menus to ensure 100% WAI-ARIA and keyboard navigation compliance.
- **Micro-Animations & Transitions**: Use `motion` for fluid tab switching, modal fade/scale physics, and smooth state transitions without performance degradation.
- **Data Densities**: For complex data tables, use `@tanstack/react-table` for clean sorting, filtering, and structured pagination.
- **Icon Uniformity**: Always use `lucide-react` with standard icon sizes (`size={14}` for micro-indicators, `size={16}` for inline actions, `size={18}` for titles).

## 4. Authentic Data Fidelity
- **Zero Hardcoded Mock Telemetry**: Every displayed metric, percentage, request count, and latency value must be bound directly to authentic backend database telemetry.
