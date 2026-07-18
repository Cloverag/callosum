---
name: design-system-extractor
version: 2.0.0
description: Specialized skill for reverse-engineering Design Systems from websites. Uses Python pre-processing to extract design tokens without hitting token limits, and generates complete HTML documentation using real fragments and images from the original site.
---

<skill>
<skill_info>
<name>design-system-extractor</name>
<version>2.0.0</version>
<description>Specialized skill for reverse-engineering Design Systems from websites. Uses Python pre-processing to extract design tokens without hitting token limits. Generates complete HTML documentation in Storybook/Figma format.</description>
</skill_info>

<triggers>
<use_cases>
- User requests a Design System analysis of a website
- Request to extract colors, typography, or components from a URL
- Request for style documentation or a pattern library
- Reverse engineering of website UI/UX
- Creating design tokens from existing sites
</use_cases>
<activation_commands>
- "extract the design system from this site"
- "analyze the design of this website"
- "create design system documentation"
- "generate a design pattern"
- "UI reverse engineering"
- "extract colors and typography"
</activation_commands>
</triggers>

<instructions>
<data_collection_and_sanitization>
CRITICAL — BEFORE ANALYZING: Due to token limits, NEVER read raw HTML or CSS in full. Use the Python pre-processor.

File Location:
All Python files are in the `tools/` folder of this skill:
.agents/skills/design-system-extractor/tools/
├── design_system_extractor.py
├── extract_tokens.py
└── requirements.txt

Required Flow:
```bash
# Navigate to the tools folder
cd .agents/skills/design-system-extractor/tools/

# Install dependencies (first time only)
pip install -r requirements.txt

# Run the Python pre-processor
python design_system_extractor.py <URL>
```

What the Python script does:
Step A: HTML Sanitization
- Removes ALL `<svg>`, `<path>`, `<script>`, `<noscript>`, `<iframe>`, `<style>` tags
- Removes base64 data (`src="data:image..."`)
- Keeps only structure: `<header>`, `<main>`, `<section>`, `<h1>`-`<h6>`, `<p>`, `<a>`, `<button>`, and CSS classes

Step B: External CSS Extraction
- Identifies `<link rel="stylesheet">` tags in `<head>`
- Fetches `.css` files
- Uses regex to extract ONLY:
  - `:root { ... }` block (90% of Design Tokens)
  - `@font-face` rules
  - Important global classes (`.btn`, `.card`, `.container`, `h1, h2, h3`)

Step C: Utility Framework Detection
- Detects Tailwind patterns: `text-[16px]`, `bg-[#RRGGBB]`, `leading-tight`
- Spacing patterns: `m-4`, `p-8`, `gap-16`, `w-full`
- Typography: `font-bold`, `text-xl`, `tracking-wide`

</data_collection_and_sanitization>

<data_analysis>
Using the JSON returned by Python, analyze:

Colors:
- Prioritize colors from CSS variables (:root)
- If no :root exists, use colors detected in HTML/Tailwind
- Classify into: Brand, Black, White, Gray (light/medium/dark/text/muted/social)
- Detect gradients and opacities
- Document usage of each color (CTAs, text, background, borders)

Typography:
- Font-family from CSS variables or @font-face
- If Google Fonts are used, extract from the <link> tag in HTML
- Font-size: mega (130px), hero (86px), display (66px), h1-h6, body, small
- Font-weight: 400, 500, 600, 700
- Line-height: tight (0.94), snug (1.03), normal (1.2), relaxed (1.25), loose (1.65)
- Letter-spacing: tighter (-0.05em), tight (-0.035em), normal (-0.03em), wide (0.175em)

Spacing:
- Based on a 4px unit
- Space system: 1(4px), 2(8px), 4(12px), 6(16px), 8(20px), 10(24px), 16(40px), 24(60px), 40(90px), 75(150px), 100(200px), 125(250px)
- Container widths: max (1920px), content (1400px), narrow (1360px), small (1200px), text (800px), tight (780px)

</data_analysis>

<component_catalog>
Use the components detected by Python and expand:

Buttons (Minimum 4 types):
- Primary: brand background, pill radius (100px), height 40px
- Chip: gray background, pill radius, hover/active states
- Link: text only, with animated arrow suffix
- FAB: fixed position, backdrop-filter, pulse animation
- Padding, border-radius, font-size, font-weight, transitions

Cards (Minimum 3 types):
- Project Card: media with image, content, title, subtitle
- Partner Card: image left, content right, max-width 310px
- Pane Card: index number, title, subtitle with divider line
- Borders (15-20px radius), shadows, hover effects, image aspect ratios

Forms:
- Textfield: animated underline, large label, height 56px
- Selectbox: underline + chevron suffix
- Filebox: dashed border, drag & drop style
- Checkbox: custom control with checkmark
- Input styles, labels, validation states, focus states

