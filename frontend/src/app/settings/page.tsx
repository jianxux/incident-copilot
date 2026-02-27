'use client';
import { useState } from 'react';
import { Save } from 'lucide-react';

interface IntegrationConfig {
  label: string;
  fields: { key: string; label: string; type: string; placeholder: string }[];
}

const integrations: IntegrationConfig[] = [
  {
    label: 'PagerDuty',
    fields: [
      { key: 'pagerduty_api_key', label: 'API Key', type: 'password', placeholder: 'Enter PagerDuty API key' },
      { key: 'pagerduty_service_id', label: 'Service ID', type: 'text', placeholder: 'P1234ABC' },
    ],
  },
  {
    label: 'Datadog',
    fields: [
      { key: 'datadog_api_key', label: 'API Key', type: 'password', placeholder: 'Enter Datadog API key' },
      { key: 'datadog_app_key', label: 'App Key', type: 'password', placeholder: 'Enter Datadog App key' },
    ],
  },
  {
    label: 'Slack',
    fields: [
      { key: 'slack_webhook_url', label: 'Webhook URL', type: 'url', placeholder: 'https://hooks.slack.com/services/...' },
      { key: 'slack_channel', label: 'Channel', type: 'text', placeholder: '#incidents' },
    ],
  },
  {
    label: 'GitHub',
    fields: [
      { key: 'github_token', label: 'Token', type: 'password', placeholder: 'ghp_...' },
      { key: 'github_org', label: 'Organization', type: 'text', placeholder: 'your-org' },
    ],
  },
];

export default function SettingsPage() {
  const [values, setValues] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="p-6 md:p-8 space-y-8 max-w-3xl">
      <h1 className="font-serif text-3xl">Settings</h1>

      {integrations.map((integration) => (
        <div key={integration.label} className="bg-white rounded-xl border border-cream-dark shadow-sm p-6">
          <h3 className="font-serif text-lg mb-4">{integration.label}</h3>
          <div className="space-y-4">
            {integration.fields.map((field) => (
              <div key={field.key}>
                <label className="block text-sm font-medium text-gray-700 mb-1">{field.label}</label>
                <input
                  type={field.type}
                  placeholder={field.placeholder}
                  value={values[field.key] || ''}
                  onChange={(e) => setValues({ ...values, [field.key]: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-coral/30 focus:border-coral"
                />
              </div>
            ))}
          </div>
        </div>
      ))}

      <button
        onClick={handleSave}
        className="inline-flex items-center gap-2 bg-coral hover:bg-coral-dark text-white px-6 py-2.5 rounded-lg font-medium transition-colors"
      >
        <Save size={16} /> {saved ? 'Saved!' : 'Save Settings'}
      </button>
    </div>
  );
}
