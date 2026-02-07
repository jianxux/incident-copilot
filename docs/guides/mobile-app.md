# Mobile App Guide

This guide covers setting up and using the Incident Copilot mobile app for iOS and Android, enabling on-the-go incident management.

## Overview

The mobile app enables:
- **Receive alerts** - Push notifications for incidents
- **Acknowledge & respond** - Quick actions without a laptop
- **View incidents** - Full incident details on mobile
- **On-call management** - Manage schedules and overrides
- **Offline access** - View recent incidents without connectivity

---

## Installation

### iOS

1. Open the App Store on your iPhone or iPad
2. Search for "Incident Copilot"
3. Tap **Get** to download
4. Open the app after installation

**Requirements:**
- iOS 14.0 or later
- iPhone 8 or newer recommended
- iPad supported

### Android

1. Open Google Play Store
2. Search for "Incident Copilot"
3. Tap **Install**
4. Open the app after installation

**Requirements:**
- Android 10 or later
- 4GB RAM recommended

<!-- Diagram: App Store Screenshots -->
<!-- Shows app icon and download buttons for iOS and Android -->

---

## Step 1: Initial Setup

### Sign In

1. Open the Incident Copilot app
2. Choose your sign-in method:
   - **SSO** - Tap "Sign in with SSO" and enter your company domain
   - **Email** - Enter your email and password
   - **Magic Link** - Enter email to receive a login link

```
┌─────────────────────────────────┐
│      Incident Copilot           │
│                                 │
│  ┌─────────────────────────┐    │
│  │  Sign in with SSO       │    │
│  └─────────────────────────┘    │
│                                 │
│  ┌─────────────────────────┐    │
│  │  Sign in with Email     │    │
│  └─────────────────────────┘    │
│                                 │
│  ┌─────────────────────────┐    │
│  │  Magic Link             │    │
│  └─────────────────────────┘    │
│                                 │
└─────────────────────────────────┘
```

### Configure Push Notifications

After signing in, enable push notifications:

1. When prompted, tap **Allow** for notifications
2. If you dismissed the prompt, go to:
   - **iOS**: Settings → Incident Copilot → Notifications → Enable
   - **Android**: Settings → Apps → Incident Copilot → Notifications → Enable

### Notification Preferences

Customize which notifications you receive:

```
Settings → Notifications
┌─────────────────────────────────┐
│  Notification Settings          │
├─────────────────────────────────┤
│  🔔 Critical Incidents    [ON]  │
│  🔔 High Priority         [ON]  │
│  🔔 Medium Priority       [OFF] │
│  🔔 Low Priority          [OFF] │
├─────────────────────────────────┤
│  🔔 Assigned to Me        [ON]  │
│  🔔 Mentioned in Comment  [ON]  │
│  🔔 SLA Warnings          [ON]  │
│  🔔 Escalations           [ON]  │
├─────────────────────────────────┤
│  🔕 Do Not Disturb              │
│     Schedule: 10pm - 7am   [ON] │
└─────────────────────────────────┘
```

---

## Step 2: Core Features

### Home Dashboard

The home screen shows:
- Active incidents count
- Your assigned incidents
- On-call status
- Quick action buttons

<!-- Diagram: Home Dashboard Layout -->
<!-- Shows metric cards, incident list preview, and action buttons -->

### Incident List

View and filter incidents:

```
┌─────────────────────────────────┐
│  🔍 Search...            🔽     │
├─────────────────────────────────┤
│  Filters: Open, Assigned to me  │
├─────────────────────────────────┤
│  🔴 INC-1234                    │
│  Payment gateway timeout        │
│  Critical • 15 min ago          │
├─────────────────────────────────┤
│  🟠 INC-1233                    │
│  High latency on API            │
│  High • 1 hour ago              │
├─────────────────────────────────┤
│  🟡 INC-1232                    │
│  Slow dashboard loading         │
│  Medium • 3 hours ago           │
└─────────────────────────────────┘
```

**Filter Options:**
- Status: Open, Acknowledged, Resolved, All
- Severity: Critical, High, Medium, Low
- Assignment: Assigned to me, My team, All
- Time: Last 24h, 7 days, 30 days