Navigation:
- Sticky header with transition
- Logo + horizontal menu + CTA button
- Dropdown with arrow animation
- Scroll-based color change

</component_catalog>

<assets_and_media>
CRITICAL FOR VISUAL IMMERSION:
- Capture and USE the real image URLs from the site (original logo, banners, profile photos, card images).
- The generated HTML MUST incorporate these "real pieces" of the site in <img> tags and component backgrounds. Do not use only solid colors if the original site uses rich imagery.
- This ensures the generated documentation has the look and feel of the original site.

Images:
- Extract URLs from src (always use the originals from the site)
- Identify format (WebP, JPG, PNG, SVG)
- Document aspect ratios (e.g. 55% padding-top for cards)
- Note border-radius and effects (hover scale, etc.)

Icons and Logos:
- Insert the exact URL of the original site's logo in the sidebar and headers.
- Library (FontAwesome, Material, Phosphor, custom SVG)
- Style (filled, outline, duotone)
- Extract inline SVGs when possible, or use the original URLs

</assets_and_media>

<animations_and_interactions>
- Transition durations: fast (0.15s), normal (0.25s), slow (0.5s)
- Timing functions: ease-smooth cubic-bezier(0.65, 0.05, 0.36, 1)
- Keyframe animations: heartbeat, fade, slide, scale, pulse, ticker
- Scroll-based animations (GSAP, ScrollMagic, AOS)
- Hover effects: transform, opacity, background-color
</animations_and_interactions>

<grid_and_layout>
- Container max-widths
- Grid system (CSS grid, flexbox)
- Breakpoints (1024px, 768px)
- Gaps and gutters
- Z-index scale: base (1), dropdown (2), header (3), sticky (10), fixed (55), overlay (100)
</grid_and_layout>
</instructions>

<anti_hallucination_guidelines>
CRITICAL: To avoid fabricating data:

Base tokens STRICTLY on the data from the JSON returned by Python.

If the site uses heavy minification (classes .a, .b, .c) and no CSS is mapped:
- Infer the Design System by analyzing numeric patterns
- Use industry defaults (4px grid, 1.25 type scale)

NEVER invent colors or fonts that are not present in the analyzed data.

If information is missing, use default values documented as "Default".

NO EMPTY PLACEHOLDERS: Instead of leaving [URL] or generic gray images, ALWAYS inject the REAL image, photo, and logo URLs extracted from the site into the HTML. The documentation should look like a piece of the real site.
</anti_hallucination_guidelines>

<output_format>
<description>
HTML file (design_pattern.html)
Generate ONLY the final HTML code. Do not add explanations before or after the code.
Use the template below and REPLACE the [Site Name], #HEX, and value placeholders with the actual extracted properties.
IMPORTANT: Replace ALL placeholders such as <!-- Site Logo SVG -->, <img src="[URL]">, or text reading "LOGO" with the REAL image URLs captured from the site.
Keep all CSS boilerplate exactly as provided, only modifying the :root block.
</description>
<html_template>

