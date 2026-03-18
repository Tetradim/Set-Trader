import { useState, useEffect } from 'react';
import { apiFetch } from '@/lib/api';
import { Shield, ChevronDown, ChevronUp } from 'lucide-react';

const AGREEMENT_VERSION = '1.0';

const AGREEMENT_TEXT = `SIGNAL FORGE LABORATORY
SENTINEL PULSE — BETA TESTER LICENSE AGREEMENT
Version ${AGREEMENT_VERSION}

IMPORTANT — READ CAREFULLY BEFORE USING THIS SOFTWARE.

This Beta Tester License Agreement ("Agreement") is a legally binding contract between you ("Tester," "you," or "your") and Signal Forge Laboratory ("Company," "we," "us," or "our") governing your access to and use of the Sentinel Pulse software application, including all related components, documentation, updates, and derivative works (collectively, the "Software").

By clicking "I Accept," entering your registration information, or otherwise accessing or using the Software, you acknowledge that you have read, understood, and agree to be bound by all terms and conditions of this Agreement. If you do not agree, you must immediately cease all use of the Software and delete all copies in your possession.

1. GRANT OF LIMITED LICENSE

1.1 Subject to the terms herein, the Company grants you a limited, non-exclusive, non-transferable, non-sublicensable, revocable license to install and use the Software solely for personal, non-commercial evaluation and testing purposes during the Beta Period.

1.2 This license does not convey any right of ownership in or to the Software. All rights not expressly granted are reserved by the Company.

2. RESTRICTIONS ON USE

You agree that you shall NOT, directly or indirectly:

(a) Reverse engineer, decompile, disassemble, decrypt, or otherwise attempt to derive the source code, algorithms, data structures, or underlying ideas of the Software or any portion thereof;

(b) Modify, adapt, translate, create derivative works based upon, or otherwise alter the Software;

(c) Copy, reproduce, distribute, publish, display, perform, transmit, broadcast, or otherwise disseminate the Software or any portion thereof to any third party;

(d) Sell, rent, lease, lend, sublicense, assign, transfer, or otherwise dispose of the Software or any rights therein;

(e) Remove, alter, obscure, or deface any proprietary notices, labels, marks, or branding on or within the Software;

(f) Use the Software for any commercial purpose, including but not limited to operating a business, providing services to third parties, or generating revenue;

(g) Use the Software in any manner that violates applicable local, state, national, or international law or regulation;

(h) Circumvent, disable, or interfere with any security, authentication, digital rights management, or copy protection features of the Software;

(i) Use the Software to develop a competing product or service;

(j) Share, post, upload, or otherwise make available any screenshots, recordings, data, outputs, or other materials derived from the Software without the Company's prior written consent;

(k) Allow any third party to access or use the Software, whether through your account, device, network, or any other means.

3. INTELLECTUAL PROPERTY

3.1 The Software and all copies thereof are proprietary to the Company and title thereto remains in the Company. All applicable rights to copyrights, trademarks, trade secrets, trade names, patents, and other intellectual property rights in the Software are and shall remain the exclusive property of the Company.

3.2 The Software is protected by copyright laws of the United States and international treaty provisions. You acknowledge that the Software contains valuable trade secrets and confidential information belonging to the Company.

3.3 Any feedback, suggestions, ideas, bug reports, or other communications you provide regarding the Software ("Feedback") shall become the sole and exclusive property of the Company. You hereby assign to the Company all right, title, and interest in and to such Feedback without any obligation of compensation or attribution.

4. CONFIDENTIALITY

4.1 You acknowledge that the Software, its features, functionality, performance characteristics, and all related documentation constitute confidential and proprietary information of the Company ("Confidential Information").

4.2 You agree to maintain the Confidential Information in strict confidence and to not disclose, publish, or otherwise reveal any Confidential Information to any third party without the prior written consent of the Company.

4.3 This obligation of confidentiality shall survive the termination or expiration of this Agreement.

5. DATA COLLECTION & PRIVACY

5.1 The Company may collect registration information, usage data, performance metrics, error reports, and other diagnostic data to improve the Software. By accepting this Agreement, you consent to such collection.

5.2 Personal information collected during registration (name, partial SSN, address, email) will be stored securely and used solely for identification, legal compliance, and communication regarding the Software.

5.3 The Company will not sell your personal information to third parties.

6. DISCLAIMER OF WARRANTIES

6.1 THE SOFTWARE IS PROVIDED "AS IS" AND "AS AVAILABLE" WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, TITLE, AND NON-INFRINGEMENT.

6.2 THE COMPANY DOES NOT WARRANT THAT THE SOFTWARE WILL BE UNINTERRUPTED, ERROR-FREE, SECURE, OR FREE OF VIRUSES OR OTHER HARMFUL COMPONENTS.

6.3 THE SOFTWARE INVOLVES FINANCIAL TRADING FUNCTIONALITY. THE COMPANY MAKES NO REPRESENTATIONS OR WARRANTIES REGARDING THE ACCURACY, RELIABILITY, OR COMPLETENESS OF ANY FINANCIAL DATA, CALCULATIONS, OR TRADING SIGNALS PROVIDED BY THE SOFTWARE. YOU ACKNOWLEDGE THAT TRADING INVOLVES SUBSTANTIAL RISK OF LOSS AND THAT PAST PERFORMANCE IS NOT INDICATIVE OF FUTURE RESULTS.

6.4 YOU USE THE SOFTWARE ENTIRELY AT YOUR OWN RISK. THE COMPANY SHALL NOT BE LIABLE FOR ANY FINANCIAL LOSSES INCURRED THROUGH THE USE OF THE SOFTWARE.

7. LIMITATION OF LIABILITY

7.1 IN NO EVENT SHALL THE COMPANY, ITS OFFICERS, DIRECTORS, EMPLOYEES, AGENTS, OR AFFILIATES BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, PUNITIVE, OR EXEMPLARY DAMAGES, INCLUDING BUT NOT LIMITED TO DAMAGES FOR LOSS OF PROFITS, GOODWILL, DATA, TRADING LOSSES, OR OTHER INTANGIBLE LOSSES, REGARDLESS OF WHETHER SUCH DAMAGES WERE FORESEEABLE AND WHETHER THE COMPANY WAS ADVISED OF THE POSSIBILITY THEREOF.

7.2 THE COMPANY'S TOTAL AGGREGATE LIABILITY ARISING OUT OF OR RELATED TO THIS AGREEMENT SHALL NOT EXCEED ONE DOLLAR ($1.00 USD).

8. INDEMNIFICATION

You agree to indemnify, defend, and hold harmless the Company and its officers, directors, employees, agents, and affiliates from and against any and all claims, damages, losses, liabilities, costs, and expenses (including reasonable attorneys' fees) arising out of or related to your use of the Software, your violation of this Agreement, or your violation of any law or the rights of any third party.

9. TERMINATION

9.1 This Agreement is effective until terminated. The Company may terminate this Agreement at any time, for any reason, with or without notice.

9.2 Upon termination, you must immediately cease all use of the Software and destroy all copies in your possession or control.

9.3 Sections 2, 3, 4, 6, 7, 8, and 10 shall survive any termination or expiration of this Agreement.

10. GOVERNING LAW & JURISDICTION

10.1 This Agreement shall be governed by and construed in accordance with the laws of the jurisdiction indicated in your registration, without regard to conflict of law principles.

10.2 Any disputes arising under or in connection with this Agreement shall be subject to the exclusive jurisdiction of the courts in the jurisdiction of your registered address.

10.3 You acknowledge that laws governing software licensing, data privacy, and financial trading may vary by jurisdiction, and you are solely responsible for compliance with all applicable local laws.

11. GENERAL PROVISIONS

11.1 This Agreement constitutes the entire agreement between you and the Company with respect to the Software and supersedes all prior or contemporaneous understandings.

11.2 If any provision of this Agreement is held to be invalid or unenforceable, the remaining provisions shall continue in full force and effect.

11.3 The Company's failure to enforce any right or provision of this Agreement shall not constitute a waiver of such right or provision.

11.4 This Agreement may not be assigned or transferred by you without the Company's prior written consent.

11.5 The Company reserves the right to modify this Agreement at any time. Continued use of the Software after any modification constitutes acceptance of the modified terms.

Copyright (c) ${new Date().getFullYear()} Signal Forge Laboratory. All rights reserved.
Sentinel Pulse is a trademark of Signal Forge Laboratory.`;

