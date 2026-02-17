'use client';

import { useEffect, useMemo, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { useAppStore } from '@/lib/store';
import { integrationApi } from '@/lib/api';
import {
  Bell,
  Check,
  Key,
  Moon,
  Palette,
  Shield,
  Sun,
  User,
  Users,
  Webhook,
} from 'lucide-react';

export default function SettingsPage() {
  const { theme, setTheme, notificationsEnabled, setNotificationsEnabled, soundEnabled, setSoundEnabled } = useAppStore();
  const [activeSection, setActiveSection] = useState('profile');
  const [integrationStatus, setIntegrationStatus] = useState<Record<string, boolean>>({});
  const [loadingProvider, setLoadingProvider] = useState<string | null>(null);

  const integrations = useMemo(
    () => [
      { id: 'slack', name: 'Slack', logo: '💬', description: 'Post incident context directly to channels.' },
      { id: 'pagerduty', name: 'PagerDuty', logo: '🔔', description: 'Sync incidents and on-call context.' },
      { id: 'github', name: 'GitHub', logo: '🐙', description: 'Attach repo commits and deployment context.' },
      { id: 'gitlab', name: 'GitLab', logo: '🦊', description: 'Fetch merge request and pipeline context.' },
      { id: 'jira', name: 'Jira', logo: '📋', description: 'Create and update Jira incident tickets.' },
    ],
    []
  );

  const callbackMessage = useMemo(() => {
    if (typeof window === 'undefined') return null;
    const params = new URLSearchParams(window.location.search);
    const provider = params.get('oauth_provider');
    const result = params.get('oauth_result');
    const reason = params.get('oauth_reason');
    if (!provider || !result) return null;
    if (result === 'success') return `Connected ${provider} successfully.`;
    return `OAuth for ${provider} failed: ${reason ?? 'unknown_error'}.`;
  }, []);

  useEffect(() => {
    const loadStatuses = async () => {
      const next: Record<string, boolean> = {};
      await Promise.all(
        integrations.map(async (integration) => {
          try {
            const status = await integrationApi.oauthStatus(integration.id);
            next[integration.id] = status.connected;
          } catch {
            next[integration.id] = false;
          }
        })
      );
      setIntegrationStatus(next);
    };

    void loadStatuses();
  }, [integrations]);

  const handleDisconnect = async (provider: string) => {
    setLoadingProvider(provider);
    try {
      await integrationApi.oauthDisconnect(provider);
      setIntegrationStatus((prev) => ({ ...prev, [provider]: false }));
    } finally {
      setLoadingProvider(null);
    }
  };

  const sections = [
    { id: 'profile', label: 'Profile', icon: User },
    { id: 'notifications', label: 'Notifications', icon: Bell },
    { id: 'appearance', label: 'Appearance', icon: Palette },
    { id: 'security', label: 'Security', icon: Shield },
    { id: 'integrations', label: 'Integrations', icon: Webhook },
    { id: 'team', label: 'Team', icon: Users },
    { id: 'api', label: 'API Keys', icon: Key },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Settings</h1>
        <p className="text-muted-foreground">
          Manage your account and application preferences
        </p>
      </div>

      <div className="flex gap-6">
        {/* Sidebar */}
        <nav className="w-64 space-y-1">
          {sections.map((section) => (
            <button
              key={section.id}
              onClick={() => setActiveSection(section.id)}
              className={`w-full flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                activeSection === section.id
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              }`}
            >
              <section.icon className="h-4 w-4" />
              {section.label}
            </button>
          ))}
        </nav>

        {/* Content */}
        <div className="flex-1 space-y-6">
          {activeSection === 'profile' && (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>Profile Information</CardTitle>
                  <CardDescription>Update your personal details</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center gap-4">
                    <div className="h-20 w-20 rounded-full bg-primary flex items-center justify-center">
                      <User className="h-10 w-10 text-primary-foreground" />
                    </div>
                    <div>
                      <Button variant="outline" size="sm">Change avatar</Button>
                      <p className="mt-1 text-xs text-muted-foreground">JPG, PNG. Max 2MB</p>
                    </div>
                  </div>
                  <Separator />
                  <div className="grid gap-4 md:grid-cols-2">
                    <div>
                      <label className="text-sm font-medium">First name</label>
                      <Input className="mt-1" defaultValue="John" />
                    </div>
                    <div>
                      <label className="text-sm font-medium">Last name</label>
                      <Input className="mt-1" defaultValue="Doe" />
                    </div>
                    <div className="md:col-span-2">
                      <label className="text-sm font-medium">Email</label>
                      <Input className="mt-1" type="email" defaultValue="john@example.com" />
                    </div>
                    <div className="md:col-span-2">
                      <label className="text-sm font-medium">Phone</label>
                      <Input className="mt-1" type="tel" placeholder="+1 (555) 000-0000" />
                    </div>
                  </div>
                  <div className="flex justify-end">
                    <Button>Save changes</Button>
                  </div>
                </CardContent>
              </Card>
            </>
          )}

          {activeSection === 'notifications' && (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>Notification Preferences</CardTitle>
                  <CardDescription>Choose how you want to be notified</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <ToggleSetting
                    title="Push notifications"
                    description="Receive push notifications for new incidents"
                    enabled={notificationsEnabled}
                    onToggle={setNotificationsEnabled}
                  />
                  <Separator />
                  <ToggleSetting
                    title="Sound alerts"
                    description="Play sound when new incidents arrive"
                    enabled={soundEnabled}
                    onToggle={setSoundEnabled}
                  />
                  <Separator />
                  <ToggleSetting
                    title="Email notifications"
                    description="Receive email for critical incidents"
                    enabled={true}
                    onToggle={() => {}}
                  />
                  <Separator />
                  <div>
                    <h4 className="font-medium">Notify me about:</h4>
                    <div className="mt-3 space-y-2">
                      {[
                        { label: 'All incidents', checked: false },
                        { label: 'Critical and high severity only', checked: true },
                        { label: 'Incidents assigned to me', checked: true },
                        { label: 'Incidents in my services', checked: true },
                      ].map((option) => (
                        <label key={option.label} className="flex items-center gap-2">
                          <input type="checkbox" defaultChecked={option.checked} className="rounded" />
                          <span className="text-sm">{option.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                </CardContent>
              </Card>
            </>
          )}

          {activeSection === 'appearance' && (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>Appearance</CardTitle>
                  <CardDescription>Customize how the app looks</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div>
                    <h4 className="font-medium mb-3">Theme</h4>
                    <div className="flex gap-4">
                      <ThemeOption
                        label="Light"
                        icon={<Sun className="h-5 w-5" />}
                        selected={theme === 'light'}
                        onClick={() => setTheme('light')}
                      />
                      <ThemeOption
                        label="Dark"
                        icon={<Moon className="h-5 w-5" />}
                        selected={theme === 'dark'}
                        onClick={() => setTheme('dark')}
                      />
                      <ThemeOption
                        label="System"
                        icon={<Palette className="h-5 w-5" />}
                        selected={theme === 'system'}
                        onClick={() => setTheme('system')}
                      />
                    </div>
                  </div>
                  <Separator />
                  <div>
                    <h4 className="font-medium mb-3">Accent Color</h4>
                    <div className="flex gap-2">
                      {['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'].map((color) => (
                        <button
                          key={color}
                          className="h-8 w-8 rounded-full ring-2 ring-offset-2 ring-offset-background ring-transparent hover:ring-primary transition-all"
                          style={{ backgroundColor: color }}
                        />
                      ))}
                    </div>
                  </div>
                </CardContent>
              </Card>
            </>
          )}

          {activeSection === 'security' && (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>Security</CardTitle>
                  <CardDescription>Manage your security settings</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="font-medium">Password</h4>
                      <p className="text-sm text-muted-foreground">Last changed 30 days ago</p>
                    </div>
                    <Button variant="outline">Change password</Button>
                  </div>
                  <Separator />
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="font-medium">Two-factor authentication</h4>
                      <p className="text-sm text-muted-foreground">Add an extra layer of security</p>
                    </div>
                    <Badge variant="secondary">Not enabled</Badge>
                  </div>
                  <Separator />
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="font-medium">Active sessions</h4>
                      <p className="text-sm text-muted-foreground">Manage your active sessions</p>
                    </div>
                    <Button variant="outline">View sessions</Button>
                  </div>
                </CardContent>
              </Card>
            </>
          )}

          {activeSection === 'integrations' && (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>Integrations</CardTitle>
                  <CardDescription>Connect your tools and services with OAuth</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {callbackMessage && (
                    <div className="rounded-md border bg-muted/40 px-3 py-2 text-sm">
                      {callbackMessage}
                    </div>
                  )}
                  {integrations.map((integration) => {
                    const connected = integrationStatus[integration.id] === true;
                    return (
                    <div
                      key={integration.id}
                      className="flex items-center justify-between rounded-lg border p-4"
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-2xl">{integration.logo}</span>
                        <div>
                          <h4 className="font-medium">{integration.name}</h4>
                          <p className="text-sm text-muted-foreground">{integration.description}</p>
                          <p className="text-xs text-muted-foreground mt-1">
                            {connected ? 'Connected ✓' : 'Not connected'}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {!connected && (
                          <Button
                            onClick={async () => {
                              setLoadingProvider(integration.id);
                              try {
                                const { redirect_url } = await integrationApi.oauthConnect(integration.id);
                                window.location.href = redirect_url;
                              } catch (err: unknown) {
                                const msg = err instanceof Error ? err.message : 'Failed to start OAuth flow';
                                alert(msg);
                              } finally {
                                setLoadingProvider(null);
                              }
                            }}
                            disabled={loadingProvider === integration.id}
                          >
                            {loadingProvider === integration.id ? 'Connecting...' : 'Connect'}
                          </Button>
                        )}
                        {connected && (
                          <Button
                            variant="outline"
                            onClick={() => void handleDisconnect(integration.id)}
                            disabled={loadingProvider === integration.id}
                          >
                            Disconnect
                          </Button>
                        )}
                      </div>
                    </div>
                  )})}
                </CardContent>
              </Card>
            </>
          )}

          {activeSection === 'api' && (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>API Keys</CardTitle>
                  <CardDescription>Manage your API access tokens</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between rounded-lg border p-4">
                    <div>
                      <h4 className="font-medium">Production Key</h4>
                      <code className="text-sm text-muted-foreground">ic_prod_xxxx...xxxx</code>
                    </div>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm">Reveal</Button>
                      <Button variant="outline" size="sm">Regenerate</Button>
                    </div>
                  </div>
                  <div className="flex items-center justify-between rounded-lg border p-4">
                    <div>
                      <h4 className="font-medium">Development Key</h4>
                      <code className="text-sm text-muted-foreground">ic_dev_xxxx...xxxx</code>
                    </div>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm">Reveal</Button>
                      <Button variant="outline" size="sm">Regenerate</Button>
                    </div>
                  </div>
                  <Button>
                    <Key className="mr-2 h-4 w-4" />
                    Create new key
                  </Button>
                </CardContent>
              </Card>
            </>
          )}

          {activeSection === 'team' && (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>Team Members</CardTitle>
                  <CardDescription>Manage your team access</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {[
                    { name: 'John Doe', email: 'john@example.com', role: 'Admin' },
                    { name: 'Jane Smith', email: 'jane@example.com', role: 'Member' },
                    { name: 'Bob Wilson', email: 'bob@example.com', role: 'Member' },
                  ].map((member) => (
                    <div
                      key={member.email}
                      className="flex items-center justify-between rounded-lg border p-4"
                    >
                      <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-full bg-primary flex items-center justify-center">
                          <User className="h-5 w-5 text-primary-foreground" />
                        </div>
                        <div>
                          <h4 className="font-medium">{member.name}</h4>
                          <p className="text-sm text-muted-foreground">{member.email}</p>
                        </div>
                      </div>
                      <Badge>{member.role}</Badge>
                    </div>
                  ))}
                  <Button>
                    <Users className="mr-2 h-4 w-4" />
                    Invite team member
                  </Button>
                </CardContent>
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function ToggleSetting({
  title,
  description,
  enabled,
  onToggle,
}: {
  title: string;
  description: string;
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <h4 className="font-medium">{title}</h4>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <button
        onClick={() => onToggle(!enabled)}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
          enabled ? 'bg-primary' : 'bg-muted'
        }`}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
            enabled ? 'translate-x-6' : 'translate-x-1'
          }`}
        />
      </button>
    </div>
  );
}

function ThemeOption({
  label,
  icon,
  selected,
  onClick,
}: {
  label: string;
  icon: React.ReactNode;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex flex-col items-center gap-2 rounded-lg border p-4 transition-colors ${
        selected ? 'border-primary bg-primary/10' : 'hover:bg-accent'
      }`}
    >
      {icon}
      <span className="text-sm font-medium">{label}</span>
      {selected && <Check className="h-4 w-4 text-primary" />}
    </button>
  );
}
