# Feature 03 — Design System & Theme

**Priority:** P0 — visual foundation for every component  
**Owner:** TBD  
**Depends on:** Nothing (pure CSS/config)  
**Target files:**  
- [`desktop/src/index.css`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/desktop/src/index.css) (rewrite)  
- [`desktop/tailwind.config.js`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/desktop/tailwind.config.js) (migrate to v4)  
- `desktop/src/App.css` (delete)  
**Test file:** `tests/test_design_system.test.ts` (new, visual regression)

---

## Product Spec

The design system defines Lear's visual identity. The app must look **premium, modern, and production-grade** — like Vercel, Linear, or Raycast. Not a generic dashboard template. The existing styling is basic Tailwind with minimal custom tokens. This spec defines the complete visual language.

### Design Principles

1. **Dark-first**: Deep dark backgrounds (`#09090b`) with subtle gray layering
2. **Glassmorphism**: Frosted glass cards with `backdrop-blur` and semi-transparent backgrounds
3. **Depth through shadow, not borders**: Subtle box shadows and glows instead of heavy borders
4. **Accent restraint**: The accent color (`#39bc81` — Lear green) is used sparingly for interactive elements, status indicators, and focus states — never as a background fill
5. **Typography hierarchy**: Inter font, clear size/weight scale from 11px labels to 32px headings
6. **Motion with purpose**: Framer Motion transitions for page changes, hover lifts for cards, pulse for live indicators — never decorative animation
7. **Information density**: Dashboard-grade density (like Datadog), not consumer-app whitespace

### Color System

```
Background layers (darkest to lightest):
  --bg-app:     #09090b     (application background)
  --bg-sidebar: #0a0a0c     (sidebar background)
  --bg-card:    #111113     (card/panel background)
  --bg-card-hover: #16161a  (card hover state)
  --bg-elevated: #1a1a1f    (modals, dropdowns, popovers)
  --bg-input:   #0f0f12     (input field background)

Border system:
  --border:        #1f1f24  (default borders)
  --border-subtle: #18181c  (very subtle separators)
  --border-hover:  #2a2a30  (hover state borders)
  --border-focus:  #39bc81  (focus ring — accent)

Text system:
  --text-primary:   #fafafa  (headings, emphasis)
  --text-secondary: #a1a1aa  (body text, descriptions)
  --text-tertiary:  #71717a  (labels, captions, timestamps)
  --text-disabled:  #3f3f46  (disabled state)

Accent / Status:
  --accent:         #39bc81  (Lear green — primary action)
  --accent-hover:   #2da36c  (hover state)
  --accent-subtle:  rgba(57, 188, 129, 0.1)  (subtle backgrounds)
  --accent-glow:    rgba(57, 188, 129, 0.15) (glow effects)

Status colors:
  --status-healthy:  #39bc81  (green)
  --status-warning:  #f59e0b  (amber)
  --status-error:    #ef4444  (red)
  --status-info:     #3b82f6  (blue)
  --status-neutral:  #71717a  (gray)

Connector brand colors (from registry):
  --color-aws:       #FF9900
  --color-azure:     #0078D4
  --color-gcp:       #4285F4
  --color-k8s:       #326CE5
  --color-github:    #24292E
  --color-gitlab:    #FC6D26
  --color-vercel:    #000000
  --color-datadog:   #632CA6
  --color-grafana:   #F46800
  --color-pagerduty: #06AC38
  --color-snyk:      #4C4A73
  --color-gitleaks:  #FF6B6B
  --color-terraform: #7B42BC
```

### Typography Scale

```
Font: Inter (Google Fonts import)
Fallback: system-ui, -apple-system, sans-serif

Scale:
  --text-xs:    11px / 1.5   (timestamps, badges)
  --text-sm:    13px / 1.5   (labels, secondary info)
  --text-base:  14px / 1.6   (body text)
  --text-lg:    16px / 1.5   (card titles)
  --text-xl:    20px / 1.4   (section headings)
  --text-2xl:   24px / 1.3   (page titles)
  --text-3xl:   32px / 1.2   (hero headings)

Weights:
  --font-normal: 400
  --font-medium: 500
  --font-semibold: 600
  --font-bold: 700
```

### Spacing Scale

```
--space-1:  4px
--space-2:  8px
--space-3:  12px
--space-4:  16px
--space-5:  20px
--space-6:  24px
--space-8:  32px
--space-10: 40px
--space-12: 48px
--space-16: 64px
```

### Component Patterns

#### Glass Card
```css
.glass-card {
  background: rgba(17, 17, 19, 0.6);
  backdrop-filter: blur(12px);
  border: 1px solid var(--border);
  border-radius: 16px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.2);
  transition: border-color 0.2s, box-shadow 0.2s;
}
.glass-card:hover {
  border-color: var(--border-hover);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}
```

#### Status Dot (live indicator)
```css
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  animation: pulse 2s ease-in-out infinite;
}
.status-dot--healthy { background: var(--status-healthy); }
.status-dot--error   { background: var(--status-error); }
.status-dot--warning { background: var(--status-warning); }
```

