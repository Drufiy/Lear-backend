import { MessageSquare, Mail, Bell, ShieldAlert } from 'lucide-react';

export default function Notifications() {
  const notifiers = [
    { id: 'slack', name: 'Slack', icon: MessageSquare, color: 'text-purple-400', status: 'connected' },
    { id: 'discord', name: 'Discord', icon: MessageSquare, color: 'text-indigo-400', status: 'disconnected' },
    { id: 'whatsapp', name: 'WhatsApp', icon: MessageSquare, color: 'text-green-500', status: 'disconnected' },
    { id: 'email', name: 'Email', icon: Mail, color: 'text-red-400', status: 'disconnected' },
    { id: 'pagerduty', name: 'PagerDuty', icon: ShieldAlert, color: 'text-green-400', status: 'disconnected' },
  ];

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Notifications</h1>
        <p className="text-gray-400">Configure where Prash sends alerts, reports, and request for approvals.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="space-y-4">
          <h2 className="text-xl font-semibold text-white mb-4">Channels</h2>
          {notifiers.map((item) => {
            const Icon = item.icon;
            return (
              <div key={item.id} className="flex items-center justify-between p-5 rounded-2xl border border-gray-800 bg-gray-900/30">
                <div className="flex items-center gap-4">
                  <div className={`p-3 rounded-xl bg-gray-800/80 ${item.color}`}>
                    <Icon size={24} />
                  </div>
                  <div>
                    <h3 className="text-lg font-medium text-white">{item.name}</h3>
                    <p className="text-sm text-gray-500">{item.status === 'connected' ? 'Active' : 'Not configured'}</p>
                  </div>
                </div>
                <button className={`px-5 py-2 rounded-lg font-medium text-sm transition-colors ${
                  item.status === 'connected'
                    ? 'bg-gray-800 text-white hover:bg-gray-700'
                    : 'bg-accent/10 text-accent hover:bg-accent hover:text-background'
                }`}>
                  {item.status === 'connected' ? 'Manage' : 'Connect'}
                </button>
              </div>
            );
          })}
        </div>

        <div>
          <h2 className="text-xl font-semibold text-white mb-4">Routing Rules</h2>
          <div className="p-6 rounded-2xl border border-gray-800 bg-gray-900/30 flex flex-col items-center text-center justify-center min-h-[300px]">
            <Bell size={48} className="text-gray-700 mb-4" />
            <h3 className="text-lg font-medium text-white mb-2">No routing rules</h3>
            <p className="text-gray-500 mb-6 max-w-sm">
              Create rules to send specific alerts (e.g., P0 production incidents) to specific channels like PagerDuty.
            </p>
            <button className="px-5 py-2 border border-gray-700 hover:border-gray-500 rounded-lg text-white font-medium transition-colors">
              Create Rule
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