<![CDATA[
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>[Site Name] Design System | Design Pattern</title>

<!-- Import detected fonts -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">

<style>
/* ============================================
DESIGN TOKENS - [Site Name] Design System
============================================ */
:root {
/* ===== COLORS ===== */
--color-brand: #000000;
--color-brand-hover: #222222;
--color-black: #000000;
--color-white: #FFFFFF;
--color-gray-light: #EEEEEE;
--color-gray-medium: #CDCDCD;
--color-gray-text: #9A9A9A;
--color-gray-dark: #7B7B7B;
--color-gray-muted: #575757;
--color-gray-social: #CBCBCB;

/* ===== TYPOGRAPHY ===== */
--font-family: 'Inter', sans-serif;
--font-weight-regular: 400;
--font-weight-medium: 500;
--font-weight-semibold: 600;
--font-weight-bold: 700;

/* ===== FONT SIZES ===== */
--text-xs: 8px;
--text-sm: 12px;
--text-base: 14px;
--text-md: 16px;
--text-lg: 18px;
--text-xl: 22px;
--text-2xl: 24px;
--text-3xl: 26px;
--text-4xl: 28px;
--text-5xl: 36px;
--text-6xl: 42px;
--text-7xl: 46px;
--text-8xl: 50px;
--text-display: 66px;
--text-hero: 86px;
--text-mega: 130px;

/* ===== LINE HEIGHTS ===== */
--leading-tight: 0.94;
--leading-snug: 1.03;
--leading-normal: 1.2;
--leading-relaxed: 1.25;
--leading-loose: 1.65;

/* ===== LETTER SPACING ===== */
--tracking-tighter: -0.05em;
--tracking-tight: -0.035em;
--tracking-normal: -0.03em;
--tracking-wide: 0.175em;

/* ===== SPACING ===== */
--space-1: 4px;
--space-2: 8px;
--space-4: 12px;
--space-6: 16px;
--space-8: 20px;
--space-10: 24px;
--space-16: 40px;
--space-24: 60px;
--space-40: 90px;
--space-75: 150px;
--space-100: 200px;
--space-125: 250px;

/* ===== CONTAINERS ===== */
--container-max: 1920px;
--container-content: 1400px;
--container-narrow: 1360px;
--container-small: 1200px;
--container-text: 800px;
--container-tight: 780px;

/* ===== BORDER RADIUS ===== */
--radius-sm: 5px;
--radius-md: 15px;
--radius-lg: 20px;
--radius-full: 50%;
--radius-pill: 100px;

/* ===== SHADOWS ===== */
--shadow-none: 0 0 0 0 rgba(0,0,0, 0);
--shadow-sm: 0 0 0 0 rgba(0,0,0, 0.1);
--shadow-md: 0px 0px 20px rgba(13, 13, 13, 0.2);

/* ===== TRANSITIONS ===== */
--transition-fast: 0.15s;
--transition-normal: 0.25s;
--transition-slow: 0.5s;
--ease-smooth: cubic-bezier(0.65, 0.05, 0.36, 1);

/* ===== Z-INDEX ===== */
--z-base: 1;
--z-dropdown: 2;
--z-header: 3;
--z-sticky: 10;
--z-fixed: 55;
--z-overlay: 100;
}

/* Base styles */
/* Layout (sidebar + main) */
/* Components */
/* Utilities */
/* Responsive */
</style>
</head>
<body>
<!-- Scroll Progress Indicator -->
<div class="ds-scroll-indicator" id="scrollIndicator"></div>

<div class="ds-layout">
<!-- Sidebar Navigation -->
<aside class="ds-sidebar">
<div class="ds-sidebar-logo">
<!-- INSERT THE REAL LOGO URL FROM THE SITE HERE -->
<img src="[REAL LOGO URL]" alt="Site logo" style="max-width: 100%;">
</div>

<nav>
<ul class="ds-nav">
<li class="ds-nav-section">Foundations</li>
<li class="ds-nav-item"><a href="#colors" class="ds-nav-link">Colors</a></li>
<li class="ds-nav-item"><a href="#typography" class="ds-nav-link">Typography</a></li>
<li class="ds-nav-item"><a href="#spacing" class="ds-nav-link">Spacing</a></li>
<li class="ds-nav-item"><a href="#icons" class="ds-nav-link">Icons</a></li>

<li class="ds-nav-section">Components</li>
<li class="ds-nav-item"><a href="#buttons" class="ds-nav-link">Buttons</a></li>
<li class="ds-nav-item"><a href="#cards" class="ds-nav-link">Cards</a></li>
<li class="ds-nav-item"><a href="#forms" class="ds-nav-link">Forms</a></li>
<li class="ds-nav-item"><a href="#navigation" class="ds-nav-link">Navigation</a></li>
<li class="ds-nav-item"><a href="#badges" class="ds-nav-link">Badges & Chips</a></li>

<li class="ds-nav-section">Patterns</li>
<li class="ds-nav-item"><a href="#numbers" class="ds-nav-link">Numbers & Stats</a></li>
<li class="ds-nav-item"><a href="#awards" class="ds-nav-link">Awards</a></li>
<li class="ds-nav-item"><a href="#footer" class="ds-nav-link">Footer</a></li>
<li class="ds-nav-item"><a href="#animations" class="ds-nav-link">Animations</a></li>
</ul>
</nav>
</aside>

<!-- Main Content -->
<main class="ds-main">
<!-- Header -->
<header class="ds-header">
<h1 class="ds-title">Design System</h1>
<p class="ds-subtitle">Complete Design System documentation for [Site Name] — extracted via reverse engineering of the official site.</p>
</header>

<!-- Colors Section -->
<section id="colors" class="ds-section">
<h2 class="ds-section-title">Colors</h2>
<p class="ds-section-description">
The color palette is built around [brand color] as the primary accent,
contrasting with black, white, and gray tones.
</p>

<h3 class="ds-mb-16">Brand Colors</h3>
<div class="ds-color-grid ds-mb-40">
<div class="ds-color-card">
<div class="ds-color-swatch" style="background-color: var(--color-brand);"></div>
<div class="ds-color-info">
<div class="ds-color-name">Brand Color</div>
<div class="ds-color-value">[#HEX]</div>
<div class="ds-color-usage">CTAs, links, icons, hover states</div>
</div>
</div>
<!-- More colors... -->
</div>

<div class="ds-code">
<div class="ds-code-title">CSS Variables</div>
<pre>:root {
--color-brand: [#HEX];
--color-brand-hover: [#HEX];
--color-black: #000000;
--color-white: #FFFFFF;
--color-gray-light: #EEEEEE;
--color-gray-medium: #CDCDCD;
--color-gray-text: #9A9A9A;
--color-gray-dark: #7B7B7B;
--color-gray-muted: #575757;
--color-gray-social: #CBCBCB;
}</pre>
</div>
</section>

<!-- Typography Section -->
<section id="typography" class="ds-section">
<h2 class="ds-section-title">Typography</h2>
<p class="ds-section-description">
Typography uses the <strong>[Font Name]</strong> font with weights from 400 to 700.
The type system is characterized by negative letter-spacing and tight line-heights.
</p>

<div class="ds-type-scale">
<div class="ds-type-item">
<div class="ds-type-preview" style="font-size: 130px; font-weight: 700; line-height: 0.94; letter-spacing: -0.05em;">
Mega Title
</div>
<div class="ds-type-meta">
<div class="ds-type-meta-item">font-size: 130px</div>
<div class="ds-type-meta-item">line-height: 0.94</div>
<div class="ds-type-meta-item">letter-spacing: -0.05em</div>
<div class="ds-type-meta-item">font-weight: 700</div>
</div>
</div>
<!-- More type levels... -->
</div>
</section>

<!-- Spacing Section -->
<section id="spacing" class="ds-section">
<h2 class="ds-section-title">Spacing</h2>
<p class="ds-section-description">
The spacing system is based on a <strong>4px</strong> unit.
Major sections are separated by 200px, with 90px lateral padding.
</p>

<div class="ds-spacing-grid ds-mb-40">
<div class="ds-spacing-item">
<div class="ds-spacing-box" style="width: 4px;"></div>
<div class="ds-spacing-label">Space 1</div>
<div class="ds-spacing-value">4px</div>
</div>
<!-- More spaces... -->
</div>
</section>

<!-- Icons Section -->
<section id="icons" class="ds-section">
<h2 class="ds-section-title">Icons</h2>
<p class="ds-section-description">
All icons are custom inline SVGs with no external libraries.
They use <code>currentColor</code> to inherit color from context.
</p>

<div class="ds-icons-grid ds-mb-40">
<div class="ds-icon-card">
<svg class="ds-icon-preview" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
<!-- SVG path -->
</svg>
<div class="ds-icon-name">Icon Name</div>
<div class="ds-icon-code">Custom SVG</div>
</div>
<!-- More icons... -->
</div>
</section>

<!-- Buttons Section -->
<section id="buttons" class="ds-section">
<h2 class="ds-section-title">Buttons</h2>
<p class="ds-section-description">
Buttons are characterized by a pill border-radius (100px),
fast transitions (0.15s), and clear hover states.
</p>

<div class="ds-buttons-grid ds-mb-40">
<div class="ds-button-card">
<h4 class="ds-mb-16">Primary Button</h4>
<div class="ds-button-example">
<button class="ds-btn ds-btn-primary">Button</button>
</div>
<div class="ds-code">
<pre>.ds-btn-primary {
background: var(--color-brand);
color: #FFFFFF;
border-radius: 100px;
height: 40px;
padding: 0 20px;
font-size: 14px;
font-weight: 600;
}</pre>
</div>
</div>
<!-- More buttons... -->
</div>
</section>

<!-- Cards Section -->
<section id="cards" class="ds-section">
<h2 class="ds-section-title">Cards</h2>
<p class="ds-section-description">
Cards are used for projects, partners, and information.
They feature a light background, 15-20px border-radius, and subtle hover effects.
</p>

<h3 class="ds-mb-24">Project Cards</h3>
<div class="ds-cards-grid ds-mb-40">
<div class="ds-card">
<div class="ds-card-media">
<!-- REPLACE WITH REAL IMAGE URL EXTRACTED FROM SITE -->
<img src="[REAL IMAGE URL FROM SITE]" alt="Project">
</div>
<div class="ds-card-content">
<h3 class="ds-card-title">Title</h3>
<p class="ds-card-text">Subtitle</p>
</div>
</div>
</div>

<h3 class="ds-mb-24">Partner Cards</h3>
<div class="ds-cards-grid ds-mb-40">
<div class="ds-partner-card">
<div class="ds-partner-image">
<!-- REPLACE WITH REAL IMAGE URL EXTRACTED FROM SITE -->
<img src="[REAL IMAGE URL FROM SITE]" alt="Partner">
</div>
<div class="ds-partner-content">
<div class="ds-partner-title">Partner Name</div>
<div class="ds-partner-subtitle">Client</div>
</div>
</div>
</div>

<h3 class="ds-mb-24">Pane Cards</h3>
<div class="ds-cards-grid ds-mb-40">
<div class="ds-pane-card">
<div class="ds-pane-index">01</div>
<h3 class="ds-pane-title">Service</h3>
<p class="ds-pane-subtitle">Description</p>
</div>
</div>
</section>

<!-- Forms Section -->
<section id="forms" class="ds-section">
<h2 class="ds-section-title">Forms</h2>
<p class="ds-section-description">
Form elements are minimalist, with an animated underline on focus
and large, bold labels.
</p>

<div class="ds-form-grid ds-mb-40">
<div class="ds-form-card">
<h3 class="ds-form-title">Text Fields</h3>

<div class="ds-textfield">
<label class="ds-textfield-label">Name</label>
<input type="text" class="ds-textfield-input" placeholder="Your name">
</div>
</div>

<div class="ds-form-card">
<h3 class="ds-form-title">Select & File Upload</h3>

<div class="ds-selectbox">
<input type="text" class="ds-selectbox-input" value="Option" readonly>
<svg class="ds-selectbox-suffix" viewBox="0 0 18 10"><!-- chevron --></svg>
</div>

<div class="ds-filebox">
<div class="ds-filebox-icon">+</div>
<div class="ds-filebox-title">Upload Files</div>
<div class="ds-filebox-text">Drag & drop or click</div>
</div>

<label class="ds-checkbox">
<input type="checkbox" class="ds-checkbox-input">
<span class="ds-checkbox-control"></span>
<span class="ds-checkbox-label">I agree</span>
</label>
</div>
</div>
</section>

<!-- Navigation Section -->
<section id="navigation" class="ds-section">
<h2 class="ds-section-title">Navigation</h2>
<p class="ds-section-description">
Navigation is sticky, with a smooth color transition on scroll.
Dropdowns appear with a 0.25s delay.
</p>

<div class="ds-nav-example ds-mb-40">
<nav class="ds-nav-bar">
<div class="ds-nav-bar-left">
<div class="ds-nav-bar-logo">
<!-- REPLACE WITH REAL LOGO URL -->
<img src="[REAL LOGO URL]" alt="Logo" style="height: 30px;">
</div>
<ul class="ds-nav-bar-menu">
<li class="ds-nav-bar-item"><a href="#" class="ds-nav-bar-link">Link</a></li>
<li class="ds-nav-bar-item"><a href="#" class="ds-nav-bar-link ds-nav-bar-dropdown">Dropdown</a></li>
</ul>
</div>
<button class="ds-btn ds-btn-primary">CTA</button>
</nav>
</div>
</section>

<!-- Badges & Chips Section -->
<section id="badges" class="ds-section">
<h2 class="ds-section-title">Badges & Chips</h2>
<p class="ds-section-description">
Chips are used for tags, filters, and categories.
They have a pill shape and clear hover/active states.
</p>

<div class="ds-chips-row ds-mb-40">
<span class="ds-chip">Tag 1</span>
<span class="ds-chip">Tag 2</span>
<span class="ds-chip ds-chip-active">Active</span>
</div>
</section>

<!-- Numbers & Stats Section -->
<section id="numbers" class="ds-section">
<h2 class="ds-section-title">Numbers & Stats</h2>
<p class="ds-section-description">
Large numbers highlight statistics and achievements.
Uses mega typography (130px) with negative letter-spacing.
</p>

<div class="ds-numbers-grid ds-mb-40">
<div class="ds-number-item">
<div class="ds-number-value">150+</div>
<div class="ds-number-label">Projects</div>
<div class="ds-number-note">Completed</div>
</div>
</div>
</section>

<!-- Awards Section -->
<section id="awards" class="ds-section">
<h2 class="ds-section-title">Awards</h2>
<p class="ds-section-description">
Awards list with animated underline on hover.
Clean design with subtle item separation.
</p>

<div class="ds-awards-list ds-mb-40">
<div class="ds-award-item">
<div class="ds-award-header">
<div class="ds-award-name">Award Name</div>
<div class="ds-award-year">2025</div>
</div>
</div>
</div>
</section>

<!-- Footer Section -->
<section id="footer" class="ds-section">
<h2 class="ds-section-title">Footer</h2>
<p class="ds-section-description">
The footer uses a dark background with white and gray text.
4-column grid with links and contact information.
</p>

<div class="ds-footer-example ds-mb-40">
<div style="font-size: 50px; color: var(--color-gray-muted);">hello@example.com</div>

<div class="ds-footer-grid">
<div class="ds-footer-col">
<div class="ds-footer-col-title">Services</div>
<ul class="ds-footer-col-list">
<li class="ds-footer-col-item"><a href="#" class="ds-footer-col-link">Service 1</a></li>
</ul>
</div>
</div>

<div class="ds-footer-bottom">
<div class="ds-footer-bottom-text">© 2026 Brand</div>
</div>
</div>
</section>

<!-- Animations Section -->
<section id="animations" class="ds-section">
<h2 class="ds-section-title">Animations</h2>
<p class="ds-section-description">
Animations are subtle and elegant, using GSAP and ScrollMagic
for scroll-based effects.
</p>

<div class="ds-animation-grid ds-mb-40">
<div class="ds-animation-card">
<div class="ds-animation-box fade"></div>
<div class="ds-animation-name">Fade</div>
</div>
<div class="ds-animation-card">
<div class="ds-animation-box slide"></div>
<div class="ds-animation-name">Slide</div>
</div>
<div class="ds-animation-card">
<div class="ds-animation-box scale"></div>
<div class="ds-animation-name">Scale</div>
</div>
<div class="ds-animation-card">
<div class="ds-animation-box pulse"></div>
<div class="ds-animation-name">Pulse</div>
</div>
</div>

<div class="ds-code">
<div class="ds-code-title">Keyframe Animations</div>
<pre>@keyframes heartbeat {
0%, 20%, 40%, 100% { transform: scale(1); }
10%, 30% { transform: scale(1.1); }
}

@keyframes pulse {
0%, 100% {
transform: scale(0.9);
box-shadow: 0 0 0 0 rgba(0,0,0, 0.1);
}
70% {
transform: scale(1);
box-shadow: 0 0 0 50px rgba(0,0,0, 0);
}
}</pre>
</div>
</section>
</main>
</div>

<!-- JavaScript for interactivity -->
<script>
// Scroll Progress Indicator
window.addEventListener('scroll', function() {
const scrollTop = window.scrollY;
const docHeight = document.documentElement.scrollHeight - window.innerHeight;
const scrollPercent = (scrollTop / docHeight) * 100;
document.getElementById('scrollIndicator').style.width = scrollPercent + '%';
});

// Smooth scroll for navigation links
document.querySelectorAll('.ds-nav-link').forEach(link => {
link.addEventListener('click', function(e) {
e.preventDefault();
const targetId = this.getAttribute('href');
const targetElement = document.querySelector(targetId);

if (targetElement) {
targetElement.scrollIntoView({
behavior: 'smooth',
block: 'start'
});
}
});
});

// Active navigation link on scroll
const sections = document.querySelectorAll('.ds-section');
const navLinks = document.querySelectorAll('.ds-nav-link');

window.addEventListener('scroll', function() {
let current = '';

sections.forEach(section => {
const sectionTop = section.offsetTop;
const sectionHeight = section.clientHeight;

if (pageYOffset >= sectionTop - 200) {
current = section.getAttribute('id');
}
});

navLinks.forEach(link => {
link.classList.remove('active');
if (link.getAttribute('href') === '#' + current) {
link.classList.add('active');
}
});
});
</script>
</body>
</html>
]]>


</html_template>
</output_format>

<validation_checklist>
Before delivering, verify:
Design Tokens:

All primary colors extracted (brand, black, white, 6+ gray shades)

Font-family identified and imported from Google Fonts

Complete type scale (minimum 10 levels: mega, hero, display, h1-h6, body)

Line-heights documented (tight, snug, normal, relaxed, loose)

Letter-spacing documented (tighter, tight, normal, wide)

Complete spacing system (minimum 10 values)

Container widths defined

Border radius system (sm, md, lg, full, pill)

Shadows documented

Transitions (fast, normal, slow) + easing

Z-index scale

Components and Visuals:

Real logos and images from the site have been injected into the final HTML (no empty placeholders)

Minimum 4 button types (primary, chip, link, fab)

Minimum 3 card types populated with REAL EXTRACTED IMAGES (project, partner, pane)

Form elements (textfield, selectbox, filebox, checkbox)

Navigation example (sticky nav with real logo + menu + CTA)

Badges & Chips with states

Icons documented (inline SVG)

Numbers & Stats with mega typography

Awards list with animation

Footer example (4 columns)

Animations demonstrated (fade, slide, scale, pulse)

Structure:

CSS variables in :root (all categories)

Functional sidebar navigation

Scroll progress indicator

Smooth scroll navigation

Active navigation on scroll

Responsive (media queries: 1024px, 768px)

Code examples in each section

Utility classes (margin, color, text-align)
</validation_checklist>

<required_tools>

Python 3.x — For pre-processing

requests — Python library for HTTP requests

beautifulsoup4 — Python library for HTML parsing

write — To create the HTML file

Location: All files are in tools/ inside this skill.
</required_tools>

<usage_example>
User Input:
"Extract the design system from this site: https://example.com"

Execution Flow:

Navigate to the tools folder and install dependencies:
cd .agents/skills/design-system-extractor/tools/
pip install -r requirements.txt

Run the Python pre-processor:
python design_system_extractor.py https://example.com

Analyze the returned JSON:
{
"url": "https://example.com",
"fonts": ["Inter", "Roboto"],
"css_variables": {
"color-brand": "#0070F3",
"color-black": "#000000"
},
"colors": ["#0070F3", "#000000", "#FFFFFF"],
"components": [
{"type": "button", "count": 5},
{"type": "card", "count": 12}
],
"images": ["https://example.com/logo.png", "https://example.com/banner.jpg"]
}

Generate HTML with extracted data, replacing <img> tags with real image URLs from the JSON.

Save file as design_pattern.html

Deliver with a summary of the main elements (Colors, Fonts, Components, and the generated file).
</usage_example>

<section_templates>

Color Card Template
<div class="ds-color-card">
    <div class="ds-color-swatch" style="background-color: #HEX;"></div>
    <div class="ds-color-info">
        <div class="ds-color-name">Color Name</div>
        <div class="ds-color-value">#HEX</div>
        <div class="ds-color-usage">Usage description</div>
    </div>
</div>

Type Item Template
<div class="ds-type-item">
  <div class="ds-type-preview" style="font-size: XXpx; font-weight: XXX; line-height: X.XX; letter-spacing: -X.XXem;">
      Preview Text
  </div>
  <div class="ds-type-meta">
      <div class="ds-type-meta-item">font-size: XXpx</div>
      <div class="ds-type-meta-item">line-height: X.XX</div>
      <div class="ds-type-meta-item">letter-spacing: -X.XXem</div>
      <div class="ds-type-meta-item">font-weight: XXX</div>
  </div>
</div>

Spacing Item Template
<div class="ds-spacing-item">
  <div class="ds-spacing-box" style="width: XXpx;"></div>
  <div class="ds-spacing-label">Space Name</div>
  <div class="ds-spacing-value">XXpx</div>
</div>

Icon Card Template
<div class="ds-icon-card">
  <svg class="ds-icon-preview" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="..."/>
  </svg>
  <div class="ds-icon-name">Icon Name</div>
  <div class="ds-icon-code">Custom SVG</div>
</div>

Button Card Template
<div class="ds-button-card">
  <h4 class="ds-mb-16">Button Name</h4>
  <div class="ds-button-example">
      <button class="ds-btn ds-btn-type">Button</button>
  </div>
  <div class="ds-code">
      <pre>.ds-btn-type {
  background: #XXX;
  color: #XXX;
  border-radius: 100px;
  height: 40px;
  font-size: XXpx;
  font-weight: 600;
}</pre>
  </div>
</div>

Project Card Template
<div class="ds-card">
  <div class="ds-card-media">
      <!-- REPLACE WITH REAL URL EXTRACTED FROM SITE -->
      <img src="[REAL IMAGE URL FROM SITE]" alt="Project">
  </div>
  <div class="ds-card-content">
      <h3 class="ds-card-title">Project Title</h3>
      <p class="ds-card-text">Category</p>
  </div>
</div>

Partner Card Template
<div class="ds-partner-card">
  <div class="ds-partner-image">
      <!-- REPLACE WITH REAL URL EXTRACTED FROM SITE -->
      <img src="[REAL IMAGE URL FROM SITE]" alt="Partner">
  </div>
  <div class="ds-partner-content">
      <div class="ds-partner-title">Partner Name</div>
      <div class="ds-partner-subtitle">Client</div>
  </div>
</div>

Pane Card Template
<div class="ds-pane-card">
  <div class="ds-pane-index">01</div>
  <h3 class="ds-pane-title">Service Name</h3>
  <p class="ds-pane-subtitle">Description text</p>
</div>

Form Elements Template
<!-- Textfield -->
<div class="ds-textfield">
  <label class="ds-textfield-label">Label</label>
  <input type="text" class="ds-textfield-input" placeholder="Placeholder">
</div>

<!-- Selectbox -->
<div class="ds-selectbox">
  <input type="text" class="ds-selectbox-input" value="Option" readonly>
  <svg class="ds-selectbox-suffix" viewBox="0 0 18 10"><!-- chevron --></svg>
</div>

<!-- Filebox -->
<div class="ds-filebox">
  <div class="ds-filebox-icon">+</div>
  <div class="ds-filebox-title">Upload Files</div>
  <div class="ds-filebox-text">Drag & drop or click</div>
</div>

<!-- Checkbox -->
<label class="ds-checkbox">
  <input type="checkbox" class="ds-checkbox-input">
  <span class="ds-checkbox-control"></span>
  <span class="ds-checkbox-label">Label</span>
</label>

Number Stats Template
<div class="ds-number-item">
  <div class="ds-number-value">150+</div>
  <div class="ds-number-label">Label</div>
  <div class="ds-number-note">Note text</div>
</div>

Award Item Template
<div class="ds-award-item">
  <div class="ds-award-header">
      <div class="ds-award-name">Award Name</div>
      <div class="ds-award-year">2025</div>
  </div>
</div>

Animation Card Template
<div class="ds-animation-card">
  <div class="ds-animation-box fade"></div>
  <div class="ds-animation-name">AnimationName</div>
</div>

Code Block Template
<div class="ds-code">
  <div class="ds-code-title">Section Title</div>
  <pre>.class {
  property: value;
}</pre>
</div>

Utility Classes
.ds-mb-0 { margin-bottom: 0; }
.ds-mb-8 { margin-bottom: var(--space-8); }
.ds-mb-16 { margin-bottom: var(--space-16); }
.ds-mb-24 { margin-bottom: var(--space-24); }
.ds-mb-40 { margin-bottom: var(--space-40); }

.ds-text-brand { color: var(--color-brand); }
.ds-text-gray { color: var(--color-gray-text); }
.ds-text-center { text-align: center; }

.ds-bg-black { background-color: var(--color-black); }
.ds-bg-white { background-color: var(--color-white); }
.ds-bg-gray { background-color: var(--color-gray-light); }
</section_templates>

<best_practices>
Always use CSS variables for consistency
Always inject REAL images from the site (logos, banners, card photos) into the generated HTML to create a visual catalog identical to the original, functioning as literal pieces of the site
Always document states (hover, active, focus, disabled)
Always include code examples in each section
Maintain fidelity to the original design
Use descriptive token names (brand, gray-light, etc.)
Document responsive breakpoints (1024px, 768px)
Include animations and transitions with timing functions
Follow the layout structure: sidebar + main content
Implement scroll progress indicator
Add smooth scroll and active navigation
Use utility classes for margins and colors
Include at least 10 spacing levels
Document line-heights and letter-spacing for typography
Create at least 4 button types and 3 card types populated with real media
</best_practices>

<required_css_structure>
Base Layout
.ds-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  min-height: 100vh;
}

.ds-sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  background-color: var(--color-black);
  color: var(--color-white);
  padding: var(--space-40) var(--space-24);
  overflow-y: auto;
}

.ds-main {
  padding: var(--space-50) var(--space-75);
  max-width: var(--container-max);
}

Header
.ds-header {
  margin-bottom: var(--space-100);
  padding-bottom: var(--space-50);
  border-bottom: 1px solid var(--color-gray-light);
}

.ds-title {
  font-size: var(--text-mega);
  font-weight: var(--font-weight-bold);
  line-height: var(--leading-tight);
  letter-spacing: var(--tracking-tighter);
}

.ds-subtitle {
  font-size: var(--text-5xl);
  font-weight: var(--font-weight-medium);
  color: var(--color-gray-text);
}

Sections
.ds-section {
  margin-bottom: var(--space-100);
}

.ds-section-title {
  font-size: var(--text-5xl);
  font-weight: var(--font-weight-bold);
  margin-bottom: var(--space-40);
  padding-bottom: var(--space-16);
  border-bottom: 3px solid var(--color-brand);
  display: inline-block;
}

.ds-section-description {
  font-size: var(--text-lg);
  color: var(--color-gray-text);
  margin-bottom: var(--space-40);
  max-width: var(--container-text);
}

Scroll Indicator
.ds-scroll-indicator {
  position: fixed;
  top: 0;
  left: 0;
  height: 3px;
  background-color: var(--color-brand);
  z-index: var(--z-fixed);
  width: 0%;
  transition: width 0.1s;
}
</required_css_structure>

<limitations>
- Do not copy copyright-protected code
- Use for educational/reference purposes only
- Respect font and asset licenses
- Do not reproduce protected text content
- Sites with anti-scraping protection may fail to fetch
</limitations>

<setup_and_metadata>
Python Dependencies:
Install before using:
```bash
# Navigate to the tools folder
cd .agents/skills/design-system-extractor/tools/

# Install dependencies
pip install -r requirements.txt
```
Or directly:
```bash
pip install requests beautifulsoup4
```

requirements.txt:
```
requests>=2.31.0
beautifulsoup4>=4.12.0
```

Location: tools/requirements.txt inside this skill.

Versioning:
Version: 2.0.0 (Optimized with Python)
Last updated: 2026-03-19

v2.0 Improvements:
- Python pre-processing — Prevents context window overflow
- HTML sanitization — Removes SVGs, scripts, base64
- Selective CSS extraction — Focuses on :root, ignores the rest
- Tailwind detection — Token inference from utility classes
- Anti-hallucination — Strict guidelines to prevent fabricated data
- Optimized output — Generates only HTML with real image injection

File Structure:
```
.agents/skills/design-system-extractor/
├── SKILL.md                        # This skill (you are here)
└── tools/
    ├── design_system_extractor.py  # Main Python script
    ├── extract_tokens.py           # Standalone CSS token extractor
    ├── requirements.txt            # Python dependencies
    └── README.md                   # Tools documentation
```

Important: Always run Python scripts from the tools/ folder:
```bash
cd .agents/skills/design-system-extractor/tools/
python design_system_extractor.py <URL>
```
</setup_and_metadata>
</skill>