### Incident Detail View

Tap an incident to see full details:

```
┌─────────────────────────────────┐
│  ← INC-1234            ⋮       │
├─────────────────────────────────┤
│  Payment gateway timeout        │
│                                 │
│  🔴 Critical   ⏱ 15 min        │
│  👤 Alice      🏷 payments      │
├─────────────────────────────────┤
│  Description                    │
│  Customers unable to complete   │
│  checkout. 503 errors from      │
│  payment service...             │
├─────────────────────────────────┤
│  Timeline                       │
│  • 15:30 Incident created       │
│  • 15:32 Alice assigned         │
│  • 15:35 Alice commented        │
├─────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐       │
│  │   ACK   │  │ RESOLVE │       │
│  └─────────┘  └─────────┘       │
└─────────────────────────────────┘
```

### Quick Actions

Perform actions directly from notifications:

| Action | Description |
|--------|-------------|
| **Acknowledge** | Mark that you're responding |
| **Snooze** | Delay notification (5/15/30 min) |
| **Assign to Me** | Take ownership |
| **View** | Open incident details |
| **Call** | Start conference bridge |

**From Lock Screen (iOS):**
1. Long-press the notification
2. Select an action
3. Authenticate if required (Face ID/Touch ID)

---

## Step 3: Responding to Incidents

### Acknowledge an Incident

1. From notification: Tap **Acknowledge** in the action buttons
2. From incident detail: Tap the **ACK** button
3. Add optional acknowledgment note

### Add Comments

```
┌─────────────────────────────────┐
│  Add Comment                    │
├─────────────────────────────────┤
│  ┌─────────────────────────┐    │
│  │ Investigating database  │    │
│  │ connections. Seeing     │    │
│  │ connection pool         │    │
│  │ exhaustion...           │    │
│  └─────────────────────────┘    │
│                                 │
│  📎 Attach  @Mention  🎤 Voice  │
│                                 │
│  [      Post Comment      ]     │
└─────────────────────────────────┘
```

**Features:**
- **@Mentions**: Tag team members
- **Attachments**: Add screenshots from camera/gallery
- **Voice Notes**: Record audio updates
- **Templates**: Use saved response templates

### Update Status

Change incident status:

1. Open incident detail
2. Tap current status badge
3. Select new status:
   - Investigating
   - Identified
   - Monitoring
   - Resolved

### Change Severity

Escalate or de-escalate:

1. Open incident detail
2. Tap severity badge
3. Select new severity level
4. Add reason for change (required for escalation)

---

## Step 4: On-Call Management

### View On-Call Schedule

```
On-Call → Schedule
┌─────────────────────────────────┐
│  This Week                      │
├─────────────────────────────────┤
│  Mon 9am - Tue 9am              │
│  👤 Alice (Primary)             │
│  👤 Bob (Secondary)             │
├─────────────────────────────────┤
│  Tue 9am - Wed 9am              │
│  👤 Carol (Primary)             │
│  👤 Dave (Secondary)            │
├─────────────────────────────────┤
│  ⚡ You're on-call now          │
│  Until: Tomorrow 9:00 AM        │
└─────────────────────────────────┘
```

### Create Schedule Override

Going on vacation? Create an override:

