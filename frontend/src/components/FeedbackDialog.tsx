import { useState } from 'react';
import { apiFetch } from '@/lib/api';
import { MessageSquarePlus, X, Bug, Lightbulb, AlertCircle, Send } from 'lucide-react';
import { toast } from 'sonner';

const FEEDBACK_TYPES = [
  { id: 'bug', label: 'Bug Report', icon: Bug, color: 'text-red-400 bg-red-500/10 border-red-500/20' },
  { id: 'error', label: 'Error Log', icon: AlertCircle, color: 'text-amber-400 bg-amber-500/10 border-amber-500/20' },
  { id: 'suggestion', label: 'Suggestion', icon: Lightbulb, color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' },
  { id: 'complaint', label: 'Complaint', icon: MessageSquarePlus, color: 'text-blue-400 bg-blue-500/10 border-blue-500/20' },
] as const;

export function FeedbackDialog() {
  const [open, setOpen] = useState(false);
  const [type, setType] = useState<string>('bug');
  const [subject, setSubject] = useState('');
  const [description, setDescription] = useState('');
  const [errorLog, setErrorLog] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const reset = () => {
    setType('bug');
    setSubject('');
    setDescription('');
    setErrorLog('');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!subject.trim() || !description.trim()) {
      toast.error('Subject and description are required.');
      return;
    }
    setSubmitting(true);
    try {
      const res = await apiFetch('/api/feedback', {
        method: 'POST',
        body: JSON.stringify({ type, subject, description, error_log: errorLog }),
      });
      toast.success('Feedback submitted — thank you!');
      if (res.email_sent) {
        toast.info('A copy was emailed to the development team.');
      } else if (res.rate_limited) {
        toast.warning('Email rate limit reached (2/hr). Your feedback was saved but not emailed.');
      }
      reset();
      setOpen(false);
    } catch (err: any) {
      toast.error(err.message || 'Failed to submit feedback.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-border bg-secondary/50 text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
        data-testid="feedback-trigger-btn"
        title="Send Feedback"
      >
        <MessageSquarePlus size={13} />
        <span className="hidden sm:inline">Feedback</span>
      </button>

      {open && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 backdrop-blur-sm" data-testid="feedback-modal-overlay">
          <div className="glass border border-border rounded-2xl w-full max-w-md max-h-[90vh] flex flex-col shadow-2xl mx-4" data-testid="feedback-modal">
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
              <h2 className="text-sm font-semibold text-foreground">Send Feedback</h2>
              <button onClick={() => setOpen(false)} className="text-muted-foreground hover:text-foreground transition-colors" data-testid="feedback-close-btn">
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="flex-1 overflow-auto px-5 py-4 space-y-4">
              {/* Type selector */}
              <div>
                <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium block mb-2">Type</label>
                <div className="grid grid-cols-2 gap-2" data-testid="feedback-type-selector">
                  {FEEDBACK_TYPES.map((ft) => {
                    const Icon = ft.icon;
                    const active = type === ft.id;
                    return (
                      <button
                        key={ft.id}
                        type="button"
                        onClick={() => setType(ft.id)}
                        className={`flex items-center gap-2 px-3 py-2 text-xs font-medium rounded-lg border transition-all ${
                          active ? ft.color + ' ring-1 ring-current' : 'border-border text-muted-foreground hover:text-foreground hover:bg-secondary/50'
                        }`}
                        data-testid={`feedback-type-${ft.id}`}
                      >
                        <Icon size={13} /> {ft.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Subject */}
              <div>
                <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium block mb-1">Subject *</label>
                <input
                  data-testid="feedback-subject"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder="Brief summary of the issue or idea"
                  className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1 focus:ring-offset-background text-foreground placeholder:text-muted-foreground/30"
                />
              </div>

              {/* Description */}
              <div>
                <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium block mb-1">Description *</label>
                <textarea
                  data-testid="feedback-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Describe what happened, steps to reproduce, or your suggestion..."
                  rows={4}
                  className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1 focus:ring-offset-background text-foreground placeholder:text-muted-foreground/30 resize-none"
                />
              </div>

              {/* Error Log (optional) */}
              {(type === 'bug' || type === 'error') && (
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium block mb-1">Error Log (optional)</label>
                  <textarea
                    data-testid="feedback-error-log"
                    value={errorLog}
                    onChange={(e) => setErrorLog(e.target.value)}
                    placeholder="Paste any error messages or log output here..."
                    rows={3}
                    className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-[11px] font-mono focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1 focus:ring-offset-background text-foreground placeholder:text-muted-foreground/30 resize-none"
                  />
                </div>
              )}

              <p className="text-[10px] text-muted-foreground/50">
                Your registered name, email, and app version will be included automatically.
              </p>

              <button
                type="submit"
                disabled={submitting}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg font-semibold text-sm bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg shadow-primary/20"
                data-testid="feedback-submit-btn"
              >
                <Send size={13} />
                {submitting ? 'Sending...' : 'Submit Feedback'}
              </button>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