#### Input Fields
```css
.input {
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 14px;
  color: var(--text-primary);
  font-size: var(--text-base);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
  outline: none;
}
```

#### Buttons
```css
.btn-primary {
  background: var(--accent);
  color: #000;
  font-weight: 600;
  border-radius: 10px;
  padding: 10px 20px;
  transition: background 0.15s, transform 0.1s;
}
.btn-primary:hover {
  background: var(--accent-hover);
  transform: translateY(-1px);
}
.btn-secondary {
  background: var(--bg-card);
  color: var(--text-primary);
  border: 1px solid var(--border);
}
```

### Scrollbar Styling
```css
::-webkit-scrollbar {
  width: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 3px;
}
```

---

## Detailed Task List

### Phase A — Foundation

- [ ] **A1. Import Inter font** from Google Fonts in `index.html`
- [ ] **A2. Migrate to Tailwind v4 CSS-based config** — remove `tailwind.config.js`, put config in `index.css` using `@theme` directive
- [ ] **A3. Define all CSS custom properties** (colors, spacing, typography) in `index.css` `:root`
- [ ] **A4. Delete `App.css`** — remove all Tauri boilerplate styles
- [ ] **A5. Set global base styles** — `body` background, font, color, anti-aliasing, scrollbar

### Phase B — Utility Classes

- [ ] **B1. Create glass-card utility** — reusable glass morphism card pattern
- [ ] **B2. Create status-dot utilities** — `.status-dot--healthy`, `.status-dot--error`, etc.
- [ ] **B3. Create input/button base styles** — consistent form element styling
- [ ] **B4. Create gradient utilities** — subtle gradient backgrounds for sections
- [ ] **B5. Create animation utilities** — pulse, fade-in, slide-up, shimmer (loading)
- [ ] **B6. Create glow utilities** — subtle accent glow for interactive elements

### Phase C — Component-Specific Tokens

- [ ] **C1. Define sidebar-specific tokens** — width, padding, separator styles
- [ ] **C2. Define widget-specific tokens** — chart colors, gauge colors, grid gaps
- [ ] **C3. Define chat-specific tokens** — message bubble styles, typing indicator
- [ ] **C4. Define wizard-specific tokens** — step indicator, progress bar

### Phase D — Tailwind v4 Integration

- [ ] **D1. Configure `@theme` in CSS** with all custom colors/spacing as Tailwind tokens
- [ ] **D2. Verify all existing Tailwind classes** work with v4 API
- [ ] **D3. Add custom Tailwind utilities** for frequently used patterns (glass, glow, etc.)

---

## Testing Methodology

### Visual Tests

```
test_DARK_THEME_CONSISTENT — Screenshot every page/component, verify no 
    white/light backgrounds leak through. All backgrounds must be in the 
    #09090b–#1a1a1f range.

test_ACCENT_COLOR_CORRECT — Every green element uses exactly #39bc81 
    (or its hover/subtle variants), not a different green.

test_FONT_LOADED — Verify Inter font is loaded and applied. Check 
    computed font-family is "Inter", not the fallback.

test_SCROLLBAR_STYLED — Verify custom scrollbar appears (no browser 
    default chrome scrollbar).

test_RESPONSIVE_MINIMUM — App renders correctly at 1024×600 (minimum 
    Tauri window).
```

### Anti-Hardcoding Test Suite

```
test_NO_INLINE_COLORS — Grep all .tsx files for inline color values 
    (hex codes, rgb(), hsl()) that are not connector brand colors from 
    the registry. All colors must come from CSS custom properties or 
    Tailwind classes.

test_NO_INLINE_FONT_SIZES — Grep all .tsx files for inline font-size 
    values. All sizes must use Tailwind classes or CSS custom properties.

test_NO_HARDCODED_SPACING — Grep for inline pixel values in style 
    attributes. Spacing must use the spacing scale.

test_CONNECTOR_COLORS_FROM_REGISTRY — Every connector's visual color 
    in the UI (icon tint, status badge, widget header) must come from 
    the registry's `color` field, not from a hardcoded class in the 
    React component.

test_NO_MAGIC_NUMBERS — No numeric literals in CSS/styled components 
    that aren't part of the defined scale.
```

### Accessibility Tests

```
test_CONTRAST_RATIO — All text/background combinations meet WCAG AA 
    (4.5:1 for normal text, 3:1 for large text).

test_FOCUS_VISIBLE — Every interactive element has a visible focus 
    indicator (the accent ring).

test_NO_COLOR_ONLY_INDICATORS — Status is never conveyed by color 
    alone — always paired with text or icon.
```

---

## Definition of Done

- [ ] Inter font loaded and applied globally
- [ ] All CSS custom properties defined and used consistently
- [ ] Tailwind v4 migration complete (no v3 config file)
- [ ] `App.css` deleted — no Tauri boilerplate
- [ ] Glass card, status dot, input, button patterns implemented
- [ ] Custom scrollbar on all scrollable areas
- [ ] No inline colors/sizes/spacing in any component (anti-hardcoding tests pass)
- [ ] WCAG AA contrast ratios met
- [ ] All connector brand colors sourced from registry