1. Go to **On-Call** → **My Schedule**
2. Tap **+ Override**
3. Select:
   - Start date/time
   - End date/time
   - Coverage (who's covering for you)
4. Add reason (optional)
5. Tap **Create Override**

### Swap Shifts

Request a shift swap:

1. Go to **On-Call** → **My Schedule**
2. Tap the shift you want to swap
3. Tap **Request Swap**
4. Select team members to request
5. They'll receive a notification to accept/decline

---

## Step 5: Offline Mode

### Available Offline

When you lose connectivity:
- View recently accessed incidents
- View cached on-call schedule
- Draft comments (queued for sync)
- Receive cached notifications

### Sync Behavior

```
┌─────────────────────────────────┐
│  ⚠️ Offline Mode                │
│                                 │
│  Viewing cached data from       │
│  15 minutes ago.                │
│                                 │
│  2 actions pending sync:        │
│  • Comment on INC-1234          │
│  • Status update on INC-1233    │
│                                 │
│  [    Retry Connection    ]     │
└─────────────────────────────────┘
```

### Configure Offline Cache

```yaml
Settings → Offline
┌─────────────────────────────────┐
│  Offline Settings               │
├─────────────────────────────────┤
│  Cache Size: 50 MB       [📊]   │
│  Auto-sync: Every 5 min  [ON]   │
│  Cache incidents: 7 days [ON]   │
│  Download attachments    [OFF]  │
└─────────────────────────────────┘
```

---

## Step 6: Widgets and Shortcuts

### iOS Widgets

Add widgets to your home screen:

1. Long-press home screen → tap **+**
2. Search "Incident Copilot"
3. Choose widget size:

| Widget | Size | Shows |
|--------|------|-------|
| Small | 2x2 | Active incident count |
| Medium | 4x2 | Top 3 active incidents |
| Large | 4x4 | Incidents + on-call status |

### Apple Watch

Basic support for Apple Watch:
- Receive notifications
- Quick acknowledge
- View incident count

### Android Widgets

Add widgets from app drawer:
- **Quick Status**: Active incidents count
- **Incident List**: Scrollable incident list
- **On-Call**: Current on-call status

### Siri Shortcuts (iOS)

Set up voice commands:

1. Open Shortcuts app
2. Tap **+** → **Add Action**
3. Search "Incident Copilot"
4. Available shortcuts:
   - "Show active incidents"
   - "Am I on call?"
   - "Acknowledge latest incident"

Example: "Hey Siri, am I on call?"

---

## Step 7: Security Settings

### Biometric Authentication

Enable Face ID/Touch ID:

```
Settings → Security
┌─────────────────────────────────┐
│  Security Settings              │
├─────────────────────────────────┤
│  Face ID / Touch ID      [ON]   │
│  Require on app open     [ON]   │
│  Require for actions     [ON]   │
├─────────────────────────────────┤
│  Auto-lock after: 5 min         │
│  Show preview in notif.  [OFF]  │
└─────────────────────────────────┘
```

### Session Management

```
Settings → Security → Sessions
┌─────────────────────────────────┐
│  Active Sessions                │
├─────────────────────────────────┤
│  📱 iPhone 14 Pro (Current)     │
│  Last active: Now               │
│  Location: San Francisco        │
├─────────────────────────────────┤
│  📱 iPad Pro                    │
│  Last active: 2 hours ago       │
│  Location: San Francisco        │
├─────────────────────────────────┤
│  [   Sign Out All Others   ]    │
└─────────────────────────────────┘
```

### Enterprise MDM

For managed devices:
- App configuration via MDM
- Automatic SSO configuration
- Remote wipe capability
- Compliance enforcement

---

## Best Practices

1. **Enable critical notifications** - Never miss a P1/P2
2. **Use Do Not Disturb wisely** - Set up override for critical
3. **Pre-cache before travel** - Sync before going offline
4. **Use quick actions** - Respond faster from lock screen
5. **Enable biometrics** - Security without friction
6. **Update regularly** - Keep app updated for latest features

---

## Common Pitfalls

| Issue | Cause | Solution |
|-------|-------|----------|
| No notifications | Permissions disabled | Check system notification settings |
| Delayed notifications | Battery optimization | Disable battery optimization for app |
| Can't acknowledge | Session expired | Re-authenticate in app |
| Sync failures | Poor connectivity | Check network, retry manually |
| Widget not updating | Background refresh disabled | Enable background app refresh |

---

## Troubleshooting

### Reset Push Notifications

```
Settings → Debug → Reset Notifications
```

This will:
1. Unregister current push token
2. Request new push token
3. Re-register with server

### Clear Cache

```
Settings → Storage → Clear Cache
```

### Report a Bug

```
Settings → Help → Report Bug
```

Includes:
- Device info
- App version
- Recent logs (no sensitive data)

---

## Next Steps

- [Real-Time Updates](./realtime-updates.md) - Understand push notification system
- [Escalation Policies](./escalation-policies.md) - Configure mobile escalations
- [Enterprise Setup](./enterprise-setup.md) - MDM and enterprise configuration
