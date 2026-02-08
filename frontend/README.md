# Incident Copilot Dashboard

A modern, responsive frontend for the Incident Copilot platform built with Next.js 14, React, and Tailwind CSS.

## Features

- 📊 **Real-time Dashboard** - Live incident tracking with auto-refresh
- 🎨 **Dark/Light Theme** - Automatic theme detection with manual toggle
- 📱 **Responsive Design** - Works on desktop, tablet, and mobile
- ⚡ **Fast Performance** - Server-side rendering with optimized client hydration
- 🔍 **Advanced Filtering** - Filter by severity, status, service, and more
- 📈 **Analytics** - Charts, trends, and team performance metrics
- 🔔 **Notifications** - Real-time alerts with sound support
- 🔐 **Authentication** - OAuth with GitHub/Google, SSO/SAML support

## Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Components**: Radix UI primitives with shadcn/ui styling
- **State**: Zustand for global state, React Query for server state
- **Charts**: Recharts
- **Animations**: Framer Motion
- **Icons**: Lucide React

## Getting Started

### Prerequisites

- Node.js 18+
- npm or pnpm

### Installation

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Start production server
npm run start
```

### Environment Variables

Create a `.env.local` file:

```env
# Backend API URL
BACKEND_URL=http://localhost:8000

# Optional: Analytics
NEXT_PUBLIC_POSTHOG_KEY=
NEXT_PUBLIC_POSTHOG_HOST=
```

## Project Structure

```
frontend/
├── src/
│   ├── app/                    # Next.js App Router pages
│   │   ├── (auth)/            # Auth pages (login, signup)
│   │   ├── (dashboard)/       # Dashboard pages
│   │   │   ├── dashboard/     # Main dashboard
│   │   │   ├── incidents/     # Incident list & detail
│   │   │   ├── analytics/     # Analytics & metrics
│   │   │   └── settings/      # User settings
│   │   ├── layout.tsx         # Root layout
│   │   └── providers.tsx      # Client providers
│   ├── components/
│   │   ├── layout/            # Layout components
│   │   └── ui/                # UI primitives (shadcn/ui)
│   ├── hooks/                 # Custom React hooks
│   ├── lib/                   # Utilities & API client
│   └── types/                 # TypeScript types
├── public/                    # Static assets
├── tailwind.config.js         # Tailwind configuration
└── package.json
```

## Pages

| Route | Description |
|-------|-------------|
| `/dashboard` | Main dashboard with stats & active incidents |
| `/incidents` | Incident list with filtering |
| `/incidents/[id]` | Incident detail with timeline & context |
| `/analytics` | Charts, trends, and team metrics |
| `/insights` | AI-generated patterns and recommendations |
| `/settings` | User preferences and integrations |
| `/login` | Authentication page |

## API Integration

The frontend proxies API requests to the backend:

```typescript
// src/lib/api.ts
const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
});
```

API calls are automatically proxied via `next.config.js`:

```javascript
async rewrites() {
  return [
    {
      source: '/api/:path*',
      destination: `${process.env.BACKEND_URL}/api/:path*`,
    },
  ];
}
```

## Customization

### Theming

Edit `tailwind.config.js` to customize colors:

```javascript
theme: {
  extend: {
    colors: {
      primary: { /* your colors */ },
      severity: {
        critical: '#dc2626',
        high: '#ea580c',
        // ...
      },
    },
  },
}
```

### Components

UI components are based on shadcn/ui. To add more:

```bash
npx shadcn-ui@latest add button
```

## Development

```bash
# Run development server
npm run dev

# Type checking
npm run type-check

# Linting
npm run lint

# Build
npm run build
```

## Deployment

### Docker

```dockerfile
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:18-alpine
WORKDIR /app
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

ENV PORT=3000
EXPOSE 3000
CMD ["node", "server.js"]
```

### Vercel

```bash
npx vercel
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## License

MIT
