# Dawn UI Components - Developer Reference

## Using Toast Notifications

The toast system is globally available via the `useNotification` hook:

```tsx
import { useNotification } from '@/context/notification-context';

export function MyComponent() {
  const { addToast } = useNotification();

  const handleSuccess = () => {
    addToast('success', 'Operation successful!', 'Your data has been saved.');
  };

  const handleError = () => {
    addToast('error', 'Something went wrong', 'Please try again later.');
  };

  return (
    <button onClick={handleSuccess}>
      Show Success Toast
    </button>
  );
}
```

### Toast Types
- `success` - Green, auto-dismisses after 4s
- `error` - Red, auto-dismisses after 5s
- `warning` - Amber, auto-dismisses after 4s
- `info` - Blue, auto-dismisses after 4s

## Using Onboarding Modal

```tsx
import { useNotification } from '@/context/notification-context';

export function TourButton() {
  const { showOnboarding } = useNotification();

  return (
    <button onClick={() => showOnboarding(true)}>
      Show Demo Tour
    </button>
  );
}
```

### Onboarding Features
- 4 steps: Upload → Preview → Agents → Chat
- Step-by-step progress indicators
- Skip button to dismiss
- Demo mode hints

## Glass Panel Styling

Use the `glass-panel` class for consistent styled containers:

```tsx
// Large panels with heavy blur
<div className="glass-panel rounded-3xl p-6">
  Content here
</div>

// Small cards with light blur
<div className="glass-panel-sm rounded-2xl p-4">
  Card content
</div>
```

## Gradient Buttons

Primary action buttons:
```tsx
<button className="bg-gradient-to-r from-amber-400 via-pink-500 to-sky-500 px-4 py-2 text-white font-semibold rounded-full shadow-aurora hover:shadow-lg">
  Primary Action
</button>
```

Secondary buttons:
```tsx
<button className="border border-white/10 hover:bg-white/10 px-4 py-2 text-slate-200 rounded-full transition-colors">
  Secondary Action
</button>
```

## Activity Feed

```tsx
import ActivityFeed, { type ActivityItem } from '@/components/ui/ActivityFeed';

export function MyActivityPanel() {
  const [activities, setActivities] = useState<ActivityItem[]>([]);

  const addActivity = (type: ActivityItem['type'], message: string, detail?: string) => {
    const newActivity: ActivityItem = {
      id: `${Date.now()}`,
      type,
      message,
      detail,
      timestamp: new Date()
    };
    setActivities(prev => [newActivity, ...prev.slice(0, 49)]);
  };

  return <ActivityFeed activities={activities} maxItems={10} />;
}
```

### Activity Types
- `upload` - File upload
- `profile` - Data profiling
- `index` - Vectorization
- `agent` - Agent run
- `chat` - Chat message
- `success` - Success message
- `warning` - Warning message
- `info` - Info message

## Message Bubbles in Chat

```tsx
{/* User message (amber) */}
<div className="flex justify-end">
  <div className="bg-amber-500/20 border border-amber-500/30 text-slate-100 max-w-xs px-4 py-2 rounded-2xl">
    User message here
  </div>
</div>

{/* Assistant message (sky) */}
<div className="flex justify-start">
  <div className="bg-sky-500/10 border border-sky-500/20 text-slate-100 max-w-xs px-4 py-2 rounded-2xl">
    Assistant message here
  </div>
</div>
```

## Status Indicators

Success state:
```tsx
<div className="flex items-center gap-2 text-emerald-400">
  <CheckCircleIcon className="h-4 w-4" />
  <span>Operation successful</span>
</div>
```

Warning state:
```tsx
<div className="flex items-center gap-2 text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-lg p-2">
  <ExclamationTriangleIcon className="h-4 w-4" />
  <span>Warning message</span>
</div>
```

Error state:
```tsx
<div className="flex items-center gap-2 text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-lg p-2">
  <XMarkIcon className="h-4 w-4" />
  <span>Error message</span>
</div>
```

## Form Inputs with Focus States

```tsx
<input
  type="text"
  className="w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-white focus:border-sky-400 focus:ring-2 focus:ring-sky-400/20"
  placeholder="Enter text..."
/>

<select
  className="w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm focus:border-sky-400 focus:ring-2 focus:ring-sky-400/20"
>
  <option>Select...</option>
</select>

<textarea
  className="w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-white focus:border-sky-400 focus:ring-2 focus:ring-sky-400/20 resize-none"
  rows={3}
/>
```

## Loading & Status States

Spinner animation:
```tsx
<div className="animate-spin-slow">
  <SparklesIcon className="h-5 w-5" />
</div>
```

Typing indicator:
```tsx
<div className="flex gap-1">
  <div className="w-2 h-2 rounded-full bg-slate-400 animate-pulse" />
  <div className="w-2 h-2 rounded-full bg-slate-400 animate-pulse" style={{ animationDelay: '0.1s' }} />
  <div className="w-2 h-2 rounded-full bg-slate-400 animate-pulse" style={{ animationDelay: '0.2s' }} />
</div>
```

Skeleton loader:
```tsx
<div className="animate-pulse space-y-3">
  <div className="h-4 bg-slate-700/30 rounded w-3/4" />
  <div className="h-4 bg-slate-700/30 rounded w-1/2" />
  <div className="h-20 bg-slate-700/30 rounded" />
</div>
```

## Dashboard Header Usage

```tsx
import DashboardHeader from '@/components/layout/DashboardHeader';

export function MainDashboard() {
  return (
    <DashboardHeader
      preview={preview}
      profile={profile}
      agentResult={agentResult}
      onRefresh={() => console.log('refresh')}
      isLoading={loading}
    />
  );
}
```

## Color Variables (Tailwind)

Access via `text-*`, `bg-*`, `border-*` classes:
- `dawn-accent` → Amber
- `dawn-accentSoft` → Pink
- `dawn-aurora` → Sky blue
- `dawn-auroraSoft` → Indigo

## Best Practices

1. **Always use `glass-panel`** for major card containers
2. **Use gradient buttons** for primary CTAs
3. **Show toasts** for all async operations
4. **Use Activity Feed** to track background processes
5. **Leverage animations** but don't overuse them
6. **Maintain color meaning**: Green=success, Red=error, Amber=warning
7. **Use icons** consistently with text for better recognition
8. **Test responsive** design on mobile/tablet
9. **Ensure focus states** are visible for accessibility
10. **Keep cognitive load** low with collapsible sections

## Testing

When testing new components:
1. Test focus states (Tab key)
2. Test hover states
3. Test loading/error states
4. Test mobile responsive
5. Test color contrast with WCAG checker
6. Test animation performance
7. Test with screen reader
8. Test keyboard navigation only
