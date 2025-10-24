# Responsive Avatar Grid System

## Overview

A simple two-level flex grid system:
1. **Categories** - Flex items that wrap based on available width (min-width: 400px)
2. **Agent Cards** - Flex items within each category with fixed sizes (180px, 240px, 300px)

Categories naturally size based on their content, and both levels wrap automatically.

## Architecture

### Level 1: Categories (Outer Flex)
```jsx
<div className="flex flex-wrap gap-8">
  {categories.map(category => (
    <div className="flex-1 min-w-[400px]">
      {/* Level 2: Agent Cards */}
    </div>
  ))}
</div>
```

**Behavior:**
- Categories use `flex-1` to grow and share available width
- `min-w-[400px]` ensures categories don't get too narrow
- Wraps to new row when space is insufficient
- Gap between categories: 32px (gap-8)

### Level 2: Agent Cards (Inner Flex)
```jsx
<div className="flex flex-wrap gap-4">
  {agents.map(agent => (
    <AvatarCard width={cardWidth} />
  ))}
</div>
```

**Behavior:**
- Cards have fixed widths: 180px, 240px, or 300px
- `flex-shrink: 0` prevents cards from shrinking
- Wraps to new row when cards don't fit
- Gap between cards: 16px (gap-4)

## Card Sizes

### Fixed Widths Based on Viewport

| Viewport Width | Card Size | Card Width | Description |
|----------------|-----------|------------|-------------|
| < 1200px       | Small     | 180px      | Hidden      |
| 1200-1599px    | Medium    | 240px      | Shown       |
| ≥ 1600px       | Large     | 300px      | Shown       |

**Card Styles:**
- **Large**: p-4, text-base name, text-sm description
- **Medium**: p-3, text-sm name, text-xs description  
- **Small**: p-2, text-xs name, no description

## Layout Examples

### Wide Screen (≥1200px)
```
┌────────────────────────────────────────────────────────────┐
│  Sports                    │  Travelling                   │
│  [240px] [240px]           │  [240px]                      │
│                            │                               │
│  (flex-1 grow)             │  (flex-1 grow)                │
└────────────────────────────────────────────────────────────┘
```
**Categories share width equally (flex-1), cards wrap inside**

### Medium Screen (900-1200px)
```
┌────────────────────────────────────────────────────────────┐
│  Sports                                                    │
│  [180px] [180px]                                           │
│                                                            │
│  Travelling                                                │
│  [180px]                                                   │
└────────────────────────────────────────────────────────────┘
```
**Categories stack (min-width: 400px not met), smaller cards**

### Ultra-Wide (≥1600px)
```
┌────────────────────────────────────────────────────────────┐
│  Sports                    │  Travelling                   │
│  [300px] [300px]           │  [300px]                      │
│                            │                               │
└────────────────────────────────────────────────────────────┘
```
**Larger cards (300px), categories share space**

## How It Works

### 1. Card Size Selection (Simple Breakpoints)
```javascript
const updateCardSize = () => {
  const width = window.innerWidth;
  
  if (width >= 1600) {
    setCardSize('large');    // 300px cards
  } else if (width >= 1200) {
    setCardSize('medium');   // 240px cards
  } else {
    setCardSize('small');    // 180px cards
  }
};
```

### 2. Natural Flex Wrapping

**Categories (Outer Level):**
```jsx
<div className="flex flex-wrap gap-8">
  <div className="flex-1 min-w-[400px]">
    {/* Category content */}
  </div>
</div>
```
- Browser automatically wraps when `min-w-[400px]` can't be satisfied
- Categories share remaining width equally with `flex-1`

**Cards (Inner Level):**
```jsx
<div className="flex flex-wrap gap-4">
  <div style={{ width: '240px', flexShrink: 0 }}>
    {/* Card content */}
  </div>
</div>
```
- Browser automatically wraps when cards don't fit
- Fixed widths prevent cards from squishing

### 3. Conditional Rendering

Cards adjust their content based on size:

```jsx
// Small cards (180px) hide description
const showDescription = size !== 'small';

{showDescription && avatar.description && (
  <p className={`${descClass} text-gray-500 truncate mt-1`}>
    {avatar.description}
  </p>
)}
```

**Why This Works:**
- No complex calculations needed
- Browser handles all wrapping logic
- Natural, predictable behavior
- Easy to understand and maintain

## Real-World Examples

### Narrow Viewport (900px wide)
```
Width: 900px < min-width[400px] * 2

┌─────────────────────────────┐
│  Sports                     │
│  [180] [180] [180] [180]    │
│                             │
│  Travelling                 │
│  [180]                      │
└─────────────────────────────┘

Result: Categories stack, 4 cards fit per row
```

### Medium Viewport (1400px wide)
```
Width: 1400px >= min-width[400px] * 2

┌─────────────────────────────────────┐
│  Sports         │  Travelling       │
│  [240] [240]    │  [240]            │
│                 │                   │
└─────────────────────────────────────┘

Result: Categories side-by-side, each gets ~700px
```

### Wide Viewport (1920px wide)
```
Width: 1920px, cards = 300px (large)

┌─────────────────────────────────────┐
│  Sports         │  Travelling       │
│  [300] [300]    │  [300]            │
│  [300]          │                   │
└─────────────────────────────────────┘

Result: Larger cards, categories share width
```

## Flexbox Configuration

Simple flex-based layout with no complex calculations:

```jsx
// Outer: Categories
<div className="flex flex-wrap gap-8">
  
  // Each category
  <div className="flex-1 min-w-[400px]">
    
    // Inner: Cards
    <div className="flex flex-wrap gap-4">
      
      // Each card
      <div style={{ width: '240px', flexShrink: 0 }}>
        {/* Card content */}
      </div>
      
    </div>
  </div>
</div>
```

**Key Properties:**
- `flex flex-wrap` - Enables wrapping at both levels
- `flex-1` - Categories grow to fill available width
- `min-w-[400px]` - Prevents categories from being too narrow
- `flexShrink: 0` - Cards maintain their fixed width
- `gap-8` / `gap-4` - Consistent spacing (32px / 16px)

## Benefits

1. **Simple** - Pure flex, no complex calculations
2. **Natural** - Browser handles all wrapping logic
3. **Predictable** - Fixed card sizes (180px, 240px, 300px)
4. **Flexible** - Categories size based on content
5. **Responsive** - Wraps naturally at any viewport size
6. **Maintainable** - Easy to understand and modify
7. **Fast** - No layout recalculations needed
8. **Clean** - Minimal code, maximum effect

## Testing

Resize your browser and observe:

### Horizontal Resizing
- **< 900px**: Categories stack vertically, cards wrap within
- **900-1400px**: Categories still stack, cards = 180px (small)
- **≥ 1400px**: Categories appear side-by-side (flex-1 shares width)

### Card Size Breakpoints
- **< 1200px**: 180px cards, no descriptions
- **1200-1599px**: 240px cards, descriptions shown
- **≥ 1600px**: 300px cards, descriptions shown

### Natural Wrapping
1. Drag window wider → Categories appear side-by-side
2. Drag window narrower → Categories stack when < 400px each
3. Cards automatically wrap to new rows
4. No jumps, smooth transitions

**Try It:**
1. Start at 800px wide → See stacked categories, small cards
2. Drag to 1400px → Categories go side-by-side
3. Drag to 1600px → Cards get larger (300px)
4. Add more agents → Watch cards wrap naturally

## Future Enhancements

Possible improvements:
- Add grid density preference (compact/comfortable/spacious)
- Save user's preferred card size
- Add zoom controls
- Animate size transitions
- Add keyboard navigation with arrow keys