interface Props {
  onRegistered: () => void;
}

export function BetaRegistrationModal({ onRegistered }: Props) {
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    ssn_last4: '',
    address_street: '',
    address_city: '',
    address_state: '',
    address_zip: '',
    address_country: 'United States',
  });
  const [agreed, setAgreed] = useState(false);
  const [showAgreement, setShowAgreement] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const update = (field: string, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    setError('');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!agreed) {
      setError('You must read and accept the Beta Tester Agreement.');
      return;
    }
    if (!form.first_name || !form.last_name || !form.email) {
      setError('First name, last name, and email are required.');
      return;
    }
    if (form.ssn_last4.length !== 4 || !/^\d{4}$/.test(form.ssn_last4)) {
      setError('Last 4 of SSN must be exactly 4 digits.');
      return;
    }
    if (!form.address_street || !form.address_city || !form.address_state || !form.address_zip) {
      setError('Full address is required.');
      return;
    }

    setSubmitting(true);
    try {
      const jurisdiction = `${form.address_state}, ${form.address_country}`;
      await apiFetch('/api/beta/register', {
        method: 'POST',
        body: JSON.stringify({
          ...form,
          agreement_accepted: true,
          agreement_version: AGREEMENT_VERSION,
          jurisdiction,
        }),
      });
      onRegistered();
    } catch (err: any) {
      setError(err.message || 'Registration failed.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-md" data-testid="beta-registration-modal">
      <div className="glass border border-border rounded-2xl w-full max-w-lg max-h-[92vh] flex flex-col shadow-2xl mx-4">
        {/* Header */}
        <div className="px-6 py-5 border-b border-border text-center shrink-0">
          <div className="flex items-center justify-center gap-2 mb-1">
            <Shield size={20} className="text-primary" />
            <h1 className="text-xl font-bold text-foreground tracking-tight">Sentinel Pulse</h1>
          </div>
          <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-medium">
            Signal Forge Laboratory — Beta Program Registration
          </p>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-auto px-6 py-5 space-y-4">
          {/* Name */}
          <div className="grid grid-cols-2 gap-3">
            <Field label="First Name *" testId="beta-first-name" value={form.first_name} onChange={(v) => update('first_name', v)} />
            <Field label="Last Name *" testId="beta-last-name" value={form.last_name} onChange={(v) => update('last_name', v)} />
          </div>

          {/* Contact */}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Email Address *" testId="beta-email" type="email" value={form.email} onChange={(v) => update('email', v)} />
            <Field label="Phone (optional)" testId="beta-phone" type="tel" value={form.phone} onChange={(v) => update('phone', v)} />
          </div>

          {/* SSN */}
          <Field
            label="Last 4 of SSN *"
            testId="beta-ssn4"
            value={form.ssn_last4}
            maxLength={4}
            pattern="\d{4}"
            placeholder="0000"
            onChange={(v) => { if (/^\d{0,4}$/.test(v)) update('ssn_last4', v); }}
          />

          {/* Address */}
          <Field label="Street Address *" testId="beta-street" value={form.address_street} onChange={(v) => update('address_street', v)} />
          <div className="grid grid-cols-2 gap-3">
            <Field label="City *" testId="beta-city" value={form.address_city} onChange={(v) => update('address_city', v)} />
            <Field label="State / Province *" testId="beta-state" value={form.address_state} onChange={(v) => update('address_state', v)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="ZIP / Postal Code *" testId="beta-zip" value={form.address_zip} onChange={(v) => update('address_zip', v)} />
            <Field label="Country *" testId="beta-country" value={form.address_country} onChange={(v) => update('address_country', v)} />
          </div>

          {/* Agreement */}
          <div className="border border-border rounded-lg overflow-hidden">
            <button
              type="button"
              onClick={() => setShowAgreement(!showAgreement)}
              className="w-full flex items-center justify-between px-4 py-3 hover:bg-secondary/30 transition-colors"
              data-testid="toggle-agreement"
            >
              <span className="text-xs font-semibold text-foreground flex items-center gap-2">
                <Shield size={12} className="text-primary" />
                Beta Tester License Agreement
              </span>
              {showAgreement ? <ChevronUp size={14} className="text-muted-foreground" /> : <ChevronDown size={14} className="text-muted-foreground" />}
            </button>
            {showAgreement && (
              <div className="border-t border-border px-4 py-3 max-h-[300px] overflow-auto">
                <pre className="text-[10px] text-muted-foreground/80 whitespace-pre-wrap font-mono leading-relaxed">
                  {AGREEMENT_TEXT}
                </pre>
              </div>
            )}
          </div>

          <label className="flex items-start gap-3 cursor-pointer" data-testid="accept-agreement-label">
            <input
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-border bg-secondary accent-primary"
              data-testid="accept-agreement-checkbox"
            />
            <span className="text-xs text-muted-foreground leading-relaxed">
              I have read and agree to the <strong className="text-foreground">Beta Tester License Agreement</strong>. I understand that this software is provided as-is, involves financial risk, and that Signal Forge Laboratory is not liable for any losses. I agree to all restrictions on use, reverse engineering, and distribution.
            </span>
          </label>

          {error && (
            <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2" data-testid="beta-error">{error}</p>
          )}

          <button
            type="submit"
            disabled={submitting || !agreed}
            className={`w-full py-3 rounded-lg font-semibold text-sm transition-all ${
              agreed && !submitting
                ? 'bg-primary text-primary-foreground hover:bg-primary/90 shadow-lg shadow-primary/25'
                : 'bg-secondary text-muted-foreground cursor-not-allowed'
            }`}
            data-testid="beta-submit"
          >
            {submitting ? 'Registering...' : 'Accept Agreement & Register'}
          </button>

          <p className="text-[9px] text-muted-foreground/50 text-center">
            Jurisdiction will be set to: {form.address_state ? `${form.address_state}, ${form.address_country}` : 'Per your registered address'}
          </p>
        </form>
      </div>
    </div>
  );
}

function Field({
  label, testId, value, onChange, type = 'text', maxLength, pattern, placeholder,
}: {
  label: string; testId: string; value: string; onChange: (v: string) => void;
  type?: string; maxLength?: number; pattern?: string; placeholder?: string;
}) {
  return (
    <div>
      <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium block mb-1">{label}</label>
      <input
        data-testid={testId}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        maxLength={maxLength}
        pattern={pattern}
        placeholder={placeholder}
        className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1 focus:ring-offset-background text-foreground placeholder:text-muted-foreground/30"
      />
    </div>
  );
}
