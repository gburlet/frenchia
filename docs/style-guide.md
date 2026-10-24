# Frenchia UI style guide

Dark-only theme for the MVP. Implement every value below as a CSS custom property / Tailwind theme token so a light theme can be added later.

## Colors

| Role | Hex |
|---|---|
| Page background | `#292929` |
| Header / footer background | `#212121` |
| Card / panel background | `#333333` |
| Borders / dividers | `#444444` (or white at 5–8% opacity) |
| Body text | `#949494` |
| Headings, button text | `#FFFFFF` |
| Muted text (timestamps) | `#6F6F6F` |
| Secondary detail text | `#B5B5B5` |
| Primary accent (links, "Admin" button) | `#5E95AB`, hover `#4E8297` |
| Purple accent | `#7E57C2`, hover `#6A45AD` |

Use purple for the main action buttons (submit, "run task"), range sliders, the drawer tab, and highlighted values. White text on `#7E57C2` has about 5:1 contrast (WCAG AA).

### Status colors (pills and left-border markers)

| Status | Color |
|---|---|
| Success | `#4F8A5D` |
| Failure / error | `#B55252` |
| Blocked / stalled | `#B8862F` |
| Skipped / neutral | `#5A5A5A` |
| Kept / correct item text | `#8FC79C` |
| Error text | `#E07A7A` |
| Warning text | `#E0B252` |

## Typography

- Headings: Avenir LT Pro Heavy, weight 800. Fallbacks: Avenir, Helvetica Neue, Helvetica, Arial, sans-serif. Color `#FFFFFF`. (macOS ships Avenir with an 800 "Heavy" face.)
- Body: Avenir LT Pro Roman, same fallbacks. Color `#949494`.
- Logs and tracebacks: system monospace (ui-monospace, SFMono-Regular, Menlo, Consolas) on a `#1B1B1B` background.
- Text is antialiased.

## Buttons

All buttons use the heading font, bold, no border. Hover: `filter: brightness(0.85)` and `scale(1.04)` over 0.2s ease.

| Type | Style |
|---|---|
| Primary / submit | Purple `#7E57C2` fill, white text, 6px radius, 1rem padding, full width in forms |
| Secondary (Admin) | Teal `#5E95AB` fill, white text, 6px radius, 38px tall, 0.9rem text |
| Ghost (Logout) | Transparent fill, 1px `#949494` border, `#949494` text, 6px radius, 38px tall, 0.85rem text |
| Drawer tab | Purple fill, pill shape (999px radius), 0.75rem text |

## Surfaces and shape

- Cards: `#333333` fill, 12px radius, 1px border in white at 5% opacity, shadow `0 10px 25px rgba(0,0,0,0.4)`.
- Inputs: 6px radius.
- Side drawer: slides in from the right with a left-edge shadow.
- Pills: small, rounded, white text on the status colors above.
- Transitions: 0.2–0.3s ease. Respect `prefers-reduced-motion`.
