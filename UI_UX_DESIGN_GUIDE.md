# Dawn UI/UX Redesign - Visual & Usability Guide

## Component Architecture

### Page Structure
```
DawnExperience (Main Container)
├── DashboardHeader (NEW)
│   ├── Logo & Branding
│   ├── Workflow Status
│   └── Active Dataset Info
├── Sidebar (Improved)
│   ├── Logo
│   ├── Auth (Collapsible)
│   ├── System Status (Collapsible)
│   ├── Background Jobs (Collapsible)
│   └── Backends (Collapsible)
└── Main Content Area
    ├── Activity Feed (NEW)
    └── Tile Grid
        ├── Upload Panel (Enhanced)
        ├── Chat Panel (Redesigned)
        ├── Agent Panel (Improved)
        └── ... other panels
```

## Key UI Improvements

### 1. Header Section
- **Purpose**: Show current dataset and system status
- **Elements**:
  - Logo with "Dawn Horizon" branding
  - Current workflow stage (color-coded)
  - Active dataset name with row count
  - Context chunks counter
  - Refresh button

### 2. Sidebar Navigation
- **Collapsible Sections**: Auth, System, Jobs, Backends
- **Benefits**:
  - Reduces cognitive load
  - Keeps focus on main content
  - Organized information hierarchy
  - Desktop/mobile friendly

### 3. Upload Panel
- **Drag-and-Drop**: Full support with visual feedback
- **Real-time Status**: Shows file name and operation status
- **Better Form**: Organized input fields with labels
- **Success State**: Green checkmark + "Redis ready" indicator

### 4. Chat Panel
- **Message Bubbles**: User messages (amber), Assistant (sky blue)
- **Typing Indicator**: Animated dots show AI is thinking
- **Source Attribution**: Shows which sources informed the answer
- **Auto-scroll**: Scrolls to latest message automatically

### 5. Agent Panel
- **Status Indicator**: Animated spinner during execution
- **Plan Display**: Collapsible execution plan with steps
- **Warnings**: Highlighted in amber for visibility
- **Results**: Clear answer + task completion count

### 6. Toast Notifications (NEW)
- **Types**: Success (green), Error (red), Warning (amber), Info (blue)
- **Auto-dismiss**: 4-5 seconds by default
- **Positioned**: Bottom-right corner
- **Non-intrusive**: Doesn't block interactions

### 7. Onboarding Modal (NEW)
- **4 Steps**: Upload → Preview → Run Agents → Chat
- **Progress Bar**: Visual indication of progress
- **Skip Option**: Users can dismiss to explore freely
- **Step Navigation**: Click dots to jump to any step

## Color Palette

| Usage | Color | Hex |
|-------|-------|-----|
| Primary Accent | Amber | `#f59e0b` |
| Secondary | Pink | `#ec4899` |
| Tertiary | Sky Blue | `#0ea5e9` |
| Success | Emerald | `#10b981` |
| Warning | Amber | `#f59e0b` |
| Error | Rose | `#ef4444` |
| Background | Dark Blue | `#050812` |
| Surface | Slate 900 | `#0f1627` |

## Typography

| Element | Font | Size | Weight |
|---------|------|------|--------|
| Page Title | Space Grotesk | 2xl | 600 |
| Section Header | Space Grotesk | lg | 600 |
| Card Title | Space Grotesk | base | 600 |
| Body Text | System | sm | 400 |
| Labels | System | xs | 600 |
| Small Text | System | xs | 400 |

## Spacing Scale

- `xs`: 4px
- `sm`: 8px
- `md`: 12px
- `lg`: 16px
- `xl`: 20px
- `2xl`: 24px
- `3xl`: 32px
- `4xl`: 40px

## Interactions & Animations

### Transitions
- **Duration**: 200ms (default)
- **Easing**: cubic-bezier(0.4, 0, 0.2, 1)
- **Apply to**: color, border, shadow, background

### Animations
- `animate-slide-in`: 300ms entrance from left
- `animate-slide-up`: 400ms entrance from bottom
- `animate-fade-in`: 300ms fade entrance
- `animate-spin-slow`: 3s continuous rotation

### Hover States
- **Buttons**: Scale up + shadow enhancement
- **Cards**: Subtle background brightening
- **Interactive Elements**: Border/color emphasis

## Accessibility Features

1. **Focus States**
   - Clear ring (3px sky-blue) around focused elements
   - High contrast colors
   - Visible on all interactive elements

2. **Color Contrast**
   - All text meets WCAG AA standards
   - Non-color-dependent status indicators
   - Icons + text for important actions

3. **Semantic HTML**
   - Proper heading hierarchy (h1, h2, h3)
   - Form labels properly associated
   - ARIA attributes where needed

4. **Keyboard Navigation**
   - Tab order follows visual layout
   - Enter/Space activates buttons
   - Collapsible sections toggle with click or enter

## Demo Mode Enhancements

### Onboarding
- Auto-shows on first visit (opt-in)
- 4-step guided tour through features
- "Demo" badge shows this is example data

### Visual Feedback
- Activity feed shows each operation
- Status badges indicate progress
- Timestamp for transparency

### Quick Start
- Sample workbook suggestions
- Pre-filled example questions
- One-click demo data loading

## Performance Optimizations

1. **Code Splitting**: Each panel loads independently
2. **Lazy Loading**: Images and heavy components load on-demand
3. **CSS Optimization**: Tailwind classes minified in production
4. **Animation Performance**: Using CSS transforms for 60fps
5. **Viewport Optimization**: Responsive breakpoints at xs, sm, md, lg, xl

## Responsive Design

| Breakpoint | Screen Size | Sidebar | Grid Cols |
|-----------|-------------|---------|-----------|
| Mobile | < 640px | Full width | 1 column |
| Tablet | 640-1024px | Full width | 2 columns |
| Desktop | 1024-1280px | Sidebar left | 3 columns |
| Large | > 1280px | Sticky sidebar | 12 columns |

## Implementation Notes

### For Demos
1. **Start with Onboarding**: Automatically shows first-time visitors
2. **Use Activity Feed**: Shows what's happening in real-time
3. **Highlight Status**: Dashboard header shows current dataset
4. **Use Chat**: Shows real-time agent responses
5. **Demonstrate Collapsible Sidebar**: Keep focus on main content

### For Users
1. **Customize Sidebar**: Collapse unneeded sections
2. **Use Toast Notifications**: Check system feedback
3. **Drag-drop Files**: Faster than browsing
4. **Chat for Quick Answers**: Natural language queries
5. **Pin Important Panels**: Collapse less-used ones

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile Safari 14+

All with full CSS Grid, Flexbox, and CSS custom properties support.
