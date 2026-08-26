import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Button, Input, Select, FormField, FormSection, Icon } from '@shared'
import api from '../lib/axios'

type FormErrors = Partial<Record<keyof FormData, string>>

interface FormData {
  username: string
  password: string
  confirmPassword: string
  fullName: string
  phone: string
  departmentId: string
  pin: string
  confirmPin: string
}

interface Department { id: string; name: string }

export default function RegisterScreen() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<FormErrors>({})

  // Public, unauthenticated — nobody has a token yet at signup. Real DB ids,
  // not the hardcoded fake strings this used to send (which 404'd every time).
  const { data: departments = [] } = useQuery<Department[]>({
    queryKey: ['public-departments'],
    queryFn: () => api.get<Department[]>('/auth/departments').then(r => r.data),
    staleTime: 5 * 60_000,
  })

  const [form, setForm] = useState<FormData>({
    username: '',
    password: '',
    confirmPassword: '',
    fullName: '',
    phone: '',
    departmentId: '',
    pin: '',
    confirmPin: '',
  })

  function updateField<K extends keyof FormData>(field: K, value: string) {
    setForm(f => ({ ...f, [field]: value }))
    // Clear error when user types
    if (errors[field]) {
      setErrors(e => { const n = { ...e }; delete n[field]; return n })
    }
  }

  function validateStep1(): boolean {
    const e: FormErrors = {}
    if (!form.username.trim()) e.username = 'Username is required'
    else if (form.username.length < 3) e.username = 'At least 3 characters'
    if (!form.fullName.trim()) e.fullName = 'Full name is required'
    if (!form.phone.trim()) e.phone = 'Phone number is required'
    if (!form.departmentId) e.departmentId = 'Select your department'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  function validateStep2(): boolean {
    const e: FormErrors = {}
    if (!form.password) e.password = 'Password is required'
    else if (form.password.length < 6) e.password = 'At least 6 characters'
    if (form.password !== form.confirmPassword) e.confirmPassword = 'Passwords do not match'
    if (!form.pin) e.pin = 'PIN is required'
    else if (!/^\d{4}$/.test(form.pin)) e.pin = 'Exactly 4 digits'
    if (form.pin !== form.confirmPin) e.confirmPin = 'PINs do not match'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  async function handleSubmit() {
    if (!validateStep2()) return
    setLoading(true)
    try {
      await api.post('/auth/register', {
        username: form.username.trim().toLowerCase(),
        password: form.password,
        full_name: form.fullName.trim(),
        phone: form.phone.trim(),
        department_id: form.departmentId,
        pin: form.pin,
      })
      setStep(3)
    } catch (err: any) {
      const msg = err?.response?.data?.error || 'Registration failed'
      setErrors({ username: msg })
    } finally {
      setLoading(false)
    }
  }

  const stepLabels = ['About You', 'Security', 'Done']

  return (
    <div className="min-h-screen flex items-center justify-center p-4"
      style={{ background: 'linear-gradient(160deg, rgba(35,18,12,0.9) 0%, rgba(18,9,6,0.7) 100%)' }}>
      
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md glass-card p-6 md:p-8"
      >
        {/* Header */}
        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold text-ink-primary font-serif">Join Kurahia</h1>
          <p className="text-sm text-ink-tertiary mt-1">Create your staff account</p>
        </div>

        {/* Stepper */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {[1, 2, 3].map(s => (
            <div key={s} className="flex items-center gap-2">
              <div className={[
                'w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-colors',
                s === step ? 'bg-primary-main text-white' 
                  : s < step ? 'bg-primary-main/30 text-primary-light'
                  : 'bg-white/10 text-ink-tertiary'
              ].join(' ')}>
                {s < step ? <Icon name="check" size={16} strokeWidth={2.5} label={`Step ${s} complete`} /> : s}
              </div>
              <span className={[
                'text-xs hidden sm:block',
                s === step ? 'text-ink-primary font-medium' : 'text-ink-tertiary'
              ].join(' ')}>
                {stepLabels[s-1]}
              </span>
              {s < 3 && <div className="w-6 h-px bg-white/15" />}
            </div>
          ))}
        </div>

        {/* STEP 1: About You */}
        {step === 1 && (
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            className="space-y-5"
          >
            <FormSection title="About You" description="Tell us who you are and where you work">

              <FormField
                label="Username"
                htmlFor="username"
                required
                error={errors.username}
                help="This is what you'll use to log in"
              >
                <Input
                  id="username"
                  value={form.username}
                  onChange={e => updateField('username', e.target.value)}
                  placeholder="e.g. mwangi_kitchen"
                  autoComplete="username"
                  autoFocus
                />
              </FormField>

              <FormField
                label="Full Name"
                htmlFor="fullName"
                required
                error={errors.fullName}
              >
                <Input
                  id="fullName"
                  value={form.fullName}
                  onChange={e => updateField('fullName', e.target.value)}
                  placeholder="Your full name"
                  autoComplete="name"
                />
              </FormField>

              <FormField
                label="Phone Number"
                htmlFor="phone"
                required
                error={errors.phone}
                help="For shift alerts and emergency contact"
              >
                <Input
                  id="phone"
                  type="tel"
                  inputMode="tel"
                  value={form.phone}
                  onChange={e => updateField('phone', e.target.value)}
                  placeholder="+254 712 345 678"
                  autoComplete="tel"
                />
              </FormField>

              <FormField
                label="Department"
                htmlFor="department"
                required
                error={errors.departmentId}
              >
                <Select
                  id="department"
                  value={form.departmentId}
                  onChange={e => updateField('departmentId', e.target.value)}
                >
                  <option value="" disabled>Select your department</option>
                  {departments.map(d => (
                    <option key={d.id} value={d.id}>{d.name}</option>
                  ))}
                </Select>
              </FormField>

            </FormSection>

            <Button
              onClick={() => validateStep1() && setStep(2)}
              className="w-full py-4 text-base font-bold"
            >
              Continue to Security
            </Button>
          </motion.div>
        )}

        {/* STEP 2: Security */}
        {step === 2 && (
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            className="space-y-5"
          >
            <FormSection title="Create Password" description="Choose a strong password">

              <FormField
                label="Password"
                htmlFor="password"
                required
                error={errors.password}
                help="At least 6 characters"
              >
                <Input
                  id="password"
                  type="password"
                  value={form.password}
                  onChange={e => updateField('password', e.target.value)}
                  placeholder="••••••"
                  autoComplete="new-password"
                />
              </FormField>

              <FormField
                label="Confirm Password"
                htmlFor="confirmPassword"
                required
                error={errors.confirmPassword}
              >
                <Input
                  id="confirmPassword"
                  type="password"
                  value={form.confirmPassword}
                  onChange={e => updateField('confirmPassword', e.target.value)}
                  placeholder="••••••"
                  autoComplete="new-password"
                />
              </FormField>

            </FormSection>

            <FormSection title="Create PIN" description="For quick daily login">

              <FormField
                label="4-Digit PIN"
                htmlFor="pin"
                required
                error={errors.pin}
                help="You'll enter this every day to clock in"
              >
                <Input
                  id="pin"
                  type="password"
                  inputMode="numeric"
                  maxLength={4}
                  value={form.pin}
                  onChange={e => updateField('pin', e.target.value.replace(/\D/g, ''))}
                  placeholder="1234"
                  autoComplete="off"
                />
              </FormField>

              <FormField
                label="Confirm PIN"
                htmlFor="confirmPin"
                required
                error={errors.confirmPin}
              >
                <Input
                  id="confirmPin"
                  type="password"
                  inputMode="numeric"
                  maxLength={4}
                  value={form.confirmPin}
                  onChange={e => updateField('confirmPin', e.target.value.replace(/\D/g, ''))}
                  placeholder="1234"
                  autoComplete="off"
                />
              </FormField>

            </FormSection>

            <div className="flex gap-3">
              <Button
                variant="ghost"
                onClick={() => setStep(1)}
                className="flex-1 py-4"
              >
                Back
              </Button>
              <Button
                onClick={handleSubmit}
                loading={loading}
                className="flex-1 py-4 text-base font-bold"
              >
                Create Account
              </Button>
            </div>
          </motion.div>
        )}

        {/* STEP 3: Success */}
        {step === 3 && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="text-center space-y-5 py-4"
          >
            <div className="w-20 h-20 rounded-full bg-status-paid/15 border border-status-paid/25
              flex items-center justify-center mx-auto">
              <Icon name="celebrate" size={40} strokeWidth={1.5} className="text-status-paid" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-ink-primary">Account Created!</h2>
              <p className="text-sm text-ink-secondary mt-2 leading-relaxed">
                Your manager will review and activate your account.
                You'll receive a notification when approved.
              </p>
            </div>
            <Button onClick={() => navigate('/login')} className="w-full py-4 text-base font-bold">
              Go to Login
            </Button>
          </motion.div>
        )}

        {/* Footer */}
        {step !== 3 && (
          <p className="mt-6 text-center text-sm text-ink-tertiary">
            Already have an account?{' '}
            <button
              type="button"
              onClick={() => navigate('/login')}
              className="text-primary-main hover:underline font-medium"
            >
              Log in
            </button>
          </p>
        )}
      </motion.div>
    </div>
  )
}
