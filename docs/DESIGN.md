# Workspace design

Reference: design-concept.png, generated with built-in Image Gen. Compact document workspace; white header, cool #f5f6fa backdrop, navy #111a33 text, violet #635bff actions. System sans-serif app typography; original document typography is preserved by each engine.

Header: HTMLtester / Upload PDF. Heading: Compare your PDF, side by side. Subtitle: Explore how different engines preserve layout and structure. Toolbar: File, Converter, Convert, Download HTML. Two equal document panes: Source PDF / Converted HTML. Thin borders, 8px radius, 16px pane gap, 32px desktop gutters. Mobile panes stack with their own scroll areas.

Functional extensions to concept: login/sign out, actual file limits, converter descriptions, preview/source toggle, conversion duration and errors. No seeded document or fabricated performance data. HTML flow outputs do not have page controls because their pagination differs from the source. PDF has real page/zoom controls. Source preview cannot execute converted scripts; generated HTML is sanitized and placed in an iframe without script or same-origin permissions.
